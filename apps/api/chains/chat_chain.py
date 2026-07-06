"""Chat chain with travel-only guardrails using Google Gemini."""
from __future__ import annotations

import asyncio
import json

from core.config import settings
from core.prompt_guard import neutralize
from models.chat import ChatMessage, ChatRequest

GUARDRAIL_SYSTEM_PROMPT = """\
You are WanderPlanner Assistant, an expert travel advisor chatbot.

YOUR ROLE:
- Help users plan trips: destinations, itineraries, budgets, accommodation, food, safety, visas, packing
- Answer questions about travel from India, specifically international travel
- Provide factual, helpful, up-to-date travel information
- Suggest budget-appropriate alternatives when asked
- Clarify itinerary options and help refine trip plans

STRICT GUARDRAILS:
1. ONLY answer travel-related questions. If asked about anything else (politics, coding, health, relationships, etc.), politely decline.
2. Never make bookings or collect personal/payment information.
3. Always clarify when information may be approximate or subject to change (visa rules, prices).
4. Do not share opinions on political matters even if framed as a travel question.
5. For safety questions, always recommend checking official government advisories.
6. Keep responses concise and friendly. Use bullet points for lists.

OUT-OF-SCOPE RESPONSE:
If a user asks something unrelated to travel, respond with:
"I'm WanderPlanner's travel assistant — I can only help with travel-related questions like destinations, itineraries, visas, budgets, or packing tips. What travel question can I help you with? 🌍"

CONTEXT:
- All users are traveling from India
- Budget is always in INR
- Trips are international only
{trip_context_section}
"""


def _build_prompt(request: ChatRequest) -> str:
    if request.trip_context:
        ctx = json.dumps(request.trip_context, indent=2)
        trip_section = f"\nCURRENT TRIP BEING PLANNED:\n{neutralize(ctx, context='trip context')}"
    else:
        trip_section = ""

    return GUARDRAIL_SYSTEM_PROMPT.format(trip_context_section=trip_section)


async def chat(request: ChatRequest) -> str:
    """Send chat message to Gemini with guardrail system prompt. Returns reply text."""

    if settings.llm_provider == "mock":
        last_msg = request.messages[-1].content if request.messages else ""
        return _mock_reply(last_msg)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed.")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    system_prompt = _build_prompt(request)

    # Build Gemini contents from message history (last 10 turns to stay within context limits)
    history = request.messages[-10:]
    contents = []
    for msg in history:
        role = "user" if msg.role == "user" else "model"
        contents.append(genai_types.Content(role=role, parts=[genai_types.Part(text=neutralize(msg.content, context="chat message"))]))

    def _call_sync() -> str:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=1024,
            ),
        )
        return response.text

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_sync)


def _mock_reply(user_msg: str) -> str:
    msg = user_msg.lower()
    if any(kw in msg for kw in ["hello", "hi", "hey"]):
        return "Hi! I'm WanderPlanner Assistant 🌍 How can I help you plan your next international trip?"
    if any(kw in msg for kw in ["visa", "passport"]):
        return "For Indian passport holders, visa requirements vary by destination. Popular visa-free countries include Thailand, Indonesia (Bali), Sri Lanka, Nepal, and many more. Where are you planning to go?"
    if any(kw in msg for kw in ["budget", "cost", "cheap", "affordable"]):
        return "Great question! Southeast Asia (Thailand, Vietnam, Bali) offers excellent value. Budget: ₹80,000–₹1,20,000 for 7 nights including flights. Would you like me to help narrow down options?"
    if any(kw in msg for kw in ["tokyo", "japan"]):
        return "Tokyo is fantastic! 🗼 Best time: March-April (cherry blossoms) or October-November. Budget for 7 days: ₹1.5–2.5L per person including flights. No visa required for stays up to 90 days (as of 2024)."
    return "I'm WanderPlanner Assistant — I can only help with travel-related questions like destinations, itineraries, visas, budgets, or packing tips. What travel question can I help you with? 🌍"
