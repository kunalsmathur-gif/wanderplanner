"""Tests for core/config.py's production-safety validators.

Covers the cookie_samesite guard added after a real production bug: frontend
(Vercel) and backend (Railway) are different origins, so SameSite=Lax
cookies were being silently dropped on every cross-site request, which
surfaced as three separate-looking symptoms (signed-in users asked to sign
in again, signup falsely claiming a duplicate account, sign-in looping).

Also covers *how* production is detected. The original guard keyed off
`ENVIRONMENT` alone, and nothing ever set that on the Railway service — so
every test below passed while the guard was inert in the one deployment it
was written to protect. The `railway_*` tests are the regression guard for
that: production detection must work off Railway's own injected vars.
"""
import pytest

from core.config import Settings, is_production

_PROD_ENV_VARS = ("ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT")


@pytest.fixture(autouse=True)
def _clear_env_markers(monkeypatch):
    """Start every test from "no deployment markers set" so a developer
    running under `railway run` (which injects RAILWAY_*) doesn't get
    different results than CI."""
    for var in _PROD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_lax_samesite_rejected_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="COOKIE_SAMESITE=lax"):
        Settings(jwt_secret="a-real-secret", cookie_samesite="lax", cookie_secure=True)


def test_none_samesite_without_secure_rejected_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="COOKIE_SAMESITE=none requires"):
        Settings(jwt_secret="a-real-secret", cookie_samesite="none", cookie_secure=False)


def test_none_samesite_with_secure_accepted_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = Settings(jwt_secret="a-real-secret", cookie_samesite="none", cookie_secure=True)
    assert settings.cookie_samesite == "none"


def test_lax_samesite_allowed_outside_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    settings = Settings(cookie_samesite="lax")
    assert settings.cookie_samesite == "lax"


# --------------------------------------------------------------------------
# Production detection — the gap that made every test above vacuous in prod
# --------------------------------------------------------------------------


def test_railway_environment_name_alone_counts_as_production(monkeypatch):
    """Railway injects RAILWAY_ENVIRONMENT_NAME and never a bare ENVIRONMENT.
    This is the exact live configuration the guard failed to fire under."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    assert is_production() is True
    with pytest.raises(ValueError, match="COOKIE_SAMESITE=lax"):
        Settings(jwt_secret="a-real-secret", cookie_samesite="lax", cookie_secure=True)


def test_railway_environment_alone_counts_as_production(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert is_production() is True
    with pytest.raises(ValueError, match="COOKIE_SAMESITE=lax"):
        Settings(jwt_secret="a-real-secret", cookie_samesite="lax", cookie_secure=True)


def test_cookie_default_would_fail_in_production(monkeypatch):
    """The default `cookie_samesite` is "lax" (correct for local dev). The
    point of the guard is that shipping that default to prod — i.e. simply
    forgetting to set COOKIE_SAMESITE on Railway — is a boot failure, not a
    silently broken sign-in flow."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with pytest.raises(ValueError, match="COOKIE_SAMESITE=lax"):
        Settings(jwt_secret="a-real-secret")


def test_railway_non_production_environment_is_not_production(monkeypatch):
    """A Railway PR/staging environment must not be held to the prod rules."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    assert is_production() is False
    settings = Settings(cookie_samesite="lax")
    assert settings.cookie_samesite == "lax"


def test_no_markers_set_is_not_production():
    assert is_production() is False


def test_default_jwt_secret_rejected_under_railway_production(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(
            jwt_secret="change-me-in-production",
            cookie_samesite="none",
            cookie_secure=True,
        )
