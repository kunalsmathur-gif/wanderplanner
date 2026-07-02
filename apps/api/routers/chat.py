from fastapi import APIRouter, HTTPException, Request
from models.chat import ChatRequest, ChatResponse
from chains.chat_chain import chat
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def chat_endpoint(request: Request, body: ChatRequest) -> ChatResponse:
    try:
        reply = await chat(body)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="chat"))
