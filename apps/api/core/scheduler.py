from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

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


async def _refresh_visa_info():
    """Refresh the `visa_info` entry-rules corpus (issue #37).

    Iterates countries, not destinations: visa rules are country-level (see
    scrapers/visa_info.py for the measurement behind that). Failures are
    per-country and non-fatal — one unreachable article must not cost the
    other sixty, the same contract as `_refresh_osm_pois`.
    """
    from scrapers.visa_info import VISA_SEED_COUNTRIES, ingest_visa_info

    total = failures = 0
    for country in VISA_SEED_COUNTRIES:
        try:
            total += await ingest_visa_info(country)
        except Exception as e:
            failures += 1
            logger.warning("visa_info refresh failed for %r: %s", country, e)
        # Wikimedia asks for unhurried serial access; this is a long, entirely
        # background loop so there is no reason to hurry it.
        await asyncio.sleep(1.0)
    logger.info(
        "visa_info refresh complete: %d chunks across %d countries (%d failed)",
        total, len(VISA_SEED_COUNTRIES), failures,
    )


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


async def _retry_youtube_narration_transcripts():
    """Slow drip-retry for `youtube_narration` destinations that landed
    description-only because a transcript-fetch burst hit a YouTube IP block
    mid-run (issue #46 follow-up — a 172-destination backfill got blocked
    after ~70 destinations, and even a small retry burst re-triggered the
    block within 2-3 destinations on 2026-07-30). Retrying is free, but only
    safe in a small trickle: a handful of destinations every few hours,
    rather than a full-corpus burst, so this never looks like the same abuse
    pattern to YouTube. Naturally converges to nothing left to retry as
    destinations pick up real transcripts and drop out of the missing set.
    """
    from scrapers.youtube_narration import (
        destinations_missing_transcripts,
        ingest_youtube_narration,
    )

    try:
        missing = await destinations_missing_transcripts()
    except Exception as e:
        logger.warning("youtube_narration transcript retry: could not list missing destinations: %s", e)
        return

    batch = missing[: settings.youtube_narration_transcript_retry_batch_size]
    if not batch:
        logger.info("youtube_narration transcript retry: nothing missing — all destinations have transcripts")
        return

    for destination in batch:
        try:
            count = await ingest_youtube_narration(destination)
        except Exception as e:
            logger.warning("youtube_narration transcript retry failed for %s: %s", destination, e)
            continue
        logger.info("youtube_narration transcript retry for %s: %d chunks stored", destination, count)
        await asyncio.sleep(settings.osm_ingest_delay_seconds)


async def _check_qdrant_storage_headroom():
    """Log a warning/error once estimated Qdrant RAM usage crosses
    `qdrant_storage_warn_threshold`/`qdrant_storage_critical_threshold` of the
    Cloud free tier's 1GiB cap (docs/scaling-tech-challenges.md — "nothing
    monitors headroom... the first symptom would be write failures during an
    ingestion run"). This doesn't prevent that failure, but turns it from a
    silent surprise into a logged, actionable warning well before the cap is
    hit — the same estimate is also surfaced on `/admin/metrics/summary` for
    a non-log view. Skipped entirely for the local `:memory:` fallback, which
    has no tier limit to run out of.
    """
    if settings.qdrant_url == ":memory:":
        return

    from core.qdrant import estimate_storage_usage, get_qdrant

    try:
        usage = estimate_storage_usage(get_qdrant())
    except Exception as e:
        logger.warning("Qdrant storage headroom check failed: %s", e)
        return

    fraction = usage["used_fraction"] or 0.0
    total_mb = usage["total_estimated_bytes"] / (1024 * 1024)
    limit_mb = usage["limit_bytes"] / (1024 * 1024)

    if fraction >= settings.qdrant_storage_critical_threshold:
        logger.error(
            "Qdrant Cloud storage estimate at %.1f%% of the free-tier cap "
            "(~%.0fMB / %.0fMB) — write failures may start soon; plan a paid "
            "tier upgrade or corpus pruning. Per-collection: %s",
            fraction * 100, total_mb, limit_mb, usage["collections"],
        )
    elif fraction >= settings.qdrant_storage_warn_threshold:
        logger.warning(
            "Qdrant Cloud storage estimate at %.1f%% of the free-tier cap "
            "(~%.0fMB / %.0fMB) — approaching the 1GiB limit.",
            fraction * 100, total_mb, limit_mb,
        )
    else:
        logger.info(
            "Qdrant Cloud storage estimate at %.1f%% of the free-tier cap "
            "(~%.0fMB / %.0fMB).",
            fraction * 100, total_mb, limit_mb,
        )


async def _check_redis_memory_headroom():
    """Monitor Redis memory usage and clear the cache outright once it passes
    `redis_memory_limit_bytes` — unlike the Qdrant check (which only warns),
    this one *acts*, because everything stored here (share links, travel
    tips) is disposable cache/derived data, not source-of-truth data: a
    flush is a cheap, safe way to recover from unexpectedly large growth
    (e.g. a bug causing unbounded distinct cache keys), and share links
    already carry a documented TTL/expiry expectation rather than a
    permanence guarantee. Logs a WARNING at `redis_memory_warn_threshold`
    before that point so a real trend is visible before it triggers a flush.
    Skipped entirely for the local in-process dict fallback (no REDIS_URL),
    which has no shared/persistent state worth protecting this way.
    """
    if not settings.redis_url:
        return

    from core.redis_client import get_cache

    cache = get_cache()
    try:
        used_bytes = await cache.memory_usage_bytes()
        key_count = await cache.key_count()
    except Exception as e:
        logger.warning("Redis memory headroom check failed: %s", e)
        return

    if used_bytes is None:
        return

    limit_bytes = settings.redis_memory_limit_bytes
    fraction = used_bytes / limit_bytes if limit_bytes else 0.0
    used_mb = used_bytes / (1024 * 1024)
    limit_mb = limit_bytes / (1024 * 1024)

    if fraction >= 1.0:
        logger.error(
            "Redis memory usage (~%.1fMB / %.0fMB, %d keys) exceeded the "
            "configured cap — flushing the cache (share links + travel tips; "
            "both are disposable/derived, not source-of-truth data).",
            used_mb, limit_mb, key_count or 0,
        )
        await cache.flush()
    elif fraction >= settings.redis_memory_warn_threshold:
        logger.warning(
            "Redis memory usage at %.1f%% of its configured cap (~%.1fMB / "
            "%.0fMB, %d keys) — a flush will trigger automatically past 100%%.",
            fraction * 100, used_mb, limit_mb, key_count or 0,
        )
    else:
        logger.info(
            "Redis memory usage at %.1f%% of its configured cap (~%.1fMB / "
            "%.0fMB, %d keys).",
            fraction * 100, used_mb, limit_mb, key_count or 0,
        )


async def _check_agent_lead_sla(*, now: datetime | None = None):
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from core.email import send_agent_lead_escalation_email, send_agent_lead_reassurance_email
    from db import AsyncSessionLocal
    from db_models import AgentLead, User

    now = now or datetime.now(UTC)
    escalation_cutoff = now - timedelta(hours=24)
    reassurance_cutoff = now - timedelta(hours=48)

    async with AsyncSessionLocal() as db:
        leads_to_escalate = (
            await db.execute(
                select(AgentLead).where(
                    AgentLead.responded_at.is_(None),
                    AgentLead.escalated_at.is_(None),
                    AgentLead.created_at <= escalation_cutoff,
                )
            )
        ).scalars().all()
        leads_to_reassure = (
            await db.execute(
                select(AgentLead).where(
                    AgentLead.responded_at.is_(None),
                    AgentLead.reassurance_sent_at.is_(None),
                    AgentLead.created_at <= reassurance_cutoff,
                )
            )
        ).scalars().all()

        admin_emails: list[str] = []
        if leads_to_escalate:
            admin_emails = [
                row[0]
                for row in (
                    await db.execute(
                        select(User.email).where(User.is_admin.is_(True), User.email.is_not(None))
                    )
                ).all()
            ]

        for lead in leads_to_escalate:
            await send_agent_lead_escalation_email(
                admin_emails=admin_emails,
                lead_id=str(lead.id),
                destination=lead.destination,
                lead_email=lead.email,
            )
            # Mark the attempt regardless of provider outcome: the contract is
            # "send at most once per threshold", and repeated hourly retries
            # would be worse than one logged failure.
            lead.escalated_at = now

        for lead in leads_to_reassure:
            await send_agent_lead_reassurance_email(
                to_email=lead.email,
                destination=lead.destination,
            )
            lead.reassurance_sent_at = now

        if leads_to_escalate or leads_to_reassure:
            await db.commit()


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
    _scheduler.add_job(
        _refresh_visa_info,
        trigger=IntervalTrigger(days=settings.visa_info_refresh_days),
        id="visa_info_refresh",
        replace_existing=True,
    )
    _scheduler.add_job(
        _retry_youtube_narration_transcripts,
        trigger=IntervalTrigger(hours=settings.youtube_narration_transcript_retry_hours),
        id="youtube_narration_transcript_retry",
        replace_existing=True,
    )
    _scheduler.add_job(
        _check_qdrant_storage_headroom,
        trigger=IntervalTrigger(hours=settings.qdrant_storage_check_hours),
        id="qdrant_storage_headroom_check",
        replace_existing=True,
    )
    _scheduler.add_job(
        _check_redis_memory_headroom,
        trigger=IntervalTrigger(hours=settings.redis_memory_check_hours),
        id="redis_memory_headroom_check",
        replace_existing=True,
    )
    _scheduler.add_job(
        _check_agent_lead_sla,
        trigger=IntervalTrigger(hours=settings.agent_lead_sla_check_hours),
        id="agent_lead_sla_check",
        replace_existing=True,
    )
    _scheduler.start()


async def stop_scheduler():
    _scheduler.shutdown(wait=False)
