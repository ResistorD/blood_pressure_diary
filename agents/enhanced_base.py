"""Enhanced base agent with error handling and metrics."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Protocol, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging
from contextlib import contextmanager
from time import perf_counter

from domain.models import Signal
from utils.time import now_utc


@dataclass
class AgentMetrics:
    """Agent performance metrics."""
    agent_id: str
    calls: int = 0
    signals_generated: int = 0
    errors: int = 0
    total_time_sec: float = 0.0
    last_run: Optional[datetime] = None
    
    @property
    def avg_time_sec(self) -> float:
        """Average processing time per call."""
        return self.total_time_sec / self.calls if self.calls > 0 else 0.0
    
    @property
    def signals_per_call(self) -> float:
        """Average signals generated per call."""
        return self.signals_generated / self.calls if self.calls > 0 else 0.0
    
    @property
    def error_rate(self) -> float:
        """Error rate (errors / calls)."""
        return self.errors / self.calls if self.calls > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "calls": self.calls,
            "signals_generated": self.signals_generated,
            "errors": self.errors,
            "total_time_sec": round(self.total_time_sec, 3),
            "avg_time_sec": round(self.avg_time_sec, 3),
            "signals_per_call": round(self.signals_per_call, 2),
            "error_rate": round(self.error_rate, 4),
            "last_run": self.last_run.isoformat() if self.last_run else None,
        }


@dataclass
class AgentContext:
    """Enhanced agent context with utilities."""
    run_id: str
    now: datetime
    repo: Any
    settings: Any
    data_provider: Optional["AgentDataProvider"] = None
    repo_latest_snapshots: Optional[Callable[[str], Dict[str, dict]]] = None
    
    # Optional caches
    markets: Optional[List[Any]] = None
    latest_snapshots: Optional[Dict[str, Dict]] = None

    def list_markets(self, limit: int = 500) -> List[Any]:
        """Read markets via narrow provider API (fallback to repo for compatibility)."""
        if self.markets is not None:
            return list(self.markets)
        if self.data_provider is not None:
            return list(self.data_provider.list_markets(limit=limit))
        if hasattr(self.repo, "list_markets"):
            return list(self.repo.list_markets(limit=limit))
        return []

    def get_market_snapshots(self, market_id: str) -> Dict[str, Dict]:
        """Get snapshots for market (cached if available).
        
        Args:
            market_id: Market identifier
            
        Returns:
            Dictionary mapping outcome -> snapshot data
        """
        # Try cache first
        if self.latest_snapshots and market_id in self.latest_snapshots:
            return self.latest_snapshots[market_id]
        
        # Prefer explicit provider for testability
        if self.data_provider is not None:
            return self.data_provider.get_latest_snapshots(market_id)

        # Fall back to repo
        if hasattr(self.repo, "get_latest_snapshots"):
            return self.repo.get_latest_snapshots(market_id)
        
        # Legacy fallback
        if self.repo_latest_snapshots is not None:
            return self.repo_latest_snapshots(market_id)

        return {}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Read open paper positions via provider/repo fallback."""
        if self.data_provider is not None:
            return self.data_provider.list_open_positions()
        if hasattr(self.repo, "list_open_positions"):
            return list(self.repo.list_open_positions())
        return []

    def get_latest_orderbook(self, market_id: str) -> Dict[str, Any]:
        """Get latest orderbook snapshot for market."""
        if self.data_provider is not None and hasattr(self.data_provider, "get_latest_orderbook"):
            return dict(self.data_provider.get_latest_orderbook(market_id) or {})
        if hasattr(self.repo, "get_latest_orderbook_snapshot"):
            return dict(self.repo.get_latest_orderbook_snapshot(market_id) or {})
        return {}


class AgentDataProvider(Protocol):
    """Narrow interface used by agents instead of full Repo."""

    def list_markets(self, limit: int = 500) -> List[Any]:
        ...

    def get_latest_snapshots(self, market_id: str) -> Dict[str, Dict]:
        ...

    def list_open_positions(self) -> List[Dict[str, Any]]:
        ...

    def get_latest_orderbook(self, market_id: str) -> Dict[str, Any]:
        ...


class EnhancedAgent(ABC):
    """Enhanced base agent with built-in metrics and error handling."""
    
    agent_id: str = "base"
    
    def __init__(self):
        self._metrics = AgentMetrics(agent_id=self.agent_id)
        self._logger = logging.getLogger(f"agent.{self.agent_id}")
    
    @abstractmethod
    def _propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Internal propose implementation.
        
        Subclasses must implement this method.
        
        Args:
            ctx: Agent context with repo, settings, etc.
            market_id: Optional market ID for per-market processing
            
        Returns:
            List of generated signals
        """
        pass
    
    def propose(self, ctx: AgentContext, market_id: Optional[str] = None) -> List[Signal]:
        """Propose signals with error handling and metrics.
        
        This method wraps _propose() with automatic error handling,
        timing, and metric collection.
        
        Args:
            ctx: Agent context
            market_id: Optional market ID
            
        Returns:
            List of signals (empty list if error occurred)
        """
        start = perf_counter()
        signals = []
        
        try:
            self._metrics.calls += 1
            self._metrics.last_run = ctx.now
            
            # Call the actual implementation
            signals = self._propose(ctx, market_id)
            
            # Update metrics
            self._metrics.signals_generated += len(signals)
            
            if signals:
                self._logger.debug(
                    f"Generated {len(signals)} signals",
                    extra={"market_id": market_id, "signal_count": len(signals)}
                )
        
        except Exception as e:
            self._metrics.errors += 1
            self._logger.exception(
                f"Agent {self.agent_id} failed",
                extra={"market_id": market_id, "error": str(e)}
            )
            # Don't re-raise, let caller handle
        
        finally:
            elapsed = perf_counter() - start
            self._metrics.total_time_sec += elapsed
            
            if elapsed > 1.0:  # Warn on slow processing
                self._logger.warning(
                    f"Slow processing: {elapsed:.2f}s",
                    extra={"market_id": market_id, "elapsed_sec": elapsed}
                )
        
        return signals
    
    def get_metrics(self) -> AgentMetrics:
        """Get agent metrics.
        
        Returns:
            Current metrics for this agent
        """
        return self._metrics
    
    def reset_metrics(self) -> None:
        """Reset agent metrics."""
        self._metrics = AgentMetrics(agent_id=self.agent_id)
    
    @contextmanager
    def _timed_section(self, name: str):
        """Context manager for timing code sections.
        
        Args:
            name: Name of the section for logging
            
        Example:
            >>> with self._timed_section("compute_features"):
            ...     features = compute_features(data)
        """
        start = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            self._logger.debug(f"{name} took {elapsed:.3f}s")


# Legacy alias for backward compatibility
class Agent(EnhancedAgent):
    """Alias for backward compatibility."""
    pass
