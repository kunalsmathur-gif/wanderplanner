from __future__ import annotations
"""Wikivoyage scraper — extracts destination guide sections."""
import hashlib
import re
import httpx
from bs4 import BeautifulSoup

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed

BASE_URL = "https://en.wikivoyage.org/wiki/{destination}"
SECTIONS_OF_INTEREST = {"go", "stay_safe", "see", "do", "eat", "drink", "sleep", "understand"}


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
            docs.append({
                "destination": destination,
                "source": "wikivoyage",
                "section": section_id,
                "text": " ".join(texts)[:1500],
                "source_url": url,
            })
    return docs


async def ingest_wikivoyage(destination: str):
    docs = await scrape_wikivoyage(destination)
    if not docs:
        return

    texts = [d["text"] for d in docs]
    vectors = embed(texts)

    client = get_qdrant()
    from qdrant_client.models import PointStruct

    points = []
    for doc, vec in zip(docs, vectors):
        point_id = hashlib.md5(f"{doc['source_url']}{doc['section']}".encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        points.append(PointStruct(
            id=point_id_int,
            vector=vec,
            payload=doc,
        ))

    client.upsert(collection_name=settings.qdrant_collection_wiki, points=points)
