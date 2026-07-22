"""One-off: recompute budget_comparison_dataset.json anchors from the current
estimator output. Run: python -m scripts._regen_budget_anchors [--write]"""
import asyncio
import json
import sys
from pathlib import Path

from core.budget_estimator import estimate_bare_minimum_budget

DATASET = Path("eval/budget_comparison_dataset.json")


async def main(write: bool) -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    for case in data["cases"]:
        tc = {
            "group": case["group"],
            "destination": case["destination"],
            "origin": case["origin"],
            "scope": case["scope"],
            "dates": case["dates"],
        }
        est = await estimate_bare_minimum_budget(tc, case.get("traveller_level_hint"))
        total = est["total_inr"]
        low, high = round(total * 0.85), round(total * 1.15)
        b = est["breakdown"]
        print(
            f"{case['id']}: total ₹{total:,} (was low={case['anchor_low_inr']:,}/high={case['anchor_high_inr']:,})"
            f" -> low={low:,}/high={high:,} | flights={b['flights_inr']:,} stay={b['stay_inr']:,} food={b['food_inr']:,}"
            f" | stay_grounded={est['stay_community_based']} food_grounded={est['food_community_based']}"
            f" flight_dist={est['flight_distance_based']} tier={est['destination_tier']} peak={est['peak_season']}"
        )
        case["_new_total"] = total
        case["anchor_low_inr"] = low
        case["anchor_high_inr"] = high

    if write:
        for case in data["cases"]:
            total = case.pop("_new_total")
            # Rewrite the total figure inside anchor_source, preserving the rest.
            src = case["anchor_source"]
            import re
            case["anchor_source"] = re.sub(
                r"=\s*₹[\d,]+\s*total", f"= ₹{total:,} total", src, count=1
            )
        DATASET.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print("\nWROTE", DATASET)


if __name__ == "__main__":
    asyncio.run(main("--write" in sys.argv))
