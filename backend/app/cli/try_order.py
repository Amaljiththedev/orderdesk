"""Upload generated test orders through the real API, wait for the worker, compare with the labels.

    python -m app.cli.try_order gen-0003            # one order
    python -m app.cli.try_order gen-0001 gen-0002   # several
    python -m app.cli.try_order --reprocess gen-0005  # run an already-uploaded order again (e.g. new prompt)

Uses real LLM calls (Groq tokens). Run inside the api container.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import select

from app.db.models import Document, Order, OrderLine
from app.db.session import SessionLocal

API = "http://localhost:8000"
GEN = Path("/data/eval/generated")


def norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def upload(case: str) -> int:
    label = json.loads((GEN / f"{case}.json").read_text())
    path = GEN / label["document"]
    r = httpx.post(f"{API}/documents", files={"file": (path.name, path.read_bytes())}, timeout=30)
    r.raise_for_status()
    d = r.json()
    if d["duplicate"]:
        print(f"{case}: already uploaded as document {d['id']} (status {d['status']})")
    return d["id"]


def reset(doc_id: int) -> None:
    """Delete the previous order for this document and queue it again."""
    with SessionLocal() as db:
        for o in db.scalars(select(Order).where(Order.document_id == doc_id)).all():
            db.query(OrderLine).filter(OrderLine.order_id == o.id).delete()
            db.delete(o)
        db.flush()
        doc = db.get(Document, doc_id)
        doc.status, doc.error = "queued", None
        db.commit()


def wait(doc_id: int, timeout: int = 120) -> str:
    for _ in range(timeout):
        status = httpx.get(f"{API}/documents/{doc_id}", timeout=10).json()["status"]
        if status not in ("queued", "processing", "extracted"):
            return status
        time.sleep(1)
    return "timeout"


def compare(case: str, doc_id: int) -> bool:
    label = json.loads((GEN / f"{case}.json").read_text())
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)
        order = db.scalar(select(Order).where(Order.document_id == doc_id))
        if not order:
            print(f"  no order created. status={doc.status} error={doc.error}")
            return False
        lines = db.scalars(select(OrderLine).where(OrderLine.order_id == order.id)
                           .order_by(OrderLine.line_no)).all()

    ok = True
    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(f"  {'OK  ' if good else 'DIFF'} {name}: got {got!r}  expected {want!r}")

    check("po_number", order.po_number, label["po_number"])
    check("delivery_date", order.delivery_date.isoformat() if order.delivery_date else None, label["delivery_date"])
    check("line count", len(lines), len(label["lines"]))
    for i, (got, want) in enumerate(zip(lines, label["lines"]), 1):
        pieces = "qty_in_pieces" in want["mess"]
        good = (norm(got.raw_text) == norm(want["raw"]) and float(got.qty) == want["written_qty"]
                and (got.unit == "pcs") == pieces)
        ok &= good
        print(f"  {'OK  ' if good else 'DIFF'} line {i}: got {got.raw_text!r} x{float(got.qty):g}"
              f"{' pcs' if got.unit == 'pcs' else ''}   expected {want['raw']!r} x{want['written_qty']}"
              f"{' pcs' if pieces else ''}")
    return ok


def main(args: list[str]) -> None:
    reprocess = "--reprocess" in args
    cases = [a for a in args if not a.startswith("--")] or ["gen-0003"]
    passed = 0
    for case in cases:
        doc_id = upload(case)
        if reprocess:
            reset(doc_id)
        status = wait(doc_id)
        print(f"\n{case} -> document {doc_id}, status {status}")
        passed += compare(case, doc_id)
    print(f"\n{passed}/{len(cases)} orders fully correct")


if __name__ == "__main__":
    main(sys.argv[1:])
