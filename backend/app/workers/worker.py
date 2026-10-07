"""Background worker: picks queued documents and processes them, one at a time.

    python -m app.workers.worker          # run forever
    python -m app.workers.worker --once   # process one document and exit (handy for testing)

The queue is just the documents table. FOR UPDATE SKIP LOCKED lets several workers run side by
side without ever grabbing the same document, and no extra queue service is needed.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import UPLOAD_DIR
from app.core.text_extract import extract
from app.db.models import Document
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


def process(db: Session, doc: Document) -> None:
    """Extract the text. Later steps add LLM extraction, matching and routing here."""
    try:
        path = next(UPLOAD_DIR.glob(f"{doc.sha256}.*"))
        doc.text, doc.ocr_used = extract(path)
        doc.status = "extracted"
        doc.error = None
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
