"""create generated_itinerary_signals table

Revision ID: 0011_generated_itinerary_signals
Revises: 0010_user_last_itinerary
Create Date: 2026-08-19

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_generated_itinerary_signals"
down_revision = "0010_user_last_itinerary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_itinerary_signals",
        sa.Column("generation_id", sa.String(length=40), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("regenerated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_duration_s", sa.Integer(), nullable=True),
        sa.Column("was_shared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("post_gen_chat_turns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_generated_itinerary_signals_user_id", "generated_itinerary_signals", ["user_id"])
    # The scheduler job's "ready to score" query filters on scored_at IS NULL.
    op.create_index("ix_generated_itinerary_signals_scored_at", "generated_itinerary_signals", ["scored_at"])


def downgrade() -> None:
    op.drop_index("ix_generated_itinerary_signals_scored_at", table_name="generated_itinerary_signals")
    op.drop_index("ix_generated_itinerary_signals_user_id", table_name="generated_itinerary_signals")
    op.drop_table("generated_itinerary_signals")
