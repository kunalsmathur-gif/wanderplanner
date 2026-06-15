from __future__ import annotations

from fastapi import APIRouter, HTTPException
from models.chat import ChatRequest, ChatResponse
from chains.chat_chain import chat

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    try:
        reply = await chat(request)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
