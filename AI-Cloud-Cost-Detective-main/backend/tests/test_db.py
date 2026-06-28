"""In-memory DB layer unit tests (no real Postgres required)."""
import pytest
import db as _db


@pytest.mark.asyncio
async def test_create_and_get_user():
    user = await _db.create_user("unit@example.com", "hashed_pw")
    assert user is not None
    assert user["email"] == "unit@example.com"

    fetched = await _db.get_user_by_email("unit@example.com")
    assert fetched is not None
    assert fetched["id"] == user["id"]


@pytest.mark.asyncio
async def test_get_user_missing():
    result = await _db.get_user_by_email("missing@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_token_revocation():
    from datetime import datetime, timezone, timedelta
    jti = "test-jti-123"
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await _db.revoke_token(jti, expires)
    assert await _db.is_token_revoked(jti)
    assert not await _db.is_token_revoked("different-jti")


@pytest.mark.asyncio
async def test_purge_old_analyses_in_memory():
    from datetime import datetime, timezone, timedelta
    # Inject a stale record directly into the in-memory store
    old_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    _db._analyses_store["old-id"] = {"user_id": 1, "created_at": old_time}
    deleted = await _db.purge_old_analyses(days=2)
    assert deleted >= 1
    assert "old-id" not in _db._analyses_store
