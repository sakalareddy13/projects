# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc bytecode files and from reading stale cache.
# A crafted .pyc in __pycache__ could shadow ownership.py with a no-op version.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONNODEBUGRANGES=1

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

# Ownership integrity check — build fails if LinkedIn ID is modified or removed
RUN python validate_ownership.py

# Drop root — create a non-privileged user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && chown -R appuser:appgroup /app \
    && mkdir -p /app/data && chown appuser:appgroup /app/data

COPY entrypoint.sh /entrypoint.sh
# Strip Windows CRLF line endings — belt-and-suspenders in case .gitattributes
# was not applied before clone (e.g. older Git on Windows with autocrlf=true).
# CRLF in a shell script causes "bad interpreter" inside the Linux container.
RUN sed -i 's/\r//' /entrypoint.sh && chmod +x /entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
