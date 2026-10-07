"""Adapter behaviour without calling a real LLM: fallback, logging, JSON handling."""
import pytest

from app.config import get_settings
from app.db.models import LlmCall
from app.db.session import SessionLocal
from app.llm import adapter


def fake(responses):
    """Replace _call with a fake that returns or raises in order, per model."""
    calls = []

    def _call(model, system, user, max_tokens):
        calls.append(model)
        r = responses[model]
        if isinstance(r, Exception):
            raise r
        return r, 10, 5
    return _call, calls


def logged(db, pv):
    return db.query(LlmCall).filter(LlmCall.prompt_version == pv).order_by(LlmCall.id).all()


def test_main_model_success(monkeypatch):
    s = get_settings()
    _call, calls = fake({s.LLM_MODEL: {"ok": 1}})
    monkeypatch.setattr(adapter, "_call", _call)
    with SessionLocal() as db:
        r = adapter.chat_json(db, system="s", user="u", purpose="test", prompt_version="t-main")
        assert r.data == {"ok": 1} and r.model == s.LLM_MODEL
        rows = logged(db, "t-main")
        assert [x.success for x in rows] == [True]
        for x in rows: db.delete(x)
        db.commit()


def test_falls_back_and_logs_both(monkeypatch):
    s = get_settings()
    _call, calls = fake({s.LLM_MODEL: ValueError("bad json"), s.LLM_FALLBACK_MODEL: {"ok": 2}})
    monkeypatch.setattr(adapter, "_call", _call)
    with SessionLocal() as db:
        r = adapter.chat_json(db, system="s", user="u", purpose="test", prompt_version="t-fb")
        assert r.model == s.LLM_FALLBACK_MODEL
        rows = logged(db, "t-fb")
        assert [x.success for x in rows] == [False, True]
        assert "bad json" in rows[0].error
        for x in rows: db.delete(x)
        db.commit()


def test_all_fail_raises(monkeypatch):
    s = get_settings()
    _call, _ = fake({s.LLM_MODEL: ValueError("x"), s.LLM_FALLBACK_MODEL: ValueError("y")})
    monkeypatch.setattr(adapter, "_call", _call)
    with SessionLocal() as db:
        with pytest.raises(adapter.LLMError):
            adapter.chat_json(db, system="s", user="u", purpose="test", prompt_version="t-fail")
        for x in logged(db, "t-fail"): db.delete(x)
        db.commit()
