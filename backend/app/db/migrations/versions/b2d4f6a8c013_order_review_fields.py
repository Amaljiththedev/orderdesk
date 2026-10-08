"""order review fields: version (optimistic locking), reviewer, reject reason

Revision ID: b2d4f6a8c013
Revises: a1c3d5e7f901
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "b2d4f6a8c013"
down_revision = "a1c3d5e7f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("orders", sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("orders", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("reject_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ("reject_reason", "reviewed_at", "reviewed_by", "version"):
        op.drop_column("orders", col)
