from __future__ import annotations

from typing import Protocol


class Dispatcher(Protocol):
    def run_forever(self) -> None: ...
    def stop(self) -> None: ...
