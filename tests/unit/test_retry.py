import pytest

from algosentinel.resilience.errors import FatalError, RetryableError
from algosentinel.resilience.retry import with_retry


def test_retries_retryable_error():
    call_count = 0

    @with_retry(max_attempts=3, min_wait=0.01, max_wait=0.1)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RetryableError("temporary failure")
        return "ok"

    result = flaky()
    assert result == "ok"
    assert call_count == 3


def test_does_not_retry_fatal_error():
    call_count = 0

    @with_retry(max_attempts=4, min_wait=0.01, max_wait=0.1)
    def always_fatal():
        nonlocal call_count
        call_count += 1
        raise FatalError("permanent failure")

    with pytest.raises(FatalError):
        always_fatal()
    assert call_count == 1
