from __future__ import annotations

from fastapi import APIRouter, HTTPException
from chains.wizard_chat_chain import WizardChatRequest, WizardChatResponse, wizard_chat

router = APIRouter()


@router.post("/wizard-chat", response_model=WizardChatResponse)
async def wizard_chat_endpoint(request: WizardChatRequest) -> WizardChatResponse:
    try:
        return await wizard_chat(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
