"""add youtube_last_ingested_at to destination_ingestion_state

Tracks YouTube-comment ingestion freshness separately from OSM/Wikivoyage:
it spends a metered API quota, so it runs on its own longer cadence and is
legitimately NULL for destinations ingested before a key was configured (or
on a day the rolling search budget was already exhausted).

Revision ID: 0005_youtube_ingestion_state
Revises: 0004_destination_ingestion_state
Create Date: 2026-07-25

"""

from alembic import op
import sqlalchemy as sa

revision = "0005_youtube_ingestion_state"
down_revision = "0004_destination_ingestion_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "destination_ingestion_state",
        sa.Column("youtube_last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("destination_ingestion_state", "youtube_last_ingested_at")
