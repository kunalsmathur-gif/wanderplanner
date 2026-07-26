"""
Itinerary corpus scrapers (docs/rag-strategy.md §9, Phase v0 — free-tier sources only).

Scope of THIS module: fetch RAW itinerary-shaped content and return it as plain
dicts with lightweight source metadata. It deliberately does NOT:
  - call any LLM to structure the text into `ItineraryCorpusDoc` (that is the
    separate downstream `itinerary-corpus-extraction` todo),
  - embed anything or write to Qdrant (ditto — a new `itinerary_corpus`
    collection is created by the extraction step once documents are shaped).

All four sources below are free and require no paid API key:
  - Travel blog RSS feeds (Nomadic Matt, Planet D, ...) via `feedparser` + a
    BeautifulSoup full-page fetch for the post body.
  - Wikivoyage "Itineraries" articles via the official Wikimedia API
    (`action=parse`) — structured HTML from a stable, keyless, ToS-friendly
    endpoint (same approach already used for other Wikimedia content in this
    repo's `scrapers/wikivoyage.py`, just targeting itinerary-specific pages).
  - Reddit trip-report self-posts, reusing the existing public-JSON pattern
    from `scrapers/reddit.py` (no OAuth/PRAW credentials needed) filtered down
    to itinerary-shaped titles (e.g. "10 day itinerary for...").
  - YouTube caption transcripts via `youtube_transcript_api`, which needs only
    a video ID (no API key). Video *discovery* is now live via the YouTube
    Data API's `search.list` (`discover_youtube_itinerary_videos()`, reusing
    scrapers/youtube_comments.py's client + shared quota budget) over an
    India-weighted seed destination list, filtered to itinerary-shaped titles.
    That path is the only one here that needs a key: it is a documented no-op
    without one, falling back to the manual `YOUTUBE_ITINERARY_VIDEO_IDS`
    list, so this module still works keyless — just with fewer videos.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Travel blog RSS feeds (Nomadic Matt, Planet D, ...)
# ---------------------------------------------------------------------------

TRAVEL_BLOG_FEEDS = [
    {"name": "Nomadic Matt", "url": "https://www.nomadicmatt.com/travel-blog/feed/"},
    # Planet D's feed (previously listed here) has been failing with a
    # connection-reset on every fetch since ~2026-07-20 (a different failure
    # mode than the earlier User-Agent 403) — dropped rather than left in as
    # dead weight; revisit if it comes back healthy.
    {"name": "Uncornered Market", "url": "https://uncorneredmarket.com/feed/"},
    # India-focused (Indian bloggers, domestic + India-outbound trips) — the
    # existing pool had zero India-specific blog coverage even though
    # ITINERARY_SUBREDDITS below already includes r/IndiaTravel; day-count
    # itinerary titles ("10 day trip to Australia", "4-Day Guide to Doha")
    # match `_ITINERARY_TITLE_PATTERN` well above the pool average.
    {"name": "Bruised Passports", "url": "https://www.bruisedpassports.com/feed"},
    # Added 2026-07-22 -- "hidden gems"-angled per docs/NEXT_SESSION_TODO.md
    # item 3's free-source list. Live-verified: both feeds return real,
    # full-body-fetchable posts. Two Wandering Soles has the strongest hit
    # rate seen yet against `_ITINERARY_TITLE_PATTERN`/gem-style titles (e.g.
    # "Portugal's Best Hidden Gem", "The 2-day Kyoto Itinerary I'd Recommend"
    # -- 3 of 12 recent items), Y Travel Blog next-best ("Queensland's Best
    # Kept Secret").
    {"name": "Two Wandering Soles", "url": "https://www.twowanderingsoles.com/feed/"},
    {"name": "Y Travel Blog", "url": "https://www.ytravelblog.com/feed/"},
]

# Titles that look like a real day-by-day itinerary post, vs. generic listicles.
_ITINERARY_TITLE_PATTERN = re.compile(
    r"\b(\d+[\s-]?(day|days|week|weeks))\b|itinerary|trip\s*report",
    re.IGNORECASE,
)


def _is_itinerary_shaped(title: str) -> bool:
    return bool(_ITINERARY_TITLE_PATTERN.search(title or ""))


async def _fetch_blog_post_body(client: httpx.AsyncClient, url: str) -> str:
    """Best-effort full-page text fetch for an RSS entry (RSS summaries are
    often truncated). Falls back to empty string on any failure — the RSS
    summary/title is still usable upstream."""
    try:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(resp.text, "lxml")
    # Most travel blogs (WordPress-based, both Nomadic Matt and Planet D are)
    # wrap the article body in <article> or a `.entry-content` div.
    container = soup.find("article") or soup.find(class_=re.compile(r"entry-content|post-content"))
    if not container:
        container = soup.find("body")
    if not container:
        return ""
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all(["p", "li", "h2", "h3"])]
    return "\n".join(p for p in paragraphs if len(p) > 20)


async def scrape_travel_blog_feed(feed: dict[str, str], limit: int = 20) -> list[dict[str, Any]]:
    """Fetch entries from one travel blog RSS feed, keeping only
    itinerary-shaped posts, and pull the full post body via BeautifulSoup."""
    try:
        parsed = feedparser.parse(feed["url"])
    except Exception as e:
        logger.warning("RSS parse failed for %s: %s", feed["name"], e)
        return []

    docs: list[dict[str, Any]] = []
    headers = {"User-Agent": settings.nominatim_user_agent}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for entry in parsed.entries[:limit]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            if not link or not _is_itinerary_shaped(title):
                continue

            body = await _fetch_blog_post_body(client, link)
            summary = BeautifulSoup(entry.get("summary", ""), "lxml").get_text(" ", strip=True)
            raw_text = body or summary
            if len(raw_text) < 200:
                continue

            published_date = None
            if entry.get("published_parsed"):
                t = entry["published_parsed"]
                published_date = datetime(
                    t[0], t[1], t[2], t[3], t[4], t[5], tzinfo=UTC
                ).date().isoformat()

            docs.append({
                "source": "travel_blog",
                "source_name": feed["name"],
                "source_url": link,
                "title": title,
                "raw_text": raw_text,
                "published_date": published_date,
            })
    return docs


async def scrape_all_travel_blogs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for feed in TRAVEL_BLOG_FEEDS:
        docs.extend(await scrape_travel_blog_feed(feed))
    return docs


# ---------------------------------------------------------------------------
# 2. Wikivoyage "Itineraries" articles (official Wikimedia API, action=parse)
# ---------------------------------------------------------------------------

WIKIVOYAGE_API_URL = "https://en.wikivoyage.org/w/api.php"

# A small, curated seed list of well-known Wikivoyage itinerary articles.
# (Wikivoyage's dedicated "Itinerary" namespace/category is sparsely populated
# and inconsistent to crawl generically, so — same spirit as the RSS feed
# list above — we seed with known-good article titles.)
WIKIVOYAGE_ITINERARY_TITLES = [
    "Golden Triangle (India)",
    # India-specific additions (NEXT_SESSION_TODO.md item 3 — the blog/RSS and
    # itinerary-corpus pools were India-thin despite India being the core
    # cohort). Both live-verified to resolve to real, itinerary-shaped
    # Wikivoyage articles (canonical titles used so a redirect change can't
    # silently break them).
    "Kerala Backwaters",
    "Rail travel in India",
    "Grand Tour of Europe",
    "Trans-Siberian Railway",
    "Backpacking in Southeast Asia",
    "Ten days in Iceland",
]


async def scrape_wikivoyage_itinerary(title: str) -> dict[str, Any] | None:
    """Fetch a Wikivoyage article via the official Wikimedia `action=parse`
    API and return its rendered text content. This is not "scraping" a raw
    HTML page — it's the same official, stable, keyless API endpoint
    Wikimedia projects publish for this exact purpose."""
    params = {
        "action": "parse",
        "page": title,
        "format": "json",
        "prop": "text",
        "redirects": "1",
    }
    # Wikimedia's API etiquette asks for an identifiable User-Agent on every
    # request; some network paths in front of wikivoyage.org also reject
    # requests missing one with a bare 403.
    headers = {"User-Agent": settings.nominatim_user_agent}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        try:
            resp = await client.get(WIKIVOYAGE_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Wikivoyage API fetch failed for %s: %s", title, e)
            return None

    if "error" in data:
        return None

    html = data.get("parse", {}).get("text", {}).get("*", "")
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "li", "h2", "h3"])]
    raw_text = "\n".join(p for p in paragraphs if len(p) > 20)
    if len(raw_text) < 200:
        return None

    resolved_title = data.get("parse", {}).get("title", title)
    return {
        "source": "wikivoyage_itinerary",
        "source_name": "Wikivoyage",
        "source_url": f"https://en.wikivoyage.org/wiki/{resolved_title.replace(' ', '_')}",
        "title": resolved_title,
        "raw_text": raw_text,
        "published_date": None,
    }


async def scrape_all_wikivoyage_itineraries() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for title in WIKIVOYAGE_ITINERARY_TITLES:
        doc = await scrape_wikivoyage_itinerary(title)
        if doc:
            docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# 3. Reddit trip-report self-posts (public JSON feed, no OAuth/PRAW needed)
# ---------------------------------------------------------------------------

ITINERARY_SUBREDDITS = ["travel", "solotravel", "backpacking", "IndiaTravel", "JapanTravel", "digitalnomad"]
_REDDIT_FEED_URL = "https://www.reddit.com/r/{sub}/search.json?q=itinerary&restrict_sr=1&sort=top&t=year&limit=25"


async def scrape_reddit_trip_reports() -> list[dict[str, Any]]:
    """Reuse the existing keyless Reddit public-JSON pattern (see
    `scrapers/reddit.py::ingest_reddit`), but search within itinerary-focused
    subreddits for itinerary-shaped self-posts specifically, rather than
    ingesting every top post generically."""
    headers = {"User-Agent": settings.nominatim_user_agent}
    docs: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for sub in ITINERARY_SUBREDDITS:
            try:
                resp = await client.get(_REDDIT_FEED_URL.format(sub=sub))
                resp.raise_for_status()
                posts = resp.json().get("data", {}).get("children", [])
            except Exception as e:
                logger.warning("Reddit trip-report search failed for r/%s: %s", sub, e)
                continue

            for post in posts:
                data = post.get("data", {})
                if data.get("score", 0) < settings.reddit_min_score:
                    continue
                title = data.get("title", "")
                selftext = data.get("selftext", "")
                if not _is_itinerary_shaped(title) or len(selftext) < 200:
                    continue

                published_date = (
                    datetime.fromtimestamp(data["created_utc"], tz=UTC).date().isoformat()
                    if data.get("created_utc")
                    else None
                )
                docs.append({
                    "source": "reddit_trip_report",
                    "source_name": f"r/{sub}",
                    "source_url": f"https://reddit.com{data.get('permalink', '')}",
                    "title": title,
                    "raw_text": f"{title}\n\n{selftext}",
                    "published_date": published_date,
                    "reddit_score": data.get("score", 0),
                })
    return docs


# ---------------------------------------------------------------------------
# 4. YouTube caption transcripts (youtube_transcript_api, no API key needed)
# ---------------------------------------------------------------------------

# Manual seed list, kept as a supplement to (not a replacement for) the live
# discovery below: transcripts themselves need no API key, so a hand-curated
# video ID still works when `YOUTUBE_API_KEY` is unset or its search budget is
# exhausted. Extend as good videos are found.
YOUTUBE_ITINERARY_VIDEO_IDS: list[dict[str, str]] = [
    # Intentionally empty by default — populate with known-good video IDs,
    # e.g. {"video_id": "dQw4w9WgXcQ", "title": "..."}
]

# Destinations to run live itinerary-video discovery for. Deliberately
# India-weighted from day one (docs/NEXT_SESSION_TODO.md item 3's "India
# domestic-travel coverage findings": the main user cohort is Indian, and
# every previous seed list in this codebase under-served domestic destinations
# — `KNOWN_DESTINATIONS` shipped with 11 India entries out of ~134, and
# `WIKIVOYAGE_ITINERARY_TITLES` with 1 of 5). Kept short because each entry
# costs a 100-unit `search.list` call against a 10,000/day quota shared with
# hidden-gems comment ingestion.
YOUTUBE_ITINERARY_SEED_DESTINATIONS: list[str] = [
    # India (majority — domestic trip-vlog ecosystem is large and under-indexed
    # by the blog/Wikivoyage sources this corpus otherwise draws on)
    "Rajasthan", "Kerala", "Goa", "Ladakh", "Himachal Pradesh",
    "Rishikesh", "Varanasi", "Meghalaya", "Andaman Islands", "Karnataka",
    # International — the most-requested outbound destinations for the same cohort
    "Bali", "Thailand", "Vietnam", "Dubai", "Singapore", "Japan",
]


def _itinerary_search_query(destination: str) -> str:
    """Itinerary-shaped phrasing, distinct from
    scrapers/youtube_comments.py's hidden-gems default: this corpus wants
    day-by-day trip plans to extract structure from, not comment sentiment."""
    return f"{destination} itinerary travel vlog day by day trip plan"


async def discover_youtube_itinerary_videos() -> list[dict[str, str]]:
    """Live per-destination video discovery via the YouTube Data API, replacing
    the previously manual-only `YOUTUBE_ITINERARY_VIDEO_IDS` list.

    Returns `[]` when no API key is configured (or the shared rolling-24h
    search budget is exhausted) — the manual seed list above still applies in
    that case, so this degrades to the old behaviour rather than breaking.

    Discovered titles are filtered through the same `_is_itinerary_shaped()`
    check the RSS path uses: `search.list` relevance alone happily returns
    "10 THINGS TO KNOW BEFORE..." videos, which have no day structure for the
    downstream extraction chain to work with.
    """
    from scrapers.youtube_comments import search_travel_videos

    if not settings.youtube_api_key:
        return []

    discovered: list[dict[str, str]] = []
    for destination in YOUTUBE_ITINERARY_SEED_DESTINATIONS:
        try:
            videos = await search_travel_videos(
                destination, query=_itinerary_search_query(destination)
            )
        except Exception as e:
            logger.warning("YouTube itinerary discovery failed for %s: %s", destination, e)
            continue
        for video in videos:
            if _is_itinerary_shaped(video.get("title", "")):
                discovered.append(video)
    return discovered


async def fetch_youtube_transcript(video_id: str, title: str = "") -> dict[str, Any] | None:
    """Fetch the English caption transcript for a single YouTube video ID.
    No API key required — `youtube_transcript_api` scrapes the public
    timedtext endpoint YouTube itself uses to render captions."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=("en",))
    except Exception as e:
        logger.warning("YouTube transcript fetch failed for %s: %s", video_id, e)
        return None

    raw_text = " ".join(snippet.text for snippet in transcript)
    if len(raw_text) < 200:
        return None

    return {
        "source": "youtube_captions",
        "source_name": "YouTube",
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title or video_id,
        "raw_text": raw_text,
        "published_date": None,
    }


async def scrape_all_youtube_transcripts() -> list[dict[str, Any]]:
    """Fetch transcripts for the manual seed list plus any live-discovered
    itinerary videos, deduped by video ID (a manually-curated video can also
    surface in search results — fetching its transcript twice would emit a
    duplicate corpus doc)."""
    entries = list(YOUTUBE_ITINERARY_VIDEO_IDS) + await discover_youtube_itinerary_videos()

    docs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        video_id = entry.get("video_id", "")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        doc = await fetch_youtube_transcript(video_id, entry.get("title", ""))
        if doc:
            docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# Orchestrator — combine all free v0 sources into one raw-document list.
# ---------------------------------------------------------------------------

async def collect_itinerary_corpus_raw() -> list[dict[str, Any]]:
    """Run all free v0 itinerary-corpus sources and return a combined list of
    raw documents ready for the (separate, downstream) extraction step.

    Each doc has: source, source_name, source_url, title, raw_text,
    published_date (nullable).
    """
    docs: list[dict[str, Any]] = []
    for fetcher in (
        scrape_all_travel_blogs,
        scrape_all_wikivoyage_itineraries,
        scrape_reddit_trip_reports,
        scrape_all_youtube_transcripts,
    ):
        try:
            docs.extend(await fetcher())
        except Exception as e:
            logger.warning("Itinerary corpus source %s failed: %s", getattr(fetcher, "__name__", str(fetcher)), e)
    return docs
