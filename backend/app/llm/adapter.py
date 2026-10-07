"""The only place that talks to an LLM.

- One OpenAI-compatible client (Groq today; swapping provider is a .env change).
- Main model first, fallback model if it fails.
- Every attempt is logged to llm_calls: model, prompt version, tokens, latency, success.
- Returns parsed JSON; callers validate it against their own Pydantic schema.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from openai import APIStatusError, OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import LlmCall

NON_RETRYABLE = {400, 401, 403, 404}  # bad request, auth, unknown model: trying again won't help


class LLMError(RuntimeError):
    """All models failed. The caller should send the document to human review."""


@dataclass
class LLMResult:
    data: dict
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        s = get_settings()
        _client = OpenAI(api_key=s.GROQ_API_KEY or "missing", base_url=s.LLM_BASE_URL,
                         timeout=s.LLM_TIMEOUT_S, max_retries=0)  # we handle retries ourselves
    return _client


def _model_args(model: str, max_tokens: int) -> dict:
    # gpt-oss reasons before answering; without room for that the visible answer comes back empty
    if "gpt-oss" in model.lower():
        return {"max_tokens": max(max_tokens, 2000), "reasoning_effort": "low"}
    return {"max_tokens": max_tokens}


def _call(model: str, system: str, user: str, max_tokens: int):
    r = client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0,  # same input, same output, so evals are repeatable
        **_model_args(model, max_tokens),
    )
    text = re.sub(r"<think>.*?</think>", "", r.choices[0].message.content or "", flags=re.S).strip()
    if not text:
        raise ValueError("empty response")
    usage = getattr(r, "usage", None)
    return json.loads(text), getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)


def chat_json(db: Session, *, system: str, user: str, purpose: str, prompt_version: str,
              document_id: int | None = None, order_id: int | None = None,
              max_tokens: int = 1500) -> LLMResult:
    """Ask for a JSON object. Tries the main model, then the fallback. Raises LLMError if both fail."""
    s = get_settings()
    last: Exception | None = None
    for model in dict.fromkeys([s.LLM_MODEL, s.LLM_FALLBACK_MODEL]):  # unique, order kept
        t0 = time.perf_counter()
        try:
            data, tin, tout = _call(model, system, user, max_tokens)
            ms = round((time.perf_counter() - t0) * 1000)
            _log(db, purpose, model, prompt_version, document_id, order_id, tin, tout, ms, True, None)
            return LLMResult(data, model, tin, tout, ms)
        except Exception as e:
            ms = round((time.perf_counter() - t0) * 1000)
            last = e
            _log(db, purpose, model, prompt_version, document_id, order_id, None, None, ms, False,
                 f"{type(e).__name__}: {str(e)[:500]}")
            if isinstance(e, APIStatusError) and e.status_code in (401, 403):
                break  # bad key: the fallback uses the same key, so stop
    raise LLMError(f"all models failed: {type(last).__name__}: {str(last)[:300]}")


def _log(db, purpose, model, prompt_version, document_id, order_id, tin, tout, ms, ok, error):
    db.add(LlmCall(purpose=purpose, model=model, prompt_version=prompt_version,
                   document_id=document_id, order_id=order_id, input_tokens=tin,
                   output_tokens=tout, latency_ms=ms, success=ok, error=error))
    db.commit()
