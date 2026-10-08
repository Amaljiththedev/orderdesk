"""Match an extracted order line to a catalogue product.

Order of methods, cheapest and most certain first; stop at the first confident hit:
  1. customer alias   exact, per customer ("our ref 44-112")
  2. product code     exact, or with the dashes removed (old codes)
  3. search           trigram on names + vector on descriptions, merged with reciprocal rank fusion
Search never "decides" on its own: it returns the top 5 candidates and a confidence. Routing
(Phase 3, step 3) uses the confidence to auto-approve or send the line to a person.
No HTTP here; it takes a DB session and plain values, so it is easy to test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.embeddings import embed_query
from app.core.history import BrandPreference, brand_preference
from app.db.models import CustomerAlias, Product

TOP_K = 5
BRANDS = ("kestrel", "northway", "proflow")
BRAND_CODES = ("-KEST-", "-NORT-", "-PROF-")
RRF_K = 60  # standard reciprocal-rank-fusion constant

# How customers shorten things, mapped back to catalogue words, so trigram search has a chance.
EXPAND = [
    (r"\bcu\b", "copper"), (r"\bcomp\b", "compression"), (r"\bef\b", "end feed"),
    (r"\bsr\b", "solder ring"), (r"\bskt\b", "socket"), (r"\bt&e\b", "twin & earth cable"),
    (r"\biso\b", "isolating"), (r"\bbc\b", "brushed chrome"), (r"\bsp\b", "single pole"),
    (r"\bdp\b", "double pole"), (r"\bfr\b", "fire rated"), (r"\bss\b", "stainless"),
    (r"\bpushfit\b", "push-fit"), (r"\bcoupling\b", "straight coupler"), (r"\bplastic pipe\b",
    "polybutylene barrier pipe"), (r"\bdownlight\b", "led downlight"), (r"\bback box\b", "metal back box"),
]
IMPERIAL = {'1 1/4"': "35mm", '1 1/2"': "42mm", '1/2"': "15mm", '3/4"': "22mm", '1"': "28mm", '2"': "54mm"}
REF_PREFIX = re.compile(r"^\s*(our\s+ref|ref|part\s*no\.?|part)\s*[:#]?\s*", re.I)


@dataclass
class Candidate:
    product_id: int
    code: str
    name: str
    score: float


@dataclass
class Match:
    product_id: int | None
    method: str | None              # alias | code | search | None
    confidence: float
    candidates: list[Candidate] = field(default_factory=list)
    reason: str = ""


def normalise(text: str) -> str:
    t = text.lower()
    if "bsp" not in t:  # BSP threads are named in inches in the catalogue; only pipe sizes are metric
        for imp, metric in IMPERIAL.items():  # longest first, so 1 1/4" isn't read as 1"
            t = t.replace(imp, metric)
    # shorthand drops the angle: "45 elbow" is the 45 degree one, a plain "elbow" means 90
    t = re.sub(r"\b45 elbow\b", "elbow 45°", t)
    t = re.sub(r"\belbow\b(?!\s*(45|90))", "elbow 90°", t)
    for pat, rep in EXPAND:
        t = re.sub(pat, rep, t)
    return re.sub(r"\s+", " ", t).strip()


def by_alias(db: Session, customer_id: int | None, raw: str) -> Product | None:
    if not customer_id:
        return None
    key = REF_PREFIX.sub("", raw).strip()
    row = db.scalar(select(CustomerAlias).where(CustomerAlias.customer_id == customer_id,
                                                func.lower(CustomerAlias.alias_text) == key.lower()))
    return db.get(Product, row.product_id) if row else None


def by_code(db: Session, raw: str) -> Product | None:
    key = raw.strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{6,}", key):
        return None
    p = db.scalar(select(Product).where(Product.code == key))
    if p:
        return p
    return db.scalar(select(Product).where(func.replace(Product.code, "-", "") == key.replace("-", "")))


def search(db: Session, raw: str) -> list[Candidate]:
    q = normalise(raw)
    sim = func.similarity(Product.name, q)
    trigram = db.execute(select(Product.id, sim.label("s")).order_by(Product.name.op("<->")(q))
                         .limit(20)).all()
    vec = embed_query(q)
    vector = db.execute(select(Product.id, (1 - Product.embedding.cosine_distance(vec)).label("s"))
                        .order_by(Product.embedding.cosine_distance(vec)).limit(20)).all()

    fused: dict[int, float] = {}
    for ranked in (trigram, vector):
        for rank, row in enumerate(ranked):
            fused[row.id] = fused.get(row.id, 0.0) + 1 / (RRF_K + rank + 1)
    tri = {r.id: float(r.s) for r in trigram}
    vsim = {r.id: float(r.s) for r in vector}
    # RRF picks the shortlist (robust to either method being off); the final order uses the
    # average of the two similarities, which is also the score shown to people (0..1)
    shortlist = sorted(fused, key=fused.get, reverse=True)[:TOP_K * 2]
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(shortlist)))}
    cands = [Candidate(pid, products[pid].code, products[pid].name,
                       round((tri.get(pid, 0.0) + vsim.get(pid, 0.0)) / 2, 4)) for pid in shortlist]
    return sorted(cands, key=lambda c: c.score, reverse=True)[:TOP_K]


def confidence(cands: list[Candidate]) -> float:
    """High only when the best candidate is good AND clearly ahead of the next one.
    A near-tie (e.g. the same fitting from two brands) must go to a person."""
    if not cands:
        return 0.0
    best = cands[0].score
    margin = max(0.0, best - (cands[1].score if len(cands) > 1 else 0.0))
    return round(best * min(1.0, margin / 0.05), 4)


def _without_brand(code: str) -> str:
    for b in BRAND_CODES:
        code = code.replace(b, "-")
    return code


def _without_pack(code: str) -> str:
    return re.sub(r"-P\d+$", "", code)


def brand_ambiguous(raw: str, cands: list[Candidate]) -> bool:
    """No brand written, and the top two are the same item from different brands."""
    if any(b in raw.lower() for b in BRANDS) or len(cands) < 2:
        return False
    return _without_brand(cands[0].code) == _without_brand(cands[1].code)


def prefer_pack(db: Session, cands: list[Candidate], qty: float | None, unit: str | None) -> list[Candidate]:
    """'20 pcs' of something sold singly and in packs of 10: the pack variant is meant
    when the count is a whole number of packs. Moves that variant to the top."""
    if unit != "pcs" or not qty or not cands:
        return cands
    base = _without_pack(cands[0].code)
    packs = db.scalars(select(Product).where(Product.code.like(base + "-P%"))).all()
    for p in packs:
        if p.pack_qty > 1 and qty % p.pack_qty == 0:
            top = Candidate(p.id, p.code, p.name, cands[0].score)
            return [top] + [c for c in cands if c.product_id != p.id][: TOP_K - 1]
    return cands


PREFERRED_BRAND_CONFIDENCE = 0.6  # above the 0.5 auto-approve threshold; see match_eval --history


def match_line(db: Session, raw: str, customer_id: int | None,
               qty: float | None = None, unit: str | None = None,
               preference: BrandPreference | None | bool = True) -> Match:
    """preference: True = look it up from order history; or pass one in (evals); None = don't use."""
    p = by_alias(db, customer_id, raw)
    if p:
        return Match(p.id, "alias", 1.0, [Candidate(p.id, p.code, p.name, 1.0)], "known customer reference")
    p = by_code(db, raw)
    if p:
        return Match(p.id, "code", 1.0, [Candidate(p.id, p.code, p.name, 1.0)], "product code")
    if REF_PREFIX.match(raw) or re.fullmatch(r"\s*\d{2}-\d{3}\s*", raw):
        return Match(None, None, 0.0, [], "customer reference not known yet")
    cands = prefer_pack(db, search(db, raw), qty, unit)
    conf = confidence(cands)
    if brand_ambiguous(raw, cands):
        pref = brand_preference(db, customer_id) if preference is True else preference
        same_item = _without_brand(cands[0].code)
        pick = next((c for c in cands if pref and pref.code_part in c.code
                     and _without_brand(c.code) == same_item), None)
        if pick:
            # the text can't tell, but this customer's checked orders can
            ordered = [pick] + [c for c in cands if c.product_id != pick.product_id]
            return Match(pick.product_id, "history", PREFERRED_BRAND_CONFIDENCE, ordered,
                         f"brand not stated; customer usually buys {pref.brand} "
                         f"({int(pref.share * 100)}% of {pref.lines} checked lines)")
        return Match(cands[0].product_id, "search", min(conf, 0.2), cands,
                     "brand not stated; same item exists from several brands")
    reason = "clear best match" if conf >= 0.5 else (
        "several products are almost equally likely" if cands else "no similar product found")
    return Match(cands[0].product_id if cands else None, "search", conf, cands, reason)


def selling_qty(written_qty: float, unit: str | None, pack_qty: int) -> float:
    """Customers sometimes count pieces; we sell packs. 20 pcs of a pack of 10 = 2."""
    if unit == "pcs" and pack_qty > 1:
        return written_qty / pack_qty
    return written_qty
