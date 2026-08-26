"""Tests for scrapers/poi_provider.py — the Google Places / OSM fallback
orchestrator for the Google Places POI trial (core/config.py's "Google
Places POI trial" block). Postgres is an in-memory sqlite engine here;
Google Places/OSM/Qdrant are mocked — fully offline.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import scrapers.poi_provider as poi_provider
from db import Base
from db_models import PoiProviderUsage
from scrapers.google_places import GooglePlacesQuotaError


@pytest_asyncio.fixture
async def session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    with patch.object(poi_provider, "AsyncSessionLocal", maker):
        yield maker
    await engine.dispose()


def _sample_poi(name: str = "Red Fort", destination: str = "Delhi") -> dict:
    return {"destination": destination, "name": name, "text": f"{name} in {destination}"}


class TestTrialActive:
    def test_true_before_end_date(self):
        with patch.object(poi_provider.settings, "google_places_trial_end_date", "2026-10-31"):
            assert poi_provider.trial_active(today=date(2026, 9, 1)) is True

    def test_true_on_end_date_itself(self):
        with patch.object(poi_provider.settings, "google_places_trial_end_date", "2026-10-31"):
            assert poi_provider.trial_active(today=date(2026, 10, 31)) is True

    def test_false_after_end_date(self):
        with patch.object(poi_provider.settings, "google_places_trial_end_date", "2026-10-31"):
            assert poi_provider.trial_active(today=date(2026, 11, 1)) is False

    def test_malformed_date_fails_safe_to_false(self):
        with patch.object(poi_provider.settings, "google_places_trial_end_date", "not-a-date"):
            assert poi_provider.trial_active(today=date(2026, 9, 1)) is False

    def test_empty_date_fails_safe_to_false(self):
        with patch.object(poi_provider.settings, "google_places_trial_end_date", ""):
            assert poi_provider.trial_active(today=date(2026, 9, 1)) is False


@pytest.mark.asyncio
class TestFetchPoisForDestination:
    async def test_trial_over_goes_straight_to_osm_without_attempting_google(self, session_maker):
        with patch.object(poi_provider, "trial_active", return_value=False), \
             patch("scrapers.osm.fetch_osm_pois", new=AsyncMock(return_value=[_sample_poi()])) as mock_osm:
            pois, provider = await poi_provider.fetch_pois_for_destination("Delhi")

        assert provider == poi_provider.PROVIDER_OSM
        assert pois == [_sample_poi()]
        mock_osm.assert_awaited_once_with("Delhi")

        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        assert len(rows) == 1
        assert rows[0].provider_used == poi_provider.PROVIDER_OSM
        assert rows[0].google_places_attempted is False

    async def test_google_places_success_is_used_and_recorded(self, session_maker):
        gp_pois = [_sample_poi("Qutub Minar")]
        with patch.object(poi_provider, "trial_active", return_value=True), \
             patch.object(poi_provider, "fetch_google_places_pois", new=AsyncMock(return_value=(gp_pois, 5))):
            pois, provider = await poi_provider.fetch_pois_for_destination("Delhi")

        assert provider == poi_provider.PROVIDER_GOOGLE_PLACES
        assert pois == gp_pois

        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.provider_used == poi_provider.PROVIDER_GOOGLE_PLACES
        assert row.google_places_attempted is True
        assert row.google_places_call_count == 5
        assert row.google_places_poi_count == 1
        assert row.google_places_estimated_cost_usd > 0

    async def test_google_places_exception_falls_back_to_osm_and_records_error(self, session_maker):
        with patch.object(poi_provider, "trial_active", return_value=True), \
             patch.object(poi_provider, "fetch_google_places_pois",
                          new=AsyncMock(side_effect=GooglePlacesQuotaError("blocked key"))), \
             patch("scrapers.osm.fetch_osm_pois", new=AsyncMock(return_value=[_sample_poi()])) as mock_osm:
            pois, provider = await poi_provider.fetch_pois_for_destination("Delhi")

        assert provider == poi_provider.PROVIDER_OSM
        mock_osm.assert_awaited_once_with("Delhi")

        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        row = rows[0]
        assert row.provider_used == poi_provider.PROVIDER_OSM
        assert row.google_places_attempted is True
        assert "blocked key" in row.google_places_error

    async def test_empty_google_places_result_falls_back_to_osm(self, session_maker):
        with patch.object(poi_provider, "trial_active", return_value=True), \
             patch.object(poi_provider, "fetch_google_places_pois", new=AsyncMock(return_value=([], 5))), \
             patch("scrapers.osm.fetch_osm_pois", new=AsyncMock(return_value=[_sample_poi()])) as mock_osm:
            pois, provider = await poi_provider.fetch_pois_for_destination("Delhi")

        assert provider == poi_provider.PROVIDER_OSM
        assert pois == [_sample_poi()]
        mock_osm.assert_awaited_once_with("Delhi")

        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        row = rows[0]
        assert row.provider_used == poi_provider.PROVIDER_OSM
        assert row.google_places_attempted is True
        assert row.google_places_call_count == 5

    async def test_osm_failure_propagates_when_trial_over(self, session_maker):
        with patch.object(poi_provider, "trial_active", return_value=False), \
             patch("scrapers.osm.fetch_osm_pois", new=AsyncMock(side_effect=RuntimeError("overpass down"))):
            with pytest.raises(RuntimeError, match="overpass down"):
                await poi_provider.fetch_pois_for_destination("Delhi")

        # No usage row should be recorded since the OSM call itself raised
        # before _record_usage was reached.
        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
class TestRecordUsage:
    async def test_never_raises_even_if_db_write_fails(self, session_maker):
        with patch.object(poi_provider, "AsyncSessionLocal", side_effect=RuntimeError("db down")):
            # Should log and swallow, not propagate.
            await poi_provider._record_usage(
                "Delhi", provider_used=poi_provider.PROVIDER_OSM, google_places_attempted=False,
            )

    async def test_error_message_truncated_to_500_chars(self, session_maker):
        long_error = "x" * 1000
        await poi_provider._record_usage(
            "Delhi", provider_used=poi_provider.PROVIDER_OSM, google_places_attempted=True,
            google_places_error=long_error,
        )
        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        assert len(rows[0].google_places_error) == 500


@pytest.mark.asyncio
class TestIngestPois:
    async def test_trial_over_delegates_to_osms_own_guarded_ingest(self, session_maker):
        """The OSM fallback must go through `ingest_osm_pois_with_outcome`
        (not a reimplemented upsert) so OSM's thin/degraded-geocode guards
        stay intact."""
        with patch.object(poi_provider, "trial_active", return_value=False), \
             patch("scrapers.osm.ingest_osm_pois_with_outcome",
                   new=AsyncMock(return_value=(0, "empty"))) as mock_osm_ingest:
            count, provider = await poi_provider.ingest_pois("Nowhereville")
        assert count == 0
        assert provider == poi_provider.PROVIDER_OSM
        mock_osm_ingest.assert_awaited_once_with("Nowhereville")

        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        assert len(rows) == 1
        assert rows[0].google_places_attempted is False

    async def test_google_places_failure_falls_back_to_osms_guarded_ingest(self, session_maker):
        with patch.object(poi_provider, "trial_active", return_value=True), \
             patch.object(poi_provider, "fetch_google_places_pois",
                          new=AsyncMock(side_effect=GooglePlacesQuotaError("blocked"))), \
             patch("scrapers.osm.ingest_osm_pois_with_outcome",
                   new=AsyncMock(return_value=(12, "written"))) as mock_osm_ingest:
            count, provider = await poi_provider.ingest_pois("Delhi")

        assert count == 12
        assert provider == poi_provider.PROVIDER_OSM
        mock_osm_ingest.assert_awaited_once_with("Delhi")

        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        assert rows[0].google_places_attempted is True
        assert "blocked" in rows[0].google_places_error

    async def test_empty_google_places_result_falls_back_to_osms_guarded_ingest(self, session_maker):
        with patch.object(poi_provider, "trial_active", return_value=True), \
             patch.object(poi_provider, "fetch_google_places_pois", new=AsyncMock(return_value=([], 5))), \
             patch("scrapers.osm.ingest_osm_pois_with_outcome",
                   new=AsyncMock(return_value=(8, "written"))) as mock_osm_ingest:
            count, provider = await poi_provider.ingest_pois("Delhi")

        assert count == 8
        assert provider == poi_provider.PROVIDER_OSM
        mock_osm_ingest.assert_awaited_once_with("Delhi")

    async def test_upserts_points_and_deletes_stale_ones_on_google_places_success(self, session_maker):
        gp_pois = [_sample_poi("Qutub Minar"), _sample_poi("India Gate")]
        mock_client = MagicMock()

        with patch.object(poi_provider, "trial_active", return_value=True), \
             patch.object(poi_provider, "fetch_google_places_pois", new=AsyncMock(return_value=(gp_pois, 2))), \
             patch("core.embeddings.embed", return_value=[[0.1, 0.2], [0.3, 0.4]]), \
             patch("core.qdrant.get_qdrant", return_value=mock_client), \
             patch("core.qdrant.delete_stale_destination_points", return_value=3) as mock_delete:
            count, provider = await poi_provider.ingest_pois("Delhi")

        assert count == 2
        assert provider == poi_provider.PROVIDER_GOOGLE_PLACES
        mock_delete.assert_called_once()
        mock_client.upsert.assert_called_once()
        _, kwargs = mock_client.upsert.call_args
        assert len(kwargs["points"]) == 2

        async with session_maker() as db:
            rows = (await db.execute(select(PoiProviderUsage))).scalars().all()
        assert rows[0].provider_used == poi_provider.PROVIDER_GOOGLE_PLACES
        assert rows[0].google_places_poi_count == 2
