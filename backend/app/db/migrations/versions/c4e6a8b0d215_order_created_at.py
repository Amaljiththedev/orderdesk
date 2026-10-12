"""orders.created_at: when the order was routed, for received -> routed timing

Revision ID: c4e6a8b0d215
Revises: b2d4f6a8c013
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision = "c4e6a8b0d215"
down_revision = "b2d4f6a8c013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # existing rows get the migration time; timings for orders made before this are not meaningful
    op.add_column("orders", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                                      server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_column("orders", "created_at")
