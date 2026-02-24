from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

from domain.models import Signal


@dataclass(frozen=True)
class AgentContext:
    run_id: str
    now: datetime

    # Required callback used by QuantAgent
    repo_latest_snapshots: Callable[[str], Dict[str, dict]]  # outcome -> fields

    # Optional extra context for more advanced agents
    repo: Optional[object] = None
    markets: Optional[List[object]] = None  # list[Market]
    settings: Optional[object] = None
    latest_mid: Optional[Dict[tuple, float]] = None  # (market_id, outcome) -> mid


class Agent(ABC):
    agent_id: str

    @abstractmethod
    def propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        ...
