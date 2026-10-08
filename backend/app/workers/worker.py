"""Background worker: picks queued documents and processes them, one at a time.

    python -m app.workers.worker          # run forever
    python -m app.workers.worker --once   # process one document and exit (handy for testing)

The queue is just the documents table. FOR UPDATE SKIP LOCKED lets several workers run side by
side without ever grabbing the same document, and no extra queue service is needed.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
import re
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import UPLOAD_DIR
from dataclasses import asdict

from app.config import get_settings
from app.core.export import export_pending
from app.core.extraction import ExtractionFailed, extract_order
from app.core.matching import match_line, selling_qty
from app.core.pricing import unit_price
from app.core.text_extract import extract
from app.db.models import Customer, Document, Order, OrderLine, Product
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
    """Save the order, match and price every line, then route it."""
    threshold = get_settings().AUTO_APPROVE_THRESHOLD
    customer = find_customer(db, doc.text or "")
    order = Order(document_id=doc.id, customer_id=customer.id if customer else None,
                  po_number=ex.po_number, delivery_date=ex.delivery_date,
                  status="needs_review", idempotency_key=doc.sha256)
    db.add(order)
    db.flush()
    priced_on = doc.received_at.date() if doc.received_at else date.today()  # price on the day it arrived
    confidences = []
    for i, ln in enumerate(ex.lines, 1):
        unit = "pcs" if ln.qty_in_pieces else ln.unit
        m = match_line(db, ln.raw_text, order.customer_id, qty=ln.qty, unit=unit)
        product = db.get(Product, m.product_id) if m.product_id else None
        qty = selling_qty(ln.qty or 0, unit, product.pack_qty) if product else (ln.qty or 0)
        if product is None or m.confidence < threshold:
            why = m.reason
        elif ln.qty is None:
            why = "no quantity given"
        elif not float(qty).is_integer():
            why = f"{ln.qty:g} pieces is not a whole number of packs of {product.pack_qty}"
        else:
            why = None
        ok = why is None
        db.add(OrderLine(
            order_id=order.id, line_no=i, raw_text=ln.raw_text, qty=qty, unit=unit,
            product_id=product.id if product else None, match_method=m.method,
            match_score=m.confidence, candidates=[asdict(c) for c in m.candidates],
            reason=why,
            unit_price=unit_price(db, order.customer_id, product, priced_on) if product else None,
            needs_review=not ok,
        ))
        confidences.append(m.confidence if ok else 0.0)
    order.confidence = min(confidences) if confidences else 0.0
    # auto-approve only when we know who it's from and every line is confident
    if customer and confidences and all(c >= threshold for c in confidences):
        order.status = "auto_approved"
    return order


def process(db: Session, doc: Document) -> None:
    """Text -> structured order -> matched, priced and routed lines."""
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
        busy = run_once()
        with SessionLocal() as db:
            busy = export_pending(db) > 0 or busy  # approved orders go to the ERP
        if not busy:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
