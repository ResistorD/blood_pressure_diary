"""
EXPERIMENTAL execution loop.

This loop is not used in canonical runtime.
Kept for research purposes only.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from db.repo import Repo
from utils.logging import get_logger, warn_exc

logger = get_logger("decision.engine_v2")
from app.config import DecisionConfig
from utils.time import now_utc, to_iso
from utils.validation import validate_market_id


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
    metadata: Optional[Dict[str, Any]] = None
    
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
    def decide(
        self,
        case: MarketCase,
        positions: Dict[str, bool],
        config: DecisionConfig,
        ctx: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Make a decision for a case."""
        pass


class ArbStrategy(DecisionStrategy):
    """Arbitrage strategy based on YES+NO sum."""
    
    def decide(
        self,
        case: MarketCase,
        positions: Dict[str, bool],
        config: DecisionConfig,
        ctx: Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Decide based on arb opportunity."""
        
        # Default: HOLD
        action = ActionType.HOLD
        status = DecisionStatus(case.status) if case.status in DecisionStatus.__members__ else DecisionStatus.OK
        reason = case.reason or "No clear signal"
        metadata: Dict[str, Any] = {}
        
        # Check if we have required data
        if case.sum_mid is None or case.spread is None or case.liquidity is None:
            return Decision(
                market_id=case.market_id,
                action=action,
                status=status,
                reason="Missing market data",
                metadata=metadata,
            )
        
        ctx = ctx or {}
        history = ctx.get("history") or []
        now = ctx.get("now")
        if not isinstance(now, datetime):
            now = now_utc()

        # --- tradeability (v2): spread + liquidity + min age + volatility + liquidity trend ---
        spread_ok = (case.spread <= config.max_spread)
        liq_ok = (case.liquidity >= config.min_liquidity)

        age_snaps = len(history)
        age_ok = (age_snaps >= int(getattr(config, "min_age_snaps", 0) or 0)) if getattr(config, "min_age_snaps", 0) else True

        # volatility: stdev of mid deltas over last N points (use only numeric mid)
        vol_ok = True
        vol_value = None
        try:
            wnd = int(getattr(config, "volatility_window", 0) or 0)
            if wnd and len(history) >= 3:
                mids = [float(x.get("mid")) for x in history[:wnd] if x.get("mid") is not None]
                # history is DESC; reverse to chronological
                mids = list(reversed(mids))
                if len(mids) >= 3:
                    deltas = [mids[i] - mids[i-1] for i in range(1, len(mids))]
                    mu = sum(deltas) / len(deltas)
                    var = sum((d - mu) ** 2 for d in deltas) / max(1, (len(deltas) - 1))
                    vol_value = var ** 0.5
                    vol_ok = (vol_value <= float(getattr(config, "max_volatility", 0.0) or 0.0))
        except Exception:
            vol_ok = True

        # liquidity trend: (last-first)/(n-1) over last N points
        trend_ok = True
        trend_value = None
        try:
            tw = int(getattr(config, "liquidity_trend_window", 0) or 0)
            min_tr = float(getattr(config, "min_liquidity_trend", 0.0) or 0.0)
            if tw and len(history) >= 3:
                liqs = [float(x.get("liquidity")) for x in history[:tw] if x.get("liquidity") is not None]
                liqs = list(reversed(liqs))
                if len(liqs) >= 3:
                    trend_value = (liqs[-1] - liqs[0]) / max(1, (len(liqs) - 1))
                    trend_ok = (trend_value >= min_tr)
        except Exception:
            trend_ok = True

        # quality flags from latest snapshot in history (expected DESC by ts)
        latest = history[0] if history else {}
        latest_bid = latest.get("bid")
        latest_ask = latest.get("ask")
        latest_liq = latest.get("liquidity")
        latest_ts = latest.get("ts")

        no_book_flag = bool(
            getattr(config, "require_two_sided_book", True)
            and (latest_bid is None or latest_ask is None)
        )

        thin_threshold = float(config.min_liquidity) * float(getattr(config, "thin_liquidity_factor", 0.5) or 0.0)
        thin_flag = False
        try:
            thin_flag = (latest_liq is None) or (float(latest_liq) < thin_threshold)
        except Exception:
            thin_flag = True

        stale_flag = False
        age_seconds = None
        try:
            if latest_ts:
                ts_dt = datetime.fromisoformat(str(latest_ts).replace("Z", "+00:00"))
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                age_seconds = max(0, int((now - ts_dt).total_seconds()))
                stale_flag = age_seconds > int(getattr(config, "stale_after_sec", 180))
        except Exception:
            stale_flag = True

        quality_ok = not (no_book_flag or thin_flag or stale_flag)

        tradeable = bool(spread_ok and liq_ok and age_ok and vol_ok and trend_ok and quality_ok)
        
        metadata = {
            "sum_mid": case.sum_mid,
            "spread": case.spread,
            "liquidity": case.liquidity,
            "tradeable": tradeable,
            "has_positions": {"YES": positions.get("YES", False), "NO": positions.get("NO", False)},
            "tradeability": {
                "spread_ok": spread_ok,
                "liq_ok": liq_ok,
                "age_ok": age_ok,
                "vol_ok": vol_ok,
                "trend_ok": trend_ok,
                "quality_ok": quality_ok,
                "age_snaps": age_snaps,
                "volatility": vol_value,
                "liq_trend": trend_value,
                "quality_flags": {
                    "no_book": no_book_flag,
                    "thin": thin_flag,
                    "stale": stale_flag,
                },
                "snapshot_age_sec": age_seconds,
            },
        }
        
        if not tradeable:
            # Human-ish structured reason for UI.
            def _pct(x: float) -> str:
                try:
                    return f"{x*100:.1f}%"
                except Exception:
                    return str(x)

            checks = []
            checks.append({
                "key": "spread",
                "label": "спред",
                "value": float(case.spread),
                "ok": spread_ok,
                "want": f"≤ {_pct(config.max_spread)}",
                "note": "узкий" if spread_ok else "слишком широкий",
            })
            checks.append({
                "key": "liquidity",
                "label": "ликвидность",
                "value": float(case.liquidity),
                "ok": liq_ok,
                "want": f"≥ {config.min_liquidity:.0f}",
                "note": "достаточная" if liq_ok else "низкая",
            })
            if getattr(config, "min_age_snaps", 0):
                checks.append({
                    "key": "age",
                    "label": "возраст",
                    "value": int(age_snaps),
                    "ok": age_ok,
                    "want": f"≥ {int(getattr(config, 'min_age_snaps', 0))} снимков",
                    "note": "достаточно истории" if age_ok else "мало истории",
                })
            if getattr(config, "volatility_window", 0) and vol_value is not None:
                checks.append({
                    "key": "volatility",
                    "label": "волатильность",
                    "value": float(vol_value),
                    "ok": vol_ok,
                    "want": f"≤ {_pct(float(getattr(config, 'max_volatility', 0.0) or 0.0))}",
                    "note": "нормальная" if vol_ok else "слишком шумно",
                })
            if getattr(config, "liquidity_trend_window", 0) and trend_value is not None:
                checks.append({
                    "key": "liq_trend",
                    "label": "тренд ликвидности",
                    "value": float(trend_value),
                    "ok": trend_ok,
                    "want": f"≥ {float(getattr(config, 'min_liquidity_trend', 0.0) or 0.0):.3f}",
                    "note": "не падает" if trend_ok else "ухудшается",
                })
            checks.append({
                "key": "no_book",
                "label": "книга котировок",
                "value": "2-sided" if not no_book_flag else "missing bid/ask",
                "ok": not no_book_flag,
                "want": "есть bid и ask",
                "note": "полная книга" if not no_book_flag else "нет полной книги",
            })
            checks.append({
                "key": "thin",
                "label": "тонкая ликвидность",
                "value": float(latest_liq) if latest_liq is not None else None,
                "ok": not thin_flag,
                "want": f"≥ {thin_threshold:.0f}",
                "note": "достаточная глубина" if not thin_flag else "слишком тонко",
            })
            checks.append({
                "key": "stale",
                "label": "свежесть",
                "value": age_seconds,
                "ok": not stale_flag,
                "want": f"≤ {int(getattr(config, 'stale_after_sec', 180))} сек",
                "note": "снимок свежий" if not stale_flag else "данные устарели",
            })

            metadata["reason_json"] = {
                "title": "Пока не годится для paper-торговли",
                "checks": checks,
                "hint": "Исправляем не рынок — мы просто ждём/фильтруем. Когда метрики войдут в пороги, кейс станет tradeable.",
            }
            return Decision(
                market_id=case.market_id,
                action=action,
                status=DecisionStatus.BLOCKED,
                reason=f"Not tradeable (spread/liquidity/age/volatility/trend/quality)",
                metadata=metadata,
            )
        
        # Check for arb opportunities
        has_both = positions.get("YES", False) and positions.get("NO", False)
        
        # Buy signal: sum < threshold and no existing position
        if not has_both and case.sum_mid < config.arb_buy_threshold and status == DecisionStatus.OK:
            action = ActionType.PAPER_BUY_BOTH
            status = DecisionStatus.OK
            reason = f"ARB buy: sum={case.sum_mid:.3f} < {config.arb_buy_threshold:.3f}"
            metadata["edge"] = config.arb_buy_threshold - case.sum_mid
        
        # Close signal: sum >= threshold and have position
        elif has_both and case.sum_mid >= config.arb_close_threshold and status == DecisionStatus.OK:
            action = ActionType.PAPER_CLOSE_BOTH
            status = DecisionStatus.OK
            reason = f"ARB close: sum={case.sum_mid:.3f} >= {config.arb_close_threshold:.3f}"
            metadata["profit"] = case.sum_mid - config.arb_buy_threshold
        
        # Near-threshold: flag for investigation
        elif status == DecisionStatus.OK and tradeable:
            delta_from_buy = abs(case.sum_mid - config.arb_buy_threshold)
            if delta_from_buy < 0.01:
                action = ActionType.HOLD
                status = DecisionStatus.INVESTIGATE
                reason = f"Near arb threshold: sum={case.sum_mid:.3f}, delta={delta_from_buy:.4f}"
                metadata["delta_from_threshold"] = delta_from_buy
        
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
        config: Optional[DecisionConfig] = None,
        strategies: Optional[List[DecisionStrategy]] = None,
        risk_gate = None,
    ):
        self.repo = repo
        self.config = config or DecisionConfig()
        self.strategies = strategies or [ArbStrategy()]
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
                    metadata={"gate_verdict": str(verdict)},
                )
        
        except Exception:
            # Don't let gate failures kill decision engine
            warn_exc(logger, "risk gate check failed", market_id=market_id)
        
        return None
    
    def reconcile(self, run_id: str) -> int:
        """Main reconciliation loop.
        
        Args:
            run_id: Current run identifier
            
        Returns:
            Number of decisions written
        """
        
        # Check pause status
        paused = False
        try:
            paused = bool(self.repo.is_paused())
        except Exception:
            warn_exc(logger, "paused check failed")
            paused = False
        
        # Get cases
        cases = self.repo.list_cases(minutes_signals=30, minutes_snaps=10)
        now = now_utc()
        written = 0

        if cases and hasattr(self.repo, "get_deprioritize_mode"):
            try:
                if self.repo.get_deprioritize_mode() == "pipeline":
                    def _activity_score(c):
                        ts = c.get("last_signal_ts") or c.get("last_snapshot_ts")
                        if not ts:
                            return 0.0
                        try:
                            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                            if t.tzinfo is None:
                                t = t.replace(tzinfo=timezone.utc)
                            return t.timestamp()
                        except Exception:
                            return 0.0

                    scored = []
                    for idx, c in enumerate(cases):
                        score = _activity_score(c)
                        weighted, _meta = self.repo.apply_deprioritize(score, c.get("market_id"), None)
                        scored.append((float(weighted), idx, c))
                    scored.sort(key=lambda x: (-x[0], x[1]))
                    cases = [c for _w, _i, c in scored]
            except Exception:
                warn_exc(logger, "deprioritize sort failed")
        
        for case_dict in cases:
            try:
                case = MarketCase.from_dict(case_dict)
                validate_market_id(case.market_id)
            except Exception:
                continue
            
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
            # Pull a small history slice for tradeability checks.
            hist = []
            try:
                hist = self.repo.market_history(
                    case.market_id,
                    limit=max(
                        self.config.volatility_window,
                        self.config.liquidity_trend_window,
                        self.config.min_age_snaps,
                        20,
                    ),
                )
            except Exception:
                hist = []
            decision = self.strategies[0].decide(case, positions, self.config, ctx={"history": hist, "now": now})
            
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

        reason_json = None
        try:
            rj = (decision.metadata or {}).get("reason_json")
            if rj is not None:
                reason_json = json.dumps(rj, ensure_ascii=False)
        except Exception:
            reason_json = None
        
        self.repo.insert_decision_v0(
            decision_id=str(uuid.uuid4()),
            ts=to_iso(now),
            run_id=run_id,
            market_id=decision.market_id,
            action=decision.action.value,
            status=decision.status.value,
            reason=decision.reason,
            reason_json=reason_json,
            payload_json=json.dumps(payload),
        )
        
        return 1


# Backward compatibility - keep old engine available
from decision.engine import DecisionEngineV0
