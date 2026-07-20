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

logger = logging.getLogger(__name__)

BASE_URL = "https://en.wikivoyage.org/wiki/{destination}"
SECTIONS_OF_INTEREST = {"go", "stay_safe", "see", "do", "eat", "drink", "sleep", "understand"}

# Same rationale as scrapers/osm.py — wikivoyage.org occasionally returns
# transient failures (rate-limiting, brief 5xx) that resolve on their own
# within seconds; retry with backoff instead of silently recording a
# destination as having zero wiki chunks.
_MAX_FETCH_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 5.0


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


async def scrape_wikivoyage(destination: str) -> list[dict]:
    url = BASE_URL.format(destination=destination.replace(" ", "_").title())
    # Wikimedia's API etiquette asks for an identifiable User-Agent on every
    # request; some network paths in front of wikivoyage.org also reject
    # requests missing one with a bare 403.
    headers = {"User-Agent": settings.nominatim_user_agent}
    resp: httpx.Response | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            try:
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

    soup = BeautifulSoup(resp.text, "lxml")
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
