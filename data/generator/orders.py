"""Generate messy, labelled test orders (emails and PDF purchase orders) from the seeded catalogue.

    python -m data.generator.orders --seed-dir /data/seed --out /data/eval/generated --n 300

Each order is written as <id>.eml or <id>.pdf plus <id>.json holding the expected answer (the label).
Mess is controlled and comes from each customer's habits (see catalogue.HABITS), so results can be broken
down by the kind of mess that caused a failure.

The 30 held-out orders are NOT made here. Write those by hand in data/eval/held_out without reading this
file, so the eval can show whether the system only learned this generator's quirks.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

LABEL_VERSION = 1
TODAY = date(2026, 10, 5)  # fixed so the same seed always gives the same files

ABBREV = [  # (full, short) applied in order, case-insensitive
    ("Copper ", "cu "), ("Elbow 90°", "elbow"), ("Elbow 45°", "45 elbow"), ("Equal Tee", "tee"),
    ("Straight Coupler", "coupling"), ("Compression", "comp"), ("End Feed", "EF"), ("Solder Ring", "SR"),
    ("Isolating Valve", "iso valve"), ("Full Bore Ball Valve", "ball valve"), ("Gate Valve", "gate valve"),
    ("Polybutylene Barrier Pipe", "plastic pipe"), ("Push-Fit", "pushfit"), ("Solvent Weld ", ""),
    ("Twin & Earth Cable", "T&E"), ("Armoured Cable", ""), ("Socket", "skt"), ("Light Switch", "switch"),
    ("Brushed Chrome", "BC"), ("White Moulded", "white"), ("Single Pole", "SP"), ("Double Pole", "DP"),
    ("Fire Rated", "FR"), ("LED Downlight", "downlight"), ("Metal Back Box", "back box"), ("Stainless", "ss"),
    (" per metre", ""), ("Plain End", ""), ("Single Socket", ""),
]
IMPERIAL = {"15mm": '1/2"', "22mm": '3/4"', "28mm": '1"', "35mm": '1 1/4"', "42mm": '1 1/2"', "54mm": '2"'}
GREETINGS = ["Hi", "Hello", "Morning", "Afternoon", "Hiya", "Dear Sales Team,"]
SIGNOFFS = ["Cheers", "Thanks", "Many thanks", "Regards", "Ta", "Kind regards"]


def load_seed(d: Path):
    read = lambda n: list(csv.DictReader((d / n).open(encoding="utf-8")))
    products = read("products.csv")
    customers = read("customers.csv")
    aliases = read("customer_aliases.csv")
    return products, customers, aliases


def preferred_brand(customer: dict) -> str:
    # Stable per customer: when they leave the brand out, they mean the one they always buy.
    return ["Kestrel", "Northway", "ProFlow"][int(customer["id"]) % 3]


def messy_line(rng: random.Random, p: dict, c: dict, habits: set, alias: str | None) -> tuple[str, int, int, list[str]]:
    """Return (text, qty_written, qty_expected, mess_tags) for one order line."""
    tags: list[str] = []
    pack = int(p["pack_qty"])
    qty = rng.choice([1, 1, 2, 2, 3, 4, 5, 6, 10, 12, 20, 25, 50]) if pack == 1 else rng.choice([1, 2, 3, 5])
    written_qty = qty

    if alias and rng.random() < 0.8:
        text = rng.choice([f"our ref {alias}", f"ref {alias}", f"{alias}", f"part no {alias}"])
        tags.append("customer_part_number")
    elif "uses_codes" in habits and rng.random() < 0.35:
        text = p["code"]
        tags.append("product_code")
    elif "old_codes" in habits and rng.random() < 0.3:
        text = p["code"].replace("-", "")  # old system had no dashes
        tags.append("old_code")
    else:
        text = p["name"]
        brand = text.split()[0]
        if brand in ("Kestrel", "Northway", "ProFlow") and (brand == preferred_brand(c)) and rng.random() < 0.6:
            text = text[len(brand) + 1:]
            tags.append("brand_omitted")
        if "abbreviates" in habits or "terse" in habits:
            for full, short in ABBREV:
                text = re.sub(re.escape(full), short, text, flags=re.I)
            tags.append("abbreviated")
        if "imperial_sizes" in habits and ("Copper" in p["name"] or "valve" in text.lower()):
            for metric, imp in IMPERIAL.items():
                if metric in text and rng.random() < 0.7:
                    text = text.replace(metric, imp)
                    tags.append("imperial_size")
        if "typos" in habits and rng.random() < 0.5:
            text = typo(rng, text)
            tags.append("typo")
        text = re.sub(r"\s+", " ", text).strip()
        if rng.random() < 0.5:
            text = text.lower()

    if pack > 1 and "units_mixed" in habits and rng.random() < 0.6:
        written_qty = qty * pack  # they count pieces, we sell packs
        text = re.sub(r"\s*\(pack of \d+\)", "", text, flags=re.I)
        tags.append("qty_in_pieces")
    return text, written_qty, qty, tags


def typo(rng: random.Random, s: str) -> str:
    words = s.split()
    idx = [i for i, w in enumerate(words) if len(w) > 4 and w.isalpha()]
    if not idx:
        return s
    i = rng.choice(idx)
    w = list(words[i])
    j = rng.randrange(1, len(w) - 1)
    w[j], w[j + 1] = w[j + 1], w[j]
    words[i] = "".join(w)
    return " ".join(words)


def fmt_line(rng: random.Random, text: str, qty: int, pieces: bool, style: int) -> str:
    q = f"{qty} pcs" if pieces else str(qty)
    return [f"{q} x {text}", f"{text} - qty {q}", f"{text} x{q}", f"{q} off {text}", f"{text} ({q})"][style]


def make_order(rng: random.Random, n: int, products: list[dict], customers: list[dict], aliases: list[dict]) -> dict:
    c = rng.choice(customers)
    habits = set(c["habits"].split(","))
    my_aliases = [a for a in aliases if a["customer_id"] == c["id"]]
    by_code = {p["code"]: p for p in products}

    # Customers buy within a couple of trades, which makes orders look real.
    families = sorted({p["family"] for p in products})
    fams = rng.sample(families, k=rng.randint(1, 4))
    pool = [p for p in products if p["family"] in fams]
    n_lines = rng.choice([1, 2, 3, 3, 4, 5, 6, 8, 10, 12])
    chosen: list[tuple[dict, str | None]] = []
    for _ in range(n_lines):
        if my_aliases and rng.random() < 0.35:
            a = rng.choice(my_aliases)
            chosen.append((by_code[a["product_code"]], a["alias_text"]))
        else:
            chosen.append((rng.choice(pool), None))
    # no duplicate products in one order
    seen, lines = set(), []
    for p, alias in chosen:
        if p["code"] in seen:
            continue
        seen.add(p["code"])
        text, wq, q, tags = messy_line(rng, p, c, habits, alias)
        lines.append({"raw": text, "written_qty": wq, "product_code": p["code"], "qty": q, "unit": p["unit"],
                      "mess": tags, "alias_known": None if alias is None else
                      next(a["known"] == "True" for a in my_aliases if a["alias_text"] == alias)})

    po = None if ("no_po" in habits and rng.random() < 0.8) else rng.choice(
        [f"PO{rng.randint(1000, 99999)}", f"{rng.randint(100, 999)}/{rng.randint(10, 99)}", f"JOB-{rng.randint(100, 9999)}"])
    delivery = None if rng.random() < 0.25 else TODAY + timedelta(days=rng.randint(1, 14))
    fmt = "pdf" if rng.random() < 0.45 else "email"
    return {"id": f"gen-{n:04d}", "label_version": LABEL_VERSION, "format": fmt, "customer_account": c["account_code"],
            "customer_name": c["name"], "contact": c["contact"], "email": c["email"], "po_number": po,
            "delivery_date": delivery.isoformat() if delivery else None, "habits": sorted(habits), "lines": lines}


def date_phrase(rng: random.Random, d: str | None) -> str:
    if not d:
        return ""
    dd = date.fromisoformat(d)
    return rng.choice([f"Need it for {dd.strftime('%d/%m')}", f"Delivery {dd.strftime('%A %d %B')} please",
                       f"Can we have this by {dd.strftime('%d/%m/%Y')}", f"required {dd.isoformat()}"])


def write_email(rng: random.Random, o: dict, path: Path) -> None:
    style = rng.randrange(5)
    polite = "polite_long" in o["habits"]
    body = []
    body.append(f"{rng.choice(GREETINGS)}\n")
    if polite:
        body.append("Hope you're well. Could you please process the following order for us and let me know if anything "
                    "is out of stock.\n")
    elif "terse" not in o["habits"]:
        body.append(rng.choice(["Can I order the below please", "Please send the following", "Order below:"]) + "\n")
    if o["po_number"]:
        body.append(rng.choice([f"PO: {o['po_number']}", f"Our order no. {o['po_number']}", f"Ref {o['po_number']}"]))
    for ln in o["lines"]:
        body.append(fmt_line(rng, ln["raw"], ln["written_qty"], "qty_in_pieces" in ln["mess"], style))
    dp = date_phrase(rng, o["delivery_date"])
    if dp:
        body.append("\n" + dp)
    body.append(f"\n{rng.choice(SIGNOFFS)}\n{o['contact']}\n{o['customer_name']}")
    subject = rng.choice(["Order", "New order", f"Order {o['po_number'] or ''}".strip(), "materials", "Re: order"])
    path.write_text(
        f"From: {o['contact']} <{o['email']}>\nTo: orders@example-supplies.co.uk\nSubject: {subject}\n"
        f"Date: {TODAY.strftime('%a, %d %b %Y')} 09:{rng.randint(10, 59)}:00 +0100\n\n" + "\n".join(body) + "\n",
        encoding="utf-8")


def write_pdf(rng: random.Random, o: dict, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 25 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, o["customer_name"])
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, y - 6 * mm, f"Contact: {o['contact']}  {o['email']}")
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(w - 20 * mm, y, "PURCHASE ORDER")
    c.setFont("Helvetica", 10)
    meta = [("PO No", o["po_number"] or ""), ("Date", TODAY.strftime("%d/%m/%Y")),
            ("Delivery", date.fromisoformat(o["delivery_date"]).strftime("%d/%m/%Y") if o["delivery_date"] else "ASAP")]
    for i, (k, v) in enumerate(meta):
        c.drawRightString(w - 20 * mm, y - (7 + 5 * i) * mm, f"{k}: {v}")
    y -= 30 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Qty")
    c.drawString(40 * mm, y, "Description")
    c.line(20 * mm, y - 2 * mm, w - 20 * mm, y - 2 * mm)
    c.setFont("Helvetica", 10)
    for ln in o["lines"]:
        y -= 7 * mm
        q = f"{ln['written_qty']}{' pcs' if 'qty_in_pieces' in ln['mess'] else ''}"
        c.drawString(20 * mm, y, q)
        c.drawString(40 * mm, y, ln["raw"][:90])
    y -= 15 * mm
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(20 * mm, y, "Please quote our PO number on all delivery notes." if o["po_number"] else "Thanks")
    c.save()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-dir", default="/data/seed")
    ap.add_argument("--out", default="/data/eval/generated")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    products, customers, aliases = load_seed(Path(a.seed_dir))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    counts = {"email": 0, "pdf": 0}
    for i in range(1, a.n + 1):
        o = make_order(rng, i, products, customers, aliases)
        doc = out / f"{o['id']}.{'eml' if o['format'] == 'email' else 'pdf'}"
        (write_email if o["format"] == "email" else write_pdf)(rng, o, doc)
        o["document"] = doc.name
        (out / f"{o['id']}.json").write_text(json.dumps(o, indent=2), encoding="utf-8")
        counts[o["format"]] += 1
    print(f"{a.n} orders -> {out}  ({counts})")


if __name__ == "__main__":
    main()
