from __future__ import annotations
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.config import settings

logger = logging.getLogger(__name__)
_scheduler = AsyncIOScheduler()


async def _refresh_reddit():
    from scrapers.reddit import ingest_reddit
    await ingest_reddit()


async def _refresh_itinerary_corpus():
    """Monthly-cadence ingestion of the free-tier itinerary corpus (docs
    §9): scrape raw content, extract structured itineraries, embed, and
    upsert into the `itinerary_corpus` Qdrant collection. Individual source
    failures are already tolerated inside `collect_itinerary_corpus_raw()`;
    this wrapper just guards the whole job so a bad run doesn't crash the
    scheduler thread."""
    from chains.itinerary_corpus_extraction_chain import ingest_itinerary_corpus
    try:
        count = await ingest_itinerary_corpus()
        logger.info("Itinerary corpus ingestion complete: %d documents", count)
    except Exception as e:
        logger.warning("Itinerary corpus ingestion failed: %s", e)


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
            logger.warning("OSM POI ingestion failed for %s: %s", destination, e)
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
    _scheduler.add_job(
        _refresh_itinerary_corpus,
        trigger=IntervalTrigger(days=settings.itinerary_corpus_refresh_days),
        id="itinerary_corpus_refresh",
        replace_existing=True,
    )
    _scheduler.start()


async def stop_scheduler():
    _scheduler.shutdown(wait=False)
