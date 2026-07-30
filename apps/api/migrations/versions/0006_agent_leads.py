"""create agent_leads table

Revision ID: 0006_agent_leads
Revises: 0005_youtube_ingestion_state
Create Date: 2026-07-30

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_agent_leads"
down_revision = "0005_youtube_ingestion_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column(
            "trip_config_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reassurance_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_booked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_leads_user_id", "agent_leads", ["user_id"])
    op.create_index("ix_agent_leads_email", "agent_leads", ["email"])
    op.create_index("ix_agent_leads_destination", "agent_leads", ["destination"])


def downgrade() -> None:
    op.drop_index("ix_agent_leads_destination", table_name="agent_leads")
    op.drop_index("ix_agent_leads_email", table_name="agent_leads")
    op.drop_index("ix_agent_leads_user_id", table_name="agent_leads")
    op.drop_table("agent_leads")
