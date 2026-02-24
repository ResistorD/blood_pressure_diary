from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from db.repo import Repo
from utils.logging import get_logger, warn_exc

logger = get_logger("decision.engine")

try:
    # ты создал app/risk_gate.py
    from app.risk_gate import RiskGate
except Exception:  # pragma: no cover
    RiskGate = None  # type: ignore


@dataclass(frozen=True)
class Decision:
    market_id: str
    action: str   # HOLD / PAPER_BUY_BOTH / PAPER_CLOSE_BOTH / PAPER_BUY_YES / PAPER_BUY_NO / PAPER_CLOSE_YES / PAPER_CLOSE_NO
    status: str   # OK / INVESTIGATE / BLOCKED
    reason: str
    reason_json: str | None = None


class DecisionEngineV0:
    """Very small, operator-friendly decision engine.

    Goal right now:
      - turn "cases" into *simple* actions
      - keep everything idempotent-ish (anti-spam)
      - keep global kill-switch (paused) respected
    """

    def __init__(
        self,
        repo: Repo,
        *,
        min_emit_interval_sec: int = 120,
        arb_buy_sum_threshold: float = 0.99,
        arb_close_sum_threshold: float = 1.00,
        max_spread: float = 0.04,
        min_liquidity: float = 50.0,
        min_age_snaps: int = 5,
        volatility_window: int = 12,
        max_volatility: float = 0.08,
        liquidity_trend_window: int = 12,
        min_liquidity_trend: float = 0.0,
        stale_after_sec: int = 180,
        require_two_sided_book: bool = True,
        thin_liquidity_factor: float = 0.5,
        risk_gate=None,  # опционально: можно передать готовый gate извне
    ):
        self.repo = repo
        self.min_emit_interval_sec = int(min_emit_interval_sec)
        self.arb_buy_sum_threshold = float(arb_buy_sum_threshold)
        self.arb_close_sum_threshold = float(arb_close_sum_threshold)
        self.max_spread = float(max_spread)
        self.min_liquidity = float(min_liquidity)
        self.min_age_snaps = int(min_age_snaps)
        self.volatility_window = int(volatility_window)
        self.max_volatility = float(max_volatility)
        self.liquidity_trend_window = int(liquidity_trend_window)
        self.min_liquidity_trend = float(min_liquidity_trend)
        self.stale_after_sec = int(stale_after_sec)
        self.require_two_sided_book = bool(require_two_sided_book)
        self.thin_liquidity_factor = float(thin_liquidity_factor)

        self._risk_gate = risk_gate

    def _get_gate(self):
        """Create gate lazily so engine works even if gate/settings are not wired yet."""
        if self._risk_gate is not None:
            return self._risk_gate
        if RiskGate is None:
            return None

        # RiskGate интерфейс может быть (repo) или (repo, settings).
        # Настроек тут нет — оставляем минимум.
        try:
            return RiskGate(self.repo)
        except TypeError:
            try:
                return RiskGate(repo=self.repo, settings=None)
            except Exception:
                warn_exc(logger, "risk gate init failed (fallback)")
                return None
        except Exception:
            warn_exc(logger, "risk gate init failed")
            return None

    def _has_open_paper_pos(self, market_id: str, outcome: str) -> bool:
        try:
            self.repo.ensure_paper_schema()
            with self.repo.conn() as con:
                row = con.execute(
                    """SELECT 1 FROM paper_positions
                        WHERE market_id=? AND outcome=? AND status='OPEN'
                        LIMIT 1""",
                    (market_id, outcome),
                ).fetchone()
            return bool(row)
        except Exception:
            warn_exc(logger, "has_open_paper_pos failed", market_id=market_id, outcome=outcome)
            return False

    def reconcile(self, run_id: str) -> int:
        cases = self.repo.list_cases(minutes_signals=30, minutes_snaps=10)
        now = datetime.now(timezone.utc)
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

        try:
            paused = bool(self.repo.is_paused())
        except Exception:
            paused = False

        gate = self._get_gate()

        written = 0
        for c in cases:
            market_id = c["market_id"]
            status = c.get("status") or "OK"
            reason = c.get("reason") or ""

            # Hard stop: kill switch
            if paused:
                d = Decision(market_id=market_id, action="HOLD", status="OK", reason="PAUSED")
                written += self._maybe_write(run_id, now, d, paused=paused)
                continue

            # Gate: risk / quality / limits
            if gate is not None:
                try:
                    verdict = gate.check_market(market_id)
                    if verdict is not None and not getattr(verdict, "allow", True):
                        d = Decision(
                            market_id=market_id,
                            action="HOLD",
                            status=getattr(verdict, "status", "BLOCKED") or "BLOCKED",
                            reason=f"{getattr(verdict, 'code', 'GATE')}: {getattr(verdict, 'reason', '')}".strip(),
                        )
                        written += self._maybe_write(run_id, now, d, paused=paused)
                        continue
                except Exception:
                    # gate не должен валить decision engine
                    warn_exc(logger, "risk gate check failed", market_id=market_id)

            # --- tiny arb heuristic on YES+NO sum ---
            sum_mid = c.get("sum_mid")
            spread = c.get("spread")
            liq = c.get("liq")
            history = []
            try:
                history = self.repo.market_history(
                    market_id,
                    limit=max(self.min_age_snaps, self.volatility_window, self.liquidity_trend_window, 20),
                )
            except Exception:
                history = []

            has_yes = self._has_open_paper_pos(market_id, "YES")
            has_no = self._has_open_paper_pos(market_id, "NO")
            has_both = has_yes and has_no

            # default
            d = Decision(market_id=market_id, action="HOLD", status=status, reason=reason)

            # Only act when numbers exist and look tradeable
            if sum_mid is not None and spread is not None and liq is not None:
                try:
                    s = float(sum_mid)
                    sp = float(spread)
                    lq = float(liq)
                except Exception:
                    s = None
                    sp = None
                    lq = None

                if s is not None and sp is not None and lq is not None:
                    spread_ok = sp <= self.max_spread
                    liq_ok = lq >= self.min_liquidity
                    age_ok = len(history) >= self.min_age_snaps if self.min_age_snaps > 0 else True

                    vol_ok = True
                    vol_value = None
                    try:
                        wnd = max(2, self.volatility_window)
                        mids = [float(x.get("mid")) for x in history[:wnd] if x.get("mid") is not None]
                        mids = list(reversed(mids))
                        if len(mids) >= 3:
                            deltas = [mids[i] - mids[i - 1] for i in range(1, len(mids))]
                            mu = sum(deltas) / len(deltas)
                            var = sum((d - mu) ** 2 for d in deltas) / max(1, (len(deltas) - 1))
                            vol_value = var ** 0.5
                            vol_ok = vol_value <= self.max_volatility
                    except Exception:
                        vol_ok = True

                    trend_ok = True
                    trend_value = None
                    try:
                        tw = max(2, self.liquidity_trend_window)
                        liqs = [float(x.get("liquidity")) for x in history[:tw] if x.get("liquidity") is not None]
                        liqs = list(reversed(liqs))
                        if len(liqs) >= 3:
                            trend_value = (liqs[-1] - liqs[0]) / max(1, (len(liqs) - 1))
                            trend_ok = trend_value >= self.min_liquidity_trend
                    except Exception:
                        trend_ok = True

                    latest = history[0] if history else {}
                    latest_bid = latest.get("bid")
                    latest_ask = latest.get("ask")
                    latest_liq = latest.get("liquidity")
                    latest_ts = latest.get("ts")

                    no_book = self.require_two_sided_book and (latest_bid is None or latest_ask is None)
                    thin_min = self.min_liquidity * self.thin_liquidity_factor
                    try:
                        thin = latest_liq is None or float(latest_liq) < thin_min
                    except Exception:
                        thin = True

                    stale = False
                    age_sec = None
                    try:
                        if latest_ts:
                            t = datetime.fromisoformat(str(latest_ts).replace("Z", "+00:00"))
                            if t.tzinfo is None:
                                t = t.replace(tzinfo=timezone.utc)
                            age_sec = max(0, int((now - t).total_seconds()))
                            stale = age_sec > self.stale_after_sec
                    except Exception:
                        stale = True

                    quality_ok = not (no_book or thin or stale)
                    tradeable = spread_ok and liq_ok and age_ok and vol_ok and trend_ok and quality_ok

                    if not tradeable and status == "OK":
                        checks = []
                        checks.append({"key": "spread", "label": "спред", "value": sp, "ok": spread_ok, "want": f"≤ {self.max_spread*100:.1f}%"})
                        checks.append({"key": "liquidity", "label": "ликвидность", "value": lq, "ok": liq_ok, "want": f"≥ {self.min_liquidity:.0f}"})
                        checks.append({"key": "age", "label": "возраст", "value": len(history), "ok": age_ok, "want": f"≥ {self.min_age_snaps}"})
                        checks.append({"key": "volatility", "label": "волатильность", "value": vol_value, "ok": vol_ok, "want": f"≤ {self.max_volatility*100:.1f}%"})
                        checks.append({"key": "liq_trend", "label": "тренд ликвидности", "value": trend_value, "ok": trend_ok, "want": f"≥ {self.min_liquidity_trend:.3f}"})
                        checks.append({"key": "no_book", "label": "книга котировок", "value": "2-sided" if not no_book else "missing bid/ask", "ok": not no_book, "want": "есть bid и ask"})
                        checks.append({"key": "thin", "label": "тонкая ликвидность", "value": latest_liq, "ok": not thin, "want": f"≥ {thin_min:.0f}"})
                        checks.append({"key": "stale", "label": "свежесть", "value": age_sec, "ok": not stale, "want": f"≤ {self.stale_after_sec} сек"})

                        reason_json = json.dumps(
                            {
                                "type": "NOT_TRADEABLE",
                                "flags": [c["key"] for c in checks if not c["ok"]],
                                "checks": checks,
                                "spread": sp,
                                "spread_max": self.max_spread,
                                "liq": lq,
                                "liq_min": self.min_liquidity,
                                "sum_mid": s,
                            },
                            ensure_ascii=False,
                        )

                        # коротко и по делу: что именно не так
                        parts = []
                        if not spread_ok:
                            parts.append(f"спред {sp*100:.1f}% (нужно ≤ {self.max_spread*100:.1f}%)")
                        if not liq_ok:
                            parts.append(f"ликвидность {lq:.0f} (нужно ≥ {self.min_liquidity:.0f})")
                        if not age_ok:
                            parts.append(f"мало истории ({len(history)} < {self.min_age_snaps})")
                        if not vol_ok and vol_value is not None:
                            parts.append(f"волатильность {vol_value*100:.1f}% (нужно ≤ {self.max_volatility*100:.1f}%)")
                        if not trend_ok and trend_value is not None:
                            parts.append(f"тренд ликвидности {trend_value:.3f} (нужно ≥ {self.min_liquidity_trend:.3f})")
                        if no_book:
                            parts.append("нет полноценной книги (bid/ask)")
                        if thin:
                            parts.append(f"тонкая ликвидность (нужно ≥ {thin_min:.0f})")
                        if stale:
                            parts.append(f"устаревший снимок (>{self.stale_after_sec} сек)")
                        reason_text = "Не торгуем: " + ", ".join(parts) if parts else "Не торгуем: условия не выполнены"

                        d = Decision(
                            market_id=market_id,
                            action="HOLD",
                            status="OK",
                            reason=reason_text,
                            reason_json=reason_json,
                        )

                    elif not has_both and tradeable and s < self.arb_buy_sum_threshold and status == "OK":
                        reason_json = json.dumps(
                            {
                                "type": "ARB_BUY",
                                "sum_mid": s,
                                "spread": sp,
                                "spread_max": self.max_spread,
                                "liq": lq,
                                "liq_min": self.min_liquidity,
                            },
                            ensure_ascii=False,
                        )
                        d = Decision(
                            market_id=market_id,
                            action="PAPER_BUY_BOTH",
                            status="OK",
                            reason=f"Открыть paper: сумма цен {s:.3f} < {self.arb_buy_sum_threshold:.3f}",
                            reason_json=reason_json,
                        )

                    elif has_both and tradeable and s >= self.arb_close_sum_threshold and status == "OK":
                        reason_json = json.dumps(
                            {
                                "type": "ARB_CLOSE",
                                "sum_mid": s,
                                "spread": sp,
                                "spread_max": self.max_spread,
                                "liq": lq,
                                "liq_min": self.min_liquidity,
                            },
                            ensure_ascii=False,
                        )
                        d = Decision(
                            market_id=market_id,
                            action="PAPER_CLOSE_BOTH",
                            status="OK",
                            reason=f"Закрыть paper: сумма цен {s:.3f} ≥ {self.arb_close_sum_threshold:.3f}",
                            reason_json=reason_json,
                        )

                    elif status == "OK" and tradeable and s < (self.arb_buy_sum_threshold + 0.01):
                        # near-threshold -> ask for eyes
                        reason_json = json.dumps(
                            {
                                "type": "NEAR_ARB",
                                "sum_mid": s,
                                "threshold": self.arb_buy_sum_threshold,
                                "spread": sp,
                                "spread_max": self.max_spread,
                                "liq": lq,
                                "liq_min": self.min_liquidity,
                            },
                            ensure_ascii=False,
                        )
                        d = Decision(
                            market_id=market_id,
                            action="HOLD",
                            status="INVESTIGATE",
                            reason=f"Почти арбитраж: сумма цен {s:.3f} рядом с {self.arb_buy_sum_threshold:.3f}",
                            reason_json=reason_json,
                        )

            written += self._maybe_write(run_id, now, d, paused=paused)

        return written

    def _maybe_write(self, run_id: str, now: datetime, d: Decision, *, paused: bool) -> int:
        last = self.repo.get_last_decision_v0(d.market_id)
        if last is not None:
            last_ts, last_action, last_status, last_reason, _last_reason_json = last
            same = (last_action == d.action and last_status == d.status and (last_reason or "") == d.reason)

            # ✅ Anti-HOLD spam: если мы уже HOLD'или этот же кейс — не пишем повтор
            if same and d.action == "HOLD":
                return 0

            # ✅ Для остальных действий: не пишем слишком часто один и тот же результат.
            if same:
                try:
                    t = datetime.fromisoformat(last_ts)
                    if (now - t) < timedelta(seconds=self.min_emit_interval_sec):
                        return 0
                except Exception:
                    return 0

        payload = json.dumps(
            {
                "source": "DecisionEngineV0",
                "paused": paused,
                "params": {
                    "arb_buy_sum_threshold": self.arb_buy_sum_threshold,
                                "arb_close_sum_threshold": self.arb_close_sum_threshold,
                                "max_spread": self.max_spread,
                                "min_liquidity": self.min_liquidity,
                                "min_age_snaps": self.min_age_snaps,
                                "max_volatility": self.max_volatility,
                                "min_liquidity_trend": self.min_liquidity_trend,
                                "stale_after_sec": self.stale_after_sec,
                            },
                        }
                    )
        self.repo.insert_decision_v0(
            decision_id=str(uuid.uuid4()),
            ts=now.isoformat(timespec="seconds"),
            run_id=run_id,
            market_id=d.market_id,
            action=d.action,
            status=d.status,
            reason=d.reason,
            reason_json=getattr(d, 'reason_json', None),
            payload_json=payload,
        )
        return 1
