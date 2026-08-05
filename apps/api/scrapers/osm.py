"""OSM POI ingester — docs §3I.

Fetches real points of interest (name, category, lat/lon, tags) for a
destination from the OpenStreetMap Overpass API and ingests them into the
`osm_pois` Qdrant collection. This gives the itinerary LLM real coordinates
and venue names to ground itineraries in, instead of relying on the model to
invent (and often hallucinate/mis-locate) lat/lon values.

No API key required — Overpass is a free public service, rate-limited by
convention (we keep queries small and destination-scoped).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
from typing import Any

import httpx

from core.config import settings
from core.embeddings import embed
from core.ingestion_metadata import OSM_POI_TYPE_TO_ATTRACTION, build_ingestion_payload
from core.qdrant import count_destination_points, delete_stale_destination_points, get_qdrant
from services.geocode import area_centroids, geocode_city

logger = logging.getLogger(__name__)

# Overpass's public instance frequently returns transient failures under
# load (429 rate-limit, 504 gateway timeout) — found 2026-07-20 during live
# re-ingestion testing, where a request would fail and succeed seconds later
# on its own. Retrying with backoff here means a scheduled/background
# ingestion job doesn't silently record a destination as having zero POIs
# just because Overpass was briefly busy.
#
# 2026-07-23: bumped from 3 to 5 attempts and switched linear->exponential
# backoff (with jitter) after live large-batch re-ingestion runs (~9-34
# destinations sequentially) visibly saturated the single primary mirror —
# Warsaw/Maldives needed a within-run retry and Fiji/Hawaii needed a whole
# extra out-of-band retry after exhausting the old 3-attempt/15s-max budget.
# Each attempt also rotates to the next mirror in _overpass_mirrors() so
# repeated failures don't all land on the same rate-limited instance.
_MAX_FETCH_ATTEMPTS = 5
_RETRY_BASE_DELAY_S = 5.0
_RETRY_MAX_DELAY_S = 60.0
_RETRY_JITTER_S = 3.0


def _is_hard_refusal(exc: Exception) -> bool:
    """True when a mirror actively refused the request rather than being
    busy. 429 (rate limited) and 408 (request timeout) are congestion and
    deserve a backoff; other 4xx responses mean this mirror will keep saying
    no, so waiting before moving on just wastes the retry budget."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500 and status not in (408, 429)


def _overpass_mirrors() -> list[str]:
    """Primary Overpass instance first, then the configured fallback
    mirrors, deduplicated while preserving order."""
    seen: set[str] = set()
    mirrors: list[str] = []
    for url in [settings.osm_overpass_url, *settings.osm_overpass_fallback_mirrors]:
        if url and url not in seen:
            seen.add(url)
            mirrors.append(url)
    return mirrors

# OSM tag categories worth surfacing to the itinerary LLM. Each maps to a
# human-readable POI type used in the embedded description text.
#
# Deliberately broad across heritage/culture, nature, sports, arts/science,
# photo-worthy spots, and transport landmarks — not just food/drink — so a
# destination's ingested pool stays well-rounded regardless of any single
# trip's preferences. Per-trip preference weighting (e.g. more parks for a
# toddler, more sports venues for a sports fan) belongs downstream, in
# itinerary-generation retrieval, not here — this pool is shared across
# every trip to the destination.
POI_TAG_QUERIES: dict[str, str] = {
    # Heritage / historic / cultural
    'tourism=attraction': "attraction",
    'tourism=museum': "museum",
    'tourism=gallery': "art gallery",
    'tourism=artwork': "public artwork",
    'tourism=zoo': "zoo",
    'tourism=aquarium': "aquarium",
    'tourism=theme_park': "theme park",
    'historic=monument': "historic monument",
    'historic=castle': "castle",
    'historic=ruins': "historic ruins",
    'historic=archaeological_site': "archaeological site",
    'historic=memorial': "memorial",
    'amenity=place_of_worship': "place of worship",
    # Arts / science / entertainment
    'amenity=theatre': "theatre",
    'amenity=arts_centre': "arts centre",
    'amenity=cinema': "cinema",
    # Sports
    'leisure=stadium': "stadium",
    'leisure=sports_centre': "sports centre",
    # Nature / photo-worthy / outdoors
    'tourism=viewpoint': "viewpoint",
    'leisure=park': "park",
    'leisure=garden': "garden",
    'leisure=nature_reserve': "nature reserve",
    'natural=beach': "beach",
    # Transportation landmarks (useful for orientation, and often
    # destinations in their own right — e.g. King's Cross/Grand Central)
    'railway=station': "train station",
    'aeroway=aerodrome': "airport",
    # Food/drink and shopping — kept last on purpose: see
    # _prioritize_landmarks below, these are numerically dominant in any
    # dense urban core and must not crowd out the categories above.
    'shop=mall': "shopping mall",
    'shop=marketplace': "market",
    'amenity=restaurant': "restaurant",
    'amenity=cafe': "cafe",
    'amenity=bar': "bar",
}


# Once a destination's dense urban core is queried across all tag types in a
# single unioned Overpass call, food/drink establishments vastly outnumber
# landmarks (live-verified: central London within 5km returned 45+ restaurant/
# cafe/bar nodes but as few as 1-2 tourism/historic nodes). A flat Overpass-side
# result cap then fills entirely with food/drink before any landmark node is
# ever seen, starving out exactly the attraction/museum/monument data the
# itinerary LLM and interest-pinning (services/poi_pinning.py) need most.
# Fix: over-fetch from Overpass, then prioritise non-food/drink categories
# client-side before truncating to the final cap.
_RAW_FETCH_MULTIPLIER = 5
_RAW_FETCH_CEILING = 400
_FOOD_DRINK_LABELS = {"restaurant", "cafe", "bar"}

# Nothing in the pipeline used to rank POIs by *prominence*, so the 60 slots
# filled with whatever Overpass happened to return first and a nameless
# neighbourhood shrine had exactly the same claim on a slot as Kiyomizu-dera.
# Live-measured 2026-07-25: Kyoto's pool held 21 obscure temples and 20 small
# museums but none of Kiyomizu-dera/Fushimi Inari/Kinkaku-ji/Arashiyama;
# Delhi carried 7 train stations but no Red Fort, Humayun's Tomb or Chandni
# Chowk; Bangkok carried 12 train stations but no Wat Arun or Wat Pho. Those
# are exactly the places travellers name in the ingested comments, which made
# this the binding constraint on hidden gems (services/gems.py can only match
# names that are in the pool) and on itinerary grounding generally.
#
# Two separate causes, both fixed below.
#
# 1. **The query only ever asked for `node`.** Famous sites are mapped as
#    areas — a live probe found Kiyomizu-dera, Kinkaku-ji and Ginkaku-ji are
#    all `way` elements, and Delhi's Jama Masjid a `relation` — so they were
#    structurally unreachable, not merely out-ranked. (The `out center` verb
#    and the `element["center"]` read below were already written for
#    ways/relations; only the query kind was missing.)
#
# 2. **No prominence signal.** OSM carries a strong free one: `wikidata`/
#    `wikipedia`/`heritage` are exactly what famous sites are tagged with and
#    what neighbourhood shrines lack.
#
# The naive fix — switching the existing broad query to `nwr` — does *not*
# work, and failing to notice would look like success: Overpass's `out
# <limit>` truncates in element-type order, nodes first, so a capped `nwr`
# query returns an all-node result and silently drops every way and relation
# (live-verified: an `nwr` query capped at 3000 for Kyoto came back 3000/3000
# nodes). Asking for every way/relation *uncapped* is the other extreme and
# simply times out on public Overpass in a dense city.
#
# So prominence is fetched as its own second pass: nodes+ways+relations, but
# filtered to elements carrying `wikidata`. That filter is what makes an
# uncapped query affordable — Delhi returns 159 elements, Kyoto 345, Bangkok
# 668 — and no cap is applied to it precisely because a cap would reintroduce
# the nodes-first truncation above.
#
# `wikidata` alone, not a regex over `wikidata|wikipedia|heritage`: the wider
# filter was measured live on the same cities and is not worth it. Istanbul
# gained 7 elements out of 836 for double the query time (42s -> 89s), and
# Bangkok's wider query timed out on every mirror after 202s where the
# `wikidata` one succeeded in 36s. In practice almost everything tagged
# `wikipedia` or `heritage` carries `wikidata` too.
_PROMINENCE_FILTER_TAG = "wikidata"

# Transport and food/drink are left out of the prominence pass. They are
# already numerically abundant in the broad node pass, and the point of this
# pass is the places a traveller plans a day *around* — v10.39.0 had to
# exclude train stations from gem candidates for the same reason (Istanbul's
# entire gem list came back as three metro stops).
_PROMINENCE_EXCLUDED_LABELS = _FOOD_DRINK_LABELS | {"train station", "airport"}

# The prominence query is heavier than the broad one and is supplementary
# rather than load-bearing, so it gets a smaller retry budget: a degraded
# Overpass shouldn't cost two full exponential-backoff budgets per
# destination before the broad pass even starts. Four rather than three
# because one of the three configured mirrors is currently hard-refusing
# every request (see `_is_hard_refusal`) — with refusals costing no backoff,
# a 4-attempt rotation still yields three real tries.
_PROMINENCE_FETCH_ATTEMPTS = 4

# Additive prominence signals, in descending strength. Deliberately a plain
# weighted tag count rather than anything learned or LLM-derived: it has to
# run over every element of every ingestion with no API budget, and the
# ordering it produces only has to be *better than arrival order*, which is
# what it replaces. `heritage=1` is OSM's convention for world-level (UNESCO)
# listing, so it earns a second increment on top of the base heritage signal.
_PROMINENCE_WEIGHTS: dict[str, int] = {
    "wikidata": 3,
    "wikipedia": 3,
    "heritage": 2,
    "website": 1,
    "name:en": 1,
}
_HERITAGE_WORLD_LEVEL = "1"
_HERITAGE_WORLD_BONUS = 2

# Ceiling on any one category's share of the pool, applied during selection
# (see _prioritize_landmarks). Deliberately half of the data-completeness
# gate's MAX_CATEGORY_SHARE=0.5, so a pool this module produces clears that
# gate with margin instead of sitting on the line; at the default 60-POI cap
# it works out to 15 slots per category. This is the "per-category hard cap
# in osm.py" that the Paris-metro/temple-town category-skew question was
# left open on — worth revisiting together with that gate, not separately.
_MAX_CATEGORY_SHARE_IN_POOL = 0.25


def _prominence_score(tags: dict[str, str]) -> int:
    """How likely `tags` describe somewhere a traveller has heard of.

    Not a measure of quality or of how good a visit would be — only of how
    well-documented the place is, which is the part OSM can actually tell us
    for free.
    """
    score = 0
    if tags.get("wikidata"):
        score += _PROMINENCE_WEIGHTS["wikidata"]
    if tags.get("wikipedia"):
        score += _PROMINENCE_WEIGHTS["wikipedia"]
    heritage = (tags.get("heritage") or "").strip()
    if heritage:
        score += _PROMINENCE_WEIGHTS["heritage"]
        if heritage == _HERITAGE_WORLD_LEVEL:
            score += _HERITAGE_WORLD_BONUS
    if tags.get("website") or tags.get("contact:website"):
        score += _PROMINENCE_WEIGHTS["website"]
    # An English name is itself weak evidence of international recognition —
    # a mapper only bothers adding one for a place foreign visitors look for.
    if tags.get("name:en") or tags.get("int_name"):
        score += _PROMINENCE_WEIGHTS["name:en"]
    return score


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """Build an Overpass QL query for all POI categories around a point.

    The broad pass: nodes only, every category, over-fetched then prioritised
    client-side. Left node-only on purpose — see the block comment above on
    why widening *this* query to `nwr` would time out rather than help.
    """
    clauses = []
    for tag, _ in POI_TAG_QUERIES.items():
        key, value = tag.split("=", 1)
        clauses.append(f'node["{key}"="{value}"](around:{radius_m},{lat},{lon});')
    body = "\n  ".join(clauses)
    raw_limit = min(settings.osm_poi_max_results * _RAW_FETCH_MULTIPLIER, _RAW_FETCH_CEILING)
    return f"""
[out:json][timeout:25];
(
  {body}
);
out center {raw_limit};
""".strip()


def _build_prominence_query(lat: float, lon: float, radius_m: int) -> str:
    """Build the prominence pass: nodes, ways *and* relations, restricted to
    elements carrying a `wikidata` tag, with no result cap (a cap would
    truncate nodes-first and drop exactly the ways/relations this pass exists
    to fetch). A longer server-side timeout than the broad pass — it covers a
    wider radius and has to consider area geometry."""
    clauses = []
    for tag, label in POI_TAG_QUERIES.items():
        if label in _PROMINENCE_EXCLUDED_LABELS:
            continue
        key, value = tag.split("=", 1)
        clauses.append(
            f'nwr["{key}"="{value}"]["{_PROMINENCE_FILTER_TAG}"](around:{radius_m},{lat},{lon});'
        )
    body = "\n  ".join(clauses)
    return f"""
[out:json][timeout:90];
(
  {body}
);
out center;
""".strip()


# OSM's `name` tag holds the name in the *local* language, so a Kyoto POI is
# stored as "清水寺" and a Cairo one in Arabic. Everything downstream reads
# names as text a traveller would recognise or type: services/gems.py looks
# for POI names inside English-language traveller comments, services/
# poi_pinning.py matches them against LLM-proposed English names, and the
# itinerary itself is rendered in English. Live-audited 2026-07-25: 59 of
# Kyoto's 60 ingested POIs were in Japanese script and consequently matched
# nothing at all, which is why hidden gems returned an empty list there
# despite 237 real comments being ingested.
#
# A live Overpass probe found `name:en` present on 43 of 107 named Kyoto
# nodes, and some of the rest carry the Latin form parenthesised inside the
# local name ("新熊野神社 (Imakumano Shrine)"). Prefer those, in that order,
# and keep the local name alongside rather than discarding it.
_LATIN_IN_PARENS = re.compile(r"\(([^)]*)\)")
_LATIN_LETTER = re.compile(r"[A-Za-z]")


def _display_name(tags: dict[str, str]) -> str:
    """The name to store for a POI: English where OSM knows one, else the
    local name (which is already Latin script for most destinations)."""
    for key in ("name:en", "int_name"):
        value = (tags.get(key) or "").strip()
        if value:
            return value

    name = (tags.get("name") or "").strip()
    if not name:
        return ""

    # Only treat a bracketed Latin fragment as a translation when the rest of
    # the name has no Latin in it. Otherwise the brackets are a disambiguator
    # ("Victoria (Seychelles)") and promoting them would rename the POI.
    outside = _LATIN_IN_PARENS.sub("", name)
    if not _LATIN_LETTER.search(outside):
        for inner in _LATIN_IN_PARENS.findall(name):
            if _LATIN_LETTER.search(inner):
                return inner.strip()
    return name


def _poi_type(tags: dict[str, str]) -> str:
    for tag, label in POI_TAG_QUERIES.items():
        key, value = tag.split("=", 1)
        if tags.get(key) == value:
            return label
    return "place of interest"


def _describe_poi(name: str, poi_type: str, destination: str, tags: dict[str, str]) -> str:
    """Build a short natural-language description to embed for semantic search."""
    bits = [f"{name} is a {poi_type} in {destination}."]
    if tags.get("cuisine"):
        bits.append(f"Cuisine: {tags['cuisine'].replace(';', ', ')}.")
    if tags.get("description"):
        bits.append(tags["description"])
    return " ".join(bits)


async def _fetch_overpass(
    query: str,
    destination: str,
    pass_label: str,
    max_attempts: int = _MAX_FETCH_ATTEMPTS,
) -> list[dict] | None:
    """POST `query` to Overpass, retrying across mirrors, and return its raw
    elements.

    Returns `None` rather than raising when every attempt fails — a caller
    merging two passes must still be able to use whichever one succeeded.
    `None` (the request failed) is deliberately distinct from `[]` (the
    request succeeded and this area genuinely has nothing): only the former
    is grounds for protecting already-stored data.
    """
    # Overpass's usage policy asks for an identifiable User-Agent; some
    # network paths (corporate proxies/CDNs in front of overpass-api.de)
    # also reject POST requests missing an explicit Accept header with a
    # bare 406, so send both defensively.
    headers = {"User-Agent": settings.nominatim_user_agent, "Accept": "*/*"}

    mirrors = _overpass_mirrors()
    for attempt in range(1, max_attempts + 1):
        mirror_url = mirrors[(attempt - 1) % len(mirrors)]
        async with httpx.AsyncClient(timeout=120, headers=headers) as client:
            try:
                resp = await client.post(mirror_url, data={"data": query})
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return data.get("elements", [])
            except Exception as e:
                if attempt == max_attempts:
                    logger.warning(
                        "Overpass %s fetch failed for %r after %d attempts across %d mirrors: %s",
                        pass_label, destination, attempt, len(mirrors), e,
                    )
                    return None
                # A hard refusal is not congestion, so backing off doesn't
                # help — rotate to the next mirror immediately instead.
                # Live-measured 2026-07-25 during the prominence re-ingestion:
                # `overpass.openstreetmap.fr` answered 403 to 5 of 5 requests
                # while the other two mirrors were still serving, so every
                # attempt landing there burned a retry slot *and* an
                # exponential-backoff sleep for a mirror that was never going
                # to answer.
                if _is_hard_refusal(e):
                    logger.info(
                        "Overpass %s attempt %d/%d for %r hard-refused by %s (%s), "
                        "rotating to %s without backoff",
                        pass_label, attempt, max_attempts, destination, mirror_url, e,
                        mirrors[attempt % len(mirrors)],
                    )
                    continue
                # Exponential backoff, capped, with jitter so a batch of
                # destinations that all failed around the same moment don't
                # all retry in lockstep and re-trigger the same rate limit.
                delay = min(_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)), _RETRY_MAX_DELAY_S)
                delay += random.uniform(0, _RETRY_JITTER_S)
                logger.info(
                    "Overpass %s attempt %d/%d for %r failed (%s), retrying on %s in %.1fs",
                    pass_label, attempt, max_attempts, destination, e,
                    mirrors[attempt % len(mirrors)], delay,
                )
                await asyncio.sleep(delay)
    return None


def _element_to_poi(element: dict, destination: str) -> dict | None:
    """Convert one raw Overpass element into a POI payload, or None if it
    can't be used (unnamed, or no resolvable coordinates)."""
    tags: dict[str, str] = element.get("tags", {})
    name = _display_name(tags)
    if not name:
        return None  # skip unnamed nodes — useless for itinerary display

    # Retained so a comment or query written in the local script can still
    # be matched (services/gems.py checks both) and so the traveller can
    # be shown the name that is actually on the signage.
    local_name = (tags.get("name") or "").strip()

    # Nodes carry lat/lon directly; ways and relations carry a `center`
    # instead, which is why the queries ask for `out center`.
    poi_lat = element.get("lat") or (element.get("center") or {}).get("lat")
    poi_lon = element.get("lon") or (element.get("center") or {}).get("lon")
    if poi_lat is None or poi_lon is None:
        return None

    poi_type = _poi_type(tags)
    element_type = element.get("type") or "node"
    return build_ingestion_payload(
        destination=destination,
        source="osm",
        text=_describe_poi(name, poi_type, destination, tags),
        source_url=f"https://www.openstreetmap.org/{element_type}/{element.get('id', '')}",
        source_name="OpenStreetMap",
        # `poi_type` is the human-readable label from POI_TAG_QUERIES; anything
        # not in the map (including `_poi_type`'s "place of interest" fallback)
        # is a generic activity.
        attraction_type=OSM_POI_TYPE_TO_ATTRACTION.get(poi_type, "activity"),
        extra={
            "name": name,
            "name_local": local_name if local_name != name else "",
            "poi_type": poi_type,
            "lat": float(poi_lat),
            "lon": float(poi_lon),
            "prominence": _prominence_score(tags),
            "tags": {k: v for k, v in tags.items() if k in ("cuisine", "opening_hours", "website")},
        },
    )


async def _fetch_osm_pois_with_meta(
    destination: str,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: int | None = None,
) -> tuple[list[dict], bool, bool]:
    """`fetch_osm_pois`, plus whether the prominence pass actually succeeded,
    plus whether the GEOCODE behind it is unverified.

    That second value matters to `ingest_osm_pois` and cannot be inferred from
    the POIs themselves: when the prominence pass fails, the broad pass still
    returns a full 60 well-distributed POIs, so the existing
    thin/dominated data-loss guard sees a perfectly healthy-looking result and
    lets it overwrite good stored data. Live-hit on the very first run of this
    change — Delhi's prominence query 403'd on all three mirrors and the
    fallback pool contained none of Red Fort, Humayun's Tomb, Qutub Minar,
    India Gate, Lotus Temple, Jama Masjid or Lodhi Gardens.
    """
    # Caller-supplied coordinates are the caller's own responsibility — we did
    # no geocoding, so there is nothing here to be unsure about.
    geocode_degraded = False
    bbox: tuple[float, float, float, float] | None = None
    if lat is None or lon is None:
        geo = await geocode_city(destination)
        lat, lon = geo.lat, geo.lon
        bbox = geo.bbox
        # 🔴 True when this is a region centroid we wanted to correct to its hub
        # town but couldn't, because that correction is itself an Overpass call
        # and it errored/throttled. Ingesting against it puts POIs tens of km
        # from what the destination name means — see ingest_osm_pois' guard.
        geocode_degraded = geo.hub_lookup_degraded
        if geocode_degraded:
            logger.warning(
                "%r: geocoded to an UNVERIFIED region centroid (%.4f, %.4f) — the "
                "hub-town lookup failed rather than finding no hub.",
                destination, lat, lon,
            )

    radius = radius_m or settings.osm_poi_radius_m
    # A destination big enough that one circle cannot reach its far end gets
    # sampled from several real settlements instead — see the block comment
    # above `_MULTI_AREA_MIN_SPAN_KM`. Only when the caller did not pin
    # coordinates (that is an explicit "use this point") and only when we have
    # a trustworthy bbox to size the place from.
    centroids: list[tuple[str, float, float]] = [("", lat, lon)]
    # Two ways to know a destination is too big for one circle, and both must
    # count. A declared extent (`_OSM_RADIUS_OVERRIDES_M`) is the stronger
    # signal precisely BECAUSE it survives hub-pinning: once "Goa" resolves to
    # Panaji, every automatic size check sees a small town, so the table is the
    # only thing left that knows the state is 105km long.
    declared_extent = _radius_override_for(destination)
    area_bbox = bbox
    if declared_extent:
        area_bbox = _bbox_around(lat, lon, declared_extent)
    if area_bbox and not geocode_degraded:
        span = _bbox_span_km(area_bbox)
        if span >= _MULTI_AREA_MIN_SPAN_KM:
            try:
                towns = await area_centroids([str(v) for v in area_bbox], _MAX_AREA_CENTROIDS)
            except Exception:
                logger.warning("%r: area-centroid lookup failed", destination, exc_info=True)
                towns = []
            centroids = _pick_spread_centroids((lat, lon), towns, area_bbox)
            logger.info(
                "%r: %.0fkm across — sampling %d areas: %s",
                destination, span, len(centroids),
                ", ".join(c[0] or "primary" for c in centroids),
            )

    # Each centre contributes its own independently-prioritised pool, so the
    # interleave below can guarantee every area is represented.
    pools: list[list[dict]] = []
    prominence_ok = False
    seen_names: set[str] = set()
    per_area_radius = _AREA_RADIUS_M if len(centroids) > 1 else radius

    for area_name, alat, alon in centroids:
        area_prominence_radius = max(per_area_radius, settings.osm_prominence_radius_m)
        # Prominence pass first so that a landmark mapped both as an area and
        # as a node is kept as the area element, which is the one carrying the
        # richer tags (and therefore the honest prominence score).
        prominent_elements = await _fetch_overpass(
            _build_prominence_query(alat, alon, area_prominence_radius),
            destination,
            "prominence",
            max_attempts=_PROMINENCE_FETCH_ATTEMPTS,
        )
        # An empty prominence result is genuinely possible for a rural or
        # thinly mapped destination, so "did the request succeed" is tracked
        # separately from "did it return anything" — only the former is a
        # reason to protect existing data. Across several areas, one success
        # is enough: the pool as a whole then carries a landmark ranking.
        prominence_ok = prominence_ok or prominent_elements is not None
        broad_elements = await _fetch_overpass(
            _build_overpass_query(alat, alon, per_area_radius), destination, "broad",
        )
        elements = (prominent_elements or []) + (broad_elements or [])
        if not elements:
            continue
        logger.info(
            "%r%s: Overpass returned %d prominent + %d broad elements",
            destination, f" [{area_name}]" if area_name else "",
            len(prominent_elements or []), len(broad_elements or []),
        )

        area_pois: list[dict] = []
        for element in elements:
            poi = _element_to_poi(element, destination)
            # Dedupe across areas as well as within one: overlapping radii
            # legitimately return the same place twice, and a duplicate would
            # otherwise consume a slot the interleave owes to another area.
            if poi is None or poi["name"] in seen_names:
                continue
            seen_names.add(poi["name"])
            area_pois.append(poi)
        if area_pois:
            pools.append(_prioritize_landmarks(area_pois))

    if not pools:
        return [], prominence_ok, geocode_degraded

    cap = settings.osm_poi_max_results
    if len(pools) == 1:
        return pools[0][:cap], prominence_ok, geocode_degraded
    return _interleave_by_area(pools, cap), prominence_ok, geocode_degraded


async def fetch_osm_pois(
    destination: str,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: int | None = None,
) -> list[dict]:
    """Fetch raw POIs for `destination` from Overpass. Geocodes the destination
    first if lat/lon aren't already known. `radius_m` defaults to
    `settings.osm_poi_radius_m`; `ingest_osm_pois` passes the wider
    `osm_poi_radius_expanded_m` as a second pass for thin/category-dominated
    destinations.

    Two Overpass passes are merged: a prominence pass (nodes+ways+relations
    carrying `wikidata`, over a wider radius) and the broad node pass. See the
    block comment above `_PROMINENCE_FILTER_TAG` for why it has to be two
    queries rather than one widened one.
    """
    pois, _, _ = await _fetch_osm_pois_with_meta(destination, lat, lon, radius_m)
    return pois


def _prioritize_landmarks(pois: list[dict]) -> list[dict]:
    """Order POIs so the most prominent land first, no single tag type can
    dominate the final truncation, and food/drink is drawn from only after
    every other category is exhausted.

    A plain "food/drink last" stable sort (the original version of this
    function) fixes total food/drink starvation, but doesn't stop a single
    *non*-food/drink category from crowding out the others the same way:
    live-verified 2026-07-20, with only that stable sort in place, a 60-slot
    cap for central Paris came back 51/60 "train station" nodes (Paris's
    metro network is extremely dense) and Tokyo came back 40/60 "place of
    worship" nodes (shrines/temples are extremely common), in both cases
    crowding out museums/attractions/theatres/parks almost entirely — the
    same starvation bug, just relocated to a different category. Round-robin
    selection guarantees every category present gets a turn before any single
    category can fill the remaining slots.

    Plain round-robin, though, treats every category as equally deserving,
    and that over-corrects: live-verified 2026-07-25 after the prominence
    passes were added, Delhi's 60 slots went to 4 cinemas and 4 art galleries
    but only 4 attractions, and Red Fort, Humayun's Tomb, Qutub Minar and
    India Gate still missed out — a cinema had exactly the same claim on a
    slot as the Red Fort. So selection runs in descending *prominence tiers*,
    round-robinning across categories within each tier:

      - Across tiers, prominence wins: every UNESCO-listed, Wikipedia-known
        site is placed before the first unremarkable neighbourhood cinema,
        whatever their categories.
      - Within a tier, round-robin still guarantees no category can crowd out
        the others — and when no POI carries any prominence signal the whole
        pool collapses to a single tier, which is exactly the previous
        behaviour.

    A per-category cap then bounds the tail, because tiers alone don't: a
    monument-dense city like Delhi has dozens of equally prominent monuments,
    and without a cap they would take every slot before a museum or a park
    got one. POIs past the cap aren't discarded, only deferred behind
    everything else, so a thinly-mapped destination still fills its quota
    rather than shrinking.
    """
    from collections import Counter, defaultdict, deque

    landmarks = [p for p in pois if p["poi_type"] not in _FOOD_DRINK_LABELS]
    food_drink = [p for p in pois if p["poi_type"] in _FOOD_DRINK_LABELS]

    def _round_robin(items: list[dict]) -> list[dict]:
        buckets: dict[str, deque] = defaultdict(deque)
        for poi in items:
            buckets[poi["poi_type"]].append(poi)
        keys = list(buckets.keys())
        ordered: list[dict] = []
        while any(buckets[key] for key in keys):
            for key in keys:
                if buckets[key]:
                    ordered.append(buckets[key].popleft())
        return ordered

    def _select(items: list[dict]) -> list[dict]:
        if not items:
            return []
        ranked: list[dict] = []
        # Descending tiers; ties inside a tier keep arrival order, so the
        # no-prominence-anywhere case is byte-identical to plain round-robin.
        for tier in sorted({p.get("prominence", 0) for p in items}, reverse=True):
            ranked.extend(_round_robin([p for p in items if p.get("prominence", 0) == tier]))

        cap = max(1, round(settings.osm_poi_max_results * _MAX_CATEGORY_SHARE_IN_POOL))
        counts: Counter = Counter()
        chosen: list[dict] = []
        overflow: list[dict] = []
        for poi in ranked:
            label = poi["poi_type"]
            if counts[label] < cap:
                counts[label] += 1
                chosen.append(poi)
            else:
                overflow.append(poi)
        return chosen + overflow

    return _select(landmarks) + _select(food_drink)


# Mirrors eval/data_completeness_scoring.py's MIN_OSM_POIS/MAX_CATEGORY_SHARE
# gate thresholds (not imported directly — that module lives in eval/ and
# pulls in eval-only deps — kept in sync by hand, same as the two other
# nearby "same rationale as X" comments in this file).
_MIN_POIS_BEFORE_RADIUS_EXPANSION = 20
_MAX_CATEGORY_SHARE_BEFORE_EXPANSION = 0.5

# Region-scale destinations whose landmarks are simply further from the hub
# than any city's are, keyed the same way as GEOCODE_QUERY_OVERRIDES
# (destination.strip().lower()).
#
# The default 5km radius (and the 15km thin-destination retry) encodes a
# city-shaped assumption: pick the centre, and what a traveller means by the
# name is within walking-to-short-cab distance. That is false for an island
# or a region, where the name covers a whole area and its landmarks are
# spread across it. Bali is the worked example — from Denpasar, Tanah Lot is
# 15.3km, Ubud 19km and Uluwatu 22.7km, so ALL of them fall outside both the
# broad pass and the 15km prominence pass, and the 60-POI pool fills up with
# Denpasar municipal noise (9 Catholic churches, 4 cinemas, 5 gyms) while
# every landmark the destination is known for is missed. Measured 2026-08-05
# from the corrected Denpasar centre: 5km/15km return zero marquee landmarks;
# 30km returns Tanah Lot, Uluwatu, Ubud Palace, Sacred Monkey Forest, Tirta
# Empul and Tegallalang Rice Terraces, with top-category share still 0.25 —
# comfortably inside the completeness gate's 0.5.
#
# ⚠️ This must live here rather than being passed at the call site, because
# core/scheduler.py::_refresh_osm_pois calls `ingest_osm_pois(destination)`
# with no radius — a one-off wide ingestion would be silently reverted to 5km
# by the next scheduled refresh, which is precisely the "correct data quietly
# replaced by worse data" failure this file already guards against elsewhere.
_OSM_RADIUS_OVERRIDES_M: dict[str, int] = {
    "bali": 30000,
    # Goa is a ~105km-long STATE, and pinning it to Panaji (its hub, which
    # `GEOCODE_QUERY_OVERRIDES` now does so the geocode stops depending on
    # Overpass being healthy) makes it *look* like a city to every size check —
    # Panaji's own bbox is a few km across. Declaring the extent here is what
    # tells the pipeline otherwise. Measured 2026-08-05 at the 5km default:
    # 5 North Goa POIs, ZERO from South Goa, and Baga + Vagator the only
    # recognisable beach names in all 60, with Agonda 52.6km and Palolem
    # 57.4km structurally unreachable.
    "goa": 55000,
}


# ── Large destinations are sampled from several centres, not one ─────────────
#
# A single centre plus a radius encodes an assumption that a destination is
# roughly disc-shaped and small. Measured on Goa (2026-08-05), which is a
# ~105km-long state: from Panaji at the default 5km radius the stored pool held
# 5 North Goa POIs and **zero** from South Goa, and the only recognisable beach
# names in all 60 were Baga and Vagator — Agonda (52.6km), Palolem (57.4km) and
# Colva (25.6km) were structurally unreachable, not out-ranked.
#
# Simply widening the circle does not fix it, and the measurement says so: at
# 60km Goa reached South Goa but also pulled POIs 83.7km out (past the state
# border entirely) and refilled 15 of 60 slots with train stations — the same
# category starvation `_prioritize_landmarks` exists to prevent, reappearing
# geographically. So the fix is more centres, not a bigger one.
#
# Centres come from OSM's own settlement data (services/geocode.py::
# area_centroids), so they are places a traveller would name — Panaji,
# Calangute, Margao, Palolem — rather than arbitrary grid points that can land
# in the sea. This matters beyond coverage: services/gems.py can only surface a
# hidden gem whose POI is in the pool, so an unreachable area's gems could
# never appear no matter how much community signal mentioned them.
#
# Cost is the binding constraint — every centre is two more Overpass passes, on
# a shared public instance we are already careful with — hence the low cap.
_MULTI_AREA_MIN_SPAN_KM = 40.0     # below this, one centre genuinely covers it
_MAX_AREA_CENTROIDS = 4            # incl. the primary centre; 4 => <= 8 passes
_MIN_KM_BETWEEN_CENTROIDS = 18.0   # keep samples from re-covering each other
_AREA_RADIUS_M = 15000


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt
    lat1, lon1, lat2, lon2 = map(radians, [a[0], a[1], b[0], b[1]])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def _bbox_span_km(bbox: tuple[float, float, float, float]) -> float:
    """Diagonal of the destination's bounding box — how big this place is."""
    south, north, west, east = bbox
    return _haversine_km((south, west), (north, east))


def _pick_spread_centroids(
    primary: tuple[float, float],
    towns: list[tuple[str, float, float]],
    bbox: tuple[float, float, float, float],
) -> list[tuple[str, float, float]]:
    """Choose up to `_MAX_AREA_CENTROIDS` well-separated sampling centres.

    `towns` arrives most-populous-first. Taking the top N by population alone
    would cluster: Goa's four biggest settlements are all within ~15km of
    Panaji, which is the very failure being fixed. So a town is only accepted
    when it is at least `_MIN_KM_BETWEEN_CENTROIDS` from every centre already
    chosen — population picks *which* places, distance picks *where*.
    """
    south, north, west, east = bbox
    chosen: list[tuple[str, float, float]] = [("", primary[0], primary[1])]
    for name, lat, lon in towns:
        if len(chosen) >= _MAX_AREA_CENTROIDS:
            break
        # Nominatim bboxes can be generous; a town outside it is not this
        # destination and would drag the pool across a border.
        if not (south <= lat <= north and west <= lon <= east):
            continue
        if all(_haversine_km((lat, lon), (c[1], c[2])) >= _MIN_KM_BETWEEN_CENTROIDS
               for c in chosen):
            chosen.append((name, lat, lon))
    return chosen


def _interleave_by_area(pools: list[list[dict]], cap: int) -> list[dict]:
    """Round-robin across AREAS, then truncate.

    `_prioritize_landmarks` already stops one *category* crowding out the rest.
    Sampling several centres reintroduces the identical starvation one
    dimension over: concatenating the pools and truncating would let the
    densest area (Panaji, or a city centre) fill the cap and leave the outer
    areas with nothing — which is the bug this whole change exists to fix.
    Each pool is pre-prioritised, so taking one at a time preserves that
    ranking within each area while guaranteeing every area is represented.
    """
    merged: list[dict] = []
    seen: set[str] = set()
    for tier in range(max((len(p) for p in pools), default=0)):
        for pool in pools:
            if tier >= len(pool):
                continue
            poi = pool[tier]
            key = (poi.get("name") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(poi)
            if len(merged) >= cap:
                return merged
    return merged


def _radius_override_for(destination: str) -> int | None:
    return _OSM_RADIUS_OVERRIDES_M.get(destination.strip().lower())


def _bbox_around(lat: float, lon: float, radius_m: int) -> tuple[float, float, float, float]:
    """A (south, north, west, east) box of `radius_m` around a point.

    Used when a destination's declared extent, not Nominatim's bbox, is what
    says how big it is — which is every destination pinned to its hub town,
    because the hub's own bbox describes the town and not the region.
    """
    from math import cos, radians
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(cos(radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def _is_thin_or_dominated(pois: list[dict]) -> bool:
    """True if `pois` would fail the data-completeness gate's OSM checks —
    too few POIs, or a single category crowding out the rest. Small towns/
    "hidden gem" destinations often have this happen at the default 5km
    radius even though a wider radius (still well within a single day-trip
    area) would round out the mix — see `ingest_osm_pois`'s expanded-radius
    retry."""
    if len(pois) < _MIN_POIS_BEFORE_RADIUS_EXPANSION:
        return True
    from collections import Counter

    counts = Counter(p["poi_type"] for p in pois)
    top_share = counts.most_common(1)[0][1] / len(pois)
    return top_share > _MAX_CATEGORY_SHARE_BEFORE_EXPANSION


async def ingest_osm_pois(destination: str) -> int:
    """Fetch and upsert POIs for `destination` into the osm_pois collection.

    Returns the number of POIs ingested. Safe to re-run — point IDs are a
    stable hash of (destination, name), so re-ingestion updates in place
    rather than duplicating.
    """
    override_radius = _radius_override_for(destination)
    if override_radius:
        logger.info(
            "%r: region-scale destination (declared extent %dm) — sampling several "
            "areas rather than widening the default %dm circle",
            destination, override_radius, settings.osm_poi_radius_m,
        )
    # Deliberately NOT passed as `radius_m`: the extent describes how far the
    # destination reaches, not how big one query should be. Handing it over as
    # a radius would rebuild the single oversized circle this replaces — which
    # measured worse, pulling POIs past Goa's border and refilling the pool
    # with train stations.
    pois, prominence_ok, geocode_degraded = await _fetch_osm_pois_with_meta(destination)
    # Thin/single-category-dominated results are common for small towns and
    # "hidden gem" destinations whose few landmark/nature POIs are spread
    # wider than the default 5km while restaurants cluster densely near the
    # centre point — live-confirmed 2026-07-23 (Coorg/Jaisalmer restaurant-
    # dominated, Spiti/Nainital thin). Retry once at a wider radius rather
    # than accepting a food/drink-only pool or an under-20 destination as
    # final; a wider-radius fetch is effectively a superset area so it's
    # never worse, only potentially the same.
    # The retry must never NARROW the search: for a destination already using a
    # region-scale override (30km for Bali), the 15km "expanded" radius is
    # smaller than what we just fetched, and re-fetching at it would quietly
    # drop the very landmarks the override exists to reach. Widen from
    # whatever radius actually ran, never from the city-shaped default.
    # A destination sampled across several areas has already searched far
    # wider than the expanded radius; re-fetching at 15km from one centre would
    # narrow it, and that is how the outer areas get lost again.
    expanded_radius = settings.osm_poi_radius_expanded_m
    if pois and _is_thin_or_dominated(pois) and not override_radius:
        expanded_pois, expanded_prominence_ok, _ = await _fetch_osm_pois_with_meta(
            destination, radius_m=expanded_radius
        )
        if expanded_pois and (len(expanded_pois) > len(pois) or not _is_thin_or_dominated(expanded_pois)):
            logger.info(
                "%r: %dm radius was thin/dominated (%d POIs), expanded to %dm radius (%d POIs)",
                destination, settings.osm_poi_radius_m,
                len(pois), expanded_radius, len(expanded_pois),
            )
            pois, prominence_ok = expanded_pois, expanded_prominence_ok
    if not pois:
        # A totally empty fetch (every mirror failed on both passes) is the
        # extreme case of "no prominence signal" and must be guarded the same
        # way as the checks below — otherwise it silently reports 0 while
        # good existing data survives untouched, which the reingestion
        # script's retry bookkeeping reads as permanent failure (it never
        # graduates a destination whose ingested count is 0, even after
        # exhausting its attempt budget). Report what's already there.
        existing_count = count_destination_points(
            get_qdrant(), settings.qdrant_collection_osm, destination
        )
        if existing_count:
            logger.warning(
                "%r: Overpass returned nothing on every pass/mirror — keeping the %d POIs "
                "already stored rather than reporting an empty result.",
                destination, existing_count,
            )
            return existing_count
        return 0

    # A broad-pass-only result looks perfectly healthy to every other check
    # here — right count, well-spread categories — while containing none of
    # the landmarks the destination is actually known for. Overwriting real
    # stored data with it would be a silent regression, so keep what's there
    # and let the caller retry. For a destination with nothing stored yet,
    # degraded data still beats no data, so this only guards overwrites.
    # 🔴 The geocode itself is unverified: this is a region centroid we wanted
    # to correct to its hub town but couldn't, because that correction is an
    # Overpass call and Overpass was throttling. The fetch will look perfectly
    # healthy — right count, well-spread categories, prominence pass fine — and
    # be centred tens of km from what the destination name means. Bali's 25
    # stored POIs sat 48km from Denpasar, in the wrong half of the island,
    # written by exactly this path (2026-08-05).
    #
    # Same contract as the prominence guard below: only ever protects an
    # OVERWRITE. With nothing stored yet, wrong-place data still beats no data
    # and the destination stays flagged for a later pass.
    if geocode_degraded:
        existing_count = count_destination_points(
            get_qdrant(), settings.qdrant_collection_osm, destination
        )
        if existing_count:
            logger.warning(
                "%r: geocode fell back to an unverified region centroid (hub-town "
                "lookup failed), so the %d fetched POIs may be for the wrong area — "
                "keeping the %d already stored rather than overwriting them.",
                destination, len(pois), existing_count,
            )
            return existing_count

    if not prominence_ok:
        existing_count = count_destination_points(
            get_qdrant(), settings.qdrant_collection_osm, destination
        )
        if existing_count:
            logger.warning(
                "%r: Overpass prominence pass failed, so the %d fetched POIs carry no landmark "
                "ranking — keeping the %d POIs already stored rather than overwriting them.",
                destination, len(pois), existing_count,
            )
            return existing_count

    # A non-empty but severely degraded fetch (e.g. Overpass silently
    # returning a near-empty/truncated result after exhausting retries,
    # rather than raising) is worse than doing nothing if it would delete an
    # existing, substantially larger dataset — live-confirmed 2026-07-23:
    # Las Vegas/Tulum each had 60 good POIs replaced by a single restaurant
    # POI during a busy retry batch. Only refuse the overwrite when the new
    # result is still thin/dominated even after the radius-expansion retry
    # above, and strictly worse than what's already there.
    if _is_thin_or_dominated(pois):
        client = get_qdrant()
        existing_count = count_destination_points(client, "osm_pois", destination)
        if existing_count > len(pois):
            logger.warning(
                "%r: new OSM fetch is thin/dominated (%d POIs) and worse than the %d POIs already "
                "stored — keeping existing data instead of overwriting it.",
                destination, len(pois), existing_count,
            )
            return existing_count

    from qdrant_client.models import PointStruct

    texts = [p["text"] for p in pois]
    # Offload the CPU-bound embed() call to a worker thread — this coroutine
    # runs on the scheduler's event loop and must not block other requests.
    vectors = await asyncio.to_thread(embed, texts)

    points = []
    new_ids: set[int] = set()
    for poi, vec in zip(pois, vectors):
        point_id = hashlib.md5(f"{poi['destination']}::{poi['name']}".encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        new_ids.add(point_id_int)
        points.append(PointStruct(id=point_id_int, vector=vec, payload=poi))

    client = get_qdrant()
    # Delete-then-upsert per destination — see delete_stale_destination_points'
    # docstring for why this matters (orphaned points from prior
    # category-selection logic otherwise accumulate forever).
    stale_count = delete_stale_destination_points(client, settings.qdrant_collection_osm, destination, new_ids)
    if stale_count:
        logger.info("Deleted %d stale OSM points for %r before re-ingestion", stale_count, destination)
    client.upsert(collection_name=settings.qdrant_collection_osm, points=points)
    return len(points)
