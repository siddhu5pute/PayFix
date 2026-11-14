from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class RetriesExhausted(Exception):
    def __init__(self, attempts: int, last: Exception):
        super().__init__(f"gave up after {attempts} attempts: {last}")
        self.attempts = attempts
        self.last = last


def with_retry(fn: Callable[[], T], *, retry_on: tuple[type[Exception], ...], max_attempts: int = 4,
               base_delay: float = 0.5, max_delay: float = 8.0,
               on_retry: Callable[[int, Exception, float], None] | None = None,
               sleep: Callable[[float], None] = time.sleep) -> T:
    """Exponential backoff with full jitter: delay = rand(0, min(max, base * 2^attempt))."""
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except retry_on as exc:
            last = exc
            if attempt == max_attempts:
                break
            delay = random.uniform(base_delay / 2, min(max_delay, base_delay * (2 ** (attempt - 1))))
            if on_retry:
                on_retry(attempt, exc, delay)
            sleep(delay)
    raise RetriesExhausted(max_attempts, last)  # type: ignore[arg-type]
