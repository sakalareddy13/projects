#!/bin/sh
# Fix SSO cache permissions so boto3 can read them regardless of how aws sso login wrote them
chmod 644 /home/appuser/.aws/sso/cache/*.json 2>/dev/null || true

# Auto-generate JWT_SECRET on first run and persist it so restarts don't invalidate tokens
SECRET_FILE=/app/data/.jwt_secret
if [ -z "$JWT_SECRET" ]; then
    if [ -f "$SECRET_FILE" ]; then
        JWT_SECRET=$(cat "$SECRET_FILE")
    else
        JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        mkdir -p /app/data
        printf '%s' "$JWT_SECRET" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "[startup] Generated new JWT_SECRET — persisted to $SECRET_FILE"
    fi
    export JWT_SECRET
fi

exec uvicorn main:app --host 0.0.0.0 --port 8000
