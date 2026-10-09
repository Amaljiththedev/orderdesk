"""Resolve-agent eval: run the agent on the lines matching was unsure about, score its picks.

    python -m evals.resolve_eval --limit 40     # first 40 unsure lines (uses Groq tokens)

Resumable: results go to <name>.partial.jsonl; rerun the same command to continue after a daily limit.
Key number: precision of the agent's picks. It may only auto-approve if that is ~99%.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.core.matching import match_line
from app.core.resolve import resolve_line
from app.db.models import Customer
from app.db.session import SessionLocal
from app.llm.adapter import DailyLimitError, chat_json

EVAL = Path("/data/eval")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="generated")
    ap.add_argument("--limit", type=int, default=40, help="max unsure lines to send to the agent")
    ap.add_argument("--name", default="resolve_v1")
    a = ap.parse_args()
    threshold = get_settings().AUTO_APPROVE_THRESHOLD
    out_dir = EVAL / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = out_dir / f"{a.name}.partial.jsonl"
    done = {}
    if partial.exists():
        for line in partial.read_text().splitlines():
            r = json.loads(line)
            done[(r["id"], r["line"])] = r

    labels = [json.loads(p.read_text()) for p in sorted((EVAL / a.split).glob("*.json"))]
    tokens = {"in": 0, "out": 0}

    def counted(db, **kw):
        res = chat_json(db, **kw)
        tokens["in"] += res.input_tokens or 0
        tokens["out"] += res.output_tokens or 0
        return res

    rows, stopped = [], None
    with SessionLocal() as db, partial.open("a") as f:
        customers = dict(db.execute(select(Customer.account_code, Customer.id)).all())
        for label in labels:
            cid = customers.get(label["customer_account"])
            for n, ln in enumerate(label["lines"], 1):
                if len(rows) >= a.limit or stopped:
                    break
                unit = "pcs" if "qty_in_pieces" in ln["mess"] else None
                m = match_line(db, ln["raw"], cid, qty=ln["written_qty"], unit=unit, preference=None)
                if m.confidence >= threshold or not m.candidates or m.method not in ("search", "history"):
                    continue
                key = (label["id"], n)
                if key in done:
                    rows.append(done[key])
                    continue
                try:
                    r = resolve_line(db, ln["raw"], ln["written_qty"], unit, m.candidates, cid, chat=counted)
                except DailyLimitError:
                    stopped = "daily token limit reached; rerun later to continue"
                    break
                if r is None:
                    continue                    # LLM outage: not scored, retried next run
                row = {"id": label["id"], "line": n, "raw": ln["raw"], "want": ln["product_code"],
                       "mess": ln["mess"], "before": m.candidates[0].code, "picked": r.code,
                       "reason": r.reason, "lookups": sum(s["action"] not in ("choose", "flag_for_human")
                                                          for s in r.steps)}
                rows.append(row)
                f.write(json.dumps(row) + "\n")
                f.flush()
            if len(rows) >= a.limit or stopped:
                break

    def pct(x, d):
        return f"{100 * x / d:5.1f}% ({x}/{d})" if d else "  n/a"

    picked = [r for r in rows if r["picked"]]
    right = [r for r in picked if r["picked"] == r["want"]]
    before = sum(r["before"] == r["want"] for r in rows)
    after = sum((r["picked"] or r["before"]) == r["want"] for r in rows)
    print(f"\n{len(rows)} unsure lines sent to the agent")
    print(f"  picked a product      {pct(len(picked), len(rows))}")
    print(f"  precision of picks    {pct(len(right), len(picked))}   <- must be ~99% before it may auto-approve")
    print(f"  flagged for a person  {pct(len(rows) - len(picked), len(rows))}")
    print(f"  top-1 on these lines  {pct(before, len(rows))} -> {pct(after, len(rows))}")
    fixed = sum(r["picked"] == r["want"] != r["before"] for r in picked)
    broke = sum(r["before"] == r["want"] != r["picked"] for r in picked)
    print(f"  fixed / broke         {fixed} / {broke}   (picks that changed the matcher's answer)")
    if rows:
        print(f"  avg lookups per line  {sum(r['lookups'] for r in rows) / len(rows):.1f}")
    print(f"  tokens this run       in {tokens['in']}  out {tokens['out']}")
    print("\n== wrong picks ==")
    for r in [r for r in picked if r["picked"] != r["want"]][:10]:
        print(f"  {r['id']} {r['raw']!r}\n      want {r['want']}  got {r['picked']}  ({r['reason']})")
    if stopped:
        print(f"\nSTOPPED: {stopped}")
    out = out_dir / f"{a.name}_{datetime.now():%Y%m%d-%H%M}.json"
    out.write_text(json.dumps(rows, indent=1))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
