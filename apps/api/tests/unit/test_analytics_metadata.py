"""Analytics metadata must survive the JSONB encode.

🔴 Regression tests for a live production bug: `itinerary_generated` passed a
`DestinationInput` model straight into the JSONB `event_metadata` column, so
**every** generation's event — for every destination, not just the reported
one — was lost at commit time with
`TypeError: Object of type DestinationInput is not JSON serializable`.

The failure mode is what makes this worth pinning. `db.add()` succeeds; the
encode only happens during `db.commit()`, and `log_event` is fire-and-forget by
design, so the request looked perfectly healthy while the admin dashboard's
generation count sat at zero.
"""
from __future__ import annotations

import json
import uuid

from core.analytics import _json_safe
from models.trip import DestinationInput, TripConfig


class TestJsonSafe:
    def test_passes_already_serialisable_metadata_through_unchanged(self):
        meta = {"destination": "Goa", "days": 5, "flexible": False, "tags": ["a"]}
        assert _json_safe(meta) is meta

    def test_none_stays_none(self):
        assert _json_safe(None) is None

    def test_coerces_the_pydantic_model_that_caused_the_outage(self):
        meta = {
            "destination": DestinationInput(
                city="Bhutan", country="Bhutan", lat=27.5142, lon=90.4336
            ),
            "days": None,
        }

        safe = _json_safe(meta)

        # The point is that the event survives at all; fidelity is secondary.
        json.dumps(safe)
        assert safe["destination"]["city"] == "Bhutan"
        assert safe["destination"]["lat"] == 27.5142

    def test_coerces_uuid_values(self):
        safe = _json_safe({"target": uuid.UUID("c967abc8-50b1-4a92-a113-42680246966e")})

        json.dumps(safe)
        assert safe["target"] == "c967abc8-50b1-4a92-a113-42680246966e"

    def test_falls_back_to_str_for_anything_else(self):
        class Opaque:
            def __repr__(self) -> str:
                return "<opaque>"

        safe = _json_safe({"thing": Opaque()})

        json.dumps(safe)
        assert safe["thing"] == "<opaque>"

    def test_one_bad_value_does_not_take_its_neighbours_with_it(self):
        # Coercion is total on purpose: a wrong-shaped value should cost
        # fidelity in one field, never the whole event.
        safe = _json_safe({"good": "Goa", "bad": DestinationInput(city="Paro", country="Bhutan")})

        json.dumps(safe)
        assert safe["good"] == "Goa"
        assert safe["bad"]["city"] == "Paro"


class TestItineraryGeneratedPayload:
    """The call site's own field paths — the second half of the same bug."""

    def test_dates_is_a_dict_so_attribute_access_would_raise(self):
        # ⚠️ `TripConfig.dates` is a plain dict by design, so
        # `trip_config.dates.duration_days` raises AttributeError — reaching
        # for the attribute is exactly how this payload came to record
        # `days: None` on every event that survived the encode.
        config = TripConfig()
        assert isinstance(config.dates, dict)

    def test_duration_is_derived_when_only_start_and_end_are_known(self):
        # The common case, and the one the old code got wrong: a trip with
        # concrete dates carries no `duration_days` key at all.
        config = TripConfig(dates={"start": "2026-03-01", "end": "2026-03-06"})

        assert config.dates.get("duration_days") is None
        assert config.effective_duration_days() == 5

    def test_an_explicit_duration_wins(self):
        config = TripConfig(dates={"duration_days": 7, "flexible": True})
        assert config.effective_duration_days() == 7

    def test_unknown_duration_is_none_not_a_fabricated_default(self):
        # `_calc_days` in recommend_cities_chain falls back to 7, which is
        # right for prompt-building and wrong here: a fabricated 7 is
        # indistinguishable from a real one once it is in the events table.
        assert TripConfig().effective_duration_days() is None

    def test_the_payload_this_endpoint_builds_is_serialisable(self):
        config = TripConfig(
            destination=DestinationInput(city="Paro", country="Bhutan"),
            dates={"start": "2026-03-01", "end": "2026-03-06"},
        )

        metadata = {
            "destination": (
                config.destination.city
                if config.destination and config.destination.city
                else config.destination_country
            ),
            "days": config.effective_duration_days(),
        }

        json.dumps(metadata)
        assert metadata == {"destination": "Paro", "days": 5}

    def test_country_mode_falls_back_to_the_country_name(self):
        config = TripConfig(destination_mode="country", destination_country="Bhutan")

        destination = (
            config.destination.city
            if config.destination and config.destination.city
            else config.destination_country
        )

        assert destination == "Bhutan"
