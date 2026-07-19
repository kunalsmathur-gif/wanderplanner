"""Tests for core/config.py's production-safety validators.

Covers the cookie_samesite guard added after a real production bug: frontend
(Vercel) and backend (Railway) are different origins, so SameSite=Lax
cookies were being silently dropped on every cross-site request, which
surfaced as three separate-looking symptoms (signed-in users asked to sign
in again, signup falsely claiming a duplicate account, sign-in looping).
"""
import pytest

from core.config import Settings


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
