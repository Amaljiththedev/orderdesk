"""Export against the real mock ERP service: no duplicates, whatever the network does.
Needs the mock_erp container running (docker compose up)."""
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.export import export_order
from app.db.models import AuditLog, Document, Order, OrderLine, Product
from app.db.session import SessionLocal

ERP = get_settings().ERP_URL


@pytest.fixture(autouse=True)
def erp():
    httpx.post(f"{ERP}/admin/reset", timeout=5)
    yield
    httpx.post(f"{ERP}/admin/reset", timeout=5)


def erp_orders_for(key):
    return [o for o in httpx.get(f"{ERP}/orders", timeout=5).json() if o["idempotency_key"] == key]


def make_order(db, qty=2):
    product = db.scalar(select(Product).limit(1))
    key = uuid.uuid4().hex
    doc = Document(source="test", filename="t.eml", sha256=key, status="processing")
    db.add(doc)
    db.flush()
    # "test_hold" so the running worker never exports it behind the test's back
    order = Order(document_id=doc.id, status="test_hold", idempotency_key=key)
    db.add(order)
    db.flush()
    db.add(OrderLine(order_id=order.id, line_no=1, raw_text="x", qty=qty, product_id=product.id,
                     unit_price=product.list_price_gbp, needs_review=False))
    db.commit()
    return order


def cleanup(db, order):
    db.query(AuditLog).filter(AuditLog.entity == "order", AuditLog.entity_id == order.id).delete()
    db.query(OrderLine).filter(OrderLine.order_id == order.id).delete()
    doc_id = order.document_id
    db.delete(order)
    db.flush()
    db.query(Document).filter(Document.id == doc_id).delete()
    db.commit()


def approve_and_export(db, order):
    order.status = "approved"
    return export_order(db, order, actor="test")


def test_sending_twice_creates_one_erp_order():
    with SessionLocal() as db:
        o = make_order(db)
        assert approve_and_export(db, o) == "exported"
        first = o.erp_ref
        assert approve_and_export(db, o) == "exported"   # e.g. someone clicks export again
        assert o.erp_ref == first
        assert len(erp_orders_for(o.idempotency_key)) == 1
        cleanup(db, o)


def test_committed_but_timed_out_is_not_duplicated():
    httpx.post(f"{ERP}/admin/config", json={"commit_then_hang_rate": 1.0}, timeout=5)
    with SessionLocal() as db:
        o = make_order(db)
        assert approve_and_export(db, o) == "exported"   # first try timed out, retry replayed
        assert len(erp_orders_for(o.idempotency_key)) == 1
        audit = db.scalars(select(AuditLog).where(AuditLog.entity_id == o.id)).all()[-1]
        assert audit.after["replayed"] is True
        cleanup(db, o)


def test_flaky_erp_still_no_duplicates():
    httpx.post(f"{ERP}/admin/config", json={"fail_rate": 0.3}, timeout=5)
    with SessionLocal() as db:
        orders = [make_order(db) for _ in range(10)]
        results = [approve_and_export(db, o) for o in orders]
        assert results.count("exported") >= 9            # ~0.8% chance one order fails 4 times
        for o in orders:
            assert len(erp_orders_for(o.idempotency_key)) == (1 if o.status == "exported" else 0)
        for o in orders:
            cleanup(db, o)


def test_reused_key_with_different_order_is_rejected():
    with SessionLocal() as db:
        o = make_order(db, qty=2)
        assert approve_and_export(db, o) == "exported"
        line = db.scalar(select(OrderLine).where(OrderLine.order_id == o.id))
        line.qty = 5                                       # same key, different body
        assert approve_and_export(db, o) == "export_failed"
        assert len(erp_orders_for(o.idempotency_key)) == 1
        cleanup(db, o)


def test_unresolved_line_is_not_sent():
    with SessionLocal() as db:
        o = make_order(db)
        line = db.scalar(select(OrderLine).where(OrderLine.order_id == o.id))
        line.needs_review = True
        assert approve_and_export(db, o) == "export_failed"
        assert erp_orders_for(o.idempotency_key) == []
        cleanup(db, o)
