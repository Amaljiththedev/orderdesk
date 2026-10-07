"""Background worker: picks queued documents and processes them, one at a time.

    python -m app.workers.worker          # run forever
    python -m app.workers.worker --once   # process one document and exit (handy for testing)

The queue is just the documents table. FOR UPDATE SKIP LOCKED lets several workers run side by
side without ever grabbing the same document, and no extra queue service is needed.
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import UPLOAD_DIR
from app.core.extraction import ExtractionFailed, extract_order
from app.core.text_extract import extract
from app.db.models import Customer, Document, Order, OrderLine
from app.db.session import SessionLocal

log = logging.getLogger("worker")
POLL_SECONDS = 2


def claim_next(db: Session) -> Document | None:
    """Atomically take the oldest queued document and mark it as processing."""
    doc = db.scalar(
        select(Document)
        .where(Document.status == "queued")
        .order_by(Document.id)
        .limit(1)
        .with_for_update(skip_locked=True)  # other workers skip rows we have locked
    )
    if doc:
        doc.status = "processing"
        db.commit()  # releases the lock; the status now tells other workers it's taken
    return doc


def find_customer(db: Session, text: str) -> Customer | None:
    """Match the sender's email address from the From: header. Name matching comes later."""
    m = re.search(r"^From:.*?<?([\w.+-]+@[\w.-]+)>?", text, flags=re.M)
    return db.scalar(select(Customer).where(Customer.email == m.group(1).lower())) if m else None


def save_order(db: Session, doc: Document, ex) -> Order:
    customer = find_customer(db, doc.text or "")
    order = Order(document_id=doc.id, customer_id=customer.id if customer else None,
                  po_number=ex.po_number, delivery_date=ex.delivery_date,
                  status="needs_review", idempotency_key=doc.sha256)
    db.add(order)
    db.flush()
    for i, ln in enumerate(ex.lines, 1):
        db.add(OrderLine(order_id=order.id, line_no=i, raw_text=ln.raw_text,
                         qty=ln.qty or 0, unit="pcs" if ln.qty_in_pieces else ln.unit,
                         needs_review=True))  # nothing is matched yet (Phase 3)
    return order


def process(db: Session, doc: Document) -> None:
    """Text -> structured order. Matching, pricing and routing are added in Phase 3."""
    try:
        path = next(UPLOAD_DIR.glob(f"{doc.sha256}.*"))
        doc.text, doc.ocr_used = extract(path)
        doc.status = "extracted"
        db.commit()
        ex = extract_order(db, doc.text, doc.received_at.date(), document_id=doc.id)
        save_order(db, doc, ex)
        doc.status = "done"
        doc.error = None
    except ExtractionFailed as e:  # readable text, but the LLM couldn't structure it
        doc.status = "needs_review"
        doc.error = str(e)[:2000]
    except Exception as e:  # one bad file must never stop the worker
        log.exception("document %s failed", doc.id)
        doc.status = "failed"
        doc.error = f"{type(e).__name__}: {e}"[:2000]
    db.commit()


def run_once() -> bool:
    """Process one document if there is one. Returns True if something was processed."""
    with SessionLocal() as db:
        doc = claim_next(db)
        if not doc:
            return False
        log.info("processing document %s (%s)", doc.id, doc.filename)
        process(db, doc)
        log.info("document %s -> %s", doc.id, doc.status)
        return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if a.once:
        run_once()
        return
    log.info("worker started")
    while True:
        if not run_once():
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
