"""India long-weekend finder — pure date math over the static holiday calendar.

Given a home state, computes the upcoming long-weekend windows for that state
by combining the national + state holiday calendar (``services/data/
india_holidays.json``) with ordinary Saturday/Sunday weekends, including
"bridge day" cases where taking 1-2 leave days connects a holiday to a
weekend (e.g. a Thursday holiday + one Friday leave day yields 4 days off).

No LLM calls, no database, no network calls — fully deterministic and
unit-testable, by design (see docs/plans/india-workation-finder-plan.md,
"Data/quality notes": "Long-weekend computation is pure date math once the
holiday calendar exists").

``services/data/india_holidays.json`` is a **curated, periodically-refreshed
static dataset**, not a live feed — same pattern as the Wikivoyage/OSM static-
+-periodic-refresh data described in docs/data-freshness-strategy.md. It must
be refreshed annually (ahead of each new calendar year) by appending that
year's national + state gazetted holiday dates; see the dataset's own
``_meta`` block for the years currently covered and the last refresh date.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

HOLIDAYS_PATH = Path(__file__).resolve().parent / "data" / "india_holidays.json"

_SATURDAY = 5
_SUNDAY = 6


class Holiday(BaseModel):
    """A single named holiday on a given date."""

    name: str
    date: date


class LongWeekendWindow(BaseModel):
    """A contiguous span of days off (holiday(s) + weekend +/- bridge leave)."""

    start_date: date
    end_date: date
    total_days_off: int
    leave_days_needed: int
    reason: str
    value: float = Field(description="total_days_off / max(leave_days_needed, 1); higher is better")


@lru_cache(maxsize=1)
def _load_dataset() -> dict:
    with HOLIDAYS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _known_states() -> list[str]:
    return sorted(_load_dataset().get("states", {}).keys())


def get_holidays_for_state(state: str, year: int) -> list[Holiday]:
    """Return national + state holidays for ``state`` falling in ``year``.

    Raises ``ValueError`` if ``state`` is not present in the curated dataset
    (see module docstring — this is a curated list, not every state/UT may
    be covered, and typos should fail loudly rather than silently return no
    state-specific holidays).
    """
    dataset = _load_dataset()
    states = dataset.get("states", {})
    if state not in states:
        known = ", ".join(_known_states())
        raise ValueError(f"Unknown state {state!r}. Known states: {known}")

    records = list(dataset.get("national", [])) + list(states[state])
    holidays = [
        Holiday(name=r["name"], date=date.fromisoformat(r["date"]))
        for r in records
    ]
    holidays = [h for h in holidays if h.date.year == year]
    # De-duplicate same-day holidays (e.g. a national + state holiday falling
    # on the same date), keeping a combined name for the reason text.
    by_date: dict[date, list[str]] = {}
    for h in holidays:
        by_date.setdefault(h.date, []).append(h.name)
    merged = [Holiday(name=" / ".join(names), date=d) for d, names in by_date.items()]
    return sorted(merged, key=lambda h: h.date)


def _is_weekend(d: date) -> bool:
    return d.weekday() in (_SATURDAY, _SUNDAY)


def get_long_weekends(state: str, year: int | None = None) -> list[LongWeekendWindow]:
    """Compute ranked long-weekend windows for ``state`` in ``year``.

    ``year`` defaults to the current calendar year (``date.today().year``) if
    omitted. Raises ``ValueError`` for a state not present in the curated
    dataset (see ``get_holidays_for_state``).

    Algorithm:
    1. Build the set of "days off" for the year: every Saturday/Sunday plus
       every holiday date for the state.
    2. Group those days off into maximal contiguous runs (a "free run").
    3. For each pair of free runs separated by a gap of 1-2 ordinary weekdays
       (a "bridge"), also consider the merged window with the gap days
       counted as leave days needed — this captures the "holiday on Thursday,
       take Friday off, get a 4-day weekend" case.
    4. Rank all candidate windows by value (days_off / max(leave_days, 1)),
       descending; ties broken by earlier start_date.
    """
    if year is None:
        year = date.today().year

    holidays = get_holidays_for_state(state, year)
    holiday_by_date = {h.date: h.name for h in holidays}

    start = date(year, 1, 1)
    end = date(year, 12, 31)
    all_days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    off_days = {d for d in all_days if _is_weekend(d) or d in holiday_by_date}

    free_runs = _contiguous_runs(off_days, start, end)

    windows: list[LongWeekendWindow] = []
    for run in free_runs:
        # Skip plain weekends with no holiday involved — those aren't "long
        # weekends" in the product sense, just the ordinary Sat/Sun off.
        if not any(d in holiday_by_date for d in run):
            continue
        windows.append(_window_from_run(run, holiday_by_date, leave_days=0))

    # Bridge candidates: merge two runs separated by a 1 or 2 weekday gap.
    for i in range(len(free_runs) - 1):
        run_a = free_runs[i]
        run_b = free_runs[i + 1]
        gap_start = run_a[-1] + timedelta(days=1)
        gap_end = run_b[0] - timedelta(days=1)
        gap_days = (gap_end - gap_start).days + 1
        if gap_days < 1 or gap_days > 2:
            continue
        gap = [gap_start + timedelta(days=k) for k in range(gap_days)]
        if any(_is_weekend(d) or d in holiday_by_date for d in gap):
            continue  # not actually a plain-weekday bridge
        merged_run = run_a + gap + run_b
        windows.append(_window_from_run(merged_run, holiday_by_date, leave_days=gap_days))

    windows.sort(key=lambda w: (-w.value, w.start_date))
    return windows


def drop_elapsed_windows(
    windows: list[LongWeekendWindow], today: date | None = None
) -> list[LongWeekendWindow]:
    """Filters out windows that have already fully elapsed as of ``today``
    (defaults to ``date.today()``) — a user can't plan a trip for a long
    weekend that's already over. A window already in progress (start in the
    past, end today-or-later) is kept since there may still be actionable
    days left.

    Deliberately **not** baked into ``get_long_weekends`` itself: that
    function is pinned to an explicit ``year`` and tested with fixed
    historical-looking dates independent of the real wall-clock date (see
    ``test_long_weekend.py``'s module docstring) — mixing in a
    ``date.today()``-dependent filter there would make those fixtures
    flaky/order-dependent on whenever the suite happens to run. Callers that
    serve live traffic (the router, the recommend chain) apply this filter
    themselves after fetching windows for the *current* year.
    """
    if today is None:
        today = date.today()
    return [w for w in windows if w.end_date >= today]


def _contiguous_runs(off_days: set[date], start: date, end: date) -> list[list[date]]:
    runs: list[list[date]] = []
    current: list[date] = []
    d = start
    while d <= end:
        if d in off_days:
            current.append(d)
        else:
            if current:
                runs.append(current)
                current = []
        d += timedelta(days=1)
    if current:
        runs.append(current)
    return runs


def _window_from_run(run: list[date], holiday_by_date: dict[date, str], leave_days: int) -> LongWeekendWindow:
    start_date = run[0]
    end_date = run[-1]
    total_days_off = (end_date - start_date).days + 1
    names = [holiday_by_date[d] for d in run if d in holiday_by_date]
    reason = _build_reason(names, has_weekend=any(_is_weekend(d) for d in run))
    value = total_days_off / max(leave_days, 1)
    return LongWeekendWindow(
        start_date=start_date,
        end_date=end_date,
        total_days_off=total_days_off,
        leave_days_needed=leave_days,
        reason=reason,
        value=value,
    )


def _build_reason(holiday_names: list[str], has_weekend: bool) -> str:
    parts = list(dict.fromkeys(holiday_names))  # de-dupe, preserve order
    if parts and has_weekend:
        return " + ".join(parts) + " + weekend"
    if parts:
        return " + ".join(parts)
    return "weekend"
