"""Bring the database schema up to date with Alembic migrations.

    docker compose -f infra/docker-compose.yml exec api python -m app.db.init_db

Migrations are the only way the schema changes now (no more create_all), so every change is
versioned, reviewable and repeatable on another machine.
"""
from alembic import command
from alembic.config import Config


def main() -> None:
    command.upgrade(Config("app/alembic.ini"), "head")
    print("schema is at the latest migration")


if __name__ == "__main__":
    main()
