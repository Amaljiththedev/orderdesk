"""Matching eval: feed each labelled line's text straight to the matcher (no LLM, no tokens).

    python -m evals.match_eval                 # all 300 generated orders
    python -m evals.match_eval --limit 50

Reports top-1 / top-5 accuracy by kind of mess, and the precision vs auto-approve trade-off
for a range of confidence thresholds, which is how the routing threshold gets chosen.
Lines with an unknown customer reference should NOT be matched: the right answer is "ask a person".
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from collections import Counter

from app.core.history import brand_of, names_a_brand, preference_from_counts
from app.core.matching import match_line
from app.db.models import Customer
from app.db.session import SessionLocal

EVAL = Path("/data/eval")
THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="generated")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--history", action="store_true",
                    help="use the first half of orders as checked history; score only the second half")
    a = ap.parse_args()

    labels = [json.loads(p.read_text()) for p in sorted((EVAL / a.split).glob("*.json"))]
    labels = labels[: a.limit] if a.limit else labels
    prefs = {}
    if a.history:
        # no leakage: preferences come only from the history half, scoring only on the other half
        half = len(labels) // 2
        counts: dict[str, Counter] = {}
        for label in labels[:half]:
            for ln in label["lines"]:
                b = brand_of(ln["product_code"])
                if b and not names_a_brand(ln["raw"]):
                    counts.setdefault(label["customer_account"], Counter())[b] += 1
        prefs = {acct: preference_from_counts(c) for acct, c in counts.items()}
        labels = labels[half:]
        print(f"history: {half} orders, {sum(p is not None for p in prefs.values())} customers with a clear brand habit")
    rows = []
    with SessionLocal() as db:
        customers = dict(db.execute(select(Customer.account_code, Customer.id)).all())
        for label in labels:
            cid = customers.get(label["customer_account"])
            for ln in label["lines"]:
                pieces = "qty_in_pieces" in ln["mess"]
                m = match_line(db, ln["raw"], cid, qty=ln["written_qty"], unit="pcs" if pieces else None,
                               preference=prefs.get(label["customer_account"]) if a.history else None)
                codes = [c.code for c in m.candidates]
                unknown_ref = ln.get("alias_known") is False and "customer_part_number" in ln["mess"]
                rows.append({
                    "id": label["id"], "raw": ln["raw"], "want": ln["product_code"],
                    "mess": ln["mess"] or ["clean"], "method": m.method, "conf": m.confidence,
                    "top1": bool(codes) and codes[0] == ln["product_code"],
                    "top5": ln["product_code"] in codes, "got": codes[0] if codes else None,
                    "unknown_ref": unknown_ref, "reason": m.reason,
                })
        print(f"{len(rows)} lines from {len(labels)} orders\n")

    def pct(n, d):
        return f"{100 * n / d:5.1f}% ({n}/{d})" if d else "  n/a"

    matchable = [r for r in rows if not r["unknown_ref"]]
    print("== overall (lines that can be matched) ==")
    print(f"  top-1 correct    {pct(sum(r['top1'] for r in matchable), len(matchable))}")
    print(f"  in top-5         {pct(sum(r['top5'] for r in matchable), len(matchable))}")
    unk = [r for r in rows if r["unknown_ref"]]
    print(f"  unknown refs correctly left unmatched  {pct(sum(r['method'] is None for r in unk), len(unk))}")

    print("\n== by method ==")
    by_m = defaultdict(list)
    for r in matchable:
        by_m[r["method"]].append(r)
    for k, v in by_m.items():
        print(f"  {str(k):<8} lines {len(v):>4}   top-1 {pct(sum(r['top1'] for r in v), len(v))}")

    print("\n== by kind of mess (top-1 / top-5) ==")
    by_t = defaultdict(list)
    for r in matchable:
        for t in r["mess"]:
            by_t[t].append(r)
    for t, v in sorted(by_t.items(), key=lambda x: sum(r["top1"] for r in x[1]) / len(x[1])):
        print(f"  {t:<22} {pct(sum(r['top1'] for r in v), len(v))}   top-5 {pct(sum(r['top5'] for r in v), len(v))}")

    print("\n== routing threshold: auto-approve if confidence >= t ==")
    print("   t     auto-approved        precision of auto-approved")
    curve = []
    for t in THRESHOLDS:
        auto = [r for r in rows if r["method"] is not None and r["conf"] >= t]
        right = sum(r["top1"] for r in auto)
        curve.append({"t": t, "auto": len(auto), "correct": right})
        print(f"  {t:.2f}  {pct(len(auto), len(rows)):<20} {pct(right, len(auto))}")

    wrong = [r for r in matchable if not r["top1"]][:15]
    print("\n== sample misses ==")
    for r in wrong:
        print(f"  {r['id']} [{','.join(r['mess'])}] {r['raw']!r}\n      want {r['want']}  got {r['got']}  conf {r['conf']}")

    out = EVAL / "results" / f"match_{a.split}_{datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"curve": curve, "rows": rows}, indent=1))
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
