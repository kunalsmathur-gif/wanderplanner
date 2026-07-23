from __future__ import annotations

"""Wikivoyage scraper — extracts destination guide sections."""
import asyncio
import hashlib
import logging
import re

import httpx
from bs4 import BeautifulSoup

from core.config import settings
from core.embeddings import embed
from core.qdrant import delete_stale_destination_points, get_qdrant
from services.geocode import geocode_city

logger = logging.getLogger(__name__)

BASE_URL = "https://en.wikivoyage.org/wiki/{destination}"
WIKIVOYAGE_API_URL = "https://en.wikivoyage.org/w/api.php"
SECTIONS_OF_INTEREST = {"go", "stay_safe", "see", "do", "eat", "drink", "sleep", "understand"}

# Manual pin kept for a case already diagnosed by hand where the naive slug
# resolves (200 OK) to a real but structurally different page (a region
# index, not the city guide) — `_resolve_disambiguation` below only handles
# genuine MediaWiki disambiguation pages (`pageprops.disambiguation` set),
# which this isn't, so it still needs a manual pin.
WIKIVOYAGE_TITLE_OVERRIDES: dict[str, str] = {
    "new york": "New_York_City",
}

# Same rationale as scrapers/osm.py — wikivoyage.org occasionally returns
# transient failures (rate-limiting, brief 5xx) that resolve on their own
# within seconds; retry with backoff instead of silently recording a
# destination as having zero wiki chunks.
_MAX_FETCH_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 5.0

# Qualifiers used on Wikivoyage disambiguation pages that denote an
# administrative region rather than a specific city/settlement — e.g.
# "Oaxaca (state)" vs "Oaxaca (city)". Deprioritized in favor of the actual
# city/settlement guide, which is what an itinerary destination means.
_REGION_QUALIFIERS = {"state", "region", "province", "department", "county", "prefecture", "oblast", "canton", "district"}


def _sentence_boundary_chunks(text: str, max_chars: int = 500) -> list[str]:
    """Split text at sentence boundaries, targeting ~500 chars per chunk for better retrieval precision."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if len(c) > 80]


async def _wikivoyage_search_title(client: httpx.AsyncClient, query: str) -> str | None:
    """Wikivoyage's own fuzzy full-text search — used generically whenever
    the naive `.title()` slug 404s (e.g. "Washington DC" -> "Washington_Dc",
    "Rio de Janeiro" -> "Rio_De_Janeiro" — Python's `.title()` mis-cases
    "DC" and "de" — live-confirmed 2026-07-23) instead of hand-adding a
    title override for every such casing mismatch."""
    try:
        resp = await client.get(
            WIKIVOYAGE_API_URL,
            params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1},
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else None
    except Exception as e:
        logger.warning("Wikivoyage search fallback failed for %r: %s", query, e)
        return None


async def _resolve_disambiguation(client: httpx.AsyncClient, title: str, destination: str) -> str | None:
    """Some destination names are genuine Wikivoyage disambiguation pages
    (`pageprops.disambiguation` set) rather than a single city guide — e.g.
    "Queenstown" (New Zealand vs South Africa vs...), "Oaxaca" (city vs
    state), "Cartagena" (Colombia vs Spain) — live-confirmed 2026-07-23,
    these silently returned zero chunks the same way New York's state page
    did. Rather than hand-pin every ambiguous name, geocode the destination
    (already-known country, e.g. "Colombia" for "Cartagena") and match it
    against the disambiguation page's own "Name (Country)"-style links to
    pick the right one generically."""
    try:
        resp = await client.get(
            WIKIVOYAGE_API_URL,
            params={"action": "query", "prop": "pageprops", "titles": title, "format": "json"},
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        is_disambiguation = any("disambiguation" in p.get("pageprops", {}) for p in pages.values())
        if not is_disambiguation:
            return None
    except Exception as e:
        logger.warning("Wikivoyage disambiguation check failed for %r: %s", title, e)
        return None

    try:
        page_resp = await client.get(BASE_URL.format(destination=title.replace(" ", "_")))
        page_resp.raise_for_status()
        soup = BeautifulSoup(page_resp.text, "lxml")
        content = soup.select_one("#mw-content-text")
        candidates = [
            (a.get_text(strip=True), a["href"].rsplit("/", 1)[-1])
            for a in (content.select("a") if content else [])
            if re.match(rf"^{re.escape(title)} \(.+\)$", a.get_text(strip=True))
        ]
    except Exception as e:
        logger.warning("Wikivoyage disambiguation page parse failed for %r: %s", title, e)
        return None
    if not candidates:
        return None

    try:
        geo = await geocode_city(destination)
        country = geo.display_name.rsplit(",", 1)[-1].strip().lower()
    except Exception:
        country = ""

    matches = [c for c in candidates if country and country in c[0].lower()]
    if not matches:
        matches = candidates
    # Some disambiguation pages qualify by administrative level rather than
    # country when the ambiguity is *within* one country — e.g. "Oaxaca
    # (state)" vs "Oaxaca (city)", both under "Mexico" — so a country match
    # alone can't break the tie. A destination-guide itinerary is about a
    # specific city, not the region it sits in (same rationale as the New
    # York state-vs-city override), so prefer a non-region-level candidate
    # among whatever the country filter left; live-confirmed 2026-07-23.
    non_region = [c for c in matches if c[0].split("(")[-1].rstrip(")").strip().lower() not in _REGION_QUALIFIERS]
    return (non_region or matches)[0][1]


def _parse_sections(html: str, destination: str, url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    docs = []
    for h2 in soup.find_all("h2"):
        section_id = h2.get("id", "").lower().replace(" ", "_")
        if not any(s in section_id for s in SECTIONS_OF_INTEREST):
            continue
        # MediaWiki's newer skin wraps each heading in a
        # `<div class="mw-heading">` rather than leaving <h2> as a direct
        # sibling of the section content, so section content are actually
        # siblings of that wrapper div, not of the <h2> itself. Fall back to
        # the <h2> when the wrapper isn't present (older markup / other
        # skins) so both layouts are handled.
        heading_wrapper = h2.parent
        if heading_wrapper is None or "mw-heading" not in (heading_wrapper.get("class") or []):
            heading_wrapper = h2
        texts = []
        for sib in heading_wrapper.find_next_siblings():
            if sib.name == "h2":
                break
            if sib.name == "div" and "mw-heading" in (sib.get("class") or []):
                break
            if sib.name in ("p", "ul", "li"):
                texts.append(sib.get_text(" ", strip=True))
        if texts:
            full_text = " ".join(texts)
            for chunk in _sentence_boundary_chunks(full_text, max_chars=500):
                docs.append({
                    "destination": destination,
                    "source": "wikivoyage",
                    "section": section_id,
                    "text": chunk,
                    "source_url": url,
                })
    return docs


async def scrape_wikivoyage(destination: str) -> list[dict]:
    slug = WIKIVOYAGE_TITLE_OVERRIDES.get(destination.strip().lower()) or destination.replace(" ", "_").title()
    url = BASE_URL.format(destination=slug)
    # Wikimedia's API etiquette asks for an identifiable User-Agent on every
    # request; some network paths in front of wikivoyage.org also reject
    # requests missing one with a bare 403.
    headers = {"User-Agent": settings.nominatim_user_agent}
    resp: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    # Naive `.title()` slug 404s — e.g. "Washington DC" ->
                    # "Washington_Dc", "Rio de Janeiro" -> "Rio_De_Janeiro"
                    # (Python's `.title()` mis-cases "DC"/"de") — fall back
                    # to Wikivoyage's own fuzzy search instead of hand-adding
                    # a title override for every such casing mismatch;
                    # live-confirmed 2026-07-23.
                    fallback_title = await _wikivoyage_search_title(client, destination)
                    if fallback_title:
                        slug = fallback_title.replace(" ", "_")
                        url = BASE_URL.format(destination=slug)
                        resp = await client.get(url)
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Wikivoyage fetch failed for %r after %d attempts: %s", destination, attempt, e
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)
                continue

        docs = _parse_sections(resp.text, destination, url)
        if docs:
            return docs

        # Zero usable chunks despite a 200 — worth the extra round-trip to
        # check whether this is actually a Wikivoyage disambiguation page
        # (see `_resolve_disambiguation`) before giving up.
        disambiguated_slug = await _resolve_disambiguation(client, slug.replace("_", " "), destination)
        if not disambiguated_slug:
            return docs
        slug = disambiguated_slug
        url = f"https://en.wikivoyage.org/wiki/{slug}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Wikivoyage disambiguated fetch failed for %r -> %r: %s", destination, slug, e)
            return docs
        return _parse_sections(resp.text, destination, url)


async def ingest_wikivoyage(destination: str) -> int:
    """Fetch and upsert wiki chunks for `destination`. Returns the number of
    chunks ingested. Safe to re-run — stale points from prior scrapes are
    deleted before the new ones are upserted (see
    core.qdrant.delete_stale_destination_points)."""
    docs = await scrape_wikivoyage(destination)
    if not docs:
        return 0

    texts = [d["text"] for d in docs]
    # Offload the CPU-bound embed() call to a worker thread — this coroutine
    # runs on the scheduler's event loop and must not block other requests.
    vectors = await asyncio.to_thread(embed, texts)

    client = get_qdrant()
    from qdrant_client.models import PointStruct

    points = []
    new_ids: set[int] = set()
    for doc, vec in zip(docs, vectors):
        # Include chunk text in the hash so each sub-chunk gets a unique point ID
        point_id = hashlib.md5(f"{doc['source_url']}{doc['section']}{doc['text'][:50]}".encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        new_ids.add(point_id_int)
        points.append(PointStruct(
            id=point_id_int,
            vector=vec,
            payload=doc,
        ))

    stale_count = delete_stale_destination_points(client, settings.qdrant_collection_wiki, destination, new_ids)
    if stale_count:
        logger.info("Deleted %d stale wiki points for %r before re-ingestion", stale_count, destination)
    client.upsert(collection_name=settings.qdrant_collection_wiki, points=points)
    return len(points)
