from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, Request

from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from core.validation import MAX_CITY_LEN, validate_query_param
from models.common import GeocodeResponse
from services.geocode import geocode_city

router = APIRouter()

# Nominatim's own format: comma-separated ISO 3166-1 alpha-2 codes. Anything
# else is passed straight through to a third party as a query parameter, so it
# is checked here rather than trusted.
_COUNTRY_CODES_RE = re.compile(r"^[A-Za-z]{2}(,[A-Za-z]{2})*$")


@router.get("/geocode", response_model=GeocodeResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def geocode(
    request: Request,
    q: str = Query(..., min_length=2, max_length=MAX_CITY_LEN),
    countrycodes: str = Query(default="", max_length=64),
):
    q = validate_query_param(q, field="q", max_length=MAX_CITY_LEN, require_alphanumeric=True)
    if countrycodes and not _COUNTRY_CODES_RE.match(countrycodes):
        raise HTTPException(
            status_code=422,
            detail="countrycodes must be comma-separated two-letter country codes (e.g. 'in,np')",
        )
    return await geocode_city(q, countrycodes=countrycodes)
