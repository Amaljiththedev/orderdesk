"""Review API: the inbox, one order in detail, fix a line, approve, reject.

Every reviewer fix teaches the system: it saves a customer alias (the next order with the same
wording matches by itself) and a new eval case (the test set grows from real corrections).
Edits use optimistic locking: the client sends the order version it saw; a stale edit gets 409,
so two reviewers can never silently overwrite each other.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.documents import UPLOAD_DIR
from app.auth.deps import get_current_user
from app.auth.security import now
from app.core.matching import REF_PREFIX
from app.core.pricing import unit_price
from app.db.models import (AuditLog, Customer, CustomerAlias, Document, EvalCase, Order, OrderLine,
                           Product, User)
from app.db.session import get_db

router = APIRouter(tags=["orders"], dependencies=[Depends(get_current_user)])
EDITABLE = ("needs_review", "auto_approved", "export_failed")


class LineFix(BaseModel):
    version: int
    product_id: int | None = None
    qty: float | None = Field(default=None, gt=0, le=100_000)


class Decision(BaseModel):
    version: int
    reason: str | None = Field(default=None, max_length=500)


def _order_or_404(db: Session, order_id: int, lock: bool = False) -> Order:
    q = select(Order).where(Order.id == order_id)
    order = db.scalar(q.with_for_update() if lock else q)
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    return order


def _check_version(order: Order, version: int) -> None:
    if order.version != version:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "this order was changed by someone else; reload it and try again")


def _audit(db, user: User, action: str, order: Order, before: dict | None, after: dict | None):
    db.add(AuditLog(actor=user.email, action=action, entity="order", entity_id=order.id,
                    before=before, after=after))


def _line_out(db: Session, ln: OrderLine) -> dict:
    p = db.get(Product, ln.product_id) if ln.product_id else None
    return {"line_no": ln.line_no, "raw_text": ln.raw_text, "qty": float(ln.qty), "unit": ln.unit,
            "product": {"id": p.id, "code": p.code, "name": p.name, "pack_qty": p.pack_qty} if p else None,
            "unit_price": float(ln.unit_price) if ln.unit_price is not None else None,
            "match_method": ln.match_method, "confidence": ln.match_score,
            "candidates": (ln.candidates or [])[:3], "needs_review": ln.needs_review, "reason": ln.reason}


@router.get("/orders")
def list_orders(status_: str | None = Query(None, alias="status"), customer_id: int | None = None,
                limit: int = Query(50, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    open_lines = (select(func.count()).select_from(OrderLine)
                  .where(OrderLine.order_id == Order.id, OrderLine.needs_review).scalar_subquery())
    all_lines = select(func.count()).select_from(OrderLine).where(OrderLine.order_id == Order.id).scalar_subquery()
    q = (select(Order, Customer.name, Document.received_at, Document.filename,
                open_lines.label("open_lines"), all_lines.label("lines"))
         .join(Document, Document.id == Order.document_id)
         .outerjoin(Customer, Customer.id == Order.customer_id))
    if status_:
        q = q.where(Order.status == status_)
    if customer_id:
        q = q.where(Order.customer_id == customer_id)
    # work first: orders needing review at the top, newest first within each group
    q = q.order_by((Order.status != "needs_review"), Document.received_at.desc()).limit(limit).offset(offset)
    return [{"id": o.id, "status": o.status, "customer": name, "po_number": o.po_number,
             "delivery_date": o.delivery_date, "received_at": rec, "filename": fn, "lines": n,
             "lines_to_review": open_n, "confidence": o.confidence, "erp_ref": o.erp_ref, "version": o.version}
            for o, name, rec, fn, open_n, n in db.execute(q).all()]


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    o = _order_or_404(db, order_id)
    doc = db.get(Document, o.document_id)
    c = db.get(Customer, o.customer_id) if o.customer_id else None
    lines = db.scalars(select(OrderLine).where(OrderLine.order_id == o.id).order_by(OrderLine.line_no)).all()
    return {"id": o.id, "status": o.status, "version": o.version, "po_number": o.po_number,
            "delivery_date": o.delivery_date, "confidence": o.confidence, "erp_ref": o.erp_ref,
            "reject_reason": o.reject_reason,
            "customer": {"id": c.id, "account_code": c.account_code, "name": c.name} if c else None,
            "document": {"id": doc.id, "filename": doc.filename, "received_at": doc.received_at,
                         "text": doc.text},
            "lines": [_line_out(db, ln) for ln in lines]}


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    path = next(UPLOAD_DIR.glob(f"{doc.sha256}.*"), None) if doc else None
    if not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    media = "application/pdf" if path.suffix == ".pdf" else "message/rfc822"
    return FileResponse(path, media_type=media, filename=doc.filename)


@router.patch("/orders/{order_id}/lines/{line_no}")
def fix_line(order_id: int, line_no: int, body: LineFix, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    o = _order_or_404(db, order_id, lock=True)
    _check_version(o, body.version)
    if o.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"order is {o.status} and can't be edited")
    ln = db.scalar(select(OrderLine).where(OrderLine.order_id == o.id, OrderLine.line_no == line_no))
    if not ln:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")
    if body.product_id is None and body.qty is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nothing to change")

    before = _line_out(db, ln)
    product = db.get(Product, body.product_id or ln.product_id) if (body.product_id or ln.product_id) else None
    if body.product_id is not None and not product:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown product")
    if body.product_id is not None:
        changed_product = body.product_id != ln.product_id
        ln.product_id, ln.match_method, ln.match_score = product.id, "human", 1.0
        if o.customer_id:
            _learn_alias(db, o.customer_id, ln.raw_text, product.id, user.email)
        _save_eval_case(db, o, ln, product, changed_product)
    if body.qty is not None:
        ln.qty = body.qty
    if product:  # price always from the pricing rules, never from the client
        doc = db.get(Document, o.document_id)
        ln.unit_price = unit_price(db, o.customer_id, product, doc.received_at.date() if doc.received_at else date.today())
    ln.needs_review = product is None or float(ln.qty) <= 0
    ln.reason = None if not ln.needs_review else ln.reason
    if o.status in ("auto_approved", "export_failed"):
        o.status = "needs_review"  # a person touched it: it now needs a person to approve it
    o.version += 1
    _audit(db, user, "line_fixed", o, before, _line_out(db, ln))
    db.commit()
    return get_order(o.id, db)


def _learn_alias(db: Session, customer_id: int, raw: str, product_id: int, who: str) -> None:
    """Next time this customer writes the same thing, it matches by alias (method 1)."""
    text = REF_PREFIX.sub("", raw).strip()
    if not text:
        return
    stmt = insert(CustomerAlias).values(customer_id=customer_id, alias_text=text, product_id=product_id,
                                        created_by=who)
    db.execute(stmt.on_conflict_do_update(index_elements=["customer_id", "alias_text"],
                                          set_={"product_id": product_id, "created_by": who}))


def _save_eval_case(db: Session, o: Order, ln: OrderLine, product: Product, corrected: bool) -> None:
    """Corrections become eval set v2, so the test set grows from real mistakes."""
    case_id = f"fix-{o.id}-{ln.line_no}"
    expected = {"label_version": 2, "raw": ln.raw_text, "customer_id": o.customer_id,
                "product_code": product.code, "was_corrected": corrected}
    stmt = insert(EvalCase).values(case_id=case_id, split="corrections", filename="", expected=expected)
    db.execute(stmt.on_conflict_do_update(index_elements=["case_id"], set_={"expected": expected}))


@router.post("/orders/{order_id}/approve")
def approve(order_id: int, body: Decision, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = _order_or_404(db, order_id, lock=True)
    _check_version(o, body.version)
    if o.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"order is {o.status} and can't be approved")
    open_lines = db.scalar(select(func.count()).select_from(OrderLine)
                           .where(OrderLine.order_id == o.id, OrderLine.needs_review))
    if open_lines:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{open_lines} line(s) still need a product or quantity")
    before = {"status": o.status}
    o.status, o.reviewed_by, o.reviewed_at = "approved", user.id, now()
    o.version += 1
    _audit(db, user, "approved", o, before, {"status": o.status})
    db.commit()
    return {"id": o.id, "status": o.status, "version": o.version}  # the worker exports it to the ERP


@router.post("/orders/{order_id}/reject")
def reject(order_id: int, body: Decision, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = _order_or_404(db, order_id, lock=True)
    _check_version(o, body.version)
    if not body.reason or not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a reason is required to reject an order")
    if o.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"order is {o.status} and can't be rejected")
    before = {"status": o.status}
    o.status, o.reject_reason, o.reviewed_by, o.reviewed_at = "rejected", body.reason.strip(), user.id, now()
    o.version += 1
    _audit(db, user, "rejected", o, before, {"status": o.status, "reason": o.reject_reason})
    db.commit()
    return {"id": o.id, "status": o.status, "version": o.version}
