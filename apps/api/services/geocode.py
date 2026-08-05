"""Nominatim geocoding proxy with 1 req/s rate limiting and LRU cache.

Also owns a small *generic* disambiguation pipeline that runs automatically
for every `geocode_city()` call, so it benefits real-time chat/RAG lookups
and batch ingestion alike (not just the destinations we've manually hit
bugs for so far):

1. **Not found at all / misspelling** -> cross-check against Wikipedia's own
   fuzzy full-text search (typo/redirect tolerant) and use the coordinates
   of whatever page it resolves to.
2. **Resolves to a country/region, not a settlement** (`is_country`-style
   hit) -> look up the largest actual town/city inside that region's
   bounding box via Overpass, and re-geocode using that hub town.
3. **Resolves to *a* real place, but likely the wrong one** (low-prominence
   hit, e.g. an obscure same-named village in another country entirely) ->
   cross-check against Wikipedia's article for the query and, if it points
   to a different country, prefer that.

`GEOCODE_QUERY_OVERRIDES` remains as a fast-path escape hatch for specific
cases worth hard-pinning (no extra network round-trip, or where the
automatic pipeline still isn't enough) — but new destination-name bugs
should generally self-heal via the pipeline above instead of needing a new
manual entry.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

import httpx

from core.config import settings
from models.common import GeocodeResponse

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_last_call = 0.0

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

# A hit is "low prominence" enough to be worth a second opinion when its
# Nominatim `importance` score (roughly: how well-linked/notable the OSM
# entry is) is below this, or when it's a village/hamlet-class settlement —
# small enough that an identically-named place elsewhere is plausible.
_LOW_IMPORTANCE_THRESHOLD = 0.3
_SMALL_SETTLEMENT_TYPES = {"village", "hamlet", "isolated_dwelling"}
_MAX_HUB_TOWN_BBOX_DEGREES = 6.0

# Manual pins kept as a fast-path / belt-and-suspenders escape hatch for a
# handful of cases already diagnosed by hand. The automatic pipeline in
# geocode_city() below (Wikipedia cross-check + Overpass hub-town lookup)
# is what should catch *new* cases of this bug class going forward.
GEOCODE_QUERY_OVERRIDES: dict[str, str] = {
    "ladakh": "Leh",
    "spiti": "Kaza",
    "andaman": "Port Blair",
    "coorg": "Madikeri",
    "maldives": "Male, Maldives",
    "fiji": "Nadi",
    "hawaii": "Honolulu",
    # Same island-without-a-hub shape as Andaman/Maldives/Fiji/Hawaii above,
    # but it reached us as an intermittent bug rather than an obviously-wrong
    # name: a bare "Bali" query returns the ISLAND centroid (-8.227, 115.192),
    # 49km north of Denpasar and 44-67km from every landmark a traveller means
    # by "Bali" (Tanah Lot, Uluwatu, Kuta, Ubud). geocode_city's automatic
    # hub-town lookup normally corrects this to Denpasar — but that lookup is
    # an Overpass call, so when Overpass throttles it silently falls back to
    # the raw centroid and ingestion lands in Buleleng/Bedugul on the north
    # coast instead. Live-confirmed 2026-08-05: the lookup returned 429 then
    # 504 on consecutive attempts while succeeding earlier the same day, and
    # the 25 POIs stored in production (centroid -8.235, 115.161 — 'Gado
    # gado', 'Pura Desa Panji', 'Monumen Panji Sakti') sit 3km from the
    # fallback centroid, i.e. they were written by exactly such a run.
    # Pinning the hub makes ingestion deterministic regardless of Overpass
    # health; the automatic path stays as the general fix for new cases.
    "bali": "Denpasar, Indonesia",
    # Genuine same-name ambiguity between two real, comparably prominent
    # cities (Cartagena, Colombia vs Cartagena, Spain) that no generic
    # heuristic can resolve on names alone — Nominatim's bare-query top hit
    # happens to be Spain, but this destination catalog groups "Cartagena"
    # alongside Bogotá/Medellín/Lima/Cusco (see scrapers/reddit.py), i.e. it
    # means Colombia. Live-confirmed 2026-07-23.
    "cartagena": "Cartagena, Colombia",
    # "La Paz" bare-queries to La Paz, Baja California Sur, Mexico — a real
    # city, so neither the importance nor the Wikipedia country cross-check
    # flags it — but the catalog groups "La Paz" with Santiago/Montevideo/
    # Cusco (South America), i.e. it means the Bolivian seat of government.
    # Same class as Cartagena. Live-confirmed 2026-07-23.
    "la paz": "La Paz, Bolivia",
    # "Austin" bare-queries to Austin, Nevada — a ~150-person former mining
    # town — instead of Austin, Texas. Both are in the US, so the Wikipedia
    # country cross-check can't correct it; a same-country namesake collision
    # only the qualifier resolves. Live-confirmed 2026-07-23 (was silently
    # ingesting 3 OSM POIs for the Nevada ghost town).
    "austin": "Austin, Texas",
    # "Valencia" bare-queries to Valencia, Venezuela, but the catalog groups
    # it with Seville/Granada/Nice/Lyon (see scrapers/reddit.py), i.e. it
    # means Valencia, Spain. Both are real cities of comparable prominence,
    # so no importance/country heuristic disambiguates. Live-confirmed
    # 2026-07-23 (was silently ingesting 60 POIs for the Venezuelan city).
    "valencia": "Valencia, Spain",
    # Found by scripts/audit_poi_geocode.py, 2026-08-05, and the audit caught
    # them the *opposite* way round from the bug it was written for: the STORED
    # POIs are correct (Medellín, Colombia and Amalfi, Italy) and the live
    # geocode is what drifted — a bare "Medellin" now resolves to a municipality
    # in the PHILIPPINES 17,113km away, and a bare "Amalfi" to a town in
    # COLOMBIA 9,480km from the Italian coast. Both are real places, so neither
    # the importance nor the Wikipedia country cross-check flags them; same
    # class as Cartagena/La Paz/Austin/Valencia above.
    #
    # ⚠️ Without these pins, the next scheduled refresh would have quietly
    # replaced two correct 60-POI pools with data for the wrong continent —
    # and every existing guard would have let it, because the fetch looks
    # perfectly healthy. The unaccented "Medellin" spelling is what the
    # catalogue uses, so pinning the accented, country-qualified form is what
    # makes it deterministic.
    "medellin": "Medellín, Colombia",
    "amalfi": "Amalfi, Italy",
    # The one destination the same audit found genuinely mis-ingested, and a
    # confirmed casualty of the throttle bug rather than a name collision: a
    # bare "Sri Lanka" is a country, so the hub-town lookup is what turns it
    # into Colombo — and that lookup 504'd on every attempt on 2026-08-05. Its
    # 60 stored POIs sat 112km away around Matale, the island's geographic
    # centre, and were obscure rural sites (Koholanwela Temple, Wedda peni
    # ella, Karagahatenna Transmission Station) rather than anything a
    # traveller means by "Sri Lanka". Same country-name shape as Maldives and
    # Fiji above; pinning the hub makes it deterministic instead of dependent
    # on Overpass being healthy at that moment.
    "sri lanka": "Colombo, Sri Lanka",
    # Goa is a state, so a bare query returns its administrative centroid and
    # the hub-town lookup is what turns it into Panaji — and that lookup 504'd
    # repeatedly on 2026-08-05, leaving an inland centroid that fetched 24 POIs
    # with ZERO from North Goa and not one recognisable beach name. Pinned for
    # determinism; the state's real 105km extent is declared separately in
    # scrapers/osm.py::_OSM_RADIUS_OVERRIDES_M, because a hub pin necessarily
    # makes a region look town-sized to every automatic size check.
    "goa": "Panaji, Goa, India",
}


@lru_cache(maxsize=512)
def _cached_geocode(city: str, lang: str = "en") -> dict | None:
    return None


def _pick_best_hit(hits: list[dict]) -> dict:
    """Nominatim's top hit for a well-known town name is sometimes the
    *district/tehsil-level administrative boundary* it sits in rather than
    the town itself — e.g. "Nainital" and "Jaisalmer" both return their
    encompassing district (`class=boundary, type=administrative`) as hit #1,
    whose centroid is many km from the actual town, before a `class=place`
    city/town/village hit for the real place. Requesting more than one
    result and preferring the first genuine place-level hit (falling back to
    hit #1 if no place-level hit is present, e.g. a country search) fixes the
    resulting Overpass OSM-zero without needing a per-destination override —
    live-confirmed 2026-07-23."""
    for hit in hits:
        if hit.get("class") == "place" and hit.get("type") in ("city", "town", "village"):
            return hit
    return hits[0]


def _is_country_like(hit: dict) -> bool:
    address = hit.get("address", {})
    return (
        not address.get("city")
        and not address.get("town")
        and not address.get("village")
        and not address.get("municipality")
        and bool(address.get("country"))
    )


def _needs_second_opinion(hit: dict) -> bool:
    """Flags a hit as worth cross-checking against an independent source
    before trusting it:
    - it's suspiciously obscure (low Nominatim `importance`), or
    - it's a settlement small enough that a same-named place elsewhere is
      plausible (e.g. bare "Cappadocia" resolving to a village in Italy
      rather than the famous region in Turkey — its Nominatim importance
      was ~0.15 and it's `type=village`; live-confirmed 2026-07-23), or
    - `_pick_best_hit` couldn't find any genuine `class=place` hit at all
      and had to fall back to an administrative boundary — e.g. "Patagonia"
      (the famous South American region) has *no* place-level Nominatim hit
      in its top candidates at all, only administrative boundaries in
      Argentina/Chile/Colombia/US, so the naive top hit (an Arizona town,
      importance ~0.38 — above the plain importance threshold) would
      otherwise slip through uncorrected; live-confirmed 2026-07-23."""
    try:
        importance = float(hit.get("importance", 1.0))
    except (TypeError, ValueError):
        importance = 1.0
    return (
        importance < _LOW_IMPORTANCE_THRESHOLD
        or hit.get("type") in _SMALL_SETTLEMENT_TYPES
        or hit.get("class") != "place"
    )


async def _rate_limited_get(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    """All Nominatim endpoints (search + reverse) share the same 1 req/s
    usage-policy budget, so both go through this single limiter."""
    global _last_call
    async with _lock:
        now = asyncio.get_event_loop().time()
        wait = (1.0 / settings.nominatim_rate_limit) - (now - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = asyncio.get_event_loop().time()
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp


async def _nominatim_search(client: httpx.AsyncClient, query: str, countrycodes: str = "") -> list[dict]:
    params = {
        "q": query,
        "format": "json",
        "limit": 5,  # >1 so _pick_best_hit can skip a district-level boundary hit
        "addressdetails": 1,
        "namedetails": 1,
    }
    if countrycodes:
        params["countrycodes"] = countrycodes
    resp = await _rate_limited_get(client, NOMINATIM_SEARCH_URL, params)
    return resp.json()


async def _reverse_geocode(client: httpx.AsyncClient, lat: float, lon: float) -> dict | None:
    params = {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1, "namedetails": 1, "zoom": 14}
    try:
        resp = await _rate_limited_get(client, NOMINATIM_REVERSE_URL, params)
        data = resp.json()
    except Exception as e:
        logger.warning("Reverse geocode failed for (%s, %s): %s", lat, lon, e)
        return None
    if not data or "error" in data:
        return None
    return data


async def _wikipedia_disambiguate(client: httpx.AsyncClient, query: str) -> tuple[float, float, str] | None:
    """Cross-checks `query` against Wikipedia's fuzzy full-text search (which
    tolerates typos/alternate spellings/transliterations via its own ranking
    and redirects far better than a raw Nominatim string match) and returns
    the resolved article's coordinates. Used both when Nominatim finds
    nothing at all, and as a second opinion when Nominatim's top hit looks
    suspicious (see `_needs_second_opinion`)."""
    try:
        search_resp = await client.get(
            WIKIPEDIA_API_URL,
            params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1},
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("query", {}).get("search", [])
        if not results:
            return None
        title = results[0]["title"]

        coord_resp = await client.get(
            WIKIPEDIA_API_URL,
            params={"action": "query", "prop": "coordinates", "titles": title, "format": "json"},
        )
        coord_resp.raise_for_status()
        pages = coord_resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            coords = page.get("coordinates")
            if coords:
                return float(coords[0]["lat"]), float(coords[0]["lon"]), title
        return None
    except Exception as e:
        logger.warning("Wikipedia disambiguation lookup failed for %r: %s", query, e)
        return None


async def _towns_in_bbox(
    client: httpx.AsyncClient, bbox: list[str], limit: int = 30
) -> tuple[list[tuple[str, float, float]], bool]:
    """The settlements inside `bbox`, most populous first, as (name, lat, lon).

    Shared by two callers with different needs, which is why it returns a list
    rather than one answer: `_hub_town_in_bbox` wants the single biggest town
    (to correct a region name to its hub), while `scrapers/osm.py` wants
    several (to sample a large destination from more than one centre — a
    105km-long state has no single point that reaches its far end).

    Same `(value, degraded)` contract as everything else on this path:
    `degraded` is True only when Overpass errored, never when it answered that
    there is nothing here.
    """
    try:
        south, north, west, east = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return [], False
    if (north - south) > _MAX_HUB_TOWN_BBOX_DEGREES or (east - west) > _MAX_HUB_TOWN_BBOX_DEGREES:
        # A deliberate decision not to ask, not a failure to get an answer.
        return [], False
    query = f"""
[out:json][timeout:20];
(
  node["place"~"^(city|town)$"]({south},{west},{north},{east});
);
out body {limit};
""".strip()
    try:
        resp = await client.post(settings.osm_overpass_url, data={"data": query}, timeout=25)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception as e:
        logger.warning(
            "Hub-town Overpass lookup FAILED for bbox %s (%s) — the region centroid "
            "is now unverified; anything ingested against it may be in the wrong "
            "place. See GeocodeResponse.hub_lookup_degraded.",
            bbox, e,
        )
        return [], True
    if not elements:
        return [], False

    def _pop(el: dict) -> int:
        try:
            return int(el.get("tags", {}).get("population", 0))
        except (TypeError, ValueError):
            return 0

    elements.sort(key=lambda el: (_pop(el), el.get("tags", {}).get("place") == "city"), reverse=True)
    towns: list[tuple[str, float, float]] = []
    for el in elements:
        name = el.get("tags", {}).get("name")
        lat, lon = el.get("lat"), el.get("lon")
        if name and lat is not None and lon is not None:
            towns.append((name, float(lat), float(lon)))
    return towns, False


async def _hub_town_in_bbox(
    client: httpx.AsyncClient, bbox: list[str]
) -> tuple[str | None, bool]:
    """The single most populous town inside `bbox`, for correcting a region
    name to the hub travellers actually base themselves in (e.g. "Ladakh" ->
    Leh). Thin wrapper over `_towns_in_bbox`; see it for the `degraded` half.
    """
    towns, degraded = await _towns_in_bbox(client, bbox)
    return (towns[0][0] if towns else None), degraded


async def area_centroids(bbox: list[str], limit: int) -> list[tuple[str, float, float]]:
    """Public entry point for sampling a large destination from several
    centres. Best-effort: any failure returns an empty list, and the caller
    falls back to single-centre behaviour rather than ingesting nothing.
    """
    headers = {"User-Agent": settings.nominatim_user_agent, "Accept-Language": "en"}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        towns, _ = await _towns_in_bbox(client, bbox, limit=max(limit * 4, 30))
    return towns


def _parse_bbox(raw: object) -> tuple[float, float, float, float] | None:
    """Nominatim's `boundingbox` is [south, north, west, east] as strings."""
    if not isinstance(raw, list | tuple) or len(raw) != 4:
        return None
    try:
        south, north, west, east = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    return south, north, west, east


def _hit_to_response(hit: dict, fallback_name: str, is_country: bool | None = None) -> GeocodeResponse:
    namedetails = hit.get("namedetails", {})
    address = hit.get("address", {})
    english_name = (
        namedetails.get("name:en")
        or address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or hit.get("display_name", fallback_name).split(",")[0].strip()
    )
    country = address.get("country", "")
    clean_display = f"{english_name}, {country}".strip(", ") if country else english_name
    return GeocodeResponse(
        display_name=clean_display,
        lat=float(hit.get("lat", 0)),
        lon=float(hit.get("lon", 0)),
        country_code=address.get("country_code", ""),
        is_country=_is_country_like(hit) if is_country is None else is_country,
        bbox=_parse_bbox(hit.get("boundingbox")),
    )


async def geocode_city(city: str, countrycodes: str = "") -> GeocodeResponse:
    query_city = GEOCODE_QUERY_OVERRIDES.get(city.strip().lower(), city)
    headers = {
        "User-Agent": settings.nominatim_user_agent,
        "Accept-Language": "en",  # force English names from Nominatim
    }

    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        data = await _nominatim_search(client, query_city, countrycodes)

        if not data:
            # Nothing at all — try Wikipedia's fuzzy search before giving
            # up; it handles typos/alternate spellings via its own ranking
            # and redirects.
            wiki_hit = await _wikipedia_disambiguate(client, city)
            if wiki_hit is None:
                raise ValueError(f"Location not found: {city}")
            lat, lon, title = wiki_hit
            reverse_hit = await _reverse_geocode(client, lat, lon)
            if reverse_hit is None:
                raise ValueError(f"Location not found: {city}")
            return _hit_to_response(reverse_hit, title)

        hit = _pick_best_hit(data)

        if _is_country_like(hit):
            # Resolves to a country/region, not a settlement — find the real
            # hub town inside it instead of trusting the region's centroid.
            hub_name, hub_degraded = await _hub_town_in_bbox(client, hit.get("boundingbox", []))
            if hub_name:
                country = hit.get("address", {}).get("country", "")
                requery = f"{hub_name}, {country}" if country else hub_name
                hub_data = await _nominatim_search(client, requery, countrycodes)
                if hub_data:
                    return _hit_to_response(_pick_best_hit(hub_data), city, is_country=False)
            # No hub town found (or re-query failed) — fall back to the
            # region-level hit as before rather than erroring out, but say so
            # when the reason was a failed lookup rather than a real absence.
            # A caller that persists data keyed on these coordinates must not
            # treat the two the same (scrapers/osm.py::ingest_osm_pois).
            if hub_degraded:
                logger.warning(
                    "Geocode for %r fell back to the region centroid (%s) because the "
                    "hub-town lookup failed, not because there is no hub.",
                    city, hit.get("display_name", ""),
                )
            response = _hit_to_response(hit, city, is_country=True)
            response.hub_lookup_degraded = hub_degraded
            return response

        if _needs_second_opinion(hit):
            wiki_hit = await _wikipedia_disambiguate(client, city)
            if wiki_hit is not None:
                lat, lon, title = wiki_hit
                reverse_hit = await _reverse_geocode(client, lat, lon)
                if reverse_hit is not None:
                    original_country = hit.get("address", {}).get("country_code")
                    corrected_country = reverse_hit.get("address", {}).get("country_code")
                    if corrected_country and corrected_country != original_country:
                        logger.warning(
                            "Correcting low-confidence geocode for %r: Nominatim's top hit was in "
                            "%r (importance=%s), but Wikipedia's %r article is in %r — using the "
                            "Wikipedia-anchored location instead.",
                            city, original_country, hit.get("importance"), title, corrected_country,
                        )
                        return _hit_to_response(reverse_hit, city)

        return _hit_to_response(hit, city)
