"""Optimized repository with caching and batch operations."""
from __future__ import annotations

import json
import os
import logging
import sqlite3
import threading
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from db.repo import Repo
from db.cache import RepoCache, CacheConfig
from domain.models import Market, Signal, Snapshot
from utils.validation import validate_market_id
from utils.time import now_utc, to_iso

logger = logging.getLogger("db.optimized_repo")


class OptimizedRepo(Repo):
    """Repository with caching, batch operations, and performance optimizations."""
    
    def __init__(
        self,
        db_path: str,
        cache_config: Optional[CacheConfig] = None,
        enable_cache: bool = True
    ):
        super().__init__(db_path)
        self._ensure_schema_ready()
        
        # Initialize cache
        self._cache: Optional[RepoCache] = None
        if enable_cache:
            config = cache_config or CacheConfig()
            self._cache = RepoCache(config)
            logger.info(f"Cache enabled: {config}")
        else:
            logger.info("Cache disabled")
        self._sf_lock = threading.Lock()
        self._sf_inflight: Dict[str, threading.Event] = {}

    def _singleflight_enter(self, key: str) -> tuple[threading.Event, bool]:
        with self._sf_lock:
            evt = self._sf_inflight.get(key)
            if evt is None:
                evt = threading.Event()
                self._sf_inflight[key] = evt
                return evt, True
            return evt, False

    def _singleflight_done(self, key: str, evt: threading.Event) -> None:
        with self._sf_lock:
            current = self._sf_inflight.get(key)
            if current is evt:
                del self._sf_inflight[key]
                evt.set()

    def _ensure_schema_ready(self) -> None:
        """Best-effort schema bootstrap for empty databases."""
        try:
            with self.conn() as con:
                row = con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='markets' LIMIT 1"
                ).fetchone()
            if row:
                return
        except sqlite3.Error:
            pass

        schema_path = Path(__file__).resolve().parent / "schema.sql"
        if schema_path.exists():
            try:
                self.init_schema(str(schema_path))
            except Exception as e:
                logger.warning(f"Auto schema initialization failed: {e}")
    
    # ========== Market Operations with Cache ==========
    
    def get_market(self, market_id: str) -> Optional[Market]:
        """Get market with caching.
        
        Cache hit: ~0.01ms
        Cache miss + DB: ~1-2ms
        """
        validate_market_id(market_id)
        
        # Try cache first
        if self._cache:
            cached = self._cache.get_market(market_id)
            if cached:
                logger.debug(f"Market cache hit: {market_id}")
                return cached

        sf_key = f"market:{market_id}"
        sf_evt, is_leader = self._singleflight_enter(sf_key)
        if not is_leader:
            sf_evt.wait(timeout=2.0)
            if self._cache:
                cached = self._cache.get_market(market_id)
                if cached:
                    return cached
        
        # Cache miss - fetch from DB
        try:
            market = super().get_market(market_id)
        finally:
            if is_leader:
                self._singleflight_done(sf_key, sf_evt)
        
        # Cache for next time
        if market and self._cache:
            self._cache.set_market(market_id, market)
            logger.debug(f"Market cached: {market_id}")
        
        return market
    
    def list_markets(self, limit: int = 100) -> List[Market]:
        """List markets with optional caching.
        
        Note: Full list not cached due to variable limit.
        Consider caching per-market instead.
        """
        markets = super().list_markets(limit)
        
        # Cache individual markets
        if self._cache:
            for market in markets:
                self._cache.set_market(market.market_id, market)
        
        return markets
    
    def insert_market(self, market: Market) -> None:
        """Insert market and invalidate cache."""
        super().upsert_market(market)
        
        # Invalidate cache for this market
        if self._cache:
            self._cache.invalidate_market(market.market_id)
    
    # ========== Snapshot Operations with Cache ==========
    
    def get_latest_snapshots(
        self,
        market_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """Get latest snapshots with caching.
        
        This is the HOT PATH - called on every agent tick.
        
        Cache hit: ~0.01ms (500x faster)
        Cache miss + DB: ~5ms
        """
        validate_market_id(market_id)
        
        # Try cache first
        if self._cache:
            cached = self._cache.get_snapshots(market_id)
            if cached:
                logger.debug(f"Snapshot cache hit: {market_id}")
                return cached

        sf_key = f"snap:{market_id}"
        sf_evt, is_leader = self._singleflight_enter(sf_key)
        if not is_leader:
            sf_evt.wait(timeout=2.0)
            if self._cache:
                cached = self._cache.get_snapshots(market_id)
                if cached:
                    return cached
        
        try:
            result = self.get_latest_snapshots_batch([market_id]).get(market_id, {})
        finally:
            if is_leader:
                self._singleflight_done(sf_key, sf_evt)
        
        # Cache for next time
        if result and self._cache:
            self._cache.set_snapshots(market_id, result)
            logger.debug(f"Snapshots cached: {market_id}")
        
        return result

    def get_latest_snapshots_batch(
        self,
        market_ids: List[str]
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Batch fetch latest snapshots for many markets in one query."""
        if not market_ids:
            return {}

        result: Dict[str, Dict[str, Dict[str, Any]]] = {mid: {} for mid in market_ids}
        misses: List[str] = []

        if self._cache:
            for mid in market_ids:
                cached = self._cache.get_snapshots(mid)
                if cached:
                    result[mid] = cached
                else:
                    misses.append(mid)
        else:
            misses = list(market_ids)

        if not misses:
            return result

        qmarks = ",".join(["?"] * len(misses))
        with self.conn() as con:
            try:
                rows = con.execute(
                    f"""
                    SELECT market_id, outcome, bid, ask, mid, spread, liquidity, volume, implied_prob
                    FROM latest_snapshots
                    WHERE market_id IN ({qmarks})
                    """,
                    tuple(misses),
                ).fetchall()
            except Exception:
                rows = con.execute(
                    f"""
                    SELECT market_id, outcome, bid, ask, mid, spread, liquidity, volume, implied_prob
                    FROM (
                        SELECT market_id, outcome, bid, ask, mid, spread, liquidity, volume, implied_prob, ts,
                               ROW_NUMBER() OVER (PARTITION BY market_id, outcome ORDER BY ts DESC) AS rn
                        FROM snapshots
                        WHERE market_id IN ({qmarks})
                    )
                    WHERE rn=1
                    """,
                    tuple(misses),
                ).fetchall()

        for row in rows:
            mid = row[0]
            outcome = row[1]
            result.setdefault(mid, {})[outcome] = {
                "bid": row[2],
                "ask": row[3],
                "mid": row[4],
                "spread": row[5],
                "liquidity": row[6],
                "volume": row[7],
                "implied_prob": row[8],
            }

        if self._cache:
            for mid in misses:
                if result.get(mid):
                    self._cache.set_snapshots(mid, result[mid])

        return result
    
    def insert_snapshot(self, snapshot: Snapshot) -> None:
        """Insert snapshot and invalidate cache."""
        super().insert_snapshots([snapshot])
        
        # Invalidate cache for this market
        if self._cache:
            self._cache.invalidate_snapshots(snapshot.market_id)
    
    # ========== Batch Operations ==========
    
    def insert_snapshots_batch(self, snapshots: List[Snapshot]) -> int:
        """Batch insert snapshots for better performance.
        
        Single insert: ~1ms per snapshot
        Batch insert: ~0.1ms per snapshot (10x faster)
        
        Args:
            snapshots: List of snapshots to insert
            
        Returns:
            Number of snapshots inserted
        """
        if not snapshots:
            return 0
        
        with self.conn() as con:
            con.executemany(
                """
                INSERT INTO snapshots(
                    ts, market_id, outcome,
                    bid, ask, mid, spread, liquidity, volume, implied_prob
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        to_iso(s.ts),
                        s.market_id,
                        s.outcome,
                        s.bid,
                        s.ask,
                        s.mid,
                        s.spread,
                        s.liquidity,
                        s.volume,
                        s.implied_prob,
                    )
                    for s in snapshots
                ]
            )
        
        # Invalidate cache for affected markets
        if self._cache:
            for snapshot in snapshots:
                self._cache.invalidate_snapshots(snapshot.market_id)
        
        logger.info(f"Batch inserted {len(snapshots)} snapshots")
        return len(snapshots)
    
    def insert_signals_batch(self, signals: List[Signal]) -> int:
        """Batch insert signals.
        
        Args:
            signals: List of signals to insert
            
        Returns:
            Number of signals inserted
        """
        if not signals:
            return 0
        if os.getenv("PS_DEMO") != "1":
            before = len(signals)
            signals = [s for s in signals if (not s.scope_market_id) or str(s.scope_market_id).isdigit()]
            if signals:
                mids = sorted({str(s.scope_market_id) for s in signals if s.scope_market_id})
                if mids:
                    qmarks = ",".join(["?"] * len(mids))
                    with self.conn() as con:
                        rows = con.execute(
                            f"SELECT market_id FROM markets WHERE market_id IN ({qmarks})",
                            tuple(mids),
                        ).fetchall()
                    valid = {r["market_id"] for r in rows or []}
                    signals = [s for s in signals if (not s.scope_market_id) or str(s.scope_market_id) in valid]
            dropped = before - len(signals)
            if dropped:
                logger.debug("dropped_invalid_market_id=%s", dropped)
        if not signals:
            return 0
        
        with self.conn() as con:
            con.executemany(
                """
                INSERT INTO signals(
                    signal_id, ts, run_id, agent_id, kind,
                    scope_market_id, scope_group_key, scope_pair_key,
                    features_json, claim_json, candidates_json,
                    explain_short, explain_long
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        s.signal_id,
                        to_iso(s.ts),
                        s.run_id,
                        s.agent_id,
                        s.kind.value,
                        s.scope_market_id,
                        s.scope_group_key,
                        s.scope_pair_key,
                        json.dumps(s.features),
                        json.dumps(s.claim),
                        json.dumps([asdict(c) for c in s.candidates]),
                        s.explain_short,
                        s.explain_long,
                    )
                    for s in signals
                ]
            )
        
        logger.info(f"Batch inserted {len(signals)} signals")
        return len(signals)
    
    def insert_markets_batch(self, markets: List[Market]) -> int:
        """Batch insert markets.
        
        Args:
            markets: List of markets to insert
            
        Returns:
            Number of markets inserted
        """
        if not markets:
            return 0
        
        with self.conn() as con:
            con.executemany(
                """
                INSERT INTO markets(
                    market_id, slug, title, close_time, rules_hash, group_key
                )
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(market_id) DO UPDATE SET
                    slug=excluded.slug,
                    title=excluded.title,
                    close_time=excluded.close_time,
                    rules_hash=excluded.rules_hash,
                    group_key=excluded.group_key
                """,
                [
                    (
                        m.market_id,
                        m.slug,
                        m.title,
                        to_iso(m.close_time) if m.close_time else None,
                        m.rules_hash,
                        m.group_key,
                    )
                    for m in markets
                ]
            )
        
        # Invalidate cache for affected markets
        if self._cache:
            for market in markets:
                self._cache.invalidate_market(market.market_id)
        
        logger.info(f"Batch inserted {len(markets)} markets")
        return len(markets)
    
    # ========== Cache Management ==========
    
    def get_cache_stats(self) -> Optional[Dict[str, Any]]:
        """Get cache statistics.
        
        Returns:
            Cache statistics or None if cache disabled
        """
        if not self._cache:
            return None
        
        return self._cache.get_stats()
    
    def get_cache_summary(self) -> Optional[Dict[str, Any]]:
        """Get cache summary.
        
        Returns:
            Cache summary or None if cache disabled
        """
        if not self._cache:
            return None
        
        return self._cache.get_summary()
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        if self._cache:
            self._cache.clear_all()
            logger.info("Cache cleared")
    
    def reset_cache_stats(self) -> None:
        """Reset cache statistics."""
        if self._cache:
            self._cache.reset_stats()
            logger.info("Cache stats reset")
    
    # ========== Performance Monitoring ==========
    
    def record_query_stats(self, query_name: str, execution_time_ms: float) -> None:
        """Record query execution statistics.
        
        Args:
            query_name: Name/identifier of the query
            execution_time_ms: Execution time in milliseconds
        """
        try:
            with self.conn() as con:
                # Check if we have query_stats table
                con.execute(
                    """
                    INSERT INTO query_stats(query_name, execution_count, total_time_ms, avg_time_ms, last_run)
                    VALUES(?, 1, ?, ?, ?)
                    ON CONFLICT(query_name) DO UPDATE SET
                        execution_count = execution_count + 1,
                        total_time_ms = total_time_ms + excluded.total_time_ms,
                        avg_time_ms = (total_time_ms + excluded.total_time_ms) / (execution_count + 1),
                        last_run = excluded.last_run
                    """,
                    (query_name, execution_time_ms, execution_time_ms, to_iso(now_utc()))
                )
        except Exception:
            # Table might not exist yet
            pass
    
    def get_query_stats(self) -> List[Dict[str, Any]]:
        """Get query performance statistics.
        
        Returns:
            List of query statistics
        """
        try:
            with self.conn() as con:
                rows = con.execute(
                    """
                    SELECT query_name, execution_count, avg_time_ms, last_run
                    FROM query_stats
                    ORDER BY avg_time_ms DESC
                    LIMIT 20
                    """
                ).fetchall()
                
                return [
                    {
                        "query_name": row[0],
                        "execution_count": row[1],
                        "avg_time_ms": round(row[2], 2),
                        "last_run": row[3],
                    }
                    for row in rows
                ]
        except Exception:
            return []
    
    # ========== Migration Helper ==========
    
    def apply_performance_migration(self) -> None:
        """Apply performance optimization migration (indexes, materialized views)."""
        import os
        from pathlib import Path
        
        migration_path = Path(__file__).parent / "migrations" / "001_performance_indexes.sql"
        
        if not migration_path.exists():
            logger.warning(f"Migration file not found: {migration_path}")
            return
        
        logger.info(f"Applying performance migration: {migration_path}")
        
        with open(migration_path) as f:
            sql = f.read()
        
        with self.conn() as con:
            # Execute as a single script so triggers/views (BEGIN..END) aren't broken by naive splitting.
            try:
                con.executescript(sql)
            except Exception as e:
                logger.error(f"Performance migration failed: {e}")
                # Keep the app running even if migration partially applies (best-effort).

        logger.info("Performance migration completed")
