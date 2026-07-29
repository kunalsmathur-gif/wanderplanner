"""Entry/visa requirements from Wikivoyage country guides (issue #37).

**Keyed by country, not city — and that was measured, not assumed.** Issue #37
proposed reusing the Wikivoyage pattern against the existing destination list.
Probing the live articles on 2026-07-29 showed visa content simply is not
city-level: counting visa/passport/e-visa mentions inside each article's
"Get in" section gave

    India 76 | Thailand 30 | UAE 31 | France 28 | Japan 16
    Jaipur  0 | Bangkok  0 | Paris  1

so scraping the 170 city guides would have produced almost nothing, while
scraping ~60 country articles covers all of them. Keying per city would also
mean storing one country's rules 170 times over, each copy drifting as it
refreshed on its own schedule.

**This is genuinely new corpus, not a duplicate of `wiki`.** `scrapers/
wikivoyage.py::SECTIONS_OF_INTEREST` is `{go, stay_safe, see, do, eat, drink,
sleep, understand}` matched as substrings, and `get_in` contains none of them —
so the main scraper has never ingested "Get in" for any destination.

The subsection holding the actual rules is **not consistently named**: India
uses "Visa", Thailand/France/UAE use "Entry requirements", Japan has no
subsection at all. So this takes the whole `Get in` H2 (subsections included)
and filters chunk-by-chunk on visa vocabulary, rather than looking for a
heading by name.

⚠️ **Not legal advice, and deliberately not sourced from a paid visa API.**
Wikivoyage is community-maintained and can lag a rule change. The retrieval
side surfaces this as background context with its source URL attached, never
as a determination — see `services/visa.py`.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re

import httpx
from bs4 import BeautifulSoup
from qdrant_client.models import PointStruct

from core.config import settings
from core.embeddings import embed
from core.ingestion_metadata import build_ingestion_payload
from core.keyword_match import has_keyword
from core.qdrant import delete_stale_destination_points, get_qdrant
from scrapers.wikivoyage import _sentence_boundary_chunks

logger = logging.getLogger(__name__)

BASE_URL = "https://en.wikivoyage.org/wiki/{title}"

# The H2 whose subtree holds entry rules. Substring-matched against the
# heading id, so "Get_in" matches and the numbered variants MediaWiki emits on
# repeated headings ("Get_in_2") do too.
_ENTRY_SECTION_IDS = ("get_in", "entry")

# Vocabulary that marks a chunk as actually about entry rules rather than
# about flights or bus routes, which share the "Get in" section. Whole-word
# matched through core/keyword_match.py — the repo has had five separate
# substring-keyword bugs (v10.40.4/5/6), and "visa" as a bare substring hits
# "visualise"/"Visakhapatnam", the latter being an Indian city this product
# would plausibly see.
_VISA_KEYWORDS = frozenset({
    "visa", "visas", "e-visa", "evisa", "visa-free", "visa-exempt",
    "passport", "passports", "entry", "immigration", "customs",
    "permit", "permits", "eta", "schengen", "arrival", "border",
})

_MAX_FETCH_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 5.0

# MediaWiki renders a per-heading "[edit]" link, and `get_text()` on a section
# that includes its subsection headings pulls those in as literal "[ edit ]"
# runs. Caught 2026-07-29 by reading the scraped France/UAE text rather than
# just counting chunks. It matters more here than elsewhere: these chunks are
# both embedded (so the noise shifts the vector) and surfaced into the wizard
# prompt (so a user could see it).
_EDIT_MARKER_RE = re.compile(r"\[\s*edit\s*\]", re.IGNORECASE)


def _clean(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _EDIT_MARKER_RE.sub(" ", text)).strip()

# Countries covering the destinations this product actually serves.
#
# A curated list rather than a derivation from `scrapers/reddit.py`'s
# KNOWN_DESTINATIONS, because that list is cities with no country attached —
# mapping it would mean ~170 Nominatim geocodes on every refresh to recover a
# fact that changes never. ~60 titles against a free Wikimedia API is cheap
# enough that demand-ranking it (the docs/scaling-tech-challenges.md §8
# pattern used for OSM/YouTube) would add machinery for no saving.
#
# India first and deliberately: it is both the home market (outbound visa rules
# are what the core cohort needs) and the largest inbound destination here.
VISA_SEED_COUNTRIES: list[str] = [
    "India",
    # Asia
    "Japan", "Thailand", "Singapore", "Malaysia", "Vietnam", "Indonesia",
    "Nepal", "Sri Lanka", "Bhutan", "Maldives", "China", "South Korea",
    "Taiwan", "Cambodia", "Laos", "Philippines", "Myanmar", "Bangladesh",
    # Middle East
    "United Arab Emirates", "Qatar", "Oman", "Saudi Arabia", "Jordan",
    "Israel", "Turkey", "Georgia", "Armenia", "Azerbaijan",
    # Europe
    "France", "Italy", "Spain", "Portugal", "Germany", "Netherlands",
    "Switzerland", "Austria", "Greece", "Czech Republic", "Hungary",
    "Poland", "Croatia", "Iceland", "Norway", "Sweden", "Denmark",
    "Finland", "Ireland", "United Kingdom", "Belgium", "Slovenia",
    "Estonia", "Latvia", "Lithuania",
    # Americas
    "United States of America", "Canada", "Mexico", "Brazil", "Argentina",
    "Peru", "Chile", "Colombia", "Costa Rica", "Cuba",
    # Africa & Oceania
    "Egypt", "Morocco", "Kenya", "Tanzania", "South Africa", "Mauritius",
    "Australia", "New Zealand", "Fiji",
]


def _parse_entry_sections(html: str, country: str, url: str) -> list[dict]:
    """Chunks from the article's entry-related H2 subtree that actually talk
    about entry rules."""
    soup = BeautifulSoup(html, "lxml")
    docs: list[dict] = []

    for h2 in soup.find_all("h2"):
        section_id = (h2.get("id") or "").lower().replace(" ", "_")
        if not any(s in section_id for s in _ENTRY_SECTION_IDS):
            continue
        # Same MediaWiki-skin handling as scrapers/wikivoyage.py: the heading
        # sits inside a `div.mw-heading` wrapper, and section content are the
        # wrapper's siblings, not the <h2>'s.
        wrapper = h2.parent
        if wrapper is None or "mw-heading" not in (wrapper.get("class") or []):
            wrapper = h2

        texts: list[str] = []
        for sib in wrapper.find_next_siblings():
            if sib.name == "h2":
                break
            if sib.name == "div" and "mw-heading" in (sib.get("class") or []):
                # A nested mw-heading is a *sub*section (h3/h4) and still ours;
                # only a sibling H2 wrapper ends this section.
                if "mw-heading2" in (sib.get("class") or []):
                    break
                texts.append(sib.get_text(" ", strip=True))
                continue
            if sib.name in ("p", "ul", "li", "section", "table"):
                texts.append(sib.get_text(" ", strip=True))

        if not texts:
            continue
        for chunk in _sentence_boundary_chunks(_clean(" ".join(texts)), max_chars=500):
            if not has_keyword(chunk, _VISA_KEYWORDS):
                continue
            docs.append(build_ingestion_payload(
                destination=country,
                source="visa_info",
                text=chunk,
                source_url=url,
                source_name="Wikivoyage",
                country=country,
                extra={"section": section_id},
            ))
    return docs


async def scrape_visa_info(country: str) -> list[dict]:
    """Fetch a Wikivoyage *country* article and return its entry-rule chunks.

    Best-effort: returns [] rather than raising, matching every other scraper
    in this package.
    """
    title = country.strip().replace(" ", "_")
    url = BASE_URL.format(title=title)
    headers = {"User-Agent": settings.nominatim_user_agent}

    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                return _parse_entry_sections(resp.text, country.strip(), url)
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "Visa info fetch failed for %r after %d attempts: %s",
                        country, attempt, e,
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)
    return []


async def ingest_visa_info(country: str) -> int:
    """Scrape and upsert entry rules for `country`. Returns chunks ingested.

    Safe to re-run: stale points are deleted before the new ones land, so a
    rule that Wikivoyage removed does not linger in the corpus — which matters
    more here than for other sources, since an obsolete visa rule is worse
    than a missing one.
    """
    docs = await scrape_visa_info(country)
    if not docs:
        logger.info("visa_info %r: no entry-rule chunks found", country)
        return 0

    vectors = await asyncio.to_thread(embed, [d["text"] for d in docs])

    points: list[PointStruct] = []
    new_ids: set[int] = set()
    for doc, vec in zip(docs, vectors):
        digest = hashlib.md5(f"{doc['source_url']}::{doc['text'][:80]}".encode()).hexdigest()
        pid = int(digest, 16) % (2**63)
        new_ids.add(pid)
        points.append(PointStruct(id=pid, vector=vec, payload=doc))

    client = get_qdrant()
    stale = delete_stale_destination_points(
        client, settings.qdrant_collection_visa_info, country.strip(), new_ids
    )
    if stale:
        logger.info("visa_info %r: deleted %d stale points", country, stale)
    client.upsert(collection_name=settings.qdrant_collection_visa_info, points=points)
    logger.info("visa_info %r: ingested %d chunks", country, len(points))
    return len(points)
