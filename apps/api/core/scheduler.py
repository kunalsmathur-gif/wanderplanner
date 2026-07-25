from __future__ import annotations

import asyncio
import logging
from datetime import UTC

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
    """Refresh OSM POI + Wikivoyage data for destinations actually requested
    by users (docs/scaling-tech-challenges.md §8), instead of looping a fixed
    global destination list. `services/destination_ingestion.py` writes a
    `destination_ingestion_state` row on first request; this job re-ingests
    only rows whose data has gone stale (past `osm_refresh_days`), keeping
    corpus size and Overpass/Wikivoyage traffic proportional to real demand.

    Sequential with a small delay between destinations — Overpass/Wikivoyage
    are free shared public services, so this avoids hammering them with a
    burst of concurrent requests.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState
    from scrapers.osm import ingest_osm_pois
    from scrapers.wikivoyage import ingest_wikivoyage

    stale_before = datetime.now(UTC) - timedelta(days=settings.osm_refresh_days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DestinationIngestionState.destination).where(
                DestinationIngestionState.osm_last_ingested_at < stale_before
            )
        )
        stale_destinations = [row[0] for row in result.all()]

    for destination in stale_destinations:
        now = datetime.now(UTC)
        try:
            await ingest_osm_pois(destination)
            await ingest_wikivoyage(destination)
        except Exception as e:
            logger.warning("Refresh ingestion failed for %s: %s", destination, e)
        else:
            async with AsyncSessionLocal() as db:
                row = await db.get(DestinationIngestionState, destination)
                if row is not None:
                    row.osm_last_ingested_at = now
                    row.wiki_last_ingested_at = now
                    await db.commit()
        await asyncio.sleep(settings.osm_ingest_delay_seconds)


async def _refresh_youtube_comments():
    """Refresh the `youtube_comments` sentiment corpus (services/gems.py) for
    demand-ranked destinations whose YouTube data is stale or was never
    ingested.

    Kept as its own job rather than folded into `_refresh_osm_pois` because it
    has fundamentally different economics: OSM/Wikivoyage are free unmetered
    public APIs refreshed weekly, while `search.list` costs 100 of the free
    tier's 10,000 daily units. So this runs on a longer cadence
    (`youtube_refresh_days`), is capped per run (`youtube_refresh_batch_size`),
    and sits behind scrapers/youtube_comments.py's own rolling-24h budget.

    Ordered by `request_count` DESC so a limited quota is spent on the
    destinations users actually ask for most, and NULL-first so destinations
    that never got YouTube data (ingested before a key existed, or during an
    exhausted-budget window) are picked up ahead of merely-stale ones.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import or_, select

    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState
    from scrapers.youtube_comments import ingest_youtube_comments

    if not settings.youtube_api_key:
        logger.info("YOUTUBE_API_KEY not set — skipping YouTube comment refresh")
        return

    stale_before = datetime.now(UTC) - timedelta(days=settings.youtube_refresh_days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DestinationIngestionState.destination)
            .where(
                or_(
                    DestinationIngestionState.youtube_last_ingested_at.is_(None),
                    DestinationIngestionState.youtube_last_ingested_at < stale_before,
                )
            )
            .order_by(
                DestinationIngestionState.youtube_last_ingested_at.is_(None).desc(),
                DestinationIngestionState.request_count.desc(),
            )
            .limit(settings.youtube_refresh_batch_size)
        )
        destinations = [row[0] for row in result.all()]

    for destination in destinations:
        now = datetime.now(UTC)
        try:
            count = await ingest_youtube_comments(destination)
        except Exception as e:
            logger.warning("YouTube comment refresh failed for %s: %s", destination, e)
            continue
        if not count:
            # Over budget, no videos found, or comments disabled everywhere.
            # Deliberately leave the timestamp untouched so the next run
            # retries this destination instead of marking it fresh-but-empty.
            logger.info("YouTube comment refresh for %s returned 0 comments — will retry next run", destination)
            continue
        async with AsyncSessionLocal() as db:
            row = await db.get(DestinationIngestionState, destination)
            if row is not None:
                row.youtube_last_ingested_at = now
                await db.commit()
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
    _scheduler.add_job(
        _refresh_youtube_comments,
        trigger=IntervalTrigger(days=settings.youtube_refresh_days),
        id="youtube_comments_refresh",
        replace_existing=True,
    )
    _scheduler.start()


async def stop_scheduler():
    _scheduler.shutdown(wait=False)
