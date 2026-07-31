# Agent recipients config

`agent_recipients.json` controls who receives a "quotation requested" email the
moment a user asks a local expert to help book their itinerary
(`POST /agent-leads`, see `core/agent_recipients.py`).

## Sole-builder mode (default)

`agent_emails` starts empty. While it's empty, every quotation request is
emailed to **every user with `is_admin = true`** — no setup required.

## Scaling up

Once there's a real agent/ops team, list their emails here:

```json
{
  "agent_emails": ["priya@wanderplanner.org", "arjun@wanderplanner.org"]
}
```

As soon as this list is non-empty, quotation-request emails go to exactly
these addresses instead of the admin roster. No deploy or code change is
needed — the file is re-read on every request.
