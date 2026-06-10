"""Best time to travel — Wikivoyage seasonal data + Open-Meteo weather."""
import httpx

from models.common import BestTimeResponse, MonthlyWeather, BusyPeriod, LocalEvent
from services.geocode import geocode_city

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


async def get_best_time(destination: str) -> BestTimeResponse:
    weather = await _fetch_weather(destination)
    busy, events = await _fetch_seasonal_info(destination)
    best_months = _compute_best_months(weather, busy)

    return BestTimeResponse(
        destination=destination,
        monthly_weather=weather,
        busy_periods=busy,
        best_months=best_months,
        events=events,
    )


async def _fetch_weather(destination: str) -> list[MonthlyWeather]:
    try:
        geo = await geocode_city(destination)
    except Exception:
        return []

    params = {
        "latitude": geo.lat,
        "longitude": geo.lon,
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,sunshine_duration",
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temps_max = daily.get("temperature_2m_max", [])
    temps_min = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    sunshine = daily.get("sunshine_duration", [])

    monthly: dict[int, dict] = {i: {"temps": [], "precip": [], "sun": []} for i in range(1, 13)}
    for i, date in enumerate(dates):
        month = int(date.split("-")[1])
        if i < len(temps_max) and temps_max[i] is not None:
            monthly[month]["temps"].append((temps_max[i] + (temps_min[i] or 0)) / 2)
        if i < len(precip) and precip[i] is not None:
            monthly[month]["precip"].append(precip[i])
        if i < len(sunshine) and sunshine[i] is not None:
            monthly[month]["sun"].append(sunshine[i] / 3600)

    result = []
    for m in range(1, 13):
        d = monthly[m]
        result.append(MonthlyWeather(
            month=MONTHS[m - 1],
            avg_temp_c=round(sum(d["temps"]) / max(len(d["temps"]), 1), 1),
            avg_rain_mm=round(sum(d["precip"]), 1),
            sunshine_hours=round(sum(d["sun"]) / max(len(d["sun"]), 1), 1),
        ))
    return result


async def _fetch_seasonal_info(destination: str) -> tuple[list[BusyPeriod], list[LocalEvent]]:
    """Scrape Wikivoyage 'Go' section for seasonal advice."""
    from scrapers.wikivoyage import scrape_wikivoyage
    docs = await scrape_wikivoyage(destination)
    busy: list[BusyPeriod] = []
    events: list[LocalEvent] = []

    for doc in docs:
        if "go" in doc.get("section", ""):
            text = doc["text"].lower()
            if "peak" in text or "busy" in text or "crowded" in text:
                busy.append(BusyPeriod(
                    months=[],
                    label=doc["text"][:200],
                    source="wikivoyage",
                ))
        if "festival" in doc.get("text", "").lower() or "event" in doc.get("section", ""):
            events.append(LocalEvent(
                name=destination + " Local Events",
                month="",
                source="wikivoyage",
            ))

    return busy, events


def _compute_best_months(
    weather: list[MonthlyWeather], busy: list[BusyPeriod]
) -> list[str]:
    if not weather:
        return []
    scored = []
    for w in weather:
        score = w.sunshine_hours - (w.avg_rain_mm / 50)
        scored.append((w.month, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [m for m, _ in scored[:4]]
