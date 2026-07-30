"""create itinerary_feedback table

Revision ID: 0007_itinerary_feedback
Revises: 0006_agent_leads
Create Date: 2026-07-30

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_itinerary_feedback"
down_revision = "0006_agent_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "itinerary_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "trip_config_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=True),
        sa.Column("place_ref", sa.String(length=200), nullable=True),
        sa.Column("sentiment", sa.String(length=30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_itinerary_feedback_user_id", "itinerary_feedback", ["user_id"])
    op.create_index("ix_itinerary_feedback_sentiment", "itinerary_feedback", ["sentiment"])


def downgrade() -> None:
    op.drop_index("ix_itinerary_feedback_sentiment", table_name="itinerary_feedback")
    op.drop_index("ix_itinerary_feedback_user_id", table_name="itinerary_feedback")
    op.drop_table("itinerary_feedback")
