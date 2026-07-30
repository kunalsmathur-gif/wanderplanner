"""One-off CLI to grant `is_admin` to an existing user by email.

Why this exists: `is_admin` is deliberately never settable via signup, and
the only in-app path is an existing admin approving a pending request
(`POST /api/admin/requests/{id}/approve`, see `routers/admin.py`). That's a
bootstrap problem the first time there are zero admins — this script is the
escape hatch, meant to be run directly against a database (local `dev.db`
or prod via `DATABASE_URL`/Railway), not exposed as an API endpoint.

Usage (from apps/api, venv active):
    python scripts/grant_admin.py someone@example.com

Against Railway prod, run it with the prod DATABASE_URL in scope, e.g.:
    railway run --service <api-service> python scripts/grant_admin.py someone@example.com

The user must already have signed up (this does not create accounts). Safe
to re-run — no-ops if the user is already an admin.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select  # noqa: E402

from db import AsyncSessionLocal  # noqa: E402
from db_models import User  # noqa: E402


async def grant_admin(email: str) -> None:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"No user found with email {email!r} — they must sign up first.")
            raise SystemExit(1)
        if user.is_admin:
            print(f"{email} is already an admin. No change made.")
            return
        user.is_admin = True
        await session.commit()
        print(f"Granted admin access to {email} (user id {user.id}).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/grant_admin.py <email>")
        raise SystemExit(1)
    asyncio.run(grant_admin(sys.argv[1]))
