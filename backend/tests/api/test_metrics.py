"""Metrics API: admin only, counts real rows, never guesses a cost."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import metrics as metrics_api
from app.auth.security import create_access_token, hash_password
from app.config import get_settings
from app.db.models import Customer, Document, LlmCall, Order, OrderLine, User
from app.db.session import SessionLocal
from app.main import app


def _client(role: str):
    with SessionLocal() as db:
        u = User(email=f"m-{uuid.uuid4().hex[:8]}@example.com", full_name="Metrics", role=role,
                 password_hash=hash_password("unused password here"), must_change_password=False)
        db.add(u)
        db.commit()
        token, uid = create_access_token(u.id, u.role, u.token_version), u.id
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {token}"
    return c, uid


@pytest.fixture
def seeded():
    """One auto-approved order with two lines and one priced LLM call."""
    model = f"test-model-{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        key = uuid.uuid4().hex
        doc = Document(source="test", filename="m.eml", sha256=key, status="done", text="t")
        db.add(doc)
        db.flush()
        cust = db.scalar(select(Customer).order_by(Customer.id))
        o = Order(document_id=doc.id, customer_id=cust.id, status="auto_approved", idempotency_key=key)
        db.add(o)
        db.flush()
        for n in (1, 2):
            db.add(OrderLine(order_id=o.id, line_no=n, raw_text=f"x{n}", qty=1, needs_review=False))
        call = LlmCall(purpose="extract", model=model, prompt_version="t-metrics", input_tokens=1_000_000,
                       output_tokens=500_000, latency_ms=100, success=True, document_id=doc.id)
        db.add(call)
        db.commit()
        ids = dict(doc=doc.id, order=o.id, call=call.id, model=model)
    yield ids
    with SessionLocal() as db:
        db.query(LlmCall).filter(LlmCall.id == ids["call"]).delete()
        db.query(OrderLine).filter(OrderLine.order_id == ids["order"]).delete()
        db.query(Order).filter(Order.id == ids["order"]).delete()
        db.flush()
        db.query(Document).filter(Document.id == ids["doc"]).delete()
        db.commit()


def _cleanup_user(uid):
    with SessionLocal() as db:
        db.query(User).filter(User.id == uid).delete()
        db.commit()


def test_reviewer_cannot_see_metrics():
    c, uid = _client("reviewer")
    try:
        assert c.get("/metrics").status_code == 403
    finally:
        _cleanup_user(uid)


def test_needs_login():
    assert TestClient(app).get("/metrics").status_code == 401


def test_admin_sees_counts_and_unpriced_cost_is_null(seeded):
    c, uid = _client("admin")
    try:
        r = c.get("/metrics?days=1")
        assert r.status_code == 200
        m = r.json()
        assert m["orders"]["orders"] >= 1 and m["orders"]["auto_approved"] >= 1
        assert m["lines"]["lines"] >= 2
        assert {"routed_p50_s", "routed_p95_s"} <= m["timing"].keys()
        row = next(x for x in m["llm"]["by_purpose"] if x["model"] == seeded["model"])
        assert row["calls"] == 1 and row["cost_gbp"] is None        # no price set: never guessed
        assert m["llm"]["cost_gbp"] is None and m["data"] == "synthetic"
    finally:
        _cleanup_user(uid)


def test_cost_uses_configured_price(seeded, monkeypatch):
    monkeypatch.setitem(get_settings().LLM_PRICES_GBP_PER_M, seeded["model"], [0.10, 0.40])
    c, uid = _client("admin")
    try:
        rows = c.get("/metrics?days=1").json()["llm"]["by_purpose"]
        row = next(x for x in rows if x["model"] == seeded["model"])
        assert row["cost_gbp"] == pytest.approx(0.10 + 0.20)   # 1M in x 0.10 + 0.5M out x 0.40
    finally:
        _cleanup_user(uid)


def test_days_is_bounded():
    c, uid = _client("admin")
    try:
        assert c.get("/metrics?days=0").status_code == 422
        assert c.get("/metrics?days=9999").status_code == 422
    finally:
        _cleanup_user(uid)


def test_latest_evals_reads_saved_files(tmp_path, monkeypatch):
    rows = [{"unknown_ref": False, "conf": 0.9, "top1": True, "top5": True},
            {"unknown_ref": False, "conf": 0.2, "top1": False, "top5": True}]
    # same shape match_eval saves
    (tmp_path / "match_generated_20261012-0000.json").write_text(__import__("json").dumps({"curve": [], "rows": rows}))
    monkeypatch.setattr(metrics_api, "RESULTS", tmp_path)
    m = metrics_api.latest_evals()["matching"]
    assert m["top1_pct"] == 50.0 and m["auto_approve_pct"] == 50.0 and m["auto_precision_pct"] == 100.0
