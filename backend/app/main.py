from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.documents import router as documents_router
from app.db.models import Product
from app.db.session import get_db

app = FastAPI(title="OrderDesk", version="0.1.0")
app.include_router(documents_router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """OK only if the database answers."""
    try:
        db.execute(text("SELECT 1"))
    except OperationalError:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok", "database": "ok"}


@app.get("/products/search")
def search_products(q: str = Query(min_length=2), limit: int = Query(5, le=20),
                    db: Session = Depends(get_db)):
    """Fuzzy search on product names. A first look at matching; the real matcher comes in Phase 3."""
    score = func.similarity(Product.name, q)
    rows = db.execute(
        select(Product.code, Product.name, score.label("score"))
        .order_by(Product.name.op("<->")(q))   # trigram distance, uses the GIN index
        .limit(limit)
    ).all()
    return [{"code": r.code, "name": r.name, "score": round(r.score, 3)} for r in rows]
