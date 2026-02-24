# Конкретные улучшения существующего кода

## 1. Улучшенный DecisionEngine

```python
# decision/engine_v1.py
"""Improved decision engine with better separation of concerns."""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from db.repo import Repo
from app.config import DecisionConfig
from utils.time import now_utc, to_iso
from utils.pricing import calculate_sum_mid, is_tradeable


class ActionType(str, Enum):
    """Decision action types."""
    HOLD = "HOLD"
    PAPER_BUY_BOTH = "PAPER_BUY_BOTH"
    PAPER_CLOSE_BOTH = "PAPER_CLOSE_BOTH"
    PAPER_BUY_YES = "PAPER_BUY_YES"
    PAPER_BUY_NO = "PAPER_BUY_NO"
    PAPER_CLOSE_YES = "PAPER_CLOSE_YES"
    PAPER_CLOSE_NO = "PAPER_CLOSE_NO"


class DecisionStatus(str, Enum):
    """Decision status."""
    OK = "OK"
    INVESTIGATE = "INVESTIGATE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class Decision:
    """Immutable decision object."""
    market_id: str
    action: ActionType
    status: DecisionStatus
    reason: str
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "market_id": self.market_id,
            "action": self.action.value,
            "status": self.status.value,
            "reason": self.reason,
            "metadata": self.metadata or {},
        }


@dataclass
class MarketCase:
    """Market case with all relevant data."""
    market_id: str
    sum_mid: Optional[float]
    spread: Optional[float]
    liquidity: Optional[float]
    status: str = "OK"
    reason: str = ""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketCase":
        """Create from dict."""
        return cls(
            market_id=data["market_id"],
            sum_mid=data.get("sum_mid"),
            spread=data.get("spread"),
            liquidity=data.get("liq"),
            status=data.get("status", "OK"),
            reason=data.get("reason", ""),
        )


class DecisionStrategy(ABC):
    """Base class for decision strategies."""
    
    @abstractmethod
    def decide(self, case: MarketCase, positions: Dict[str, bool]) -> Decision:
        """Make a decision for a case."""
        pass


class ArbStrategy(DecisionStrategy):
    """Arbitrage strategy based on YES+NO sum."""
    
    def __init__(self, config: DecisionConfig):
        self.config = config
    
    def decide(self, case: MarketCase, positions: Dict[str, bool]) -> Decision:
        """Decide based on arb opportunity."""
        
        # Default: HOLD
        action = ActionType.HOLD
        status = DecisionStatus(case.status)
        reason = case.reason or "No clear signal"
        metadata = {}
        
        # Check if we have required data
        if case.sum_mid is None or case.spread is None or case.liquidity is None:
            return Decision(
                market_id=case.market_id,
                action=action,
                status=status,
                reason="Missing market data",
                metadata=metadata,
            )
        
        # Check tradeability
        tradeable = is_tradeable(
            case.spread,
            case.liquidity,
            self.config.max_spread,
            self.config.min_liquidity,
        )
        
        if not tradeable:
            return Decision(
                market_id=case.market_id,
                action=action,
                status=DecisionStatus.BLOCKED,
                reason=f"Not tradeable: spread={case.spread:.3f}, liq={case.liquidity:.1f}",
                metadata={"spread": case.spread, "liquidity": case.liquidity},
            )
        
        # Check for arb opportunities
        has_both = positions.get("YES", False) and positions.get("NO", False)
        
        metadata = {
            "sum_mid": case.sum_mid,
            "spread": case.spread,
            "liquidity": case.liquidity,
            "has_positions": {"YES": positions.get("YES", False), "NO": positions.get("NO", False)},
        }
        
        # Buy signal: sum < threshold and no existing position
        if not has_both and case.sum_mid < self.config.arb_buy_threshold and status == DecisionStatus.OK:
            action = ActionType.PAPER_BUY_BOTH
            status = DecisionStatus.OK
            reason = f"ARB buy opportunity: sum={case.sum_mid:.3f} < {self.config.arb_buy_threshold:.3f}"
        
        # Close signal: sum >= threshold and have position
        elif has_both and case.sum_mid >= self.config.arb_close_threshold and status == DecisionStatus.OK:
            action = ActionType.PAPER_CLOSE_BOTH
            status = DecisionStatus.OK
            reason = f"ARB close: sum={case.sum_mid:.3f} >= {self.config.arb_close_threshold:.3f}"
        
        # Near-threshold: flag for investigation
        elif status == DecisionStatus.OK and tradeable:
            delta_from_buy = abs(case.sum_mid - self.config.arb_buy_threshold)
            if delta_from_buy < 0.01:
                action = ActionType.HOLD
                status = DecisionStatus.INVESTIGATE
                reason = f"Near arb threshold: sum={case.sum_mid:.3f}, delta={delta_from_buy:.4f}"
        
        return Decision(
            market_id=case.market_id,
            action=action,
            status=status,
            reason=reason,
            metadata=metadata,
        )


class DecisionEngine:
    """Decision engine with strategy pattern and better testability."""
    
    def __init__(
        self,
        repo: Repo,
        config: DecisionConfig,
        strategies: Optional[List[DecisionStrategy]] = None,
        risk_gate = None,
    ):
        self.repo = repo
        self.config = config
        self.strategies = strategies or [ArbStrategy(config)]
        self.risk_gate = risk_gate
        self._decision_cache: Dict[str, tuple[datetime, Decision]] = {}
    
    def _get_positions(self, market_id: str) -> Dict[str, bool]:
        """Get current positions for market."""
        try:
            self.repo.ensure_paper_schema()
            with self.repo.conn() as con:
                rows = con.execute(
                    """
                    SELECT outcome, 1
                    FROM paper_positions
                    WHERE market_id=? AND status='OPEN'
                    """,
                    (market_id,)
                ).fetchall()
            
            return {outcome: True for outcome, _ in rows}
        
        except Exception:
            return {}
    
    def _check_rate_limit(self, market_id: str, decision: Decision, now: datetime) -> bool:
        """Check if we should emit this decision based on rate limiting."""
        
        # Always allow non-HOLD actions
        if decision.action != ActionType.HOLD:
            return True
        
        # Check cache
        if market_id in self._decision_cache:
            last_time, last_decision = self._decision_cache[market_id]
            
            # Same decision?
            if (last_decision.action == decision.action and
                last_decision.status == decision.status and
                last_decision.reason == decision.reason):
                
                # Within rate limit window?
                if (now - last_time).total_seconds() < self.config.min_emit_interval_sec:
                    return False
        
        return True
    
    def _check_risk_gate(self, market_id: str) -> Optional[Decision]:
        """Check risk gate, return Decision if blocked."""
        if self.risk_gate is None:
            return None
        
        try:
            verdict = self.risk_gate.check_market(market_id)
            
            if verdict and not getattr(verdict, "allow", True):
                return Decision(
                    market_id=market_id,
                    action=ActionType.HOLD,
                    status=DecisionStatus.BLOCKED,
                    reason=f"{getattr(verdict, 'code', 'GATE')}: {getattr(verdict, 'reason', '')}",
                    metadata={"gate_verdict": verdict},
                )
        
        except Exception as e:
            # Don't let gate failures kill decision engine
            pass
        
        return None
    
    def reconcile(self, run_id: str) -> int:
        """Main reconciliation loop."""
        
        # Check pause status
        paused = False
        try:
            paused = bool(self.repo.is_paused())
        except Exception:
            pass
        
        # Get cases
        cases = self.repo.list_cases(minutes_signals=30, minutes_snaps=10)
        now = now_utc()
        written = 0
        
        for case_dict in cases:
            case = MarketCase.from_dict(case_dict)
            
            # Paused? HOLD everything
            if paused:
                decision = Decision(
                    market_id=case.market_id,
                    action=ActionType.HOLD,
                    status=DecisionStatus.OK,
                    reason="System paused",
                    metadata={"paused": True},
                )
                written += self._write_decision(run_id, now, decision, paused=True)
                continue
            
            # Check risk gate
            gate_decision = self._check_risk_gate(case.market_id)
            if gate_decision:
                written += self._write_decision(run_id, now, gate_decision, paused=False)
                continue
            
            # Get positions
            positions = self._get_positions(case.market_id)
            
            # Run strategies (first one wins for now)
            decision = self.strategies[0].decide(case, positions)
            
            # Write if passes rate limit
            if self._check_rate_limit(case.market_id, decision, now):
                written += self._write_decision(run_id, now, decision, paused=False)
                self._decision_cache[case.market_id] = (now, decision)
        
        return written
    
    def _write_decision(
        self,
        run_id: str,
        now: datetime,
        decision: Decision,
        paused: bool,
    ) -> int:
        """Write decision to database."""
        
        payload = {
            "source": self.__class__.__name__,
            "paused": paused,
            "config": {
                "arb_buy_threshold": self.config.arb_buy_threshold,
                "arb_close_threshold": self.config.arb_close_threshold,
                "max_spread": self.config.max_spread,
                "min_liquidity": self.config.min_liquidity,
            },
            "decision_metadata": decision.metadata or {},
        }
        
        self.repo.insert_decision_v0(
            decision_id=str(uuid.uuid4()),
            ts=to_iso(now),
            run_id=run_id,
            market_id=decision.market_id,
            action=decision.action.value,
            status=decision.status.value,
            reason=decision.reason,
            payload_json=json.dumps(payload),
        )
        
        return 1
```

## 2. Улучшенный QuantAgent

```python
# agents/quant_v2.py
"""Improved QuantAgent with better structure."""

from __future__ import annotations
import uuid
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from agents.enhanced_base import EnhancedAgent, AgentContext
from domain.enums import SignalKind
from domain.models import Signal
from utils.pricing import get_mid, calculate_spread
from utils.validation import validate_market_id


@dataclass
class QualityThresholds:
    """Quality thresholds for market data."""
    min_liquidity: float = 50.0
    max_spread: float = 0.10
    partition_range: tuple[float, float] = (0.95, 1.05)


class QuantAgent(EnhancedAgent):
    """Quantitative quality checks agent."""
    
    agent_id = "quant.v2"
    
    def __init__(self, thresholds: Optional[QualityThresholds] = None):
        super().__init__()
        self.thresholds = thresholds or QualityThresholds()
    
    def _check_liquidity(
        self,
        ctx: AgentContext,
        market_id: str,
        outcome: str,
        liquidity: float,
    ) -> Optional[Signal]:
        """Check liquidity constraint."""
        
        if liquidity >= self.thresholds.min_liquidity:
            return None
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.RISK_CONSTRAINT,
            scope_market_id=market_id,
            features={
                "liquidity": float(liquidity),
                "min_liquidity": self.thresholds.min_liquidity,
                "shortfall": self.thresholds.min_liquidity - float(liquidity),
            },
            claim={
                "type": "min_liquidity",
                "outcome": outcome,
                "severity": "high" if liquidity < self.thresholds.min_liquidity * 0.5 else "medium",
            },
            explain_short=f"Low liquidity: {market_id}/{outcome} liq={liquidity:.1f} < {self.thresholds.min_liquidity:.1f}",
            explain_long=(
                "Risk constraint: Thin order books increase slippage and market impact. "
                "Trading this market may result in poor fills and high transaction costs."
            ),
        )
    
    def _check_spread(
        self,
        ctx: AgentContext,
        market_id: str,
        outcome: str,
        spread: float,
    ) -> Optional[Signal]:
        """Check spread constraint."""
        
        if spread <= self.thresholds.max_spread:
            return None
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.RISK_CONSTRAINT,
            scope_market_id=market_id,
            features={
                "spread": float(spread),
                "max_spread": self.thresholds.max_spread,
                "excess": float(spread) - self.thresholds.max_spread,
            },
            claim={
                "type": "max_spread",
                "outcome": outcome,
                "severity": "high" if spread > self.thresholds.max_spread * 2 else "medium",
            },
            explain_short=f"Wide spread: {market_id}/{outcome} spread={spread:.3f} > {self.thresholds.max_spread:.3f}",
            explain_long=(
                "Risk constraint: Wide bid-ask spreads erode trading edge and increase costs. "
                "The expected profit must exceed the spread to make the trade worthwhile."
            ),
        )
    
    def _check_partition(
        self,
        ctx: AgentContext,
        market_id: str,
        yes_mid: float,
        no_mid: float,
    ) -> Optional[Signal]:
        """Check partition property: YES + NO ≈ 1."""
        
        sum_mid = yes_mid + no_mid
        min_sum, max_sum = self.thresholds.partition_range
        
        if min_sum <= sum_mid <= max_sum:
            return None
        
        deviation = sum_mid - 1.0
        severity = "critical" if abs(deviation) > 0.10 else "high"
        
        return Signal(
            signal_id=str(uuid.uuid4()),
            ts=ctx.now,
            run_id=ctx.run_id,
            agent_id=self.agent_id,
            kind=SignalKind.QUALITY_ALERT,
            scope_market_id=market_id,
            features={
                "sum_mid": sum_mid,
                "yes_mid": yes_mid,
                "no_mid": no_mid,
                "deviation": deviation,
                "abs_deviation": abs(deviation),
            },
            claim={
                "type": "partition_sum",
                "expected_range": list(self.thresholds.partition_range),
                "severity": severity,
            },
            explain_short=f"Partition violation: {market_id} YES+NO={sum_mid:.3f} (dev={deviation:+.3f})",
            explain_long=(
                f"Quality alert: YES({yes_mid:.3f}) + NO({no_mid:.3f}) = {sum_mid:.3f} "
                f"deviates from expected value of 1.0 by {deviation:+.3f}. "
                "This may indicate stale data, pricing inconsistency, or arbitrage opportunity."
            ),
        )
    
    def _propose(
        self,
        ctx: AgentContext,
        market_id: Optional[str] = None,
    ) -> List[Signal]:
        """Generate quality signals for market."""
        
        if not market_id:
            return []
        
        validate_market_id(market_id)
        
        # Get snapshots
        snapshots = ctx.get_market_snapshots(market_id)
        if not snapshots:
            return []
        
        signals = []
        
        # Check each outcome
        for outcome in ["YES", "NO"]:
            snap = snapshots.get(outcome, {})
            
            # Liquidity check
            liq = snap.get("liquidity")
            if liq is not None:
                sig = self._check_liquidity(ctx, market_id, outcome, float(liq))
                if sig:
                    signals.append(sig)
            
            # Spread check
            spr = snap.get("spread")
            if spr is not None:
                sig = self._check_spread(ctx, market_id, outcome, float(spr))
                if sig:
                    signals.append(sig)
        
        # Partition check (requires both YES and NO)
        yes_mid = get_mid(snapshots, "YES")
        no_mid = get_mid(snapshots, "NO")
        
        if yes_mid is not None and no_mid is not None:
            sig = self._check_partition(ctx, market_id, yes_mid, no_mid)
            if sig:
                signals.append(sig)
        
        return signals
```

## 3. Улучшенный Main Loop

```python
# dispatcher/main_loop.py
"""Improved main dispatcher loop with better error handling."""

from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional
from dataclasses import dataclass

from app.config import AppConfig
from db.optimized_repo import OptimizedRepo
from dispatcher.bus import EventBus
from dispatcher.events import Alert, MarketTick, Timer
from dispatcher.scheduler import Scheduler
from agents.enhanced_base import EnhancedAgent, AgentContext
from decision.engine_v1 import DecisionEngine
from execution.reconcile import reconcile_paper
from ingest.ingestor import Ingestor
from ingest.polymarket_client import PolymarketClient

log = logging.getLogger("dispatcher.loop")


@dataclass
class LoopMetrics:
    """Metrics for main loop."""
    iterations: int = 0
    markets_ingested: int = 0
    snapshots_ingested: int = 0
    events_processed: int = 0
    errors: int = 0
    last_ingest: Optional[datetime] = None
    last_reconcile: Optional[datetime] = None


class MainLoop:
    """Main dispatcher loop with improved error handling and metrics."""
    
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
        self.decision_engine = DecisionEngine(repo, config.decision)
        
        # Agents
        self.fast_agents: List[EnhancedAgent] = []
        self.slow_agents: List[EnhancedAgent] = []
        self._load_agents()
        
        # State
        self._stop = False
        self._metrics = LoopMetrics()
    
    def _load_agents(self) -> None:
        """Load and initialize agents."""
        
        # Fast agents (run per-market)
        if self.config.enable_agents:
            try:
                from agents.quant_v2 import QuantAgent, QualityThresholds
                self.fast_agents.append(
                    QuantAgent(
                        thresholds=QualityThresholds(
                            min_liquidity=self.config.agent.min_liquidity,
                            max_spread=self.config.agent.max_spread,
                        )
                    )
                )
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
                log.info(f"Loaded agent: {agent_name}")
            except Exception as e:
                log.warning(f"Failed to load {agent_name} agent: {e}")
    
    def _create_context(self, now: datetime) -> AgentContext:
        """Create agent context."""
        return AgentContext(
            run_id=self.run_id,
            now=now,
            repo=self.repo,
            settings=self.config,
        )
    
    def _run_fast_agents(self, ctx: AgentContext, market_id: str) -> None:
        """Run fast agents for a single market."""
        
        for agent in self.fast_agents:
            try:
                signals = agent.propose(ctx, market_id=market_id)
                
                if signals:
                    self.repo.insert_signals_batch(signals)
                    log.debug(f"{agent.agent_id} generated {len(signals)} signals for {market_id}")
            
            except Exception as e:
                self._metrics.errors += 1
                log.exception(f"Fast agent {agent.agent_id} failed: {e}")
                self.repo.log_event(
                    ts=ctx.now,
                    level="ERROR",
                    component=f"agent:{agent.agent_id}",
                    message=str(e),
                    payload={"market_id": market_id},
                )
    
    def _run_slow_agents(self, ctx: AgentContext) -> None:
        """Run slow agents (global scans)."""
        
        for agent in self.slow_agents:
            try:
                # Try global propose first
                try:
                    signals = agent.propose(ctx)
                except TypeError:
                    # Fallback to per-market scan
                    signals = []
                    markets = self.repo.list_markets(limit=200)
                    for m in markets:
                        signals.extend(agent.propose(ctx, market_id=m.market_id))
                
                if signals:
                    self.repo.insert_signals_batch(signals)
                    log.info(f"{agent.agent_id} generated {len(signals)} signals")
            
            except Exception as e:
                self._metrics.errors += 1
                log.exception(f"Slow agent {agent.agent_id} failed: {e}")
                self.repo.log_event(
                    ts=ctx.now,
                    level="ERROR",
                    component=f"agent:{agent.agent_id}",
                    message=str(e),
                    payload={},
                )
    
    def _handle_ingest(self, now: datetime) -> None:
        """Handle market data ingestion."""
        
        try:
            m_cnt, s_cnt = self.ingestor.ingest()
            self._metrics.markets_ingested += m_cnt
            self._metrics.snapshots_ingested += s_cnt
            self._metrics.last_ingest = now
            
            log.info(f"Ingest: {m_cnt} markets, {s_cnt} snapshots")
            
            # Trigger market ticks
            markets = self.repo.list_markets(limit=200)
            for m in markets:
                self.bus.publish(MarketTick(ts=now, market_id=m.market_id))
        
        except Exception as e:
            self._metrics.errors += 1
            log.exception(f"Ingest failed: {e}")
            self.bus.publish(
                Alert(ts=now, severity="ERROR", code="INGEST_FAIL", message=str(e))
            )
    
    def _handle_reconcile(self, now: datetime) -> None:
        """Handle decision reconciliation."""
        
        ctx = self._create_context(now)
        
        # Run slow agents first
        if self.config.enable_agents:
            self._run_slow_agents(ctx)
        
        # Run decision engine
        decision_count = 0
        if self.config.enable_decision:
            try:
                decision_count = self.decision_engine.reconcile(self.run_id)
            except Exception as e:
                self._metrics.errors += 1
                log.exception(f"Decision engine failed: {e}")
        
        # Execute paper trades
        executed_count = 0
        if self.config.enable_execution:
            try:
                executed_count = reconcile_paper(self.repo, self.run_id)
            except Exception as e:
                self._metrics.errors += 1
                log.exception(f"Paper execution failed: {e}")
        
        self._metrics.last_reconcile = now
        
        log.info(f"Reconcile: {decision_count} decisions, {executed_count} executed")
        
        self.repo.log_event(
            ts=now,
            level="INFO",
            component="reconcile",
            message=f"Decisions: {decision_count}, Executed: {executed_count}",
            payload={
                "decisions": decision_count,
                "executed": executed_count,
            },
        )
    
    def _handle_event(self, event: Any) -> None:
        """Handle a single event."""
        
        self._metrics.events_processed += 1
        ctx = self._create_context(event.ts)
        
        try:
            if isinstance(event, MarketTick) and self.config.enable_agents:
                self._run_fast_agents(ctx, event.market_id)
            
            elif isinstance(event, Timer):
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
        log.info("Main loop stopping...")
    
    def run_forever(self) -> None:
        """Main event loop."""
        
        log.info("Main loop starting...")
        
        while not self._stop:
            self._metrics.iterations += 1
            now = datetime.now(timezone.utc)
            
            # Scheduler tick
            do_poll, do_reconcile = self.scheduler.tick(now)
            
            # Ingest
            if do_poll and self.config.enable_ingest:
                self._handle_ingest(now)
            
            # Reconcile
            if do_reconcile:
                self.bus.publish(Timer(ts=now, purpose="reconcile"))
            
            # Process events
            for _ in range(self.config.dispatcher.event_batch_size):
                event = self.bus.pop()
                if event is None:
                    break
                self._handle_event(event)
            
            # Sleep
            time.sleep(self.config.dispatcher.sleep_sec)
        
        log.info(f"Main loop stopped. Metrics: {self._metrics}")
```

Это основные улучшения. Дополнительно нужно:

1. Добавить тесты
2. Создать миграции для БД
3. Улучшить UI
4. Добавить мониторинг

Следующие шаги?
