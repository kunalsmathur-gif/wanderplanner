"""create poi_provider_usage table

Revision ID: 0013_poi_provider_usage
Revises: 0012_job_run_state
Create Date: 2026-08-26

"""

import sqlalchemy as sa
from alembic import op

revision = "0013_poi_provider_usage"
down_revision = "0012_job_run_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "poi_provider_usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("provider_used", sa.String(length=20), nullable=False),
        sa.Column("google_places_attempted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("google_places_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("google_places_poi_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("google_places_estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("google_places_error", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("osm_poi_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_poi_provider_usage_destination", "poi_provider_usage", ["destination"])


def downgrade() -> None:
    op.drop_index("ix_poi_provider_usage_destination", table_name="poi_provider_usage")
    op.drop_table("poi_provider_usage")
