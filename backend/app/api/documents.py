"""Receive order documents. Saving is cheap; reading them is the worker's job (step 3)."""
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document
from app.db.session import get_db

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path("/data/uploads")
ALLOWED = {".eml", ".pdf"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _out(d: Document) -> dict:
    return {"id": d.id, "filename": d.filename, "source": d.source, "status": d.status,
            "sha256": d.sha256, "received_at": d.received_at, "error": d.error}


@router.post("", status_code=201)
async def upload(file: UploadFile, source: str = "upload", db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, f"only {', '.join(sorted(ALLOWED))} files are accepted")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file larger than 10 MB")

    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.sha256 == digest))
    if existing:  # the same file is never processed twice
        return {**_out(existing), "duplicate": True}

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{digest}{ext}").write_bytes(data)  # named by hash, so names never clash

    doc = Document(source=source, filename=file.filename, sha256=digest, status="queued")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {**_out(doc), "duplicate": False}


@router.get("")
def list_documents(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.scalars(select(Document).order_by(Document.id.desc()).limit(min(limit, 200))).all()
    return [_out(d) for d in rows]


@router.get("/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(404, "document not found")
    return {**_out(d), "text": d.text}
