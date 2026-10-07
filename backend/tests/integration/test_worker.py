"""The worker against the real database: queued -> extracted, bad files -> failed."""
import hashlib
import uuid

from app.api.documents import UPLOAD_DIR
from app.db.models import Document
from app.db.session import SessionLocal
from app.workers.worker import claim_next, process


def make_doc(db, content: bytes, ext: str) -> Document:
    digest = hashlib.sha256(content).hexdigest()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{digest}{ext}").write_bytes(content)
    doc = Document(source="test", filename=f"t{ext}", sha256=digest, status="queued")
    db.add(doc)
    db.commit()
    return doc


def test_email_is_extracted():
    body = f"From: a@b.co.uk\nSubject: Order\n\n20 x cu elbow 15mm comp\nref {uuid.uuid4()}\n".encode()
    with SessionLocal() as db:
        doc = make_doc(db, body, ".eml")
        process(db, doc)
        db.refresh(doc)
        assert doc.status == "extracted"
        assert "cu elbow 15mm comp" in doc.text
        db.delete(doc)
        db.commit()


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
