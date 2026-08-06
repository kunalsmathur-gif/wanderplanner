"""add source to agent_leads

Revision ID: 0009_agent_lead_source
Revises: 0008_agent_lead_custom_notes
Create Date: 2026-08-06

"""

import sqlalchemy as sa
from alembic import op

revision = "0009_agent_lead_source"
down_revision = "0008_agent_lead_custom_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Distinguishes leads created after the feasibility gate blocked
    # generation ("infeasible_budget") from the pre-existing happy-path
    # "Get this itinerary booked" CTA on an already-generated itinerary
    # ("itinerary"), so the admin console can be filtered/read separately.
    op.add_column(
        "agent_leads",
        sa.Column("source", sa.String(length=40), nullable=False, server_default="itinerary"),
    )


def downgrade() -> None:
    op.drop_column("agent_leads", "source")
