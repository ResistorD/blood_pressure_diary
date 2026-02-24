from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from utils.logging import get_logger, warn_exc

logger = get_logger("execution.paper_executor")

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _price_from_snapshot_or_default(repo: Any, market_id: str, outcome: str) -> float:
    """Try snapshot.mid first, then repo.get_latest_mid, else 0.50."""
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
            price = _price_from_snapshot_or_default(repo, market_id, outcome) if price_mode == "MID" else 0.50
            if cmd == "BUY":
                repo.paper_buy(
                    run_id=run_id,
                    market_id=market_id,
                    outcome=outcome,
                    qty=qty or 1.0,
                    price=price,
                    note=f"queue:{command_id}",
                    decision_id=source_decision_id,
                )
            elif cmd == "CLOSE":
                _ = repo.paper_close(
                    run_id=run_id,
                    market_id=market_id,
                    outcome=outcome,
                    qty=None,
                    price=price,
                    note=f"queue:{command_id}",
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
