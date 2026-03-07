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
    risk_kind: str = "NONE"


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
        self._case_obs_emit_every = 10
        self._case_prev_position_state_by_market: dict[str, str] = {}
        self._case_last_non_hold_action_by_market: dict[str, str] = {}
        self._case_obs_counts = {
            "total": 0,
            "written": 0,
            "dedup": 0,
            "risk_block": 0,
            "dedup_kind_NONE": 0,
            "dedup_kind_MIN_INTERVAL": 0,
            "dedup_kind_HOLD_SPAM": 0,
            "dedup_kind_DUP_PARSE_ERROR": 0,
        }
        self._decision_quality_counts = {
            "total": 0,
            "same_decision": 0,
            "position_changed": 0,
            "flips": 0,
            "noop": 0,
            "writes": 0,
            "dedup": 0,
        }

    @staticmethod
    def _reason_code(reason: str) -> str:
        txt = str(reason or "").strip()
        if not txt:
            return "-"
        head = txt.split(":", 1)[0].strip()
        if len(head) > 48:
            head = head[:48]
        return head.replace(" ", "_").upper() or "-"

    @staticmethod
    def _case_status_from_action(action: str) -> str:
        a = str(action or "").strip().upper()
        if a.startswith("PAPER_BUY"):
            return "OPEN"
        if a.startswith("PAPER_CLOSE"):
            return "CLOSED"
        if a == "HOLD":
            return "HOLD"
        return "NONE"

    def _emit_case_lifecycle_summary(
        self,
        *,
        run_id: str,
        now: datetime,
        d: Decision,
        wrote: int,
        dedup: int,
        dedup_kind: str,
        paused: bool,
        has_yes: bool | None = None,
        has_no: bool | None = None,
        last_decision: tuple | None = None,
    ) -> None:
        case_id = str(d.market_id or "-")
        open_sides = -1
        position_state = "NA"
        if has_yes is not None and has_no is not None:
            open_sides = int(bool(has_yes)) + int(bool(has_no))
            if open_sides <= 0:
                position_state = "FLAT"
            elif open_sides == 1:
                position_state = "OPEN_SINGLE"
            else:
                position_state = "OPEN_BOTH"
        decision_action = str(d.action or "").strip().upper() or "NONE"
        log_reason = self._reason_code(str(d.reason or ""))
        risk_block = int(str(d.status or "").strip().upper() == "BLOCKED")
        raw_risk_kind = str(getattr(d, "risk_kind", "") or "").strip().upper()
        risk_kind = raw_risk_kind if risk_block and raw_risk_kind else "NONE"
        kill_kind = self._resolve_kill_kind(risk_kind)
        last_action = str((last_decision[1] if last_decision else "") or "").strip().upper()
        last_status = str((last_decision[2] if last_decision else "") or "").strip().upper()
        last_reason = str((last_decision[3] if last_decision else "") or "")
        same_as_previous_decision = int(
            bool(
                last_decision is not None
                and last_action == decision_action
                and last_status == (str(d.status or "").strip().upper() or "-")
                and last_reason == str(d.reason or "")
            )
        )
        prev_position_state = str(self._case_prev_position_state_by_market.get(case_id, "") or "")
        position_changed = int(bool(prev_position_state) and prev_position_state != position_state)
        prev_non_hold_action = str(self._case_last_non_hold_action_by_market.get(case_id, "") or "")
        if not prev_non_hold_action and last_action and last_action != "HOLD":
            prev_non_hold_action = last_action
        action_flip = int(
            bool(
                self._action_polarity(prev_non_hold_action)
                and self._action_polarity(decision_action)
                and self._action_polarity(prev_non_hold_action) != self._action_polarity(decision_action)
            )
        )
        exposure_changed = self._action_changes_exposure(decision_action, position_state)
        noop_decision = int(not exposure_changed and position_changed == 0)
        self._case_prev_position_state_by_market[case_id] = position_state
        if decision_action and decision_action != "HOLD":
            self._case_last_non_hold_action_by_market[case_id] = decision_action
        logger.info(
            "CASE_LIFECYCLE_SUMMARY ts=%s run_id=%s case_id=%s source_market=%s current_status=%s "
            "decision_action=%s decision_reason=%s decision_status=%s dedup=%s risk_block=%s "
            "risk_kind=%s kill_kind=%s dedup_kind=%s same_as_previous_decision=%s position_changed=%s action_flip=%s noop_decision=%s "
            "open_sides=%s position_state=%s paused=%s written=%s",
            now.isoformat(timespec="seconds"),
            str(run_id or "-"),
            case_id,
            case_id,
            self._case_status_from_action(decision_action),
            decision_action,
            log_reason,
            str(d.status or "").strip().upper() or "-",
            int(dedup),
            int(risk_block),
            risk_kind,
            kill_kind,
            str(dedup_kind or "NONE"),
            int(same_as_previous_decision),
            int(position_changed),
            int(action_flip),
            int(noop_decision),
            int(open_sides),
            position_state,
            int(bool(paused)),
            int(wrote),
        )
        self._case_obs_update_and_maybe_emit(
            wrote=int(wrote),
            dedup=int(dedup),
            dedup_kind=str(dedup_kind or "NONE").strip().upper() or "NONE",
            risk_block=int(risk_block),
        )
        self._decision_quality_update_and_maybe_emit(
            same_decision=int(same_as_previous_decision),
            position_changed=int(position_changed),
            flips=int(action_flip),
            noop=int(noop_decision),
            writes=int(bool(wrote)),
            dedup=int(bool(dedup)),
        )

    @staticmethod
    def _action_polarity(action: str) -> str | None:
        a = str(action or "").strip().upper()
        if a in {"PAPER_BUY_BOTH", "PAPER_BUY_YES", "PAPER_BUY_NO", "BUY", "BUY_BOTH"}:
            return "BUY"
        if a in {"PAPER_CLOSE_BOTH", "PAPER_CLOSE_YES", "PAPER_CLOSE_NO", "SELL", "SELL_BOTH"}:
            return "SELL"
        return None

    @staticmethod
    def _action_changes_exposure(action: str, position_state: str) -> bool:
        a = str(action or "").strip().upper()
        ps = str(position_state or "").strip().upper()
        if a == "HOLD":
            return False
        if a == "PAPER_BUY_BOTH":
            return ps != "OPEN_BOTH"
        if a == "PAPER_CLOSE_BOTH":
            return ps != "FLAT"
        if a in {"PAPER_BUY_YES", "PAPER_BUY_NO"}:
            return ps in {"FLAT", "OPEN_SINGLE"}
        if a in {"PAPER_CLOSE_YES", "PAPER_CLOSE_NO"}:
            return ps in {"OPEN_SINGLE", "OPEN_BOTH"}
        return False

    def _resolve_kill_kind(self, risk_kind: str) -> str:
        if str(risk_kind or "").strip().upper() != "KILL_SWITCH":
            return "NONE"

        reason = ""
        try:
            getter = getattr(self.repo, "get_setting", None)
            if callable(getter):
                reason = str(getter("kill_switch_reason", "") or "").strip()
        except Exception:
            reason = ""

        up = str(reason or "").upper()
        if not up.startswith("AUTO:"):
            return "MANUAL"

        tail = str(reason or "").split(":", 1)[1].strip() if ":" in str(reason or "") else ""
        if tail == "слишком много открытых paper-позиций":
            return "AUTO_LIMIT_MAX_OPEN_POSITIONS"
        if tail == "исчерпан общий лимит капитала (paper)":
            return "AUTO_LIMIT_MAX_NOTIONAL_TOTAL"
        if tail.startswith("capital usage "):
            return "AUTO_LIMIT_MAX_CAPITAL_USAGE_PCT"
        if tail == "исчерпан лимит экспозиции по кластеру":
            return "AUTO_LIMIT_MAX_NOTIONAL_PER_GROUP"
        if tail == "уже есть открытая paper-позиция по рынку":
            return "AUTO_LIMIT_MARKET_ALREADY_OPEN"
        return "AUTO_OTHER"

    def _case_obs_update_and_maybe_emit(
        self,
        *,
        wrote: int,
        dedup: int,
        dedup_kind: str,
        risk_block: int,
    ) -> None:
        c = self._case_obs_counts
        c["total"] = int(c.get("total", 0) or 0) + 1
        c["written"] = int(c.get("written", 0) or 0) + int(bool(wrote))
        c["dedup"] = int(c.get("dedup", 0) or 0) + int(bool(dedup))
        c["risk_block"] = int(c.get("risk_block", 0) or 0) + int(bool(risk_block))
        kind = str(dedup_kind or "NONE").strip().upper() or "NONE"
        key = f"dedup_kind_{kind}"
        if key in c:
            c[key] = int(c.get(key, 0) or 0) + 1
        emit_every = max(1, int(getattr(self, "_case_obs_emit_every", 10) or 10))
        if int(c.get("total", 0) or 0) % emit_every != 0:
            return
        logger.info(
            "CASE_OBS_SUMMARY total=%s written=%s dedup=%s none=%s min_interval=%s hold_spam=%s "
            "dup_parse_error=%s risk_block=%s",
            int(c.get("total", 0) or 0),
            int(c.get("written", 0) or 0),
            int(c.get("dedup", 0) or 0),
            int(c.get("dedup_kind_NONE", 0) or 0),
            int(c.get("dedup_kind_MIN_INTERVAL", 0) or 0),
            int(c.get("dedup_kind_HOLD_SPAM", 0) or 0),
            int(c.get("dedup_kind_DUP_PARSE_ERROR", 0) or 0),
            int(c.get("risk_block", 0) or 0),
        )

    def _decision_quality_update_and_maybe_emit(
        self,
        *,
        same_decision: int,
        position_changed: int,
        flips: int,
        noop: int,
        writes: int,
        dedup: int,
    ) -> None:
        c = self._decision_quality_counts
        c["total"] = int(c.get("total", 0) or 0) + 1
        c["same_decision"] = int(c.get("same_decision", 0) or 0) + int(bool(same_decision))
        c["position_changed"] = int(c.get("position_changed", 0) or 0) + int(bool(position_changed))
        c["flips"] = int(c.get("flips", 0) or 0) + int(bool(flips))
        c["noop"] = int(c.get("noop", 0) or 0) + int(bool(noop))
        c["writes"] = int(c.get("writes", 0) or 0) + int(bool(writes))
        c["dedup"] = int(c.get("dedup", 0) or 0) + int(bool(dedup))
        emit_every = max(1, int(getattr(self, "_case_obs_emit_every", 10) or 10))
        if int(c.get("total", 0) or 0) % emit_every != 0:
            return
        logger.info(
            "DECISION_QUALITY_SUMMARY total=%s same_decision=%s position_changed=%s flips=%s noop=%s writes=%s dedup=%s",
            int(c.get("total", 0) or 0),
            int(c.get("same_decision", 0) or 0),
            int(c.get("position_changed", 0) or 0),
            int(c.get("flips", 0) or 0),
            int(c.get("noop", 0) or 0),
            int(c.get("writes", 0) or 0),
            int(c.get("dedup", 0) or 0),
        )

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
                            risk_kind=str(getattr(verdict, "kind", "NONE") or "NONE"),
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

            written += self._maybe_write(run_id, now, d, paused=paused, has_yes=has_yes, has_no=has_no)

        return written

    def _maybe_write(
        self,
        run_id: str,
        now: datetime,
        d: Decision,
        *,
        paused: bool,
        has_yes: bool | None = None,
        has_no: bool | None = None,
    ) -> int:
        last = self.repo.get_last_decision_v0(d.market_id)
        if last is not None:
            last_ts, last_action, last_status, last_reason, _last_reason_json = last
            same = (last_action == d.action and last_status == d.status and (last_reason or "") == d.reason)

            # ✅ Anti-HOLD spam: если мы уже HOLD'или этот же кейс — не пишем повтор
            if same and d.action == "HOLD":
                self._emit_case_lifecycle_summary(
                    run_id=run_id,
                    now=now,
                    d=d,
                    wrote=0,
                    dedup=1,
                    dedup_kind="HOLD_SPAM",
                    paused=paused,
                    has_yes=has_yes,
                    has_no=has_no,
                    last_decision=last,
                )
                return 0

            # ✅ Для остальных действий: не пишем слишком часто один и тот же результат.
            if same:
                try:
                    t = datetime.fromisoformat(last_ts)
                    if (now - t) < timedelta(seconds=self.min_emit_interval_sec):
                        self._emit_case_lifecycle_summary(
                            run_id=run_id,
                            now=now,
                            d=d,
                            wrote=0,
                            dedup=1,
                            dedup_kind="MIN_INTERVAL",
                            paused=paused,
                            has_yes=has_yes,
                            has_no=has_no,
                            last_decision=last,
                        )
                        return 0
                except Exception:
                    self._emit_case_lifecycle_summary(
                        run_id=run_id,
                        now=now,
                        d=d,
                        wrote=0,
                        dedup=1,
                        dedup_kind="DUP_PARSE_ERROR",
                        paused=paused,
                        has_yes=has_yes,
                        has_no=has_no,
                        last_decision=last,
                    )
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
        self._emit_case_lifecycle_summary(
            run_id=run_id,
            now=now,
            d=d,
            wrote=1,
            dedup=0,
            dedup_kind="NONE",
            paused=paused,
            has_yes=has_yes,
            has_no=has_no,
            last_decision=last,
        )
        return 1
