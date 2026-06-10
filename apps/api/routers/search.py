from fastapi import APIRouter, Query
from models.common import SearchResponse
from services.search import semantic_search

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2),
    destination: str = Query(...),
    limit: int = Query(default=10, ge=1, le=30),
):
    results = await semantic_search(q, destination, limit)
    return SearchResponse(results=results)
