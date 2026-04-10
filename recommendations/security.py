import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request

from recommendations.core.config import settings


_request_windows: dict[str, deque[float]] = defaultdict(deque)


def fetch_rate_limit(request: Request) -> None:
    # Simple in-memory limiter per client IP and route path.
    client_ip = request.client.host if request.client else "unknown"
    bucket_key = f"{client_ip}:{request.url.path}"
    now = time.time()
    window_start = now - 60
    limit = settings.fetch_rate_limit_per_minute

    bucket = _request_windows[bucket_key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please retry later.")

    bucket.append(now)


def require_s3_api_key(x_api_key: str | None = Header(default=None)) -> None:
    # If no API key is configured, keep this dependency as a no-op.
    configured_key = settings.s3_api_key.strip()
    if not configured_key:
        return

    if not x_api_key or x_api_key.strip() != configured_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
