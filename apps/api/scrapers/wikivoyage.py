from __future__ import annotations
"""Wikivoyage scraper — extracts destination guide sections."""
import asyncio
import hashlib
import re
import httpx
from bs4 import BeautifulSoup

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed

BASE_URL = "https://en.wikivoyage.org/wiki/{destination}"
SECTIONS_OF_INTEREST = {"go", "stay_safe", "see", "do", "eat", "drink", "sleep", "understand"}


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
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception:
            return []

    soup = BeautifulSoup(resp.text, "lxml")
    docs = []
    for h2 in soup.find_all("h2"):
        section_id = h2.get("id", "").lower().replace(" ", "_")
        if not any(s in section_id for s in SECTIONS_OF_INTEREST):
            continue
        texts = []
        for sib in h2.find_next_siblings():
            if sib.name == "h2":
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


async def ingest_wikivoyage(destination: str):
    docs = await scrape_wikivoyage(destination)
    if not docs:
        return

    texts = [d["text"] for d in docs]
    # Offload the CPU-bound embed() call to a worker thread — this coroutine
    # runs on the scheduler's event loop and must not block other requests.
    vectors = await asyncio.to_thread(embed, texts)

    client = get_qdrant()
    from qdrant_client.models import PointStruct

    points = []
    for doc, vec in zip(docs, vectors):
        # Include chunk text in the hash so each sub-chunk gets a unique point ID
        point_id = hashlib.md5(f"{doc['source_url']}{doc['section']}{doc['text'][:50]}".encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        points.append(PointStruct(
            id=point_id_int,
            vector=vec,
            payload=doc,
        ))

    client.upsert(collection_name=settings.qdrant_collection_wiki, points=points)
