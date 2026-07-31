from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_recipients import get_quotation_recipient_emails
from core.analytics import log_event
from core.auth_dependency import get_optional_user
from core.email import send_agent_lead_confirmation_email, send_agent_lead_request_email
from db import get_db
from db_models import AgentLead, User
from models.agent_leads import AgentLeadCreateRequest, AgentLeadCreateResponse

router = APIRouter()


@router.post("/agent-leads", response_model=AgentLeadCreateResponse)
async def create_agent_lead(
    body: AgentLeadCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> AgentLeadCreateResponse:
    lead = AgentLead(
        user_id=user.id if user else None,
        email=body.email,
        destination=body.destination,
        trip_config_summary=body.trip_config_summary,
        custom_notes=body.custom_notes,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    await send_agent_lead_confirmation_email(
        to_email=body.email,
        destination=body.destination,
        trip_config_summary=body.trip_config_summary,
    )

    # The actual quote-request notification — fires immediately, not just on
    # the 24h-unanswered escalation path. Recipients: every admin user in
    # sole-builder mode, or the configured agent roster once one exists
    # (see core/agent_recipients.py).
    pdf_bytes: bytes | None = None
    if body.pdf_base64:
        try:
            pdf_bytes = base64.b64decode(body.pdf_base64, validate=True)
        except (binascii.Error, ValueError):
            pdf_bytes = None

    recipient_emails = await get_quotation_recipient_emails(db)
    await send_agent_lead_request_email(
        to_emails=recipient_emails,
        lead_id=str(lead.id),
        lead_email=body.email,
        destination=body.destination,
        trip_config_summary=body.trip_config_summary,
        custom_notes=body.custom_notes,
        itinerary_html=body.itinerary_html,
        pdf_attachment=pdf_bytes,
        pdf_filename=f"{body.destination.replace(' ', '_')}_itinerary.pdf",
    )

    await log_event(
        db,
        "agent_lead_created",
        user_id=user.id if user else None,
        metadata={"lead_id": str(lead.id), "destination": body.destination},
    )

    return AgentLeadCreateResponse(id=str(lead.id))
