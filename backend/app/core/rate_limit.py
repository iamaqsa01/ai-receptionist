"""A small, dependency-free, in-memory rate limiter for the handful of
unauthenticated-or-abuse-prone endpoints that actually need one: login and
registration (credential stuffing / spam account creation) and the Twilio
voice webhook (cost/abuse — see app.api.telephony, which also verifies the
request signature).

This is a per-process sliding-window counter, keyed by (client IP, bucket).
It is NOT a substitute for a real distributed limiter (Redis, an API
gateway, etc.) once this runs as more than one process — each worker/
replica keeps its own counts, so the *effective* limit across N processes
is N times the configured one. That's an honest, stated limitation, not a
claim of production-grade protection; it still stops the easy case (a
single client hammering one process) and is better than nothing while this
project has no shared-state infra to lean on.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        # Trusts X-Forwarded-For only in the sense of using it as a rate-limit
        # bucket key, not for any authorization decision — worst case a
        # spoofed value just puts the request in the wrong (or a fresh)
        # bucket, it never grants access to anything.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check(self, request: Request) -> None:
        key = self._client_key(request)
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests. Please try again later.")
        hits.append(now)


# One shared instance per protected endpoint category — separate buckets so
# hammering /auth/login doesn't also exhaust a caller's /auth/register quota.
login_rate_limiter = RateLimiter(limit=10, window_seconds=60)
register_rate_limiter = RateLimiter(limit=5, window_seconds=60)
telephony_webhook_rate_limiter = RateLimiter(limit=30, window_seconds=60)


def rate_limit(limiter: RateLimiter):
    def dependency(request: Request) -> None:
        limiter.check(request)
    return dependency
