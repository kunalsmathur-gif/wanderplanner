"""Reddit public JSON feed ingester — no API key required."""
from __future__ import annotations

import hashlib
import httpx
from better_profanity import profanity

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed

SUBREDDITS = ["travel", "solotravel", "digitalnomad", "backpacking"]
FEED_URL = "https://www.reddit.com/r/{sub}/top.json?limit=50&t=month"

profanity.load_censor_words()


def _is_safe(text: str) -> bool:
    return not profanity.contains_profanity(text)


def _extract_destination(title: str, selftext: str) -> str:
    """Very naive extraction — real impl would use NER."""
    return "general"


async def ingest_reddit():
    headers = {"User-Agent": settings.nominatim_user_agent}
    client_qdrant = get_qdrant()

    async with httpx.AsyncClient(timeout=15, headers=headers) as http:
        for sub in SUBREDDITS:
            try:
                resp = await http.get(FEED_URL.format(sub=sub))
                resp.raise_for_status()
                posts = resp.json().get("data", {}).get("children", [])
            except Exception:
                continue

            docs = []
            for post in posts:
                data = post.get("data", {})
                if data.get("score", 0) < settings.reddit_min_score:
                    continue
                title = data.get("title", "")
                selftext = data.get("selftext", "")[:800]
                full_text = f"{title}. {selftext}".strip()
                if not _is_safe(full_text):
                    continue
                docs.append({
                    "destination": _extract_destination(title, selftext),
                    "source": "reddit",
                    "subreddit": sub,
                    "title": title,
                    "text": full_text,
                    "text_preview": full_text[:300],
                    "post_url": f"https://reddit.com{data.get('permalink', '')}",
                    "score": data.get("score", 0),
                })

            if not docs:
                continue

            vectors = embed([d["text"] for d in docs])
            from qdrant_client.models import PointStruct
            points = []
            for doc, vec in zip(docs, vectors):
                pid = int(hashlib.md5(doc["post_url"].encode()).hexdigest(), 16) % (2**63)
                points.append(PointStruct(id=pid, vector=vec, payload=doc))

            client_qdrant.upsert(
                collection_name=settings.qdrant_collection_reddit,
                points=points,
            )
