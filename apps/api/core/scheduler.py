from __future__ import annotations
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.config import settings

_scheduler = AsyncIOScheduler()


async def _refresh_reddit():
    from scrapers.reddit import ingest_reddit
    await ingest_reddit()


async def _refresh_osm_pois():
    """Weekly OSM POI ingestion for all known travel destinations (docs §3I).

    Sequential with a small delay between destinations — Overpass is a free
    shared public service, so this avoids hammering it with a burst of
    concurrent requests.
    """
    from scrapers.osm import ingest_osm_pois
    from scrapers.reddit import KNOWN_DESTINATIONS

    for destination in KNOWN_DESTINATIONS:
        try:
            await ingest_osm_pois(destination)
        except Exception as e:
            print(f"⚠️ OSM POI ingestion failed for {destination}: {e}")
        await asyncio.sleep(settings.osm_ingest_delay_seconds)


async def start_scheduler():
    _scheduler.add_job(
        _refresh_reddit,
        trigger=IntervalTrigger(hours=settings.reddit_refresh_hours),
        id="reddit_refresh",
        replace_existing=True,
    )
    _scheduler.add_job(
        _refresh_osm_pois,
        trigger=IntervalTrigger(days=settings.osm_refresh_days),
        id="osm_poi_refresh",
        replace_existing=True,
    )
    _scheduler.start()


async def stop_scheduler():
    _scheduler.shutdown(wait=False)
