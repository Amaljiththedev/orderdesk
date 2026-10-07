"""The worker against the real database: queued -> extracted, bad files -> failed."""
import hashlib
import uuid

import pytest

from app.api.documents import UPLOAD_DIR
from app.core import extraction
from app.core.extraction import ExtractedOrder, ExtractionFailed
from app.db.models import Document, Order, OrderLine
from app.workers import worker
from app.db.session import SessionLocal
from app.workers.worker import claim_next, process


def make_doc(db, content: bytes, ext: str, status: str = "processing") -> Document:
    # "processing" by default so the running worker service never grabs a test document
    digest = hashlib.sha256(content).hexdigest()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{digest}{ext}").write_bytes(content)
    doc = Document(source="test", filename=f"t{ext}", sha256=digest, status=status)
    db.add(doc)
    db.commit()
    return doc


def cleanup(db, doc):
    for o in db.query(Order).filter(Order.document_id == doc.id).all():
        db.query(OrderLine).filter(OrderLine.order_id == o.id).delete()
        db.delete(o)
    db.flush()  # no ORM relationship links these tables, so delete orders before their document
    db.delete(doc)
    db.commit()


def test_email_becomes_order(monkeypatch):
    fake = ExtractedOrder.model_validate({"po_number": "PO1", "lines": [
        {"raw_text": "cu elbow 15mm comp", "qty": 20}, {"raw_text": "ref 44-112", "qty": 2, "qty_in_pieces": True}]})
    monkeypatch.setattr(worker, "extract_order", lambda *a, **k: fake)   # no real LLM call
    body = f"From: a@b.co.uk\nSubject: Order\n\n20 x cu elbow 15mm comp\nref {uuid.uuid4()}\n".encode()
    with SessionLocal() as db:
        doc = make_doc(db, body, ".eml")
        process(db, doc)
        db.refresh(doc)
        assert doc.status == "done"
        assert "cu elbow 15mm comp" in doc.text
        order = db.query(Order).filter(Order.document_id == doc.id).one()
        lines = db.query(OrderLine).filter(OrderLine.order_id == order.id).order_by(OrderLine.line_no).all()
        assert order.po_number == "PO1" and [l.raw_text for l in lines] == ["cu elbow 15mm comp", "ref 44-112"]
        assert lines[1].unit == "pcs"
        cleanup(db, doc)


def test_unreadable_order_goes_to_review(monkeypatch):
    def boom(*a, **k):
        raise ExtractionFailed("invalid output after retry")
    monkeypatch.setattr(worker, "extract_order", boom)
    with SessionLocal() as db:
        doc = make_doc(db, f"From: a@b.c\n\nhello {uuid.uuid4()}".encode(), ".eml")
        process(db, doc)
        db.refresh(doc)
        assert doc.status == "needs_review" and "invalid output" in doc.error
        cleanup(db, doc)


def test_broken_pdf_fails_cleanly():
    with SessionLocal() as db:
        doc = make_doc(db, b"not a pdf " + uuid.uuid4().bytes, ".pdf")
        process(db, doc)
        db.refresh(doc)
        assert doc.status == "failed"
        assert doc.error
        db.delete(doc)
        db.commit()


def test_claim_skips_non_queued():
    with SessionLocal() as db:
        doc = make_doc(db, f"From: x@y.z\n\n{uuid.uuid4()}".encode(), ".eml")
        doc.status = "processing"
        db.commit()
        claimed = claim_next(db)
        assert claimed is None or claimed.id != doc.id
        if claimed:                      # put back anything we grabbed by accident
            claimed.status = "queued"
        db.delete(doc)
        db.commit()
