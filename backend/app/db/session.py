"""Database engine and per-request sessions."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

# pool_pre_ping: test a pooled connection before using it, so a restarted Postgres
# doesn't hand us a dead connection.
engine = create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    """FastAPI dependency: one session per request, always closed afterwards."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
