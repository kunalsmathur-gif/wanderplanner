"""Re-ingest every destination under multi-area sampling, and verify the centre.

WHY THIS EXISTS
---------------
v10.72.0 changed how a large destination is *fetched*: instead of one centre
plus a radius, it is sampled from up to 4 real settlements discovered inside
its extent. That only affects data at ingestion time, so every stored pool —
all of which were written single-centre — needs a real re-fetch.

Measured on Goa, a ~105km state, at the 5km default:

    North Goa 5 POIs   South Goa 0 POIs   max reach 15.6km
    Only recognisable beach names in all 60: Baga, Vagator
    Agonda (52.6km), Palolem (57.4km), Colva (25.6km) unreachable

After multi-area sampling: North 18 / Central 28 / South 14.

This also gates hidden gems — `services/gems.py` can only surface a gem whose
POI is in the pool, and sparsely-populated outskirts are exactly where gems
are.

WHAT "DONE" MEANS HERE
----------------------
Not "the call returned". A destination is done when it has real POIs **and**
its stored centroid sits near the geocode it was ingested against. Counting a
call as success is how the v10.40 prominence run reported 169/169 complete
while 29 destinations had no prominence signal at all — the state file must
encode the property we actually want, not a proxy for it.

Two outcomes are deliberately NOT failures, and neither burns the retry budget
in a way that hides them:

  * **degraded geocode** — the hub-town lookup is itself an Overpass call, and
    when it throttles `ingest_osm_pois` keeps the existing data rather than
    overwriting it with wrong-place POIs. That is the guard working. The
    destination stays pending and is retried on the next run.
  * **already-correct data** — a destination whose centroid is already right
    and whose pool is full still gets re-fetched (multi-area may reach further
    than the stored single-centre pool did), but a failure to improve it is
    not a regression.

Real writes against the production Qdrant Cloud cluster. OSM only — Wikivoyage,
YouTube and visa corpora are untouched.

SAFE TO LEAVE RUNNING UNATTENDED. Every write path is guarded: an unverified
geocode cannot overwrite good data, a thin result cannot replace a better one,
and a failed prominence pass cannot either. The worst an interrupted or
throttled run does is leave destinations pending.

    cd apps/api && venv/Scripts/python.exe scripts/reingest_multi_area.py

Resumes automatically. Re-run until it reports 0 pending. Expect several
passes: the comparable v10.40 run reached the end of the alphabet with 29 of
169 still outstanding.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from collections import Counter
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

from qdrant_client import models as qm

from core.config import settings
from core.logging_config import configure_script_logging
from core.qdrant import get_qdrant
from scrapers.osm import _radius_override_for, ingest_osm_pois
from services.geocode import geocode_city

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).parent / "out" / "reingest_multi_area.jsonl"

MAX_ATTEMPTS_PER_DESTINATION = 3

# How far a stored centroid may sit from the geocode it was ingested against
# before the pool is considered mis-centred. Generous enough for a genuine
# multi-area spread — Goa's centroid legitimately drifts ~20km from Panaji once
# South Goa is included — while still catching a real miss like Bali's 48km.
MAX_CENTROID_DRIFT_KM = 30.0

# Overpass is a free shared service and this run is up to 9 queries per
# destination. Pause between destinations so a long batch does not look like
# an attack; it also measurably reduces the 504 rate on a sustained run.
PAUSE_BETWEEN_DESTINATIONS_S = 6.0


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def _load_state() -> tuple[set[str], Counter]:
    """(destinations that are done, attempts per destination).

    Mirrors scripts/reingest_prominence_ranking.py's shape on purpose — same
    resume semantics, same attempt cap, so the two behave alike when a batch
    is interrupted.
    """
    done: set[str] = set()
    attempts: Counter = Counter()
    if not STATE_PATH.exists():
        return done, attempts
    for line in STATE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        destination = record.get("destination")
        if not destination:
            continue
        # A degraded geocode is not an attempt at the thing we are trying to
        # do — the fetch never ran against a trustworthy centre. Counting it
        # would let three throttled minutes retire a destination that has
        # never actually been re-ingested.
        if record.get("outcome") != "degraded_geocode":
            attempts[destination] += 1
        if record.get("outcome") == "ok" or (
            record.get("osm_count") and attempts[destination] >= MAX_ATTEMPTS_PER_DESTINATION
        ):
            done.add(destination)
    return done, attempts


def _record(entry: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _all_destinations() -> list[str]:
    """Every destination already in osm_pois — the authoritative set, rather
    than a hand-maintained list that can drift out of sync with the data."""
    client = get_qdrant()
    seen: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_osm,
            limit=1000,
            offset=offset,
            with_payload=["destination"],
            with_vectors=False,
        )
        for point in points:
            destination = (point.payload or {}).get("destination")
            if destination:
                seen.add(destination)
        if offset is None:
            break
    return sorted(seen)


def _stored_pool(destination: str) -> tuple[int, tuple[float, float] | None, Counter]:
    """(count, centroid, category counts) for what is stored right now."""
    client = get_qdrant()
    points, _ = client.scroll(
        collection_name=settings.qdrant_collection_osm,
        limit=500,
        scroll_filter=qm.Filter(must=[
            qm.FieldCondition(key="destination", match=qm.MatchValue(value=destination))
        ]),
        with_payload=True,
        with_vectors=False,
    )
    lats, lons = [], []
    categories: Counter = Counter()
    for point in points:
        payload = point.payload or {}
        if payload.get("lat") is not None and payload.get("lon") is not None:
            lats.append(float(payload["lat"]))
            lons.append(float(payload["lon"]))
        categories[payload.get("poi_type", "?")] += 1
    if not lats:
        return len(points), None, categories
    return len(points), (sum(lats) / len(lats), sum(lons) / len(lons)), categories


async def _reingest_one(destination: str) -> dict:
    """One destination, start to finish, with the centre verified afterwards."""
    started = time.time()
    entry: dict = {
        "destination": destination,
        "at": datetime.now(UTC).isoformat(),
        "extent_m": _radius_override_for(destination),
    }

    before_count, before_centroid, _ = _stored_pool(destination)
    entry["before_count"] = before_count

    try:
        geo = await geocode_city(destination)
    except Exception as e:
        entry.update(outcome="geocode_failed", error=f"{type(e).__name__}: {e}")
        return entry

    entry["geocode"] = geo.display_name
    # 🔴 The guard in ingest_osm_pois would refuse the overwrite anyway; stopping
    # here saves up to 9 Overpass queries that could not have been used.
    if geo.hub_lookup_degraded:
        entry.update(outcome="degraded_geocode",
                     note="hub-town lookup throttled; centre unverified, nothing written")
        return entry

    centre = (geo.lat, geo.lon)
    try:
        count = await ingest_osm_pois(destination)
    except Exception as e:
        entry.update(outcome="ingest_failed", error=f"{type(e).__name__}: {e}")
        return entry

    after_count, after_centroid, categories = _stored_pool(destination)
    entry.update(osm_count=count, after_count=after_count,
                 elapsed_s=round(time.time() - started, 1))

    if after_centroid is None:
        entry.update(outcome="no_coordinates")
        return entry

    drift = _km(after_centroid, centre)
    entry["centroid_drift_km"] = round(drift, 1)
    entry["moved_km"] = (
        round(_km(after_centroid, before_centroid), 1) if before_centroid else None
    )
    if categories:
        top, n = categories.most_common(1)[0]
        entry["top_category"] = top
        entry["top_category_share"] = round(n / max(after_count, 1), 3)

    # The real bar: POIs exist AND they are near the centre we ingested
    # against. Either half alone has previously reported success on data that
    # was wrong.
    entry["outcome"] = "ok" if (after_count and drift <= MAX_CENTROID_DRIFT_KM) else "mis_centred"
    return entry


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="comma-separated destinations")
    parser.add_argument("--limit", type=int, default=0, help="stop after N destinations")
    parser.add_argument("--fresh", action="store_true", help="ignore saved state")
    args = parser.parse_args()

    configure_script_logging()

    if args.fresh and STATE_PATH.exists():
        STATE_PATH.unlink()
    done, attempts = _load_state()

    only = {d.strip() for d in args.only.split(",") if d.strip()}
    destinations = [d for d in _all_destinations() if not only or d in only]
    pending = [d for d in destinations if d not in done]
    if args.limit:
        pending = pending[: args.limit]

    print(f"{len(destinations)} destinations · {len(done)} done · {len(pending)} to do")
    if not pending:
        print("Nothing pending. 0 remaining.")
        return
    print(f"State: {STATE_PATH}\n")

    counts: Counter = Counter()
    for i, destination in enumerate(pending, 1):
        attempt_no = attempts[destination] + 1
        entry = await _reingest_one(destination)
        entry["attempt"] = attempt_no
        _record(entry)
        counts[entry["outcome"]] += 1

        outcome = entry["outcome"]
        if outcome == "ok":
            detail = (f"{entry['after_count']:>3} POIs · centroid "
                      f"{entry['centroid_drift_km']:>5.1f}km · moved "
                      f"{entry.get('moved_km')}km · {entry['elapsed_s']}s")
        elif outcome == "degraded_geocode":
            detail = "hub lookup throttled — nothing written, will retry"
        else:
            detail = str(entry.get("error") or entry.get("note") or
                         entry.get("centroid_drift_km", ""))
        print(f"[{i}/{len(pending)}] {destination:24} {outcome:17} {detail}")

        if i < len(pending):
            await asyncio.sleep(PAUSE_BETWEEN_DESTINATIONS_S)

    done_after, _ = _load_state()
    remaining = [d for d in destinations if d not in done_after]
    print("\n" + "=" * 72)
    for outcome, n in counts.most_common():
        print(f"  {outcome:18} {n}")
    print(f"\n{len(remaining)} still pending — re-run to continue.")
    if remaining:
        print("  " + ", ".join(remaining[:25]) + ("…" if len(remaining) > 25 else ""))
    degraded = counts.get("degraded_geocode", 0)
    if degraded:
        print(f"\n{degraded} were skipped because the hub-town Overpass lookup was "
              "throttled.\nThat is the data-loss guard working, not a failure — their "
              "existing POIs\nwere left untouched. Re-run when Overpass is healthier.")


if __name__ == "__main__":
    asyncio.run(main())
