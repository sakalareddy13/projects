"""Shared fixtures for all backend tests."""
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use a short secret so tests don't depend on the env
os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-32-chars-long")
os.environ.setdefault("DEBUG", "true")

from main import app  # noqa: E402 — must come after env setup


@pytest_asyncio.fixture
async def client():
    """Async HTTPX client wired to the FastAPI app (no real network)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
