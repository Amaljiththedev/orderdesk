"""Send approved orders to the ERP, without ever creating a duplicate.

Every request carries the order's idempotency key (the source document's hash). If a request
times out we cannot know whether the ERP saved it, so we retry with the SAME key: the ERP
returns the original reference instead of creating a second order. At-least-once delivery +
idempotency = effectively once.

Retry: timeouts, connection errors, 5xx. Don't retry: 4xx (the request itself is wrong).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AuditLog, Customer, Order, OrderLine, Product

EXPORTABLE = ("auto_approved", "approved")


class ExportError(RuntimeError):
    pass


def build_payload(db: Session, order: Order) -> dict:
    customer = db.get(Customer, order.customer_id) if order.customer_id else None
    lines = db.scalars(select(OrderLine).where(OrderLine.order_id == order.id).order_by(OrderLine.line_no)).all()
    out = []
    for ln in lines:
        if ln.product_id is None or ln.needs_review:
            raise ExportError(f"line {ln.line_no} is not resolved")
        p = db.get(Product, ln.product_id)
        out.append({"line": ln.line_no, "product_code": p.code, "qty": float(ln.qty),
                    "unit_price": float(ln.unit_price) if ln.unit_price is not None else None})
    return {"customer_account": customer.account_code if customer else None,
            "po_number": order.po_number,
            "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
            "lines": out}


def _post(payload: dict, key: str) -> dict:
    s = get_settings()
    delay = 0.5
    for attempt in range(1, s.ERP_RETRIES + 1):
        try:
            r = httpx.post(f"{s.ERP_URL}/orders", json=payload, headers={"Idempotency-Key": key},
                           timeout=s.ERP_TIMEOUT_S)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            err = f"{type(e).__name__}"          # may or may not have been saved: retry, same key
        else:
            if r.status_code in (200, 201):
                return r.json()
            if 400 <= r.status_code < 500:
                raise ExportError(f"ERP rejected the order ({r.status_code}): {r.text[:200]}")
            err = f"HTTP {r.status_code}"
        if attempt == s.ERP_RETRIES:
            raise ExportError(f"ERP unavailable after {attempt} attempts: {err}")
        time.sleep(delay)
        delay *= 2


def export_order(db: Session, order: Order, actor: str = "system") -> str:
    """Returns the new status: 'exported' or 'export_failed'."""
    if order.status not in EXPORTABLE:
        raise ValueError(f"order {order.id} is {order.status}, not exportable")
    before = {"status": order.status}
    try:
        res = _post(build_payload(db, order), order.idempotency_key)
        order.erp_ref = res["erp_ref"]
        order.exported_at = datetime.now(timezone.utc)
        order.status = "exported"
        detail = {"erp_ref": order.erp_ref, "replayed": res.get("replayed", False)}
    except ExportError as e:
        order.status = "export_failed"
        detail = {"error": str(e)}
    db.add(AuditLog(actor=actor, action="export", entity="order", entity_id=order.id,
                    before=before, after={"status": order.status, **detail}))
    db.commit()
    return order.status


def export_pending(db: Session, limit: int = 20) -> int:
    """Export orders waiting to go out. Returns how many were attempted."""
    orders = db.scalars(select(Order).where(Order.status.in_(EXPORTABLE)).order_by(Order.id)
                        .limit(limit).with_for_update(skip_locked=True)).all()
    for o in orders:
        export_order(db, o)
    return len(orders)
