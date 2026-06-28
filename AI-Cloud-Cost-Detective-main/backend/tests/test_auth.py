"""Auth endpoint tests (signup, login, logout, me, change-password)."""
import pytest


@pytest.mark.asyncio
async def test_signup_and_login(client):
    r = await client.post("/api/auth/signup", json={"email": "test@example.com", "password": "password123"})
    assert r.status_code == 201
    body = r.json()
    assert "user" in body
    assert body["user"]["email"] == "test@example.com"
    # httpOnly cookie must be set
    assert "token" in r.cookies

    r2 = await client.post("/api/auth/login", json={"email": "test@example.com", "password": "password123"})
    assert r2.status_code == 200
    assert "token" in r2.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/auth/signup", json={"email": "pw@example.com", "password": "correct123"})
    r = await client.post("/api/auth/login", json={"email": "pw@example.com", "password": "wrongpassword"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    r = await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "anything"})
    # Returns 404 so the UI can show a "create account" prompt without guessing
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user(client):
    await client.post("/api/auth/signup", json={"email": "me@example.com", "password": "password123"})
    r2 = await client.post("/api/auth/login", json={"email": "me@example.com", "password": "password123"})
    cookie = r2.cookies.get("token")
    # Use header instead of per-request cookies= (avoids httpx deprecation warning)
    r3 = await client.get("/api/auth/me", headers={"cookie": f"token={cookie}"})
    assert r3.status_code == 200
    assert r3.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_logout_clears_cookie(client):
    await client.post("/api/auth/signup", json={"email": "logout@example.com", "password": "password123"})
    r2 = await client.post("/api/auth/login", json={"email": "logout@example.com", "password": "password123"})
    cookie = r2.cookies.get("token")
    r3 = await client.post("/api/auth/logout", headers={"cookie": f"token={cookie}"})
    assert r3.status_code == 200
    # After logout the token is revoked — /me should fail
    r4 = await client.get("/api/auth/me", headers={"cookie": f"token={cookie}"})
    assert r4.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_signup(client):
    await client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    r = await client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_invalid_email_rejected(client):
    r = await client.post("/api/auth/signup", json={"email": "not-an-email", "password": "password123"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_short_password_rejected(client):
    r = await client.post("/api/auth/signup", json={"email": "short@example.com", "password": "abc"})
    assert r.status_code == 422
