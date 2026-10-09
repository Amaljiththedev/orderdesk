"""Bounded resolve agent: an LLM that may look things up, but only picks from what code showed it.

Limits enforced here, not trusted to the prompt:
  - at most MAX_TOOL_CALLS lookups, then it must answer (otherwise: flagged)
  - the final code must be one it was shown (initial candidates + its own searches), else rejected
  - it never sets qty or price; anything else it returns is ignored
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

import re

from app.core.history import BRAND_BY_CODE, brand_of, brand_preference, names_a_brand
from app.core.matching import Candidate, _without_brand, _without_pack, search
from app.db.models import Order, OrderLine, Product
from app.llm.adapter import DailyLimitError, LLMError, chat_json

PROMPT_VERSION = "resolve_v1"  # prompt unchanged; v1b adds code guards
PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / f"{PROMPT_VERSION}.md").read_text()
MAX_TOOL_CALLS = 4
TOOLS = {"search_catalogue", "get_product_details", "get_customer_history"}
AGENT_CONFIDENCE = 0.45  # suggestion only, until resolve_eval shows ~99% precision


@dataclass
class Resolution:
    code: str | None                 # chosen product code, or None if flagged
    product_id: int | None
    reason: str
    steps: list[dict] = field(default_factory=list)
    shown: list[Candidate] = field(default_factory=list)   # everything the agent was allowed to pick


class Tools:
    """Read-only lookups. Real DB by default; tests pass a fake with the same methods."""

    def __init__(self, db: Session, customer_id: int | None):
        self.db, self.customer_id = db, customer_id

    def search(self, query: str) -> list[Candidate]:
        return search(self.db, query)[:5]

    def details(self, code: str) -> dict | None:
        p = self.db.scalar(select(Product).where(Product.code == code))
        return None if p is None else {"code": p.code, "name": p.name, "description": p.description,
                                       "family": p.family, "pack_qty": p.pack_qty}

    def has_brand_sibling(self, code: str) -> bool:
        """Same item from another brand exists in the catalogue (it may not be among the candidates)."""
        part = brand_of(code)
        if not part:
            return False
        others = [code.replace(part, b) for b in BRAND_BY_CODE if b != part]
        return self.db.scalar(select(Product.id).where(Product.code.in_(others)).limit(1)) is not None

    def preferred_brand(self) -> str | None:
        """Code part ("-NORT-") of the customer's clear brand habit, or None."""
        pref = brand_preference(self.db, self.customer_id) if self.customer_id else None
        return pref.code_part if pref else None

    def history(self) -> dict:
        if not self.customer_id:
            return {"known_customer": False}
        pref = brand_preference(self.db, self.customer_id)
        recent = self.db.scalars(
            select(Product.code).join(OrderLine, OrderLine.product_id == Product.id)
            .join(Order, Order.id == OrderLine.order_id)
            .where(Order.customer_id == self.customer_id, Order.status.in_(("approved", "exported")))
            .order_by(Order.id.desc()).limit(20)).all()
        return {"known_customer": True,
                "usual_brand": f"{pref.brand} ({int(pref.share * 100)}% of {pref.lines} lines)" if pref else None,
                "recent_products": list(dict.fromkeys(recent))}


def _show(cands: list[Candidate]) -> list[dict]:
    return [{"code": c.code, "name": c.name, "score": round(c.score, 3)} for c in cands]


PACK_HINT = re.compile(r"\bpack|\bpk\b|\bpcs\b|\bpieces\b|\bbox\b|\bx\s*\d+\b|\b\d+\s*off\b", re.I)


def guard(raw: str, pick: Candidate, shown: list[Candidate], tools) -> str | None:
    """Rules the model kept breaking in resolve_eval v1, now enforced in code. Returns why it's refused."""
    others = [c for c in shown if c.code != pick.code]
    sibling = any(_without_brand(c.code) == _without_brand(pick.code) for c in others) \
        or tools.has_brand_sibling(pick.code)
    if not names_a_brand(raw) and sibling:
        if brand_of(pick.code) != tools.preferred_brand():
            return "brand not stated and the customer's history doesn't settle it"
    if not PACK_HINT.search(raw) and any(_without_pack(c.code) == _without_pack(pick.code) for c in others):
        return "pack size not stated; single and pack versions both exist"
    return None


def resolve_line(db: Session, raw: str, qty: float | None, unit: str | None,
                 candidates: list[Candidate], customer_id: int | None, *,
                 tools: Tools | None = None, chat=None,
                 document_id: int | None = None, order_id: int | None = None) -> Resolution | None:
    """Returns a Resolution, or None if the LLM is unavailable (line stays as it was).
    DailyLimitError is re-raised so the caller can stop resolving for the rest of the batch."""
    tools = tools or Tools(db, customer_id)
    chat = chat or chat_json
    shown: dict[str, Candidate] = {c.code: c for c in candidates}
    steps: list[dict] = []
    tool_calls = 0
    header = (f"<order_line>{json.dumps(raw)}</order_line>\n"
              f"quantity written: {qty} {unit or ''}\n"
              f"candidates from automatic matching:\n{json.dumps(_show(candidates))}")

    def done(code, reason):
        c = shown.get(code) if code else None
        return Resolution(c.code if c else None, c.product_id if c else None, reason, steps, list(shown.values()))

    while True:
        transcript = "\n".join(f"step {i + 1}: {json.dumps(s)}" for i, s in enumerate(steps))
        left = MAX_TOOL_CALLS - tool_calls
        user = f"{header}\n\nsteps so far:\n{transcript or '(none)'}\n\ntool calls left: {left}"
        try:
            out = chat(db, system=PROMPT, user=user, purpose="resolve", prompt_version=PROMPT_VERSION,
                       document_id=document_id, order_id=order_id, max_tokens=2000).data
        except DailyLimitError:
            raise
        except LLMError:
            return None
        action = out.get("action") if isinstance(out, dict) else None
        args = out.get("args") if isinstance(out, dict) and isinstance(out.get("args"), dict) else {}
        why = str(out.get("why", ""))[:300] if isinstance(out, dict) else ""
        step = {"action": action, "args": args, "why": why}
        steps.append(step)

        if action == "choose":
            code = str(args.get("code", ""))
            if code not in shown:
                return done(None, f"agent picked {code or 'nothing'}, which it was never shown; rejected")
            refused = guard(raw, shown[code], list(shown.values()), tools)
            if refused:
                return done(None, f"agent suggested {code}, refused: {refused}")
            return done(code, why or "agent choice")
        if action == "flag_for_human":
            return done(None, str(args.get("reason") or why or "agent was unsure")[:300])
        if action not in TOOLS:
            return done(None, f"agent gave an invalid action ({action!r})")
        if tool_calls >= MAX_TOOL_CALLS:
            return done(None, f"agent used all {MAX_TOOL_CALLS} lookups without deciding")
        tool_calls += 1

        if action == "search_catalogue":
            found = tools.search(str(args.get("query", ""))[:200])
            for c in found:
                shown.setdefault(c.code, c)
            step["result"] = _show(found)
        elif action == "get_product_details":
            code = str(args.get("code", ""))
            step["result"] = tools.details(code) if code in shown else "not allowed: code was never shown"
        else:
            step["result"] = tools.history()
