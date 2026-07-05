"""Reddit public JSON feed ingester — no API key required."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
import httpx
from better_profanity import profanity

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed

SUBREDDITS = ["travel", "solotravel", "digitalnomad", "backpacking"]
FEED_URL = "https://www.reddit.com/r/{sub}/top.json?limit=50&t=month"

# Curated list of popular travel destinations for NER-free destination tagging.
# Ordered roughly by global travel popularity so first-match bias favours top destinations.
KNOWN_DESTINATIONS = [
    # Asia
    "Tokyo", "Osaka", "Kyoto", "Bangkok", "Bali", "Singapore", "Seoul", "Hong Kong",
    "Taipei", "Kuala Lumpur", "Ho Chi Minh City", "Hanoi", "Hoi An", "Phuket",
    "Chiang Mai", "Siem Reap", "Kathmandu", "Mumbai", "Delhi", "Goa", "Jaipur",
    "Varanasi", "Agra", "Kolkata", "Chennai", "Hyderabad", "Bengaluru", "Kochi",
    "Sri Lanka", "Colombo", "Maldives", "Dubai", "Abu Dhabi", "Doha", "Muscat",
    "Istanbul", "Cappadocia", "Tbilisi", "Baku",
    # Europe
    "Paris", "London", "Rome", "Barcelona", "Amsterdam", "Berlin", "Prague",
    "Vienna", "Budapest", "Lisbon", "Porto", "Madrid", "Athens", "Santorini",
    "Mykonos", "Dubrovnik", "Split", "Copenhagen", "Stockholm", "Oslo",
    "Helsinki", "Edinburgh", "Dublin", "Bruges", "Venice", "Florence", "Milan",
    "Zurich", "Geneva", "Brussels", "Reykjavik", "Tallinn", "Riga", "Vilnius",
    "Warsaw", "Krakow", "Munich", "Hamburg", "Seville", "Granada", "Valencia",
    "Nice", "Lyon", "Marseille", "Cinque Terre", "Amalfi",
    # Americas
    "New York", "Los Angeles", "San Francisco", "Chicago", "Miami", "Las Vegas",
    "New Orleans", "Boston", "Seattle", "Denver", "Austin", "Washington DC",
    "Mexico City", "Cancun", "Tulum", "Oaxaca", "Havana", "Bogotá", "Medellín",
    "Cartagena", "Lima", "Cusco", "Machu Picchu", "Buenos Aires", "Rio de Janeiro",
    "São Paulo", "Santiago", "Montevideo", "Quito", "La Paz", "Toronto",
    "Vancouver", "Montreal", "Quebec City",
    # Africa & Oceania
    "Cape Town", "Marrakech", "Cairo", "Nairobi", "Zanzibar", "Casablanca",
    "Sydney", "Melbourne", "Brisbane", "Auckland", "Queenstown", "Bora Bora",
    "Fiji", "Hawaii", "Honolulu",
]

# Build a lowercase lookup for fast case-insensitive matching
_DEST_LOWER = {d.lower(): d for d in KNOWN_DESTINATIONS}

profanity.load_censor_words()


def _is_safe(text: str) -> bool:
    return not profanity.contains_profanity(text)


def _chunk_reddit_post(title: str, selftext: str) -> list[str]:
    """
    Split a Reddit post into paragraph-level chunks.
    Each chunk is prefixed with the title so it carries topic context
    even when retrieved in isolation.

    Rules:
    - Split body on blank lines (natural paragraph / comment boundary)
    - Drop any paragraph shorter than 80 chars (noise)
    - If no viable paragraphs, fall back to title + first 800 chars of body
    """
    if not selftext:
        return [title]

    paragraphs = [p.strip() for p in re.split(r'\n{2,}', selftext) if len(p.strip()) >= 80]
    if not paragraphs:
        full = f"{title}. {selftext[:800]}".strip()
        return [full]

    return [f"{title}. {para}" for para in paragraphs]


def _extract_destination(title: str, selftext: str) -> str:
    """
    Match post title (then body) against a curated list of travel destinations.
    Returns the canonical destination name, or "general" if no match is found.
    """
    for text in (title, selftext):
        lower = text.lower()
        for dest_lower, dest_canonical in _DEST_LOWER.items():
            # Word-boundary match to avoid "Bali" matching "Balinese" mid-word
            if re.search(r'\b' + re.escape(dest_lower) + r'\b', lower):
                return dest_canonical
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
                selftext = data.get("selftext", "")
                if not _is_safe(f"{title} {selftext}"):
                    continue

                destination = _extract_destination(title, selftext)
                post_url = f"https://reddit.com{data.get('permalink', '')}"
                published_date = (
                    datetime.fromtimestamp(data["created_utc"], tz=timezone.utc).date().isoformat()
                    if data.get("created_utc")
                    else None
                )

                for chunk_text in _chunk_reddit_post(title, selftext):
                    docs.append({
                        "destination": destination,
                        "source": "reddit",
                        "subreddit": sub,
                        "title": title,
                        "text": chunk_text,
                        "text_preview": chunk_text[:300],
                        "post_url": post_url,
                        "reddit_score": data.get("score", 0),
                        "published_date": published_date,
                    })

            if not docs:
                continue

            vectors = embed([d["text"] for d in docs])
            from qdrant_client.models import PointStruct
            points = []
            for doc, vec in zip(docs, vectors):
                # Unique ID per chunk (post URL + first 50 chars of chunk text)
                pid = int(hashlib.md5(f"{doc['post_url']}{doc['text'][:50]}".encode()).hexdigest(), 16) % (2**63)
                points.append(PointStruct(id=pid, vector=vec, payload=doc))

            client_qdrant.upsert(
                collection_name=settings.qdrant_collection_reddit,
                points=points,
            )
