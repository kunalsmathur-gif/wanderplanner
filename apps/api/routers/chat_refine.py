
from fastapi import APIRouter, HTTPException, Request
from chains.chat_refine_chain import ChatRefineRequest, ChatRefineResponse, chat_refine
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter

router = APIRouter()


@router.post("/chat-refine", response_model=ChatRefineResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def chat_refine_endpoint(request: Request, body: ChatRefineRequest) -> ChatRefineResponse:
    try:
        return await chat_refine(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="chat-refine"))
