"""Rate-limiting tests."""
import pytest


@pytest.mark.asyncio
async def test_login_rate_limit_by_email(client):
    """After 10 failed logins for the same email within 60s, the 11th should 429."""
    await client.post("/api/auth/signup", json={"email": "rl@example.com", "password": "password123"})
    for _ in range(10):
        await client.post("/api/auth/login", json={"email": "rl@example.com", "password": "wrong"})
    r = await client.post("/api/auth/login", json={"email": "rl@example.com", "password": "wrong"})
    assert r.status_code == 429
