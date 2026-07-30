from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.analytics import log_event
from core.auth_dependency import get_optional_user
from core.email import send_agent_lead_confirmation_email
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
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    await send_agent_lead_confirmation_email(
        to_email=body.email,
        destination=body.destination,
        trip_config_summary=body.trip_config_summary,
    )
    await log_event(
        db,
        "agent_lead_created",
        user_id=user.id if user else None,
        metadata={"lead_id": str(lead.id), "destination": body.destination},
    )

    return AgentLeadCreateResponse(id=str(lead.id))
