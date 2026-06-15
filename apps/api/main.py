from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.scheduler import start_scheduler, stop_scheduler
from routers import itinerary, comparison, best_time, search, geocode, feasibility, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_scheduler()
    yield
    await stop_scheduler()


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


@app.get("/health")
async def health():
    return {"status": "ready", "version": "1.0.0"}
