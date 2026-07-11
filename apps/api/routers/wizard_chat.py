
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chains.wizard_chat_chain import WizardChatRequest, WizardChatResponse, wizard_chat
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter
from core.llm_usage import reset_usage
from core.analytics import flush_llm_usage
from core.auth_dependency import get_optional_user
from db import get_db
from db_models import User

router = APIRouter()


@router.post("/wizard-chat", response_model=WizardChatResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def wizard_chat_endpoint(
    request: Request,
    body: WizardChatRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> WizardChatResponse:
    reset_usage()
    try:
        return await wizard_chat(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="wizard-chat"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)
