"""Conftest — shared pytest fixtures."""
from __future__ import annotations

from datetime import datetime, timezone
from itertools import count

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import db_models  # noqa: F401
from core.config import settings
from core.rate_limit import limiter
from core.security import generate_refresh_token, hash_password
from db import Base, get_db
from db_models import RefreshToken, User
from main import app

# Ensures async test loop is set up correctly for all async tests.
pytest_plugins = ("pytest_asyncio",)

_client_counter = count(start=1000)


@pytest.fixture(autouse=True)
def _test_safe_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "cookie_domain", "")
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    previous_enabled = limiter.enabled
    limiter.enabled = False
    limiter._storage.reset()
    yield
    limiter._storage.reset()
    limiter.enabled = previous_enabled


@pytest_asyncio.fixture
async def db_session_maker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session_maker
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session_maker):
    transport = ASGITransport(app=app, client=("127.0.0.1", next(_client_counter)))
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def user_factory(db_session_maker):
    async def factory(
        *,
        email: str,
        password: str = "Password123!",
        display_name: str | None = None,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        async with db_session_maker() as session:
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
                is_admin=is_admin,
                is_active=is_active,
                consent_accepted_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return factory


@pytest_asyncio.fixture
async def refresh_token_factory(db_session_maker):
    async def factory(*, user_id) -> tuple[str, RefreshToken]:
        raw_token, token_hash, expires_at = generate_refresh_token()
        async with db_session_maker() as session:
            token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
            session.add(token)
            await session.commit()
            await session.refresh(token)
            return raw_token, token

    return factory
