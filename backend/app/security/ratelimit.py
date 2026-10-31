"""Sliding-window rate limiter.

shortcut: per-process memory, so limits are per instance; move to Redis or a DB-backed
counter before running more than one backend instance.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float) -> tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False, window_seconds - (now - q[0])
            q.append(now)
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Render/Vercel put the real client first in X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, limit: int, window_seconds: float = 60, subject: str | None = None) -> None:
    """Limit both by client IP and (when known) by workspace, so neither rotating
    workspaces nor rotating IPs bypasses the limit."""
    keys = [f"{bucket}:ip:{client_ip(request)}"]
    if subject:
        keys.append(f"{bucket}:ws:{subject}")
    for key in keys:
        ok, retry = limiter.check(key, limit, window_seconds)
        if not ok:
            raise HTTPException(
                status_code=429,
                detail={"code": "RATE_LIMITED", "message": "Too many requests. Please wait and try again."},
                headers={"Retry-After": str(max(1, int(retry)))},
            )
