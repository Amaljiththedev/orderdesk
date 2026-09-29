"""Create the schema and load the synthetic catalogue, customers, aliases, price rules and eval cases.

    python -m app.db.seed [--seed-dir /data/seed] [--eval-dir /data/eval] [--no-embed] [--reset]

Safe to run again: rows are upserted by their natural keys.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db.models import Base, Customer, CustomerAlias, EvalCase, PriceRule, Product
from app.db.session import SessionLocal, engine


def read(p: Path) -> list[dict]:
    return list(csv.DictReader(p.open(encoding="utf-8")))


def create_schema(reset: bool) -> None:
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def upsert(db, model, rows: list[dict], key: list[str]) -> None:
    if not rows:
        return
    stmt = insert(model).values(rows)
    cols = {c: stmt.excluded[c] for c in rows[0] if c not in key}
    db.execute(stmt.on_conflict_do_update(index_elements=key, set_=cols) if cols else stmt.on_conflict_do_nothing())


def embed_products(db) -> int:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(get_settings().EMBED_MODEL)
    todo = db.scalars(select(Product).where(Product.embedding.is_(None))).all()
    if not todo:
        return 0
    vecs = model.encode([p.description for p in todo], batch_size=64, normalize_embeddings=True,
                        show_progress_bar=True)
    for p, v in zip(todo, vecs):
        p.embedding = v.tolist()
    return len(todo)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-dir", default="/data/seed")
    ap.add_argument("--eval-dir", default="/data/eval")
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    a = ap.parse_args()
    seed, ev = Path(a.seed_dir), Path(a.eval_dir)
    create_schema(a.reset)

    with SessionLocal() as db:
        upsert(db, Customer, [{"id": int(c["id"]), "account_code": c["account_code"], "name": c["name"],
                               "contact": c["contact"], "email": c["email"], "town": c["town"]}
                              for c in read(seed / "customers.csv")], ["account_code"])
        upsert(db, Product, [{"code": p["code"], "name": p["name"], "description": p["description"],
                              "family": p["family"], "unit": p["unit"], "pack_qty": int(p["pack_qty"]),
                              "list_price_gbp": p["price_gbp"]} for p in read(seed / "products.csv")], ["code"])
        db.flush()
        pid = dict(db.execute(select(Product.code, Product.id)).all())
        # only the aliases a person has already taught the system; the rest must be learned through review
        upsert(db, CustomerAlias, [{"customer_id": int(a["customer_id"]), "alias_text": a["alias_text"],
                                    "product_id": pid[a["product_code"]]}
                                   for a in read(seed / "customer_aliases.csv") if a["known"] == "True"],
               ["customer_id", "alias_text"])
        db.execute(delete(PriceRule))
        db.add_all(PriceRule(customer_id=int(r["customer_id"]), family=r["family"] or None,
                             discount_pct=r["discount_pct"]) for r in read(seed / "price_rules.csv"))
        cases = []
        for split in ("generated", "held_out"):
            for f in sorted((ev / split).glob("*.json")):
                o = json.loads(f.read_text(encoding="utf-8"))
                cases.append({"case_id": o["id"], "split": split, "filename": o["document"], "expected": o})
        upsert(db, EvalCase, cases, ["case_id"])
        db.commit()
        n = 0 if a.no_embed else embed_products(db)
        db.commit()
        counts = {t: db.scalar(text(f"SELECT count(*) FROM {t}")) for t in
                  ("products", "customers", "customer_aliases", "price_rules", "eval_cases")}
    print(f"seeded {counts}; embedded {n} products")


if __name__ == "__main__":
    main()
