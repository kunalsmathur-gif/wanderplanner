from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.scheduler import start_scheduler, stop_scheduler
from routers import itinerary, comparison, best_time, search, geocode, feasibility, chat, recommend_cities, chat_refine, reddit_highlights, travel_tips


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
    title="WanderPlan API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
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


@app.get("/health")
async def health():
    return {"status": "ready", "version": "1.0.0"}
