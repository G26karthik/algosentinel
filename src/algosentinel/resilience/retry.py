import logging

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from algosentinel.resilience.errors import RetryableError


def with_retry(max_attempts: int = 4, min_wait: float = 1.0, max_wait: float = 60.0):
    """Decorator for external calls. Retries RetryableError only."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=min_wait, max=max_wait, jitter=1.0),
        retry=retry_if_exception_type(RetryableError),
        before_sleep=before_sleep_log(
            logging.getLogger("tenacity"), logging.WARNING
        ),
        reraise=True,
    )
