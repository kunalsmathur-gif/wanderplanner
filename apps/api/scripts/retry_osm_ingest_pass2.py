"""Second retry pass — targets only destinations still at 0 POIs after
scripts/retry_osm_ingest.py's first pass (still Overpass 429/504-limited
even at 6s delay). Uses a longer 12s delay."""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("retry_osm_ingest_pass2")

DELAY_SECONDS = 12.0

STILL_ZERO = [
    "Bangkok", "Taipei", "Ho Chi Minh City", "Hoi An", "Phuket", "Mumbai",
    "Delhi", "Jaipur", "Varanasi", "Agra", "Bengaluru", "Kochi", "Maldives",
    "Abu Dhabi", "Doha", "Muscat", "Istanbul", "Paris", "London", "Barcelona",
    "Prague", "Budapest", "Lisbon", "Santorini", "Mykonos", "Oslo", "Helsinki",
    "Venice", "Florence", "Brussels", "Reykjavik", "Warsaw", "Hamburg",
    "Granada", "Marseille", "Cinque Terre", "Amalfi", "New York", "Las Vegas",
    "New Orleans", "Seattle", "Austin", "Mexico City", "Tulum", "Havana",
    "Bogotá", "Medellin", "Rio de Janeiro", "São Paulo", "Quito", "Toronto",
    "Vancouver", "Montreal", "Cape Town", "Zanzibar", "Casablanca", "Auckland",
    "Fiji", "Hawaii", "Goa", "Sri Lanka", "Bali",
]


async def main() -> None:
    from scrapers.osm import ingest_osm_pois

    results: dict[str, int] = {}
    failures: dict[str, str] = {}

    for i, destination in enumerate(STILL_ZERO, 1):
        try:
            count = await ingest_osm_pois(destination)
            results[destination] = count
            logger.info("[%d/%d] %s: %d POIs ingested", i, len(STILL_ZERO), destination, count)
        except Exception as e:
            failures[destination] = str(e)
            logger.warning("[%d/%d] %s: FAILED (%s)", i, len(STILL_ZERO), destination, e)
        await asyncio.sleep(DELAY_SECONDS)

    still_zero = [d for d, c in results.items() if c == 0]
    logger.info("=== Summary ===")
    logger.info("Total destinations attempted: %d", len(STILL_ZERO))
    logger.info("Succeeded (>0 POIs): %d", sum(1 for c in results.values() if c > 0))
    logger.info("Zero POIs returned: %d -> %s", len(still_zero), still_zero)
    logger.info("Exceptions: %d -> %s", len(failures), failures)


if __name__ == "__main__":
    asyncio.run(main())
