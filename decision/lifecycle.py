from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class LifecycleState:
    """Very small state machine placeholder for position lifecycle."""
    state: str  # FLAT / OPEN / CLOSING / CLOSED
