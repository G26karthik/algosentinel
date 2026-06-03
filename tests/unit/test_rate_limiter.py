import time

from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter


def test_initial_tokens_allow_immediate_calls():
    limiter = TokenBucketRateLimiter(rate_per_minute=10)
    start = time.monotonic()
    limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


def test_exhausted_tokens_cause_blocking():
    limiter = TokenBucketRateLimiter(rate_per_minute=60)
    for _ in range(60):
        limiter.acquire()
    start = time.monotonic()
    limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05
