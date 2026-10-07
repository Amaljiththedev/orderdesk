"""Extraction eval: run the real extraction on labelled test orders and score it.

    python -m evals.run_eval --stage extract --limit 30          # quick run
    python -m evals.run_eval --stage extract --name full         # all 300 (resumable)

Calls the LLM directly (no API or worker), so the score measures extraction only.
Each finished order is appended to <name>.partial.jsonl, so hitting the daily token limit
loses nothing: run the same command again to continue. Results: /data/eval/results/.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.core.extraction import PROMPT_VERSION, ExtractionFailed, extract_order
from app.core.text_extract import extract
from app.llm.adapter import DailyLimitError
from app.db.models import LlmCall
from app.db.session import SessionLocal

EVAL = Path("/data/eval")
RESULTS = EVAL / "results"
GENERATED_RECEIVED = date(2026, 10, 5)  # the date every generated order was "sent" (see generator)


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def received_date(label: dict) -> date:
    if label.get("received_date"):
        return date.fromisoformat(label["received_date"])
    return GENERATED_RECEIVED


def score_case(label: dict, got: dict | None) -> dict:
    """Compare one extracted order with its label."""
    want_lines = label["lines"]
    row = {"id": label["id"], "format": label["format"], "n_lines": len(want_lines)}
    if got is None:
        row.update(failed=True, lines=[{"mess": l.get("mess", []), "text": False, "qty": False,
                                        "pieces": False} for l in want_lines])
        return row
    row["failed"] = False
    row["po"] = norm(got.get("po_number")) == norm(label.get("po_number"))
    row["date"] = got.get("delivery_date") == label.get("delivery_date")
    row["line_count"] = len(got["lines"]) == len(want_lines)

    # pair lines by exact (normalised) text first, then by position for whatever is left
    unused = list(range(len(got["lines"])))
    pairs = {}
    for i, w in enumerate(want_lines):
        j = next((j for j in unused if norm(got["lines"][j]["raw_text"]) == norm(w["raw"])), None)
        if j is not None:
            pairs[i] = j
            unused.remove(j)
    for i in range(len(want_lines)):
        if i not in pairs and unused:
            pairs[i] = unused.pop(0)

    lines = []
    for i, w in enumerate(want_lines):
        g = got["lines"][pairs[i]] if i in pairs else None
        pieces_want = "qty_in_pieces" in w.get("mess", [])
        lines.append({
            "mess": w.get("mess", []),
            "text": bool(g) and norm(g["raw_text"]) == norm(w["raw"]),
            "qty": bool(g) and g["qty"] is not None and float(g["qty"]) == float(w["written_qty"]),
            "pieces": bool(g) and bool(g["qty_in_pieces"]) == pieces_want,
            "pieces_want": pieces_want, "pieces_got": bool(g and g["qty_in_pieces"]),
            # kept so a miss can be inspected later without re-running the LLM
            "want_text": w["raw"], "got_text": g["raw_text"] if g else None,
            "want_qty": w["written_qty"], "got_qty": g["qty"] if g else None,
        })
    row["extra_lines"] = len(unused)
    row["lines"] = lines
    row["all_correct"] = (row["po"] and row["date"] and row["line_count"] and not unused
                          and all(l["text"] and l["qty"] and l["pieces"] for l in lines))
    return row


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "n/a"


def report(rows: list[dict], calls: dict) -> dict:
    ok = [r for r in rows if not r["failed"]]
    lines = [l for r in rows for l in r["lines"]]
    by_tag = defaultdict(lambda: [0, 0])
    for l in lines:
        for t in (l["mess"] or ["clean"]):
            by_tag[t][0] += l["text"] and l["qty"] and l["pieces"]
            by_tag[t][1] += 1
    by_format = defaultdict(lambda: [0, 0])
    for r in rows:
        by_format[r["format"]][0] += bool(r.get("all_correct"))
        by_format[r["format"]][1] += 1
    pw = sum(l["pieces_want"] for l in lines if "pieces_want" in l)
    pg = sum(l["pieces_got"] for l in lines if "pieces_got" in l)
    ptp = sum(l["pieces_want"] and l["pieces_got"] for l in lines if "pieces_want" in l)

    m = {
        "orders": len(rows),
        "extraction_failed": pct(len(rows) - len(ok), len(rows)),
        "orders_fully_correct": pct(sum(bool(r.get("all_correct")) for r in rows), len(rows)),
        "po_number_correct": pct(sum(r["po"] for r in ok), len(ok)),
        "delivery_date_correct": pct(sum(r["date"] for r in ok), len(ok)),
        "line_count_correct": pct(sum(r["line_count"] for r in ok), len(ok)),
        "lines": len(lines),
        "line_text_exact": pct(sum(l["text"] for l in lines), len(lines)),
        "line_qty_correct": pct(sum(l["qty"] for l in lines), len(lines)),
        "pieces_precision": pct(ptp, pg),
        "pieces_recall": pct(ptp, pw),
        "by_format_fully_correct": {k: pct(*v) for k, v in sorted(by_format.items())},
        "by_mess_line_correct": {k: pct(*v) for k, v in sorted(by_tag.items(), key=lambda x: x[1][0] / x[1][1])},
        **calls,
    }
    return m


def llm_stats(since: datetime) -> dict:
    with SessionLocal() as db:
        rows = db.execute(select(LlmCall.success, LlmCall.latency_ms, LlmCall.input_tokens,
                                 LlmCall.output_tokens, LlmCall.model)
                          .where(LlmCall.purpose == "extract", LlmCall.at >= since)).all()
    lat = sorted(r.latency_ms for r in rows if r.success)
    return {
        "llm_calls": len(rows), "llm_failed_calls": sum(not r.success for r in rows),
        "latency_p50_ms": int(statistics.median(lat)) if lat else None,
        "latency_p95_ms": lat[int(0.95 * (len(lat) - 1))] if lat else None,
        "tokens_in": sum(r.input_tokens or 0 for r in rows),
        "tokens_out": sum(r.output_tokens or 0 for r in rows),
        "models_used": sorted({r.model for r in rows if r.success}),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["extract"], default="extract")
    ap.add_argument("--split", choices=["generated", "held_out"], default="generated")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--name", default=None, help="run name; reuse it to resume")
    a = ap.parse_args()

    name = a.name or f"extract_{PROMPT_VERSION}_{a.split}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    ckpt = RESULTS / f"{name}.partial.jsonl"
    done = {}
    if ckpt.exists():
        for line in ckpt.read_text().splitlines():
            r = json.loads(line)
            if r.get("failed") and r.get("error_kind") == "llm":
                continue  # LLM outages are retried on resume; only real results are kept
            done[r["id"]] = r
        print(f"resuming {name}: {len(done)} already scored")

    labels = [json.loads(p.read_text()) for p in sorted((EVAL / a.split).glob("*.json"))]
    labels = labels[: a.limit] if a.limit else labels
    started = datetime.now().astimezone()
    rows = []
    with SessionLocal() as db:
        for i, label in enumerate(labels, 1):
            if label["id"] in done:
                rows.append(done[label["id"]])
                continue
            text, _ = extract(EVAL / a.split / label["document"])
            error = None
            try:
                got = extract_order(db, text, received_date(label)).model_dump(mode="json")
            except DailyLimitError:
                print(f"\ndaily token limit reached at {label['id']}; progress saved, run the same command later")
                break
            except ExtractionFailed as e:
                got, error = None, str(e)[:300]
            row = score_case(label, got)
            if error:
                row["error"] = error
                row["error_kind"] = "llm" if error.startswith("all models failed") else "invalid_output"
                print(f"      error: {error[:160]}")
            row["prompt_version"] = PROMPT_VERSION
            rows.append(row)
            with ckpt.open("a") as f:
                f.write(json.dumps(row) + "\n")
            mark = "ok " if row.get("all_correct") else ("FAIL" if row["failed"] else "diff")
            print(f"{i:>4}/{len(labels)} {mark} {label['id']} ({label['format']}, {row['n_lines']} lines)", flush=True)
            time.sleep(0.5)  # be gentle with the free tier

    m = report(rows, llm_stats(started))
    print(f"\n==== extraction eval: {name} (prompt {PROMPT_VERSION}, split {a.split}) ====")
    for k, v in m.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"      {kk:<22} {vv}")
        else:
            print(f"  {k:<26} {v}")
    out = RESULTS / f"{name}_{datetime.now():%Y%m%d-%H%M}.json"
    out.write_text(json.dumps({"name": name, "prompt_version": PROMPT_VERSION, "split": a.split,
                               "metrics": m, "rows": rows}, indent=2, default=str))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
