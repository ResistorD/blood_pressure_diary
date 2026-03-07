from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Optional

from .events import Event


class EventBus:
    def __init__(self, maxlen: int | None = 5000):
        bounded = int(maxlen) if maxlen is not None else 5000
        if bounded <= 0:
            bounded = 5000
        self._maxlen = bounded
        self._q: Deque[Event] = deque(maxlen=self._maxlen)
        self._lock = Lock()
        self._dropped = 0

    def publish(self, ev: Event) -> None:
        with self._lock:
            full_before = len(self._q) >= self._maxlen
            self._q.append(ev)
            if full_before and len(self._q) == self._maxlen:
                self._dropped += 1

    def pop(self) -> Optional[Event]:
        with self._lock:
            if not self._q:
                return None
            return self._q.popleft()

    def size(self) -> int:
        with self._lock:
            return len(self._q)

    def dropped(self) -> int:
        with self._lock:
            return self._dropped
