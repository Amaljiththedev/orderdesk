"""Schema rules and the one-retry behaviour, with a fake LLM."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.core import extraction
from app.core.extraction import ExtractedOrder, ExtractionFailed, extract_order
from app.llm.adapter import LLMResult


def test_schema_rejects_bad_lines():
    with pytest.raises(ValidationError):
        ExtractedOrder.model_validate({"lines": []})                       # no lines
    with pytest.raises(ValidationError):
        ExtractedOrder.model_validate({"lines": [{"raw_text": "x", "qty": -1}]})  # negative qty
    with pytest.raises(ValidationError):
        ExtractedOrder.model_validate({"lines": [{"raw_text": "   ", "qty": 1}]})  # blank text


def fake_llm(outputs):
    seen = []

    def chat_json(db, **kw):
        seen.append(kw["user"])
        return LLMResult(outputs[len(seen) - 1], "fake", 1, 1, 1)
    return chat_json, seen


def test_retry_fixes_invalid_output(monkeypatch):
    chat, seen = fake_llm([{"lines": []}, {"lines": [{"raw_text": "cu elbow", "qty": 5}]}])
    monkeypatch.setattr(extraction, "chat_json", chat)
    out = extract_order(None, "5 x cu elbow", date(2026, 10, 5))
    assert out.lines[0].raw_text == "cu elbow" and len(seen) == 2
    assert "invalid" in seen[1]            # the retry tells the model what was wrong


def test_gives_up_after_one_retry(monkeypatch):
    chat, _ = fake_llm([{"lines": []}, {"lines": []}])
    monkeypatch.setattr(extraction, "chat_json", chat)
    with pytest.raises(ExtractionFailed):
        extract_order(None, "x", date(2026, 10, 5))


def test_prompt_has_received_date():
    assert "{received_date}" in extraction.PROMPT
