"""add custom_notes to agent_leads

Revision ID: 0008_agent_lead_custom_notes
Revises: 0007_itinerary_feedback
Create Date: 2026-07-31

"""

import sqlalchemy as sa
from alembic import op

revision = "0008_agent_lead_custom_notes"
down_revision = "0007_itinerary_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_leads", sa.Column("custom_notes", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_leads", "custom_notes")
