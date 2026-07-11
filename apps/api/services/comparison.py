from __future__ import annotations
"""Comparison engine — assembles side-by-side destination data with AI qualitative analysis."""

import asyncio
import json
import logging

from google import genai as google_genai

from core.config import settings
from core.llm_client import track_gemini_usage
from models.itinerary import ComparisonResponse, ComparisonParameter
from models.trip import TripConfig, DestinationInput
from services.geocode import geocode_city
from services.best_time import _fetch_weather

logger = logging.getLogger(__name__)

_QUALITATIVE_PROMPT = """\
You are a world travel expert. Compare two travel destinations for an Indian traveller.

Destination A: {dest_a}
Destination B: {dest_b}

Trip context:
- Purpose: {purpose}
- Duration: {duration} days
- Group: {group}
- Budget (INR): {budget}
- Themes: {themes}
- Travel pace: {pace}

Return a JSON array of exactly 10 comparison parameters. Each element must be:
{{
  "parameter": "Short label (3-5 words)",
  "values": {{
    "{dest_a}": "Concise value (1-2 sentences max)",
    "{dest_b}": "Concise value (1-2 sentences max)"
  }},
  "winner": "{dest_a}" | "{dest_b}" | null
}}

Parameters to cover (use these exact labels):
1. "Food & Cuisine"
2. "Culture & Heritage"
3. "Adventure Activities"
4. "Family Friendliness"
5. "Nightlife & Entertainment"
6. "English Proficiency"
7. "Safety & Crime"
8. "Best Travel Season"
9. "Cost of Living"
10. "Crowd & Tourism Level"

Rules:
- winner is the better destination for the trip context provided, or null if comparable
- Keep each value under 20 words
- Be factual and specific, not generic
- Respond with ONLY the JSON array, no markdown fences
"""


async def build_comparison(
    destinations: list[DestinationInput], trip_config: TripConfig
) -> ComparisonResponse:
    params: list[ComparisonParameter] = []
    partial_failures: list[str] = []
    weather_data: dict[str, dict] = {}

    # Fetch weather data for both destinations concurrently
    async def _fetch_dest_data(dest: DestinationInput) -> None:
        try:
            geo = await geocode_city(dest.city)
            weather = await _fetch_weather(dest.city)
            avg_temp = (
                sum(w.avg_temp_c for w in weather) / len(weather) if weather else None
            )
            weather_data[dest.city] = {"geo": geo, "avg_temp": avg_temp}
        except Exception:
            partial_failures.append(dest.city)
            weather_data[dest.city] = {}

    await asyncio.gather(*[_fetch_dest_data(d) for d in destinations])

    dest_names = [d.city for d in destinations]

    # Static factual parameters
    weather_param = _compare_weather(dest_names, weather_data)
    if weather_param:
        params.append(weather_param)

    # Deterministic bare-minimum budget estimate per destination (⭐ NEW,
    # free-tools-only — same core.budget_estimator used in the wizard chat's
    # budget recommendations, so "which destination is cheaper" isn't left
    # purely to the LLM's qualitative "Cost of Living" guess below).
    budget_param = _compare_bare_minimum_budget(destinations, trip_config)
    if budget_param:
        params.append(budget_param)

    # AI qualitative parameters (10 rich dimensions)
    if len(destinations) >= 2:
        ai_params = await _compare_qualitative(destinations[0].city, destinations[1].city, trip_config)
        params.extend(ai_params)

    params = [p for p in params if p is not None]
    _annotate_winners(params)

    return ComparisonResponse(comparison=params, partial_failures=partial_failures)


def _compare_bare_minimum_budget(
    destinations: list[DestinationInput], trip_config: TripConfig
) -> ComparisonParameter | None:
    """Real computed (not LLM-guessed) bare-minimum flights+stay+food estimate
    per destination, using the trip's own group/dates. Best-effort — skipped
    entirely if group size isn't known yet (same rule as the wizard chat
    recommendation: never guess headcount)."""
    from core.budget_estimator import estimate_bare_minimum_budget

    values: dict[str, str] = {}
    totals: dict[str, float] = {}
    for dest in destinations:
        try:
            config_dict = trip_config.model_dump()
            config_dict["destination"] = {"city": dest.city, "country": dest.country}
            estimate = estimate_bare_minimum_budget(config_dict)
        except Exception:
            estimate = None
        if estimate is None:
            return None  # group size unknown — skip this parameter entirely
        values[dest.city] = f"~₹{estimate['total_inr']:,} total (₹{estimate['per_person_inr']:,}/person)"
        totals[dest.city] = estimate["total_inr"]

    param = ComparisonParameter(parameter="Estimated Trip Budget (bare minimum)", values=values)
    if totals:
        param.winner = min(totals, key=totals.__getitem__)  # cheaper destination wins
        param.highlight = "winner"
    return param


def _compare_weather(names: list[str], data: dict) -> ComparisonParameter | None:
    values = {}
    for name in names:
        temp = data.get(name, {}).get("avg_temp")
        values[name] = f"{round(temp, 1)}°C annual avg" if temp is not None else "Data unavailable"
    return ComparisonParameter(parameter="Average Temperature", values=values)


async def _compare_qualitative(
    dest_a: str, dest_b: str, trip_config: TripConfig
) -> list[ComparisonParameter]:
    """Ask Gemini for 10 qualitative comparison parameters."""
    if settings.llm_provider == "mock" or not settings.gemini_api_key:
        return _mock_qualitative(dest_a, dest_b)

    group = trip_config.group
    group_desc = f"{group.adults} adult(s)"
    if group.kids:
        group_desc += f" + {len(group.kids)} kid(s)"

    prompt = _QUALITATIVE_PROMPT.format(
        dest_a=dest_a,
        dest_b=dest_b,
        purpose=trip_config.purpose or "leisure",
        duration=trip_config.dates.duration_days or 7,
        group=group_desc,
        budget=trip_config.budget.amount,
        themes=", ".join(trip_config.themes) if trip_config.themes else "general",
        pace=trip_config.pace,
    )

    try:
        client = google_genai.Client(api_key=settings.gemini_api_key)
        models_to_try = [settings.gemini_model, "gemini-2.5-flash-lite-preview-06-17", "gemini-1.5-flash"]
        max_attempts = 4
        raw = ""

        for model_name in models_to_try:
            for attempt in range(max_attempts):
                try:
                    def _call_sync(m: str = model_name):  # noqa: E731
                        return client.models.generate_content(model=m, contents=prompt)

                    resp = await asyncio.get_event_loop().run_in_executor(None, _call_sync)
                    track_gemini_usage(resp, model=model_name, purpose="comparison")
                    raw = resp.text or ""
                    break  # success
                except Exception as exc:
                    is_transient = any(kw in str(exc) for kw in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
                    if is_transient and attempt < max_attempts - 1:
                        await asyncio.sleep(5 * (2 ** attempt))
                        continue
                    elif is_transient:
                        break  # try next model
                    raise
            else:
                continue  # inner loop didn't break → raw set, exit model loop
            if raw:
                break

        rows = json.loads(raw.strip())

        return [
            ComparisonParameter(
                parameter=row["parameter"],
                values={dest_a: str(row["values"].get(dest_a, "—")),
                        dest_b: str(row["values"].get(dest_b, "—"))},
                winner=row.get("winner"),
            )
            for row in rows
            if isinstance(row, dict)
        ]
    except Exception as exc:
        logger.warning("AI comparison failed: %s — using fallback", exc)
        return _mock_qualitative(dest_a, dest_b)


def _mock_qualitative(dest_a: str, dest_b: str) -> list[ComparisonParameter]:
    labels = [
        "Food & Cuisine",
        "Culture & Heritage",
        "Adventure Activities",
        "Family Friendliness",
        "Nightlife & Entertainment",
        "English Proficiency",
        "Safety & Crime",
        "Best Travel Season",
        "Cost of Living",
        "Crowd & Tourism Level",
    ]
    return [
        ComparisonParameter(
            parameter=label,
            values={dest_a: "See travel guides", dest_b: "See travel guides"},
        )
        for label in labels
    ]


def _annotate_winners(params: list[ComparisonParameter]) -> None:
    for param in params:
        if param.winner:
            continue  # already set by AI
        numeric_vals: dict[str, float] = {}
        for k, v in param.values.items():
            try:
                numeric_vals[k] = float(str(v).split("°")[0].split(" ")[0])
            except (ValueError, AttributeError):
                pass
        if len(numeric_vals) == len(param.values):
            winner = max(numeric_vals, key=numeric_vals.__getitem__)
            param.winner = winner
            param.highlight = "winner"
