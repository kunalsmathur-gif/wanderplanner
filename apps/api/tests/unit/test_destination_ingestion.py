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

from db import Base
from db_models import DestinationIngestionState
import services.destination_ingestion as di


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
    yield
    di._locks.clear()


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
