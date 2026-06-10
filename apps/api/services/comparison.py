"""Comparison engine — assembles side-by-side destination data."""
from models.itinerary import ComparisonResponse, ComparisonParameter
from models.trip import TripConfig, DestinationInput
from services.geocode import geocode_city
from services.best_time import _fetch_weather


async def build_comparison(
    destinations: list[DestinationInput], trip_config: TripConfig
) -> ComparisonResponse:
    params: list[ComparisonParameter] = []
    partial_failures: list[str] = []
    data: dict[str, dict] = {}

    for dest in destinations:
        try:
            geo = await geocode_city(dest.city)
            weather = await _fetch_weather(dest.city)
            avg_temp = (
                sum(w.avg_temp_c for w in weather) / len(weather) if weather else None
            )
            data[dest.city] = {"geo": geo, "avg_temp": avg_temp, "weather": weather}
        except Exception:
            partial_failures.append(dest.city)
            data[dest.city] = {}

    dest_names = [d.city for d in destinations]

    params.append(_compare_weather(dest_names, data))
    params.append(_compare_budget_estimate(dest_names, trip_config))
    params.append(_compare_visa_friction(dest_names))

    params = [p for p in params if p is not None]
    _annotate_winners(params)

    return ComparisonResponse(comparison=params, partial_failures=partial_failures)


def _compare_weather(names: list[str], data: dict) -> ComparisonParameter | None:
    values = {}
    for name in names:
        temp = data.get(name, {}).get("avg_temp")
        values[name] = f"{round(temp, 1)}°C avg" if temp is not None else "Data unavailable"
    return ComparisonParameter(parameter="Average Temperature", values=values)


def _compare_budget_estimate(
    names: list[str], trip_config: TripConfig
) -> ComparisonParameter:
    # Placeholder: real cost-of-living data deferred to Phase 2 API integrations
    values = {n: "See booking platforms" for n in names}
    return ComparisonParameter(
        parameter="Total Estimated Budget",
        unit=trip_config.budget.currency,
        values=values,
    )


def _compare_visa_friction(names: list[str]) -> ComparisonParameter:
    values = {n: "Check Wikivoyage visa section" for n in names}
    return ComparisonParameter(parameter="Visa Requirements", values=values)


def _annotate_winners(params: list[ComparisonParameter]):
    for param in params:
        numeric_vals = {}
        for k, v in param.values.items():
            try:
                numeric_vals[k] = float(str(v).split("°")[0].split(" ")[0])
            except (ValueError, AttributeError):
                pass
        if len(numeric_vals) == len(param.values):
            winner = max(numeric_vals, key=numeric_vals.__getitem__)
            param.winner = winner
            param.highlight = "winner"
