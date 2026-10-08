from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.core import pricing


class FakeDB:
    def __init__(self, rules):
        self.rules = rules

    def scalars(self, _):
        return SimpleNamespace(all=lambda: self.rules)


def rule(product_id=None, family=None, pct="0"):
    return SimpleNamespace(product_id=product_id, family=family, discount_pct=Decimal(pct))


PRODUCT = SimpleNamespace(id=7, family="CU-EL90", list_price_gbp=Decimal("10.00"))
TODAY = date(2026, 10, 5)


def test_most_specific_rule_wins():
    db = FakeDB([rule(pct="5"), rule(family="CU-EL90", pct="10"), rule(product_id=7, pct="20")])
    assert pricing.unit_price(db, 1, PRODUCT, TODAY) == Decimal("8.00")


def test_family_beats_account_wide():
    db = FakeDB([rule(pct="15"), rule(family="CU-EL90", pct="10")])
    assert pricing.unit_price(db, 1, PRODUCT, TODAY) == Decimal("9.00")


def test_no_customer_pays_list_price():
    assert pricing.unit_price(FakeDB([rule(pct="50")]), None, PRODUCT, TODAY) == Decimal("10.00")
