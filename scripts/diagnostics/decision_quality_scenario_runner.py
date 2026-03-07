#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Tuple, TypeVar


@dataclass(frozen=True)
class Phase:
    name: str
    yes_mid: float
    no_mid: float
    spread: float
    liquidity: float
    risk_state: str = "NONE"  # NONE | SAFE | EDGE | BLOCK | RECOVER
    target_risk_kind: str = "NONE"
    force_limit_market_open: bool = False
    clear_limit_market_open: bool = False
    force_group_limit_per_group: bool = False
    clear_group_limit_per_group: bool = False
    force_limit_max_open_positions: bool = False
    clear_limit_max_open_positions: bool = False
    force_limit_max_notional_total: bool = False
    clear_limit_max_notional_total: bool = False
    kill_isolation: bool = False
    add_scout_signal: bool = True


@dataclass(frozen=True)
class SignalPlan:
    market_idx: int
    opportunity_key: str
    inject_every_ticks: int
    claim_variant: str


PHASES: List[Phase] = [
    Phase("STABLE_BASELINE", yes_mid=0.50, no_mid=0.50, spread=0.02, liquidity=180.0, risk_state="NONE"),
    Phase("OPPORTUNITY_APPEARS", yes_mid=0.45, no_mid=0.45, spread=0.02, liquidity=190.0, risk_state="NONE"),
    Phase("OPPORTUNITY_STRENGTHENS", yes_mid=0.42, no_mid=0.43, spread=0.015, liquidity=220.0, risk_state="NONE"),
    Phase("RISK_SAFE", yes_mid=0.49, no_mid=0.49, spread=0.02, liquidity=185.0, risk_state="SAFE"),
    Phase("RISK_EDGE", yes_mid=0.47, no_mid=0.47, spread=0.018, liquidity=195.0, risk_state="EDGE"),
    Phase(
        "RISK_BLOCK",
        yes_mid=0.44,
        no_mid=0.44,
        spread=0.016,
        liquidity=205.0,
        risk_state="BLOCK",
        target_risk_kind="RISK_CONSTRAINT_SIGNAL",
    ),
    Phase("RISK_RECOVER", yes_mid=0.50, no_mid=0.50, spread=0.02, liquidity=180.0, risk_state="RECOVER"),
    Phase(
        "LIMIT_MARKET_ALREADY_OPEN_BLOCK",
        yes_mid=0.46,
        no_mid=0.46,
        spread=0.018,
        liquidity=190.0,
        target_risk_kind="LIMIT_MARKET_ALREADY_OPEN",
        force_limit_market_open=True,
        kill_isolation=True,
    ),
    Phase(
        "LIMIT_MARKET_ALREADY_OPEN_RECOVER",
        yes_mid=0.50,
        no_mid=0.50,
        spread=0.02,
        liquidity=180.0,
        target_risk_kind="NONE",
        clear_limit_market_open=True,
        kill_isolation=True,
    ),
    Phase("NEW_OR_OPPOSITE_OPPORTUNITY", yes_mid=0.56, no_mid=0.56, spread=0.02, liquidity=200.0, risk_state="NONE"),
]

DB_RETRY_ATTEMPTS = 5
DB_RETRY_BASE_SLEEP_S = 0.20

T = TypeVar("T")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _connect_db(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30.0)
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def _is_transient_sqlite_error(exc: sqlite3.OperationalError) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "unable to open database file",
            "database is locked",
            "database is busy",
            "disk i/o error",
            "locking protocol",
        )
    )


def _with_db_retry(
    op_name: str,
    fn: Callable[[], T],
    *,
    retries: int = DB_RETRY_ATTEMPTS,
    base_sleep_s: float = DB_RETRY_BASE_SLEEP_S,
    on_retry: Callable[[int, sqlite3.OperationalError], None] | None = None,
) -> T:
    for attempt in range(1, int(retries) + 1):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if not _is_transient_sqlite_error(exc) or attempt >= int(retries):
                print(f"SCENARIO_DB_FAIL op={op_name} attempt={attempt} error={str(exc)}")
                raise
            sleep_s = float(base_sleep_s) * float(attempt)
            print(
                f"SCENARIO_DB_RETRY op={op_name} attempt={attempt} "
                f"sleep_s={sleep_s:.2f} error={str(exc)}"
            )
            if on_retry is not None:
                on_retry(attempt, exc)
            time.sleep(sleep_s)


def _ensure_market_rows(con: sqlite3.Connection) -> None:
    # Local synthetic snapshot ids often include m1/m2. Keep market FK consistent.
    for mid in ("m1", "m2"):
        con.execute(
            """
            INSERT OR IGNORE INTO markets(market_id, slug, title, close_time, rules_hash, group_key, raw_json)
            VALUES(?, ?, ?, NULL, '', 'diag', ?)
            """,
            (mid, f"synthetic-{mid}", f"Synthetic {mid}", json.dumps({"market_id": mid})),
        )


def _pick_markets(con: sqlite3.Connection, limit: int) -> List[Tuple[str, int, int]]:
    rows = con.execute(
        """
        WITH latest AS (
          SELECT s.market_id, s.outcome, s.rowid,
                 ROW_NUMBER() OVER (PARTITION BY s.market_id, s.outcome ORDER BY s.ts DESC, s.rowid DESC) rn
          FROM snapshots s
          JOIN markets m ON m.market_id = s.market_id
          WHERE s.outcome IN ('YES', 'NO')
        )
        SELECT y.market_id, y.rowid AS yes_rowid, n.rowid AS no_rowid
        FROM latest y
        JOIN latest n ON n.market_id = y.market_id
        WHERE y.outcome='YES' AND n.outcome='NO' AND y.rn=1 AND n.rn=1
        ORDER BY y.market_id
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [(str(r[0]), int(r[1]), int(r[2])) for r in rows]


def _insert_signal(
    con: sqlite3.Connection,
    *,
    run_id: str,
    agent_id: str,
    kind: str,
    market_id: str,
    phase: str,
    explain: str,
    claim: dict,
    ) -> None:
    ts = _now_iso()
    con.execute(
        """
        INSERT INTO signals(
          signal_id, ts, run_id, agent_id, kind,
          scope_market_id, scope_group_key, scope_pair_key,
          features_json, claim_json, candidates_json,
          explain_short, explain_long
        ) VALUES(?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            ts,
            run_id,
            agent_id,
            kind,
            market_id,
            json.dumps({"phase": phase}, ensure_ascii=False),
            json.dumps(claim, ensure_ascii=False),
            "[]",
            explain,
            f"{explain} phase={phase}",
        ),
    )


def _phase_signal_plan(
    phase_name: str,
    markets: List[Tuple[str, int, int]],
    *,
    limit_market_idx: int,
) -> List[SignalPlan]:
    # Make paper-candidate identity visibly different by phase:
    # - phase 2 introduces opportunity A (new market/key)
    # - phase 3 keeps same opportunity A but injects new rows frequently (same-opportunity continuation)
    # - risk phases keep one stable risk-line identity for same-case gate transitions
    # - final phase forces distinct market + distinct opportunity key
    last_idx = max(0, len(markets) - 1)
    mid_idx = 1 if len(markets) > 1 else 0
    alt_idx = 2 if len(markets) > 2 else last_idx
    plans: Dict[str, List[SignalPlan]] = {
        "STABLE_BASELINE": [
            SignalPlan(
                market_idx=0,
                opportunity_key=f"scenario:baseline:{markets[0][0]}",
                inject_every_ticks=25,
                claim_variant="baseline",
            ),
        ],
        "OPPORTUNITY_APPEARS": [
            SignalPlan(
                market_idx=mid_idx,
                opportunity_key=f"scenario:opp_a:{markets[mid_idx][0]}",
                inject_every_ticks=20,
                claim_variant="appears",
            ),
        ],
        "OPPORTUNITY_STRENGTHENS": [
            SignalPlan(
                market_idx=mid_idx,
                opportunity_key=f"scenario:opp_a:{markets[mid_idx][0]}",
                inject_every_ticks=12,
                claim_variant="strengthens_same_opportunity",
            ),
        ],
        "RISK_SAFE": [
            SignalPlan(
                market_idx=0,
                opportunity_key=f"scenario:risk_line:{markets[0][0]}",
                inject_every_ticks=18,
                claim_variant="risk_safe",
            ),
        ],
        "RISK_EDGE": [
            SignalPlan(
                market_idx=0,
                opportunity_key=f"scenario:risk_line:{markets[0][0]}",
                inject_every_ticks=10,
                claim_variant="risk_edge",
            ),
        ],
        "RISK_BLOCK": [
            SignalPlan(
                market_idx=0,
                opportunity_key=f"scenario:risk_line:{markets[0][0]}",
                inject_every_ticks=8,
                claim_variant="risk_block",
            ),
        ],
        "RISK_RECOVER": [
            SignalPlan(
                market_idx=0,
                opportunity_key=f"scenario:risk_line:{markets[0][0]}",
                inject_every_ticks=14,
                claim_variant="risk_recover",
            ),
        ],
        "LIMIT_MARKET_ALREADY_OPEN_BLOCK": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_market_open:{markets[limit_market_idx][0]}",
                inject_every_ticks=9,
                claim_variant="limit_market_open_block",
            ),
        ],
        "LIMIT_MARKET_ALREADY_OPEN_RECOVER": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_market_recover:{markets[limit_market_idx][0]}",
                inject_every_ticks=12,
                claim_variant="limit_market_open_recover",
            ),
        ],
        "LIMIT_MAX_NOTIONAL_PER_GROUP_BLOCK": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_group_block:{markets[limit_market_idx][0]}",
                inject_every_ticks=9,
                claim_variant="limit_group_block",
            ),
        ],
        "LIMIT_MAX_NOTIONAL_PER_GROUP_RECOVER": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_group_recover:{markets[limit_market_idx][0]}",
                inject_every_ticks=12,
                claim_variant="limit_group_recover",
            ),
        ],
        "QUALITY_ALERT_BLOCK": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:quality_alert_block:{markets[limit_market_idx][0]}",
                inject_every_ticks=9,
                claim_variant="quality_alert_block",
            ),
        ],
        "QUALITY_ALERT_RECOVER": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:quality_alert_recover:{markets[limit_market_idx][0]}",
                inject_every_ticks=12,
                claim_variant="quality_alert_recover",
            ),
        ],
        "LIMIT_MAX_OPEN_POSITIONS_BLOCK": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_max_open_block:{markets[limit_market_idx][0]}",
                inject_every_ticks=9,
                claim_variant="limit_max_open_block",
            ),
        ],
        "LIMIT_MAX_OPEN_POSITIONS_RECOVER": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_max_open_recover:{markets[limit_market_idx][0]}",
                inject_every_ticks=12,
                claim_variant="limit_max_open_recover",
            ),
        ],
        "LIMIT_MAX_NOTIONAL_TOTAL_BLOCK": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_notional_total_block:{markets[limit_market_idx][0]}",
                inject_every_ticks=9,
                claim_variant="limit_notional_total_block",
            ),
        ],
        "LIMIT_MAX_NOTIONAL_TOTAL_RECOVER": [
            SignalPlan(
                market_idx=limit_market_idx,
                opportunity_key=f"scenario:limit_notional_total_recover:{markets[limit_market_idx][0]}",
                inject_every_ticks=12,
                claim_variant="limit_notional_total_recover",
            ),
        ],
        "NEW_OR_OPPOSITE_OPPORTUNITY": [
            SignalPlan(
                market_idx=alt_idx,
                opportunity_key=f"scenario:opp_z_opposite:{markets[alt_idx][0]}",
                inject_every_ticks=10,
                claim_variant="new_or_opposite",
            ),
        ],
    }
    return plans.get(phase_name, [])


def _build_phases(
    *,
    focus_limit_market: bool,
    focus_group_limit: bool,
    focus_quality_alert: bool,
    focus_max_open_positions: bool,
    focus_max_notional_total: bool,
) -> List[Phase]:
    if bool(focus_limit_market):
        # Focused diagnostic path: keep a compact pre/block/recover sequence
        # centered on LIMIT_MARKET_ALREADY_OPEN behavior.
        return [
            Phase("STABLE_BASELINE", yes_mid=0.50, no_mid=0.50, spread=0.02, liquidity=180.0, risk_state="NONE"),
            Phase(
                "LIMIT_MARKET_ALREADY_OPEN_BLOCK",
                yes_mid=0.46,
                no_mid=0.46,
                spread=0.018,
                liquidity=190.0,
                target_risk_kind="LIMIT_MARKET_ALREADY_OPEN",
                force_limit_market_open=True,
                kill_isolation=True,
            ),
            Phase(
                "LIMIT_MARKET_ALREADY_OPEN_RECOVER",
                yes_mid=0.50,
                no_mid=0.50,
                spread=0.02,
                liquidity=180.0,
                target_risk_kind="NONE",
                clear_limit_market_open=True,
                kill_isolation=True,
            ),
        ]
    if bool(focus_group_limit):
        # Focused diagnostic path for group-level exposure limit.
        return [
            Phase("STABLE_BASELINE", yes_mid=0.50, no_mid=0.50, spread=0.02, liquidity=180.0, risk_state="NONE"),
            Phase(
                "LIMIT_MAX_NOTIONAL_PER_GROUP_BLOCK",
                yes_mid=0.46,
                no_mid=0.46,
                spread=0.018,
                liquidity=190.0,
                target_risk_kind="LIMIT_MAX_NOTIONAL_PER_GROUP",
                force_group_limit_per_group=True,
                kill_isolation=True,
            ),
            Phase(
                "LIMIT_MAX_NOTIONAL_PER_GROUP_RECOVER",
                yes_mid=0.50,
                no_mid=0.50,
                spread=0.02,
                liquidity=180.0,
                target_risk_kind="NONE",
                clear_group_limit_per_group=True,
                kill_isolation=True,
            ),
        ]
    if bool(focus_quality_alert):
        # Focused diagnostic path for quality-alert gate behavior.
        return [
            Phase("STABLE_BASELINE", yes_mid=0.50, no_mid=0.50, spread=0.02, liquidity=180.0, risk_state="NONE"),
            Phase(
                "QUALITY_ALERT_BLOCK",
                yes_mid=0.46,
                no_mid=0.46,
                spread=0.018,
                liquidity=190.0,
                target_risk_kind="QUALITY_ALERT_SIGNAL",
                kill_isolation=False,
            ),
            Phase(
                "QUALITY_ALERT_RECOVER",
                yes_mid=0.50,
                no_mid=0.50,
                spread=0.02,
                liquidity=180.0,
                target_risk_kind="NONE",
                kill_isolation=False,
            ),
        ]
    if bool(focus_max_open_positions):
        # Focused diagnostic path for max-open-positions limit behavior.
        return [
            Phase("STABLE_BASELINE", yes_mid=0.50, no_mid=0.50, spread=0.02, liquidity=180.0, risk_state="NONE"),
            Phase(
                "LIMIT_MAX_OPEN_POSITIONS_BLOCK",
                yes_mid=0.46,
                no_mid=0.46,
                spread=0.018,
                liquidity=190.0,
                target_risk_kind="LIMIT_MAX_OPEN_POSITIONS",
                force_limit_max_open_positions=True,
                kill_isolation=True,
            ),
            Phase(
                "LIMIT_MAX_OPEN_POSITIONS_RECOVER",
                yes_mid=0.50,
                no_mid=0.50,
                spread=0.02,
                liquidity=180.0,
                target_risk_kind="NONE",
                clear_limit_max_open_positions=True,
                kill_isolation=True,
            ),
        ]
    if bool(focus_max_notional_total):
        # Focused diagnostic path for max-notional-total limit behavior.
        return [
            Phase("STABLE_BASELINE", yes_mid=0.50, no_mid=0.50, spread=0.02, liquidity=180.0, risk_state="NONE"),
            Phase(
                "LIMIT_MAX_NOTIONAL_TOTAL_BLOCK",
                yes_mid=0.46,
                no_mid=0.46,
                spread=0.018,
                liquidity=190.0,
                target_risk_kind="LIMIT_MAX_NOTIONAL_TOTAL",
                force_limit_max_notional_total=True,
                kill_isolation=True,
            ),
            Phase(
                "LIMIT_MAX_NOTIONAL_TOTAL_RECOVER",
                yes_mid=0.50,
                no_mid=0.50,
                spread=0.02,
                liquidity=180.0,
                target_risk_kind="NONE",
                clear_limit_max_notional_total=True,
                kill_isolation=True,
            ),
        ]
    if not bool(focus_limit_market):
        return list(PHASES)
    return list(PHASES)


def _write_tick(
    con: sqlite3.Connection,
    markets: List[Tuple[str, int, int]],
    phase: Phase,
) -> None:
    ts = _now_iso()
    cur = con.cursor()
    for mid, yes_rowid, no_rowid in markets:
        yes_bid = max(0.0, phase.yes_mid - (phase.spread / 2.0))
        yes_ask = min(1.0, phase.yes_mid + (phase.spread / 2.0))
        no_bid = max(0.0, phase.no_mid - (phase.spread / 2.0))
        no_ask = min(1.0, phase.no_mid + (phase.spread / 2.0))
        cur.execute(
            """
            UPDATE snapshots
            SET ts=?, updated_at=?, bid=?, ask=?, mid=?, spread=?, liquidity=?, volume=?, implied_prob=?
            WHERE rowid=?
            """,
            (ts, ts, yes_bid, yes_ask, phase.yes_mid, phase.spread, phase.liquidity, 1000.0, phase.yes_mid, yes_rowid),
        )
        cur.execute(
            """
            UPDATE snapshots
            SET ts=?, updated_at=?, bid=?, ask=?, mid=?, spread=?, liquidity=?, volume=?, implied_prob=?
            WHERE rowid=?
            """,
            (ts, ts, no_bid, no_ask, phase.no_mid, phase.spread, phase.liquidity, 980.0, phase.no_mid, no_rowid),
        )

    mid0 = markets[0][0]
    best_bid = max(0.0, phase.yes_mid - (phase.spread / 2.0))
    best_ask = min(1.0, phase.yes_mid + (phase.spread / 2.0))
    cur.execute(
        """
        INSERT INTO orderbook_snapshots(market_id, ts_utc, best_bid, best_ask, mid, bids_json, asks_json)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mid0,
            ts,
            best_bid,
            best_ask,
            phase.yes_mid,
            json.dumps([[best_bid, 100.0]]),
            json.dumps([[best_ask, 100.0]]),
        ),
    )


def _age_out_scenario_risk_constraints(
    con: sqlite3.Connection,
    *,
    market_id: str | None = None,
    older_minutes: int = 180,
) -> int:
    cur = con.cursor()
    if market_id:
        cur.execute(
            """
            DELETE FROM signals
            WHERE kind = 'RISK_CONSTRAINT'
              AND agent_id = 'risk.scenario_runner'
              AND scope_market_id = ?
            """,
            (market_id,),
        )
    else:
        cur.execute(
            """
            DELETE FROM signals
            WHERE kind = 'RISK_CONSTRAINT'
              AND agent_id = 'risk.scenario_runner'
            """
        )
    return int(cur.rowcount or 0)


def _clear_scenario_quality_alerts(
    con: sqlite3.Connection,
    *,
    market_id: str | None = None,
) -> int:
    cur = con.cursor()
    if market_id:
        cur.execute(
            """
            DELETE FROM signals
            WHERE kind = 'QUALITY_ALERT'
              AND agent_id = 'auditor.scenario_runner'
              AND scope_market_id = ?
            """,
            (market_id,),
        )
    else:
        cur.execute(
            """
            DELETE FROM signals
            WHERE kind = 'QUALITY_ALERT'
              AND agent_id = 'auditor.scenario_runner'
            """
        )
    return int(cur.rowcount or 0)


def _pick_limit_market_idx(con: sqlite3.Connection, markets: List[Tuple[str, int, int]]) -> int:
    # Prefer a market without currently open position to isolate LIMIT_MARKET_ALREADY_OPEN when we inject it.
    cur = con.cursor()
    for idx, (mid, _y, _n) in enumerate(markets):
        try:
            row = cur.execute(
                """
                SELECT 1
                FROM paper_positions
                WHERE market_id = ?
                  AND status = 'OPEN'
                LIMIT 1
                """,
                (mid,),
            ).fetchone()
            if not row:
                return int(idx)
        except Exception:
            # If table is unavailable for any reason, fallback to deterministic index.
            break
    return max(0, len(markets) - 1)


def _insert_scenario_open_position(
    con: sqlite3.Connection,
    *,
    run_id: str,
    market_id: str,
    outcome: str = "YES",
    qty: float = 1.0,
    avg_price: float = 0.50,
) -> str:
    position_id = str(uuid.uuid4())
    opened_at = _now_iso()
    con.execute(
        """
        INSERT INTO paper_positions(position_id, opened_at, run_id, market_id, outcome, qty, avg_price, status)
        VALUES(?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """,
        (
            position_id,
            opened_at,
            run_id,
            market_id,
            str(outcome or "YES").upper(),
            float(qty),
            float(avg_price),
        ),
    )
    return position_id


def _set_market_group_key(con: sqlite3.Connection, *, market_id: str, group_key: str) -> int:
    cur = con.cursor()
    cur.execute(
        """
        UPDATE markets
        SET group_key = ?
        WHERE market_id = ?
        """,
        (str(group_key), str(market_id)),
    )
    return int(cur.rowcount or 0)


def _inject_positions_for_max_open_limit(
    con: sqlite3.Connection,
    *,
    run_id: str,
    market_ids: List[str],
    count: int,
) -> List[str]:
    ids: List[str] = []
    mids = [str(m) for m in (market_ids or []) if str(m).strip()]
    if not mids:
        return ids
    n = max(1, int(count))
    for i in range(n):
        mid = mids[i % len(mids)]
        # Use synthetic unique outcomes so we can deterministically exceed
        # max_open_positions even when only a few markets are available.
        out = f"SYNTH_{i+1}"
        pid = _insert_scenario_open_position(
            con,
            run_id=run_id,
            market_id=mid,
            outcome=out,
            qty=1.0,
            avg_price=1.0,
        )
        ids.append(str(pid))
    return ids


def _remove_scenario_positions(con: sqlite3.Connection, *, position_ids: List[str]) -> int:
    if not position_ids:
        return 0
    cur = con.cursor()
    changed = 0
    for pid in position_ids:
        cur.execute("DELETE FROM paper_positions WHERE position_id = ?", (pid,))
        changed += int(cur.rowcount or 0)
    return int(changed)


def _get_setting(con: sqlite3.Connection, key: str) -> str | None:
    row = con.execute("SELECT value FROM settings WHERE key = ? LIMIT 1", (str(key),)).fetchone()
    if not row:
        return None
    return str(row[0] or "")


def _set_setting(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        """
        INSERT INTO settings(key, value, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (str(key), str(value), _now_iso()),
    )


def _kill_switch_reset_if_auto(con: sqlite3.Connection) -> tuple[bool, str, str]:
    prev_value = str(_get_setting(con, "kill_switch") or "0").strip()
    prev_reason = str(_get_setting(con, "kill_switch_reason") or "").strip()
    if prev_value != "1":
        return (False, prev_value, prev_reason)
    # Narrow reset policy: only AUTO-created kill switch, never manual/operator value.
    if not prev_reason.upper().startswith("AUTO:"):
        return (False, prev_value, prev_reason)
    _set_setting(con, "kill_switch", "0")
    _set_setting(con, "kill_switch_reason", "SCENARIO_RESET")
    return (True, prev_value, prev_reason)


def run_scenario(
    db_path: str,
    markets_limit: int,
    phase_seconds: int,
    tick_seconds: float,
    *,
    focus_limit_market: bool = False,
    focus_group_limit: bool = False,
    focus_quality_alert: bool = False,
    focus_max_open_positions: bool = False,
    focus_max_notional_total: bool = False,
) -> int:
    if not os.path.exists(db_path):
        print(f"SCENARIO_ERROR db_not_found path={db_path}")
        return 1

    con = _connect_db(db_path)
    con_ref = {"con": con}

    def _on_db_retry(_attempt: int, exc: sqlite3.OperationalError) -> None:
        msg = str(exc).lower()
        if "unable to open database file" in msg or "disk i/o error" in msg:
            try:
                con_ref["con"].close()
            except Exception:
                pass
            con_ref["con"] = _connect_db(db_path)

    def _db(op_name: str, fn: Callable[[sqlite3.Connection], T]) -> T:
        return _with_db_retry(
            op_name,
            lambda: fn(con_ref["con"]),
            on_retry=_on_db_retry,
        )

    try:
        _db("ensure_market_rows", lambda c: _ensure_market_rows(c))
        _db("commit.ensure_market_rows", lambda c: c.commit())
        effective_markets_limit = max(int(markets_limit), 8) if bool(focus_max_open_positions) else int(markets_limit)
        markets = _db("pick_markets", lambda c: _pick_markets(c, effective_markets_limit))
        if not markets:
            print("SCENARIO_ERROR no_paired_yes_no_markets")
            return 1
        limit_market_idx = int(_db("pick_limit_market_idx", lambda c: _pick_limit_market_idx(c, markets)))
        limit_market_id = markets[limit_market_idx][0]
        injected_limit_position_ids: List[str] = []
        injected_group_limit_position_ids: List[str] = []
        injected_max_open_position_ids: List[str] = []
        injected_notional_total_position_ids: List[str] = []
        group_limit_key = f"diag-limit-group-{limit_market_id}"

        run_id = f"scenario-runner-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        phases = _build_phases(
            focus_limit_market=bool(focus_limit_market),
            focus_group_limit=bool(focus_group_limit),
            focus_quality_alert=bool(focus_quality_alert),
            focus_max_open_positions=bool(focus_max_open_positions),
            focus_max_notional_total=bool(focus_max_notional_total),
        )
        print(
            f"SCENARIO_START db={db_path} markets={len(markets)} ids={[m[0] for m in markets]} "
            f"phase_seconds={phase_seconds} tick_seconds={tick_seconds} "
            f"limit_market={limit_market_id} focus_limit_mode={int(bool(focus_limit_market))} "
                f"focus_group_mode={int(bool(focus_group_limit))} "
                f"focus_quality_mode={int(bool(focus_quality_alert))} "
                f"focus_open_positions_mode={int(bool(focus_max_open_positions))} "
                f"focus_notional_total_mode={int(bool(focus_max_notional_total))}"
            )
        # Clear stale runner-owned risk signals from prior runs so risk transitions are deterministic.
        aged = _db(
            "risk_constraints.age_out.prep",
            lambda c: _age_out_scenario_risk_constraints(c, market_id=None, older_minutes=180),
        )
        _db("commit.age_out.prep", lambda c: c.commit())
        if aged:
            print(f"SCENARIO_PREP aged_out_runner_risk_constraints={aged}")
        if bool(focus_quality_alert):
            q_cleared = _db(
                "quality_alerts.clear.prep",
                lambda c: _clear_scenario_quality_alerts(c, market_id=None),
            )
            _db("commit.quality_alerts.clear.prep", lambda c: c.commit())
            if q_cleared:
                print(f"SCENARIO_PREP cleared_runner_quality_alerts={q_cleared}")

        for phase in phases:
            phase_plans = _phase_signal_plan(
                phase.name,
                markets,
                limit_market_idx=limit_market_idx,
            )
            risk_market = markets[0][0]
            quality_market = limit_market_id
            driven_markets = ",".join(sorted({markets[p.market_idx][0] for p in phase_plans})) or "-"
            plan_txt = ",".join(
                [
                    f"{markets[p.market_idx][0]}|{p.opportunity_key}|every={p.inject_every_ticks}"
                    for p in phase_plans
                ]
            ) or "-"
            ts = _now_iso()
            print(
                f"SCENARIO_PHASE phase={phase.name} ts={ts} yes_mid={phase.yes_mid:.3f} "
                f"no_mid={phase.no_mid:.3f} spread={phase.spread:.3f} liq={phase.liquidity:.1f} "
                f"risk_state={phase.risk_state} risk_market={risk_market} "
                f"target_risk_kind={phase.target_risk_kind} limit_market={limit_market_id} "
                f"kill_isolation={int(bool(phase.kill_isolation))} "
                f"focus_limit_mode={int(bool(focus_limit_market))} "
                f"focus_group_mode={int(bool(focus_group_limit))} "
                f"focus_quality_mode={int(bool(focus_quality_alert))} "
                f"focus_open_positions_mode={int(bool(focus_max_open_positions))} "
                f"focus_notional_total_mode={int(bool(focus_max_notional_total))} "
                f"driven_markets={driven_markets} signal_plan={plan_txt}"
            )
            if phase.kill_isolation:
                changed, prev_value, prev_reason = _db(
                    "settings.kill_switch_reset_if_auto",
                    lambda c: _kill_switch_reset_if_auto(c),
                )
                if changed:
                    print(
                        f"SCENARIO_KILL_RESET phase={phase.name} previous_value={prev_value} "
                        f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                    )
                _db("commit.kill_switch_reset_if_auto", lambda c: c.commit())

            # Phase marker scouts with explicit candidate identity plan.
            if phase.add_scout_signal and phase_plans:
                for p in phase_plans:
                    market_id = markets[p.market_idx][0]
                    _db(
                        "insert_signal.phase_marker",
                        lambda c, market_id=market_id, p=p: _insert_signal(
                            c,
                            run_id=run_id,
                            agent_id="scout.scenario_runner",
                            kind="SCOUT",
                            market_id=market_id,
                            phase=phase.name,
                            explain=f"scenario scout marker {p.claim_variant}",
                            claim={
                                "opportunity_key": p.opportunity_key,
                                "variant": p.claim_variant,
                                "phase": phase.name,
                                "target_market": market_id,
                            },
                        ),
                    )

            # Explicit risk transitions for the same case/market line:
            # SAFE/EDGE => ensure no active scenario-owned risk constraint in window,
            # BLOCK => inject active risk constraint,
            # RECOVER => age out scenario-owned constraints again.
            if phase.risk_state in {"SAFE", "EDGE", "RECOVER"}:
                _db(
                    "risk_constraints.age_out.phase",
                    lambda c: _age_out_scenario_risk_constraints(c, market_id=risk_market, older_minutes=180),
                )
            if phase.risk_state == "BLOCK":
                _db(
                    "insert_signal.risk_constraint",
                    lambda c: _insert_signal(
                        c,
                        run_id=run_id,
                        agent_id="risk.scenario_runner",
                        kind="RISK_CONSTRAINT",
                        market_id=risk_market,
                        phase=phase.name,
                        explain=f"scenario risk constraint marker state={phase.risk_state}",
                        claim={"source": "scenario_runner", "risk_state": phase.risk_state},
                    ),
                )
            if phase.name == "QUALITY_ALERT_BLOCK":
                _db(
                    "insert_signal.quality_alert",
                    lambda c: _insert_signal(
                        c,
                        run_id=run_id,
                        agent_id="auditor.scenario_runner",
                        kind="QUALITY_ALERT",
                        market_id=quality_market,
                        phase=phase.name,
                        explain="scenario quality alert marker state=BLOCK",
                        claim={"source": "scenario_runner", "quality_state": "BLOCK"},
                    ),
                )
                print(
                    f"SCENARIO_QUALITY_INJECT phase={phase.name} target_risk_kind={phase.target_risk_kind} "
                    f"market={quality_market}"
                )
            if phase.name == "QUALITY_ALERT_RECOVER":
                q_removed = _db(
                    "quality_alerts.clear.phase",
                    lambda c: _clear_scenario_quality_alerts(c, market_id=quality_market),
                )
                print(
                    f"SCENARIO_QUALITY_CLEAR phase={phase.name} market={quality_market} removed={q_removed}"
                )
            if phase.clear_limit_market_open and injected_limit_position_ids:
                removed = _db(
                    "paper_positions.remove_injected",
                    lambda c: _remove_scenario_positions(c, position_ids=injected_limit_position_ids),
                )
                print(
                    f"SCENARIO_LIMIT_CLEAR phase={phase.name} market={limit_market_id} "
                    f"removed={removed} tracked={len(injected_limit_position_ids)}"
                )
                injected_limit_position_ids.clear()
            if phase.force_group_limit_per_group:
                touched = _db(
                    "markets.set_group_key.group_limit",
                    lambda c: _set_market_group_key(c, market_id=limit_market_id, group_key=group_limit_key),
                )
                print(
                    f"SCENARIO_GROUP_LIMIT_PREP phase={phase.name} market={limit_market_id} "
                    f"group_key={group_limit_key} touched={touched}"
                )
            if phase.clear_group_limit_per_group and injected_group_limit_position_ids:
                removed = _db(
                    "paper_positions.remove_injected.group_limit",
                    lambda c: _remove_scenario_positions(c, position_ids=injected_group_limit_position_ids),
                )
                print(
                    f"SCENARIO_GROUP_LIMIT_CLEAR phase={phase.name} market={limit_market_id} "
                    f"group_key={group_limit_key} removed={removed} tracked={len(injected_group_limit_position_ids)}"
                )
                injected_group_limit_position_ids.clear()
            if phase.clear_limit_max_open_positions and injected_max_open_position_ids:
                removed = _db(
                    "paper_positions.remove_injected.max_open_positions",
                    lambda c: _remove_scenario_positions(c, position_ids=injected_max_open_position_ids),
                )
                print(
                    f"SCENARIO_OPENPOS_CLEAR phase={phase.name} removed={removed} "
                    f"tracked={len(injected_max_open_position_ids)}"
                )
                injected_max_open_position_ids.clear()
            if phase.clear_limit_max_notional_total and injected_notional_total_position_ids:
                removed = _db(
                    "paper_positions.remove_injected.max_notional_total",
                    lambda c: _remove_scenario_positions(c, position_ids=injected_notional_total_position_ids),
                )
                print(
                    f"SCENARIO_NOTIONAL_TOTAL_CLEAR phase={phase.name} removed={removed} "
                    f"tracked={len(injected_notional_total_position_ids)}"
                )
                injected_notional_total_position_ids.clear()
            _db("commit.phase_setup", lambda c: c.commit())

            ticks = max(1, int(round(float(phase_seconds) / max(0.1, float(tick_seconds)))))
            limit_inject_i: int | None = None
            limit_clear_i: int | None = None
            group_inject_i: int | None = None
            group_clear_i: int | None = None
            openpos_inject_i: int | None = None
            openpos_clear_i: int | None = None
            notional_total_inject_i: int | None = None
            notional_total_clear_i: int | None = None
            if phase.force_limit_market_open:
                if bool(focus_limit_market):
                    # Focused mode: keep injected state across most of BLOCK phase
                    # so at least one reconcile is likely to overlap.
                    limit_inject_i = 1 if ticks > 2 else 0
                    limit_clear_i = max(limit_inject_i + 1, ticks - 2)
                    mode = "focused_overlap"
                else:
                    # Default mode: bounded but shorter overlap.
                    limit_hold_ticks = max(2, min(6, ticks // 2))
                    limit_inject_i = 1 if ticks > 2 else 0
                    limit_clear_i = min(ticks - 1, limit_inject_i + limit_hold_ticks)
                    mode = "bounded_overlap"
                print(
                    f"SCENARIO_LIMIT_ISOLATION phase={phase.name} mode={mode} "
                    f"inject_i={limit_inject_i} clear_i={limit_clear_i} ticks={ticks}"
                )
            if phase.force_group_limit_per_group:
                if bool(focus_group_limit):
                    group_inject_i = 1 if ticks > 2 else 0
                    group_clear_i = max(group_inject_i + 1, ticks - 2)
                    gmode = "focused_group_overlap"
                else:
                    group_inject_i = 1 if ticks > 2 else 0
                    group_hold_ticks = max(2, min(6, ticks // 2))
                    group_clear_i = min(ticks - 1, group_inject_i + group_hold_ticks)
                    gmode = "bounded_group_overlap"
                print(
                    f"SCENARIO_GROUP_LIMIT_ISOLATION phase={phase.name} mode={gmode} "
                    f"group_key={group_limit_key} inject_i={group_inject_i} clear_i={group_clear_i} ticks={ticks}"
                )
            if phase.force_limit_max_open_positions:
                if bool(focus_max_open_positions):
                    openpos_inject_i = 1 if ticks > 2 else 0
                    openpos_clear_i = max(openpos_inject_i + 1, ticks - 2)
                    omode = "focused_openpos_overlap"
                else:
                    openpos_inject_i = 1 if ticks > 2 else 0
                    openpos_hold_ticks = max(2, min(6, ticks // 2))
                    openpos_clear_i = min(ticks - 1, openpos_inject_i + openpos_hold_ticks)
                    omode = "bounded_openpos_overlap"
                print(
                    f"SCENARIO_OPENPOS_ISOLATION phase={phase.name} mode={omode} "
                    f"inject_i={openpos_inject_i} clear_i={openpos_clear_i} ticks={ticks}"
                )
            if phase.force_limit_max_notional_total:
                if bool(focus_max_notional_total):
                    notional_total_inject_i = 1 if ticks > 2 else 0
                    notional_total_clear_i = max(notional_total_inject_i + 1, ticks - 2)
                    nmode = "focused_notional_total_overlap"
                else:
                    notional_total_inject_i = 1 if ticks > 2 else 0
                    notional_hold_ticks = max(2, min(6, ticks // 2))
                    notional_total_clear_i = min(ticks - 1, notional_total_inject_i + notional_hold_ticks)
                    nmode = "bounded_notional_total_overlap"
                print(
                    f"SCENARIO_NOTIONAL_TOTAL_ISOLATION phase={phase.name} mode={nmode} "
                    f"inject_i={notional_total_inject_i} clear_i={notional_total_clear_i} ticks={ticks}"
                )

            for i in range(ticks):
                if phase.force_limit_market_open and limit_inject_i is not None and i == limit_inject_i:
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.pre_inject",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    pos_id = _db(
                        "paper_positions.inject_open",
                        lambda c: _insert_scenario_open_position(
                            c,
                            run_id=run_id,
                            market_id=limit_market_id,
                            outcome="YES",
                        ),
                    )
                    injected_limit_position_ids.append(str(pos_id))
                    print(
                        f"SCENARIO_LIMIT_INJECT phase={phase.name} i={i} target_risk_kind={phase.target_risk_kind} "
                        f"market={limit_market_id} position_id={pos_id}"
                    )
                    _db("commit.limit_inject_window", lambda c: c.commit())
                if phase.force_group_limit_per_group and group_inject_i is not None and i == group_inject_i:
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.pre_group_inject",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    pos_id = _db(
                        "paper_positions.inject_group_limit",
                        lambda c: _insert_scenario_open_position(
                            c,
                            run_id=run_id,
                            market_id=limit_market_id,
                            outcome="YES",
                            qty=300.0,
                            avg_price=1.0,
                        ),
                    )
                    injected_group_limit_position_ids.append(str(pos_id))
                    print(
                        f"SCENARIO_GROUP_LIMIT_INJECT phase={phase.name} i={i} "
                        f"target_risk_kind={phase.target_risk_kind} market={limit_market_id} "
                        f"group_key={group_limit_key} position_id={pos_id} qty=300.0 avg_price=1.0"
                    )
                    _db("commit.group_limit_inject_window", lambda c: c.commit())
                if phase.force_limit_max_open_positions and openpos_inject_i is not None and i == openpos_inject_i:
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.pre_openpos_inject",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    injected_ids = _db(
                        "paper_positions.inject_max_open_positions",
                        lambda c: _inject_positions_for_max_open_limit(
                            c,
                            run_id=run_id,
                            market_ids=[m[0] for m in markets],
                            count=16,
                        ),
                    )
                    injected_max_open_position_ids.extend([str(x) for x in injected_ids])
                    print(
                        f"SCENARIO_OPENPOS_INJECT phase={phase.name} i={i} "
                        f"target_risk_kind={phase.target_risk_kind} count={len(injected_ids)} "
                        f"driven_markets={','.join([m[0] for m in markets])}"
                    )
                    _db("commit.max_open_positions_inject_window", lambda c: c.commit())
                if (
                    phase.force_limit_max_notional_total
                    and notional_total_inject_i is not None
                    and i == notional_total_inject_i
                ):
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.pre_notional_total_inject",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    pos_id = _db(
                        "paper_positions.inject_max_notional_total",
                        lambda c: _insert_scenario_open_position(
                            c,
                            run_id=run_id,
                            market_id=limit_market_id,
                            outcome="SYNTH_TOTAL",
                            qty=1_000_000.0,
                            avg_price=1.0,
                        ),
                    )
                    injected_notional_total_position_ids.append(str(pos_id))
                    print(
                        f"SCENARIO_NOTIONAL_TOTAL_INJECT phase={phase.name} i={i} "
                        f"target_risk_kind={phase.target_risk_kind} market={limit_market_id} "
                        f"position_id={pos_id} qty=1000000.0 avg_price=1.0"
                    )
                    _db("commit.max_notional_total_inject_window", lambda c: c.commit())

                if phase.add_scout_signal and phase_plans:
                    for p in phase_plans:
                        if i > 0 and i % max(1, int(p.inject_every_ticks)) == 0:
                            market_id = markets[p.market_idx][0]
                            _db(
                                "insert_signal.refresh",
                                lambda c, market_id=market_id, p=p, i=i: _insert_signal(
                                    c,
                                    run_id=run_id,
                                    agent_id="scout.scenario_runner",
                                    kind="SCOUT",
                                    market_id=market_id,
                                    phase=phase.name,
                                    explain=f"scenario scout refresh {p.claim_variant}",
                                    claim={
                                        "opportunity_key": p.opportunity_key,
                                        "variant": p.claim_variant,
                                        "phase": phase.name,
                                        "target_market": market_id,
                                        "refresh_i": i,
                                    },
                                ),
                            )
                _db("write_tick", lambda c: _write_tick(c, markets, phase))
                _db("commit.tick", lambda c: c.commit())
                if i % 10 == 0:
                    print(
                        f"SCENARIO_TICK phase={phase.name} i={i} ts={_now_iso()} "
                        f"signal_plan={plan_txt}"
                    )

                if (
                    phase.force_limit_market_open
                    and limit_clear_i is not None
                    and i == limit_clear_i
                    and injected_limit_position_ids
                ):
                    removed = _db(
                        "paper_positions.remove_injected.window",
                        lambda c: _remove_scenario_positions(c, position_ids=injected_limit_position_ids),
                    )
                    print(
                        f"SCENARIO_LIMIT_CLEAR phase={phase.name} i={i} market={limit_market_id} "
                        f"removed={removed} tracked={len(injected_limit_position_ids)}"
                    )
                    injected_limit_position_ids.clear()
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.post_clear",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    _db("commit.limit_clear_window", lambda c: c.commit())
                if (
                    phase.force_group_limit_per_group
                    and group_clear_i is not None
                    and i == group_clear_i
                    and injected_group_limit_position_ids
                ):
                    removed = _db(
                        "paper_positions.remove_injected.group_limit.window",
                        lambda c: _remove_scenario_positions(c, position_ids=injected_group_limit_position_ids),
                    )
                    print(
                        f"SCENARIO_GROUP_LIMIT_CLEAR phase={phase.name} i={i} market={limit_market_id} "
                        f"group_key={group_limit_key} removed={removed} tracked={len(injected_group_limit_position_ids)}"
                    )
                    injected_group_limit_position_ids.clear()
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.post_group_clear",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    _db("commit.group_limit_clear_window", lambda c: c.commit())
                if (
                    phase.force_limit_max_open_positions
                    and openpos_clear_i is not None
                    and i == openpos_clear_i
                    and injected_max_open_position_ids
                ):
                    removed = _db(
                        "paper_positions.remove_injected.max_open_positions.window",
                        lambda c: _remove_scenario_positions(c, position_ids=injected_max_open_position_ids),
                    )
                    print(
                        f"SCENARIO_OPENPOS_CLEAR phase={phase.name} i={i} removed={removed} "
                        f"tracked={len(injected_max_open_position_ids)}"
                    )
                    injected_max_open_position_ids.clear()
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.post_openpos_clear",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    _db("commit.max_open_positions_clear_window", lambda c: c.commit())
                if (
                    phase.force_limit_max_notional_total
                    and notional_total_clear_i is not None
                    and i == notional_total_clear_i
                    and injected_notional_total_position_ids
                ):
                    removed = _db(
                        "paper_positions.remove_injected.max_notional_total.window",
                        lambda c: _remove_scenario_positions(c, position_ids=injected_notional_total_position_ids),
                    )
                    print(
                        f"SCENARIO_NOTIONAL_TOTAL_CLEAR phase={phase.name} i={i} removed={removed} "
                        f"tracked={len(injected_notional_total_position_ids)}"
                    )
                    injected_notional_total_position_ids.clear()
                    if phase.kill_isolation:
                        changed, prev_value, prev_reason = _db(
                            "settings.kill_switch_reset_if_auto.post_notional_total_clear",
                            lambda c: _kill_switch_reset_if_auto(c),
                        )
                        if changed:
                            print(
                                f"SCENARIO_KILL_RESET phase={phase.name} i={i} previous_value={prev_value} "
                                f"previous_reason={json.dumps(prev_reason, ensure_ascii=False)}"
                            )
                    _db("commit.max_notional_total_clear_window", lambda c: c.commit())
                time.sleep(float(tick_seconds))

        print(f"SCENARIO_DONE ts={_now_iso()} phases={len(phases)}")
        return 0
    finally:
        try:
            con_ref["con"].close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Controlled dynamic market-phase runner for decision-quality and risk diagnostics."
    )
    parser.add_argument("--db-path", default="polysyndicate.db", help="Path to local sqlite DB.")
    parser.add_argument("--markets", type=int, default=3, help="How many paired YES/NO markets to drive.")
    parser.add_argument("--phase-seconds", type=int, default=75, help="Seconds per phase.")
    parser.add_argument("--tick-seconds", type=float, default=1.0, help="Seconds per DB update tick.")
    parser.add_argument(
        "--focus-limit-market",
        action="store_true",
        help="Run compact pre/block/recover phases with stronger LIMIT_MARKET_ALREADY_OPEN overlap.",
    )
    parser.add_argument(
        "--focus-group-limit",
        action="store_true",
        help="Run compact pre/block/recover phases targeting LIMIT_MAX_NOTIONAL_PER_GROUP.",
    )
    parser.add_argument(
        "--focus-quality-alert",
        action="store_true",
        help="Run compact pre/block/recover phases targeting QUALITY_ALERT_SIGNAL.",
    )
    parser.add_argument(
        "--focus-max-open-positions",
        action="store_true",
        help="Run compact pre/block/recover phases targeting LIMIT_MAX_OPEN_POSITIONS.",
    )
    parser.add_argument(
        "--focus-max-notional-total",
        action="store_true",
        help="Run compact pre/block/recover phases targeting LIMIT_MAX_NOTIONAL_TOTAL.",
    )
    args = parser.parse_args()
    focus_count = (
        int(bool(args.focus_limit_market))
        + int(bool(args.focus_group_limit))
        + int(bool(args.focus_quality_alert))
        + int(bool(args.focus_max_open_positions))
        + int(bool(args.focus_max_notional_total))
    )
    if focus_count > 1:
        print(
            "SCENARIO_ERROR choose_only_one_focus_mode "
            f"focus_limit_market={int(bool(args.focus_limit_market))} "
                f"focus_group_limit={int(bool(args.focus_group_limit))} "
                f"focus_quality_alert={int(bool(args.focus_quality_alert))} "
                f"focus_max_open_positions={int(bool(args.focus_max_open_positions))} "
                f"focus_max_notional_total={int(bool(args.focus_max_notional_total))}"
        )
        return 2
    return run_scenario(
        db_path=str(args.db_path),
        markets_limit=max(1, int(args.markets)),
        phase_seconds=max(1, int(args.phase_seconds)),
        tick_seconds=max(0.1, float(args.tick_seconds)),
        focus_limit_market=bool(args.focus_limit_market),
        focus_group_limit=bool(args.focus_group_limit),
        focus_quality_alert=bool(args.focus_quality_alert),
        focus_max_open_positions=bool(args.focus_max_open_positions),
        focus_max_notional_total=bool(args.focus_max_notional_total),
    )


if __name__ == "__main__":
    raise SystemExit(main())
