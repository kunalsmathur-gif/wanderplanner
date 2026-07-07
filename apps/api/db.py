"""Async SQLAlchemy engine/session setup for Postgres (users, sessions, analytics events).

Kept separate from the existing `models/` package (which holds request/response
Pydantic schemas) — this module and `db_models/` own persistence.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# SQLite (used for local dev / tests) does not enforce FK constraints by
# default, so `ondelete="CASCADE"`/`"SET NULL"` clauses defined on our models
# silently no-op unless enabled per-connection — Postgres (prod) enforces FKs
# natively and is unaffected by this. Without this, cascade-deleting a user's
# refresh_tokens/password_reset_tokens/events on account deletion or admin
# purge only works in prod, not in local SQLite testing.
if engine.url.get_backend_name() == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
