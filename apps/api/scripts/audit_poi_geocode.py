"""Audit every destination's stored OSM POIs for a mis-geocoded centroid.

WHY THIS EXISTS
---------------
`services/geocode.py::geocode_city` corrects a region-sized name to its hub
town via `_hub_town_in_bbox` — which is itself an Overpass call. When Overpass
throttles, that correction fails and the raw region centroid is used instead,
so ingestion runs against a point tens of km from what the destination name
actually means. Live-confirmed 2026-08-05: "Bali" returned Denpasar cleanly,
then 429, then 504 within one session, and the 25 POIs then in production sat
48km away in the wrong half of the island.

**No existing check catches this.** The data-completeness gate measures POI
count and category share; the prominence guard measures whether the prominence
pass ran. All three pass happily on data for the wrong place — the same blind
spot that let Austin resolve to a 150-person Nevada ghost town (v10.37.0).

WHAT IT MEASURES
----------------
For each destination in `osm_pois`, compares the centroid of its stored POIs
against a freshly-resolved `geocode_city()` for the same name, and reverse-
geocodes the centroid to see which place it actually sits in. Three outcomes:

  OK        — centroid is within `--max-km` of the current geocode
  DRIFT     — centroid and geocode disagree. ⚠️ THIS DOES NOT SAY WHICH ONE IS
              WRONG, and the first real run found it was usually the geocode:
              of 3 drifts, 2 had CORRECT stored data and a live geocode that
              had drifted to a same-named place on another continent
              (Medellin -> Philippines, Amalfi -> Colombia). Read the
              `centroid_place` / `geocode_name` columns and decide per case —
              re-ingesting blind would have destroyed two correct 60-POI pools.
  UNKNOWN   — the geocode or reverse lookup failed this run; says nothing about
              the data, only that we could not check it (rerun later)

Two different bugs produce a DRIFT, and they need opposite fixes:

  * The GEOCODE is wrong -> pin it in `GEOCODE_QUERY_OVERRIDES` and do NOT
    re-ingest until it resolves correctly, or the good stored data is lost.
  * The STORED DATA is wrong -> re-ingest, once the geocode is verified.

Read-only: it never writes to Qdrant. Resumable via `scripts/out/` so a
throttled run can be continued rather than restarted.

Usage (from apps/api, venv python):
    python scripts/audit_poi_geocode.py
    python scripts/audit_poi_geocode.py --max-km 30 --fresh
    python scripts/audit_poi_geocode.py --only Bali,Goa,Kerala
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import httpx

from core.config import settings
from core.logging_config import configure_script_logging
from core.qdrant import get_qdrant
from services.geocode import (
    GEOCODE_QUERY_OVERRIDES,
    NOMINATIM_REVERSE_URL,
    geocode_city,
)

logger = logging.getLogger(__name__)

OUT_DIR = Path(__file__).parent / "out"
STATE_PATH = OUT_DIR / "poi_geocode_audit.jsonl"

# A destination's POIs are fetched within a radius of its centre, so the
# centroid of a healthy pool sits well inside that radius. 25km is generous
# enough for the 30km region-scale overrides (see scrapers/osm.py's
# _OSM_RADIUS_OVERRIDES_M) without hiding a real 48km miss like Bali's.
DEFAULT_MAX_DRIFT_KM = 25.0


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


@dataclass
class Result:
    destination: str
    verdict: str                 # "ok" | "drift" | "unknown"
    poi_count: int
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    geocode_lat: float | None = None
    geocode_lon: float | None = None
    geocode_name: str = ""
    drift_km: float | None = None
    centroid_place: str = ""     # what the centroid reverse-geocodes to
    centroid_country: str = ""
    geocode_country: str = ""
    hub_lookup_degraded: bool = False
    pinned_override: bool = False
    note: str = ""


def stored_centroids(only: set[str] | None) -> dict[str, tuple[int, float, float]]:
    """destination -> (poi_count, centroid_lat, centroid_lon), read-only."""
    client = get_qdrant()
    acc: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_osm,
            limit=1000,
            offset=offset,
            with_payload=["destination", "lat", "lon"],
            with_vectors=False,
        )
        for p in points:
            payload = p.payload or {}
            dest = payload.get("destination")
            lat, lon = payload.get("lat"), payload.get("lon")
            if not dest or lat is None or lon is None:
                continue
            if only and dest not in only:
                continue
            slot = acc.setdefault(dest, [0.0, 0.0])
            slot[0] += float(lat)
            slot[1] += float(lon)
            counts[dest] = counts.get(dest, 0) + 1
        if offset is None:
            break
    return {
        d: (counts[d], acc[d][0] / counts[d], acc[d][1] / counts[d])
        for d in acc if counts.get(d)
    }


async def reverse_place(client: httpx.AsyncClient, lat: float, lon: float) -> tuple[str, str]:
    """(place_name, country) for a coordinate — what is actually *there*."""
    try:
        resp = await client.get(
            NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 10,
                    "addressdetails": 1},
        )
        resp.raise_for_status()
        address = resp.json().get("address", {}) or {}
        place = (
            address.get("city") or address.get("town") or address.get("village")
            or address.get("county") or address.get("state") or ""
        )
        return place, address.get("country", "")
    except Exception as e:
        logger.warning("reverse geocode failed at (%.4f, %.4f): %s", lat, lon, type(e).__name__)
        return "", ""


def load_done() -> dict[str, Result]:
    if not STATE_PATH.exists():
        return {}
    done: dict[str, Result] = {}
    with STATE_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            # An "unknown" verdict is not an answer — re-check it next run,
            # exactly as reingest_prominence_ranking.py refuses to graduate a
            # destination whose ingested count is 0.
            if row.get("verdict") in ("ok", "drift"):
                done[row["destination"]] = Result(**row)
    return done


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-km", type=float, default=DEFAULT_MAX_DRIFT_KM)
    ap.add_argument("--fresh", action="store_true", help="ignore saved state")
    ap.add_argument("--only", default="", help="comma-separated destinations")
    args = ap.parse_args()

    configure_script_logging()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    only = {d.strip() for d in args.only.split(",") if d.strip()} or None

    centroids = stored_centroids(only)
    done = {} if args.fresh else load_done()
    pending = [d for d in sorted(centroids) if d not in done]
    print(f"{len(centroids)} destinations in osm_pois · {len(done)} already audited · "
          f"{len(pending)} to check\n")

    results: list[Result] = list(done.values())
    headers = {"User-Agent": settings.nominatim_user_agent, "Accept-Language": "en"}

    async with httpx.AsyncClient(timeout=20, headers=headers) as http:
        with STATE_PATH.open("w" if args.fresh else "a", encoding="utf-8") as state:
            for i, dest in enumerate(pending, 1):
                count, clat, clon = centroids[dest]
                res = Result(destination=dest, verdict="unknown", poi_count=count,
                             centroid_lat=round(clat, 5), centroid_lon=round(clon, 5),
                             pinned_override=dest.strip().lower() in GEOCODE_QUERY_OVERRIDES)
                try:
                    geo = await geocode_city(dest)
                except Exception as e:
                    res.note = f"geocode failed: {type(e).__name__}"
                    print(f"[{i}/{len(pending)}] {dest:22} UNKNOWN  ({res.note})")
                    results.append(res)
                    state.write(json.dumps(asdict(res), ensure_ascii=False) + "\n")
                    state.flush()
                    continue

                res.geocode_lat, res.geocode_lon = round(geo.lat, 5), round(geo.lon, 5)
                res.geocode_name = geo.display_name
                res.hub_lookup_degraded = geo.hub_lookup_degraded
                res.drift_km = round(haversine_km((clat, clon), (geo.lat, geo.lon)), 1)

                if geo.hub_lookup_degraded:
                    # We cannot judge the stored data against a geocode that is
                    # itself unverified — that is the very bug being audited.
                    res.verdict = "unknown"
                    res.note = "hub-town lookup degraded this run; re-run when Overpass is healthy"
                else:
                    res.verdict = "drift" if res.drift_km > args.max_km else "ok"

                if res.verdict == "drift":
                    res.centroid_place, res.centroid_country = await reverse_place(http, clat, clon)
                    _, res.geocode_country = await reverse_place(http, geo.lat, geo.lon)

                flag = {"ok": "ok     ", "drift": "🔴 DRIFT", "unknown": "UNKNOWN"}[res.verdict]
                extra = ""
                if res.verdict == "drift":
                    extra = f"  centroid sits in {res.centroid_place or '?'}, {res.centroid_country or '?'}"
                print(f"[{i}/{len(pending)}] {dest:22} {flag}  {res.drift_km:>6.1f} km"
                      f"  ({count} POIs){extra}")

                results.append(res)
                state.write(json.dumps(asdict(res), ensure_ascii=False) + "\n")
                state.flush()
                await asyncio.sleep(1.1)   # Nominatim asks for <= 1 req/s

    drift = sorted([r for r in results if r.verdict == "drift"],
                   key=lambda r: -(r.drift_km or 0))
    unknown = [r for r in results if r.verdict == "unknown"]
    print("\n" + "=" * 72)
    print(f"AUDITED {len(results)}  ·  OK {len(results) - len(drift) - len(unknown)}"
          f"  ·  DRIFT {len(drift)}  ·  UNKNOWN {len(unknown)}")
    if drift:
        print(f"\n🔴 DRIFT — stored centroid and live geocode disagree by > {args.max_km:g} km.")
        print("   Read each row before acting: EITHER side can be the wrong one.")
        for r in drift:
            pin = " [has override]" if r.pinned_override else ""
            print(f"   {r.destination:22} {r.drift_km:>6.1f} km  {r.poi_count:>3} POIs  "
                  f"stored near {r.centroid_place or '?'}, {r.centroid_country or '?'}"
                  f"  vs geocode {r.geocode_name[:40]}{pin}")
        print("\n   If 'stored near' is the RIGHT place and the geocode is wrong:")
        print("     pin it in services/geocode.py::GEOCODE_QUERY_OVERRIDES and do NOT")
        print("     re-ingest first — the next refresh would overwrite good data.")
        print("   If 'stored near' is the WRONG place and the geocode is right:")
        print("     re-ingest it (scrapers/osm.py::ingest_osm_pois).")
    if unknown:
        print(f"\nUNKNOWN ({len(unknown)}) — not judged, re-run when Overpass/Nominatim are healthy:")
        print("   " + ", ".join(r.destination for r in unknown[:25]))
    print(f"\nState: {STATE_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
