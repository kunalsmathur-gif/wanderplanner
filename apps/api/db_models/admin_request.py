from __future__ import annotations
from typing import Optional
from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class AdminRequest(Base):
    """A user's request to be granted admin access. Nobody becomes an admin
    automatically — signup never accepts an `is_admin` field (see
    routers/auth.py + models/auth.SignupRequest), and the only way `is_admin`
    is ever flipped to True post-signup is here: an existing admin explicitly
    approving a pending request via POST /admin/requests/{id}/approve.

    First-ever admin bootstrap is intentionally out of band (direct DB
    write/seed script) since there is no admin yet to approve anyone.
    """

    __tablename__ = "admin_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # "pending" | "approved" | "rejected"
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    # Optional free-text reason the requester gave for wanting admin access.
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
