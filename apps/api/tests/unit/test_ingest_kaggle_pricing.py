"""Tests for scripts/ingest_kaggle_pricing.py — Kaggle flight-fare
calibration-proposal script (Workstream B).

Uses a small in-memory fixture CSV matching the real
`shubhambathwal/flight-price-prediction` `economy.csv` schema (verified
live in 2026-08 — see `docs/kaggle-data-runbook.md`), so these tests don't
need live Kaggle credentials.
"""
import json

from scripts.ingest_kaggle_pricing import (
    _band_index_for_km,
    _normalise_city,
    _parse_month,
    _parse_price,
    _percentile,
    build_proposal,
    load_fares_by_band,
)

_FIXTURE_HEADER = "date,airline,ch_code,num_code,dep_time,from,time_taken,stop,arr_time,to,price\n"

_FIXTURE_ROWS = [
    # short_domestic_hop band (Bangalore->Hyderabad, ~500km)
    "01-03-2022,SpiceJet,SG,101,06:00,Bangalore,01h 20m,non-stop ,07:20,Hyderabad,\"5,000\"\n",
    "02-03-2022,IndiGo,6E,102,08:00,Bangalore,01h 20m,non-stop ,09:20,Hyderabad,\"6,000\"\n",
    "03-03-2022,Vistara,UK,103,10:00,Bangalore,01h 20m,non-stop ,11:20,Hyderabad,\"7,000\"\n",
    # domestic_near_neighbour band (Delhi->Mumbai, ~1150km)
    "01-03-2022,SpiceJet,SG,201,06:00,Delhi,02h 10m,non-stop ,08:10,Mumbai,\"5,953\"\n",
    "02-03-2022,IndiGo,6E,202,08:00,Delhi,02h 10m,non-stop ,10:10,Mumbai,\"6,500\"\n",
    # a row with an unknown city — should be skipped
    "01-03-2022,SpiceJet,SG,301,06:00,Pune,02h 00m,non-stop ,08:00,Nagpur,\"4,000\"\n",
    # a row with a malformed price — should be skipped
    "01-03-2022,SpiceJet,SG,401,06:00,Chennai,01h 30m,non-stop ,07:30,Bangalore,not-a-number\n",
    # a row with a zero price — should be skipped
    "01-03-2022,SpiceJet,SG,402,06:00,Chennai,01h 30m,non-stop ,07:30,Bangalore,0\n",
    # a row with the same source and destination — should be skipped
    "01-03-2022,SpiceJet,SG,403,06:00,Delhi,00h 00m,non-stop ,06:00,Delhi,\"1,000\"\n",
    # a row with a malformed date — should be skipped
    "not-a-date,SpiceJet,SG,404,06:00,Delhi,02h 10m,non-stop ,08:10,Mumbai,\"5,000\"\n",
]


def _write_fixture_csv(tmp_path) -> str:
    path = tmp_path / "economy_fixture.csv"
    path.write_text(_FIXTURE_HEADER + "".join(_FIXTURE_ROWS), encoding="utf-8")
    return str(path)


class TestNormaliseCity:
    def test_known_city_is_normalised_case_insensitively(self):
        assert _normalise_city("Bangalore") == "bangalore"
        assert _normalise_city("  DELHI  ") == "delhi"

    def test_misspelling_alias_is_recognised(self):
        assert _normalise_city("Banglore") == "banglore"

    def test_unknown_city_returns_none(self):
        assert _normalise_city("Nagpur") is None


class TestParseMonth:
    def test_parses_dd_mm_yyyy(self):
        assert _parse_month("11-02-2022") == 2

    def test_rejects_malformed_date(self):
        assert _parse_month("not-a-date") is None

    def test_rejects_out_of_range_month(self):
        assert _parse_month("11-13-2022") is None


class TestParsePrice:
    def test_strips_comma_thousands_separator(self):
        assert _parse_price("5,953") == 5953.0

    def test_rejects_unparseable_price(self):
        assert _parse_price("not-a-number") is None


class TestPercentile:
    def test_median_of_odd_length_list(self):
        assert _percentile([1.0, 2.0, 3.0], 50) == 2.0

    def test_p25_and_p75_bracket_the_median(self):
        values = [float(v) for v in range(1, 101)]  # 1..100
        p25 = _percentile(values, 25)
        p75 = _percentile(values, 75)
        assert p25 < _percentile(values, 50) < p75


class TestBandIndexForKm:
    def test_short_hop_maps_to_first_band(self):
        assert _band_index_for_km(400) == 0

    def test_near_neighbour_maps_to_second_band(self):
        assert _band_index_for_km(1200) == 1

    def test_far_beyond_all_bands_maps_to_last_band(self):
        assert _band_index_for_km(50000) == 4


class TestLoadFaresByBand:
    def test_buckets_known_routes_and_skips_bad_rows(self, tmp_path):
        csv_path = _write_fixture_csv(tmp_path)
        by_band = load_fares_by_band(csv_path, reference_year=2026)

        # 3 valid Bangalore<->Hyderabad rows in the short-hop band.
        assert len(by_band[0]) == 3
        # 2 valid Delhi<->Mumbai rows in the near-neighbour band.
        assert len(by_band[1]) == 2
        # Unknown city, malformed price, zero price, same-city, and
        # malformed-date rows are all skipped — no other bands populated.
        assert set(by_band.keys()) == {0, 1}

    def test_applies_inflation_multiplier_for_dataset_staleness(self, tmp_path):
        csv_path = _write_fixture_csv(tmp_path)
        same_year = load_fares_by_band(csv_path, reference_year=2022)
        four_years_later = load_fares_by_band(csv_path, reference_year=2026)

        # Same fares, inflation-adjusted for a later reference year, should
        # be strictly larger (round-trip = one-way x2 x inflation).
        assert sum(same_year[0]) < sum(four_years_later[0])
        # Sanity-check the raw x2 round-trip conversion at zero inflation.
        assert sorted(same_year[0]) == [10000.0, 12000.0, 14000.0]


class TestBuildProposal:
    def test_proposal_includes_all_bands_even_when_empty(self, tmp_path):
        csv_path = _write_fixture_csv(tmp_path)
        by_band = load_fares_by_band(csv_path, reference_year=2022)
        proposal = build_proposal(by_band)

        assert len(proposal["bands"]) == 5
        assert proposal["bands"][0]["band"] == "short_domestic_hop"
        assert proposal["bands"][0]["n_fares"] == 3
        assert "proposed_median_inr" in proposal["bands"][0]
        # Bands with no fares still appear, just without proposed figures.
        assert proposal["bands"][3]["n_fares"] == 0
        assert "proposed_median_inr" not in proposal["bands"][3]

    def test_proposal_is_json_serialisable(self, tmp_path):
        csv_path = _write_fixture_csv(tmp_path)
        by_band = load_fares_by_band(csv_path, reference_year=2026)
        proposal = build_proposal(by_band)

        json.dumps(proposal)  # should not raise
