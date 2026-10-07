"""Turn an incoming document into plain text for the LLM.

Emails: headers that matter (From, Subject, Date) plus the plain-text body.
PDFs: the text layer via pdfplumber; OCR with Tesseract only if a page has no text layer.
No HTTP or database code here, so it is easy to test on its own.
"""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path

import pdfplumber


def extract_email(data: bytes) -> str:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    body = msg.get_body(preferencelist=("plain", "html"))
    text = ""
    if body:
        # Decode the raw bytes ourselves: many real emails omit the charset, and the default
        # (ASCII) turns characters like "²" and "°" into garbage. UTF-8 is the safe fallback.
        raw = body.get_payload(decode=True) or b""
        charset = body.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            text = raw.decode("utf-8", errors="replace")
    header = "\n".join(f"{k}: {msg[k]}" for k in ("From", "Subject", "Date") if msg[k])
    return f"{header}\n\n{text}".strip()


def extract_pdf(path: Path) -> tuple[str, bool]:
    """Return (text, ocr_used)."""
    pages, ocr_used = [], False
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if not t.strip():  # scanned page: no text layer
                t = _ocr(page)
                ocr_used = True
            pages.append(t)
    return "\n\n".join(pages).strip(), ocr_used


def _ocr(page) -> str:
    import pytesseract  # imported here so the rest works without tesseract installed
    image = page.to_image(resolution=300).original
    return pytesseract.image_to_string(image)


def extract(path: Path) -> tuple[str, bool]:
    """Pick the extractor from the file extension. Returns (text, ocr_used)."""
    ext = path.suffix.lower()
    if ext == ".eml":
        return extract_email(path.read_bytes()), False
    if ext == ".pdf":
        return extract_pdf(path)
    raise ValueError(f"unsupported file type: {ext}")
