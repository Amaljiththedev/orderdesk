"""Create extensions and all tables. Safe to run again (existing tables are left alone).

    docker compose -f infra/docker-compose.yml exec api python -m app.db.init_db
"""
from sqlalchemy import text

from app.db.models import Base
from app.db.session import engine


def main() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))   # pgvector
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))  # fuzzy text search
    Base.metadata.create_all(engine)
    print("tables:", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()
