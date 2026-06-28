"""Rate-limit tests for /api/validate (max 10 per user per 60s)."""
import pytest


async def _get_auth_header(client, email="validate_rl@example.com") -> dict:
    """Sign up + log in; return a headers dict with the session cookie."""
    await client.post("/api/auth/signup", json={"email": email, "password": "password123"})
    r = await client.post("/api/auth/login", json={"email": email, "password": "password123"})
    token = r.cookies.get("token")
    return {"cookie": f"token={token}"}


@pytest.mark.asyncio
async def test_validate_rate_limit(client):
    """The 11th call to /api/validate within 60s for the same user must return 429."""
    headers = await _get_auth_header(client, "validate_rl@example.com")

    # The endpoint validates cloud credentials — we send a deliberately minimal
    # (invalid) payload so each call fails fast without hitting real cloud APIs.
    # All we care about here is the HTTP status coming from the rate limiter.
    payload = {
        "cloud_provider": "aws",
        "regions": ["us-east-1"],
        "services": ["ec2"],
        "aws_access_key_id": "AKIA0000000000000000",
        "aws_secret_access_key": "fake/secret/key/0000000000000000000000000",
    }

    for _ in range(10):
        await client.post("/api/validate", json=payload, headers=headers)

    r = await client.post("/api/validate", json=payload, headers=headers)
    assert r.status_code == 429, f"Expected 429, got {r.status_code}"


@pytest.mark.asyncio
async def test_validate_requires_auth(client):
    """Unauthenticated request must return 401 before hitting rate limit logic."""
    r = await client.post(
        "/api/validate",
        json={"cloud_provider": "aws", "regions": ["us-east-1"], "services": ["ec2"]},
    )
    assert r.status_code == 401
