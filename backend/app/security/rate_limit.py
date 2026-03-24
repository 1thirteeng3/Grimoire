from collections import defaultdict, deque
from threading import RLock
from time import monotonic
from typing import Callable

from fastapi import HTTPException, Request

from app.config import settings


class SlidingWindowLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = monotonic()
        with self._lock:
            bucket = self._events[key]
            threshold = now - float(window_seconds)
            while bucket and bucket[0] < threshold:
                bucket.popleft()
            if len(bucket) >= max(1, int(limit)):
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


_rest_limiter = SlidingWindowLimiter()
_ws_limiter = SlidingWindowLimiter()


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _rest_rate_limit_dependency(request: Request) -> None:
    ok, retry_after = _rest_limiter.allow(
        key=f"rest:ip:{_client_ip(request)}",
        limit=settings.rest_rate_limit_per_minute,
        window_seconds=60,
    )
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="RATE_LIMIT_EXCEEDED",
            headers={"Retry-After": str(retry_after)},
        )


def rest_rate_limit_dep() -> Callable:
    return _rest_rate_limit_dependency


def check_ws_limits(client_ip: str, session_id: str) -> tuple[bool, str, int]:
    ok_ip, retry_ip = _ws_limiter.allow(
        key=f"ws:ip:{client_ip}",
        limit=settings.ws_rate_limit_per_minute_per_ip,
        window_seconds=60,
    )
    if not ok_ip:
        return False, "RATE_LIMIT_IP", retry_ip
    ok_session, retry_session = _ws_limiter.allow(
        key=f"ws:session:{session_id}",
        limit=settings.ws_rate_limit_per_minute_per_session,
        window_seconds=60,
    )
    if not ok_session:
        return False, "RATE_LIMIT_SESSION", retry_session
    return True, "OK", 0


def reset_rate_limiters() -> None:
    _rest_limiter.clear()
    _ws_limiter.clear()
