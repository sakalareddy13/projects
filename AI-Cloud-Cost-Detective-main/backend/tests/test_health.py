"""Tests for /health endpoint."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_health_in_memory_mode(client):
    """When db.pool is None (in-memory mode), /health returns 200 with db=in-memory."""
    import db
    original_pool = db.pool
    try:
        db.pool = None
        r = await client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "in-memory"
    finally:
        db.pool = original_pool


@pytest.mark.asyncio
async def test_health_db_connected(client):
    """When db.pool is set and SELECT 1 succeeds, /health returns 200 with db=connected."""
    import db

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=1)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    original_pool = db.pool
    try:
        db.pool = mock_pool
        r = await client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "connected"
    finally:
        db.pool = original_pool


@pytest.mark.asyncio
async def test_health_db_error_returns_503(client):
    """When db.pool.acquire raises, /health returns 503 with status=degraded."""
    import db

    mock_pool = MagicMock()
    mock_pool.acquire.side_effect = Exception("connection refused")

    original_pool = db.pool
    try:
        db.pool = mock_pool
        r = await client.get("/health")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["db"] == "error"
    finally:
        db.pool = original_pool
