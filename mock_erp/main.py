"""A pretend ERP, as a separate service, so OrderDesk's export crosses a real network boundary.

POST /orders with an Idempotency-Key header:
  - new key                      -> 201, creates the order, returns an ERP reference
  - same key, same body          -> 200, returns the ORIGINAL reference, creates nothing
  - same key, different body     -> 409, someone reused a key by mistake
Failure simulation (POST /admin/config) so retries can be tested:
  - fail_rate: fraction of requests that get a 503 before doing anything
  - commit_then_hang_rate: fraction that create the order, then never answer in time.
    This is the case idempotency exists for: the client can't tell it worked.
"""
import asyncio
import hashlib
import json
import random
import sqlite3
import threading
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

DB_PATH = "/tmp/erp.db"
HANG_SECONDS = 10
app = FastAPI(title="Mock ERP")
lock = threading.Lock()
config = {"fail_rate": 0.0, "commit_then_hang_rate": 0.0}


def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, idem_key TEXT UNIQUE, body_hash TEXT,
        erp_ref TEXT, body TEXT, created_at REAL)""")
    return c


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/config")
def set_config(cfg: dict):
    config.update({k: float(v) for k, v in cfg.items() if k in config})
    return config


@app.post("/admin/reset")
def reset():
    with lock, db() as c:
        c.execute("DELETE FROM orders")
    config.update(fail_rate=0.0, commit_then_hang_rate=0.0)
    return {"reset": True}


@app.get("/orders")
def list_orders():
    with db() as c:
        rows = c.execute("SELECT erp_ref, idem_key, body, created_at FROM orders ORDER BY id").fetchall()
    return [{"erp_ref": r[0], "idempotency_key": r[1], "order": json.loads(r[2]), "created_at": r[3]} for r in rows]


@app.post("/orders")
async def create_order(request: Request, idempotency_key: str | None = Header(default=None)):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    if random.random() < config["fail_rate"]:
        raise HTTPException(503, "temporarily unavailable")
    body = await request.json()
    body_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    with lock, db() as c:
        row = c.execute("SELECT body_hash, erp_ref FROM orders WHERE idem_key = ?", (idempotency_key,)).fetchone()
        if row:
            if row[0] != body_hash:
                raise HTTPException(409, "Idempotency-Key reused with a different order")
            return JSONResponse({"erp_ref": row[1], "replayed": True}, status_code=200)
        cur = c.execute("INSERT INTO orders (idem_key, body_hash, erp_ref, body, created_at) VALUES (?,?,?,?,?)",
                        (idempotency_key, body_hash, "", json.dumps(body), time.time()))
        ref = f"ERP-{cur.lastrowid:06d}"
        c.execute("UPDATE orders SET erp_ref = ? WHERE id = ?", (ref, cur.lastrowid))

    if random.random() < config["commit_then_hang_rate"]:
        await asyncio.sleep(HANG_SECONDS)  # order is saved, but the caller times out first (non-blocking)
    return JSONResponse({"erp_ref": ref, "replayed": False}, status_code=201)
