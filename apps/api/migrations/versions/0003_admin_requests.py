"""create admin_requests table

Revision ID: 0003_admin_requests
Revises: 0002_password_reset
Create Date: 2026-07-08

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_admin_requests"
down_revision = "0002_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_admin_requests_user_id", "admin_requests", ["user_id"])
    op.create_index("ix_admin_requests_status", "admin_requests", ["status"])


def downgrade() -> None:
    op.drop_table("admin_requests")
