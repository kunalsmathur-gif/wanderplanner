"""HyDE (Hypothetical Document Embeddings) query augmentation — docs §3G.

Instead of embedding the raw, sparse query text ("things to do in Tokyo
digital_nomad moderate trip hidden gems local tips"), we first synthesize a
plausible-looking passage of the kind that would actually appear in a travel
guide or forum post, then embed *that*. Dense passage-style text sits much
closer in embedding space to real corpus content (which is also dense prose)
than a keyword-ish query is, which measurably improves recall for
niche/persona-specific queries.

This is a deliberately template-based implementation (no LLM round-trip):
it keeps retrieval latency and cost unchanged while still moving the query
into "prose passage" space, matching the lightweight pseudocode in the
strategy doc. A full LLM-generated hypothetical document is a possible
future upgrade but adds an extra network call + failure mode to every
retrieval, which isn't justified yet.
"""
from __future__ import annotations

_PERSONA_HOOKS: dict[str, str] = {
    "digital_nomad": "reliable wifi, coworking spaces and laptop-friendly cafes",
    "sports_fitness": "gyms, running trails and active outdoor experiences",
    "pet_parent": "dog-friendly parks, cafes and pet-welcoming accommodation",
    "foodie": "must-try local dishes, street food stalls and acclaimed restaurants",
    "photographer": "photogenic viewpoints, golden-hour spots and unique architecture",
    "family": "kid-friendly activities, stroller-accessible sights and family dining",
    "budget": "free attractions, affordable eats and money-saving local tips",
    "luxury": "high-end stays, fine dining and premium experiences",
    "nightlife": "bars, live music venues and late-night hotspots",
    "solo": "safe solo-friendly spots and easy ways to meet other travelers",
}

_PACE_HOOKS: dict[str, str] = {
    "relaxed": "with plenty of downtime between a few well-chosen highlights",
    "moderate": "balancing well-known sights with a couple of local favorites each day",
    "packed": "packing in as many highlights, neighborhoods and experiences as possible",
}


def generate_hypothetical_passage(
    destination: str, purpose: str = "", pace: str = "", personas: list[str] | None = None
) -> str:
    """Build a synthetic "ideal" travel-guide passage for `destination`.

    The result reads like an actual guide excerpt so that embedding it lands
    closer to real wiki/reddit chunks than the raw structured query would.
    """
    personas = personas or []
    persona_bits = [_PERSONA_HOOKS[p] for p in personas if p in _PERSONA_HOOKS]
    pace_bit = _PACE_HOOKS.get(pace, "with a good mix of top sights and local experiences")
    purpose_bit = f"for a {purpose} trip" if purpose else "for travelers"

    sentence = (
        f"Top things to do and see in {destination} {purpose_bit}, {pace_bit}. "
        f"Includes hidden gems away from the crowds, local tips on where to eat, "
        f"and practical advice on getting around safely."
    )
    if persona_bits:
        sentence += " Especially good for travelers looking for " + ", ".join(persona_bits) + "."

    return sentence
