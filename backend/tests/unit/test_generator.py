"""The eval set is only trustworthy if the generator is deterministic and its labels are correct."""
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, "/")  # so `data` imports inside the container

from data.generator import catalogue, orders  # noqa: E402

SEED_DIR = Path("/data/seed")


def run_orders(out: Path, n: int = 30) -> None:
    sys.argv = ["x", "--seed-dir", str(SEED_DIR), "--out", str(out), "--n", str(n)]
    orders.main()


def test_catalogue_is_deterministic_and_codes_unique():
    a = catalogue.build_products(random.Random(42))
    b = catalogue.build_products(random.Random(42))
    assert [p.code for p in a] == [p.code for p in b]
    assert len({p.code for p in a}) == len(a) >= 2000


def test_orders_are_deterministic(tmp_path):
    run_orders(tmp_path / "a")
    run_orders(tmp_path / "b")
    digest = lambda d: [hashlib.sha256(f.read_bytes()).hexdigest()
                        for f in sorted((tmp_path / d).glob("*.json"))]
    assert digest("a") == digest("b")


def test_labels_point_at_real_products(tmp_path):
    codes = {r["code"] for r in csv.DictReader((SEED_DIR / "products.csv").open(encoding="utf-8"))}
    run_orders(tmp_path / "o", n=50)
    for f in (tmp_path / "o").glob("*.json"):
        o = json.loads(f.read_text())
        assert o["lines"], f.name
        for ln in o["lines"]:
            assert ln["product_code"] in codes
            assert ln["qty"] > 0
            assert ln["written_qty"] % ln["qty"] == 0   # pieces are always whole packs
