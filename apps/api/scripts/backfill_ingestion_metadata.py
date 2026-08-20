"""One-off backfill for unified ingestion-metadata fields onto pre-2026-07-29
Qdrant points (issue #61, follow-up to #33 / v10.50.0).

**Decision recorded here (issue #61's acceptance criteria):** measured the
legacy-only share per collection on 2026-08-19 against the live Qdrant Cloud
cluster:

    wiki                0.0%  (0 / 35,592)   — already fully re-ingested (#45/#46)
    youtube_narration    0.0%  (0 / 10,858)   — already fully re-ingested (#45/#46)
    visa_info            0.0%  (0 / 1,291)    — shipped after the unified schema
    reddit               n/a   (0 points total, collection currently empty)
    osm_pois             1.0%  (104 / 10,097) — small enough to backfill directly
    youtube_comments    92.1%  (23,311 / 25,306) — large; no re-ingestion pass is
                                                    scheduled for this collection,
                                                    so "let it age out" would leave
                                                    it mixed indefinitely

**Decision: backfill `osm_pois` and `youtube_comments` now** (option 1),
rather than wait for age-out (option 2) — `youtube_comments` in particular
has no scheduled re-ingestion pass to age it out, and both collections'
`content_type`/`language`/`attraction_type` values are fully derivable from
already-stored fields with no re-fetch. `wiki`/`youtube_narration`/`visa_info`
need nothing — age-out already did the job. `reddit` is empty; nothing to
backfill until it has data.

**Per issue #61's acceptance criteria: `country` is never invented.** Only
fields genuinely derivable from a point's own stored payload are written:

- `language` — `core.ingestion_metadata.detect_language(text)`, every
  collection.
- `content_type` — `core.ingestion_metadata.SOURCE_CONTENT_TYPE[source]`,
  every collection (falls back to the collection's own known default source
  when a legacy point is missing the `source` key entirely — observed on a
  handful of `osm_pois` points).
- `attraction_type` — `osm_pois` only, derived from the point's own stored
  `poi_type` via `core.ingestion_metadata.OSM_POI_TYPE_TO_ATTRACTION`.

Deliberately NOT backfilled (out of this issue's scope — not asked for, and
every consumer already has a safe default so nothing is broken by their
continued absence): `source_name`, `quality_score`, `ingested_at`. Writing
`ingested_at` during a backfill would misrepresent *when the point was
originally ingested*, which is exactly the kind of invented value issue #61
warns against for `country` — the same reasoning applies here.

Usage:
    cd apps/api && .venv/bin/python -m scripts.backfill_ingestion_metadata --dry-run
    cd apps/api && .venv/bin/python -m scripts.backfill_ingestion_metadata --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from core.logging_config import configure_script_logging  # noqa: E402

configure_script_logging()
logger = logging.getLogger("backfill_ingestion_metadata")

# Collection name (settings attr) -> the source string to assume for a
# legacy point missing the `source` key entirely (observed on a handful of
# osm_pois points — see core/ingestion_metadata.py's docstring on the four
# legacy fields for why `source` was expected but isn't always present pre-
# cutover).
_DEFAULT_SOURCE_BY_COLLECTION = {
    "qdrant_collection_osm": "osm",
    "qdrant_collection_youtube_comments": "youtube_comment",
}

# Only these two collections are in scope per the recorded decision above —
# the rest are either already fully migrated (age-out did the job) or empty.
_BACKFILL_COLLECTIONS = ["qdrant_collection_osm", "qdrant_collection_youtube_comments"]


def _derive_extra_payload(payload: dict, *, collection_setting: str) -> dict:
    """Computes only the fields genuinely derivable from `payload` itself —
    see module docstring for exactly which fields and why. Returns an empty
    dict if the point isn't legacy (already has `language`), so callers can
    skip it."""
    if "language" in payload:
        return {}

    from core.ingestion_metadata import (
        OSM_POI_TYPE_TO_ATTRACTION,
        SOURCE_CONTENT_TYPE,
        detect_language,
    )

    text = payload.get("text", "")
    source = payload.get("source") or _DEFAULT_SOURCE_BY_COLLECTION[collection_setting]

    extra: dict = {
        "language": detect_language(text),
        "content_type": SOURCE_CONTENT_TYPE.get(source, "guide"),
    }

    if collection_setting == "qdrant_collection_osm":
        poi_type = payload.get("poi_type")
        if poi_type:
            extra["attraction_type"] = OSM_POI_TYPE_TO_ATTRACTION.get(poi_type, "activity")

    return extra


def _plan_backfill(client, collection_name: str, collection_setting: str) -> dict[tuple, list[int | str]]:
    """Scrolls `collection_name` and groups legacy point IDs by their
    identical computed extra-payload dict (there are only a handful of
    distinct combinations — e.g. 2 languages x 1 content_type — so this
    turns tens of thousands of points into a handful of `set_payload`
    calls instead of one call per point)."""
    groups: dict[tuple, list[int | str]] = defaultdict(list)
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name, limit=500, with_payload=True, with_vectors=False, offset=offset
        )
        for p in points:
            extra = _derive_extra_payload(p.payload or {}, collection_setting=collection_setting)
            if extra:
                key = tuple(sorted(extra.items()))
                groups[key].append(p.id)
        if offset is None:
            break
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually write — default is a dry run (plan only)")
    args = parser.parse_args()

    from core.config import settings
    from core.qdrant import get_qdrant

    client = get_qdrant()

    total_planned = 0
    for collection_setting in _BACKFILL_COLLECTIONS:
        collection_name = getattr(settings, collection_setting)
        groups = _plan_backfill(client, collection_name, collection_setting)
        n_points = sum(len(ids) for ids in groups.values())
        total_planned += n_points
        logger.info(
            "%s: %d legacy point(s) across %d distinct payload group(s)",
            collection_name, n_points, len(groups),
        )
        for key, ids in groups.items():
            extra = dict(key)
            logger.info("  %s -> %d point(s)", extra, len(ids))
            if args.apply:
                client.set_payload(collection_name=collection_name, payload=extra, points=ids)

    if not args.apply:
        logger.info(
            "DRY RUN — %d point(s) would be updated. Re-run with --apply to write.",
            total_planned,
        )
    else:
        logger.info("Applied backfill to %d point(s).", total_planned)
    return 0


if __name__ == "__main__":
    sys.exit(main())
