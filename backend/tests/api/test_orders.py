"""Review API through the real app and database."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.security import create_access_token, hash_password
from app.core.matching import match_line
from app.db.models import (AuditLog, Customer, CustomerAlias, Document, EvalCase, Order, OrderLine,
                           Product, User)
from app.db.session import SessionLocal
from app.main import app


@pytest.fixture
def ctx():
    """A reviewer, a customer, and a needs-review order with one unresolved line."""
    raw = f"widget thing {uuid.uuid4().hex[:6]}"   # unique wording, so the alias is new
    with SessionLocal() as db:
        user = User(email=f"r-{uuid.uuid4().hex[:8]}@example.com", full_name="Rev", role="reviewer",
                    password_hash=hash_password("unused password here"), must_change_password=False)
        db.add(user)
        customer = db.scalar(select(Customer).order_by(Customer.id))
        product = db.scalar(select(Product).order_by(Product.id))
        key = uuid.uuid4().hex
        doc = Document(source="test", filename="t.eml", sha256=key, status="done", text="t")
        db.add(doc)
        db.flush()
        order = Order(document_id=doc.id, customer_id=customer.id, status="needs_review", idempotency_key=key)
        db.add(order)
        db.flush()
        db.add(OrderLine(order_id=order.id, line_no=1, raw_text=raw, qty=3, needs_review=True,
                         reason="no similar product found"))
        db.commit()
        ids = dict(user=user.id, customer=customer.id, product=product.id, order=order.id, doc=doc.id, raw=raw)
        token = create_access_token(user.id, user.role, user.token_version)
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token}"
    yield c, ids
    with SessionLocal() as db:
        db.query(AuditLog).filter(AuditLog.entity == "order", AuditLog.entity_id == ids["order"]).delete()
        db.query(EvalCase).filter(EvalCase.case_id.like(f"fix-{ids['order']}-%")).delete(synchronize_session=False)
        db.query(CustomerAlias).filter(CustomerAlias.customer_id == ids["customer"],
                                       CustomerAlias.alias_text == ids["raw"]).delete()
        db.query(OrderLine).filter(OrderLine.order_id == ids["order"]).delete()
        db.query(Order).filter(Order.id == ids["order"]).delete()
        db.flush()
        db.query(Document).filter(Document.id == ids["doc"]).delete()
        db.query(User).filter(User.id == ids["user"]).delete()
        db.commit()


def test_inbox_lists_needs_review_first(ctx):
    c, ids = ctx
    rows = c.get("/orders", params={"status": "needs_review"}).json()
    assert any(r["id"] == ids["order"] and r["lines_to_review"] == 1 for r in rows)


def test_cannot_approve_with_unresolved_lines(ctx):
    c, ids = ctx
    r = c.post(f"/orders/{ids['order']}/approve", json={"version": 0})
    assert r.status_code == 409 and "still need" in r.json()["detail"]


def test_fix_teaches_alias_then_approve(ctx):
    c, ids = ctx
    r = c.patch(f"/orders/{ids['order']}/lines/1", json={"version": 0, "product_id": ids["product"]})
    assert r.status_code == 200
    body = r.json()
    line = body["lines"][0]
    assert line["product"]["id"] == ids["product"] and not line["needs_review"] and line["unit_price"] is not None
    # the system learned: same wording from the same customer now matches by alias
    with SessionLocal() as db:
        m = match_line(db, ids["raw"], ids["customer"])
        assert m.method == "alias" and m.product_id == ids["product"]
        assert db.scalar(select(EvalCase).where(EvalCase.case_id == f"fix-{ids['order']}-1"))
    r = c.post(f"/orders/{ids['order']}/approve", json={"version": body["version"]})
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_stale_version_is_rejected(ctx):
    c, ids = ctx
    assert c.patch(f"/orders/{ids['order']}/lines/1", json={"version": 0, "qty": 5}).status_code == 200
    # a second reviewer still holding version 0
    r = c.patch(f"/orders/{ids['order']}/lines/1", json={"version": 0, "qty": 7})
    assert r.status_code == 409


def test_reject_needs_reason_and_is_audited(ctx):
    c, ids = ctx
    assert c.post(f"/orders/{ids['order']}/reject", json={"version": 0}).status_code == 422
    r = c.post(f"/orders/{ids['order']}/reject", json={"version": 0, "reason": "duplicate of PO 123"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    with SessionLocal() as db:
        actions = [a.action for a in db.scalars(select(AuditLog).where(
            AuditLog.entity == "order", AuditLog.entity_id == ids["order"]))]
    assert "rejected" in actions


def test_orders_need_login():
    assert TestClient(app).get("/orders").status_code == 401
