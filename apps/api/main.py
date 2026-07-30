import sys

if sys.version_info < (3, 11):  # noqa: UP036 — deliberate runtime guard, not dead code
    raise RuntimeError(
        f"WanderPlanner's API requires Python 3.11+ (uses `datetime.UTC`, added in "
        f"3.11), but this interpreter is {sys.version_info.major}.{sys.version_info.minor}. "
        "If you created .venv with a bare `python3 -m venv .venv`, it likely picked up "
        "an older system Python — recreate it with `python3.11 -m venv .venv` (or newer)."
    )

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.config import settings
from core.logging_config import configure_logging
from core.rate_limit import limiter
from core.scheduler import start_scheduler, stop_scheduler
from routers import (
    admin,
    agent_leads,
    analytics,
    auth,
    best_time,
    chat,
    chat_refine,
    comparison,
    extract_trip,
    feasibility,
    geocode,
    itinerary,
    itinerary_feedback,
    recommend_cities,
    reddit_highlights,
    search,
    share,
    travel_tips,
    wizard_chat,
)

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_scheduler()
    # Kick off Reddit ingestion immediately on startup (non-blocking)
    asyncio.create_task(_seed_reddit())
    yield
    await stop_scheduler()


async def _seed_reddit():
    try:
        from scrapers.reddit import ingest_reddit
        await ingest_reddit()
    except Exception:
        pass  # Fail silently — Reddit is enhancement only


app = FastAPI(
    title="WanderPlanner API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

# FastAPI's default 422 body echoes the rejected value back under "input", so
# rejecting an oversized payload produced an equally oversized response — the
# input caps in core/validation.py would otherwise be paid for twice. The
# offending value is still shown, just bounded, because a truncated echo is
# what makes a validation error debuggable.
_MAX_ECHOED_INPUT_CHARS = 200


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        bounded = dict(error)
        value = bounded.get("input")
        if isinstance(value, str) and len(value) > _MAX_ECHOED_INPUT_CHARS:
            bounded["input"] = value[:_MAX_ECHOED_INPUT_CHARS] + "… [truncated]"
        elif isinstance(value, list | dict) and len(value) > 20:
            bounded["input"] = f"<{type(value).__name__} of {len(value)} entries>"
        errors.append(bounded)
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    # Credentialed requests are now required for auth (httpOnly session
    # cookies). `allowed_origins` is validated at startup to reject "*"
    # (core/config.py), so this is safe — see Security Vulnerabilities #7.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(itinerary.router, prefix="/api")
app.include_router(comparison.router, prefix="/api")
app.include_router(best_time.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(geocode.router, prefix="/api")
app.include_router(feasibility.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(recommend_cities.router, prefix="/api")
app.include_router(chat_refine.router, prefix="/api")
app.include_router(reddit_highlights.router, prefix="/api")
app.include_router(travel_tips.router, prefix="/api")
app.include_router(extract_trip.router, prefix="/api")
app.include_router(share.router, prefix="/api")
app.include_router(wizard_chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(agent_leads.router, prefix="/api")
app.include_router(itinerary_feedback.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ready", "version": "1.0.0"}
