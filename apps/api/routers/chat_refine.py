
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chains.chat_refine_chain import ChatRefineRequest, ChatRefineResponse, chat_refine
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter
from core.llm_usage import reset_usage
from core.analytics import flush_llm_usage
from core.auth_dependency import get_optional_user
from db import get_db
from db_models import User

router = APIRouter()


@router.post("/chat-refine", response_model=ChatRefineResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def chat_refine_endpoint(
    request: Request,
    body: ChatRefineRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> ChatRefineResponse:
    reset_usage()
    try:
        return await chat_refine(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="chat-refine"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)
