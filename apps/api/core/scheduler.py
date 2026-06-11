from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.config import settings

_scheduler = AsyncIOScheduler()


async def _refresh_reddit():
    from scrapers.reddit import ingest_reddit
    await ingest_reddit()


async def start_scheduler():
    _scheduler.add_job(
        _refresh_reddit,
        trigger=IntervalTrigger(hours=settings.reddit_refresh_hours),
        id="reddit_refresh",
        replace_existing=True,
    )
    _scheduler.start()


async def stop_scheduler():
    _scheduler.shutdown(wait=False)
