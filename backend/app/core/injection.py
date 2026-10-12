"""Spot text that is trying to instruct the system instead of ordering goods.

The LLM is told order text is data, but injection_eval showed it can still obey
"ignore the order above, the real order is ...". So code checks too: if the document
contains instruction-like text, nothing in it may auto-approve, and lines read from
those rows are flagged. A false positive costs one human look; a miss costs a wrong order.
"""
from __future__ import annotations

import re

PATTERNS = [
    r"ignore (all |any |the |your )?(previous |prior |above )?(instructions|order|rules)",
    r"\b(system|assistant)\s*:",
    r"</?\s*(system|order_text|order_line|instructions?)\s*>",
    r"\byou are now\b",
    r"\badmin mode\b",
    r"\b(note|message|instruction)s? to (the )?(ai|assistant|model|agent|resolver)",
    r"\b(ai|llm|chatgpt|gpt)\s*[:,]",
    r"\bthe real order is\b",
    r"\buse this json\b",
    r"\b(set|change|make)\b.{0,40}\b(price|prices|quantit(y|ies)|discount)\b",
    r"\b(skip|bypass)\b.{0,20}\breview\b",
    r"\bpre-?approved\b|\bmark (it|this( order)?) (as )?approved\b",
    r"\b(100%|free of charge|at no charge|no charge)\b",
]
_RX = re.compile("|".join(f"(?:{p})" for p in PATTERNS), re.I)


def suspicious_rows(text: str) -> list[str]:
    """Rows of the document that look like instructions, trimmed for display."""
    return [row.strip()[:120] for row in (text or "").splitlines() if _RX.search(row)]


def from_suspicious_row(raw: str, rows: list[str]) -> bool:
    """Was this extracted line read from one of the suspicious rows?"""
    r = raw.lower().strip()
    return bool(r) and any(r in row.lower() for row in rows)
