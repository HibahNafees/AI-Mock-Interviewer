"""A small in-process rate limiter for login and signup (brute-force guard).

Counts live in each worker's memory, so with N gunicorn workers the effective
limit is up to N times the setting: fine for slowing down password guessing on
a single small server, without adding Redis.
"""

import threading
import time
from collections import defaultdict, deque

from flask import current_app, request

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def allow(name: str, limit: int, window_sec: int, key: str | None = None) -> bool:
    """Record one attempt; False once `limit` attempts happened in the window."""
    if not current_app.config.get("RATE_LIMITS", True):
        return True
    bucket = f"{name}:{key or request.remote_addr}"
    now = time.monotonic()
    with _lock:
        q = _hits[bucket]
        while q and now - q[0] > window_sec:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset() -> None:
    with _lock:
        _hits.clear()
