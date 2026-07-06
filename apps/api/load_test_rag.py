"""
Retrieval load test for WanderPlanner's RAG pipeline.

Runs IN-PROCESS (imports the app's own service/core modules) rather than over
HTTP, because local dev uses an in-memory Qdrant instance (QDRANT_URL=:memory:)
that only exists inside a single process. This also lets us isolate the
retrieval layer itself (embedding + Qdrant search + RRF + summarisation) from
web-server/HTTP overhead.

Usage:
    cd apps/api && .venv/bin/python load_test_rag.py
"""
from __future__ import annotations

import asyncio
import random
import statistics
import time
import uuid

from qdrant_client.models import PointStruct

from core.config import settings
from core.embeddings import embed
from core.qdrant import get_qdrant
from models.trip import TripConfig, DestinationInput
from services.search import semantic_search, retrieve_context, summarise_context

DESTINATIONS = ["Paris", "Tokyo", "Bali", "New York", "Rome"]
PERSONAS = ["foodie", "adventure", "culture", "relaxation", "digital_nomad"]
PURPOSES = ["honeymoon", "solo_backpacking", "family_vacation", "business", "friends_trip"]

# ~120-word synthetic paragraphs to approximate real chunk sizes (400-600 chars)
TOPIC_SENTENCES = [
    "The old town is best explored on foot early in the morning before the crowds arrive.",
    "Street food stalls near the central market serve the most authentic local dishes.",
    "Public transport is reliable, cheap, and the easiest way to reach the outer neighborhoods.",
    "A short day trip to the coastline is highly recommended for first-time visitors.",
    "The historic quarter has cobblestone streets, small cafes, and independent bookshops.",
    "Safety is generally good, but keep an eye on belongings in crowded tourist areas.",
    "Locals recommend visiting the rooftop bars at sunset for the best skyline views.",
    "The museum district gets very busy on weekends, so book tickets in advance.",
    "Budget travelers can find good hostels near the train station at low prices.",
    "The night market is a must-visit for street food, crafts, and live music.",
]


def _synthetic_chunk(dest: str, idx: int) -> str:
    body = " ".join(random.sample(TOPIC_SENTENCES, k=4))
    return f"{dest} travel guide, section {idx}: {body}"


def seed_data(per_destination: int = 60) -> None:
    """Populate the in-memory wiki + reddit collections with synthetic chunks."""
    client = get_qdrant()
    texts, payloads = [], []

    for dest in DESTINATIONS:
        for i in range(per_destination):
            texts.append(_synthetic_chunk(dest, i))
            payloads.append({
                "destination": dest,
                "text": texts[-1],
                "source": "synthetic",
                "source_url": f"https://example.com/{dest.lower()}/{i}",
                "published_date": "2025-01-01",
            })

    print(f"Embedding {len(texts)} synthetic chunks...")
    t0 = time.perf_counter()
    vectors = embed(texts)
    print(f"  embed() took {time.perf_counter() - t0:.2f}s for {len(texts)} texts")

    for collection in [settings.qdrant_collection_wiki, settings.qdrant_collection_reddit]:
        points = [
            PointStruct(id=str(uuid.uuid4()), vector=vectors[i], payload=payloads[i])
            for i in range(len(texts))
        ]
        client.upsert(collection_name=collection, points=points)
        print(f"  seeded {len(points)} points into '{collection}'")


def _pctile(values: list[float], p: float) -> float:
    values = sorted(values)
    k = int(round((p / 100) * (len(values) - 1)))
    return values[k]


def _random_trip_config() -> TripConfig:
    dest = random.choice(DESTINATIONS)
    return TripConfig(
        purpose=random.choice(PURPOSES),
        destination=DestinationInput(city=dest, country=""),
        personas=random.sample(PERSONAS, k=2),
        pace=random.choice(["relaxed", "moderate", "packed"]),
    )


async def _timed_call(fn, *args) -> tuple[float, bool]:
    t0 = time.perf_counter()
    try:
        await fn(*args)
        ok = True
    except Exception as e:
        print(f"  ERROR: {e}")
        ok = False
    return time.perf_counter() - t0, ok


async def run_load_test(concurrency: int, total_requests: int, label: str) -> dict:
    """Fire `total_requests` calls to retrieve_context with `concurrency` in flight at once."""
    latencies: list[float] = []
    errors = 0
    sem = asyncio.Semaphore(concurrency)

    async def worker():
        nonlocal errors
        async with sem:
            trip_config = _random_trip_config()
            elapsed, ok = await _timed_call(retrieve_context, trip_config)
            latencies.append(elapsed)
            if not ok:
                errors += 1

    t0 = time.perf_counter()
    await asyncio.gather(*[worker() for _ in range(total_requests)])
    wall_time = time.perf_counter() - t0

    result = {
        "label": label,
        "concurrency": concurrency,
        "total_requests": total_requests,
        "wall_time_s": wall_time,
        "throughput_rps": total_requests / wall_time if wall_time > 0 else float("inf"),
        "errors": errors,
        "p50_ms": _pctile(latencies, 50) * 1000,
        "p95_ms": _pctile(latencies, 95) * 1000,
        "p99_ms": _pctile(latencies, 99) * 1000,
        "min_ms": min(latencies) * 1000,
        "max_ms": max(latencies) * 1000,
        "mean_ms": statistics.mean(latencies) * 1000,
    }
    return result


def print_result(r: dict) -> None:
    print(f"\n=== {r['label']} (concurrency={r['concurrency']}, n={r['total_requests']}) ===")
    print(f"  wall time:   {r['wall_time_s']:.2f}s")
    print(f"  throughput:  {r['throughput_rps']:.2f} req/s")
    print(f"  errors:      {r['errors']}")
    print(f"  latency ms:  min={r['min_ms']:.0f}  p50={r['p50_ms']:.0f}  "
          f"p95={r['p95_ms']:.0f}  p99={r['p99_ms']:.0f}  max={r['max_ms']:.0f}  mean={r['mean_ms']:.0f}")


async def main():
    print("Seeding synthetic corpus into in-memory Qdrant...")
    seed_data(per_destination=60)

    print("\nWarm-up call (loads embedding model into memory)...")
    await retrieve_context(_random_trip_config())

    scenarios = [
        (1, 20, "Baseline — sequential (concurrency=1)"),
        (5, 50, "Light concurrent load (concurrency=5)"),
        (20, 100, "Moderate concurrent load (concurrency=20)"),
        (50, 150, "Heavy concurrent load (concurrency=50)"),
    ]

    results = []
    for concurrency, total, label in scenarios:
        r = await run_load_test(concurrency, total, label)
        print_result(r)
        results.append(r)

    print("\n\n=== SUMMARY ===")
    print(f"{'Scenario':<45} {'Concurrency':>11} {'p50 ms':>8} {'p95 ms':>8} {'RPS':>8}")
    for r in results:
        print(f"{r['label']:<45} {r['concurrency']:>11} {r['p50_ms']:>8.0f} {r['p95_ms']:>8.0f} {r['throughput_rps']:>8.2f}")

    # Key diagnostic: does per-request latency stay flat as concurrency rises?
    # If it scales up roughly linearly with concurrency, retrieval is serializing
    # (blocking the event loop) rather than truly running concurrently.
    base_p50 = results[0]["p50_ms"]
    heavy_p50 = results[-1]["p50_ms"]
    ratio = heavy_p50 / base_p50 if base_p50 else float("inf")
    print(f"\np50 latency at concurrency=50 is {ratio:.1f}x the sequential baseline p50.")
    if ratio > concurrency_threshold_hint(results):
        print("⚠️  Latency scales ~linearly with concurrency — retrieval is NOT achieving "
              "true parallelism under load (likely blocking calls on the event loop).")
    else:
        print("✅ Latency stays relatively flat under concurrency — retrieval parallelizes well.")


def concurrency_threshold_hint(results: list[dict]) -> float:
    # A generous threshold: real parallel I/O-bound work should show much less
    # than linear latency growth as concurrency increases.
    return results[-1]["concurrency"] / 5


if __name__ == "__main__":
    asyncio.run(main())
