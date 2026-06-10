"""Conftest — shared pytest fixtures."""
import pytest

# Ensures async test loop is set up correctly for all async tests.
pytest_plugins = ("pytest_asyncio",)
