from __future__ import annotations

from fastapi import APIRouter, HTTPException
from chains.chat_refine_chain import ChatRefineRequest, ChatRefineResponse, chat_refine

router = APIRouter()


@router.post("/chat-refine", response_model=ChatRefineResponse)
async def chat_refine_endpoint(request: ChatRefineRequest) -> ChatRefineResponse:
    try:
        return await chat_refine(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
