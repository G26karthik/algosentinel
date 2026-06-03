import threading
import time


class TokenBucketRateLimiter:
    """Thread-safe token bucket. Caps Gemini calls at rate_per_minute."""

    def __init__(self, rate_per_minute: int = 14):
        self.rate = rate_per_minute
        self.capacity = float(rate_per_minute)
        self.tokens = float(rate_per_minute)
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
