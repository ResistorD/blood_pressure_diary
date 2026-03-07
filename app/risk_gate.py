from dataclasses import dataclass
from typing import Optional

from utils.logging import get_logger, warn_exc

logger = get_logger("app.risk_gate")

@dataclass(frozen=True)
class GateVerdict:
    allow: bool
    status: str               # "OK" | "BLOCKED"
    code: str                 # "RISK" | "DATA" | "LIMIT" | ...
    reason: str               # коротко для UI / логов
    kind: str = "NONE"        # конкретный триггер правила для observability
    ttl_seconds: int = 300    # сколько считаем вердикт актуальным

class RiskGate:
    def __init__(self, repo, settings):
        self.repo = repo
        self.settings = settings

    def _rget(self, name: str, default):
        try:
            risk = getattr(self.settings, "risk", None)
            if risk is None:
                return default
            return getattr(risk, name, default)
        except Exception:
            warn_exc(logger, "risk_gate: failed to read risk setting", setting=name)
            return default

    def _sget(self, name: str, default):
        try:
            return getattr(self.settings, name, default)
        except Exception:
            warn_exc(logger, "risk_gate: failed to read setting", setting=name)
            return default

    def _maybe_enable_auto_kill(self, market_id: str) -> None:
        """Enable kill-switch automatically when hard limits are breached."""
        auto = bool(self._rget("auto_kill_on_limit_breach", True))
        if not auto:
            return

        if self.repo.get_bool_setting("kill_switch", default=bool(self._rget("kill_switch_default", False))):
            return

        lim = self._check_limits(market_id)
        if lim is None:
            return
        if lim.code != "LIMIT":
            return

        try:
            self.repo.set_setting("kill_switch", "1")
            self.repo.set_setting("kill_switch_reason", f"AUTO: {lim.reason}")
        except Exception:
            warn_exc(logger, "risk_gate: failed to set kill_switch")

    def check_market(self, market_id: str) -> GateVerdict:
        # auto kill-switch evaluation (best-effort)
        try:
            self._maybe_enable_auto_kill(market_id)
        except Exception:
            warn_exc(logger, "risk_gate: auto kill-switch evaluation failed", market_id=market_id)

        # 0) Kill-switch (операторский стоп-кран)
        try:
            ks = self.repo.get_bool_setting("kill_switch", default=bool(self._rget("kill_switch_default", False)))
            if ks:
                return GateVerdict(
                    False,
                    "BLOCKED",
                    "KILL",
                    "kill-switch включён: новые paper-открытия запрещены",
                    kind="KILL_SWITCH",
                )
        except Exception:
            # если настройки недоступны — не валим UI
            warn_exc(logger, "risk_gate: kill_switch check failed", market_id=market_id)

        # 1) Risk constraints (из signals)
        risk_window = int(self._sget("risk_window_minutes", 60) or 60)
        rc = self.repo.latest_risk_constraint(market_id, minutes=risk_window)
        if rc:
            return GateVerdict(
                False,
                "BLOCKED",
                "RISK",
                rc["explain_short"] or "risk constraint",
                kind="RISK_CONSTRAINT_SIGNAL",
            )

        # 2) Data quality (из auditor signals)
        quality_window = int(self._sget("quality_window_minutes", 180) or 180)
        dq = self.repo.latest_quality_alert(market_id, minutes=quality_window)
        if dq:
            return GateVerdict(
                False,
                "BLOCKED",
                "DATA",
                dq["explain_short"] or "data quality",
                kind="QUALITY_ALERT_SIGNAL",
            )

        # 3) Execution limits (paper exposure)
        lim = self._check_limits(market_id)
        if lim:
            return lim

        return GateVerdict(True, "OK", "OK", "")

    def _check_limits(self, market_id: str) -> Optional[GateVerdict]:
        # 3a) лимит открытых paper-позиций
        st = self.repo.paper_stats() or {"open_positions": 0, "notional_open": 0.0, "notional_by_group": {}}
        max_pos = int(self._rget("max_open_positions", 0) or 0)
        if max_pos and st.get("open_positions", 0) >= max_pos:
            return GateVerdict(
                False,
                "BLOCKED",
                "LIMIT",
                "слишком много открытых paper-позиций",
                kind="LIMIT_MAX_OPEN_POSITIONS",
            )

        # 3b) capital usage / notional total
        max_total = float(self._rget("max_notional_total", 0.0) or 0.0)
        notional_open = float(st.get("notional_open", 0.0) or 0.0)
        if max_total and notional_open >= max_total:
            return GateVerdict(
                False,
                "BLOCKED",
                "LIMIT",
                "исчерпан общий лимит капитала (paper)",
                kind="LIMIT_MAX_NOTIONAL_TOTAL",
            )
        usage_pct = (notional_open / max_total) if max_total > 0 else 0.0
        max_usage = float(self._rget("max_capital_usage_pct", 0.0) or 0.0)
        if max_total > 0 and max_usage > 0 and usage_pct >= max_usage:
            return GateVerdict(
                False,
                "BLOCKED",
                "LIMIT",
                f"capital usage {usage_pct*100:.1f}% ≥ {max_usage*100:.1f}%",
                kind="LIMIT_MAX_CAPITAL_USAGE_PCT",
            )

        # 3c) exposure per cluster (group_key)
        try:
            m = self.repo.get_market(market_id)
            gk = getattr(m, "group_key", "") if m else ""
            per_group = st.get("notional_by_group", {}) or {}
            if gk:
                max_group = float(self._rget("max_notional_per_group", 0.0) or 0.0)
                if max_group and float(per_group.get(gk, 0.0) or 0.0) >= max_group:
                    return GateVerdict(
                        False,
                        "BLOCKED",
                        "LIMIT",
                        "исчерпан лимит экспозиции по кластеру",
                        kind="LIMIT_MAX_NOTIONAL_PER_GROUP",
                    )
        except Exception:
            warn_exc(logger, "risk_gate: per-group limit check failed", market_id=market_id)

        # пример: лимит на рынок (не дублировать)
        if self.repo.paper_has_open_position(market_id):
            return GateVerdict(
                False,
                "BLOCKED",
                "LIMIT",
                "уже есть открытая paper-позиция по рынку",
                kind="LIMIT_MARKET_ALREADY_OPEN",
            )

        return None
