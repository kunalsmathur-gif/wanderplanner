"""Conftest — shared pytest fixtures."""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
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


class _StubVectors(list):
    """A list that also answers `.tolist()`, matching what sentence-transformers
    returns (a numpy array) closely enough for `core/embeddings.py`."""

    def tolist(self) -> list:
        return list(self)


def _deterministic_vector(text: str, dims: int = 384) -> list[float]:
    """A stable unit vector derived from `text`.

    Deterministic and text-derived on purpose, not random: the cache tests
    depend on real similarity semantics — the same trip config must embed
    identically (so a stored itinerary is found again), while an unrelated
    destination must land far enough away to fall below the cosine threshold.
    A random or constant stub would make one of those two tests pass for the
    wrong reason.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [(digest[i % len(digest)] - 127.5) / 127.5 for i in range(dims)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


@pytest.fixture
def stub_embedding_models(monkeypatch: pytest.MonkeyPatch):
    """Replace the sentence-transformers models with deterministic stubs.

    `sentence-transformers` lives in `requirements-ml.txt` (~3GB with PyTorch)
    and is deliberately *not* installed in CI, so anything reaching a real
    model raises `RuntimeError: sentence-transformers not installed` there
    while passing on a dev machine — a local/CI split that hid these tests
    from CI entirely.

    Patched at `get_embedder`/`get_reranker` rather than at `embed`: those are
    resolved lazily inside `embed()`/`rerank_scores()`, so this covers every
    caller no matter how each module imported them. Patching `embed` itself
    would miss `services/search.py`, which binds it at import time.
    """

    class _StubEncoder:
        def encode(self, texts, **_kwargs):
            return _StubVectors(_deterministic_vector(t) for t in texts)

    class _StubReranker:
        def predict(self, pairs, **_kwargs):
            # Descending, so ordering is stable and the top result is the first
            # candidate — the reranker's *ranking* behaviour has its own tests.
            return _StubVectors(1.0 - (i * 0.01) for i, _ in enumerate(pairs))

    monkeypatch.setattr("core.embeddings.get_embedder", lambda: _StubEncoder())
    monkeypatch.setattr("core.embeddings.get_reranker", lambda: _StubReranker())


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
                consent_accepted_at=datetime.now(UTC),
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
