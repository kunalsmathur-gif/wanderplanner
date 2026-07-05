
from fastapi import APIRouter, HTTPException, Request
from chains.wizard_chat_chain import WizardChatRequest, WizardChatResponse, wizard_chat
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter

router = APIRouter()


@router.post("/wizard-chat", response_model=WizardChatResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def wizard_chat_endpoint(request: Request, body: WizardChatRequest) -> WizardChatResponse:
    try:
        return await wizard_chat(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="wizard-chat"))
