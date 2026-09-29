# OrderDesk — Product Requirements

## Problem

B2B distributors (plumbing, electrical, building supplies) still get most orders as emails, PDFs and photos.
Customers use their own part numbers, abbreviations, old codes and imperial sizes. Staff retype every order into
the ERP, look up products, apply the customer's prices and chase missing details. It is slow and error-prone.

## Users

| User | Needs |
|---|---|
| Order-entry staff (reviewer) | Only see the lines that need a human. Fix them fast. |
| Sales-ops manager (admin) | Know how many orders went through untouched, how many errors reached the ERP, what it costs. |

## Goals and non-goals

Goals: turn a messy order into a checked, priced order; know when to ask a human; measure all of it.

Non-goals: a real ERP integration, real customer data, invoicing, stock management, a mobile app.

## Success metrics (measured on the eval set, never estimated)

| Metric | Target |
|---|---|
| Precision of auto-approved lines | ≥ 99% |
| Orders needing no edits | report it; aim ≥ 50% |
| Line match accuracy, top-1 / top-5 | report both |
| Held-out gap (hand-written vs generated) | report it; explain it |
| Injection test orders that changed a price or product | 0 |
| p95 time, received → routed | report it |
| Cost per order (£) | report it |

## Data

- **Catalogue:** ~2,000 synthetic plumbing and electrical products, 3 invented brands (so "15mm copper elbow"
  is ambiguous), pack sizes, list prices. Seeded, so the same seed gives the same data.
- **Customers:** 40, each with 2–4 writing habits: abbreviates, imperial sizes, own part numbers, old codes,
  typos, terse, polite and long, pieces instead of packs, no PO.
- **Aliases:** about half of each customer's part numbers known in advance; the rest only appear in orders.
- **Price rules:** account-wide discounts and per-family discounts.
- **Eval set v1:** 300 generated orders (emails + PDFs) with JSON labels, each line tagged with the kind of mess
  it contains. Plus 30 hand-written held-out orders, written without looking at the generator. Freeze v1 before
  tuning anything; new cases go into v2 and both are reported.

Label format:

```json
{
  "id": "gen-0001", "label_version": 1, "format": "email", "document": "gen-0001.eml",
  "customer_account": "C1007", "po_number": "PO4471", "delivery_date": "2026-10-09",
  "lines": [{"raw": "3/4 cu elbows comp", "product_code": "CU-EL90-NORT-22-COMP", "qty": 20,
             "unit": "each", "mess": ["abbreviated", "imperial_size", "brand_omitted"]}]
}
```

`null` for anything the order does not contain. `"product_code": null` for a line that should be flagged.
Quantities are in selling units: "20 pcs" of a pack-of-10 product is `qty: 2`.

---

## Phase 1 — Data and foundations (week 1)

**Build:** Docker Compose (db, api). SQLAlchemy models for every table in the architecture doc. Seed loader
(idempotent). Catalogue + customer generator. Order generator (emails + PDFs) with labels. 300 generated orders.
Start the 30 held-out orders. `docs/decisions.md` started.

**Done when:**
- `docker compose up` gives a healthy API and database.
- One command seeds everything; running it twice changes nothing.
- The generator is deterministic (test: same seed → identical files).
- Every label points at a real product code (test).
- `/products/search?q=cu elbow 15mm comp` returns sensible results from trigram search.

## Phase 2 — Ingest and extraction (week 2)

**Build:** `POST /documents` (upload) creating a queued row; duplicate files rejected by hash. Worker using
`FOR UPDATE SKIP LOCKED`. Text from emails and PDFs. LLM adapter (Groq, main + fallback) that logs every call
to `llm_calls`. Extraction prompt v1 → Pydantic schema, with one retry on invalid output.
`evals/run_eval.py --stage extract`.

**Polish:**
- Real inbox: an inbound email route (free Mailgun or Postmark inbound webhook → `POST /inbound/email`), so
  orders can be forwarded and seen arriving live. Upload stays as the fallback.
- Evidence spans: extraction returns, for every line, the exact piece of source text it came from (start/end
  offsets). The review screen uses these to highlight where each line was read.

**Done when:**
- Uploading the same file twice creates one document.
- A crashed worker leaves the job to be picked up again, not lost.
- Every LLM call has a row with model, prompt version, tokens, latency, cost.
- First results table: field precision/recall for customer, PO, date, qty, unit — in `docs/evaluation.md`.
- An order forwarded to the inbound address appears as a document within a minute.
- Every extracted line has a span that points at real text in the document (test).

## Phase 3 — Matching, pricing, routing, export (week 3)

**Build:** matcher (alias → code → trigram → vector) with top-5 candidates and a confidence score. Product
embeddings. Pricing in code. Routing by threshold. Mock ERP with idempotency. Alembic migrations.

**Polish:**
- A plain-English reason on every flagged line, built by code from the match result: "Brand not stated; this
  customer usually buys Northway", "Customer part number 44-112 not seen before", "20 pcs = 2 packs of 10".
- Precision vs auto-approve curve saved as a chart in `docs/evaluation.md`, with the chosen threshold marked.
- Results broken down by mess tag, so the weakest kind of line is obvious.
- Before/after log: each change that moves a metric gets a row in `docs/evaluation.md` (what changed, which
  metric, from → to, on which eval version).

**Done when:**
- Eval reports line match accuracy top-1 and top-5, broken down by mess tag.
- Precision of auto-approved lines vs auto-approve rate is plotted for several thresholds; one is chosen and
  written down in decisions.md.
- Sending the same approved order to the ERP twice creates one ERP order (test).
- Every line routed to review has a reason (test).
- The curve and the by-tag table are generated by `run_eval.py`, not drawn by hand.
- **Milestone:** end-to-end from the command line: file in → priced order out. First README with numbers.

## Phase 4 — Review UI, agent, safety (week 4)

**Build:** React + TypeScript inbox, review screen (document left, order right, unsure lines with candidates and
reason), approve/fix. Each fix → customer alias + new eval case (v2). Email/password auth with JWT, roles
reviewer/admin. Bounded resolve agent (≤ 4 tool calls). 20 prompt-injection test orders. Audit log.

**Polish:**
- Start the frontend from PolicyPilot's setup (Next.js, dark theme, the same UI components, Redux Toolkit +
  RTK Query) so it looks finished from day one.
- Side-by-side review: source document left, extracted order right; hovering a line highlights its evidence span.
- The correction loop is visible: after a fix, the UI shows "Saved as alias for <customer>", and the order
  list marks later orders that matched because of it.
- Clear empty, loading and error states; keyboard shortcuts for approve / next line.

**Done when:**
- A reviewer can fix a line; the next order from that customer with the same text matches automatically.
- Agent tool calls are logged; any product outside the candidates is rejected (test).
- 0 of 20 injection orders change a price or product.
- Only admins can change thresholds and price rules (test).
- The injection result is stated in the README as a number ("0 of 20 injected orders changed a price or product").

## Phase 5 — Ship (week 5)

**Build:** GitHub Actions: tests on every push, eval on every PR (fails if auto-approve precision drops below
target). OpenTelemetry traces. Metrics page (auto-approve rate, review rate, accuracy, p95, cost/order). Deploy
(AWS Lightsail or Render + Neon) with a demo login. Demo video. Final README with results. Optional: OCR for
scanned orders, MCP server.

**Polish:**
- Evaluation page (`docs/evaluation.md`, linked at the top of the README): dataset and version, results by field
  and by mess tag, held-out gap, precision vs auto-approve curve, p50/p95 time, cost per order, before/after log.
- Failure gallery: 3–5 orders it still gets wrong, each with the document, what it did, what was right, and why.
- Metrics page in the app, built from `llm_calls` and orders: auto-approve rate, review rate, accuracy on the
  latest eval run, p95 time, cost per order, by day. Each LLM call traceable to model and prompt version.
- CI eval gate: the eval runs on every pull request and fails if auto-approved precision drops below target.
- 30-second README: one-line pitch, demo GIF, architecture diagram, results table, how to run.
- Public demo: a demo login with pre-loaded sample orders in every state, so a visitor can click through
  without uploading anything. Reset nightly.
- Optional standout: an MCP server (`find_product`, `order_status`, `submit_order_for_review`) so an AI assistant
  can use OrderDesk. Reuse the pattern from PolicyPilot.

**Done when:**
- A public URL with a demo account works, with sample orders already there.
- `docs/evaluation.md` includes the failure gallery and the weak numbers, not only the best ones.
- CI badge green; eval results in the README state the dataset they came from.
- The 3-minute demo runs without edits: scanned order in → 11/12 lines auto → one flagged → fix → next order
  matches → metrics page.

## Rules

- No new features after phase 4. Only fixes, tests and docs.
- If a week slips, cut OCR and MCP before cutting evaluation.
- Every number in the README says which dataset it came from. Say the data is synthetic.
