from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db

app = FastAPI(title="OrderDesk", version="0.1.0")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """OK only if the database answers."""
    try:
        db.execute(text("SELECT 1"))
    except OperationalError:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok", "database": "ok"}
