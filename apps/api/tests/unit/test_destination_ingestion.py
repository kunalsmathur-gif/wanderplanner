"""
Unit tests for services/destination_ingestion.py — the demand-driven
ingestion gatekeeper (docs/scaling-tech-challenges.md §8). Postgres is an
in-memory sqlite engine here; Overpass/Wikivoyage/Nominatim are mocked —
fully offline.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import services.destination_ingestion as di
from db import Base
from db_models import DestinationIngestionState


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    with patch.object(di, "AsyncSessionLocal", maker):
        yield maker
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_locks():
    di._locks.clear()
    di._cold_start_times.clear()
    yield
    di._locks.clear()
    di._cold_start_times.clear()


class TestEnsureDestinationIngested:
    @pytest.mark.asyncio
    async def test_first_request_ingests_and_writes_row(self, session_maker):
        with patch("services.destination_ingestion.geocode_city", new=AsyncMock(return_value=object())), \
             patch("scrapers.osm.ingest_osm_pois", new=AsyncMock(return_value=12)) as mock_osm, \
             patch("scrapers.wikivoyage.ingest_wikivoyage", new=AsyncMock(return_value=None)) as mock_wiki:
            await di.ensure_destination_ingested("Lisbon")

        mock_osm.assert_awaited_once_with("Lisbon")
        mock_wiki.assert_awaited_once_with("Lisbon")

        async with session_maker() as db:
            row = await db.get(DestinationIngestionState, "Lisbon")
            assert row is not None
            assert row.request_count == 1
            assert row.osm_last_ingested_at is not None
            assert row.wiki_last_ingested_at is not None

    @pytest.mark.asyncio
    async def test_second_request_bumps_counter_without_reingesting(self, session_maker):
        async with session_maker() as db:
            from datetime import datetime, timezone
            db.add(DestinationIngestionState(
                destination="Lisbon",
                osm_last_ingested_at=datetime.now(timezone.utc),
                wiki_last_ingested_at=datetime.now(timezone.utc),
                request_count=1,
                last_requested_at=datetime.now(timezone.utc),
            ))
            await db.commit()

        with patch("scrapers.osm.ingest_osm_pois", new=AsyncMock()) as mock_osm, \
             patch("scrapers.wikivoyage.ingest_wikivoyage", new=AsyncMock()) as mock_wiki:
            await di.ensure_destination_ingested("Lisbon")

        mock_osm.assert_not_awaited()
        mock_wiki.assert_not_awaited()

        async with session_maker() as db:
            row = await db.get(DestinationIngestionState, "Lisbon")
            assert row.request_count == 2

    @pytest.mark.asyncio
    async def test_ungeocodable_destination_skips_ingestion(self, session_maker):
        with patch("services.destination_ingestion.geocode_city", new=AsyncMock(side_effect=ValueError("not found"))), \
             patch("scrapers.osm.ingest_osm_pois", new=AsyncMock()) as mock_osm:
            await di.ensure_destination_ingested("Asdkjaskd")

        mock_osm.assert_not_awaited()
        async with session_maker() as db:
            row = await db.get(DestinationIngestionState, "Asdkjaskd")
            assert row is None

    @pytest.mark.asyncio
    async def test_concurrent_first_requests_ingest_once(self, session_maker):
        with patch("services.destination_ingestion.geocode_city", new=AsyncMock(return_value=object())), \
             patch("scrapers.osm.ingest_osm_pois", new=AsyncMock(return_value=5)) as mock_osm, \
             patch("scrapers.wikivoyage.ingest_wikivoyage", new=AsyncMock(return_value=None)):
            await asyncio.gather(*[
                di.ensure_destination_ingested("Porto") for _ in range(5)
            ])

        assert mock_osm.await_count == 1  # ingested once despite 5 concurrent callers
        async with session_maker() as db:
            row = await db.get(DestinationIngestionState, "Porto")
            assert row.request_count == 5  # each real request still bumps the demand counter

    @pytest.mark.asyncio
    async def test_warns_when_both_sources_return_zero(self, session_maker, caplog):
        # Found 2026-07-20: this exact failure mode (both OSM and wiki
        # scrapers silently returning zero) previously left a destination
        # with no grounding data at all and no error to surface it.
        with patch("services.destination_ingestion.geocode_city", new=AsyncMock(return_value=object())), \
             patch("scrapers.osm.ingest_osm_pois", new=AsyncMock(return_value=0)), \
             patch("scrapers.wikivoyage.ingest_wikivoyage", new=AsyncMock(return_value=0)), \
             caplog.at_level("WARNING", logger="services.destination_ingestion"):
            await di.ensure_destination_ingested("Ghost Town")

        assert any("zero OSM POIs and zero wiki chunks" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_warning_when_at_least_one_source_returns_data(self, session_maker, caplog):
        with patch("services.destination_ingestion.geocode_city", new=AsyncMock(return_value=object())), \
             patch("scrapers.osm.ingest_osm_pois", new=AsyncMock(return_value=0)), \
             patch("scrapers.wikivoyage.ingest_wikivoyage", new=AsyncMock(return_value=4)), \
             caplog.at_level("WARNING", logger="services.destination_ingestion"):
            await di.ensure_destination_ingested("Partial Town")

        assert not any("zero OSM POIs and zero wiki chunks" in r.message for r in caplog.records)


class TestColdStartRateLimit:
    """docs/scaling-tech-challenges.md §8 item 5 — cap first-request ingestion
    cost so garbage/spam input naming many distinct destinations can't run up
    unbounded Overpass/Gemini spend."""

    @pytest.mark.asyncio
    async def test_allows_up_to_the_hourly_cap(self):
        for _ in range(di._MAX_COLD_STARTS_PER_HOUR):
            assert await di._cold_start_budget_available() is True

    @pytest.mark.asyncio
    async def test_denies_once_cap_is_exhausted(self):
        for _ in range(di._MAX_COLD_STARTS_PER_HOUR):
            await di._cold_start_budget_available()
        assert await di._cold_start_budget_available() is False

    @pytest.mark.asyncio
    async def test_old_slots_expire_out_of_the_window(self):
        from datetime import datetime, timedelta, timezone
        stale = datetime.now(timezone.utc) - timedelta(hours=2)
        di._cold_start_times.extend([stale] * di._MAX_COLD_STARTS_PER_HOUR)
        # all slots are outside the 1-hour window, so a fresh one should free up
        assert await di._cold_start_budget_available() is True

    @pytest.mark.asyncio
    async def test_exhausted_budget_skips_first_request_ingestion(self, session_maker, caplog):
        from datetime import datetime, timezone
        di._cold_start_times.extend([datetime.now(timezone.utc)] * di._MAX_COLD_STARTS_PER_HOUR)
        with patch("services.destination_ingestion.geocode_city", new=AsyncMock(return_value=object())) as mock_geo, \
             patch("scrapers.osm.ingest_osm_pois", new=AsyncMock()) as mock_osm, \
             caplog.at_level("WARNING", logger="services.destination_ingestion"):
            await di.ensure_destination_ingested("Overbooked City")

        mock_geo.assert_not_awaited()
        mock_osm.assert_not_awaited()
        assert any("budget exhausted" in r.message for r in caplog.records)

        async with session_maker() as db:
            row = await db.get(DestinationIngestionState, "Overbooked City")
            assert row is None  # not persisted, so it can be retried once the window clears
