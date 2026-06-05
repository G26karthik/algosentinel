import threading
import time


class TokenBucketRateLimiter:
    """Thread-safe token bucket. Caps Gemini calls at rate_per_minute."""

    def __init__(self, rate_per_minute: int = 14, burst: int = 1):
        self.rate = rate_per_minute
        # Cap the burst so we never exceed the provider's rolling-window quota.
        # A token bucket that starts full can emit `rate` calls instantly; on a
        # hard N-per-minute free-tier limit that alone trips a 429.
        self.capacity = float(max(1, min(burst, rate_per_minute)))
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        new_tokens = elapsed * (self.rate / 60.0)
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def acquire(self, tokens: int = 1) -> None:
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
            time.sleep(0.1)


_shared_limiter: "TokenBucketRateLimiter | None" = None
_shared_lock = threading.Lock()


def get_shared_rate_limiter() -> "TokenBucketRateLimiter":
    """Process-wide limiter shared by the parent agent and every subagent.

    Free-tier and most paid Gemini quotas are enforced per API key, not per
    component, so the parent loop and any spawned subagents must draw from a
    single bucket rather than each holding their own.
    """
    global _shared_limiter
    if _shared_limiter is None:
        with _shared_lock:
            if _shared_limiter is None:
                from algosentinel.config import settings

                _shared_limiter = TokenBucketRateLimiter(
                    rate_per_minute=settings.gemini_max_rpm
                )
    return _shared_limiter
