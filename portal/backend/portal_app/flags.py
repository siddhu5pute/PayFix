"""Failure-injection flags. Defaults come from env; the demo control room can flip them live."""
from __future__ import annotations

import threading

from .config import settings


class Flags:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values = {
            "drop_webhooks": settings.drop_webhooks,
            "delay_webhook_seconds": settings.delay_webhook_seconds,
            "duplicate_webhooks": settings.duplicate_webhooks,
        }

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._values)

    def update(self, **changes) -> dict:
        with self._lock:
            for k, v in changes.items():
                if k in self._values and v is not None:
                    self._values[k] = v
            return dict(self._values)


flags = Flags()
