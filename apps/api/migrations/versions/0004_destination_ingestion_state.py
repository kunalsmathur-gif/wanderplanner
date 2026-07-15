"""create destination_ingestion_state table

Revision ID: 0004_destination_ingestion_state
Revises: 0003_admin_requests
Create Date: 2026-07-15

"""

from alembic import op
import sqlalchemy as sa

revision = "0004_destination_ingestion_state"
down_revision = "0003_admin_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "destination_ingestion_state",
        sa.Column("destination", sa.String(length=120), primary_key=True),
        sa.Column("osm_last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wiki_last_ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("destination_ingestion_state")
