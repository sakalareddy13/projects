import asyncio
import asyncpg
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

pool: Optional[asyncpg.Pool] = None

# ── In-memory fallback stores ─────────────────────────────────────────────────
# Used when DATABASE_URL is not set or the Postgres connection fails at startup.
#
# LIMITATIONS — do not use this mode in production:
#   • No persistence: all data is lost on process restart.
#   • No concurrency safety across multiple OS processes (UVICORN_WORKERS must be 1).
#   • No pagination or indexed lookups: get_analyses_by_user is an O(n) full scan.
#   • No size cap: _analyses_store grows unbounded until purge_old_analyses runs.
#   • purge_old_analyses uses ISO string comparison which is timezone-fragile.
#
# Intended use: local development without a running Postgres instance.
# The /health endpoint reports db="in-memory" when this mode is active.
# ─────────────────────────────────────────────────────────────────────────────
_users_store: dict[str, dict] = {}
_analyses_store: dict[str, dict] = {}
_user_counter = 0
_mem_lock = asyncio.Lock()


async def init_pool():
    global pool
    url = os.getenv("DATABASE_URL")
    if not url:
        logger.warning("db.no_url", extra={"detail": "DATABASE_URL not set — running in-memory mode (no persistence)"})
        return
    try:
        pool = await asyncpg.create_pool(
            url,
            min_size=2,
            max_size=10,
            command_timeout=30,
            max_inactive_connection_lifetime=300,
        )
        logger.info("db.connected")
    except Exception as e:
        logger.error("db.connect_failed", extra={"error": str(e), "detail": "running in-memory mode"})


async def close_pool():
    global pool
    if pool:
        await pool.close()


async def create_tables():
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                expires_at TIMESTAMPTZ NOT NULL,
                used BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                cloud_provider TEXT DEFAULT 'aws',
                regions TEXT[] NOT NULL DEFAULT '{}',
                services TEXT[] NOT NULL DEFAULT '{}',
                accounts TEXT[] DEFAULT '{}',
                resources_scanned INTEGER DEFAULT 0,
                issues_found INTEGER DEFAULT 0,
                estimated_savings TEXT,
                analysis_result JSONB,
                status TEXT DEFAULT 'running',
                error_message TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Migrations for existing DBs
        await conn.execute("""
            ALTER TABLE analyses ADD COLUMN IF NOT EXISTS error_message TEXT
        """)
        await conn.execute("""
            ALTER TABLE analyses ADD COLUMN IF NOT EXISTS cloud_provider TEXT DEFAULT 'aws'
        """)
        # Index for fast per-user history queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS analyses_user_id_idx ON analyses(user_id)
        """)
        # Index for purge queries (time-range deletes)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS analyses_created_at_idx ON analyses(created_at)
        """)
        # Token revocation table (for logout / JTI blacklist)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                expires_at TIMESTAMPTZ NOT NULL
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS revoked_tokens_exp_idx ON revoked_tokens(expires_at)
        """)


_revoked_jti_store: set = set()  # fallback in-memory store


async def revoke_token(jti: str, expires_at) -> None:
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO revoked_tokens (jti, expires_at) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                jti, expires_at,
            )
        return
    _revoked_jti_store.add(jti)


async def is_token_revoked(jti: str) -> bool:
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM revoked_tokens WHERE jti=$1", jti)
            return row is not None
    return jti in _revoked_jti_store


async def purge_revoked_tokens() -> None:
    """Remove expired revoked tokens — runs periodically to keep the table small."""
    if pool:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM revoked_tokens WHERE expires_at < NOW()")


async def purge_old_analyses(days: int = 2) -> int:
    """Delete all analyses older than `days` days. Returns number of rows deleted."""
    if pool:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM analyses WHERE created_at < NOW() - ($1 * INTERVAL '1 day')",
                days,
            )
            # asyncpg returns "DELETE N"
            try:
                return int(result.split()[-1])
            except Exception:
                return 0
    async with _mem_lock:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        old_ids = [
            aid for aid, a in _analyses_store.items()
            if a.get("created_at", "") < cutoff.isoformat()
        ]
        for aid in old_ids:
            del _analyses_store[aid]
        return len(old_ids)


async def fail_stale_analyses():
    """Mark any analyses that were left 'running' at last shutdown as failed."""
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE analyses SET status = 'failed', error_message = 'Server restarted while analysis was running'
               WHERE status = 'running'"""
        )


_reset_tokens_store: dict[str, dict] = {}


async def create_reset_token(user_id: int, token: str, expires_at) -> None:
    if pool:
        async with pool.acquire() as conn:
            # Invalidate any previous unused tokens for this user
            await conn.execute(
                "UPDATE password_reset_tokens SET used = TRUE WHERE user_id = $1 AND used = FALSE",
                user_id,
            )
            await conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES ($1, $2, $3)",
                token, user_id, expires_at,
            )
        return
    async with _mem_lock:
        for t, v in list(_reset_tokens_store.items()):
            if v["user_id"] == user_id and not v["used"]:
                v["used"] = True
        _reset_tokens_store[token] = {"user_id": user_id, "expires_at": expires_at, "used": False}


async def get_valid_reset_token(token: str):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id FROM password_reset_tokens WHERE token = $1 AND used = FALSE AND expires_at > $2",
                token, now,
            )
            return row["user_id"] if row else None
    entry = _reset_tokens_store.get(token)
    if entry and not entry["used"] and entry["expires_at"] > now:
        return entry["user_id"]
    return None


async def consume_reset_token(token: str) -> None:
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE password_reset_tokens SET used = TRUE WHERE token = $1",
                token,
            )
        return
    async with _mem_lock:
        if token in _reset_tokens_store:
            _reset_tokens_store[token]["used"] = True


async def update_user_password(user_id: int, new_hash: str) -> bool:
    if pool:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET password_hash = $1 WHERE id = $2",
                new_hash, user_id
            )
            return result == "UPDATE 1"
    async with _mem_lock:
        for user in _users_store.values():
            if user["id"] == user_id:
                user["password_hash"] = new_hash
                return True
    return False


async def get_user_by_id(user_id: int) -> Optional[dict]:
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            return dict(row) if row else None
    for user in _users_store.values():
        if user["id"] == user_id:
            return dict(user)
    return None


async def get_user_by_email(email: str) -> Optional[dict]:
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
            return dict(row) if row else None
    return _users_store.get(email)


async def create_user(email: str, password_hash: str) -> Optional[dict]:
    global _user_counter
    if pool:
        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING *",
                    email, password_hash
                )
                return dict(row) if row else None
            except asyncpg.UniqueViolationError:
                return None
    async with _mem_lock:
        if email in _users_store:
            return None
        _user_counter += 1
        user = {"id": _user_counter, "email": email, "password_hash": password_hash}
        _users_store[email] = user
    return user


async def create_analysis(
    analysis_id: str,
    user_id: int,
    regions: list,
    services: list,
    accounts: list = None,
    cloud_provider: str = "aws",
) -> None:
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO analyses (id, user_id, cloud_provider, regions, services, accounts, status)
                   VALUES ($1, $2, $3, $4, $5, $6, 'running')
                   ON CONFLICT (id) DO NOTHING""",
                analysis_id, user_id, cloud_provider, regions, services, accounts or []
            )
        return
    _analyses_store[analysis_id] = {
        "id": analysis_id,
        "user_id": user_id,
        "cloud_provider": cloud_provider,
        "regions": regions,
        "services": services,
        "accounts": accounts or [],
        "resources_scanned": 0,
        "issues_found": 0,
        "estimated_savings": None,
        "analysis_result": None,
        "status": "running",
        "error_message": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


async def update_analysis(analysis_id: str, result: dict) -> None:
    savings = f"${result.get('estimated_monthly_savings', 0):.2f}/month"
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE analyses SET
                   resources_scanned = $1,
                   issues_found = $2,
                   estimated_savings = $3,
                   analysis_result = $4::jsonb,
                   status = 'complete'
                   WHERE id = $5""",
                result.get("total_resources", 0),
                result.get("issues_found", 0),
                savings,
                json.dumps(result),
                analysis_id,
            )
        return
    if analysis_id in _analyses_store:
        _analyses_store[analysis_id].update({
            "resources_scanned": result.get("total_resources", 0),
            "issues_found": result.get("issues_found", 0),
            "estimated_savings": savings,
            "analysis_result": result,
            "status": "complete",
        })


async def fail_analysis(analysis_id: str, error: str) -> None:
    if pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE analyses SET status = 'failed', error_message = $1 WHERE id = $2",
                error, analysis_id
            )
        return
    if analysis_id in _analyses_store:
        _analyses_store[analysis_id]["status"] = "failed"
        _analyses_store[analysis_id]["error_message"] = error


async def get_analyses_by_user(user_id: int, limit: int = 100, offset: int = 0) -> list:
    if pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, cloud_provider, regions, services, accounts, resources_scanned, issues_found,
                          estimated_savings, status, error_message, created_at
                   FROM analyses WHERE user_id = $1 ORDER BY created_at DESC
                   LIMIT $2 OFFSET $3""",
                user_id, limit, offset,
            )
            result = []
            for r in rows:
                d = dict(r)
                if d.get("created_at"):
                    d["created_at"] = d["created_at"].isoformat()
                result.append(d)
            return result
    rows = [
        {k: v for k, v in a.items() if k != "analysis_result"}
        for a in _analyses_store.values()
        if a.get("user_id") == user_id
    ]
    rows.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return rows[offset: offset + limit]


async def get_running_analyses_for_user(user_id: int) -> list:
    if pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM analyses WHERE user_id = $1 AND status = 'running'",
                user_id,
            )
            return [{"analysis_id": r["id"]} for r in rows]
    return [
        {"analysis_id": aid}
        for aid, a in _analyses_store.items()
        if a.get("user_id") == user_id and a.get("status") == "running"
    ]


async def delete_analysis(analysis_id: str, user_id: int) -> bool:
    """Delete a single analysis belonging to user_id. Returns True if a row was deleted."""
    if pool:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM analyses WHERE id = $1 AND user_id = $2",
                analysis_id, user_id,
            )
            return result == "DELETE 1"
    async with _mem_lock:
        a = _analyses_store.get(analysis_id)
        if a and a.get("user_id") == user_id:
            del _analyses_store[analysis_id]
            return True
        return False


async def get_analysis_by_id(analysis_id: str, user_id: int) -> Optional[dict]:
    if pool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM analyses WHERE id = $1 AND user_id = $2",
                analysis_id, user_id,
            )
            if not row:
                return None
            d = dict(row)
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            # asyncpg auto-deserializes JSONB to dict; this guard is kept only for safety
            if d.get("analysis_result") and isinstance(d["analysis_result"], str):
                d["analysis_result"] = json.loads(d["analysis_result"])
            return d
    a = _analyses_store.get(analysis_id)
    if a and a.get("user_id") == user_id:
        return dict(a)
    return None
