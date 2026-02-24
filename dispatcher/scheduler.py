from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Scheduler:
    poll_interval_sec: int
    reconcile_interval_sec: int

    _next_poll: datetime | None = None
    _next_reconcile: datetime | None = None

    def tick(self, now: datetime) -> tuple[bool, bool]:
        """
        Возвращает (do_poll, do_reconcile)
        """
        if self._next_poll is None:
            self._next_poll = now
        if self._next_reconcile is None:
            self._next_reconcile = now

        do_poll = now >= self._next_poll
        do_reconcile = now >= self._next_reconcile

        if do_poll:
            self._next_poll = now + timedelta(seconds=self.poll_interval_sec)
        if do_reconcile:
            self._next_reconcile = now + timedelta(seconds=self.reconcile_interval_sec)

        return do_poll, do_reconcile
