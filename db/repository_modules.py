from __future__ import annotations

import json
import uuid
import os
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, List, Optional

from domain.enums import Mode
from domain.models import Market, Run
from app.runtime_config import load_runtime_config
from utils.logging import get_logger, warn_exc

logger = get_logger("db.repository_modules")
_invalid_signal_count = 0


def _valid_market_id(market_id: str | None) -> bool:
    if not market_id:
        return True
    if os.getenv("PS_DEMO") == "1":
        return True
    return str(market_id).isdigit()


def _market_exists(repo: Any, market_id: str) -> bool:
    try:
        with repo.conn() as con:
            row = con.execute(
                "SELECT 1 FROM markets WHERE market_id = ?",
                (market_id,),
            ).fetchone()
        return row is not None
    except Exception:
        return False


def _dt_to_str(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def _str_to_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


class MarketRepository:
    """Narrow market-related operations."""

    def __init__(self, repo: Any):
        self._repo = repo

    def list_markets(self, limit: int = 100):
        lim = int(limit) if limit is not None else 200
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT market_id, slug, title, close_time, rules_hash, group_key
                FROM markets
                ORDER BY rowid DESC LIMIT ?
                """,
                (lim,),
            ).fetchall()
        out: List[Market] = []
        for r in rows:
            out.append(
                Market(
                    market_id=r["market_id"],
                    slug=r["slug"],
                    title=r["title"],
                    close_time=_str_to_dt(r["close_time"]),
                    rules_hash=r["rules_hash"],
                    group_key=r["group_key"],
                )
            )
        return out

    def get_market(self, market_id: str):
        with self._repo.conn() as con:
            row = con.execute(
                """
                SELECT market_id, slug, title, close_time, rules_hash, group_key
                FROM markets
                WHERE market_id = ?
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        if not row:
            return None
        return Market(
            market_id=row["market_id"],
            slug=row["slug"],
            title=row["title"],
            close_time=_str_to_dt(row["close_time"]),
            rules_hash=row["rules_hash"],
            group_key=row["group_key"],
        )

    def upsert_market(self, market: Any) -> None:
        row = (
            market.market_id,
            market.slug,
            market.title,
            _dt_to_str(getattr(market, "close_time", None)),
            getattr(market, "rules_hash", None),
            getattr(market, "group_key", None),
            getattr(market, "raw_json", None),
        )

        def _op(con):
            con.execute(
                """
                INSERT INTO markets(market_id, slug, title, close_time, rules_hash, group_key, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(market_id) DO
                UPDATE SET slug=excluded.slug,
                           title=excluded.title,
                           close_time=excluded.close_time,
                           rules_hash=excluded.rules_hash,
                           group_key=excluded.group_key,
                           raw_json=excluded.raw_json
                """,
                row,
            )

        if hasattr(self._repo, "enqueue_write"):
            self._repo.enqueue_write(_op)
        else:
            with self._repo.conn() as con:
                _op(con)

    def list_markets_by_group(self, group_key: str, limit: int = 200):
        lim = int(limit) if limit is not None else 200
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT market_id, slug, title, close_time, rules_hash, group_key
                FROM markets
                WHERE group_key = ?
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (group_key, lim),
            ).fetchall()
        out: List[Market] = []
        for r in rows or []:
            out.append(
                Market(
                    market_id=r["market_id"],
                    slug=r["slug"],
                    title=r["title"],
                    close_time=r["close_time"],
                    rules_hash=r["rules_hash"],
                    group_key=r["group_key"],
                )
            )
        return out

    def count_markets_with_fallback(self) -> int:
        with self._repo.conn() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM markets").fetchone()
            n = int(row["n"]) if row else 0
            if n > 0:
                return n

            try:
                self._repo.ensure_decisions_v0_schema()
                row = con.execute("SELECT COUNT(DISTINCT market_id) AS n FROM decisions_v0").fetchone()
                n_dec = int(row["n"]) if row else 0
            except Exception:
                n_dec = 0

            try:
                row = con.execute(
                    "SELECT COUNT(DISTINCT scope_market_id) AS n FROM signals WHERE scope_market_id IS NOT NULL"
                ).fetchone()
                n_sig = int(row["n"]) if row else 0
            except Exception:
                n_sig = 0

            try:
                row = con.execute("SELECT COUNT(DISTINCT market_id) AS n FROM snapshots").fetchone()
                n_snap = int(row["n"]) if row else 0
            except Exception:
                n_snap = 0

        return max(n_dec, n_sig, n_snap)


class RunRepository:
    """Run lifecycle persistence."""

    def __init__(self, repo: Any):
        self._repo = repo

    def insert_run(self, run: Run) -> None:
        with self._repo.conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO runs(run_id, started_at, mode, config_hash, git_hash) VALUES(?,?,?,?,?)",
                (run.run_id, _dt_to_str(run.started_at), run.mode.value, run.config_hash, run.git_hash),
            )

    def get_latest_run(self) -> Run | None:
        with self._repo.conn() as con:
            row = con.execute(
                "SELECT run_id, started_at, mode, config_hash, git_hash FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return Run(
            run_id=row["run_id"],
            started_at=_str_to_dt(row["started_at"]) or datetime.now(timezone.utc),
            mode=Mode(row["mode"]),
            config_hash=row["config_hash"],
            git_hash=row["git_hash"],
        )


class SnapshotRepository:
    """Snapshot write/read operations."""

    def __init__(self, repo: Any):
        self._repo = repo

    def insert_snapshot(self, snap: Any) -> None:
        self.insert_snapshots([snap])

    def insert_snapshots(self, snaps: Any) -> int:
        rows = []
        for s in snaps:
            rows.append(
                (
                    _dt_to_str(s.ts),
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
            )
        if not rows:
            return 0
        def _op(con):
            con.executemany(
                """
                INSERT OR REPLACE INTO snapshots
                (ts, market_id, outcome, bid, ask, mid, spread, liquidity, volume, implied_prob)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )
        if hasattr(self._repo, "enqueue_write"):
            self._repo.enqueue_write(_op)
        else:
            with self._repo.conn() as con:
                _op(con)
        return len(rows)

    def count_snapshots(self) -> int:
        with self._repo.conn() as con:
            try:
                row = con.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()
            except Exception:
                return 0
        return int(row["n"]) if row else 0

    def market_history(self, market_id: str, limit: int = 50, outcome: str = "YES") -> List[Dict[str, Any]]:
        lim = max(1, int(limit))
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT ts, market_id, outcome, bid, ask, mid, spread, liquidity
                FROM snapshots
                WHERE market_id = ? AND outcome = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (market_id, outcome, lim),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows or []:
            out.append(
                {
                    "ts": r["ts"],
                    "market_id": r["market_id"],
                    "outcome": r["outcome"],
                    "bid": r["bid"],
                    "ask": r["ask"],
                    "mid": r["mid"],
                    "spread": r["spread"],
                    "liquidity": r["liquidity"],
                }
            )
        return out

    def get_latest_snapshots(self, market_id: str) -> Dict[str, Dict[str, Any]]:
        out = self.get_latest_snapshots_batch([market_id])
        return out.get(market_id, {})

    def get_latest_snapshots_batch(self, market_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not market_ids:
            return {}
        qmarks = ",".join(["?"] * len(market_ids))
        with self._repo.conn() as con:
            rows = con.execute(
                f"""
                SELECT market_id, outcome, bid, ask, mid, spread, liquidity, volume, implied_prob
                FROM (
                    SELECT market_id,
                           outcome,
                           bid,
                           ask,
                           mid,
                           spread,
                           liquidity,
                           volume,
                           implied_prob,
                           ts,
                           ROW_NUMBER() OVER (PARTITION BY market_id, outcome ORDER BY ts DESC) AS rn
                    FROM snapshots
                    WHERE market_id IN ({qmarks})
                ) s
                WHERE rn = 1
                """,
                tuple(market_ids),
            ).fetchall()

        out: Dict[str, Dict[str, Any]] = {mid: {} for mid in market_ids}
        for r in rows or []:
            out[r["market_id"]][r["outcome"]] = {
                "bid": r["bid"],
                "ask": r["ask"],
                "mid": r["mid"],
                "spread": r["spread"],
                "liquidity": r["liquidity"],
                "volume": r["volume"],
                "implied_prob": r["implied_prob"],
            }
        return out


class SignalRepository:
    """Narrow signal-related operations."""

    def __init__(self, repo: Any):
        self._repo = repo

    def insert_signal(self, signal: Any) -> None:
        global _invalid_signal_count
        mid = getattr(signal, "scope_market_id", None)
        if not _valid_market_id(mid):
            _invalid_signal_count += 1
            if _invalid_signal_count <= 5 or _invalid_signal_count % 50 == 0:
                logger.debug(
                    "dropped_invalid_market_id=%s agent=%s kind=%s",
                    mid,
                    getattr(signal, "agent_id", None),
                    getattr(signal, "kind", None),
                )
            return
        if mid and os.getenv("PS_DEMO") != "1":
            if not _market_exists(self._repo, str(mid)):
                _invalid_signal_count += 1
                if _invalid_signal_count <= 5 or _invalid_signal_count % 50 == 0:
                    logger.debug(
                        "dropped_invalid_market_id=%s agent=%s kind=%s",
                        mid,
                        getattr(signal, "agent_id", None),
                        getattr(signal, "kind", None),
                    )
                return
        with self._repo.conn() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO signals
                (signal_id, ts, run_id, agent_id, kind,
                 scope_market_id, scope_group_key, scope_pair_key,
                 features_json, claim_json, candidates_json,
                 explain_short, explain_long)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    signal.signal_id,
                    _dt_to_str(signal.ts),
                    signal.run_id,
                    signal.agent_id,
                    signal.kind.value,
                    signal.scope_market_id,
                    signal.scope_group_key,
                    signal.scope_pair_key,
                    json.dumps(signal.features, ensure_ascii=False),
                    json.dumps(signal.claim, ensure_ascii=False),
                    json.dumps([c.__dict__ for c in signal.candidates], ensure_ascii=False),
                    signal.explain_short,
                    signal.explain_long,
                ),
            )

    def list_recent_signals(self, limit: int = 200):
        lim = int(limit) if limit is not None else 100
        with self._repo.conn() as con:
            if os.getenv("PS_DEMO") != "1":
                return con.execute(
                    """
                    SELECT ts, agent_id, kind, scope_market_id, explain_short
                    FROM signals
                    WHERE scope_market_id IS NULL OR scope_market_id GLOB '[0-9]*'
                    ORDER BY ts DESC LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
            return con.execute(
                """
                SELECT ts, agent_id, kind, scope_market_id, explain_short
                FROM signals
                ORDER BY ts DESC LIMIT ?
                """,
                (lim,),
            ).fetchall()

    def count_signals(self) -> int:
        with self._repo.conn() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM signals").fetchone()
        return int(row["n"]) if row else 0

    def list_recent_signals_filtered(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        agent: str | None = None,
        kind: str | None = None,
        market_id: str | None = None,
        q: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
    ):
        where = []
        params: List[Any] = []
        if os.getenv("PS_DEMO") != "1":
            where.append("(scope_market_id IS NULL OR scope_market_id GLOB '[0-9]*')")
        if agent:
            where.append("agent_id = ?")
            params.append(agent)
        if kind:
            where.append("kind = ?")
            params.append(kind.upper())
        if market_id:
            where.append("scope_market_id = ?")
            params.append(market_id)
        if q:
            where.append("(LOWER(COALESCE(explain_short, '')) LIKE ? OR LOWER(COALESCE(scope_market_id, '')) LIKE ?)")
            like = f"%{q.lower()}%"
            params.extend([like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_map = {
            "ts": "ts",
            "agent": "agent_id",
            "kind": "kind",
            "market": "scope_market_id",
        }
        order_col = order_map.get((sort_by or "").lower(), "ts")
        order_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
        with self._repo.conn() as con:
            rows = con.execute(
                f"""
                SELECT ts, agent_id, kind, scope_market_id, explain_short
                FROM signals
                {where_sql}
                ORDER BY {order_col} {order_dir}, ts DESC
                LIMIT ? OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return rows

    def count_signals_filtered(
        self,
        *,
        agent: str | None = None,
        kind: str | None = None,
        market_id: str | None = None,
        q: str | None = None,
    ) -> int:
        where = []
        params: List[Any] = []
        if os.getenv("PS_DEMO") != "1":
            where.append("(scope_market_id IS NULL OR scope_market_id GLOB '[0-9]*')")
        if agent:
            where.append("agent_id = ?")
            params.append(agent)
        if kind:
            where.append("kind = ?")
            params.append(kind.upper())
        if market_id:
            where.append("scope_market_id = ?")
            params.append(market_id)
        if q:
            where.append("(LOWER(COALESCE(explain_short, '')) LIKE ? OR LOWER(COALESCE(scope_market_id, '')) LIKE ?)")
            like = f"%{q.lower()}%"
            params.extend([like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._repo.conn() as con:
            row = con.execute(
                f"SELECT COUNT(*) AS n FROM signals {where_sql}",
                tuple(params),
            ).fetchone()
        return int(row["n"]) if row else 0


class DecisionRepository:
    """Narrow decision-related operations."""

    def __init__(self, repo: Any):
        self._repo = repo

    def insert_decision_v0(
        self,
        *,
        decision_id: str,
        ts: str,
        run_id: str,
        market_id: str,
        action: str,
        status: str,
        reason: str | None = None,
        reason_json: str | None = None,
        payload_json: str | None = None,
    ) -> None:
        self._repo.ensure_decisions_v0_schema()
        action_u = str(action or "").upper()
        status_u = str(status or "").upper()
        paper_cmds: list[tuple[str, str]] = []
        if status_u == "OK":
            if action_u == "PAPER_BUY_BOTH":
                paper_cmds = [("YES", "BUY"), ("NO", "BUY")]
            elif action_u == "PAPER_CLOSE_BOTH":
                paper_cmds = [("YES", "CLOSE"), ("NO", "CLOSE")]
            elif action_u == "PAPER_BUY_YES":
                paper_cmds = [("YES", "BUY")]
            elif action_u == "PAPER_BUY_NO":
                paper_cmds = [("NO", "BUY")]
            elif action_u == "PAPER_CLOSE_YES":
                paper_cmds = [("YES", "CLOSE")]
            elif action_u == "PAPER_CLOSE_NO":
                paper_cmds = [("NO", "CLOSE")]

        if paper_cmds:
            self._repo.ensure_paper_queue_schema()

        with self._repo.conn() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                con.execute(
                    """
                    INSERT OR REPLACE INTO decisions_v0(decision_id, ts, run_id, market_id, action, status, reason, reason_json, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (decision_id, ts, run_id, market_id, action, status, reason, reason_json, payload_json),
                )

                for outcome, cmd in paper_cmds:
                    command_id = f"{decision_id}:{outcome}:{cmd}"
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
                            outcome,
                            cmd,
                            1.0,
                            "MID",
                            decision_id,
                        ),
                    )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise

    def insert_decision_domain(self, decision: Any) -> None:
        with self._repo.conn() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO decisions
                (decision_id, ts, run_id, type, plan_json, risk_json, next_review_at, explain_short, explain_long)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    decision.decision_id,
                    _dt_to_str(decision.ts),
                    decision.run_id,
                    decision.type.value,
                    json.dumps(decision.plan, ensure_ascii=False),
                    json.dumps(decision.risk, ensure_ascii=False),
                    _dt_to_str(decision.next_review_at),
                    decision.explain_short,
                    decision.explain_long,
                ),
            )
            for sid in decision.based_on_signal_ids:
                con.execute(
                    "INSERT OR IGNORE INTO decision_signals(decision_id, signal_id) VALUES (?,?)",
                    (decision.decision_id, sid),
                )

    def count_decisions(self) -> int:
        with self._repo.conn() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()
        return int(row["n"]) if row else 0

    def get_last_decision_v0(self, market_id: str):
        self._repo.ensure_decisions_v0_schema()
        with self._repo.conn() as con:
            return con.execute(
                """
                SELECT ts, action, status, reason, reason_json
                FROM decisions_v0
                WHERE market_id = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()

    def get_last_decision_v0_map(self) -> dict[str, tuple]:
        self._repo.ensure_decisions_v0_schema()
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT d.market_id, d.ts, d.action, d.status, d.reason, d.reason_json
                FROM decisions_v0 d
                         JOIN (SELECT market_id, MAX(ts) AS max_ts
                               FROM decisions_v0
                               GROUP BY market_id) last
                ON d.market_id = last.market_id AND d.ts = last.max_ts
                """
            ).fetchall()
        return {r["market_id"]: (r["ts"], r["action"], r["status"], r["reason"], r["reason_json"]) for r in rows}

    def list_decisions_v0_since(self, cursor_ts: str | None, limit: int = 200):
        self._repo.ensure_decisions_v0_schema()
        lim = int(limit) if limit is not None else 200
        with self._repo.conn() as con:
            if cursor_ts:
                rows = con.execute(
                    """
                    SELECT decision_id,
                           ts,
                           run_id,
                           market_id, action, status, COALESCE (reason, '') AS reason, COALESCE (payload_json, '') AS payload_json
                    FROM decisions_v0
                    WHERE ts > ?
                    ORDER BY ts ASC
                    LIMIT ?
                    """,
                    (cursor_ts, lim),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT decision_id,
                           ts,
                           run_id,
                           market_id, action, status, COALESCE (reason, '') AS reason, COALESCE (payload_json, '') AS payload_json
                    FROM decisions_v0
                    ORDER BY ts ASC
                    LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
        return rows

    def list_recent_decisions_v0(self, limit: int = 200):
        self._repo.ensure_decisions_v0_schema()
        lim = int(limit) if limit is not None else 200
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT ts, market_id, action, status, COALESCE(reason, '') AS reason, COALESCE(reason_json, '') AS reason_json
                FROM decisions_v0
                ORDER BY ts DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
        return rows

    def list_recent_decisions_v0_filtered(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        action: str | None = None,
        status: str | None = None,
        market_id: str | None = None,
        q: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
    ):
        self._repo.ensure_decisions_v0_schema()
        where = []
        params: List[Any] = []
        if action:
            where.append("action = ?")
            params.append(action.upper())
        if status:
            where.append("status = ?")
            params.append(status.upper())
        if market_id:
            where.append("market_id = ?")
            params.append(market_id)
        if q:
            where.append("(LOWER(COALESCE(reason, '')) LIKE ? OR LOWER(market_id) LIKE ?)")
            like = f"%{q.lower()}%"
            params.extend([like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_map = {
            "ts": "ts",
            "market": "market_id",
            "action": "action",
            "status": "status",
        }
        order_col = order_map.get((sort_by or "").lower(), "ts")
        order_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
        with self._repo.conn() as con:
            rows = con.execute(
                f"""
                SELECT ts, market_id, action, status, COALESCE(reason, '') AS reason, COALESCE(reason_json, '') AS reason_json
                FROM decisions_v0
                {where_sql}
                ORDER BY {order_col} {order_dir}, ts DESC
                LIMIT ? OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return rows

    def count_decisions_v0_filtered(
        self,
        *,
        action: str | None = None,
        status: str | None = None,
        market_id: str | None = None,
        q: str | None = None,
    ) -> int:
        self._repo.ensure_decisions_v0_schema()
        where = []
        params: List[Any] = []
        if action:
            where.append("action = ?")
            params.append(action.upper())
        if status:
            where.append("status = ?")
            params.append(status.upper())
        if market_id:
            where.append("market_id = ?")
            params.append(market_id)
        if q:
            where.append("(LOWER(COALESCE(reason, '')) LIKE ? OR LOWER(market_id) LIKE ?)")
            like = f"%{q.lower()}%"
            params.extend([like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._repo.conn() as con:
            row = con.execute(
                f"SELECT COUNT(*) AS n FROM decisions_v0 {where_sql}",
                tuple(params),
            ).fetchone()
        return int(row["n"]) if row else 0

    def count_decisions_v0(self) -> int:
        self._repo.ensure_decisions_v0_schema()
        with self._repo.conn() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM decisions_v0").fetchone()
        return int(row["n"]) if row else 0


class PaperRepository:
    """Narrow paper-execution operations."""

    def __init__(self, repo: Any):
        self._repo = repo

    def enqueue_command(
        self,
        *,
        command_id: str,
        created_at: str,
        run_id: str,
        market_id: str,
        outcome: str,
        cmd: str,
        qty: float,
        price_mode: str,
        source_decision_id: str,
    ) -> bool:
        self._repo.ensure_paper_queue_schema()
        with self._repo.conn() as con:
            before = con.total_changes
            con.execute(
                """
                INSERT
                OR IGNORE INTO paper_queue(
                    command_id, created_at, run_id, market_id,
                    outcome, cmd, qty, price_mode, source_decision_id,
                    status, attempts, error, executed_at
                )
                VALUES(?,?,?,?,?,?,?,?,?, 'PENDING', 0, NULL, NULL)
                """,
                (
                    command_id,
                    created_at,
                    run_id,
                    market_id,
                    str(outcome).upper(),
                    str(cmd).upper(),
                    float(qty),
                    str(price_mode).upper(),
                    source_decision_id,
                ),
            )
            return (con.total_changes - before) > 0

    def list_open_positions(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            if hasattr(self._repo, "ensure_paper_schema"):
                self._repo.ensure_paper_schema()
            with self._repo.conn() as con:
                rows = con.execute(
                    "SELECT market_id, outcome, qty, price FROM paper_positions WHERE status='OPEN'"
                ).fetchall()
                for row in rows:
                    out.append(
                        {
                            "market_id": row[0],
                            "outcome": row[1],
                            "notional": float(row[2]) * float(row[3]),
                        }
                    )
        except Exception:
            return []
        return out

    def list_pending_commands(self, limit: int = 200):
        self._repo.ensure_paper_queue_schema()
        lim = int(limit) if limit is not None else 200
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT command_id,
                       created_at,
                       run_id,
                       market_id,
                       outcome,
                       cmd,
                       qty,
                       price_mode,
                       source_decision_id,
                       attempts
                FROM paper_queue
                WHERE status = 'PENDING'
                ORDER BY created_at ASC LIMIT ?
                """,
                (lim,),
            ).fetchall()
        return rows

    def mark_command_executed(self, command_id: str, executed_at: str) -> None:
        self._repo.ensure_paper_queue_schema()
        with self._repo.conn() as con:
            con.execute(
                """
                UPDATE paper_queue
                SET status='EXECUTED',
                    error=NULL,
                    executed_at=?,
                    attempts=attempts + 1
                WHERE command_id = ?
                """,
                (executed_at, command_id),
            )

    def mark_command_failed(self, command_id: str, executed_at: str, error: str) -> None:
        self._repo.ensure_paper_queue_schema()
        with self._repo.conn() as con:
            con.execute(
                """
                UPDATE paper_queue
                SET status='FAILED',
                    error=?,
                    executed_at=?,
                    attempts=attempts + 1
                WHERE command_id = ?
                """,
                ((error or "")[:500], executed_at, command_id),
            )

    def list_recent_for_market(self, market_id: str, limit: int = 50):
        self._repo.ensure_paper_queue_schema()
        lim = int(limit) if limit is not None else 50
        with self._repo.conn() as con:
            cols = [r[1] for r in con.execute("PRAGMA table_info(paper_queue)").fetchall()]
            if "ts" in cols and "action" in cols:
                rows = con.execute(
                    """
                    SELECT ts, action, status, attempts, COALESCE(error, '') AS error
                    FROM paper_queue
                    WHERE market_id = ?
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (market_id, lim),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT created_at AS ts,
                           (COALESCE(outcome, '') || ':' || COALESCE(cmd, '')) AS action,
                           status,
                           attempts,
                           COALESCE(error, '') AS error
                    FROM paper_queue
                    WHERE market_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (market_id, lim),
                ).fetchall()
        return rows

    def count_pending(self) -> int:
        self._repo.ensure_paper_queue_schema()
        with self._repo.conn() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM paper_queue WHERE status='PENDING'").fetchone()
        return int(row["n"]) if row else 0


class EventsRepository:
    """Narrow events-log operations."""

    def __init__(self, repo: Any):
        self._repo = repo

    def log_event(
        self,
        *,
        ts: datetime,
        level: str,
        component: str,
        message: str,
        payload: Dict[str, Any] | None = None,
    ) -> None:
        self._repo.ensure_events_schema()
        with self._repo.conn() as con:
            con.execute(
                "INSERT INTO events_log(ts, level, component, message, payload_json) VALUES (?,?,?,?,?)",
                (_dt_to_str(ts), level, component, message, json.dumps(payload or {}, ensure_ascii=False)),
            )

    def log_events_batch(self, events: List[Dict[str, Any]]) -> int:
        if not events:
            return 0
        self._repo.ensure_events_schema()
        rows = [
            (
                _dt_to_str(e.get("ts")),
                str(e.get("level", "INFO")),
                str(e.get("component", "app")),
                str(e.get("message", "")),
                json.dumps(e.get("payload") or {}, ensure_ascii=False),
            )
            for e in events
        ]
        with self._repo.conn() as con:
            con.executemany(
                "INSERT INTO events_log(ts, level, component, message, payload_json) VALUES (?,?,?,?,?)",
                rows,
            )
        return len(rows)


class SettingsRepository:
    """Narrow settings operations."""

    def __init__(self, repo: Any):
        self._repo = repo

    def get(self, key: str, default: str | None = None) -> str | None:
        self._repo.ensure_settings_schema()
        with self._repo.conn() as con:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self._repo.ensure_settings_schema()
        now = _dt_to_str(datetime.now(timezone.utc))
        with self._repo.conn() as con:
            con.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?) ON CONFLICT(key) DO
                UPDATE SET value =excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, now or ""),
            )

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key, "1" if default else "0")
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    def is_paused(self) -> bool:
        return self.get_bool("paused", default=False)

    def set_paused(self, paused: bool) -> None:
        self.set("paused", "1" if paused else "0")

    def toggle_paused(self) -> bool:
        new_val = not self.is_paused()
        self.set_paused(new_val)
        return new_val


class DeprioritizeRepository:
    """Read-only access to deprioritize rules and effective weights."""

    def __init__(self, repo: Any):
        self._repo = repo

    def list_rules(self) -> List[Dict[str, Any]]:
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT id, scope, key, weight, reason, created_ts, expires_ts, is_enabled
                FROM deprioritize_rules
                ORDER BY id DESC
                """
            ).fetchall()
        return [dict(r) for r in rows or []]

    def get_effective_weight(self, market_id: str, action: str | None = None) -> Dict[str, Any]:
        market_id = (market_id or "").strip()
        action = (action or "").strip()
        if not market_id:
            return {"weight": 1.0, "reason": "", "matched_rules_count": 0}

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        clauses = ["(scope='market' AND key=?)"]
        params: List[Any] = [market_id]
        if action:
            clauses.append("(scope='action' AND key=?)")
            params.append(action)
            clauses.append("(scope='market_action' AND key=?)")
            params.append(f"{market_id}|{action}")

        sql = f"""
            SELECT scope, key, weight, reason
            FROM deprioritize_rules
            WHERE is_enabled=1
              AND (expires_ts IS NULL OR expires_ts > ?)
              AND ({' OR '.join(clauses)})
        """
        with self._repo.conn() as con:
            rows = con.execute(sql, [now] + params).fetchall()

        if not rows:
            return {"weight": 1.0, "reason": "", "matched_rules_count": 0}

        weights: List[float] = []
        reasons: List[str] = []
        for r in rows:
            try:
                weights.append(float(r["weight"]))
            except Exception:
                weights.append(1.0)
            reason = (r["reason"] or "").strip()
            if reason:
                reasons.append(reason)

        weight = min(weights) if weights else 1.0
        reason = "; ".join(reasons)
        return {"weight": weight, "reason": reason, "matched_rules_count": len(rows)}


class ReadModelRepository:
    """Read-side/UI-oriented aggregated queries."""

    def __init__(self, repo: Any):
        self._repo = repo

    @staticmethod
    def _json_loads_safe(raw: str | None, default: Any = None) -> Any:
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def list_cases(self, minutes_signals: int = 30, minutes_snaps: int = 10):
        now = datetime.now(timezone.utc)
        since_signals = now - timedelta(minutes=int(minutes_signals))
        since_snaps = now - timedelta(minutes=int(minutes_snaps))

        with self._repo.conn() as con:
            sig_rows = con.execute(
                """
                SELECT scope_market_id                                           AS market_id,
                       COUNT(1)                                                  AS cnt,
                       MAX(ts)                                                   AS last_ts,
                       GROUP_CONCAT(DISTINCT agent_id)                           AS agents,
                       GROUP_CONCAT(DISTINCT kind)                               AS kinds,
                       SUM(CASE WHEN kind = 'RISK_CONSTRAINT' THEN 1 ELSE 0 END) AS risk_cnt
                FROM signals
                WHERE scope_market_id IS NOT NULL
                  AND ts >= ?
                GROUP BY scope_market_id
                """,
                (_dt_to_str(since_signals),),
            ).fetchall()

            sig_by_market: dict[str, dict] = {}
            for r in sig_rows:
                mid = r["market_id"]
                risk_cnt = int(r["risk_cnt"] or 0)
                sig_by_market[mid] = {
                    "signal_count": int(r["cnt"] or 0),
                    "last_signal_ts": r["last_ts"],
                    "signal_agents": (r["agents"] or "").replace(",", ", "),
                    "signal_kinds": (r["kinds"] or "").replace(",", ", "),
                    "risk_cnt": risk_cnt,
                    "status": "BLOCKED" if risk_cnt > 0 else "OK",
                }

            snap_rows = con.execute(
                """
                SELECT market_id, MAX(ts) AS last_ts
                FROM snapshots
                WHERE ts >= ?
                GROUP BY market_id
                """,
                (_dt_to_str(since_snaps),),
            ).fetchall()
            snap_by_market = {r["market_id"]: r["last_ts"] for r in snap_rows}

            active_market_ids = set(sig_by_market.keys()) | set(snap_by_market.keys())
            if not active_market_ids:
                return []

            qmarks = ",".join(["?"] * len(active_market_ids))
            latest_rows = con.execute(
                f"""
                SELECT market_id, outcome, mid, spread, liquidity
                FROM (
                    SELECT market_id, outcome, mid, spread, liquidity, ts,
                           ROW_NUMBER() OVER (PARTITION BY market_id, outcome ORDER BY ts DESC) AS rn
                    FROM snapshots
                    WHERE market_id IN ({qmarks})
                )
                WHERE rn=1 AND outcome IN ('YES','NO')
                """,
                tuple(active_market_ids),
            ).fetchall()

            latest_by_market: dict[str, dict[str, dict]] = {}
            for r in latest_rows:
                mid = r["market_id"]
                outc = r["outcome"]
                latest_by_market.setdefault(mid, {})[outc] = {
                    "mid": r["mid"],
                    "spread": r["spread"],
                    "liquidity": r["liquidity"],
                }

            market_rows = con.execute(
                f"""
                SELECT market_id, slug, title, group_key
                FROM markets
                WHERE market_id IN ({qmarks})
                """,
                tuple(active_market_ids),
            ).fetchall()

            out = []
            for m in market_rows:
                mid = m["market_id"]
                siginfo = sig_by_market.get(mid, {})
                latest = latest_by_market.get(mid, {})

                yes = latest.get("YES", {})
                no = latest.get("NO", {})

                sum_mid = None
                spread = None
                liq = None

                try:
                    y = yes.get("mid")
                    n = no.get("mid")
                    if y is not None and n is not None:
                        sum_mid = float(y) + float(n)
                except Exception:
                    sum_mid = None

                try:
                    ys = yes.get("spread")
                    ns = no.get("spread")
                    if ys is not None or ns is not None:
                        spread = max(float(ys or 0.0), float(ns or 0.0))
                except Exception:
                    spread = None

                try:
                    yl = yes.get("liquidity")
                    nl = no.get("liquidity")
                    if yl is not None or nl is not None:
                        vals = [float(v) for v in (yl, nl) if v is not None]
                        liq = min(vals) if vals else None
                except Exception:
                    liq = None

                info = {
                    "market_id": mid,
                    "slug": m["slug"],
                    "title": m["title"],
                    "group_key": m["group_key"],
                    "last_snapshot_ts": snap_by_market.get(mid),
                    "last_signal_ts": siginfo.get("last_signal_ts"),
                    "signal_count": siginfo.get("signal_count", 0),
                    "signal_agents": siginfo.get("signal_agents", ""),
                    "signal_kinds": siginfo.get("signal_kinds", ""),
                    "status": siginfo.get("status", "OK"),
                    "sum_mid": sum_mid,
                    "spread": spread,
                    "liq": liq,
                }

                parts = []
                if info["signal_count"]:
                    parts.append(f"Сигналов: {info['signal_count']}")
                if info["signal_agents"]:
                    parts.append(f"агенты: {info['signal_agents']}")
                if info["signal_kinds"]:
                    parts.append(f"типы: {info['signal_kinds']}")
                if info["status"] == "BLOCKED":
                    parts.append("⚠️ риск-ограничение")
                if info["last_snapshot_ts"] and not info["signal_count"]:
                    parts.append("есть свежие снимки цен")
                info["reason"] = "; ".join(parts)

                out.append(info)

            def _ts_key(x):
                return x.get("last_signal_ts") or x.get("last_snapshot_ts") or ""

            out.sort(key=_ts_key, reverse=True)
            if os.getenv("PS_DEMO") != "1":
                out = [
                    x for x in out
                    if str(x.get("group_key") or "").lower() != "demo_cluster"
                    and "demo market" not in str(x.get("title") or "").lower()
                ]
            return out

    def get_case_details(self, market_id: str, signals_limit: int = 200, snaps_limit: int = 80) -> dict:
        with self._repo.conn() as con:
            sigs = con.execute(
                """
                SELECT ts, agent_id, kind, features_json, explain_short
                FROM signals
                WHERE scope_market_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (market_id, signals_limit),
            ).fetchall()

            snaps = con.execute(
                """
                SELECT ts, outcome, bid, ask, mid, spread, liquidity
                FROM snapshots
                WHERE market_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (market_id, snaps_limit),
            ).fetchall()

            quality_alert = self.latest_quality_alert(market_id, minutes=180, con=con)

        market = None
        for m in self._repo.list_markets(limit=5000):
            if m.market_id == market_id:
                market = m
                break

        return {
            "market": market,
            "market_id": market_id,
            "sigs": sigs,
            "snaps": snaps,
            "quality_alert": quality_alert,
        }

    def get_latest_decision_v0_row(self, market_id: str) -> Dict[str, Any] | None:
        with self._repo.conn() as con:
            row = con.execute(
                """
                SELECT ts, market_id, action, status, COALESCE(reason, '') AS reason,
                       COALESCE(reason_json, '') AS reason_json, COALESCE(payload_json, '') AS payload_json
                FROM decisions_v0
                WHERE market_id = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "ts": row["ts"],
            "market_id": row["market_id"],
            "action": row["action"],
            "status": row["status"],
            "reason": row["reason"],
            "reason_json": self._json_loads_safe(row["reason_json"], {}),
            "payload": self._json_loads_safe(row["payload_json"], {}),
        }

    def get_case_narrative(self, market_id: str, minutes: int = 240) -> Dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(minutes=max(1, int(minutes)))
        since_s = since.isoformat(timespec="seconds")
        with self._repo.conn() as con:
            sigs = con.execute(
                """
                SELECT ts, agent_id, kind, COALESCE(explain_short, '') AS explain_short, COALESCE(explain_long, '') AS explain_long
                FROM signals
                WHERE scope_market_id = ?
                  AND ts >= ?
                ORDER BY ts DESC
                LIMIT 200
                """,
                (market_id, since_s),
            ).fetchall()
            trades = con.execute(
                """
                SELECT ts, side, outcome, qty, price, COALESCE(note, '') AS note
                FROM paper_trades
                WHERE market_id = ?
                ORDER BY ts DESC
                LIMIT 40
                """,
                (market_id,),
            ).fetchall()
            pos = con.execute(
                """
                SELECT status, qty, avg_price, opened_at
                FROM paper_positions
                WHERE market_id = ?
                ORDER BY opened_at DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()

        scout = next((s for s in sigs if str(s["agent_id"]).lower().startswith("scout")), None)
        logic = next((s for s in sigs if str(s["agent_id"]).lower().startswith("logic")), None)
        risk_sig = next((s for s in sigs if str(s["kind"]).upper() in {"RISK_CONSTRAINT", "QUALITY_ALERT"}), None)
        decision = self.get_latest_decision_v0_row(market_id)

        realized = 0.0
        for t in trades or []:
            if str(t["side"]).upper() == "SELL":
                realized += 0.0

        risk_reason = ""
        if decision and str(decision.get("status", "")).upper() == "BLOCKED":
            risk_reason = str(decision.get("reason", ""))
        elif self._repo.get_bool_setting("kill_switch", default=False):
            risk_reason = self._repo.get_setting("kill_switch_reason", "kill-switch enabled") or "kill-switch enabled"

        return {
            "scout": dict(scout) if scout else None,
            "logic": dict(logic) if logic else None,
            "decision": decision,
            "paper": {
                "position": dict(pos) if pos else None,
                "trades": [dict(x) for x in (trades or [])[:10]],
                "realized_pnl_estimate": realized,
            },
            "risk": {
                "blocked_reason": risk_reason or "",
                "risk_signal": dict(risk_sig) if risk_sig else None,
                "kill_switch": self._repo.get_bool_setting("kill_switch", default=False),
            },
        }

    def latest_risk_constraint(self, market_id: str, minutes: int = 60):
        since = datetime.now(timezone.utc) - timedelta(minutes=int(minutes))
        since_s = since.isoformat(timespec="seconds")
        with self._repo.conn() as con:
            return con.execute(
                """
                SELECT ts, agent_id, kind, explain_short, COALESCE(explain_long, '') AS explain_long
                FROM signals
                WHERE scope_market_id = ?
                  AND ts >= ?
                  AND kind = 'RISK_CONSTRAINT'
                ORDER BY ts DESC
                LIMIT 1
                """,
                (market_id, since_s),
            ).fetchone()

    def latest_quality_alert(self, market_id: str, minutes: int = 60, con: Any | None = None):
        since = datetime.now(timezone.utc) - timedelta(minutes=int(minutes))
        since_s = since.isoformat(timespec="seconds")

        own_cm = None
        if con is None:
            own_cm = self._repo.conn()
            con = own_cm.__enter__()

        try:
            row = con.execute(
                """
                SELECT ts, agent_id, kind, explain_short, COALESCE(explain_long, '') AS explain_long
                FROM signals
                WHERE scope_market_id = ?
                  AND ts >= ?
                  AND (
                        kind IN ('QUALITY_ALERT', 'QUALITY', 'AUDIT_ALERT', 'AUDIT', 'DATA_QUALITY')
                        OR agent_id IN ('auditor', 'Auditor', 'AuditorAgent')
                      )
                ORDER BY ts DESC
                LIMIT 1
                """,
                (market_id, since_s),
            ).fetchone()
            return row
        finally:
            if own_cm is not None:
                own_cm.__exit__(None, None, None)


class PaperAnalyticsRepository:
    """Paper trading analytics and aggregate metrics."""

    def __init__(self, repo: Any):
        self._repo = repo

    @staticmethod
    def _json_loads_safe(raw: str | None, default: Any = None) -> Any:
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def get_metrics(self) -> dict:
        self._repo.ensure_paper_schema()
        now_s = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def _dt(ts: str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        with self._repo.conn() as con:
            pos_rows = con.execute(
                """
                SELECT position_id, opened_at, market_id, outcome, qty, avg_price, status
                FROM paper_positions
                """
            ).fetchall()

            sell_map = {}
            for r in con.execute(
                """
                SELECT market_id, outcome, ts, price
                FROM paper_trades
                WHERE side='SELL'
                ORDER BY ts DESC
                """
            ).fetchall():
                key = (r["market_id"], r["outcome"])
                if key not in sell_map:
                    sell_map[key] = (r["ts"], float(r["price"]))

            mid_map = {}
            for r in con.execute(
                """
                SELECT s.market_id, s.outcome, s.mid
                FROM snapshots s
                JOIN (
                    SELECT market_id, outcome, MAX(ts) AS ts
                    FROM snapshots
                    GROUP BY market_id, outcome
                ) last
                ON s.market_id=last.market_id AND s.outcome=last.outcome AND s.ts=last.ts
                """
            ).fetchall():
                mid_map[(r["market_id"], r["outcome"])] = float(r["mid"]) if r["mid"] is not None else None

            realized = 0.0
            unrealized = 0.0

            closed_pnls = []
            closed_holds = []
            open_holds = []
            entry_spreads = []

            for p in pos_rows:
                opened_at = p["opened_at"]
                market_id = p["market_id"]
                outcome = p["outcome"]
                qty = float(p["qty"]) if p["qty"] is not None else 0.0
                entry = float(p["avg_price"]) if p["avg_price"] is not None else 0.0
                status = p["status"]

                try:
                    row = con.execute(
                        """
                        SELECT spread
                        FROM snapshots
                        WHERE market_id=? AND outcome=? AND ts<=?
                        ORDER BY ts DESC LIMIT 1
                        """,
                        (market_id, outcome, opened_at),
                    ).fetchone()
                    if row and row["spread"] is not None:
                        entry_spreads.append(float(row["spread"]))
                except Exception:
                    warn_exc(logger, "entry spread lookup failed", market_id=market_id, outcome=outcome)

                o_dt = _dt(opened_at)
                n_dt = _dt(now_s)
                if o_dt and n_dt:
                    open_holds.append((n_dt - o_dt).total_seconds())

                if status == "CLOSED":
                    sell = sell_map.get((market_id, outcome))
                    if sell:
                        sell_ts, sell_px = sell
                        pnl = (sell_px - entry) * qty
                        realized += pnl
                        closed_pnls.append(pnl)

                        o = _dt(opened_at)
                        c = _dt(sell_ts)
                        if o and c:
                            closed_holds.append((c - o).total_seconds())
                    continue

                if status == "OPEN":
                    mid = mid_map.get((market_id, outcome))
                    if mid is None:
                        mid = entry
                    unrealized += (float(mid) - entry) * qty

            pnl_total = realized + unrealized
            fees_paid = 0.0
            try:
                row = con.execute(
                    "SELECT COALESCE(SUM(fee), 0.0) AS fees_paid FROM paper_trades"
                ).fetchone()
                fees_paid = float(row["fees_paid"] or 0.0) if row else 0.0
            except Exception:
                fees_paid = 0.0
            net_pnl = pnl_total - fees_paid

            hit_rate = 0.0
            true_positive = 0
            false_positive = 0
            if closed_pnls:
                wins = sum(1 for x in closed_pnls if x > 0)
                true_positive = wins
                false_positive = len(closed_pnls) - wins
                hit_rate = wins / len(closed_pnls)

            holds = closed_holds if closed_holds else open_holds
            avg_hold = sum(holds) / len(holds) if holds else 0.0

            avg_entry_spread = sum(entry_spreads) / len(entry_spreads) if entry_spreads else 0.0

        return {
            "pnl_total": pnl_total,
            "gross_pnl": pnl_total,
            "fees_paid": fees_paid,
            "net_pnl": net_pnl,
            "pnl_realized": realized,
            "pnl_unrealized": unrealized,
            "hit_rate": hit_rate,
            "avg_hold_sec": avg_hold,
            "avg_entry_spread": avg_entry_spread,
            "closed_trades": len(closed_pnls),
            "true_positive": true_positive,
            "false_positive": false_positive,
        }

    def _table_has_column(self, con: Any, table: str, column: str) -> bool:
        try:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        except Exception:
            return False
        return column in cols

    def _resolve_group_field(self, by: str) -> tuple[str, str] | None:
        key = (by or "").strip().lower()
        with self._repo.conn() as con:
            if key == "action":
                if self._table_has_column(con, "decisions_v0", "action"):
                    return ("decisions_v0", "action")
                return None
            if key == "agent":
                for col in ("agent", "agent_id"):
                    if self._table_has_column(con, "decisions_v0", col):
                        return ("decisions_v0", col)
                for col in ("agent", "agent_id"):
                    if self._table_has_column(con, "decisions", col):
                        return ("decisions", col)
                return None
            if key in {"type", "kind"}:
                if self._table_has_column(con, "decisions", "type"):
                    return ("decisions", "type")
                if self._table_has_column(con, "decisions_v0", "type"):
                    return ("decisions_v0", "type")
                if self._table_has_column(con, "decisions_v0", "kind"):
                    return ("decisions_v0", "kind")
                return None
        return None

    def get_pnl_timeseries(self, limit: int = 200) -> List[Dict[str, Any]]:
        lim = max(1, int(limit))
        with self._repo.conn() as con:
            sells = con.execute(
                """
                SELECT ts, market_id, outcome, qty, price, COALESCE(fee, 0.0) AS fee
                FROM paper_trades
                WHERE side='SELL'
                ORDER BY ts ASC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
            max_ts = sells[-1]["ts"] if sells else None
            fee_rows = []
            if max_ts:
                fee_rows = con.execute(
                    """
                    SELECT ts, COALESCE(fee, 0.0) AS fee
                    FROM paper_trades
                    WHERE ts <= ?
                    ORDER BY ts ASC
                    """,
                    (max_ts,),
                ).fetchall()
            pos_rows = con.execute(
                """
                SELECT position_id, opened_at, market_id, outcome, qty, avg_price
                FROM paper_positions
                WHERE status='CLOSED'
                ORDER BY opened_at ASC
                """
            ).fetchall()

        by_key: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for p in pos_rows or []:
            k = (p["market_id"], p["outcome"])
            by_key.setdefault(k, []).append(
                {
                    "position_id": p["position_id"],
                    "opened_at": p["opened_at"],
                    "qty": float(p["qty"] or 0.0),
                    "avg_price": float(p["avg_price"] or 0.0),
                }
            )

        used_positions: set[str] = set()
        cumulative = 0.0
        cumulative_fees = 0.0
        fee_idx = 0
        out: List[Dict[str, Any]] = []

        for t in sells or []:
            ts = t["ts"]
            market_id = t["market_id"]
            outcome = t["outcome"]
            qty = float(t["qty"] or 0.0)
            price = float(t["price"] or 0.0)
            event_fee = float(t["fee"] or 0.0)
            key = (market_id, outcome)

            matched = None
            for p in by_key.get(key, []):
                if p["position_id"] in used_positions:
                    continue
                if p["opened_at"] and p["opened_at"] <= ts:
                    matched = p
            event_pnl = 0.0
            if matched is not None:
                used_positions.add(matched["position_id"])
                event_pnl = (price - float(matched["avg_price"])) * (qty or float(matched["qty"]))
            cumulative += event_pnl
            while fee_idx < len(fee_rows) and fee_rows[fee_idx]["ts"] <= ts:
                cumulative_fees += float(fee_rows[fee_idx]["fee"] or 0.0)
                fee_idx += 1
            out.append(
                {
                    "ts": ts,
                    "market_id": market_id,
                    "outcome": outcome,
                    "event_pnl": event_pnl,
                    "cumulative_pnl": cumulative,
                    "event_fee": event_fee,
                    "cumulative_fees": cumulative_fees,
                    "event_net_pnl": event_pnl - event_fee,
                    "cumulative_net_pnl": cumulative - cumulative_fees,
                }
            )
        return out

    def get_quality_breakdown(self, by: str = "action") -> List[Dict[str, Any]]:
        group_ref = self._resolve_group_field(by)
        if not group_ref:
            return []
        table_name, group_field = group_ref
        self._repo.ensure_paper_schema()
        with self._repo.conn() as con:
            rows = con.execute(
                f"""
                WITH d AS (
                  SELECT
                    decision_id,
                    SUM(CASE WHEN side='SELL' THEN qty*price ELSE -qty*price END) AS gross_pnl,
                    SUM(COALESCE(fee,0.0)) AS fees_paid,
                    SUM(CASE WHEN side='BUY'  THEN qty ELSE 0 END) AS buy_qty,
                    SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END) AS sell_qty
                  FROM paper_trades
                  WHERE decision_id IS NOT NULL AND TRIM(decision_id) != ''
                  GROUP BY decision_id
                ),
                o AS (
                  SELECT
                    decision_id,
                    (gross_pnl - fees_paid) AS net_pnl,
                    CASE WHEN buy_qty > sell_qty THEN 'OPEN' ELSE 'CLOSED' END AS status
                  FROM d
                )
                SELECT
                  r.{group_field} AS bucket,
                  COUNT(*) AS decisions_total,
                  SUM(CASE WHEN o.status='CLOSED' THEN 1 ELSE 0 END) AS closed_count,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl < 0 THEN 1 ELSE 0 END) AS losses,
                  AVG(CASE WHEN o.status='CLOSED' THEN o.net_pnl END) AS avg_net_pnl,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl > 0 THEN o.net_pnl ELSE 0 END) AS sum_wins,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl < 0 THEN -o.net_pnl ELSE 0 END) AS sum_losses
                FROM o
                JOIN {table_name} r ON r.decision_id = o.decision_id
                GROUP BY r.{group_field}
                ORDER BY avg_net_pnl DESC
                """
            ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            closed_count = int(r["closed_count"] or 0)
            wins = int(r["wins"] or 0)
            losses = int(r["losses"] or 0)
            sum_wins = float(r["sum_wins"] or 0.0)
            sum_losses = float(r["sum_losses"] or 0.0)
            win_rate = (wins / closed_count) if closed_count > 0 else 0.0
            profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else None
            avg_net = float(r["avg_net_pnl"] or 0.0) if r["avg_net_pnl"] is not None else 0.0
            out.append(
                {
                    "bucket": r["bucket"],
                    "decisions_total": int(r["decisions_total"] or 0),
                    "closed_count": closed_count,
                    "wins": wins,
                    "losses": losses,
                    "avg_net_pnl": avg_net,
                    "sum_wins": sum_wins,
                    "sum_losses": sum_losses,
                    "win_rate": win_rate,
                    "profit_factor": profit_factor,
                    "expectancy": avg_net,
                }
            )
        return out

    def get_top_decisions(self, limit: int = 10, direction: str = "winners") -> List[Dict[str, Any]]:
        lim = max(1, int(limit))
        dir_key = (direction or "winners").strip().lower()
        order = "DESC" if dir_key == "winners" else "ASC"

        with self._repo.conn() as con:
            if not self._table_has_column(con, "decisions_v0", "market_id"):
                return []
            rows = con.execute(
                f"""
                WITH d AS (
                  SELECT
                    decision_id,
                    SUM(CASE WHEN side='SELL' THEN qty*price ELSE -qty*price END) AS gross_pnl,
                    SUM(COALESCE(fee,0.0)) AS fees_paid,
                    SUM(CASE WHEN side='BUY'  THEN qty ELSE 0 END) AS buy_qty,
                    SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END) AS sell_qty
                  FROM paper_trades
                  WHERE decision_id IS NOT NULL AND TRIM(decision_id) != ''
                  GROUP BY decision_id
                ),
                o AS (
                  SELECT
                    decision_id,
                    (gross_pnl - fees_paid) AS net_pnl,
                    CASE WHEN buy_qty > sell_qty THEN 'OPEN' ELSE 'CLOSED' END AS status
                  FROM d
                )
                SELECT
                  o.decision_id,
                  o.net_pnl,
                  o.status,
                  r.market_id,
                  r.action,
                  r.ts
                FROM o
                JOIN decisions_v0 r ON r.decision_id = o.decision_id
                WHERE o.status='CLOSED'
                ORDER BY o.net_pnl {order}
                LIMIT ?
                """,
                (lim,),
            ).fetchall()

        return [
            {
                "decision_id": r["decision_id"],
                "market_id": r["market_id"],
                "action": r["action"],
                "net_pnl": float(r["net_pnl"] or 0.0),
                "status": r["status"],
                "ts": r["ts"],
            }
            for r in rows or []
        ]

    def get_market_quality(self, limit: int = 15, direction: str = "best") -> List[Dict[str, Any]]:
        lim = max(1, int(limit))
        dir_key = (direction or "best").strip().lower()
        order = "DESC" if dir_key == "best" else "ASC"

        with self._repo.conn() as con:
            if not self._table_has_column(con, "decisions_v0", "market_id"):
                return []
            rows = con.execute(
                f"""
                WITH d AS (
                  SELECT
                    decision_id,
                    SUM(CASE WHEN side='SELL' THEN qty*price ELSE -qty*price END) AS gross_pnl,
                    SUM(COALESCE(fee,0.0)) AS fees_paid,
                    SUM(CASE WHEN side='BUY'  THEN qty ELSE 0 END) AS buy_qty,
                    SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END) AS sell_qty
                  FROM paper_trades
                  WHERE decision_id IS NOT NULL AND TRIM(decision_id) != ''
                  GROUP BY decision_id
                ),
                o AS (
                  SELECT
                    decision_id,
                    (gross_pnl - fees_paid) AS net_pnl,
                    CASE WHEN buy_qty > sell_qty THEN 'OPEN' ELSE 'CLOSED' END AS status
                  FROM d
                )
                SELECT
                  r.market_id AS market_id,
                  COUNT(*) AS decisions_total,
                  SUM(CASE WHEN o.status='CLOSED' THEN 1 ELSE 0 END) AS closed_count,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl < 0 THEN 1 ELSE 0 END) AS losses,
                  SUM(CASE WHEN o.status='CLOSED' THEN o.net_pnl ELSE 0 END) AS sum_net_pnl,
                  AVG(CASE WHEN o.status='CLOSED' THEN o.net_pnl END) AS avg_net_pnl,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl > 0 THEN o.net_pnl ELSE 0 END) AS sum_wins,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl < 0 THEN -o.net_pnl ELSE 0 END) AS sum_losses
                FROM o
                JOIN decisions_v0 r ON r.decision_id = o.decision_id
                GROUP BY r.market_id
                ORDER BY sum_net_pnl {order}
                LIMIT ?
                """,
                (lim,),
            ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            closed_count = int(r["closed_count"] or 0)
            wins = int(r["wins"] or 0)
            losses = int(r["losses"] or 0)
            sum_wins = float(r["sum_wins"] or 0.0)
            sum_losses = float(r["sum_losses"] or 0.0)
            win_rate = (wins / closed_count) if closed_count > 0 else None
            profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else None
            out.append(
                {
                    "market_id": r["market_id"],
                    "decisions_total": int(r["decisions_total"] or 0),
                    "closed_count": closed_count,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate,
                    "sum_net_pnl": float(r["sum_net_pnl"] or 0.0),
                    "avg_net_pnl": float(r["avg_net_pnl"] or 0.0) if r["avg_net_pnl"] is not None else 0.0,
                    "profit_factor": profit_factor,
                }
            )
        return out

    def get_quality_coverage(self) -> Dict[str, Any]:
        self._repo.ensure_paper_schema()
        with self._repo.conn() as con:
            row_total = con.execute("SELECT COUNT(*) AS n FROM decisions_v0").fetchone()
            total = int(row_total["n"] or 0) if row_total else 0
            row_linked = con.execute(
                """
                SELECT COUNT(DISTINCT decision_id) AS n
                FROM paper_trades
                WHERE decision_id IS NOT NULL AND TRIM(decision_id) != ''
                """
            ).fetchone()
            linked = int(row_linked["n"] or 0) if row_linked else 0
            row_status = con.execute(
                """
                WITH d AS (
                  SELECT
                    decision_id,
                    SUM(CASE WHEN side='BUY'  THEN qty ELSE 0 END) AS buy_qty,
                    SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END) AS sell_qty
                  FROM paper_trades
                  WHERE decision_id IS NOT NULL AND TRIM(decision_id) != ''
                  GROUP BY decision_id
                )
                SELECT
                  SUM(CASE WHEN buy_qty > sell_qty THEN 1 ELSE 0 END) AS open_count,
                  SUM(CASE WHEN buy_qty > sell_qty THEN 0 ELSE 1 END) AS closed_count
                FROM d
                """
            ).fetchone()
            open_count = int(row_status["open_count"] or 0) if row_status else 0
            closed_count = int(row_status["closed_count"] or 0) if row_status else 0

        linked_rate = (linked / total) if total > 0 else 0.0
        closed_rate = (closed_count / linked) if linked > 0 else 0.0
        return {
            "decisions_with_trades": linked,
            "decisions_total": total,
            "linked_rate": linked_rate,
            "outcomes_closed": closed_count,
            "outcomes_open": open_count,
            "closed_rate": closed_rate,
        }

    def get_market_worst_by_win_rate(self, limit: int = 15, min_closed: int = 5) -> List[Dict[str, Any]]:
        lim = max(1, int(limit))
        min_c = max(1, int(min_closed))
        with self._repo.conn() as con:
            if not self._table_has_column(con, "decisions_v0", "market_id"):
                return []
            rows = con.execute(
                """
                WITH d AS (
                  SELECT
                    decision_id,
                    SUM(CASE WHEN side='SELL' THEN qty*price ELSE -qty*price END) AS gross_pnl,
                    SUM(COALESCE(fee,0.0)) AS fees_paid,
                    SUM(CASE WHEN side='BUY'  THEN qty ELSE 0 END) AS buy_qty,
                    SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END) AS sell_qty
                  FROM paper_trades
                  WHERE decision_id IS NOT NULL AND TRIM(decision_id) != ''
                  GROUP BY decision_id
                ),
                o AS (
                  SELECT
                    decision_id,
                    (gross_pnl - fees_paid) AS net_pnl,
                    CASE WHEN buy_qty > sell_qty THEN 'OPEN' ELSE 'CLOSED' END AS status
                  FROM d
                )
                SELECT
                  r.market_id AS market_id,
                  COUNT(*) AS decisions_total,
                  SUM(CASE WHEN o.status='CLOSED' THEN 1 ELSE 0 END) AS closed_count,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl < 0 THEN 1 ELSE 0 END) AS losses,
                  SUM(CASE WHEN o.status='CLOSED' THEN o.net_pnl ELSE 0 END) AS sum_net_pnl,
                  AVG(CASE WHEN o.status='CLOSED' THEN o.net_pnl END) AS avg_net_pnl,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl > 0 THEN o.net_pnl ELSE 0 END) AS sum_wins,
                  SUM(CASE WHEN o.status='CLOSED' AND o.net_pnl < 0 THEN -o.net_pnl ELSE 0 END) AS sum_losses
                FROM o
                JOIN decisions_v0 r ON r.decision_id = o.decision_id
                GROUP BY r.market_id
                HAVING closed_count >= ?
                ORDER BY (CAST(wins AS REAL) / closed_count) ASC, sum_net_pnl ASC
                LIMIT ?
                """,
                (min_c, lim),
            ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            closed_count = int(r["closed_count"] or 0)
            wins = int(r["wins"] or 0)
            losses = int(r["losses"] or 0)
            sum_wins = float(r["sum_wins"] or 0.0)
            sum_losses = float(r["sum_losses"] or 0.0)
            win_rate = (wins / closed_count) if closed_count > 0 else None
            profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else None
            out.append(
                {
                    "market_id": r["market_id"],
                    "decisions_total": int(r["decisions_total"] or 0),
                    "closed_count": closed_count,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate,
                    "sum_net_pnl": float(r["sum_net_pnl"] or 0.0),
                    "avg_net_pnl": float(r["avg_net_pnl"] or 0.0) if r["avg_net_pnl"] is not None else 0.0,
                    "profit_factor": profit_factor,
                }
            )
        return out

    def get_tradeability_metrics(self, hours: int = 24) -> Dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))
        since_s = since.isoformat(timespec="seconds")

        with self._repo.conn() as con:
            decision_rows = con.execute(
                """
                SELECT market_id, ts, action, status, COALESCE(reason_json, '') AS reason_json, COALESCE(reason, '') AS reason
                FROM decisions_v0
                WHERE ts >= ?
                ORDER BY ts DESC
                """,
                (since_s,),
            ).fetchall()
            trade_rows = con.execute(
                """
                SELECT DISTINCT market_id
                FROM paper_trades
                WHERE ts >= ?
                  AND side='BUY'
                """,
                (since_s,),
            ).fetchall()

        latest_by_market: Dict[str, Any] = {}
        for r in decision_rows or []:
            mid = r["market_id"]
            if mid and mid not in latest_by_market:
                latest_by_market[mid] = r

        tradeable_markets: set[str] = set()
        blocked_markets: set[str] = set()
        for mid, r in latest_by_market.items():
            reason_json = self._json_loads_safe(r["reason_json"], {})
            flags = reason_json.get("flags", []) if isinstance(reason_json, dict) else []
            reason = (r["reason"] or "").lower()
            is_not_tradeable = (
                (isinstance(reason_json, dict) and reason_json.get("type") == "NOT_TRADEABLE")
                or ("not tradeable" in reason)
                or ("не торгуем" in reason)
                or (isinstance(flags, list) and len(flags) > 0)
            )
            if is_not_tradeable:
                blocked_markets.add(mid)
            else:
                tradeable_markets.add(mid)

        opened_markets = {r["market_id"] for r in trade_rows or [] if r["market_id"]}
        opened_from_tradeable = opened_markets & tradeable_markets
        conversion = (len(opened_from_tradeable) / len(tradeable_markets)) if tradeable_markets else 0.0

        return {
            "window_hours": max(1, int(hours)),
            "tradeable_cases": len(tradeable_markets),
            "blocked_cases": len(blocked_markets),
            "opened_cases": len(opened_markets),
            "opened_from_tradeable": len(opened_from_tradeable),
            "conversion_rate": conversion,
        }

    def get_decision_outcomes(self, limit: int = 200) -> List[Dict[str, Any]]:
        self._repo.ensure_paper_schema()
        lim = max(1, int(limit))
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT
                  decision_id,
                  MIN(ts) AS first_ts,
                  MAX(ts) AS last_ts,
                  SUM(CASE WHEN side='SELL' THEN qty*price ELSE -qty*price END) AS gross_pnl,
                  SUM(COALESCE(fee,0.0)) AS fees_paid,
                  SUM(CASE WHEN side='BUY'  THEN qty ELSE 0 END) AS buy_qty,
                  SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END) AS sell_qty
                FROM paper_trades
                WHERE decision_id IS NOT NULL AND TRIM(decision_id) != ''
                GROUP BY decision_id
                ORDER BY last_ts DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            gross = float(r["gross_pnl"] or 0.0)
            fees = float(r["fees_paid"] or 0.0)
            net = gross - fees
            buy_qty = float(r["buy_qty"] or 0.0)
            sell_qty = float(r["sell_qty"] or 0.0)
            status = "OPEN" if buy_qty > sell_qty else "CLOSED"
            outcome = "OPEN"
            if status == "CLOSED":
                if net > 0:
                    outcome = "WIN"
                elif net < 0:
                    outcome = "LOSS"
                else:
                    outcome = "NEUTRAL"

            duration_sec: float | None = None
            if status == "CLOSED":
                dt_start = _str_to_dt(r["first_ts"])
                dt_end = _str_to_dt(r["last_ts"])
                if dt_start and dt_end:
                    duration_sec = max(0.0, (dt_end - dt_start).total_seconds())

            out.append(
                {
                    "decision_id": r["decision_id"],
                    "first_ts": r["first_ts"],
                    "last_ts": r["last_ts"],
                    "gross_pnl": gross,
                    "fees_paid": fees,
                    "net_pnl": net,
                    "buy_qty": buy_qty,
                    "sell_qty": sell_qty,
                    "status": status,
                    "outcome": outcome,
                    "duration_sec": duration_sec,
                }
            )
        return out

    def get_decision_outcome(self, decision_id: str) -> Optional[Dict[str, Any]]:
        if not decision_id:
            return None
        self._repo.ensure_paper_schema()
        with self._repo.conn() as con:
            r = con.execute(
                """
                SELECT
                  decision_id,
                  MIN(ts) AS first_ts,
                  MAX(ts) AS last_ts,
                  SUM(CASE WHEN side='SELL' THEN qty*price ELSE -qty*price END) AS gross_pnl,
                  SUM(COALESCE(fee,0.0)) AS fees_paid,
                  SUM(CASE WHEN side='BUY'  THEN qty ELSE 0 END) AS buy_qty,
                  SUM(CASE WHEN side='SELL' THEN qty ELSE 0 END) AS sell_qty
                FROM paper_trades
                WHERE decision_id = ?
                GROUP BY decision_id
                """,
                (decision_id,),
            ).fetchone()
        if not r:
            return None
        gross = float(r["gross_pnl"] or 0.0)
        fees = float(r["fees_paid"] or 0.0)
        net = gross - fees
        buy_qty = float(r["buy_qty"] or 0.0)
        sell_qty = float(r["sell_qty"] or 0.0)
        status = "OPEN" if buy_qty > sell_qty else "CLOSED"
        outcome = "OPEN"
        if status == "CLOSED":
            if net > 0:
                outcome = "WIN"
            elif net < 0:
                outcome = "LOSS"
            else:
                outcome = "NEUTRAL"
        duration_sec: float | None = None
        if status == "CLOSED":
            dt_start = _str_to_dt(r["first_ts"])
            dt_end = _str_to_dt(r["last_ts"])
            if dt_start and dt_end:
                duration_sec = max(0.0, (dt_end - dt_start).total_seconds())
        return {
            "decision_id": r["decision_id"],
            "first_ts": r["first_ts"],
            "last_ts": r["last_ts"],
            "gross_pnl": gross,
            "fees_paid": fees,
            "net_pnl": net,
            "buy_qty": buy_qty,
            "sell_qty": sell_qty,
            "status": status,
            "outcome": outcome,
            "duration_sec": duration_sec,
        }

    def get_quality_metrics(self) -> Dict[str, Any]:
        rows = self.get_decision_outcomes(limit=2000)
        closed = [r for r in rows if r.get("outcome") in {"WIN", "LOSS", "NEUTRAL"}]
        closed_count = len(closed)
        if closed_count == 0:
            return {
                "closed_count": 0,
                "win_rate": 0.0,
                "avg_net_pnl": 0.0,
                "profit_factor": None,
                "expectancy": 0.0,
            }
        wins = [r for r in closed if float(r.get("net_pnl") or 0.0) > 0]
        losses = [r for r in closed if float(r.get("net_pnl") or 0.0) < 0]
        win_rate = len(wins) / closed_count if closed_count else 0.0
        avg_net = sum(float(r.get("net_pnl") or 0.0) for r in closed) / closed_count
        sum_wins = sum(float(r.get("net_pnl") or 0.0) for r in wins)
        sum_losses = sum(float(r.get("net_pnl") or 0.0) for r in losses)
        profit_factor = None
        if sum_losses < 0:
            profit_factor = sum_wins / abs(sum_losses) if abs(sum_losses) > 0 else None
        return {
            "closed_count": closed_count,
            "win_rate": win_rate,
            "avg_net_pnl": avg_net,
            "profit_factor": profit_factor,
            "expectancy": avg_net,
        }

    def stats(self) -> dict:
        self._repo.ensure_paper_schema()
        with self._repo.conn() as con:
            row = con.execute(
                """
                SELECT
                    COUNT(*) AS open_positions,
                    COALESCE(SUM(qty * avg_price), 0.0) AS notional_open
                FROM paper_positions
                WHERE status='OPEN'
                """
            ).fetchone()
            group_rows = con.execute(
                """
                SELECT
                    COALESCE(m.group_key, '') AS group_key,
                    COALESCE(SUM(p.qty * p.avg_price), 0.0) AS notional
                FROM paper_positions p
                LEFT JOIN markets m ON m.market_id = p.market_id
                WHERE p.status='OPEN'
                GROUP BY COALESCE(m.group_key, '')
                """
            ).fetchall()

        return {
            "open_positions": int(row["open_positions"]) if row else 0,
            "notional_open": float(row["notional_open"]) if row and row["notional_open"] is not None else 0.0,
            "notional_by_group": {
                (r["group_key"] or ""): float(r["notional"] or 0.0)
                for r in group_rows or []
            },
        }


class PaperQueryRepository:
    """Paper trading query/list operations for UI and reporting."""

    def __init__(self, repo: Any):
        self._repo = repo

    def list_positions(self, limit: int = 200):
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT opened_at, market_id, outcome, qty, avg_price, status
                FROM paper_positions
                ORDER BY opened_at DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [(r["opened_at"], r["market_id"], r["outcome"], r["qty"], r["avg_price"], r["status"]) for r in rows]

    def list_positions_filtered(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        status: str | None = None,
        market_id: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
    ):
        where = []
        params: List[Any] = []
        if status:
            where.append("status = ?")
            params.append(status.upper())
        if market_id:
            where.append("market_id = ?")
            params.append(market_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_map = {
            "opened_at": "opened_at",
            "market": "market_id",
            "outcome": "outcome",
            "qty": "qty",
            "avg_price": "avg_price",
            "status": "status",
        }
        order_col = order_map.get((sort_by or "").lower(), "opened_at")
        order_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
        with self._repo.conn() as con:
            rows = con.execute(
                f"""
                SELECT opened_at, market_id, outcome, qty, avg_price, status
                FROM paper_positions
                {where_sql}
                ORDER BY {order_col} {order_dir}, opened_at DESC
                LIMIT ? OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return [(r["opened_at"], r["market_id"], r["outcome"], r["qty"], r["avg_price"], r["status"]) for r in rows]

    def count_positions_filtered(self, *, status: str | None = None, market_id: str | None = None) -> int:
        where = []
        params: List[Any] = []
        if status:
            where.append("status = ?")
            params.append(status.upper())
        if market_id:
            where.append("market_id = ?")
            params.append(market_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._repo.conn() as con:
            row = con.execute(
                f"SELECT COUNT(*) AS n FROM paper_positions {where_sql}",
                tuple(params),
            ).fetchone()
        return int(row["n"]) if row else 0

    def list_trades(self, limit: int = 200):
        with self._repo.conn() as con:
            rows = con.execute(
                """
                SELECT ts, market_id, outcome, side, qty, price, COALESCE(fee, 0.0) AS fee, COALESCE(note, '') AS note
                FROM paper_trades
                ORDER BY ts DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [
            (r["ts"], r["market_id"], r["outcome"], r["side"], r["qty"], r["price"], r["fee"], r["note"])
            for r in rows
        ]

    def list_trades_filtered(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        side: str | None = None,
        market_id: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
    ):
        where = []
        params: List[Any] = []
        if side:
            where.append("side = ?")
            params.append(side.upper())
        if market_id:
            where.append("market_id = ?")
            params.append(market_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        order_map = {
            "ts": "ts",
            "market": "market_id",
            "outcome": "outcome",
            "side": "side",
            "qty": "qty",
            "price": "price",
        }
        order_col = order_map.get((sort_by or "").lower(), "ts")
        order_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"
        with self._repo.conn() as con:
            rows = con.execute(
                f"""
                SELECT ts, market_id, outcome, side, qty, price, COALESCE(fee, 0.0) AS fee, COALESCE(note, '') AS note
                FROM paper_trades
                {where_sql}
                ORDER BY {order_col} {order_dir}, ts DESC
                LIMIT ? OFFSET ?
                """,
                (*params, int(limit), int(offset)),
            ).fetchall()
        return [
            (r["ts"], r["market_id"], r["outcome"], r["side"], r["qty"], r["price"], r["fee"], r["note"])
            for r in rows
        ]

    def count_trades_filtered(self, *, side: str | None = None, market_id: str | None = None) -> int:
        where = []
        params: List[Any] = []
        if side:
            where.append("side = ?")
            params.append(side.upper())
        if market_id:
            where.append("market_id = ?")
            params.append(market_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._repo.conn() as con:
            row = con.execute(
                f"SELECT COUNT(*) AS n FROM paper_trades {where_sql}",
                tuple(params),
            ).fetchone()
        return int(row["n"]) if row else 0

    def count_positions(self) -> int:
        with self._repo.conn() as con:
            row = con.execute("SELECT COUNT(*) AS n FROM paper_positions").fetchone()
        return int(row["n"]) if row else 0

    def has_open_position(self, market_id: str) -> bool:
        self._repo.ensure_paper_schema()
        with self._repo.conn() as con:
            row = con.execute(
                """
                SELECT 1
                FROM paper_positions
                WHERE market_id = ? AND status='OPEN'
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        return bool(row)


class PaperExecutionRepository:
    """Paper position mutating operations (buy/close)."""

    def __init__(self, repo: Any):
        self._repo = repo

    @staticmethod
    def _fee_rate() -> float:
        try:
            _cfg, runtime = load_runtime_config()
            return float(getattr(runtime, "taker_fee_rate", 0.0) or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _slippage_rate() -> float:
        try:
            _cfg, runtime = load_runtime_config()
            return float(getattr(runtime, "slippage_rate", 0.0) or 0.0)
        except Exception:
            return 0.0

    def buy(
        self,
        run_id: str,
        market_id: str,
        outcome: str,
        qty: float,
        price: float,
        note: str = "",
        decision_id: str | None = None,
        meta: dict | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        now_ts = datetime.now(timezone.utc).timestamp()
        trade_id = str(uuid.uuid4())
        fee_rate = self._fee_rate()
        slip = self._slippage_rate()
        exec_price = float(price) * (1.0 + slip) if float(price) > 0 else float(price)
        fee = float(qty) * float(exec_price) * fee_rate
        explain_type = None
        explain_edge = None
        explain_score = None
        if isinstance(meta, dict):
            explain_type = meta.get("explain_type")
            explain_edge = meta.get("explain_edge_pct")
            explain_score = meta.get("explain_score")
        with self._repo.conn() as con:
            con.execute(
                """
                INSERT INTO paper_trades(trade_id, ts, run_id, market_id, decision_id, outcome, side, qty, price, fee, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    now,
                    run_id,
                    market_id,
                    decision_id,
                    outcome,
                    "BUY",
                    float(qty),
                    float(exec_price),
                    float(fee),
                    note,
                ),
            )
            row = con.execute(
                """
                SELECT position_id, qty, avg_price, entry_mid, best_mid_seen, worst_mid_seen
                FROM paper_positions
                WHERE market_id = ?
                  AND outcome = ?
                  AND status = 'OPEN' LIMIT 1
                """,
                (market_id, outcome),
            ).fetchone()

            if row:
                pos_id = row["position_id"]
                old_qty = float(row["qty"])
                old_avg = float(row["avg_price"])
                new_qty = old_qty + float(qty)
                new_avg = (old_qty * old_avg + float(qty) * float(exec_price)) / new_qty if new_qty > 0 else float(exec_price)
                con.execute(
                    """
                    UPDATE paper_positions
                    SET qty=?,
                        avg_price=?,
                        entry_mid=COALESCE(entry_mid, ?),
                        best_mid_seen=COALESCE(best_mid_seen, ?),
                        worst_mid_seen=COALESCE(worst_mid_seen, ?),
                        explain_type=COALESCE(explain_type, ?),
                        explain_edge_pct=COALESCE(explain_edge_pct, ?),
                        explain_score=COALESCE(explain_score, ?),
                        opened_ts=COALESCE(opened_ts, ?)
                    WHERE position_id=?
                    """,
                    (
                        new_qty,
                        new_avg,
                        float(exec_price),
                        float(exec_price),
                        float(exec_price),
                        explain_type,
                        explain_edge,
                        explain_score,
                        float(now_ts),
                        pos_id,
                    ),
                )
            else:
                pos_id = str(uuid.uuid4())
                con.execute(
                    """
                    INSERT INTO paper_positions(position_id, opened_at, run_id, market_id, outcome, qty, avg_price,
                                                entry_mid, best_mid_seen, worst_mid_seen, explain_type, explain_edge_pct,
                                                explain_score, opened_ts, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pos_id,
                        now,
                        run_id,
                        market_id,
                        outcome,
                        float(qty),
                        float(exec_price),
                        float(exec_price),
                        float(exec_price),
                        float(exec_price),
                        explain_type,
                        explain_edge,
                        explain_score,
                        float(now_ts),
                        "OPEN",
                    ),
                )

    def close(
        self,
        run_id: str,
        market_id: str,
        outcome: str,
        price: float,
        qty: float | None = None,
        note: str = "",
        decision_id: str | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        now_ts = datetime.now(timezone.utc).timestamp()
        trade_id = str(uuid.uuid4())
        if qty is not None and float(qty) <= 0:
            return {"ok": False, "error": "BAD_QTY", "closed_qty": 0.0, "remaining_qty": None}
        with self._repo.conn() as con:
            row = con.execute(
                """
                SELECT position_id, qty, entry_mid, best_mid_seen, worst_mid_seen
                FROM paper_positions
                WHERE market_id = ?
                  AND outcome = ?
                  AND status = 'OPEN' LIMIT 1
                """,
                (market_id, outcome),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "NO_POSITION", "closed_qty": 0.0, "remaining_qty": 0.0}
            pos_qty = float(row["qty"])
            if qty is None:
                close_qty = pos_qty
            else:
                close_qty = min(pos_qty, float(qty))
            if close_qty <= 0:
                return {"ok": False, "error": "BAD_QTY", "closed_qty": 0.0, "remaining_qty": pos_qty}
            fee_rate = self._fee_rate()
            slip = self._slippage_rate()
            exec_price = float(price) * (1.0 - slip) if float(price) > 0 else float(price)
            fee = float(close_qty) * float(exec_price) * fee_rate
            con.execute(
                """
                INSERT INTO paper_trades(trade_id, ts, run_id, market_id, decision_id, outcome, side, qty, price, fee, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    now,
                    run_id,
                    market_id,
                    decision_id,
                    outcome,
                    "SELL",
                    float(close_qty),
                    float(exec_price),
                    float(fee),
                    note,
                ),
            )
            if close_qty >= pos_qty:
                entry_mid = float(row["entry_mid"]) if row["entry_mid"] is not None else float(exec_price)
                best_mid = float(row["best_mid_seen"]) if row["best_mid_seen"] is not None else entry_mid
                worst_mid = float(row["worst_mid_seen"]) if row["worst_mid_seen"] is not None else entry_mid
                exit_mid = float(exec_price)
                best_mid = max(best_mid, exit_mid)
                worst_mid = min(worst_mid, exit_mid)
                if str(outcome).upper() == "NO":
                    realized = (entry_mid - exit_mid) / entry_mid * 100.0 if entry_mid else 0.0
                    best_runup = (entry_mid - worst_mid) / entry_mid * 100.0 if entry_mid else 0.0
                    worst_draw = (entry_mid - best_mid) / entry_mid * 100.0 if entry_mid else 0.0
                else:
                    realized = (exit_mid - entry_mid) / entry_mid * 100.0 if entry_mid else 0.0
                    best_runup = (best_mid - entry_mid) / entry_mid * 100.0 if entry_mid else 0.0
                    worst_draw = (worst_mid - entry_mid) / entry_mid * 100.0 if entry_mid else 0.0
                con.execute(
                    """
                    UPDATE paper_positions
                    SET status='CLOSED',
                        exit_mid=?,
                        realized_pnl_pct=?,
                        best_runup_pct=?,
                        worst_drawdown_pct=?,
                        best_mid_seen=?,
                        worst_mid_seen=?,
                        closed_ts=?
                    WHERE position_id=?
                    """,
                    (exit_mid, realized, best_runup, worst_draw, best_mid, worst_mid, float(now_ts), row["position_id"]),
                )
                return {
                    "ok": True,
                    "error": None,
                    "closed_qty": float(close_qty),
                    "remaining_qty": 0.0,
                }
            else:
                remain = max(0.0, pos_qty - close_qty)
                con.execute(
                    "UPDATE paper_positions SET qty=? WHERE position_id=?",
                    (float(remain), row["position_id"]),
                )
                return {
                    "ok": True,
                    "error": None,
                    "closed_qty": float(close_qty),
                    "remaining_qty": float(remain),
                }


class ClusterRepository:
    """Cluster/graph-oriented read models."""

    def __init__(self, repo: Any):
        self._repo = repo

    def get_cluster_details(self, group_key: str, limit_markets: int = 200) -> dict:
        return self.get_cluster_details_v2(group_key, limit_markets=limit_markets)

    def get_cluster_details_v2(
        self,
        group_key: str,
        *,
        limit_markets: int = 200,
        signals_window_minutes: int = 240,
        selected_market_id: Optional[str] = None,
        neighbor_sort: str = "closest",
    ) -> dict:
        markets = self._repo.list_markets_by_group(group_key, limit=limit_markets)
        if not markets:
            return {
                "group_key": group_key,
                "markets": [],
                "latest": {},
                "market_metrics": {},
                "cluster_stats": {
                    "markets_count": 0,
                    "markets_with_quotes": 0,
                    "min_spread": None,
                    "median_liquidity": None,
                    "last_update_ts": None,
                    "edges_count": 0,
                    "connected_markets": 0,
                },
                "edges": [],
                "neighbors": [],
            }

        market_ids = [m.market_id for m in markets]
        market_id_set = set(market_ids)
        qmarks = ",".join(["?"] * len(market_ids))

        latest: dict[str, dict[str, dict]] = {}
        with self._repo.conn() as con:
            rows = con.execute(
                f"""
                SELECT market_id, outcome, mid, spread, liquidity, ts
                FROM (
                    SELECT market_id, outcome, mid, spread, liquidity, ts,
                           ROW_NUMBER() OVER (PARTITION BY market_id, outcome ORDER BY ts DESC) AS rn
                    FROM snapshots
                    WHERE market_id IN ({qmarks})
                )
                WHERE rn=1 AND outcome IN ('YES','NO')
                """,
                tuple(market_ids),
            ).fetchall()

            for r in rows or []:
                mid = r[0]
                outc = r[1]
                latest.setdefault(mid, {})[outc] = {
                    "mid": r[2],
                    "spread": r[3],
                    "liquidity": r[4],
                    "ts": r[5],
                }

            since = datetime.now(timezone.utc) - timedelta(minutes=int(signals_window_minutes))
            sig_rows = con.execute(
                """
                SELECT ts, kind, scope_pair_key, features_json, claim_json, explain_short
                FROM signals
                WHERE scope_group_key = ?
                  AND ts >= ?
                ORDER BY ts DESC
                LIMIT 3000
                """,
                (group_key, _dt_to_str(since)),
            ).fetchall()

        def _f(v: Any) -> Optional[float]:
            try:
                if v is None:
                    return None
                return float(v)
            except (ValueError, TypeError):
                return None

        def _extract_pair_ids(scope_pair_key: Optional[str], claim_raw: str) -> Optional[tuple[str, str]]:
            def _ok(a: str, b: str) -> Optional[tuple[str, str]]:
                if not a or not b or a == b:
                    return None
                if a not in market_id_set or b not in market_id_set:
                    return None
                return (a, b) if a < b else (b, a)

            if scope_pair_key:
                parts = [x.strip() for x in str(scope_pair_key).split("::") if x.strip()]
                if len(parts) >= 2:
                    p = _ok(parts[0], parts[1])
                    if p is not None:
                        return p

            try:
                claim = json.loads(claim_raw) if claim_raw else {}
            except Exception:
                claim = {}

            candidates: list[tuple[Optional[str], Optional[str]]] = [
                (claim.get("market_a", {}).get("id"), claim.get("market_b", {}).get("id")),
                (claim.get("low_market", {}).get("id"), claim.get("high_market", {}).get("id")),
                (claim.get("left_market", {}).get("id"), claim.get("right_market", {}).get("id")),
            ]
            pair_arr = claim.get("pair")
            if isinstance(pair_arr, (list, tuple)) and len(pair_arr) >= 2:
                candidates.append((str(pair_arr[0]), str(pair_arr[1])))
            market_ids_arr = claim.get("market_ids")
            if isinstance(market_ids_arr, (list, tuple)) and len(market_ids_arr) >= 2:
                candidates.append((str(market_ids_arr[0]), str(market_ids_arr[1])))

            for a, b in candidates:
                if a is None or b is None:
                    continue
                p = _ok(str(a), str(b))
                if p is not None:
                    return p
            return None

        edges_map: dict[tuple[str, str], dict[str, Any]] = {}
        for r in sig_rows or []:
            ts = r["ts"]
            kind = str(r["kind"] or "")
            pair = _extract_pair_ids(r["scope_pair_key"], r["claim_json"])
            if pair is None:
                continue

            try:
                features = json.loads(r["features_json"] or "{}")
            except Exception:
                features = {}
            try:
                claim = json.loads(r["claim_json"] or "{}")
            except Exception:
                claim = {}

            similarity = _f(features.get("similarity"))
            if similarity is None:
                similarity = _f(claim.get("similarity"))
            if similarity is None and kind == "PAIR_ARB":
                similarity = 0.15

            violation = _f(features.get("violation"))
            if violation is None:
                vio_obj = claim.get("violation", {})
                if isinstance(vio_obj, dict):
                    violation = _f(vio_obj.get("violation"))
            if violation is None and kind in {"ANOMALY", "IMPLICATION", "RISK_CONSTRAINT"}:
                violation = 0.05

            e = edges_map.setdefault(
                pair,
                {
                    "market_a": pair[0],
                    "market_b": pair[1],
                    "signal_count": 0,
                    "kind_counts": {},
                    "closest_score": 0.0,
                    "conflict_score": 0.0,
                    "last_ts": "",
                    "sample": "",
                },
            )
            e["signal_count"] += 1
            e["kind_counts"][kind] = int(e["kind_counts"].get(kind, 0)) + 1
            if similarity is not None:
                e["closest_score"] = max(float(e["closest_score"]), float(similarity))
            if violation is not None:
                e["conflict_score"] = max(float(e["conflict_score"]), float(violation))
            if ts and ts >= str(e["last_ts"]):
                e["last_ts"] = ts
                e["sample"] = r["explain_short"] or ""

        edges = list(edges_map.values())
        edges.sort(
            key=lambda x: (
                float(x.get("conflict_score") or 0.0),
                float(x.get("closest_score") or 0.0),
                int(x.get("signal_count") or 0),
            ),
            reverse=True,
        )

        market_metrics: dict[str, dict[str, Any]] = {}
        spreads: list[float] = []
        liquidities: list[float] = []
        last_updates: list[str] = []
        for m in markets:
            l = latest.get(m.market_id, {})
            y = l.get("YES", {})
            n = l.get("NO", {})

            yes_mid = _f(y.get("mid"))
            no_mid = _f(n.get("mid"))
            yes_sp = _f(y.get("spread"))
            no_sp = _f(n.get("spread"))
            yes_lq = _f(y.get("liquidity"))
            no_lq = _f(n.get("liquidity"))
            yes_ts = str(y.get("ts") or "")
            no_ts = str(n.get("ts") or "")

            spread = None
            vals_sp = [x for x in (yes_sp, no_sp) if x is not None]
            if vals_sp:
                spread = max(vals_sp)
                spreads.append(spread)

            liq = None
            vals_lq = [x for x in (yes_lq, no_lq) if x is not None]
            if vals_lq:
                liq = min(vals_lq)
                liquidities.append(liq)

            last_ts = max(yes_ts, no_ts)
            if last_ts:
                last_updates.append(last_ts)

            sum_mid = None
            if yes_mid is not None and no_mid is not None:
                sum_mid = yes_mid + no_mid

            market_metrics[m.market_id] = {
                "yes_mid": yes_mid,
                "no_mid": no_mid,
                "sum_mid": sum_mid,
                "spread": spread,
                "liquidity": liq,
                "last_ts": last_ts or None,
            }

        connected = set()
        for e in edges:
            connected.add(e["market_a"])
            connected.add(e["market_b"])

        cluster_stats = {
            "markets_count": len(markets),
            "markets_with_quotes": sum(1 for _, mm in market_metrics.items() if mm.get("last_ts")),
            "min_spread": min(spreads) if spreads else None,
            "median_liquidity": float(median(liquidities)) if liquidities else None,
            "last_update_ts": max(last_updates) if last_updates else None,
            "edges_count": len(edges),
            "connected_markets": len(connected),
        }

        neighbors: list[dict[str, Any]] = []
        if selected_market_id and selected_market_id in market_id_set:
            by_id = {m.market_id: m for m in markets}
            score_map: dict[str, dict[str, Any]] = {}
            for e in edges:
                a = e["market_a"]
                b = e["market_b"]
                if selected_market_id not in (a, b):
                    continue
                other = b if a == selected_market_id else a
                st = score_map.setdefault(
                    other,
                    {"closest_score": 0.0, "conflict_score": 0.0, "signal_count": 0, "kind_counts": {}, "last_ts": ""},
                )
                st["closest_score"] = max(float(st["closest_score"]), float(e.get("closest_score") or 0.0))
                st["conflict_score"] = max(float(st["conflict_score"]), float(e.get("conflict_score") or 0.0))
                st["signal_count"] += int(e.get("signal_count") or 0)
                for kind, cnt in (e.get("kind_counts") or {}).items():
                    st["kind_counts"][kind] = int(st["kind_counts"].get(kind, 0)) + int(cnt)
                st["last_ts"] = max(str(st["last_ts"]), str(e.get("last_ts") or ""))

            for mid, st in score_map.items():
                m = by_id.get(mid)
                if m is None:
                    continue
                mm = market_metrics.get(mid, {})
                neighbors.append(
                    {
                        "market_id": mid,
                        "slug": m.slug,
                        "title": m.title,
                        "closest_score": float(st["closest_score"]),
                        "conflict_score": float(st["conflict_score"]),
                        "signal_count": int(st["signal_count"]),
                        "kind_counts": st["kind_counts"],
                        "last_ts": st["last_ts"] or mm.get("last_ts"),
                    }
                )

            mode = (neighbor_sort or "closest").strip().lower()
            if mode == "conflict":
                neighbors.sort(
                    key=lambda x: (x["conflict_score"], x["signal_count"], x["closest_score"]),
                    reverse=True,
                )
            else:
                neighbors.sort(
                    key=lambda x: (x["closest_score"], x["signal_count"], x["conflict_score"]),
                    reverse=True,
                )

        return {
            "group_key": group_key,
            "markets": markets,
            "latest": latest,
            "market_metrics": market_metrics,
            "cluster_stats": cluster_stats,
            "edges": edges,
            "neighbors": neighbors,
            "selected_market_id": selected_market_id,
            "neighbor_sort": neighbor_sort,
        }
