"""
Golden-dataset RAG retrieval evaluation for WanderPlanner.

Seeds the curated corpus in `golden_dataset.json` into Qdrant, runs each golden
query through the real `semantic_search()` retrieval path, and scores results
against the hand-labelled `relevant_ids` using standard IR metrics:

    Precision@k  — fraction of the top-k results that are relevant
    Recall@k     — fraction of all relevant docs found in the top-k
    MRR          — reciprocal rank of the first relevant result
    nDCG@k       — rank-aware relevance score (rewards relevant docs near the top)

Run against the same in-memory Qdrant used for local dev:
    cd apps/api && QDRANT_URL=":memory:" .venv/bin/python eval/run_rag_eval.py

Extend golden_dataset.json (add corpus chunks + queries) to grow coverage —
this file's metric functions and runner don't need to change.
"""
from __future__ import annotations

import asyncio
import json
import math
import statistics
import uuid
from pathlib import Path

from qdrant_client.models import PointStruct

from core.config import settings
from core.embeddings import embed
from core.qdrant import get_qdrant
from services.search import semantic_search

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"
K = 10  # cutoff for Precision@k / Recall@k / nDCG@k


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text())


def seed_corpus(corpus: list[dict]) -> None:
    """Seed the golden corpus into both wiki + reddit collections (retrieval
    reads from both), tagging each point with its golden chunk id so results
    can be matched back to relevance judgments."""
    client = get_qdrant()
    texts = [c["text"] for c in corpus]
    vectors = embed(texts)

    for collection in [settings.qdrant_collection_wiki, settings.qdrant_collection_reddit]:
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vectors[i],
                payload={
                    "destination": corpus[i]["destination"],
                    "text": corpus[i]["text"],
                    "source": "golden",
                    "source_url": "",
                    "published_date": corpus[i]["published_date"],
                    "chunk_id": corpus[i]["id"],
                },
            )
            for i in range(len(corpus))
        ]
        client.upsert(collection_name=collection, points=points)


# ---------------------------------------------------------------------------
# IR metrics
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for rid in top_k if rid in relevant_ids)
    return hits / len(top_k)


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for rid in top_k if rid in relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    dcg = sum(
        1.0 / math.log2(rank + 1) for rank, rid in enumerate(top_k, start=1) if rid in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def evaluate_query(q: dict) -> dict:
    relevant = set(q["relevant_ids"])

    hits = await semantic_search(q["query"], q["destination"], limit=K)
    # semantic_search doesn't return chunk_id on SearchResult directly, so we
    # match retrieved text back to golden corpus ids via a lookup built by the
    # caller — see run() below, which passes text->id through a closure.
    retrieved_texts = [h.text for h in hits]

    return {
        "id": q["id"],
        "query": q["query"],
        "destination": q["destination"],
        "relevant": relevant,
        "retrieved_texts": retrieved_texts,
    }


async def run() -> None:
    data = load_dataset()
    corpus = data["corpus"]
    queries = data["queries"]

    text_to_id = {c["text"]: c["id"] for c in corpus}

    print(f"Seeding {len(corpus)} golden corpus chunks into Qdrant...")
    seed_corpus(corpus)

    print(f"Running {len(queries)} golden queries (k={K})...\n")

    per_query_metrics = []
    for q in queries:
        result = await evaluate_query(q)
        raw_ids = [text_to_id.get(t, "<unmatched>") for t in result["retrieved_texts"]]
        # semantic_search() queries both the wiki and reddit collections, and
        # the golden corpus is seeded into both (since we don't know a priori
        # which collection each real chunk would live in). This means the
        # same logical chunk can appear twice in raw results. Dedupe by first
        # occurrence so metrics reflect distinct relevant documents found,
        # not collection-seeding duplicates.
        seen = set()
        retrieved_ids = []
        for rid in raw_ids:
            if rid not in seen:
                seen.add(rid)
                retrieved_ids.append(rid)
        relevant = result["relevant"]

        p_at_k = precision_at_k(retrieved_ids, relevant, K)
        r_at_k = recall_at_k(retrieved_ids, relevant, K)
        rr = reciprocal_rank(retrieved_ids, relevant)
        ndcg = ndcg_at_k(retrieved_ids, relevant, K)

        per_query_metrics.append({
            "id": q["id"], "precision": p_at_k, "recall": r_at_k, "rr": rr, "ndcg": ndcg,
        })

        status = "✅" if rr > 0 else "❌"
        print(f"{status} {q['id']:<20} P@{K}={p_at_k:.2f}  R@{K}={r_at_k:.2f}  "
              f"RR={rr:.2f}  nDCG@{K}={ndcg:.2f}   query='{q['query']}'")
        if rr == 0:
            print(f"     expected one of {relevant}, got top-3: {retrieved_ids[:3]}")

    print("\n=== AGGREGATE (mean across all queries) ===")
    print(f"Precision@{K}: {statistics.mean(m['precision'] for m in per_query_metrics):.3f}")
    print(f"Recall@{K}:    {statistics.mean(m['recall'] for m in per_query_metrics):.3f}")
    print(f"MRR:           {statistics.mean(m['rr'] for m in per_query_metrics):.3f}")
    print(f"nDCG@{K}:       {statistics.mean(m['ndcg'] for m in per_query_metrics):.3f}")

    failed = [m["id"] for m in per_query_metrics if m["rr"] == 0]
    if failed:
        print(f"\n⚠️  {len(failed)}/{len(per_query_metrics)} queries found ZERO relevant results: {failed}")


if __name__ == "__main__":
    asyncio.run(run())
