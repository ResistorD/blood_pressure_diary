"""Caching layer for database queries with TTL and statistics."""
from __future__ import annotations

import threading
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
from cachetools import TTLCache

from utils.time import now_utc


@dataclass
class CacheStats:
    """Cache statistics for monitoring."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0
    errors: int = 0
    
    @property
    def total_requests(self) -> int:
        """Total cache requests."""
        return self.hits + self.misses
    
    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self.total_requests
        return self.hits / total if total > 0 else 0.0
    
    @property
    def miss_rate(self) -> float:
        """Cache miss rate (0.0 to 1.0)."""
        total = self.total_requests
        return self.misses / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "evictions": self.evictions,
            "errors": self.errors,
            "total_requests": self.total_requests,
            "hit_rate": round(self.hit_rate, 4),
            "miss_rate": round(self.miss_rate, 4),
        }
    
    def reset(self) -> None:
        """Reset all counters."""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.evictions = 0
        self.errors = 0


@dataclass
class CacheConfig:
    """Cache configuration."""
    market_ttl: int = 300  # 5 minutes
    snapshot_ttl: int = 10  # 10 seconds
    signal_ttl: int = 60  # 1 minute
    decision_ttl: int = 30  # 30 seconds
    
    max_markets: int = 1000
    max_snapshots: int = 5000
    max_signals: int = 1000
    max_decisions: int = 500
    
    enabled: bool = True


class ThreadSafeCache:
    """Thread-safe TTL cache wrapper."""
    
    def __init__(self, maxsize: int, ttl: int):
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()
        self._eviction_count = 0
    
    def get(self, key: Any) -> Optional[Any]:
        """Get value from cache."""
        with self._lock:
            return self._cache.get(key)
    
    def set(self, key: Any, value: Any) -> None:
        """Set value in cache."""
        with self._lock:
            old_size = len(self._cache)
            self._cache[key] = value
            new_size = len(self._cache)
            
            # Track evictions
            if old_size == self._cache.maxsize and new_size == old_size:
                self._eviction_count += 1
    
    def delete(self, key: Any) -> None:
        """Delete value from cache."""
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()
    
    def __len__(self) -> int:
        """Get cache size."""
        with self._lock:
            return len(self._cache)
    
    @property
    def eviction_count(self) -> int:
        """Get eviction count."""
        with self._lock:
            return self._eviction_count


class RepoCache:
    """Multi-level cache for repository queries with statistics."""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        
        # Cache layers
        self._markets: Optional[ThreadSafeCache] = None
        self._snapshots: Optional[ThreadSafeCache] = None
        self._signals: Optional[ThreadSafeCache] = None
        self._decisions: Optional[ThreadSafeCache] = None
        
        # Statistics
        self._market_stats = CacheStats()
        self._snapshot_stats = CacheStats()
        self._signal_stats = CacheStats()
        self._decision_stats = CacheStats()
        
        # Initialize caches if enabled
        if self.config.enabled:
            self._initialize_caches()
    
    def _initialize_caches(self) -> None:
        """Initialize all cache layers."""
        self._markets = ThreadSafeCache(
            maxsize=self.config.max_markets,
            ttl=self.config.market_ttl
        )
        self._snapshots = ThreadSafeCache(
            maxsize=self.config.max_snapshots,
            ttl=self.config.snapshot_ttl
        )
        self._signals = ThreadSafeCache(
            maxsize=self.config.max_signals,
            ttl=self.config.signal_ttl
        )
        self._decisions = ThreadSafeCache(
            maxsize=self.config.max_decisions,
            ttl=self.config.decision_ttl
        )
    
    # ========== Market Cache ==========
    
    def get_market(self, market_id: str) -> Optional[Any]:
        """Get cached market."""
        if not self.config.enabled or self._markets is None:
            self._market_stats.misses += 1
            return None
        
        try:
            value = self._markets.get(market_id)
            if value is not None:
                self._market_stats.hits += 1
            else:
                self._market_stats.misses += 1
            return value
        except Exception:
            self._market_stats.errors += 1
            return None
    
    def set_market(self, market_id: str, market: Any) -> None:
        """Cache market."""
        if not self.config.enabled or self._markets is None:
            return
        
        try:
            self._markets.set(market_id, market)
            self._market_stats.sets += 1
            self._market_stats.evictions = self._markets.eviction_count
        except Exception:
            self._market_stats.errors += 1
    
    def invalidate_market(self, market_id: str) -> None:
        """Invalidate market cache."""
        if self._markets is not None:
            self._markets.delete(market_id)
    
    # ========== Snapshot Cache ==========
    
    def get_snapshot(self, market_id: str, outcome: str) -> Optional[Dict[str, Any]]:
        """Get cached snapshot."""
        if not self.config.enabled or self._snapshots is None:
            self._snapshot_stats.misses += 1
            return None
        
        try:
            key = (market_id, outcome)
            value = self._snapshots.get(key)
            if value is not None:
                self._snapshot_stats.hits += 1
            else:
                self._snapshot_stats.misses += 1
            return value
        except Exception:
            self._snapshot_stats.errors += 1
            return None
    
    def set_snapshot(self, market_id: str, outcome: str, data: Dict[str, Any]) -> None:
        """Cache snapshot."""
        if not self.config.enabled or self._snapshots is None:
            return
        
        try:
            key = (market_id, outcome)
            self._snapshots.set(key, data)
            self._snapshot_stats.sets += 1
            self._snapshot_stats.evictions = self._snapshots.eviction_count
        except Exception:
            self._snapshot_stats.errors += 1
    
    def get_snapshots(self, market_id: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """Get all cached snapshots for market."""
        if not self.config.enabled or self._snapshots is None:
            return None
        
        result = {}
        for outcome in ["YES", "NO"]:
            snap = self.get_snapshot(market_id, outcome)
            if snap is not None:
                result[outcome] = snap
        
        return result if result else None
    
    def set_snapshots(self, market_id: str, snapshots: Dict[str, Dict[str, Any]]) -> None:
        """Cache all snapshots for market."""
        if not self.config.enabled:
            return
        
        for outcome, data in snapshots.items():
            self.set_snapshot(market_id, outcome, data)
    
    def invalidate_snapshots(self, market_id: str) -> None:
        """Invalidate all snapshots for market."""
        if self._snapshots is not None:
            for outcome in ["YES", "NO"]:
                key = (market_id, outcome)
                self._snapshots.delete(key)
    
    # ========== Signal Cache ==========
    
    def get_signals(self, cache_key: str) -> Optional[List[Any]]:
        """Get cached signals."""
        if not self.config.enabled or self._signals is None:
            self._signal_stats.misses += 1
            return None
        
        try:
            value = self._signals.get(cache_key)
            if value is not None:
                self._signal_stats.hits += 1
            else:
                self._signal_stats.misses += 1
            return value
        except Exception:
            self._signal_stats.errors += 1
            return None
    
    def set_signals(self, cache_key: str, signals: List[Any]) -> None:
        """Cache signals."""
        if not self.config.enabled or self._signals is None:
            return
        
        try:
            self._signals.set(cache_key, signals)
            self._signal_stats.sets += 1
            self._signal_stats.evictions = self._signals.eviction_count
        except Exception:
            self._signal_stats.errors += 1
    
    # ========== Decision Cache ==========
    
    def get_decision(self, cache_key: str) -> Optional[Any]:
        """Get cached decision."""
        if not self.config.enabled or self._decisions is None:
            self._decision_stats.misses += 1
            return None
        
        try:
            value = self._decisions.get(cache_key)
            if value is not None:
                self._decision_stats.hits += 1
            else:
                self._decision_stats.misses += 1
            return value
        except Exception:
            self._decision_stats.errors += 1
            return None
    
    def set_decision(self, cache_key: str, decision: Any) -> None:
        """Cache decision."""
        if not self.config.enabled or self._decisions is None:
            return
        
        try:
            self._decisions.set(cache_key, decision)
            self._decision_stats.sets += 1
            self._decision_stats.evictions = self._decisions.eviction_count
        except Exception:
            self._decision_stats.errors += 1
    
    # ========== Cache Management ==========
    
    def clear_all(self) -> None:
        """Clear all caches."""
        if self._markets:
            self._markets.clear()
        if self._snapshots:
            self._snapshots.clear()
        if self._signals:
            self._signals.clear()
        if self._decisions:
            self._decisions.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        return {
            "enabled": self.config.enabled,
            "markets": self._market_stats.to_dict(),
            "snapshots": self._snapshot_stats.to_dict(),
            "signals": self._signal_stats.to_dict(),
            "decisions": self._decision_stats.to_dict(),
            "sizes": {
                "markets": len(self._markets) if self._markets else 0,
                "snapshots": len(self._snapshots) if self._snapshots else 0,
                "signals": len(self._signals) if self._signals else 0,
                "decisions": len(self._decisions) if self._decisions else 0,
            },
            "config": {
                "market_ttl": self.config.market_ttl,
                "snapshot_ttl": self.config.snapshot_ttl,
                "signal_ttl": self.config.signal_ttl,
                "decision_ttl": self.config.decision_ttl,
            }
        }
    
    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._market_stats.reset()
        self._snapshot_stats.reset()
        self._signal_stats.reset()
        self._decision_stats.reset()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        stats = self.get_stats()
        
        total_hits = sum(
            stats[key]["hits"]
            for key in ["markets", "snapshots", "signals", "decisions"]
        )
        total_requests = sum(
            stats[key]["total_requests"]
            for key in ["markets", "snapshots", "signals", "decisions"]
        )
        
        return {
            "enabled": stats["enabled"],
            "total_hits": total_hits,
            "total_requests": total_requests,
            "overall_hit_rate": round(total_hits / total_requests, 4) if total_requests > 0 else 0.0,
            "cache_sizes": stats["sizes"],
        }
