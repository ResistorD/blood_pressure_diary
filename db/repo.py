# polysyndicate/db/repo.py
from __future__ import annotations

import sqlite3
import os
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from domain.models import Decision, Market, Run, Signal, Snapshot
from db.repository_modules import (
    DeprioritizeRepository,
    DecisionRepository,
    EventsRepository,
    ClusterRepository,
    MarketRepository,
    PaperAnalyticsRepository,
    PaperExecutionRepository,
    PaperQueryRepository,
    PaperRepository,
    ReadModelRepository,
    RunRepository,
    SignalRepository,
    SnapshotRepository,
    SettingsRepository,
)
from utils.logging import get_logger, warn_exc

logger = get_logger("db.repo")


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") if dt else None


class _WriteBuffer:
    def __init__(self, repo: "Repo", flush_sec: float = 3.0, max_ops: int = 2000, batch_size: int = 300, max_batches_per_flush: int = 3):
        self._repo = repo
        self._flush_sec = float(flush_sec)
        self._max_ops = int(max_ops)
        self._batch_size = int(batch_size)
        self._max_batches_per_flush = int(max_batches_per_flush)
        self._ops: List[callable] = []
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()

    def set_flush_sec(self, flush_sec: float) -> None:
        try:
            self._flush_sec = float(flush_sec)
        except Exception:
            self._flush_sec = 0.0

    def enqueue(self, op: callable) -> None:
        if self._flush_sec <= 0:
            self._execute_now(op)
            return
        do_flush = False
        with self._lock:
            self._ops.append(op)
            if self._max_ops > 0 and len(self._ops) >= self._max_ops:
                do_flush = True
        if do_flush:
            try:
                self.flush()
            except Exception as e:
                logger.warning("write-behind flush failed on enqueue: %s", e, exc_info=True)

    def flush_if_due(self) -> None:
        if self._flush_sec <= 0:
            self.flush()
            return
        if (time.monotonic() - self._last_flush) >= self._flush_sec:
            self.flush()

    def flush(self) -> None:
        batches_done = 0
        while True:
            with self._lock:
                if not self._ops:
                    self._last_flush = time.monotonic()
                    return
                batch = self._ops[: self._batch_size]
                self._ops = self._ops[self._batch_size :]
            exc_to_raise = None
            try:
                with self._repo.conn() as con:
                    try:
                        con.execute("BEGIN")
                        for op in batch:
                            op(con)
                        con.execute("COMMIT")
                    except Exception as e:
                        try:
                            con.execute("ROLLBACK")
                        except Exception:
                            pass  # connection may already be in a clean state
                        exc_to_raise = e
            except Exception as e:
                exc_to_raise = e
            if exc_to_raise is not None:
                with self._lock:
                    self._ops = batch + self._ops
                raise exc_to_raise
            self._last_flush = time.monotonic()
            batches_done += 1
            if self._max_batches_per_flush > 0 and batches_done >= self._max_batches_per_flush:
                return

    def _execute_now(self, op: callable) -> None:
        with self._repo.conn() as con:
            op(con)


class Repo:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._thread_local = threading.local()
        self._write_buffer = _WriteBuffer(self, flush_sec=3.0)
        self._events_schema_ready = False
        # Modular repositories (stage 1): keep legacy API while exposing narrow SRP-oriented modules.
        self.markets = MarketRepository(self)
        self.runs = RunRepository(self)
        self.snapshots = SnapshotRepository(self)
        self.signals = SignalRepository(self)
        self.decisions = DecisionRepository(self)
        self.paper = PaperRepository(self)
        self.paper_analytics = PaperAnalyticsRepository(self)
        self.paper_queries = PaperQueryRepository(self)
        self.paper_exec = PaperExecutionRepository(self)
        self.events = EventsRepository(self)
        self.settings = SettingsRepository(self)
        self.deprioritize = DeprioritizeRepository(self)
        self.read_models = ReadModelRepository(self)
        self.clusters = ClusterRepository(self)
        self.deprioritize_mode = (os.getenv("PS_DEPRIORITIZE_MODE") or os.getenv("DEPRIORITIZE_MODE") or "ui").strip().lower()
        try:
            self.deprioritize_min_weight = float(
                os.getenv("PS_DEPRIORITIZE_MIN_WEIGHT") or os.getenv("DEPRIORITIZE_MIN_WEIGHT") or 0.05
            )
        except Exception:
            warn_exc(logger, "invalid deprioritize_min_weight, using default")
            self.deprioritize_min_weight = 0.05
        self._deprioritize_log_last: dict[tuple[str, str], float] = {}
        self._deprioritize_log_ttl_sec = 600.0

    @contextmanager
    def conn(self) -> sqlite3.Connection:
        con = getattr(self._thread_local, "con", None)
        if con is not None:
            try:
                con.execute("SELECT 1")
            except Exception:
                try:
                    con.close()
                except Exception:
                    pass
                con = None
        if con is None:
            con = sqlite3.connect(self.db_path, timeout=30, isolation_level=None, check_same_thread=False)
            con.row_factory = sqlite3.Row
            # Concurrency/perf settings are applied once per thread-local connection.
            con.execute("PRAGMA busy_timeout=2000;")
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("PRAGMA synchronous=NORMAL;")
            con.execute("PRAGMA temp_store=MEMORY;")
            con.execute("PRAGMA cache_size=-65536;")
            con.execute("PRAGMA wal_autocheckpoint=20000;")
            con.execute("PRAGMA foreign_keys=ON;")
            self._thread_local.con = con
        try:
            yield con
        finally:
            pass

    def set_flush_sec(self, flush_sec: float) -> None:
        if self._write_buffer:
            self._write_buffer.set_flush_sec(flush_sec)

    def enqueue_write(self, op: callable) -> None:
        if self._write_buffer:
            self._write_buffer.enqueue(op)
        else:
            with self.conn() as con:
                op(con)

    def flush_if_due(self) -> None:
        if self._write_buffer:
            self._write_buffer.flush_if_due()

    def flush_writes(self) -> None:
        if self._write_buffer:
            self._write_buffer.flush()

    def init_schema(self, schema_sql_path: str) -> None:
        with open(schema_sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
        with self.conn() as con:
            con.executescript(sql)

        # runtime expectations (idempotent)
        self.ensure_settings_schema()
        self.ensure_decisions_schema()
        self.ensure_decisions_v0_schema()
        self.ensure_paper_schema()
        self.ensure_paper_queue_schema()
        self.ensure_events_schema()
        self.ensure_deprioritize_schema()
        self.ensure_performance_indexes()

        # markets/snapshots/signals might be older schema.sql: ensure columns we rely on
        self.ensure_markets_columns()
        self.ensure_signals_columns()
        self.ensure_snapshots_columns()

    def ensure_performance_indexes(self) -> None:
        """Idempotent secondary indexes for hot query paths."""
        with self.conn() as con:
            for sql in (
                "CREATE INDEX IF NOT EXISTS idx_snapshots_market_ts ON snapshots(market_id, ts DESC)",
                "CREATE INDEX IF NOT EXISTS idx_signals_market_ts ON signals(scope_market_id, ts DESC)",
                "CREATE INDEX IF NOT EXISTS idx_signals_group_ts ON signals(scope_group_key, ts DESC)",
                "CREATE INDEX IF NOT EXISTS idx_paper_trades_market_ts ON paper_trades(market_id, ts DESC)",
                "CREATE INDEX IF NOT EXISTS idx_events_component_ts ON events_log(component, ts DESC)",
            ):
                try:
                    con.execute(sql)
                except Exception:
                    warn_exc(logger, "ensure_performance_indexes failed", sql=sql)

    # ---------------------------
    # schema helpers
    # ---------------------------

    def ensure_paper_queue_schema(self) -> None:
        """
        Ensure paper_queue exists AND is upgraded to the new format.

        Old format (v1):
          paper_queue(command_id, ts, run_id, market_id, action, payload_json, status, attempts, error, updated_ts)

        New format (v2) expected by reconcile + paper_executor:
          paper_queue(command_id, created_at, run_id, market_id, outcome, cmd, qty, price_mode, source_decision_id,
                     status, attempts, error, executed_at)

        We upgrade in-place via ALTER TABLE and backfill created_at from ts when present.
        """
        with self.conn() as con:
            # 1) Create base table if missing (new format)
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_queue
                (
                    command_id
                    TEXT
                    PRIMARY
                    KEY,
                    created_at
                    TEXT
                    NOT
                    NULL,
                    run_id
                    TEXT
                    NOT
                    NULL,
                    market_id
                    TEXT
                    NOT
                    NULL,
                    outcome
                    TEXT
                    NOT
                    NULL,
                    cmd
                    TEXT
                    NOT
                    NULL,
                    qty
                    REAL
                    NOT
                    NULL,
                    price_mode
                    TEXT
                    NOT
                    NULL,
                    source_decision_id
                    TEXT
                    NOT
                    NULL,

                    status
                    TEXT
                    NOT
                    NULL
                    DEFAULT
                    'PENDING',
                    attempts
                    INTEGER
                    NOT
                    NULL
                    DEFAULT
                    0,
                    error
                    TEXT,
                    executed_at
                    TEXT
                )
                """
            )

            # 2) Detect existing columns (in case this table was created in old format)
            cols = [r[1] for r in con.execute("PRAGMA table_info(paper_queue)").fetchall()]

            def add_col(name: str, ddl: str) -> None:
                if name not in cols:
                    con.execute(f"ALTER TABLE paper_queue ADD COLUMN {ddl}")
                    cols.append(name)

            # Old table may have `ts`, `action`, `payload_json`, `updated_ts`.
            # We keep them if present, but upgrade to v2 columns.
            add_col("created_at", "created_at TEXT")
            add_col("outcome", "outcome TEXT")
            add_col("cmd", "cmd TEXT")
            add_col("qty", "qty REAL")
            add_col("price_mode", "price_mode TEXT")
            add_col("source_decision_id", "source_decision_id TEXT")
            add_col("executed_at", "executed_at TEXT")

            # 3) Backfill created_at from ts if old column exists
            if "ts" in cols:
                con.execute(
                    """
                    UPDATE paper_queue
                    SET created_at = COALESCE(created_at, ts)
                    WHERE created_at IS NULL
                    """
                )

            # 4) Backfill cmd from action if old column exists
            if "action" in cols:
                con.execute(
                    """
                    UPDATE paper_queue
                    SET cmd = COALESCE(cmd, action)
                    WHERE cmd IS NULL
                    """
                )

            # 5) Ensure NOT NULL-ish defaults for new columns for old rows (best-effort)
            # We can't add NOT NULL constraints via ALTER easily, so we just fill empties.
            con.execute("UPDATE paper_queue SET outcome = COALESCE(outcome, 'YES') WHERE outcome IS NULL")
            con.execute("UPDATE paper_queue SET qty = COALESCE(qty, 1.0) WHERE qty IS NULL")
            con.execute("UPDATE paper_queue SET price_mode = COALESCE(price_mode, 'MID') WHERE price_mode IS NULL")
            con.execute(
                "UPDATE paper_queue SET source_decision_id = COALESCE(source_decision_id, '') WHERE source_decision_id IS NULL")
            con.execute("UPDATE paper_queue SET created_at = COALESCE(created_at, '') WHERE created_at IS NULL")

            # 6) Indexes: only on columns that exist
            con.execute("CREATE INDEX IF NOT EXISTS idx_paperq_status ON paper_queue(status)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_paperq_market ON paper_queue(market_id)")
            if "created_at" in cols:
                con.execute("CREATE INDEX IF NOT EXISTS idx_paperq_created ON paper_queue(created_at)")

    def ensure_deprioritize_schema(self) -> None:
        with self.conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS deprioritize_rules
                (
                    id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    scope
                    TEXT
                    NOT
                    NULL,
                    key
                    TEXT
                    NOT
                    NULL,
                    weight
                    REAL
                    NOT
                    NULL
                    DEFAULT
                    0.5,
                    reason
                    TEXT
                    NOT
                    NULL
                    DEFAULT
                    '',
                    created_ts
                    TEXT
                    NOT
                    NULL,
                    expires_ts
                    TEXT,
                    is_enabled
                    INTEGER
                    NOT
                    NULL
                    DEFAULT
                    1
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_deprioritize_rules_scope_key "
                "ON deprioritize_rules(scope, key)"
            )

    def ensure_events_schema(self) -> None:
        with self.conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS events_log
                (
                    log_id
                    INTEGER
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    ts
                    TEXT
                    NOT
                    NULL,
                    level
                    TEXT
                    NOT
                    NULL,
                    component
                    TEXT
                    NOT
                    NULL,
                    message
                    TEXT
                    NOT
                    NULL,
                    payload_json
                    TEXT
                    NOT
                    NULL
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events_log(ts DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_events_component_ts ON events_log(component, ts DESC)")

    def ensure_markets_columns(self) -> None:
        # Ensure markets has what we use in code (group_key etc).
        # Also: if someone created markets without raw_json — we won't require it.
        with self.conn() as con:
            cols = [r[1] for r in con.execute("PRAGMA table_info(markets)").fetchall()]

            def add_col(name: str, ddl: str) -> None:
                if name not in cols:
                    con.execute(f"ALTER TABLE markets ADD COLUMN {ddl}")

            add_col("group_key", "group_key TEXT")
            add_col("rules_hash", "rules_hash TEXT")
            add_col("close_time", "close_time TEXT")
            add_col("raw_json", "raw_json TEXT NOT NULL DEFAULT ''")

            # Backfill missing group_key for existing rows (best-effort).
            try:
                con.execute(
                    """
                    UPDATE markets
                    SET group_key =
                        CASE
                            WHEN group_key IS NOT NULL AND TRIM(group_key) <> '' THEN group_key
                            WHEN slug IS NOT NULL AND TRIM(slug) <> '' AND close_time IS NOT NULL THEN substr(slug, 1, 80) || '|' || substr(close_time, 1, 7)
                            WHEN slug IS NOT NULL AND TRIM(slug) <> '' THEN substr(slug, 1, 80) || '|na'
                            ELSE COALESCE(group_key, 'unknown|na')
                        END
                    WHERE group_key IS NULL OR TRIM(group_key) = ''
                    """
                )
            except Exception:
                warn_exc(logger, "ensure_markets_columns backfill failed")

    def ensure_signals_columns(self) -> None:
        # Ensure signals has columns used by UI and read models.
        with self.conn() as con:
            cols = [r[1] for r in con.execute("PRAGMA table_info(signals)").fetchall()]

            def add_col(name: str, ddl: str) -> None:
                if name not in cols:
                    con.execute(f"ALTER TABLE signals ADD COLUMN {ddl}")
                    cols.append(name)

            add_col("signal_id", "signal_id TEXT")
            add_col("ts", "ts TEXT")
            add_col("run_id", "run_id TEXT")
            add_col("agent_id", "agent_id TEXT")
            add_col("kind", "kind TEXT")
            add_col("scope_market_id", "scope_market_id TEXT")
            add_col("scope_group_key", "scope_group_key TEXT")
            add_col("scope_pair_key", "scope_pair_key TEXT")
            add_col("features_json", "features_json TEXT")
            add_col("claim_json", "claim_json TEXT")
            add_col("candidates_json", "candidates_json TEXT")
            add_col("explain_short", "explain_short TEXT")
            add_col("explain_long", "explain_long TEXT")

    def ensure_snapshots_columns(self) -> None:
        # Ensure snapshots has columns used by UI and analytics.
        with self.conn() as con:
            cols = [r[1] for r in con.execute("PRAGMA table_info(snapshots)").fetchall()]

            def add_col(name: str, ddl: str) -> None:
                if name not in cols:
                    con.execute(f"ALTER TABLE snapshots ADD COLUMN {ddl}")
                    cols.append(name)

            add_col("ts", "ts TEXT")
            add_col("market_id", "market_id TEXT")
            add_col("outcome", "outcome TEXT")
            add_col("bid", "bid REAL")
            add_col("ask", "ask REAL")
            add_col("mid", "mid REAL")
            add_col("spread", "spread REAL")
            add_col("liquidity", "liquidity REAL")
            add_col("volume", "volume REAL")
            add_col("implied_prob", "implied_prob REAL")
            add_col("updated_at", "updated_at TEXT")  # wall-clock insert time for freshness tracking
            # Index for fast MAX(updated_at) freshness queries
            try:
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_snapshots_updated_at ON snapshots(updated_at DESC)"
                )
            except Exception:
                pass

    def ensure_settings_schema(self) -> None:
        with self.conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS settings
                (
                    key
                    TEXT
                    PRIMARY
                    KEY,
                    value
                    TEXT
                    NOT
                    NULL,
                    updated_at
                    TEXT
                    NOT
                    NULL
                )
                """
            )
            con.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?,?,?)",
                ("paused", "0", _dt_to_str(datetime.now(timezone.utc)) or ""),
            )

    def ensure_decisions_schema(self) -> None:
        # Domain decisions (Decision model)
        with self.conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions
                (
                    decision_id
                    TEXT
                    PRIMARY
                    KEY,
                    ts
                    TEXT
                    NOT
                    NULL,
                    run_id
                    TEXT
                    NOT
                    NULL,
                    type
                    TEXT
                    NOT
                    NULL,
                    plan_json
                    TEXT
                    NOT
                    NULL,
                    risk_json
                    TEXT
                    NOT
                    NULL,
                    next_review_at
                    TEXT,
                    explain_short
                    TEXT,
                    explain_long
                    TEXT
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_signals
                (
                    decision_id
                    TEXT
                    NOT
                    NULL,
                    signal_id
                    TEXT
                    NOT
                    NULL,
                    PRIMARY
                    KEY
                (
                    decision_id,
                    signal_id
                )
                    )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_decision_signals_sid ON decision_signals(signal_id)")

    def ensure_decisions_v0_schema(self) -> None:
        # Operator decisions (old/simple table)
        with self.conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions_v0
                (
                    decision_id
                    TEXT
                    PRIMARY
                    KEY,
                    ts
                    TEXT
                    NOT
                    NULL,
                    run_id
                    TEXT
                    NOT
                    NULL,
                    market_id
                    TEXT
                    NOT
                    NULL,
                    action
                    TEXT
                    NOT
                    NULL,
                    status
                    TEXT
                    NOT
                    NULL,
                    reason
                    TEXT,
                    reason_json
                    TEXT,
                    payload_json
                    TEXT
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_v0_ts ON decisions_v0(ts DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_decisions_v0_market_ts ON decisions_v0(market_id, ts DESC)")

            # Backward-compatible: if table existed before reason_json was added.
            try:
                cols = [r[1] for r in con.execute("PRAGMA table_info(decisions_v0)").fetchall()]
                if "reason_json" not in cols:
                    con.execute("ALTER TABLE decisions_v0 ADD COLUMN reason_json TEXT")
            except Exception:
                warn_exc(logger, "ensure_decisions_v0_schema reason_json add failed")

            # Idempotent backfill: legacy string reason -> reason_json
            try:
                con.execute(
                    """
                    UPDATE decisions_v0
                    SET reason_json = json_object('type','LEGACY','raw',COALESCE(reason,''))
                    WHERE (reason_json IS NULL OR TRIM(reason_json) = '')
                      AND (reason IS NOT NULL AND TRIM(reason) <> '')
                    """
                )
            except Exception:
                warn_exc(logger, "ensure_decisions_v0_schema backfill failed")

    def ensure_paper_schema(self) -> None:
        with self.conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_positions
                (
                    position_id
                    TEXT
                    PRIMARY
                    KEY,
                    opened_at
                    TEXT
                    NOT
                    NULL,
                    run_id
                    TEXT
                    NOT
                    NULL,
                    market_id
                    TEXT
                    NOT
                    NULL,
                    outcome
                    TEXT
                    NOT
                    NULL,
                    qty
                    REAL
                    NOT
                    NULL,
                    avg_price
                    REAL
                    NOT
                    NULL,
                    entry_mid
                    REAL,
                    best_mid_seen
                    REAL,
                    worst_mid_seen
                    REAL,
                    exit_mid
                    REAL,
                    realized_pnl_pct
                    REAL,
                    best_runup_pct
                    REAL,
                    worst_drawdown_pct
                    REAL,
                    explain_type
                    TEXT,
                    explain_edge_pct
                    REAL,
                    explain_score
                    REAL,
                    opened_ts
                    REAL,
                    closed_ts
                    REAL,
                    status
                    TEXT
                    NOT
                    NULL
                )
                """
            )
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_pos_market_outcome_open "
                "ON paper_positions(market_id, outcome) WHERE status='OPEN'"
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_paper_pos_opened ON paper_positions(opened_at DESC)")

            try:
                cols = [r[1] for r in con.execute("PRAGMA table_info(paper_positions)").fetchall()]
                if "entry_mid" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN entry_mid REAL")
                if "best_mid_seen" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN best_mid_seen REAL")
                if "worst_mid_seen" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN worst_mid_seen REAL")
                if "exit_mid" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN exit_mid REAL")
                if "realized_pnl_pct" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN realized_pnl_pct REAL")
                if "best_runup_pct" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN best_runup_pct REAL")
                if "worst_drawdown_pct" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN worst_drawdown_pct REAL")
                if "explain_type" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN explain_type TEXT")
                if "explain_edge_pct" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN explain_edge_pct REAL")
                if "explain_score" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN explain_score REAL")
                if "opened_ts" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN opened_ts REAL")
                if "closed_ts" not in cols:
                    con.execute("ALTER TABLE paper_positions ADD COLUMN closed_ts REAL")
            except Exception:
                warn_exc(logger, "ensure_paper_schema add excursion cols failed")

            con.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_trades
                (
                    trade_id
                    TEXT
                    PRIMARY
                    KEY,
                    ts
                    TEXT
                    NOT
                    NULL,
                    run_id
                    TEXT
                    NOT
                    NULL,
                    market_id
                    TEXT
                    NOT
                    NULL,
                    decision_id
                    TEXT,
                    outcome
                    TEXT
                    NOT
                    NULL,
                    side
                    TEXT
                    NOT
                    NULL,
                    qty
                    REAL
                    NOT
                    NULL,
                    price
                    REAL
                    NOT
                    NULL,
                    fee
                    REAL
                    NOT
                    NULL
                    DEFAULT
                    0.0,
                    note
                    TEXT
                )
                """
            )
            try:
                cols = [r[1] for r in con.execute("PRAGMA table_info(paper_trades)").fetchall()]
                if "fee" not in cols:
                    con.execute("ALTER TABLE paper_trades ADD COLUMN fee REAL NOT NULL DEFAULT 0.0")
                if "decision_id" not in cols:
                    con.execute("ALTER TABLE paper_trades ADD COLUMN decision_id TEXT")
            except Exception:
                warn_exc(logger, "ensure_paper_schema paper_trades columns add failed")
            con.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_ts ON paper_trades(ts DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_market ON paper_trades(market_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_market_ts ON paper_trades(market_id, ts DESC)")

    # ---------------------------
    # runs
    # ---------------------------
    def insert_run(self, run: Run) -> None:
        self.runs.insert_run(run)

    def get_latest_run(self) -> Optional[Run]:
        return self.runs.get_latest_run()

    # ---------------------------
    # markets
    # ---------------------------
    def get_market(self, market_id: str) -> Optional[Market]:
        return self.markets.get_market(market_id)

    def upsert_market(self, m: Market) -> None:
        self.markets.upsert_market(m)

    def insert_market(self, m: Market) -> None:
        """Backward-compatible alias for upsert."""
        self.upsert_market(m)

    def list_markets(self, limit: int = 200) -> List[Market]:
        return self.markets.list_markets(limit=limit)


    def list_markets_by_group(self, group_key: str, limit: int = 200) -> List[Market]:
        return self.markets.list_markets_by_group(group_key, limit=limit)

    def get_cluster_details(self, group_key: str, limit_markets: int = 200) -> dict:
        return self.clusters.get_cluster_details(group_key, limit_markets=limit_markets)

    def get_cluster_details_v2(
        self,
        group_key: str,
        *,
        limit_markets: int = 200,
        signals_window_minutes: int = 240,
        selected_market_id: Optional[str] = None,
        neighbor_sort: str = "closest",
    ) -> dict:
        return self.clusters.get_cluster_details_v2(
            group_key=group_key,
            limit_markets=limit_markets,
            signals_window_minutes=signals_window_minutes,
            selected_market_id=selected_market_id,
            neighbor_sort=neighbor_sort,
        )

    def count_markets(self) -> int:
        return self.markets.count_markets_with_fallback()

    # ---------------------------
    # snapshots
    # ---------------------------
    def insert_snapshot(self, snap: Snapshot) -> None:
        self.snapshots.insert_snapshot(snap)

    def insert_snapshots(self, snaps: Iterable[Snapshot]) -> int:
        return self.snapshots.insert_snapshots(snaps)

    def count_snapshots(self) -> int:
        return self.snapshots.count_snapshots()

    def market_history(self, market_id: str, limit: int = 50, outcome: str = "YES") -> List[Dict[str, Any]]:
        return self.snapshots.market_history(market_id, limit=limit, outcome=outcome)

    def get_latest_snapshots(self, market_id: str) -> Dict[str, Dict[str, Any]]:
        return self.snapshots.get_latest_snapshots(market_id)

    def get_latest_snapshots_batch(self, market_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        return self.snapshots.get_latest_snapshots_batch(market_ids)

    # ---------------------------
    # orderbook snapshots
    # ---------------------------
    def insert_orderbook_snapshot(
        self,
        *,
        market_id: str,
        ts_utc: str,
        best_bid: float | None,
        best_ask: float | None,
        mid: float | None,
        bids_json: str,
        asks_json: str,
        retention_minutes: int = 180,
        keep_per_market: int = 200,
    ) -> None:
        with self.conn() as con:
            con.execute(
                """
                INSERT INTO orderbook_snapshots
                (market_id, ts_utc, best_bid, best_ask, mid, bids_json, asks_json)
                VALUES (?,?,?,?,?,?,?)
                """,
                (market_id, ts_utc, best_bid, best_ask, mid, bids_json, asks_json),
            )
            # retention by age
            con.execute(
                "DELETE FROM orderbook_snapshots WHERE ts_utc < datetime('now', ?)",
                (f"-{int(retention_minutes)} minutes",),
            )
            # retention by count per market
            con.execute(
                """
                DELETE FROM orderbook_snapshots
                WHERE market_id = ?
                  AND id NOT IN (
                    SELECT id FROM orderbook_snapshots
                    WHERE market_id = ?
                    ORDER BY ts_utc DESC
                    LIMIT ?
                  )
                """,
                (market_id, market_id, int(keep_per_market)),
            )

    def get_latest_orderbook_snapshot(self, market_id: str) -> dict | None:
        with self.conn() as con:
            row = con.execute(
                """
                SELECT id, market_id, ts_utc, best_bid, best_ask, mid, bids_json, asks_json
                FROM orderbook_snapshots
                WHERE market_id = ?
                ORDER BY ts_utc DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    # ---------------------------
    # signals
    # ---------------------------
    def insert_signal(self, s: Signal) -> None:
        self.signals.insert_signal(s)

    def count_signals(self) -> int:
        return self.signals.count_signals()

    # ---------------------------
    # decisions (domain)
    # ---------------------------
    def insert_decision_domain(self, d: Decision) -> None:
        self.decisions.insert_decision_domain(d)

    def count_decisions(self) -> int:
        return self.decisions.count_decisions()

    # ---------------------------
    # decisions_v0 (operator)
    # ---------------------------
    def insert_decision_v0(
            self,
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
        self.decisions.insert_decision_v0(
            decision_id=decision_id,
            ts=ts,
            run_id=run_id,
            market_id=market_id,
            action=action,
            status=status,
            reason=reason,
            reason_json=reason_json,
            payload_json=payload_json,
        )

    def get_last_decision_v0(self, market_id: str):
        return self.decisions.get_last_decision_v0(market_id)

    def get_last_decision_v0_map(self) -> dict[str, tuple]:
        return self.decisions.get_last_decision_v0_map()

    def count_decisions_v0(self) -> int:
        return self.decisions.count_decisions_v0()

    def list_recent_decisions_v0(self, limit: int = 200):
        return self.decisions.list_recent_decisions_v0(limit=limit)

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
        return self.decisions.list_recent_decisions_v0_filtered(
            limit=limit,
            offset=offset,
            action=action,
            status=status,
            market_id=market_id,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    def count_decisions_v0_filtered(
        self,
        *,
        action: str | None = None,
        status: str | None = None,
        market_id: str | None = None,
        q: str | None = None,
    ) -> int:
        return self.decisions.count_decisions_v0_filtered(
            action=action,
            status=status,
            market_id=market_id,
            q=q,
        )

    def list_decisions_v0_since(self, cursor_ts: str | None, limit: int = 200):
        return self.decisions.list_decisions_v0_since(cursor_ts, limit=limit)

    # ---------------------------
    # events log
    # ---------------------------

    # ---------------------------
    # paper queue (execution plumbing)
    # ---------------------------
    def enqueue_paper_command(
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
        return self.paper.enqueue_command(
            command_id=command_id,
            created_at=created_at,
            run_id=run_id,
            market_id=market_id,
            outcome=outcome,
            cmd=cmd,
            qty=qty,
            price_mode=price_mode,
            source_decision_id=source_decision_id,
        )

    def list_pending_paper_commands(self, limit: int = 200):
        return self.paper.list_pending_commands(limit=limit)

    def mark_paper_command_executed(self, command_id: str, executed_at: str) -> None:
        self.paper.mark_command_executed(command_id, executed_at)

    def mark_paper_command_failed(self, command_id: str, executed_at: str, error: str) -> None:
        self.paper.mark_command_failed(command_id, executed_at, error)

    def list_recent_paper_queue_for_market(self, market_id: str, limit: int = 50):
        return self.paper.list_recent_for_market(market_id, limit=limit)

    def count_paper_queue_pending(self) -> int:
        return self.paper.count_pending()

    def log_event(
            self,
            ts: datetime,
            level: str,
            component: str,
            message: str,
            payload: Dict[str, Any] | None = None,
    ) -> None:
        # Event APIs are expected to be visible immediately to direct SQL readers.
        self.events.log_event(
            ts=ts,
            level=level,
            component=component,
            message=message,
            payload=payload,
        )
        self._events_schema_ready = True

    def log_events_batch(self, events: List[Dict[str, Any]]) -> int:
        if not events:
            return 0
        written = self.events.log_events_batch(events)
        self._events_schema_ready = True
        return int(written)

    # ---------------------------
    # settings
    # ---------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self.settings.set(key, value)

    def get_bool_setting(self, key: str, default: bool = False) -> bool:
        return self.settings.get_bool(key, default)

    def is_paused(self) -> bool:
        return self.settings.is_paused()

    def set_paused(self, paused: bool) -> None:
        self.settings.set_paused(paused)

    def toggle_paused(self) -> bool:
        return self.settings.toggle_paused()

    # ---------------------------
    # UI helpers
    # ---------------------------
    def list_recent_signals(self, limit: int = 100):
        return self.signals.list_recent_signals(limit=limit)

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
        return self.signals.list_recent_signals_filtered(
            limit=limit,
            offset=offset,
            agent=agent,
            kind=kind,
            market_id=market_id,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    def count_signals_filtered(
        self,
        *,
        agent: str | None = None,
        kind: str | None = None,
        market_id: str | None = None,
        q: str | None = None,
    ) -> int:
        return self.signals.count_signals_filtered(
            agent=agent,
            kind=kind,
            market_id=market_id,
            q=q,
        )

    def list_cases(self, minutes_signals: int = 30, minutes_snaps: int = 10):
        return self.read_models.list_cases(minutes_signals=minutes_signals, minutes_snaps=minutes_snaps)

    def get_case_details(self, market_id: str, signals_limit: int = 200, snaps_limit: int = 80) -> dict:
        return self.read_models.get_case_details(
            market_id=market_id,
            signals_limit=signals_limit,
            snaps_limit=snaps_limit,
        )

    # ---------------------------
    # paper ops
    # ---------------------------
    def list_paper_positions(self, limit: int = 200):
        return self.paper_queries.list_positions(limit=limit)

    def list_paper_positions_filtered(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        status: str | None = None,
        market_id: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
    ):
        return self.paper_queries.list_positions_filtered(
            limit=limit,
            offset=offset,
            status=status,
            market_id=market_id,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    def count_paper_positions_filtered(self, *, status: str | None = None, market_id: str | None = None) -> int:
        return self.paper_queries.count_positions_filtered(status=status, market_id=market_id)

    def list_paper_trades(self, limit: int = 200):
        return self.paper_queries.list_trades(limit=limit)

    def list_paper_trades_filtered(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        side: str | None = None,
        market_id: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
    ):
        return self.paper_queries.list_trades_filtered(
            limit=limit,
            offset=offset,
            side=side,
            market_id=market_id,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

    def count_paper_trades_filtered(self, *, side: str | None = None, market_id: str | None = None) -> int:
        return self.paper_queries.count_trades_filtered(side=side, market_id=market_id)

    def count_paper_positions(self) -> int:
        return self.paper_queries.count_positions()

    def paper_buy(
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
        self.paper_exec.buy(
            run_id=run_id,
            market_id=market_id,
            outcome=outcome,
            qty=qty,
            price=price,
            note=note,
            decision_id=decision_id,
            meta=meta,
        )

    def paper_close(
        self,
        run_id: str,
        market_id: str,
        outcome: str,
        price: float,
        qty: float | None = None,
        note: str = "",
        decision_id: str | None = None,
    ) -> dict:
        return self.paper_exec.close(
            run_id=run_id,
            market_id=market_id,
            outcome=outcome,
            price=price,
            qty=qty,
            note=note,
            decision_id=decision_id,
        )

    def get_paper_metrics(self) -> dict:
        return self.paper_analytics.get_metrics()

    def get_paper_pnl_timeseries(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.paper_analytics.get_pnl_timeseries(limit=limit)

    def get_tradeability_metrics(self, hours: int = 24) -> Dict[str, Any]:
        return self.paper_analytics.get_tradeability_metrics(hours=hours)

    def get_decision_outcomes(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.paper_analytics.get_decision_outcomes(limit=limit)

    def get_quality_metrics(self) -> Dict[str, Any]:
        return self.paper_analytics.get_quality_metrics()

    def get_decision_outcome(self, decision_id: str) -> Optional[Dict[str, Any]]:
        return self.paper_analytics.get_decision_outcome(decision_id)

    def get_quality_breakdown(self, by: str = "action") -> List[Dict[str, Any]]:
        return self.paper_analytics.get_quality_breakdown(by=by)

    def get_top_decisions(self, limit: int = 10, direction: str = "winners") -> List[Dict[str, Any]]:
        return self.paper_analytics.get_top_decisions(limit=limit, direction=direction)

    def get_market_quality(self, limit: int = 15, direction: str = "best") -> List[Dict[str, Any]]:
        return self.paper_analytics.get_market_quality(limit=limit, direction=direction)

    def get_market_worst_by_win_rate(self, limit: int = 15, min_closed: int = 5) -> List[Dict[str, Any]]:
        return self.paper_analytics.get_market_worst_by_win_rate(limit=limit, min_closed=min_closed)

    def get_quality_coverage(self) -> Dict[str, Any]:
        return self.paper_analytics.get_quality_coverage()

    def get_deprioritize_rules(self) -> List[Dict[str, Any]]:
        self.ensure_deprioritize_schema()
        return self.deprioritize.list_rules()

    def get_deprioritize_weight(self, market_id: str, action: str | None = None) -> Dict[str, Any]:
        self.ensure_deprioritize_schema()
        return self.deprioritize.get_effective_weight(market_id, action)

    def get_deprioritize_mode(self) -> str:
        try:
            return str(getattr(self, "deprioritize_mode", "ui") or "ui").strip().lower()
        except Exception:
            warn_exc(logger, "get_deprioritize_mode failed")
            return "ui"

    def get_deprioritize_min_weight(self) -> float:
        try:
            return float(getattr(self, "deprioritize_min_weight", 0.05))
        except Exception:
            warn_exc(logger, "get_deprioritize_min_weight failed")
            return 0.05

    def _maybe_log_deprioritize_applied(
        self,
        *,
        market_id: str,
        action: str | None,
        score: float,
        weighted_score: float,
        prio: float,
        matched: int,
        reason: str,
    ) -> None:
        key = (market_id or "", (action or "").strip())
        now = time.monotonic()
        last = self._deprioritize_log_last.get(key, 0.0)
        if (now - last) < float(self._deprioritize_log_ttl_sec or 0.0):
            return
        self._deprioritize_log_last[key] = now
        reason_short = (reason or "").strip()
        if len(reason_short) > 200:
            reason_short = reason_short[:200]
        self.log_event(
            ts=datetime.now(timezone.utc),
            level="INFO",
            component="deprioritize",
            message="deprioritize_applied",
            payload={
                "market_id": market_id,
                "action": action,
                "score": float(score),
                "weighted_score": float(weighted_score),
                "prio": float(prio),
                "matched": int(matched),
                "reason": reason_short,
            },
        )

    def apply_deprioritize(self, score: float, market_id: str, action: str | None) -> tuple[float, Dict[str, Any]]:
        try:
            base_score = float(score)
        except Exception:
            base_score = 0.0

        if self.get_deprioritize_mode() != "pipeline":
            return base_score, {"prio": 1.0, "reason": "", "matched": 0}

        info = self.get_deprioritize_weight(market_id, action)
        try:
            weight = float(info.get("weight", 1.0))
        except Exception:
            weight = 1.0
        reason = info.get("reason", "")
        matched = int(info.get("matched_rules_count", 0) or 0)

        min_weight = self.get_deprioritize_min_weight()
        if weight < min_weight:
            weight = min_weight

        weighted_score = base_score * weight

        if weight != 1.0:
            try:
                self._maybe_log_deprioritize_applied(
                    market_id=market_id,
                    action=action,
                    score=base_score,
                    weighted_score=weighted_score,
                    prio=weight,
                    matched=matched,
                    reason=reason,
                )
            except Exception:
                warn_exc(logger, "deprioritize log event failed", market_id=market_id, action=action)

        return weighted_score, {"prio": weight, "reason": reason, "matched": matched}

    def get_latest_decision_v0_row(self, market_id: str) -> Optional[Dict[str, Any]]:
        return self.read_models.get_latest_decision_v0_row(market_id)

    def get_case_narrative(self, market_id: str, minutes: int = 240) -> Dict[str, Any]:
        return self.read_models.get_case_narrative(market_id=market_id, minutes=minutes)

    def latest_risk_constraint(self, market_id: str, minutes: int = 60):
        return self.read_models.latest_risk_constraint(market_id=market_id, minutes=minutes)

    def latest_quality_alert(self, market_id: str, minutes: int = 60, con: sqlite3.Connection | None = None):
        return self.read_models.latest_quality_alert(market_id=market_id, minutes=minutes, con=con)

    def paper_stats(self) -> dict:
        return self.paper_analytics.stats()

    def paper_has_open_position(self, market_id: str) -> bool:
        return self.paper_queries.has_open_position(market_id)


def ensure_markets_schema(self) -> None:
    """Ensure markets table exists and has expected columns (idempotent)."""
    with self.conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS markets (
              market_id TEXT PRIMARY KEY,
              slug TEXT NOT NULL,
              title TEXT NOT NULL,
              close_time TEXT,
              rules_hash TEXT NOT NULL DEFAULT '',
              group_key TEXT,
              raw_json TEXT NOT NULL DEFAULT ''
            );
            """
        )
        cols = {row["name"] for row in con.execute("PRAGMA table_info(markets)").fetchall()}
        if "close_time" not in cols:
            con.execute("ALTER TABLE markets ADD COLUMN close_time TEXT")
        if "rules_hash" not in cols:
            con.execute("ALTER TABLE markets ADD COLUMN rules_hash TEXT NOT NULL DEFAULT ''")
        if "group_key" not in cols:
            con.execute("ALTER TABLE markets ADD COLUMN group_key TEXT")
        if "raw_json" not in cols:
            con.execute("ALTER TABLE markets ADD COLUMN raw_json TEXT NOT NULL DEFAULT ''")

def ensure_snapshots_schema(self) -> None:
    """Ensure snapshots table exists and has expected columns (idempotent)."""
    with self.conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
              ts TEXT NOT NULL,
              market_id TEXT NOT NULL,
              outcome TEXT NOT NULL,
              bid REAL,
              ask REAL,
              mid REAL,
              spread REAL,
              liquidity REAL,
              volume REAL,
              implied_prob REAL,
              PRIMARY KEY (ts, market_id, outcome),
              FOREIGN KEY (market_id) REFERENCES markets(market_id)
            );
            """
        )
        cols = {row["name"] for row in con.execute("PRAGMA table_info(snapshots)").fetchall()}
        for col, ddl in [
            ("bid", "ALTER TABLE snapshots ADD COLUMN bid REAL"),
            ("ask", "ALTER TABLE snapshots ADD COLUMN ask REAL"),
            ("mid", "ALTER TABLE snapshots ADD COLUMN mid REAL"),
            ("spread", "ALTER TABLE snapshots ADD COLUMN spread REAL"),
            ("liquidity", "ALTER TABLE snapshots ADD COLUMN liquidity REAL"),
            ("volume", "ALTER TABLE snapshots ADD COLUMN volume REAL"),
            ("implied_prob", "ALTER TABLE snapshots ADD COLUMN implied_prob REAL"),
            ("updated_at", "ALTER TABLE snapshots ADD COLUMN updated_at TEXT"),
        ]:
            if col not in cols:
                con.execute(ddl)

def ensure_orderbook_schema(self) -> None:
    """Ensure orderbook snapshots table exists (idempotent)."""
    with self.conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              market_id TEXT NOT NULL,
              ts_utc TEXT NOT NULL,
              best_bid REAL,
              best_ask REAL,
              mid REAL,
              bids_json TEXT NOT NULL,
              asks_json TEXT NOT NULL,
              FOREIGN KEY (market_id) REFERENCES markets(market_id)
            );
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_orderbook_market_ts ON orderbook_snapshots(market_id, ts_utc DESC)"
        )

def ensure_signals_schema(self) -> None:
    """Ensure signals table exists and has expected columns (idempotent)."""
    with self.conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
              signal_id TEXT PRIMARY KEY,
              ts TEXT NOT NULL,
              run_id TEXT NOT NULL,
              agent_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              scope_market_id TEXT,
              scope_group_key TEXT,
              scope_pair_key TEXT,
              features_json TEXT NOT NULL,
              claim_json TEXT NOT NULL,
              candidates_json TEXT NOT NULL,
              explain_short TEXT NOT NULL DEFAULT '',
              explain_long TEXT NOT NULL DEFAULT '',
              FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            """
        )
        cols = {row["name"] for row in con.execute("PRAGMA table_info(signals)").fetchall()}
        # required core fields
        for col, ddl in [
            ("agent_id", "ALTER TABLE signals ADD COLUMN agent_id TEXT NOT NULL DEFAULT ''"),
            ("kind", "ALTER TABLE signals ADD COLUMN kind TEXT NOT NULL DEFAULT ''"),
            ("scope_market_id", "ALTER TABLE signals ADD COLUMN scope_market_id TEXT"),
            ("scope_group_key", "ALTER TABLE signals ADD COLUMN scope_group_key TEXT"),
            ("scope_pair_key", "ALTER TABLE signals ADD COLUMN scope_pair_key TEXT"),
            ("features_json", "ALTER TABLE signals ADD COLUMN features_json TEXT NOT NULL DEFAULT '{}'"),
            ("claim_json", "ALTER TABLE signals ADD COLUMN claim_json TEXT NOT NULL DEFAULT '{}'"),
            ("candidates_json", "ALTER TABLE signals ADD COLUMN candidates_json TEXT NOT NULL DEFAULT '[]'"),
            ("explain_short", "ALTER TABLE signals ADD COLUMN explain_short TEXT NOT NULL DEFAULT ''"),
            ("explain_long", "ALTER TABLE signals ADD COLUMN explain_long TEXT NOT NULL DEFAULT ''"),
        ]:
            if col not in cols:
                con.execute(ddl)
