"""
EXPERIMENTAL execution loop.

This loop is not used in canonical runtime.
Kept for research purposes only.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional
from dataclasses import dataclass
from time import perf_counter

from app.config import AppConfig
from db.optimized_repo import OptimizedRepo
from dispatcher.bus import EventBus
from dispatcher.events import Alert, MarketTick, Timer
from dispatcher.scheduler import Scheduler
from agents.enhanced_base import EnhancedAgent, AgentContext
from decision.engine_v2 import DecisionEngine
from execution.reconcile import reconcile_paper
from ingest.ingestor import Ingestor
from ingest.polymarket_client import PolymarketClient
from db.agent_provider import RepoAgentDataProvider
from utils.time import now_utc
from app.risk_gate import RiskGate

log = logging.getLogger("dispatcher.optimized_loop")


@dataclass
class LoopMetrics:
    """Metrics for main loop performance."""
    iterations: int = 0
    markets_ingested: int = 0
    snapshots_ingested: int = 0
    events_processed: int = 0
    errors: int = 0
    
    # Performance metrics
    total_ingest_time_sec: float = 0.0
    total_agent_time_sec: float = 0.0
    total_decision_time_sec: float = 0.0
    total_execution_time_sec: float = 0.0
    
    last_ingest: Optional[datetime] = None
    last_reconcile: Optional[datetime] = None
    
    @property
    def avg_ingest_time_ms(self) -> float:
        """Average ingest time in milliseconds."""
        count = 1 if self.last_ingest else 0
        return (self.total_ingest_time_sec / count * 1000) if count > 0 else 0.0
    
    @property
    def avg_agent_time_ms(self) -> float:
        """Average agent processing time in milliseconds."""
        return (self.total_agent_time_sec / self.iterations * 1000) if self.iterations > 0 else 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "iterations": self.iterations,
            "markets_ingested": self.markets_ingested,
            "snapshots_ingested": self.snapshots_ingested,
            "events_processed": self.events_processed,
            "errors": self.errors,
            "avg_ingest_time_ms": round(self.avg_ingest_time_ms, 2),
            "avg_agent_time_ms": round(self.avg_agent_time_ms, 2),
            "last_ingest": self.last_ingest.isoformat() if self.last_ingest else None,
            "last_reconcile": self.last_reconcile.isoformat() if self.last_reconcile else None,
        }


class OptimizedMainLoop:
    """Optimized main dispatcher loop with caching and batch operations."""
    
    def __init__(
        self,
        config: AppConfig,
        repo: OptimizedRepo,
        bus: EventBus,
        run_id: str,
    ):
        self.config = config
        self.repo = repo
        self.bus = bus
        self.run_id = run_id
        
        # Components
        self.scheduler = Scheduler(
            poll_interval_sec=config.dispatcher.poll_interval_sec,
            reconcile_interval_sec=config.dispatcher.reconcile_interval_sec,
        )
        self.ingestor = Ingestor(repo, PolymarketClient())
        self.decision_engine = DecisionEngine(repo, config.decision, risk_gate=RiskGate(repo, config))
        
        # Agents
        self.fast_agents: List[EnhancedAgent] = []
        self.slow_agents: List[EnhancedAgent] = []
        self._load_agents()
        
        # State
        self._stop = False
        self._metrics = LoopMetrics()
        self._ingest_failures = 0
        self._next_ingest_monotonic = 0.0
        
        # Cache for market list (refreshed periodically)
        self._market_cache: List = []
        self._market_cache_time: Optional[datetime] = None
        self._market_cache_ttl_sec = 60  # Refresh every minute
    
    def _load_agents(self) -> None:
        """Load and initialize agents."""
        
        # Fast agents (run per-market)
        if self.config.enable_agents:
            try:
                from agents.quant import QuantAgent
                self.fast_agents.append(
                    QuantAgent(
                        min_liquidity=self.config.agent.min_liquidity,
                        max_spread=self.config.agent.max_spread,
                    )
                )
                log.info("Loaded QuantAgent")
            except Exception as e:
                log.warning(f"Failed to load QuantAgent: {e}")
        
        # Slow agents (run global)
        for agent_name in ["scout", "logic", "auditor", "risk"]:
            if not self.config.enable_agents:
                break
            
            try:
                module = __import__(f"agents.{agent_name}", fromlist=[f"{agent_name.capitalize()}Agent"])
                agent_class = getattr(module, f"{agent_name.capitalize()}Agent")
                self.slow_agents.append(agent_class())
                log.info(f"Loaded {agent_name.capitalize()}Agent")
            except Exception as e:
                log.debug(f"Optional agent {agent_name} not loaded: {e}")
    
    def _get_markets_cached(self) -> List:
        """Get markets with caching to reduce DB load.
        
        Markets don't change frequently, so we can cache the list.
        """
        now = now_utc()
        
        # Check if cache is fresh
        if (self._market_cache and 
            self._market_cache_time and
            (now - self._market_cache_time).total_seconds() < self._market_cache_ttl_sec):
            log.debug(f"Using cached market list ({len(self._market_cache)} markets)")
            return self._market_cache
        
        # Refresh cache
        markets = self.repo.list_markets(limit=200)
        self._market_cache = markets
        self._market_cache_time = now
        log.debug(f"Refreshed market cache ({len(markets)} markets)")
        
        return markets
    
    def _create_context(self, now: datetime) -> AgentContext:
        """Create agent context with cached data."""
        ctx = AgentContext(
            run_id=self.run_id,
            now=now,
            repo=self.repo,
            settings=self.config,
            data_provider=RepoAgentDataProvider(self.repo),
        )
        
        # Pre-populate markets in context to avoid repeated queries
        ctx.markets = self._market_cache if self._market_cache else None
        if self._market_cache and hasattr(self.repo, "get_latest_snapshots_batch"):
            market_ids = [m.market_id for m in self._market_cache]
            try:
                ctx.latest_snapshots = self.repo.get_latest_snapshots_batch(market_ids)
            except Exception:
                ctx.latest_snapshots = None
        
        return ctx
    
    def _run_fast_agents_batch(self, ctx: AgentContext, market_ids: List[str]) -> None:
        """Run fast agents on multiple markets with batch insert.
        
        This is a key optimization:
        - Process all markets
        - Collect all signals
        - Batch insert at the end
        
        Instead of: insert → insert → insert (N DB calls)
        We do: collect → collect → collect → batch insert (1 DB call)
        """
        start = perf_counter()
        all_signals = []
        
        for market_id in market_ids:
            for agent in self.fast_agents:
                try:
                    signals = agent.propose(ctx, market_id=market_id)
                    if signals:
                        all_signals.extend(signals)
                
                except Exception as e:
                    self._metrics.errors += 1
                    log.exception(f"Fast agent {agent.agent_id} failed on {market_id}: {e}")
        
        # Batch insert all signals at once
        if all_signals:
            self.repo.insert_signals_batch(all_signals)
            log.info(f"Fast agents generated {len(all_signals)} signals across {len(market_ids)} markets")
        
        elapsed = perf_counter() - start
        self._metrics.total_agent_time_sec += elapsed
        log.debug(f"Fast agent batch processing: {elapsed:.3f}s for {len(market_ids)} markets")
    
    def _run_slow_agents(self, ctx: AgentContext) -> None:
        """Run slow agents (global scans) with batch operations."""
        start = perf_counter()
        all_signals = []
        
        for agent in self.slow_agents:
            try:
                # Try global propose first
                try:
                    signals = agent.propose(ctx)
                except TypeError:
                    # Fallback to per-market scan
                    signals = []
                    markets = self._get_markets_cached()
                    for m in markets:
                        signals.extend(agent.propose(ctx, market_id=m.market_id))
                
                if signals:
                    all_signals.extend(signals)
            
            except Exception as e:
                self._metrics.errors += 1
                log.exception(f"Slow agent {agent.agent_id} failed: {e}")
        
        # Batch insert all signals
        if all_signals:
            self.repo.insert_signals_batch(all_signals)
            log.info(f"Slow agents generated {len(all_signals)} signals")
        
        elapsed = perf_counter() - start
        log.debug(f"Slow agent processing: {elapsed:.3f}s")
    
    def _handle_ingest(self, now: datetime) -> None:
        """Handle market data ingestion with timing."""
        start = perf_counter()
        
        try:
            m_cnt, s_cnt = self.ingestor.ingest()
            self._ingest_failures = 0
            self._next_ingest_monotonic = 0.0
            self._metrics.markets_ingested += m_cnt
            self._metrics.snapshots_ingested += s_cnt
            self._metrics.last_ingest = now
            
            log.info(f"Ingest: {m_cnt} markets, {s_cnt} snapshots")
            
            # Get fresh market list for processing
            markets = self._get_markets_cached()
            
            # Batch process all markets with fast agents
            market_ids = [m.market_id for m in markets]
            
            if market_ids and self.config.enable_agents:
                ctx = self._create_context(now)
                self._run_fast_agents_batch(ctx, market_ids)
        
        except Exception as e:
            self._metrics.errors += 1
            self._ingest_failures += 1
            retry_in = min(30.0, 0.5 * (2 ** (self._ingest_failures - 1)))
            self._next_ingest_monotonic = time.monotonic() + retry_in
            log.exception(f"Ingest failed: {e}")
            self.bus.publish(
                Alert(
                    ts=now,
                    severity="ERROR",
                    code="INGEST_FAIL",
                    message=f"{e} | retry in {retry_in:.1f}s",
                )
            )
        
        finally:
            elapsed = perf_counter() - start
            self._metrics.total_ingest_time_sec += elapsed
            self.repo.record_query_stats("ingest_full", elapsed * 1000)
    
    def _handle_reconcile(self, now: datetime) -> None:
        """Handle decision reconciliation with timing."""
        ctx = self._create_context(now)
        
        # Run slow agents first
        if self.config.enable_agents:
            self._run_slow_agents(ctx)
        
        # Run decision engine
        decision_start = perf_counter()
        decision_count = 0
        if self.config.enable_decision:
            try:
                decision_count = self.decision_engine.reconcile(self.run_id)
            except Exception as e:
                self._metrics.errors += 1
                log.exception(f"Decision engine failed: {e}")
        
        decision_elapsed = perf_counter() - decision_start
        self._metrics.total_decision_time_sec += decision_elapsed
        
        # Execute paper trades
        exec_start = perf_counter()
        executed_count = 0
        if self.config.enable_execution:
            try:
                executed_count = reconcile_paper(self.repo, self.run_id)
            except Exception as e:
                self._metrics.errors += 1
                log.exception(f"Paper execution failed: {e}")
        
        exec_elapsed = perf_counter() - exec_start
        self._metrics.total_execution_time_sec += exec_elapsed
        
        self._metrics.last_reconcile = now
        
        log.info(
            f"Reconcile: {decision_count} decisions ({decision_elapsed:.3f}s), "
            f"{executed_count} executed ({exec_elapsed:.3f}s)"
        )
        
        # Log performance summary
        if self.repo:
            cache_stats = self.repo.get_cache_summary()
            if cache_stats:
                log.info(
                    f"Cache: {cache_stats['overall_hit_rate']:.2%} hit rate, "
                    f"{cache_stats['total_hits']}/{cache_stats['total_requests']} hits"
                )
    
    def _handle_event(self, event: Any) -> None:
        """Handle a single event."""
        self._metrics.events_processed += 1
        
        try:
            if isinstance(event, Timer):
                if event.purpose == "reconcile":
                    self._handle_reconcile(event.ts)
            
            elif isinstance(event, Alert):
                self.repo.log_event(
                    ts=event.ts,
                    level=event.severity,
                    component="alert",
                    message=f"{event.code}: {event.message}",
                    payload={},
                )
        
        except Exception as e:
            self._metrics.errors += 1
            log.exception(f"Event handler failed: {e}")
    
    def stop(self) -> None:
        """Stop the loop."""
        self._stop = True
        log.info("Optimized main loop stopping...")
    
    def get_metrics(self) -> dict:
        """Get loop metrics."""
        metrics = self._metrics.to_dict()
        
        # Add cache stats
        cache_stats = self.repo.get_cache_summary()
        if cache_stats:
            metrics["cache"] = cache_stats
        
        # Add agent metrics
        agent_metrics = {}
        for agent in self.fast_agents + self.slow_agents:
            agent_metrics[agent.agent_id] = agent.get_metrics().to_dict()
        metrics["agents"] = agent_metrics
        
        return metrics
    
    def run_forever(self) -> None:
        """Main event loop with optimizations."""
        
        log.info("Optimized main loop starting...")
        log.info(f"Config: poll={self.config.dispatcher.poll_interval_sec}s, "
                 f"reconcile={self.config.dispatcher.reconcile_interval_sec}s")
        
        # Apply performance migration if needed
        try:
            self.repo.apply_performance_migration()
        except Exception as e:
            log.warning(f"Could not apply performance migration: {e}")
        
        while not self._stop:
            self._metrics.iterations += 1
            now = datetime.now(timezone.utc)
            
            # Scheduler tick
            do_poll, do_reconcile = self.scheduler.tick(now)
            
            # Ingest with batch processing
            if do_poll and self.config.enable_ingest and time.monotonic() >= self._next_ingest_monotonic:
                self._handle_ingest(now)
            
            # Reconcile
            if do_reconcile:
                self.bus.publish(Timer(ts=now, purpose="reconcile"))
            
            # Process events in batch
            events_processed = 0
            for _ in range(self.config.dispatcher.event_batch_size):
                event = self.bus.pop()
                if event is None:
                    break
                self._handle_event(event)
                events_processed += 1
            
            # Periodic metrics logging
            if self._metrics.iterations % 100 == 0:
                log.info(f"Loop metrics: {self.get_metrics()}")
            
            # Sleep
            time.sleep(self.config.dispatcher.sleep_sec)
        
        log.info(f"Optimized main loop stopped. Final metrics: {self._metrics.to_dict()}")


# Alias for compatibility
MainLoop = OptimizedMainLoop
