"""What a customer means when they DON'T name a brand, learned from orders a person has checked.

Only lines where the customer left the brand out count: when someone writes "Kestrel elbow"
that says nothing about what they mean by a plain "elbow".

Only approved / exported orders count: auto-approved guesses must never teach the system,
or one early mistake would reinforce itself.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Order, OrderLine, Product

BRAND_BY_CODE = {"-KEST-": "Kestrel", "-NORT-": "Northway", "-PROF-": "ProFlow"}
BRAND_WORDS = ("kestrel", "northway", "proflow")


def names_a_brand(text: str) -> bool:
    return any(b in text.lower() for b in BRAND_WORDS)
MIN_LINES = 3        # need some evidence
MIN_SHARE = 0.7      # and a clear habit, not a coin flip


@dataclass
class BrandPreference:
    brand: str
    code_part: str
    share: float
    lines: int


def brand_of(code: str) -> str | None:
    return next((part for part in BRAND_BY_CODE if part in code), None)


def preference_from_counts(counts: Counter) -> BrandPreference | None:
    total = sum(counts.values())
    if total < MIN_LINES:
        return None
    part, n = counts.most_common(1)[0]
    share = n / total
    return BrandPreference(BRAND_BY_CODE[part], part, round(share, 2), total) if share >= MIN_SHARE else None


def brand_preference(db: Session, customer_id: int | None) -> BrandPreference | None:
    if not customer_id:
        return None
    rows = db.execute(
        select(Product.code, OrderLine.raw_text).join(OrderLine, OrderLine.product_id == Product.id)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.customer_id == customer_id, Order.status.in_(("approved", "exported")),
               Order.reviewed_by.is_not(None))
    ).all()
    return preference_from_counts(Counter(b for code, raw in rows
                                          if not names_a_brand(raw) and (b := brand_of(code))))
