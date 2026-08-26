"""create job_run_state table

Revision ID: 0012_job_run_state
Revises: 0011_generated_itinerary_signals
Create Date: 2026-08-26

"""

import sqlalchemy as sa
from alembic import op

revision = "0012_job_run_state"
down_revision = "0011_generated_itinerary_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_run_state",
        sa.Column("job_id", sa.String(length=80), primary_key=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("job_run_state")
