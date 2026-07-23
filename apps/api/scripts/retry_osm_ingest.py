"""One-off retry pass for OSM POI ingestion — docs/NEXT_SESSION_TODO.md item 2.

Re-ingests the destinations that were missing entirely or under-covered after
the 2026-07-15 run, using a longer delay between requests to avoid the
Overpass rate-limit collisions that caused the original gaps.

Run from apps/api with the venv active:
    venv/Scripts/python.exe scripts/retry_osm_ingest.py
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("retry_osm_ingest")

DELAY_SECONDS = 6.0

MISSING = [
    "Bangkok", "Singapore", "Hong Kong", "Taipei", "Ho Chi Minh City", "Hoi An",
    "Phuket", "Siem Reap", "Kathmandu", "Mumbai", "Delhi", "Jaipur", "Varanasi",
    "Agra", "Kolkata", "Chennai", "Bengaluru", "Kochi", "Colombo", "Maldives",
    "Abu Dhabi", "Doha", "Muscat", "Istanbul", "Baku", "Paris", "London", "Rome",
    "Barcelona", "Prague", "Vienna", "Budapest", "Lisbon", "Madrid", "Santorini",
    "Mykonos", "Dubrovnik", "Split", "Oslo", "Helsinki", "Edinburgh", "Venice",
    "Florence", "Milan", "Brussels", "Reykjavik", "Tallinn", "Warsaw", "Hamburg",
    "Seville", "Granada", "Valencia", "Marseille", "Cinque Terre", "Amalfi",
    "New York", "San Francisco", "Miami", "Las Vegas", "New Orleans", "Seattle",
    "Austin", "Washington DC", "Mexico City", "Tulum", "Havana", "Bogotá",
    "Medellin", "Lima", "Cusco", "Rio de Janeiro", "São Paulo", "Quito",
    "Toronto", "Vancouver", "Montreal", "Cape Town", "Marrakech", "Nairobi",
    "Zanzibar", "Casablanca", "Brisbane", "Auckland", "Queenstown", "Fiji",
    "Hawaii", "Honolulu",
]

LOW_COVERAGE_TOPUP = ["Goa", "Sri Lanka", "Oaxaca", "Cappadocia", "Bali"]

DESTINATIONS = MISSING + LOW_COVERAGE_TOPUP


async def main() -> None:
    from scrapers.osm import ingest_osm_pois

    results: dict[str, int] = {}
    failures: dict[str, str] = {}

    for i, destination in enumerate(DESTINATIONS, 1):
        try:
            count = await ingest_osm_pois(destination)
            results[destination] = count
            logger.info("[%d/%d] %s: %d POIs ingested", i, len(DESTINATIONS), destination, count)
        except Exception as e:
            failures[destination] = str(e)
            logger.warning("[%d/%d] %s: FAILED (%s)", i, len(DESTINATIONS), destination, e)
        await asyncio.sleep(DELAY_SECONDS)

    still_zero = [d for d, c in results.items() if c == 0]
    logger.info("=== Summary ===")
    logger.info("Total destinations attempted: %d", len(DESTINATIONS))
    logger.info("Succeeded (>0 POIs): %d", sum(1 for c in results.values() if c > 0))
    logger.info("Zero POIs returned: %d -> %s", len(still_zero), still_zero)
    logger.info("Exceptions: %d -> %s", len(failures), failures)


if __name__ == "__main__":
    asyncio.run(main())
