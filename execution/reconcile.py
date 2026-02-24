from __future__ import annotations

"""execution.reconcile

Reconcile PAPER_* decisions into paper_queue.

Key guarantees:
- Cursor advances ONLY when we actually saw PAPER decisions.
- Cursor is clamped if it ever ends up ahead of MAX(ts) among PAPER decisions.
- We DO NOT trust tuple ordering from Repo helpers; decisions are read via SQL.
- Enqueue count is REAL: we increment only when an INSERT actually happened
  (INSERT OR IGNORE may ignore duplicates silently).

This file is intentionally self-contained and uses direct SQL as a source of truth.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from utils.logging import get_logger, warn_exc

logger = get_logger("execution.reconcile")

CURSOR_KEY = "paper_decisions_cursor_ts"
EPOCH_TS = "1970-01-01T00:00:00+00:00"


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _get_setting(repo: Any, key: str) -> Optional[str]:
    if hasattr(repo, "get_setting"):
        try:
            return repo.get_setting(key)
        except Exception:
            warn_exc(logger, "get_setting failed; falling back to SQL", key=key)
    try:
        with repo.conn() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else None
    except Exception:
        warn_exc(logger, "get_setting SQL fallback failed", key=key)
        return None


def _set_setting(repo: Any, key: str, value: str) -> None:
    if hasattr(repo, "set_setting"):
        try:
            repo.set_setting(key, value)
            return
        except Exception:
            warn_exc(logger, "set_setting failed; falling back to SQL", key=key)
    with repo.conn() as con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def _max_paper_ts(repo: Any) -> Optional[str]:
    with repo.conn() as con:
        row = con.execute("SELECT MAX(ts) FROM decisions_v0 WHERE action LIKE 'PAPER_%'").fetchone()
        return row[0] if row and row[0] else None


def _decision_rows_since(repo: Any, cursor_ts: str, limit: int = 200):
    """Returns (decision_id, ts, market_id, action, status) rows."""
    with repo.conn() as con:
        return con.execute(
            """
            SELECT decision_id, ts, market_id, action, status
            FROM decisions_v0
            WHERE action LIKE 'PAPER_%'
              AND status='OK'
              AND ts >= ?
            ORDER BY ts ASC, decision_id ASC
            LIMIT ?
            """,
            (cursor_ts, int(limit)),
        ).fetchall()


@dataclass(frozen=True)
class PaperCmd:
    outcome: str  # YES/NO
    cmd: str      # BUY/CLOSE
    qty: float
    price_mode: str  # MID


def _expand_action(action: str) -> list[PaperCmd]:
    a = (action or "").upper()
    if a == "PAPER_BUY_BOTH":
        return [PaperCmd("YES", "BUY", 1.0, "MID"), PaperCmd("NO", "BUY", 1.0, "MID")]
    if a == "PAPER_CLOSE_BOTH":
        return [PaperCmd("YES", "CLOSE", 1.0, "MID"), PaperCmd("NO", "CLOSE", 1.0, "MID")]
    if a == "PAPER_BUY_YES":
        return [PaperCmd("YES", "BUY", 1.0, "MID")]
    if a == "PAPER_BUY_NO":
        return [PaperCmd("NO", "BUY", 1.0, "MID")]
    if a == "PAPER_CLOSE_YES":
        return [PaperCmd("YES", "CLOSE", 1.0, "MID")]
    if a == "PAPER_CLOSE_NO":
        return [PaperCmd("NO", "CLOSE", 1.0, "MID")]
    return []


def reconcile_paper(repo: Any, run_id: str = "ui", limit: int = 200) -> int:
    """Enqueue new paper commands for PAPER_* decisions.
    Returns number of REALLY enqueued commands (i.e., inserted rows).
    """

    for fn in ("ensure_paper_queue_schema", "ensure_decisions_v0_schema"):
        if hasattr(repo, fn):
            try:
                getattr(repo, fn)()
            except Exception:
                warn_exc(logger, "schema ensure failed", fn=fn)

    cursor_ts = _get_setting(repo, CURSOR_KEY) or EPOCH_TS

    # Clamp runaway cursor
    max_ts = _max_paper_ts(repo)
    if max_ts and _parse_iso(cursor_ts) > _parse_iso(max_ts):
        cursor_ts = max_ts

    rows = _decision_rows_since(repo, cursor_ts, limit=limit)

    enqueued = 0
    max_seen_ts: Optional[str] = None

    for decision_id, ts, market_id, action, _status in rows:
        for c in _expand_action(action):
            command_id = f"{decision_id}:{c.outcome}:{c.cmd}"

            inserted = False

            if hasattr(repo, "enqueue_paper_command"):
                # Repo.enqueue_paper_command returns bool (True if inserted, False if ignored)
                if hasattr(repo, "paper"):
                    inserted = bool(
                        repo.paper.enqueue_command(
                            command_id=command_id,
                            created_at=ts,
                            run_id=run_id,
                            market_id=market_id,
                            outcome=c.outcome,
                            cmd=c.cmd,
                            qty=c.qty,
                            price_mode=c.price_mode,
                            source_decision_id=decision_id,
                        )
                    )
                else:
                    inserted = bool(
                        repo.enqueue_paper_command(
                            command_id=command_id,
                            created_at=ts,
                            run_id=run_id,
                            market_id=market_id,
                            outcome=c.outcome,
                            cmd=c.cmd,
                            qty=c.qty,
                            price_mode=c.price_mode,
                            source_decision_id=decision_id,
                        )
                    )
            else:
                # Fallback: compute insertion via total_changes delta
                with repo.conn() as con:
                    before = con.total_changes
                    con.execute(
                        """
                        INSERT OR IGNORE INTO paper_queue(
                            command_id, created_at, run_id, market_id,
                            outcome, cmd, qty, price_mode, source_decision_id,
                            status, attempts, error, executed_at
                        )
                        VALUES(?,?,?,?,?,?,?,?,?, 'PENDING', 0, NULL, NULL)
                        """,
                        (
                            command_id,
                            ts,
                            run_id,
                            market_id,
                            c.outcome,
                            c.cmd,
                            float(c.qty),
                            c.price_mode,
                            decision_id,
                        ),
                    )
                    inserted = (con.total_changes - before) > 0

            if inserted:
                enqueued += 1

        if max_seen_ts is None or _parse_iso(ts) > _parse_iso(max_seen_ts):
            max_seen_ts = ts

    # Advance cursor only if we actually saw paper decisions
    if max_seen_ts is not None:
        _set_setting(repo, CURSOR_KEY, max_seen_ts)

    return enqueued
