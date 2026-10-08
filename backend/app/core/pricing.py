"""Prices come from code and the price rules, never from the LLM.

Discount precedence: a rule for this exact product beats a rule for its family, which beats
an account-wide discount. Only one discount applies (the most specific), which is how most
distributors' price lists work. Rules outside their valid dates are ignored.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import PriceRule, Product


def discount_pct(db: Session, customer_id: int | None, product: Product, on: date) -> Decimal:
    if not customer_id:
        return Decimal("0")
    rules = db.scalars(select(PriceRule).where(
        PriceRule.customer_id == customer_id,
        or_(PriceRule.valid_from.is_(None), PriceRule.valid_from <= on),
        or_(PriceRule.valid_to.is_(None), PriceRule.valid_to >= on),
    )).all()
    for pick in (lambda r: r.product_id == product.id,
                 lambda r: r.product_id is None and r.family == product.family,
                 lambda r: r.product_id is None and r.family is None):
        found = [r.discount_pct for r in rules if pick(r)]
        if found:
            return max(found)
    return Decimal("0")


def unit_price(db: Session, customer_id: int | None, product: Product, on: date) -> Decimal:
    pct = discount_pct(db, customer_id, product, on)
    price = Decimal(product.list_price_gbp) * (Decimal("100") - pct) / Decimal("100")
    return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
