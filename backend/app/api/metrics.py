"""Admin metrics: how much went through untouched, how fast, how accurate, what it cost.

Plain SQL aggregates over orders, order_lines, audit_log and llm_calls. No LLM calls.
Accuracy here comes from reviewer actions (live); eval numbers come from the saved eval files.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/metrics", tags=["metrics"])
RESULTS = Path("/data/eval/results")


def _pct(n, d):
    return round(100 * n / d, 1) if d else None


def _one(db, sql, **p):
    return dict(db.execute(text(sql), p).mappings().one())


def _all(db, sql, **p):
    return [dict(r) for r in db.execute(text(sql), p).mappings().all()]


def orders_summary(db: Session, since: datetime) -> dict:
    r = _one(db, """
        select count(*) as orders,
               count(*) filter (where o.status = 'auto_approved') as auto_approved,
               count(*) filter (where o.status = 'needs_review') as needs_review,
               count(*) filter (where o.status = 'approved') as approved,
               count(*) filter (where o.status = 'exported') as exported,
               count(*) filter (where o.status = 'export_failed') as export_failed,
               count(*) filter (where o.status = 'rejected') as rejected,
               count(*) filter (where o.status in ('auto_approved','approved','exported')
                                and not exists (select 1 from audit_log a where a.entity = 'order'
                                                and a.entity_id = o.id and a.action = 'line_fixed'))
                   as accepted_without_edits,
               count(*) filter (where o.status in ('auto_approved','approved','exported')) as accepted
        from orders o join documents d on d.id = o.document_id
        where d.received_at >= :since""", since=since)
    docs = _one(db, """
        select count(*) as documents,
               count(*) filter (where status = 'failed') as failed,
               count(*) filter (where status = 'needs_review') as unreadable
        from documents where received_at >= :since""", since=since)
    r.update(docs)
    r["auto_approve_rate_pct"] = _pct(r["auto_approved"], r["orders"])
    r["no_edit_rate_pct"] = _pct(r["accepted_without_edits"], r["accepted"])  # PRD: aim >= 50%
    return r


def lines_summary(db: Session, since: datetime) -> dict:
    r = _one(db, """
        select count(*) as lines,
               count(*) filter (where l.needs_review) as still_flagged,
               count(*) filter (where l.match_method = 'human') as fixed_by_reviewer
        from order_lines l join orders o on o.id = l.order_id join documents d on d.id = o.document_id
        where d.received_at >= :since""", since=since)
    # what the matcher had said before a reviewer changed the line (the audit keeps the 'before')
    r["fixes_by_original_method"] = {row["method"] or "none": row["n"] for row in _all(db, """
        select a.before->>'match_method' as method, count(*) as n
        from audit_log a join orders o on o.id = a.entity_id join documents d on d.id = o.document_id
        where a.entity = 'order' and a.action = 'line_fixed' and d.received_at >= :since
        group by 1 order by 2 desc""", since=since)}
    # the number that matters most: a line that went through on its own and was later corrected
    r["auto_approved_then_fixed"] = _one(db, """
        select count(*) as n from audit_log a join orders o on o.id = a.entity_id
        join documents d on d.id = o.document_id
        where a.entity = 'order' and a.action = 'line_fixed' and d.received_at >= :since
          and (a.before->>'needs_review') = 'false'""", since=since)["n"]
    return r


def timing(db: Session, since: datetime) -> dict:
    return _one(db, """
        select round((percentile_cont(0.5) within group (order by extract(epoch from o.created_at - d.received_at)))::numeric, 1) as routed_p50_s,
               round((percentile_cont(0.95) within group (order by extract(epoch from o.created_at - d.received_at)))::numeric, 1) as routed_p95_s,
               round((percentile_cont(0.5) within group (order by extract(epoch from o.exported_at - coalesce(o.reviewed_at, o.created_at)))
                      filter (where o.exported_at is not null))::numeric, 1) as export_p50_s
        from orders o join documents d on d.id = o.document_id
        where d.received_at >= :since and o.created_at >= d.received_at""", since=since)


def llm_usage(db: Session, since: datetime, n_orders: int) -> dict:
    s = get_settings()
    rows = _all(db, """
        select purpose, prompt_version, model, count(*) as calls,
               count(*) filter (where not success) as failures,
               coalesce(sum(input_tokens), 0) as input_tokens, coalesce(sum(output_tokens), 0) as output_tokens,
               percentile_cont(0.95) within group (order by latency_ms) as latency_p95_ms
        from llm_calls where at >= :since
        group by 1, 2, 3 order by 1, 2, 3""", since=since)
    total, unpriced = 0.0, False
    for r in rows:
        price = s.LLM_PRICES_GBP_PER_M.get(r["model"])
        r["fallback"] = r["model"] == s.LLM_FALLBACK_MODEL
        r["latency_p95_ms"] = round(r["latency_p95_ms"]) if r["latency_p95_ms"] is not None else None
        if price:
            r["cost_gbp"] = round((r["input_tokens"] * price[0] + r["output_tokens"] * price[1]) / 1e6, 4)
            total += r["cost_gbp"]
        else:
            r["cost_gbp"], unpriced = None, True
    return {"by_purpose": rows,
            "cost_gbp": None if unpriced else round(total, 4),
            "cost_per_order_gbp": None if unpriced or not n_orders else round(total / n_orders, 5),
            "note": "set LLM_PRICES_GBP_PER_M in .env to report cost" if unpriced else None}


def by_day(db: Session, since: datetime) -> list[dict]:
    return [dict(r, day=r["day"].isoformat()) for r in _all(db, """
        select date_trunc('day', d.received_at)::date as day, count(*) as orders,
               count(*) filter (where o.status = 'auto_approved') as auto_approved,
               count(*) filter (where o.status <> 'auto_approved') as reviewed_or_pending
        from orders o join documents d on d.id = o.document_id
        where d.received_at >= :since group by 1 order by 1""", since=since)]


def _latest(prefix: str) -> Path | None:
    files = sorted(RESULTS.glob(f"{prefix}_2*.json")) if RESULTS.exists() else []
    return files[-1] if files else None


def latest_evals() -> dict:
    """Headline numbers from the newest saved eval runs (synthetic data)."""
    threshold = get_settings().AUTO_APPROVE_THRESHOLD
    out: dict = {}
    if f := _latest("match_generated"):
        saved = json.loads(f.read_text())
        rows = saved["rows"] if isinstance(saved, dict) else saved   # match_eval saves {"curve", "rows"}
        ok = [r for r in rows if not r["unknown_ref"]]
        auto = [r for r in rows if r["conf"] >= threshold]
        out["matching"] = {"file": f.name, "lines": len(rows),
                           "top1_pct": _pct(sum(r["top1"] for r in ok), len(ok)),
                           "top5_pct": _pct(sum(r["top5"] for r in ok), len(ok)),
                           "auto_approve_pct": _pct(len(auto), len(rows)),
                           "auto_precision_pct": _pct(sum(r["top1"] for r in auto), len(auto))}
    if f := _latest("injection_v2"):
        rows = json.loads(f.read_text())
        out["injection"] = {"file": f.name, "orders": len(rows),
                            "changed_without_review": sum(bool(r["problems"]) for r in rows)}
    if f := _latest("resolve_v1b"):
        rows = json.loads(f.read_text())
        picked = [r for r in rows if r["picked"]]
        out["resolve_agent"] = {"file": f.name, "lines": len(rows),
                                "pick_precision_pct": _pct(sum(r["picked"] == r["want"] for r in picked), len(picked))}
    return out


@router.get("")
def metrics(days: int = Query(30, ge=1, le=365), _: User = Depends(require_admin),
            db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    orders = orders_summary(db, since)
    return {"window_days": days, "since": since.isoformat(),
            "orders": orders, "lines": lines_summary(db, since), "timing": timing(db, since),
            "llm": llm_usage(db, since, orders["orders"]), "by_day": by_day(db, since),
            "evals": latest_evals(), "data": "synthetic"}
