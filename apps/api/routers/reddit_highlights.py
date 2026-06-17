"""Reddit highlights endpoint — returns top traveler posts for a destination."""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.config import settings
from core.qdrant import get_qdrant
from core.embeddings import embed

router = APIRouter()


class RedditPost(BaseModel):
    title: str
    text_preview: str
    post_url: str
    subreddit: str
    score: int


class RedditHighlightsResponse(BaseModel):
    posts: list[RedditPost]
    destination: str


@router.get("/reddit-highlights", response_model=RedditHighlightsResponse)
async def reddit_highlights(
    destination: str = Query(..., description="Destination city name"),
    limit: int = Query(5, ge=1, le=20),
) -> RedditHighlightsResponse:
    try:
        client = get_qdrant()
        query = f"{destination} travel tips guide best places"
        vector = embed([query])[0]

        # Search without destination filter first (destination tagging is naive)
        # to surface any relevant posts
        hits = client.search(
            collection_name=settings.qdrant_collection_reddit,
            query_vector=vector,
            limit=limit * 2,
            score_threshold=0.1,
        )

        seen_urls: set[str] = set()
        posts: list[RedditPost] = []
        for hit in hits:
            p = hit.payload or {}
            url = p.get("post_url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            posts.append(RedditPost(
                title=p.get("title", "Travel tip"),
                text_preview=p.get("text_preview", p.get("text", ""))[:200],
                post_url=url,
                subreddit=p.get("subreddit", "travel"),
                score=int(p.get("score", 0)),
            ))
            if len(posts) >= limit:
                break

        return RedditHighlightsResponse(posts=posts, destination=destination)

    except Exception:
        # Graceful degradation — collection may be empty on first run
        return RedditHighlightsResponse(posts=[], destination=destination)
