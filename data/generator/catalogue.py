"""Synthetic but realistic plumbing / electrical catalogue, customers and price rules.

Everything is seeded, so the same seed always gives the same data. Run:
    python -m data.generator.catalogue --out data/seed
Writes products.csv, customers.csv, customer_aliases.csv, price_rules.csv.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import random
from dataclasses import dataclass, asdict
from pathlib import Path

SEED = 42

# ---------------------------------------------------------------- products
# Each family: code prefix, name template, the attribute lists it is built from, unit, pack sizes, base price.
COPPER_MM = [8, 10, 15, 22, 28, 35, 42, 54]
IMPERIAL = {15: '1/2"', 22: '3/4"', 28: '1"', 35: '1 1/4"', 42: '1 1/2"', 54: '2"'}
PLASTIC_MM = [15, 22, 28, 32, 40, 50, 110]
CABLE_MM2 = [1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 16.0]

FAMILIES = [
    # (prefix, template, {attr: values}, unit, pack options, base price per unit £)
    ("CU-EL90", "Copper Elbow 90° {mm}mm {joint}", {"mm": COPPER_MM, "joint": ["End Feed", "Solder Ring", "Compression"]}, "each", [1, 10], 1.10),
    ("CU-EL45", "Copper Elbow 45° {mm}mm {joint}", {"mm": COPPER_MM, "joint": ["End Feed", "Solder Ring", "Compression"]}, "each", [1, 10], 1.25),
    ("CU-TEE", "Copper Equal Tee {mm}mm {joint}", {"mm": COPPER_MM, "joint": ["End Feed", "Solder Ring", "Compression"]}, "each", [1, 10], 1.60),
    ("CU-CPL", "Copper Straight Coupler {mm}mm {joint}", {"mm": COPPER_MM, "joint": ["End Feed", "Solder Ring", "Compression"]}, "each", [1, 10], 0.80),
    ("CU-TUBE", "Copper Tube {mm}mm x {len}m {grade}", {"mm": COPPER_MM, "len": [2, 3, 6], "grade": ["Table X", "Table Y"]}, "length", [1], 6.50),
    ("CU-RED", "Copper Reducer {mm}mm x {mm2}mm {joint}", {"mm": COPPER_MM[2:], "mm2": COPPER_MM[:4], "joint": ["End Feed", "Compression"]}, "each", [1, 10], 1.40),
    ("BR-VLV-ISO", "Brass Isolating Valve {mm}mm {handle}", {"mm": [15, 22, 28], "handle": ["Slotted", "Lever Red", "Lever Blue"]}, "each", [1, 5], 3.90),
    ("BR-VLV-GATE", "Brass Gate Valve {mm}mm {joint}", {"mm": [15, 22, 28, 35, 42, 54], "joint": ["Compression", "BSP Female"]}, "each", [1], 9.50),
    ("BR-VLV-BALL", "Brass Full Bore Ball Valve {inch} BSP {handle}", {"inch": list(IMPERIAL.values()), "handle": ["Lever", "Butterfly"]}, "each", [1], 7.20),
    ("PB-PIPE", "Polybutylene Barrier Pipe {mm}mm x {len}m Coil", {"mm": [10, 15, 22, 28], "len": [25, 50, 100]}, "coil", [1], 38.00),
    ("PB-EL90", "Push-Fit Elbow 90° {mm}mm {colour}", {"mm": [10, 15, 22, 28], "colour": ["White", "Grey"]}, "each", [1, 10], 2.10),
    ("PB-TEE", "Push-Fit Equal Tee {mm}mm {colour}", {"mm": [10, 15, 22, 28], "colour": ["White", "Grey"]}, "each", [1, 10], 2.80),
    ("PB-INS", "Pipe Insert Stainless {mm}mm", {"mm": [10, 15, 22, 28]}, "each", [10, 50], 0.35),
    ("WST-PIPE", "Solvent Weld Waste Pipe {mm}mm x {len}m {colour}", {"mm": [32, 40, 50], "len": [3, 4], "colour": ["White", "Grey", "Black"]}, "length", [1], 5.40),
    ("WST-BND", "Solvent Weld Bend {deg}° {mm}mm {colour}", {"deg": [45, 90], "mm": [32, 40, 50], "colour": ["White", "Grey", "Black"]}, "each", [1, 10], 1.30),
    ("SOIL-PIPE", "Soil Pipe Plain End {mm}mm x {len}m {colour}", {"mm": [110], "len": [2.5, 3, 4], "colour": ["Grey", "Black", "White"]}, "length", [1], 16.80),
    ("SOIL-BND", "Soil Bend Single Socket {deg}° 110mm {colour}", {"deg": [45, 87.5, 92.5], "colour": ["Grey", "Black", "White"]}, "each", [1], 7.60),
    ("TRAP", "{kind} Trap {mm}mm {seal}mm Seal", {"kind": ["Bottle", "Tubular P", "Tubular S", "Bath", "Shower"], "mm": [32, 40], "seal": [38, 75]}, "each", [1], 4.20),
    ("RAD-VLV", "Radiator Valve {kind} 15mm x 1/2\" {finish}", {"kind": ["Manual Angled", "Manual Straight", "TRV Angled", "Lockshield Angled"], "finish": ["White", "Chrome", "Anthracite"]}, "pair", [1], 11.50),
    ("CBL-TE", "Twin & Earth Cable {mm2}mm² {len}m {colour}", {"mm2": CABLE_MM2[:5], "len": [50, 100], "colour": ["Grey", "White"]}, "drum", [1], 42.00),
    ("CBL-FLEX", "{cores} Core Flex {mm2}mm² {len}m {colour}", {"cores": [2, 3], "mm2": [0.75, 1.0, 1.5, 2.5], "len": [50, 100], "colour": ["White", "Black"]}, "drum", [1], 31.00),
    ("CBL-SWA", "SWA Armoured Cable {cores} Core {mm2}mm² per metre", {"cores": [2, 3, 4], "mm2": [1.5, 2.5, 4.0, 6.0, 10.0, 16.0]}, "metre", [1], 2.40),
    ("ACC-SKT", "{gang} Gang {sw} Socket {finish}", {"gang": [1, 2], "sw": ["Switched", "Unswitched", "USB-A/C Switched"], "finish": ["White Moulded", "Brushed Chrome", "Matt Black", "Polished Brass"]}, "each", [1, 10], 3.20),
    ("ACC-SW", "{gang} Gang {way} Way Light Switch {finish}", {"gang": [1, 2, 3], "way": [1, 2], "finish": ["White Moulded", "Brushed Chrome", "Matt Black", "Polished Brass"]}, "each", [1, 10], 2.60),
    ("ACC-FCU", "Fused Spur {kind} 13A {finish}", {"kind": ["Switched", "Unswitched", "Switched with Neon"], "finish": ["White Moulded", "Brushed Chrome", "Matt Black"]}, "each", [1], 4.80),
    ("CON-MCB", "MCB Type {curve} {amps}A {poles}", {"curve": ["B", "C"], "amps": [6, 10, 16, 20, 32, 40], "poles": ["Single Pole", "Double Pole"]}, "each", [1], 5.90),
    ("CON-RCBO", "RCBO Type {curve} {amps}A 30mA", {"curve": ["B", "C"], "amps": [6, 10, 16, 20, 32, 40]}, "each", [1], 24.00),
    ("LED-DL", "LED Downlight Fire Rated {w}W {k}K {finish}", {"w": [5, 6, 8], "k": [3000, 4000, 6500], "finish": ["White", "Chrome", "Brushed Nickel"]}, "each", [1, 10], 7.90),
    ("BOX-BACK", "Metal Back Box {gang} Gang {depth}mm", {"gang": [1, 2], "depth": [16, 25, 35, 47]}, "each", [1, 10], 0.70),
    ("CLIP-CBL", "Cable Clips {kind} {size}mm", {"kind": ["Flat Twin", "Round"], "size": [4, 5, 6, 7, 8, 10, 12]}, "box of 100", [1], 1.90),
    ("PTFE", "PTFE Tape 12mm x {len}m", {"len": [12, 25]}, "roll", [10], 0.40),
    ("SOLDER", "Lead-Free Solder Wire {g}g", {"g": [250, 500]}, "reel", [1], 14.00),
    ("CLIP-PIPE", "Pipe Clip {kind} {mm}mm", {"kind": ["Single", "Double", "Hinged"], "mm": [15, 22, 28]}, "bag of 10", [1], 1.20),
]


# Invented brands. Branded families exist once per brand, so 'copper elbow 15mm' is genuinely ambiguous.
BRANDS = ["Kestrel", "Northway", "ProFlow"]
BRANDED = {"CU", "BR", "PB", "ACC", "LED", "CON"}


@dataclass
class Product:
    code: str
    name: str
    description: str
    unit: str
    pack_qty: int
    price_gbp: float
    family: str


def _fmt(v) -> str:
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def _token(v) -> str:
    """Short code piece: numbers stay, words become initials ('End Feed' -> 'EF', 'Brushed Chrome' -> 'BC')."""
    t = _fmt(v).replace('"', "IN").replace("/", "")
    if t.replace(".", "").replace(" ", "").isdigit() or t.replace(".", "").isdigit():
        return t.replace(".", "P").replace(" ", "")
    words = [w for w in t.replace("-", " ").split() if w]
    return "".join(w[0] for w in words).upper() if len(words) > 1 else t[:4].upper()


def build_products(rng: random.Random) -> list[Product]:
    out: list[Product] = []
    seen: set[str] = set()
    for prefix, template, attrs, unit, packs, base in FAMILIES:
        if prefix.split("-")[0] in BRANDED:
            attrs = {"brand": BRANDS, **attrs}
            template = "{brand} " + template
        keys = list(attrs)
        for combo in itertools.product(*(attrs[k] for k in keys)):
            vals = dict(zip(keys, combo))
            if "mm2" in vals and "mm" in vals and vals["mm2"] >= vals["mm"]:
                continue  # reducer must go down in size
            for pack in packs:
                name = template.format(**{k: _fmt(v) for k, v in vals.items()})
                if pack > 1:
                    name += f" (Pack of {pack})"
                code = f"{prefix}-" + "-".join(_token(v) for v in combo) + (f"-P{pack}" if pack > 1 else "")
                base_code, n = code, 2
                while code in seen:  # never drop a product because two codes happen to abbreviate the same
                    code, n = f"{base_code}{n}", n + 1
                seen.add(code)
                size = vals.get("mm") or vals.get("mm2") or 1
                price = base * (1 + float(size) / 40) * pack * rng.uniform(0.9, 1.1)
                desc = f"{name}. {FAMILY_BLURB.get(prefix.split('-')[0], 'Trade quality.')}"
                if "mm" in vals and vals["mm"] in IMPERIAL and prefix.startswith("CU"):
                    desc += f" Imperial equivalent approx {IMPERIAL[vals['mm']]}."
                out.append(Product(code, name, desc, unit, pack, round(price, 2), prefix))
    return out


FAMILY_BLURB = {
    "CU": "WRAS approved copper fitting for hot and cold water and central heating.",
    "BR": "DZR brass valve, WRAS approved.",
    "PB": "Push-fit plumbing system, demountable, suitable for heating and potable water.",
    "WST": "Solvent weld waste system to BS EN 1329.",
    "SOIL": "Soil and vent system to BS EN 1329.",
    "TRAP": "Anti-syphon waste trap.",
    "RAD": "Radiator valve pair, supplied with drain-off.",
    "CBL": "Cable to BS 6004 / BS 5467, CPR rated.",
    "ACC": "Wiring accessory to BS 1363 / BS EN 60669.",
    "CON": "Circuit protection for consumer units to BS EN 60898 / 61009.",
    "LED": "Fire rated for 30/60/90 minute ceilings, IP65.",
    "BOX": "Galvanised steel with knockouts.",
    "CLIP": "Fixings for cable or pipe.",
    "PTFE": "Thread sealing tape.",
    "SOLDER": "Lead-free for potable water.",
}

# ---------------------------------------------------------------- customers
TRADES = ["Plumbing & Heating", "Electrical Services", "Building Services", "Maintenance", "Heating Engineers",
          "Electrical Contractors", "Property Services", "M&E Ltd", "Installations", "Renovations"]
TOWNS = ["Liverpool", "Wirral", "St Helens", "Warrington", "Chester", "Southport", "Wigan", "Runcorn", "Bootle",
         "Crosby", "Widnes", "Ormskirk", "Preston", "Bolton", "Salford", "Stockport"]
SURNAMES = ["Hughes", "Walsh", "Doyle", "Kaur", "Patel", "Murphy", "Jones", "Byrne", "Okafor", "Nowak", "Evans",
            "Kelly", "Shah", "Price", "Reid", "Brennan", "Clarke", "Ahmed", "Taylor", "Quinn"]
FIRST = ["Dave", "Sam", "Priya", "Tom", "Aisha", "Gary", "Megan", "Kevin", "Lisa", "Paul", "Nadia", "Chris",
         "Jo", "Mark", "Rachel", "Steve", "Tariq", "Emma", "Liam", "Sophie"]

# Writing habits that the order generator uses to make each customer's orders messy in their own way.
HABITS = ["abbreviates", "imperial_sizes", "own_part_numbers", "old_codes", "typos", "terse", "polite_long",
          "units_mixed", "no_po", "uses_codes"]


@dataclass
class Customer:
    id: int
    account_code: str
    name: str
    contact: str
    email: str
    town: str
    habits: str  # comma-separated
    discount_pct: float


def build_customers(rng: random.Random, n: int = 40) -> list[Customer]:
    out = []
    for i in range(1, n + 1):
        sur = rng.choice(SURNAMES)
        trade = rng.choice(TRADES)
        name = f"{sur} {trade}" if rng.random() < 0.7 else f"{sur} & {rng.choice(SURNAMES)} {trade}"
        first = rng.choice(FIRST)
        domain = "".join(c for c in (sur + trade.split()[0]).lower() if c.isalnum())[:18]
        habits = rng.sample(HABITS, k=rng.randint(2, 4))
        out.append(Customer(i, f"C{1000 + i}", name, f"{first} {sur}", f"{first.lower()}@{domain}.co.uk",
                            rng.choice(TOWNS), ",".join(habits), rng.choice([0, 0, 2.5, 5, 7.5, 10, 12.5, 15])))
    return out


def build_aliases(rng: random.Random, customers: list[Customer], products: list[Product]) -> list[dict]:
    """Customers with 'own_part_numbers' have their own codes for some products (e.g. 'our ref 44-112').
    These are the *known* aliases, as if a person had already taught the system. The generator also uses some
    aliases the system has never seen, which is what the review queue is for."""
    rows = []
    for c in customers:
        if "own_part_numbers" not in c.habits:
            continue
        for p in rng.sample(products, k=rng.randint(15, 40)):
            rows.append({"customer_id": c.id, "alias_text": f"{rng.randint(10, 99)}-{rng.randint(100, 999)}",
                         "product_code": p.code, "known": rng.random() < 0.7})
    return rows


def build_price_rules(rng: random.Random, customers: list[Customer], products: list[Product]) -> list[dict]:
    rules = []
    for c in customers:
        if c.discount_pct:
            rules.append({"customer_id": c.id, "product_code": "", "family": "", "discount_pct": c.discount_pct})
        for fam in rng.sample(sorted({p.family for p in products}), k=rng.randint(0, 3)):
            rules.append({"customer_id": c.id, "product_code": "", "family": fam,
                          "discount_pct": rng.choice([5, 10, 15, 20])})
    return rules


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/seed")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    products = build_products(rng)
    customers = build_customers(rng)
    write_csv(out / "products.csv", [asdict(p) for p in products])
    write_csv(out / "customers.csv", [asdict(c) for c in customers])
    write_csv(out / "customer_aliases.csv", build_aliases(rng, customers, products))
    write_csv(out / "price_rules.csv", build_price_rules(rng, customers, products))
    print(f"{len(products)} products, {len(customers)} customers -> {out}")


if __name__ == "__main__":
    main()
