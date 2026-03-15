from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
import os

from utils.logging import get_logger, warn_exc

logger = get_logger("execution.paper_executor")

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _paper_fixed_notional() -> float:
    raw = os.getenv("PS_PAPER_FIXED_NOTIONAL", os.getenv("PAPER_FIXED_NOTIONAL", "10.0"))
    try:
        val = float(raw)
    except Exception:
        val = 10.0
    if val <= 0:
        return 10.0
    return val


def _latest_quote(repo: Any, market_id: str, outcome: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {"bid": None, "ask": None, "mid": None}
    try:
        fn = getattr(repo, "get_latest_snapshots", None)
        if callable(fn):
            snap = fn(market_id) or {}
            q = (snap.get(outcome) or {}) if isinstance(snap, dict) else {}
            if isinstance(q, dict):
                out["bid"] = q.get("bid")
                out["ask"] = q.get("ask")
                out["mid"] = q.get("mid")
    except Exception:
        warn_exc(logger, "latest quote lookup failed", market_id=market_id, outcome=outcome)
    return out


def _resolve_fill_price(repo: Any, market_id: str, outcome: str, cmd: str) -> tuple[float, str]:
    """BUY -> ASK, CLOSE -> BID, fallback MID, then legacy fallback 0.50."""
    quote = _latest_quote(repo, market_id, outcome)
    side = "ask" if str(cmd or "").upper() == "BUY" else "bid"
    raw_side = quote.get(side)
    try:
        if raw_side is not None and float(raw_side) > 0.0:
            return float(raw_side), side.upper()
    except Exception:
        pass
    raw_mid = quote.get("mid")
    try:
        if raw_mid is not None and float(raw_mid) > 0.0:
            return float(raw_mid), "MID_FALLBACK"
    except Exception:
        pass
    return 0.50, "DEFAULT_FALLBACK"


def _qty_for_buy(fill_price: float) -> float:
    if fill_price <= 0.0:
        raise ValueError("BAD_FILL_PRICE")
    fixed_notional = _paper_fixed_notional()
    qty = fixed_notional / float(fill_price)
    if qty <= 0.0:
        raise ValueError("BAD_QTY")
    return float(qty)


def _price_from_snapshot_or_default(repo: Any, market_id: str, outcome: str) -> float:
    """Legacy helper (kept for compatibility); prefer _resolve_fill_price."""
    try:
        fn = getattr(repo, "get_latest_snapshot", None)
        if callable(fn):
            s = fn(market_id=market_id, outcome=outcome)
            if s is not None:
                mid = getattr(s, "mid", None)
                if mid is not None:
                    return float(mid)
    except Exception:
        warn_exc(logger, "snapshot price lookup failed", market_id=market_id, outcome=outcome)

    try:
        fn2 = getattr(repo, "get_latest_mid", None)
        if callable(fn2):
            mid = fn2(market_id, outcome)
            if mid is not None:
                return float(mid)
    except Exception:
        warn_exc(logger, "latest mid lookup failed", market_id=market_id, outcome=outcome)

    return 0.50


def execute_pending_paper(repo: Any, run_id: str, limit: int = 200) -> int:
    """Execute pending paper_queue commands into paper_trades/positions.

    Idempotency: queue rows are unique by command_id; we only execute status=PENDING.
    """
    try:
        rows = repo.list_pending_paper_commands(limit=limit)
    except Exception:
        warn_exc(logger, "list_pending_paper_commands failed")
        return 0

    executed = 0

    for r in rows or []:
        try:
            command_id = r["command_id"]
            created_at = r["created_at"]
            market_id = r["market_id"]
            outcome = r["outcome"]
            cmd = str(r["cmd"]).upper()
            qty = float(r["qty"])
            price_mode = str(r["price_mode"]).upper()
            source_decision_id = r.get("source_decision_id")
        except Exception:
            command_id, created_at, _, market_id, outcome, cmd, qty, price_mode, source_decision_id = r[:9]

        try:
            cmd_up = str(cmd or "").upper()
            price, fill_side_source = _resolve_fill_price(repo, market_id, outcome, cmd_up)
            if price <= 0.0:
                raise ValueError("BAD_FILL_PRICE")
            if cmd == "BUY":
                qty_exec = _qty_for_buy(price)
                repo.paper_buy(
                    run_id=run_id,
                    market_id=market_id,
                    outcome=outcome,
                    qty=qty_exec,
                    price=price,
                    note=f"queue:{command_id} fill_side_source={fill_side_source}",
                    decision_id=source_decision_id,
                )
            elif cmd == "CLOSE":
                _ = repo.paper_close(
                    run_id=run_id,
                    market_id=market_id,
                    outcome=outcome,
                    qty=None,
                    price=price,
                    note=f"queue:{command_id} fill_side_source={fill_side_source}",
                    decision_id=source_decision_id,
                )
            else:
                raise ValueError(f"Unknown cmd: {cmd}")

            repo.mark_paper_command_executed(command_id, executed_at=_now_iso())
            executed += 1

        except Exception as e:
            try:
                repo.mark_paper_command_failed(command_id, executed_at=_now_iso(), error=str(e))
            except Exception:
                warn_exc(logger, "mark_paper_command_failed failed", command_id=command_id)

    return executed
