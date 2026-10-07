"""Order text -> structured order, using the LLM.

The LLM only reads the order. It never picks product codes: that is the matcher's job (Phase 3),
so a hallucinated code can't reach an order. Output is validated with Pydantic; invalid output
gets one retry with the validation error, then the document goes to human review.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.llm.adapter import LLMError, chat_json

PROMPT_VERSION = "extract_v2"  # v2: "2 off" is a count, not pieces (gen-0005)
PROMPT = (Path(__file__).resolve().parents[1] / "llm" / "prompts" / f"{PROMPT_VERSION}.md").read_text()


class ExtractedLine(BaseModel):
    raw_text: str = Field(min_length=1)
    qty: float | None = Field(default=None, gt=0)
    qty_in_pieces: bool = False
    unit: str | None = None

    @field_validator("raw_text")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("raw_text is empty")
        return v


class ExtractedOrder(BaseModel):
    customer_name: str | None = None
    po_number: str | None = None
    delivery_date: date | None = None
    lines: list[ExtractedLine] = Field(min_length=1)


class ExtractionFailed(RuntimeError):
    """The order could not be read reliably. Send it to a person."""


def extract_order(db: Session, text: str, received: date, document_id: int | None = None) -> ExtractedOrder:
    system = PROMPT.replace("{received_date}", received.isoformat())
    user = f"ORDER:\n<<<\n{text}\n>>>"
    for attempt in range(2):
        try:
            res = chat_json(db, system=system, user=user, purpose="extract",
                            prompt_version=PROMPT_VERSION, document_id=document_id)
        except LLMError as e:
            raise ExtractionFailed(str(e)) from e
        try:
            return ExtractedOrder.model_validate(res.data)
        except ValidationError as e:
            if attempt == 1:
                raise ExtractionFailed(f"invalid output after retry: {e.errors()[:3]}") from e
            # one retry, telling the model exactly what was wrong
            user += f"\n\nYour previous JSON was invalid: {e.errors()[:3]}. Return corrected JSON only."
    raise ExtractionFailed("unreachable")
