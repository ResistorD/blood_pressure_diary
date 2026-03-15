from __future__ import annotations

import logging
import time
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.settings import Settings
from db.repo import Repo
from dispatcher.bus import EventBus
from dispatcher.events import Alert, MarketTick, Timer
from dispatcher.scheduler import Scheduler
from ingest.ingestor import Ingestor
from ingest.polymarket_client import GAMMA_BASE, PolymarketClient, _extract_tokens_from_row
from ingest.orderbook_collector import OrderbookCollector
from db.agent_provider import RepoAgentDataProvider

from agents.enhanced_base import AgentContext
from agents.quant import QuantAgent
from decision.engine import DecisionEngineV0
from execution.reconcile import reconcile_paper
from app.risk_gate import RiskGate
from dispatcher.contract import Dispatcher
from agents.auto_paper_agent import get_auto_paper_agent
from utils.orderbook_math import calc_depth
from dispatcher.freshness import (
    STATE_OK,
    STATE_STOP,
    STATE_WARN,
    compute_state as compute_freshness_state,
    max_severity as freshness_max_severity,
)
from dispatcher.paper_decision_pipeline import run_paper_pipeline
from dispatcher.paper_decision_pipeline import (
    _mm_threshold,
    _paper_min_similarity,
    _parse_mm_payload,
    _parse_strategy_kind,
    _parse_opportunity_key,
    _parse_similarity,
    _scout_pool_size,
)

log = logging.getLogger("dispatcher.loop")

DECISION_MODE_FULL = "FULL"
DECISION_MODE_SAFE = "SAFE"
DECISION_MODE_HALTED = "HALTED"


def _try_import_optional_agents():
    """Optional agents are allowed to be missing during early development."""
    scout = None
    logic = None
    auditor = None
    risk = None

    try:
        from agents.scout import ScoutAgent  # type: ignore
        scout = ScoutAgent()
    except Exception:
        scout = None

    try:
        from agents.logic import LogicAgent  # type: ignore
        logic = LogicAgent()
    except Exception:
        logic = None

    try:
        from agents.auditor import AuditorAgent  # type: ignore
        auditor = AuditorAgent()
    except Exception:
        auditor = None

    try:
        from agents.risk import RiskAgent  # type: ignore
        risk = RiskAgent()
    except Exception:
        risk = None

    return scout, logic, auditor, risk


class MainLoop:
    BOOK_WARN_S = 2.5
    BOOK_STOP_S = 7.0
    FRESHNESS_HYSTERESIS_S = 0.5

    def __init__(self, settings: Settings, repo: Repo, bus: EventBus, run_id: str):
        self.settings = settings
        self.repo = repo
        self.bus = bus
        self.run_id = run_id

        self.decision_engine = DecisionEngineV0(repo, risk_gate=RiskGate(repo, settings))

        self.scheduler = Scheduler(
            poll_interval_sec=settings.poll_interval_sec,
            reconcile_interval_sec=settings.reconcile_interval_sec,
        )
        self.ingestor = Ingestor(repo, PolymarketClient())
        self.book_collector = OrderbookCollector(repo, PolymarketClient())

        # --- Agents ---
        # Fast agents run on each MarketTick (cheap per-market).
        self.fast_agents = [
            QuantAgent(
                min_liquidity=settings.risk.min_liquidity,
                max_spread=settings.risk.max_spread,
            )
        ]

        # Slow agents run on reconcile tick (cross-market scans + global checks).
        scout, logic, auditor, risk = _try_import_optional_agents()
        self.slow_agents = []
        if scout is not None:
            self.slow_agents.append(scout)
        if logic is not None:
            self.slow_agents.append(logic)
        if auditor is not None:
            self.slow_agents.append(auditor)
        if risk is not None:
            self.slow_agents.append(risk)

        # Backward-compat alias (some code may expect self.agents)
        self.agents = self.fast_agents

        self._stop = False
        self._ingest_failures = 0
        self._next_ingest_ts = 0.0
        self._ingest_neterr_until = 0.0
        try:
            self._ingest_max_block_ms = float(os.getenv("PS_INGEST_MAX_BLOCK_MS", "0") or 0.0)
        except Exception:
            self._ingest_max_block_ms = 0.0
        try:
            self._ingest_block_guard_skip_cap = int(os.getenv("PS_INGEST_BLOCK_GUARD_SKIP_CAP", "3") or 3)
        except Exception:
            self._ingest_block_guard_skip_cap = 3
        self._ingest_block_guard_skip_cap = max(1, int(self._ingest_block_guard_skip_cap))
        self._ingest_block_guard_skips = 0
        self._last_ingest_wall_ms = 0.0
        self._next_book_ts = 0.0
        self._book_failures = 0
        self._last_orderbook_log = 0.0
        self._event_buffer = []
        self._latest_snapshots_cache = {}
        self._auto_agent = get_auto_paper_agent()
        self._iter = 0
        self._last_loop_log_ts = 0.0
        self._last_summary_log_ts = 0.0
        self._last_ingest_fail_log_ts = 0.0
        self._last_ingest_skip_log_ts = 0.0
        self._last_ingest_skip_reason_log_ts: Dict[str, float] = {}
        self._last_book_skip_log_ts = 0.0
        self._last_stage_flags_log_ts = 0.0
        self._last_ts_parse_diag_log_ts = 0.0
        self._last_freshness_diverge_log_ts = 0.0
        self._last_net_ping_ts = 0.0
        try:
            self._book_stale_sec = float(os.getenv("PS_BOOK_STALE_SEC", "0") or 0.0)
        except Exception:
            self._book_stale_sec = 0.0
        try:
            dev_mode = bool(getattr(self.settings, "dev_mode", False)) or (
                str(os.getenv("PS_DEV", "0") or "0").strip().lower() not in {"0", "false", "no", ""}
            )
            default_book_target_limit = 20 if dev_mode else 30
            self._book_target_limit = int(
                os.getenv("PS_BOOK_TARGET_LIMIT", str(default_book_target_limit)) or default_book_target_limit
            )
        except Exception:
            self._book_target_limit = 0
        self._book_target_limit = max(0, int(self._book_target_limit))
        self._book_last_fetch_mono: Dict[str, float] = {}
        self._book_rr_cursor = 0
        self._db_path_logged = False
        self._net_ping_enabled = str(os.getenv("PS_NET_PING_ENABLED", "0") or "0").strip() not in {"0", "false", "no"}
        self._telemetry: Dict[str, Any] = {
            "ingest_ok": 0,
            "ingest_err": 0,
            "book_ok": 0,
            "book_err": 0,
            "agent_ok": 0,
            "agent_err": 0,
            "skipped_book_no_targets": 0,
            "skipped_ingest_guard": 0,
            "skipped_agent_disabled": 0,
            "last_ok": {"ingest": "", "book": "", "agent": ""},
            "last_error": {"ingest": None, "book": None, "agent": None},
            "error_repeat": {"ingest": 0, "book": 0, "agent": 0},
            "error_signature": {"ingest": "", "book": "", "agent": ""},
            "last_ingest_snapshots": 0,
            "last_book_inserted": 0,
        }
        self._iter_stage_ms: Dict[str, float] = {}
        self._iter_errs = 0
        self._iter_agent_timing: Dict[str, float] = {
            "cases": 0.0,
            "scout": 0.0,
            "logic": 0.0,
            "risk": 0.0,
            "paper": 0.0,
            "explain": 0.0,
        }
        self._iter_db_write_signals_count = 0
        self._iter_db_write_calls = 0
        self._iter_signal_flush_timing: Dict[str, float] = {
            "calls": 0.0,
            "total_ms": 0.0,
            "build_ms": 0.0,
            "call_ms": 0.0,
            "post_ms": 0.0,
            "exec_ms": 0.0,
            "rows": 0.0,
            "chunks": 0.0,
        }
        self._iter_signals_buf = []
        self._last_ingest_done_utc: Optional[str] = None
        self._last_book_done_utc: Optional[str] = None
        self._last_agent_done_utc: Optional[str] = None
        self._ingest_every_ema_sec: Optional[float] = None
        self._last_data_ts_epoch: Optional[float] = None
        self._iter_freshness: Optional[Dict[str, Any]] = None
        self._freshness_prev_state: Dict[str, Optional[str]] = {"data": None, "book": None, "overall": None}
        self._iter_pipe: Dict[str, Any] = {"cand_count": 0, "dec_count": 0, "last": "HOLD/NO_CANDIDATES"}
        self._iter_reconcile_diag: Dict[str, Any] = {
            "scheduled": 0,
            "allowed": 0,
            "skip_reason": "NOT_SCHEDULED",
            "decision_mode": DECISION_MODE_HALTED,
            "open_blocked_by_freshness": 0,
        }
        self._iter_decision_diag: Dict[str, Any] = {
            "scout_raw": 0,
            "scout_kept_ids": set(),
            "logic_pass": 0,
            "logic_hold": 0,
            "fast_scout_candidates": 0,
            "slow_scout_candidates": 0,
            "logic_reason_counts": {},
            "paper_reason_counts": {},
            "paper_action_counts": {},
            "hold_reason_counts": {},
            "mm_markets_raw": 0,
            "mm_markets_eligible": 0,
            "mm_candidates_found": 0,
            "mm_decision_accepted": 0,
            "mm_orders_placed": 0,
            "mm_probe_bypass_untradeable": 0,
            "mm_probe_orders_attempted": 0,
            "mm_probe_orders_failed": 0,
            "mm_probe_orders_filled": 0,
            "mm_final_probe_candidates_seen": 0,
            "mm_final_probe_candidates_selected": 0,
            "mm_final_probe_orders_attempted": 0,
            "mm_final_probe_orders_failed": 0,
        }
        self._paper_pipeline_ctx: Dict[str, Any] = {
            "last_signature": "",
            "last_consumed_scout_key": "",
            "last_consumed_opportunity_key": "",
            "cluster_mode": "NONE",
            "run_id": run_id,
        }
        self._live_stage0_last_submit_signature = ""
        self._mm_probe_prev_stats: Dict[str, int] = {"placed": 0, "filled": 0, "canceled": 0}
        self._live_stage0_untradeable_suppression: Dict[str, Dict[str, Any]] = {}
        self._wal_ck_enabled = str(os.getenv("PS_WAL_CHECKPOINT_ENABLED", "1")).strip() != "0"
        try:
            self._wal_ck_every_s = max(1.0, float(os.getenv("PS_WAL_CHECKPOINT_EVERY_S", "60") or 60.0))
        except Exception:
            self._wal_ck_every_s = 60.0
        mode_raw = str(os.getenv("PS_WAL_CHECKPOINT_MODE", "PASSIVE") or "PASSIVE").strip().upper()
        self._wal_ck_mode = mode_raw if mode_raw in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"} else "PASSIVE"
        self._last_wal_ck_ts = time.monotonic()

    @staticmethod
    def _iso_utc(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _age_sec(iso_ts: str) -> Optional[float]:
        if not iso_ts:
            return None
        try:
            dt = datetime.fromisoformat(str(iso_ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
        except Exception:
            return None

    def _fmt_age(self, iso_ts: str) -> str:
        age = self._age_sec(iso_ts)
        if age is None:
            return "-"
        return f"{age:.1f}s"

    @staticmethod
    def _fmt_age_s(age_s: Optional[float]) -> str:
        if age_s is None:
            return "-"
        return f"{max(0.0, float(age_s)):.1f}s"

    @staticmethod
    def _diag_inc(counter: Dict[str, int], key: str) -> None:
        k = str(key or "").strip() or "UNKNOWN"
        counter[k] = int(counter.get(k, 0) or 0) + 1

    @staticmethod
    def _diag_top(counter: Dict[str, int], limit: int = 3) -> list[str]:
        items = sorted(counter.items(), key=lambda kv: (-int(kv[1]), kv[0]))
        return [f"{k}:{int(v)}" for k, v in items[: max(1, int(limit))]]

    @staticmethod
    def _diag_reason_from_candidate(signal: Any, cand: Any) -> str:
        details = getattr(cand, "details", {}) or {}
        if isinstance(details, dict):
            for key in ("reason", "constraint_kind", "constraint", "why"):
                raw = details.get(key)
                if raw:
                    return str(raw).strip()
        action = str(getattr(cand, "action", "") or "").strip().upper()
        if action:
            return action
        kind = str(getattr(signal, "kind", "") or "").strip().upper()
        return kind or "UNKNOWN"

    @staticmethod
    def _diag_candidate_count(signals: list[Any]) -> int:
        total = 0
        for s in signals or []:
            total += len(list(getattr(s, "candidates", None) or []))
        return int(total)

    def _record_signal_batch_diag(self, bucket: str, signals: list[Any]) -> None:
        diag = self._iter_decision_diag
        if bucket == "scout":
            for s in signals or []:
                cands = list(getattr(s, "candidates", None) or [])
                diag["scout_raw"] = int(diag.get("scout_raw", 0) or 0) + len(cands)
                for c in cands:
                    mid = str(getattr(c, "market_id", "") or "").strip()
                    if mid and mid.isdigit():
                        diag["scout_kept_ids"].add(mid)
            return
        if bucket == "logic":
            reason_counts = diag.get("logic_reason_counts", {})
            hold_counts = diag.get("hold_reason_counts", {})
            for s in signals or []:
                for c in (getattr(s, "candidates", None) or []):
                    action = str(getattr(c, "action", "") or "").strip().upper()
                    reason = self._diag_reason_from_candidate(s, c)
                    self._diag_inc(reason_counts, reason)
                    if action in {"HOLD", "WAIT"}:
                        diag["logic_hold"] = int(diag.get("logic_hold", 0) or 0) + 1
                        self._diag_inc(hold_counts, reason)
                    else:
                        diag["logic_pass"] = int(diag.get("logic_pass", 0) or 0) + 1

    def _merge_mm_scan_diag(self, agent: Any) -> None:
        stats = getattr(agent, "_last_mm_scan_stats", None)
        if not isinstance(stats, dict):
            return
        diag = self._iter_decision_diag
        diag["mm_markets_raw"] = int(stats.get("raw_markets_count", diag.get("mm_markets_raw", 0)) or 0)
        diag["mm_markets_eligible"] = int(stats.get("eligible_markets_count", diag.get("mm_markets_eligible", 0)) or 0)
        diag["mm_candidates_found"] = int(stats.get("candidates_found", diag.get("mm_candidates_found", 0)) or 0)

    def _current_mm_probe_deltas(self) -> Dict[str, int]:
        current = {"placed": 0, "filled": 0, "canceled": 0}
        executor = getattr(self, "executor", None)
        if executor is not None and callable(getattr(executor, "get_mm_probe_stats", None)):
            try:
                raw = executor.get_mm_probe_stats() or {}
                current = {
                    "placed": int(raw.get("placed", 0) or 0),
                    "filled": int(raw.get("filled", 0) or 0),
                    "canceled": int(raw.get("canceled", 0) or 0),
                }
            except Exception:
                current = {"placed": 0, "filled": 0, "canceled": 0}
        prev = getattr(self, "_mm_probe_prev_stats", None)
        if not isinstance(prev, dict):
            prev = {"placed": 0, "filled": 0, "canceled": 0}
        delta = {
            key: max(0, int(current.get(key, 0) or 0) - int(prev.get(key, 0) or 0))
            for key in ("placed", "filled", "canceled")
        }
        self._mm_probe_prev_stats = current
        return delta

    def _emit_mm_probe_summary(self) -> None:
        diag = getattr(self, "_iter_decision_diag", None) or {}
        deltas = self._current_mm_probe_deltas()
        if isinstance(diag, dict):
            diag["mm_probe_orders_filled"] = int(deltas.get("filled", 0) or 0)
        log.info(
            "MM_PROBE_SUMMARY raw_markets=%s eligible_markets=%s candidates=%s "
            "probe_bypass_untradeable=%s orders_attempted=%s orders_failed=%s "
            "orders_filled=%s orders_canceled=%s",
            int(diag.get("mm_markets_raw", 0) or 0),
            int(diag.get("mm_markets_eligible", 0) or 0),
            int(diag.get("mm_candidates_found", 0) or 0),
            int(diag.get("mm_probe_bypass_untradeable", 0) or 0),
            int(diag.get("mm_probe_orders_attempted", 0) or 0),
            int(diag.get("mm_probe_orders_failed", 0) or 0),
            int(deltas.get("filled", 0) or 0),
            int(deltas.get("canceled", 0) or 0),
        )

    def _emit_mm_final_probe_summary(self) -> None:
        diag = getattr(self, "_iter_decision_diag", None) or {}
        deltas = self._current_mm_probe_deltas()
        log.info(
            "MM_FINAL_PROBE_SUMMARY candidates_seen=%s candidates_selected=%s orders_attempted=%s "
            "orders_placed=%s orders_filled=%s orders_canceled=%s orders_failed=%s",
            int(diag.get("mm_final_probe_candidates_seen", 0) or 0),
            int(diag.get("mm_final_probe_candidates_selected", 0) or 0),
            int(diag.get("mm_final_probe_orders_attempted", 0) or 0),
            int(deltas.get("placed", 0) or 0),
            int(deltas.get("filled", 0) or 0),
            int(deltas.get("canceled", 0) or 0),
            int(diag.get("mm_final_probe_orders_failed", 0) or 0),
        )

    def _count_live_cases_for_diag(self) -> int:
        try:
            rows = self.repo.list_cases(minutes_signals=30, minutes_snaps=10) or []
            return int(len(rows))
        except Exception:
            return 0

    def _emit_fast_agent_diag_summary(self) -> int:
        diag = self._iter_decision_diag or {}
        scout_kept = len(diag.get("scout_kept_ids", set()) or set())
        paper_actions = diag.get("paper_action_counts", {}) or {}
        live_cases = self._count_live_cases_for_diag()
        log.info(
            "FAST_AGENT_DIAG_SUMMARY live_cases=%s scout_raw=%s scout_kept=%s logic_pass=%s logic_hold=%s "
            "paper_open=%s paper_hold=%s logic_reasons=%s paper_reasons=%s top_reasons=%s",
            live_cases,
            int(diag.get("scout_raw", 0) or 0),
            scout_kept,
            int(diag.get("logic_pass", 0) or 0),
            int(diag.get("logic_hold", 0) or 0),
            int(paper_actions.get("OPEN", 0) or 0),
            int(paper_actions.get("HOLD", 0) or 0),
            self._diag_top(diag.get("logic_reason_counts", {}) or {}, limit=3),
            self._diag_top(diag.get("paper_reason_counts", {}) or {}, limit=3),
            self._diag_top(diag.get("hold_reason_counts", {}) or {}, limit=5),
        )
        return int(live_cases)

    def _emit_pipeline_obs(self, live_cases: int) -> None:
        diag = self._iter_decision_diag or {}
        pipe = self._iter_pipe or {}
        rec = self._iter_reconcile_diag or {}
        paper_candidate = 1 if int(pipe.get("cand_count", 0) or 0) > 0 else 0
        paper_action_raw = str(pipe.get("paper_action", "") or "").strip().upper()
        paper_action = paper_action_raw if paper_action_raw in {"OPEN", "HOLD", "CLOSE"} else "NONE"
        reconcile_allowed = int(rec.get("allowed", 0) or 0)
        reconcile_skip_reason = str(rec.get("skip_reason", "") or "").strip().upper() or "NONE"
        decision_mode = str(rec.get("decision_mode", DECISION_MODE_HALTED) or DECISION_MODE_HALTED).strip().upper()
        open_blocked_by_freshness = int(rec.get("open_blocked_by_freshness", 0) or 0)
        freshness_obj = self._compute_iter_freshness().get("state") or {}
        freshness_overall = str(freshness_obj.get("overall") or STATE_STOP).strip().upper()
        log.info(
            "PIPELINE_OBS fast_diag_scout_raw=%s fast_diag_logic_pass=%s paper_candidate=%s paper_action=%s "
            "live_cases=%s candidate_origin_fast=%s fast_scout_candidates=%s candidate_origin_slow=%s "
            "slow_scout_candidates=%s candidate_origin_paper=%s reconcile_allowed=%s reconcile_skip_reason=%s "
            "freshness=FRESHNESS_%s decision_mode=%s open_blocked_by_freshness=%s",
            int(diag.get("scout_raw", 0) or 0),
            int(diag.get("logic_pass", 0) or 0),
            paper_candidate,
            paper_action,
            int(live_cases),
            "fast_scout",
            int(diag.get("fast_scout_candidates", 0) or 0),
            "slow_scout",
            int(diag.get("slow_scout_candidates", 0) or 0),
            "db_latest_scout_signal",
            reconcile_allowed,
            reconcile_skip_reason,
            freshness_overall,
            decision_mode,
            open_blocked_by_freshness,
        )

    @staticmethod
    def _decision_mode_from_freshness(overall_state: str) -> str:
        st = str(overall_state or STATE_STOP).strip().upper()
        if st == STATE_OK:
            return DECISION_MODE_FULL
        if st == STATE_WARN:
            return DECISION_MODE_SAFE
        return DECISION_MODE_HALTED

    @staticmethod
    def _apply_paper_action_freshness_gate(pipe: Dict[str, Any], decision_mode: str) -> tuple[Dict[str, Any], int]:
        mode = str(decision_mode or DECISION_MODE_HALTED).strip().upper()
        out = dict(pipe or {})
        out["freshness_reason"] = "NONE"
        if mode != DECISION_MODE_SAFE:
            return out, 0
        action = str(out.get("paper_action", "") or "").strip().upper()
        if action != "OPEN":
            return out, 0
        if str(out.get("paper_strategy") or "").strip().upper() == "MM":
            mm_score = out.get("mm_score")
            log.info(
                "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=FRESHNESS_BLOCK",
                str(out.get("paper_market_id") or out.get("ref_id") or "").strip() or "-",
                "-" if mm_score is None else f"{float(mm_score):.6f}",
                float(_mm_threshold()),
            )
        out["paper_action"] = "HOLD"
        out["paper_reason"] = "FRESHNESS_WARN_OPEN_BLOCKED"
        out["last"] = "HOLD/FRESHNESS_WARN_OPEN_BLOCKED"
        out["dec_count"] = 0
        out["freshness_reason"] = "FRESHNESS_WARN_OPEN_BLOCKED"
        return out, 1

    @staticmethod
    def _parse_open_market_id_from_pipe(pipe: Dict[str, Any]) -> str:
        market_id = str(pipe.get("paper_market_id") or pipe.get("ref_id") or "").strip()
        if market_id:
            return market_id
        sig = str(pipe.get("dedup_signature") or "").strip()
        if not sig:
            return ""
        parts = sig.split("|", 2)
        if len(parts) != 3:
            return ""
        return str(parts[2] or "").strip()

    def _resolve_stage0_token_id(self, market_id: str, outcome: str = "YES") -> str:
        out = str(outcome or "YES").strip().upper() or "YES"
        mid = str(market_id or "").strip()
        if not mid:
            return ""
        try:
            with self.repo.conn() as con:
                row = con.execute("SELECT raw_json FROM markets WHERE market_id = ? LIMIT 1", (mid,)).fetchone()
            raw_json = str((row["raw_json"] if row and isinstance(row, dict) else (row[0] if row else "")) or "")
            if not raw_json:
                return mid
            raw = json.loads(raw_json)
            tokens = _extract_tokens_from_row(raw)
            if not tokens:
                return mid
            fallback = ""
            for t in tokens:
                tid = (
                    t.get("token_id")
                    or t.get("tokenId")
                    or t.get("clobTokenId")
                    or t.get("clob_token_id")
                    or t.get("id")
                )
                if tid is None:
                    continue
                tok_out = str(t.get("outcome") or "").strip().upper()
                tid_s = str(tid).strip()
                if not tid_s:
                    continue
                if not fallback:
                    fallback = tid_s
                if tok_out == out:
                    return tid_s
            return fallback or mid
        except Exception:
            return mid

    def _resolve_stage0_order_price(self, market_id: str, outcome: str = "YES", token_id: str = "") -> Optional[float]:
        out = str(outcome or "YES").strip().upper() or "YES"
        tid = str(token_id or "").strip() or "-"
        log.info("PIPE_OPEN_BRIDGE_PRICE_LOOKUP market_id=%s outcome=%s token_id=%s", market_id, out, tid)
        try:
            snaps = self._latest_snapshots_by_outcome(market_id)
            q: Dict[str, Any] = {}
            snapshot_outcome_key = "-"
            if isinstance(snaps, dict):
                direct = snaps.get(out)
                if isinstance(direct, dict):
                    q = direct
                    snapshot_outcome_key = out
                else:
                    for k, v in snaps.items():
                        if str(k or "").strip().upper() == out and isinstance(v, dict):
                            q = v
                            snapshot_outcome_key = str(k or "").strip() or out
                            break
            ask = q.get("ask")
            bid = q.get("bid")
            mid = q.get("mid")
            book_found = 0
            book_best_ask: Any = None
            book_mid: Any = None
            if hasattr(self.repo, "get_latest_orderbook_snapshot"):
                try:
                    ob = self.repo.get_latest_orderbook_snapshot(market_id)
                except Exception:
                    ob = None
                if isinstance(ob, dict):
                    book_found = 1
                    book_best_ask = ob.get("best_ask")
                    book_mid = ob.get("mid")

            log.info(
                "PIPE_OPEN_BRIDGE_PRICE_SOURCE market_id=%s outcome=%s token_id=%s snapshot_found=%s "
                "snapshot_outcome_key=%s book_found=%s ask=%s bid=%s mid=%s book_best_ask=%s book_mid=%s",
                market_id,
                out,
                tid,
                int(bool(q)),
                snapshot_outcome_key,
                int(book_found),
                str(ask if ask is not None else "-"),
                str(bid if bid is not None else "-"),
                str(mid if mid is not None else "-"),
                str(book_best_ask if book_best_ask is not None else "-"),
                str(book_mid if book_mid is not None else "-"),
            )
            for src, raw in (
                ("SNAPSHOT_ASK", ask),
                ("SNAPSHOT_MID", mid),
                ("ORDERBOOK_BEST_ASK", book_best_ask),
                ("ORDERBOOK_MID", book_mid),
            ):
                try:
                    p = float(raw)
                    if 0.0 < p < 1.0:
                        log.info(
                            "PIPE_OPEN_BRIDGE_PRICE_RESOLVED market_id=%s outcome=%s token_id=%s source=%s price=%.6f",
                            market_id,
                            out,
                            tid,
                            src,
                            p,
                        )
                        return p
                except Exception:
                    continue
            log.warning(
                "PIPE_OPEN_BRIDGE_PRICE_SKIP reason=NO_VALID_PRICE market_id=%s outcome=%s token_id=%s",
                market_id,
                out,
                tid,
            )
            return None
        except Exception:
            log.exception(
                "PIPE_OPEN_BRIDGE_PRICE_SKIP reason=PRICE_LOOKUP_EXCEPTION market_id=%s outcome=%s token_id=%s",
                market_id,
                out,
                tid,
            )
            return None

    def _resolve_stage0_order_qty(self, price: float) -> Optional[float]:
        if not (price > 0.0):
            return None
        try:
            fixed_notional = float(getattr(self.settings, "paper_fixed_notional", 0.0) or 0.0)
        except Exception:
            fixed_notional = 0.0
        if fixed_notional <= 0.0:
            fixed_notional = 1.0
        try:
            min_submit_notional = float(
                getattr(self.settings, "live_stage0_min_submit_notional", 0.0)
                or os.getenv("PS_LIVE_STAGE0_MIN_SUBMIT_NOTIONAL", os.getenv("LIVE_STAGE0_MIN_SUBMIT_NOTIONAL", "1.05"))
                or 1.05
            )
        except Exception:
            min_submit_notional = 1.05
        # Keep stage-0 orders safely above Polymarket's $1 marketable BUY minimum.
        target_notional = max(float(fixed_notional), float(min_submit_notional))
        qty = target_notional / float(price)
        if qty <= 0.0:
            return None
        return float(qty)

    def _live_exec_style(self) -> str:
        raw = getattr(self.settings, "live_exec_style", None)
        if raw is None:
            raw = os.getenv("PS_LIVE_EXEC_STYLE", os.getenv("LIVE_EXEC_STYLE", "human_limit"))
        style = str(raw or "human_limit").strip().lower()
        if style in {"direct", "legacy"}:
            return "direct"
        return "human_limit"

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)) or default)
        except Exception:
            return float(default)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            out = float(value)
        except Exception:
            return None
        if out != out:
            return None
        return out

    @staticmethod
    def _clamp_price(price: float) -> float:
        return max(0.001, min(0.999, round(float(price), 6)))

    def _latest_stage0_orderbook(self, market_id: str) -> dict:
        repo = getattr(self, "repo", None)
        getter = getattr(repo, "get_latest_orderbook_snapshot", None)
        if not callable(getter):
            return {}
        try:
            row = getter(market_id) or {}
            return row if isinstance(row, dict) else {}
        except Exception:
            log.exception("HUMAN_ORDER_SKIP reason=ORDERBOOK_LOOKUP_EXCEPTION market_id=%s", market_id)
            return {}

    def _build_human_limit_order_plan(self, market_id: str, outcome: str, token_id: str) -> Optional[dict[str, Any]]:
        outcome_u = str(outcome or "YES").strip().upper() or "YES"
        snaps = self._latest_snapshots_by_outcome(market_id)
        quote = {}
        for key, row in (snaps or {}).items():
            if str(key or "").strip().upper() == outcome_u:
                quote = row if isinstance(row, dict) else {}
                break
        if not quote:
            log.info(
                "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=NO_SNAPSHOT outcome=%s",
                market_id,
                token_id,
                outcome_u,
            )
            return None

        bid = self._safe_float(quote.get("bid"))
        ask = self._safe_float(quote.get("ask"))
        mid = self._safe_float(quote.get("mid"))
        spread = self._safe_float(quote.get("spread"))
        liquidity = self._safe_float(quote.get("liquidity"))
        book = self._latest_stage0_orderbook(market_id)
        book_bid = self._safe_float(book.get("best_bid"))
        book_ask = self._safe_float(book.get("best_ask"))
        book_mid = self._safe_float(book.get("mid"))

        asks = []
        try:
            asks = json.loads(book.get("asks_json") or "[]")
        except Exception:
            asks = []
        ask_levels = [lvl for lvl in asks if isinstance(lvl, dict)]

        ask_candidates = [x for x in (book_ask, ask) if x is not None and 0.0 < x < 1.0]
        bid_candidates = [x for x in (book_bid, bid) if x is not None and 0.0 < x < 1.0]
        mid_candidates = [x for x in (mid, book_mid) if x is not None and 0.0 < x < 1.0]
        if not ask_candidates or not bid_candidates:
            log.info(
                "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=INSUFFICIENT_PRICE_DATA outcome=%s",
                market_id,
                token_id,
                outcome_u,
            )
            return None

        ref_ask = min(ask_candidates)
        ref_bid = max(bid_candidates)
        ref_mid = mid_candidates[0] if mid_candidates else ((ref_bid + ref_ask) / 2.0)
        eff_spread = spread if spread is not None and spread > 0.0 else (ref_ask - ref_bid)

        max_spread = self._env_float("PS_LIVE_HUMAN_MAX_SPREAD", 0.035)
        min_price = self._env_float("PS_LIVE_HUMAN_MIN_PRICE", 0.03)
        max_price = self._env_float("PS_LIVE_HUMAN_MAX_PRICE", 0.97)
        tick_size = self._env_float("PS_LIVE_HUMAN_TICK_SIZE", 0.001)
        min_submit_notional = self._env_float("PS_LIVE_HUMAN_MIN_NOTIONAL", 2.0)
        ttl_seconds = max(0.0, self._env_float("PS_LIVE_HUMAN_TTL_SEC", 15.0))
        depth_pct = max(0.001, self._env_float("PS_LIVE_HUMAN_DEPTH_PCT", 0.03))
        depth_multiple = max(1.0, self._env_float("PS_LIVE_HUMAN_MIN_DEPTH_MULTIPLE", 1.25))

        try:
            target_notional = float(getattr(self.settings, "paper_fixed_notional", 0.0) or 0.0)
        except Exception:
            target_notional = 0.0
        if target_notional <= 0.0:
            target_notional = 1.0

        if target_notional < min_submit_notional:
            original_notional = float(target_notional)
            target_notional = float(min_submit_notional)
            log.info(
                "HUMAN_LIMIT_NOTIONAL_UPSCALED market_id=%s token_id=%s original_notional=%.6f adjusted_notional=%.6f min_notional=%.6f",
                market_id,
                token_id,
                original_notional,
                target_notional,
                min_submit_notional,
            )

        risk_cfg = getattr(self.settings, "risk", None)
        cap_candidates = [
            self._safe_float(getattr(self.settings, "live_max_notional", None)),
            self._safe_float(getattr(risk_cfg, "max_notional_total", None)),
        ]
        positive_caps = [x for x in cap_candidates if x is not None and x > 0.0]
        available_capital = min(positive_caps) if positive_caps else target_notional
        if available_capital < target_notional:
            log.info(
                "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=CAPITAL_TOO_SMALL available_capital=%.6f target_notional=%.6f",
                market_id,
                token_id,
                available_capital,
                target_notional,
            )
            return None

        if not (0.0 < ref_bid < ref_ask < 1.0) or eff_spread <= 0.0 or eff_spread > max_spread:
            log.info(
                "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=SPREAD_OR_PRICE_INVALID bid=%.6f ask=%.6f spread=%.6f max_spread=%.6f",
                market_id,
                token_id,
                ref_bid,
                ref_ask,
                eff_spread,
                max_spread,
            )
            return None

        if ref_bid <= min_price or ref_ask >= max_price or ref_mid <= min_price or ref_mid >= max_price:
            log.info(
                "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=PATHOLOGICAL_BOUNDARY bid=%.6f ask=%.6f mid=%.6f min_price=%.6f max_price=%.6f",
                market_id,
                token_id,
                ref_bid,
                ref_ask,
                ref_mid,
                min_price,
                max_price,
            )
            return None

        ask_depth_notional = calc_depth(ask_levels, ref_mid, depth_pct, "ask") if ask_levels else 0.0
        visible_liquidity = max(float(liquidity or 0.0), float(ask_depth_notional or 0.0))
        min_visible_liquidity = max(target_notional * depth_multiple, min_submit_notional * depth_multiple)
        if visible_liquidity < min_visible_liquidity:
            log.info(
                "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=INSUFFICIENT_VISIBLE_LIQUIDITY visible_liquidity=%.6f min_visible=%.6f",
                market_id,
                token_id,
                visible_liquidity,
                min_visible_liquidity,
            )
            return None

        if available_capital < (target_notional * 2.0):
            log.info(
                "HUMAN_ORDER_SINGLE_LEG_SMOKE market_id=%s token_id=%s available_capital=%.6f target_notional=%.6f paired_affordable=0",
                market_id,
                token_id,
                available_capital,
                target_notional,
            )

        limit_price = self._clamp_price(max(ref_bid, ref_ask - tick_size))
        if not (0.0 < limit_price < ref_ask < 1.0):
            log.info(
                "HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=NON_PASSIVE_LIMIT price=%.6f bid=%.6f ask=%.6f",
                market_id,
                token_id,
                limit_price,
                ref_bid,
                ref_ask,
            )
            return None
        qty = target_notional / limit_price
        if qty <= 0.0:
            log.info("HUMAN_ORDER_PLACE_FAIL market_id=%s token_id=%s reason=BAD_QTY", market_id, token_id)
            return None
        return {
            "price": float(limit_price),
            "qty": float(qty),
            "notional": float(qty * limit_price),
            "ttl_seconds": ttl_seconds,
            "visible_liquidity": float(visible_liquidity),
            "spread": float(eff_spread),
            "reference_ask": float(ref_ask),
            "reference_bid": float(ref_bid),
            "single_leg_smoke_mode": int(available_capital < (target_notional * 2.0)),
        }

    def _live_stage0_market_untradeable_reason(
        self,
        market_id: str,
        outcome: str,
        token_id: str,
    ) -> tuple[str, Optional[float], Optional[float], Optional[float]]:
        outcome_u = str(outcome or "YES").strip().upper() or "YES"
        snaps = self._latest_snapshots_by_outcome(market_id)
        quote = {}
        for key, row in (snaps or {}).items():
            if str(key or "").strip().upper() == outcome_u:
                quote = row if isinstance(row, dict) else {}
                break

        bid = self._safe_float(quote.get("bid"))
        ask = self._safe_float(quote.get("ask"))
        spread = self._safe_float(quote.get("spread"))
        book = self._latest_stage0_orderbook(market_id)
        book_bid = self._safe_float(book.get("best_bid"))
        book_ask = self._safe_float(book.get("best_ask"))

        ref_bid = book_bid if book_bid is not None else bid
        ref_ask = book_ask if book_ask is not None else ask
        eff_spread = spread if spread is not None and spread > 0.0 else None
        if eff_spread is None and ref_bid is not None and ref_ask is not None:
            eff_spread = ref_ask - ref_bid

        max_spread = self._env_float("PS_LIVE_HUMAN_MAX_SPREAD", 0.035)
        min_price = self._env_float("PS_LIVE_HUMAN_MIN_PRICE", 0.03)
        max_price = self._env_float("PS_LIVE_HUMAN_MAX_PRICE", 0.97)

        reason = ""
        if ref_bid is None or ref_ask is None:
            reason = "MISSING_BOOK"
        elif not (0.0 < ref_bid < ref_ask < 1.0):
            reason = "INVALID_BOOK"
        elif ref_bid <= 0.01 or ref_ask >= 0.99:
            reason = "BOUNDARY_BOOK"
        elif eff_spread is None or eff_spread <= 0.0 or eff_spread > max_spread:
            reason = "WIDE_SPREAD"
        elif ref_bid <= min_price or ref_ask >= max_price:
            reason = "BOUNDARY_BOOK"
        return reason, ref_bid, ref_ask, eff_spread

    @staticmethod
    def _mm_probe_allow_untradeable() -> bool:
        raw = str(os.getenv("PS_MM_PROBE_ALLOW_UNTRADEABLE", "false") or "false").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _mm_final_probe_enabled() -> bool:
        raw = str(os.getenv("PS_MM_FINAL_PROBE", "false") or "false").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _mm_probe_post_side(self, pipe: Dict[str, Any]) -> str:
        bid = self._safe_float((pipe or {}).get("mm_bid"))
        ask = self._safe_float((pipe or {}).get("mm_ask"))
        if bid is None and ask is not None:
            return "SELL"
        if ask is None and bid is not None:
            return "BUY"
        return "BOTH"

    def _is_live_stage0_market_tradeable(self, market_id: str, outcome: str, token_id: str) -> bool:
        outcome_u = str(outcome or "YES").strip().upper() or "YES"
        reason, ref_bid, ref_ask, eff_spread = self._live_stage0_market_untradeable_reason(
            market_id,
            outcome_u,
            token_id,
        )

        if reason:
            log.info(
                "LIVE_STAGE0_MARKET_UNTRADEABLE market_id=%s token_id=%s outcome=%s bid=%s ask=%s spread=%s reason=%s",
                market_id,
                token_id,
                outcome_u,
                "-" if ref_bid is None else f"{ref_bid:.6f}",
                "-" if ref_ask is None else f"{ref_ask:.6f}",
                "-" if eff_spread is None else f"{eff_spread:.6f}",
                reason,
            )
            return False
        return True

    def _live_stage0_untradeable_key(self, pipe: Dict[str, Any], market_id: str, outcome: str, token_id: str) -> str:
        opportunity_key = str(pipe.get("opportunity_key", "") or "").strip()
        if opportunity_key:
            return f"opp:{opportunity_key}"
        return f"mkt:{market_id}|tok:{token_id}|out:{str(outcome or 'YES').strip().upper() or 'YES'}"

    def _live_stage0_untradeable_cooldown_sec(self) -> float:
        return max(1.0, self._env_float("PS_LIVE_STAGE0_UNTRADEABLE_COOLDOWN_SEC", 300.0))

    def _prune_live_stage0_untradeable_suppression(self, now_mono: float) -> None:
        store = getattr(self, "_live_stage0_untradeable_suppression", None)
        if not isinstance(store, dict) or not store:
            return
        cooldown = self._live_stage0_untradeable_cooldown_sec()
        stale_keys = [
            key for key, item in store.items()
            if (now_mono - float((item or {}).get("ts_mono", 0.0) or 0.0)) >= cooldown
        ]
        for key in stale_keys:
            store.pop(key, None)

    def _is_live_stage0_untradeable_suppressed(
        self,
        pipe: Dict[str, Any],
        market_id: str,
        outcome: str,
        token_id: str,
    ) -> bool:
        now_mono = time.monotonic()
        self._prune_live_stage0_untradeable_suppression(now_mono)
        key = self._live_stage0_untradeable_key(pipe, market_id, outcome, token_id)
        store = getattr(self, "_live_stage0_untradeable_suppression", None)
        if not isinstance(store, dict):
            return False
        item = store.get(key) or {}
        if not item:
            return False
        age_sec = max(0.0, now_mono - float(item.get("ts_mono", 0.0) or 0.0))
        cooldown = self._live_stage0_untradeable_cooldown_sec()
        if age_sec >= cooldown:
            store.pop(key, None)
            return False
        log.info(
            "LIVE_STAGE0_CANDIDATE_SUPPRESSED market_id=%s token_id=%s outcome=%s suppression_key=%s age_sec=%.3f cooldown_sec=%.3f reason=%s",
            market_id,
            token_id,
            str(outcome or "YES").strip().upper() or "YES",
            key,
            age_sec,
            cooldown,
            str(item.get("reason") or "UNTRADEABLE_MARKET").strip() or "UNTRADEABLE_MARKET",
        )
        return True

    def _record_live_stage0_untradeable_suppression(
        self,
        pipe: Dict[str, Any],
        market_id: str,
        outcome: str,
        token_id: str,
        reason: str,
    ) -> None:
        now_mono = time.monotonic()
        self._prune_live_stage0_untradeable_suppression(now_mono)
        store = getattr(self, "_live_stage0_untradeable_suppression", None)
        if not isinstance(store, dict):
            self._live_stage0_untradeable_suppression = {}
            store = self._live_stage0_untradeable_suppression
        key = self._live_stage0_untradeable_key(pipe, market_id, outcome, token_id)
        store[key] = {
            "ts_mono": now_mono,
            "reason": str(reason or "UNTRADEABLE_MARKET").strip().upper() or "UNTRADEABLE_MARKET",
        }

    def _apply_live_stage0_untradeable_suppression_to_pipe(self, pipe: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(pipe or {})
        mode = str(getattr(self.settings, "execution_mode", "paper") or "paper").strip().lower()
        if mode != "live_stage0" or self._live_exec_style() != "human_limit":
            return out
        action = str(out.get("paper_action", "") or "").strip().upper()
        if action != "OPEN":
            return out
        market_id = self._parse_open_market_id_from_pipe(out)
        if not market_id:
            return out
        outcome = str(out.get("paper_outcome", "YES") or "YES").strip().upper() or "YES"
        token_id = self._resolve_stage0_token_id(market_id, outcome)
        if not token_id:
            return out
        if not self._is_live_stage0_untradeable_suppressed(out, market_id, outcome, token_id):
            return out
        out["paper_action"] = "HOLD"
        out["paper_reason"] = "UNTRADEABLE_COOLDOWN"
        out["last"] = "HOLD/UNTRADEABLE_COOLDOWN"
        out["paper_source"] = "live_stage0.untradeable_cooldown"
        out["selected"] = 0
        out["open_blocked_by_untradeable_cooldown"] = 1
        log.info(
            "LIVE_STAGE0_PIPE_SUPPRESSED market_id=%s token_id=%s outcome=%s reason=UNTRADEABLE_COOLDOWN",
            market_id,
            token_id,
            outcome,
        )
        return out

    def _pending_scout_signal_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for signal in list(getattr(self, "_iter_signals_buf", []) or []):
            agent_id = str(getattr(signal, "agent_id", "") or "").strip().lower()
            market_id = str(getattr(signal, "scope_market_id", "") or "").strip()
            if not market_id or not agent_id.startswith("scout"):
                continue
            ts = getattr(signal, "ts", None)
            if isinstance(ts, datetime):
                signal_ts = ts.astimezone(timezone.utc).isoformat(timespec="seconds")
            else:
                signal_ts = str(ts or "").strip()
            claim = getattr(signal, "claim", {})
            features = getattr(signal, "features", {})
            try:
                claim_json = json.dumps(claim if isinstance(claim, dict) else {}, ensure_ascii=False)
            except Exception:
                claim_json = "{}"
            try:
                features_json = json.dumps(features if isinstance(features, dict) else {}, ensure_ascii=False)
            except Exception:
                features_json = "{}"
            rows.append(
                {
                    "signal_rowid": 0,
                    "signal_ts": signal_ts,
                    "market_id": market_id,
                    "claim_json": claim_json,
                    "features_json": features_json,
                    "signal_origin": "pending_iter_scout",
                }
            )
        return rows

    def _live_stage0_current_generation_rows(self) -> list[dict[str, Any]]:
        pending_rows = self._pending_scout_signal_rows()
        current_ts = max((str(row.get("signal_ts") or "") for row in pending_rows), default="")
        db_rows: list[dict[str, Any]] = []
        if not current_ts:
            with self.repo.conn() as con:
                latest_cur = con.execute(
                    """
                    SELECT MAX(ts) AS latest_ts
                    FROM signals
                    WHERE scope_market_id IS NOT NULL
                      AND scope_market_id <> ''
                      AND lower(agent_id) LIKE 'scout%'
                    """
                )
                try:
                    latest = latest_cur.fetchone()
                except Exception:
                    latest_rows = latest_cur.fetchall()
                    latest = latest_rows[0] if latest_rows else None
                if latest is not None:
                    try:
                        current_ts = str(latest["latest_ts"] or "").strip()
                    except Exception:
                        current_ts = ""
                if current_ts:
                    db_rows = con.execute(
                        """
                        SELECT
                          rowid AS signal_rowid,
                          ts AS signal_ts,
                          scope_market_id AS market_id,
                          claim_json,
                          features_json,
                          'signals.latest_scout_generation' AS signal_origin
                        FROM signals
                        WHERE scope_market_id IS NOT NULL
                          AND scope_market_id <> ''
                          AND lower(agent_id) LIKE 'scout%'
                          AND ts = ?
                        ORDER BY rowid DESC
                        """,
                        (current_ts,),
                    ).fetchall()
        else:
            with self.repo.conn() as con:
                db_rows = con.execute(
                    """
                    SELECT
                      rowid AS signal_rowid,
                      ts AS signal_ts,
                      scope_market_id AS market_id,
                      claim_json,
                      features_json,
                      'signals.latest_scout_generation' AS signal_origin
                    FROM signals
                    WHERE scope_market_id IS NOT NULL
                      AND scope_market_id <> ''
                      AND lower(agent_id) LIKE 'scout%'
                      AND ts = ?
                    ORDER BY rowid DESC
                    """,
                    (current_ts,),
                ).fetchall()
        rows = [row for row in pending_rows if str(row.get("signal_ts") or "") == current_ts]
        rows.extend(db_rows or [])
        return rows

    def _live_stage0_ranked_candidate_pool(self) -> list[dict[str, Any]]:
        try:
            pool_n = _scout_pool_size()
            arb_threshold = _paper_min_similarity()
            mm_threshold = _mm_threshold()
            mode = str(getattr(self.settings, "execution_mode", "paper") or "paper").strip().lower()
            live_human_limit = mode == "live_stage0" and self._live_exec_style() == "human_limit"
            if live_human_limit:
                rows = self._live_stage0_current_generation_rows()
            else:
                with self.repo.conn() as con:
                    rows = con.execute(
                        f"""
                        SELECT
                          rowid AS signal_rowid,
                          ts AS signal_ts,
                          scope_market_id AS market_id,
                          claim_json,
                          features_json
                        FROM signals
                        WHERE scope_market_id IS NOT NULL
                          AND scope_market_id <> ''
                          AND lower(agent_id) LIKE 'scout%'
                        ORDER BY ts DESC, rowid DESC
                        LIMIT {int(pool_n)}
                        """
                    ).fetchall()
            ranked: list[dict[str, Any]] = []
            for row in rows or []:
                market_id = str(row["market_id"] or "").strip()
                if not market_id:
                    continue
                strategy = _parse_strategy_kind(row["claim_json"])
                similarity = _parse_similarity(row["features_json"], row["claim_json"])
                mm_payload = _parse_mm_payload(row["features_json"], row["claim_json"])
                score: float | None
                if strategy == "MM":
                    score = self._safe_float(mm_payload.get("mm_score"))
                    if score is None or float(score) < float(mm_threshold):
                        continue
                else:
                    score = similarity
                    if score is None or float(score) < float(arb_threshold):
                        continue
                rowid_raw = str(row["signal_rowid"] or "").strip()
                ts_raw = str(row["signal_ts"] or "").strip()
                if rowid_raw:
                    consumed_key = f"rowid:{rowid_raw}"
                elif ts_raw:
                    consumed_key = f"ts:{ts_raw}|ref:{market_id}"
                else:
                    consumed_key = f"ref:{market_id}"
                try:
                    rowid_num = int(row["signal_rowid"])
                except Exception:
                    rowid_num = 0
                candidate = {
                    "ref_id": market_id,
                    "consumed_key": consumed_key,
                    "opportunity_key": _parse_opportunity_key(row["claim_json"]),
                    "similarity": float(similarity) if similarity is not None else None,
                    "score": float(score),
                    "strategy": strategy,
                    "paper_reason": "TOP_MM_CANDIDATE" if strategy == "MM" else "TOP_SCOUT_CANDIDATE",
                    "strategy_action": "OPEN_MM" if strategy == "MM" else "OPEN_ARB",
                    "ts": ts_raw,
                    "rowid": rowid_num,
                    "source": str(
                        row["signal_origin"]
                        if "signal_origin" in row.keys()
                        else "signals.recent_scout_pool_ranked_by_similarity_ts_rowid"
                    ),
                    "mm_bid": self._safe_float(mm_payload.get("bid")),
                    "mm_ask": self._safe_float(mm_payload.get("ask")),
                    "mm_mid": self._safe_float(mm_payload.get("mid")),
                    "mm_spread": self._safe_float(mm_payload.get("spread")),
                    "mm_bid_size": self._safe_float(mm_payload.get("bid_size")),
                    "mm_ask_size": self._safe_float(mm_payload.get("ask_size")),
                    "mm_liquidity": self._safe_float(mm_payload.get("liquidity")),
                    "mm_score": self._safe_float(mm_payload.get("mm_score")),
                    "mm_quote_mode": str(mm_payload.get("quote_mode") or "TWO_SIDED").strip().upper() or "TWO_SIDED",
                    "mm_post_side": str(mm_payload.get("post_side") or "BOTH").strip().upper() or "BOTH",
                }
                if mode == "live_stage0" and self._live_exec_style() == "human_limit":
                    token_id = self._resolve_stage0_token_id(market_id, "YES")
                    reason, ref_bid, ref_ask, eff_spread = self._live_stage0_market_untradeable_reason(
                        market_id,
                        "YES",
                        token_id,
                    )
                    if reason:
                        if strategy == "MM" and self._mm_probe_allow_untradeable():
                            candidate["mm_probe_bypass_untradeable"] = 1
                            candidate["mm_probe_untradeable_reason"] = reason
                            candidate["mm_probe_ref_bid"] = ref_bid
                            candidate["mm_probe_ref_ask"] = ref_ask
                            candidate["mm_probe_ref_spread"] = eff_spread
                            diag = getattr(self, "_iter_decision_diag", None)
                            if isinstance(diag, dict):
                                diag["mm_probe_bypass_untradeable"] = int(
                                    diag.get("mm_probe_bypass_untradeable", 0) or 0
                                ) + 1
                            log.info(
                                "MM_PROBE_BYPASS_UNTRADEABLE market_id=%s reason=%s bid=%s ask=%s spread=%s",
                                market_id,
                                reason,
                                "-" if ref_bid is None else f"{ref_bid:.6f}",
                                "-" if ref_ask is None else f"{ref_ask:.6f}",
                                "-" if eff_spread is None else f"{eff_spread:.6f}",
                            )
                        else:
                            log.info(
                                "LIVE_STAGE0_CANDIDATE_FILTERED opportunity_key=%s market_id=%s token_id=%s reason=%s bid=%s ask=%s spread=%s",
                                str(candidate.get("opportunity_key") or "").strip() or "-",
                                market_id,
                                token_id or "-",
                                reason,
                                "-" if ref_bid is None else f"{ref_bid:.6f}",
                                "-" if ref_ask is None else f"{ref_ask:.6f}",
                                "-" if eff_spread is None else f"{eff_spread:.6f}",
                            )
                            continue
                ranked.append(candidate)
            ranked.sort(
                key=lambda c: (
                    1 if str(c.get("strategy") or "ARB").strip().upper() == "ARB" else 0,
                    float(c.get("score", -1.0)),
                    str(c.get("ts") or ""),
                    int(c.get("rowid") or 0),
                ),
                reverse=True,
            )
            if live_human_limit and ranked:
                ranked = ranked[: int(pool_n)]
            return ranked
        except Exception:
            log.exception("LIVE_STAGE0_CANDIDATE_FALLBACK_POOL_FAIL")
            return []

    def _mm_final_probe_candidates(self, ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mm_candidates = [
            cand for cand in (ranked or [])
            if str(cand.get("strategy") or "").strip().upper() == "MM" and cand.get("mm_score") is not None
        ]
        mm_candidates.sort(
            key=lambda cand: (
                float(cand.get("mm_score") or -1.0),
                float(cand.get("mm_spread") or -1.0),
                str(cand.get("ts") or ""),
                int(cand.get("rowid") or 0),
            ),
            reverse=True,
        )
        selected: list[dict[str, Any]] = []
        for idx, cand in enumerate(mm_candidates[:3], start=1):
            out = dict(cand)
            out["mm_final_probe_rank"] = idx
            selected.append(out)
            log.info(
                "MM_FINAL_PROBE_SELECTED market_id=%s mm_score=%s spread=%s bid=%s ask=%s bid_size=%s ask_size=%s probe_rank=%s",
                str(out.get("ref_id") or "").strip() or "-",
                "-" if out.get("mm_score") is None else f"{float(out.get('mm_score')):.6f}",
                "-" if out.get("mm_spread") is None else f"{float(out.get('mm_spread')):.6f}",
                "-" if out.get("mm_bid") is None else f"{float(out.get('mm_bid')):.6f}",
                "-" if out.get("mm_ask") is None else f"{float(out.get('mm_ask')):.6f}",
                "-" if out.get("mm_bid_size") is None else f"{float(out.get('mm_bid_size')):.6f}",
                "-" if out.get("mm_ask_size") is None else f"{float(out.get('mm_ask_size')):.6f}",
                idx,
            )
        diag = getattr(self, "_iter_decision_diag", None)
        if isinstance(diag, dict):
            diag["mm_final_probe_candidates_seen"] = int(len(mm_candidates))
            diag["mm_final_probe_candidates_selected"] = int(len(selected))
        return selected

    def _apply_mm_final_probe(self, pipe: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(pipe or {})
        mode = str(getattr(self.settings, "execution_mode", "paper") or "paper").strip().lower()
        if mode != "live_stage0" or self._live_exec_style() != "human_limit" or not self._mm_final_probe_enabled():
            return out
        if str(out.get("paper_action", "") or "").strip().upper() == "OPEN" and str(out.get("paper_strategy", "") or "").strip().upper() == "ARB":
            return out
        ranked = self._live_stage0_ranked_candidate_pool()
        selected = self._mm_final_probe_candidates(ranked)
        if not selected:
            return out
        for cand in selected:
            market_id = str(cand.get("ref_id") or "").strip()
            if not market_id:
                continue
            outcome = "YES"
            token_id = self._resolve_stage0_token_id(market_id, outcome)
            if not token_id:
                continue
            if self._is_live_stage0_untradeable_suppressed({"opportunity_key": cand.get("opportunity_key", "")}, market_id, outcome, token_id):
                continue
            log.info(
                "MM_FINAL_PROBE_DECISION_BYPASS market_id=%s mm_score=%s original_decision=%s original_reason=%s",
                market_id,
                "-" if cand.get("mm_score") is None else f"{float(cand.get('mm_score')):.6f}",
                str(out.get("paper_action", "") or "").strip().upper() or "NONE",
                str(out.get("paper_reason", "") or "").strip().upper() or "NONE",
            )
            signature = f"OPEN|TOP_MM_CANDIDATE|{market_id}"
            return {
                **out,
                "last": "OPEN/TOP_MM_CANDIDATE",
                "paper_action": "OPEN",
                "paper_reason": "TOP_MM_CANDIDATE",
                "paper_source": f"live_stage0.final_probe.{str(cand.get('source') or 'ranked_pool')}",
                "dedup_signature": signature,
                "matched_prev_signature": "",
                "selected": 1,
                "skipped_as_stale": 0,
                "consumed_key": str(cand.get("consumed_key") or "").strip(),
                "opportunity_key": str(cand.get("opportunity_key") or "").strip(),
                "same_opportunity_as_prev": 0,
                "skipped_as_same_opportunity": 0,
                "paper_market_id": market_id,
                "cand_count": 1,
                "candidate_pool_size": len(selected),
                "paper_strategy": "MM",
                "strategy_action": "OPEN_MM",
                "cluster_mode": "MM",
                "mm_bid": cand.get("mm_bid"),
                "mm_ask": cand.get("mm_ask"),
                "mm_mid": cand.get("mm_mid"),
                "mm_spread": cand.get("mm_spread"),
                "mm_bid_size": cand.get("mm_bid_size"),
                "mm_ask_size": cand.get("mm_ask_size"),
                "mm_liquidity": cand.get("mm_liquidity"),
                "mm_score": cand.get("mm_score"),
                "mm_quote_mode": cand.get("mm_quote_mode"),
                "mm_post_side": cand.get("mm_post_side"),
                "mm_probe_bypass_untradeable": cand.get("mm_probe_bypass_untradeable", 0),
                "mm_probe_untradeable_reason": cand.get("mm_probe_untradeable_reason", ""),
                "mm_probe_ref_bid": cand.get("mm_probe_ref_bid"),
                "mm_probe_ref_ask": cand.get("mm_probe_ref_ask"),
                "mm_probe_ref_spread": cand.get("mm_probe_ref_spread"),
                "mm_final_probe": 1,
                "mm_final_probe_rank": cand.get("mm_final_probe_rank"),
            }
        return out

    def _apply_live_stage0_candidate_fallback(self, pipe: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(pipe or {})
        mode = str(getattr(self.settings, "execution_mode", "paper") or "paper").strip().lower()
        if mode != "live_stage0" or self._live_exec_style() != "human_limit":
            return out
        if self._mm_final_probe_enabled():
            return self._apply_mm_final_probe(out)

        action = str(out.get("paper_action", "") or "").strip().upper()
        reason = str(out.get("paper_reason", "") or "").strip().upper()
        if action not in {"OPEN", "HOLD"}:
            return out
        if int(out.get("open_blocked_by_freshness", 0) or 0) > 0:
            return out
        if str(out.get("freshness_reason", "NONE") or "NONE").strip().upper() == "FRESHNESS_WARN_OPEN_BLOCKED":
            return out

        current_market_id = self._parse_open_market_id_from_pipe(out)
        current_consumed_key = str(out.get("consumed_key", "") or "").strip()
        current_opportunity_key = str(out.get("opportunity_key", "") or "").strip()
        prev_consumed_key = str(getattr(self, "_paper_pipeline_ctx", {}).get("last_consumed_scout_key") or "").strip()
        prev_opportunity_key = str(getattr(self, "_paper_pipeline_ctx", {}).get("last_consumed_opportunity_key") or "").strip()

        ranked = self._live_stage0_ranked_candidate_pool()
        if not ranked:
            fallback_reason = "NO_USABLE_LIVE_CANDIDATES"
            if action == "HOLD" and reason and reason not in {"TOP_SCOUT_CANDIDATE", "TOP_MM_CANDIDATE", "DEDUP", "NO_DECISION"}:
                fallback_reason = reason
            return {
                **out,
                "last": f"HOLD/{fallback_reason}",
                "paper_action": "HOLD",
                "paper_reason": fallback_reason,
                "paper_source": "live_stage0.filtered_ranked_pool_empty",
                "selected": 0,
            }

        last_reject_reason = reason if action == "HOLD" else ""
        for idx, cand in enumerate(ranked, start=1):
            market_id = str(cand.get("ref_id") or "").strip()
            consumed_key = str(cand.get("consumed_key") or "").strip()
            opportunity_key = str(cand.get("opportunity_key") or "").strip()
            if not market_id:
                continue
            reject_reason = ""
            if current_consumed_key and consumed_key and consumed_key == current_consumed_key:
                reject_reason = reason or "CURRENT_CANDIDATE_REJECTED"
            elif current_market_id and market_id == current_market_id and current_opportunity_key and opportunity_key == current_opportunity_key:
                reject_reason = reason or "CURRENT_CANDIDATE_REJECTED"
            elif prev_consumed_key and consumed_key and consumed_key == prev_consumed_key:
                reject_reason = "STALE_CANDIDATE_SKIPPED"
            elif opportunity_key and prev_opportunity_key and opportunity_key == prev_opportunity_key:
                reject_reason = "SAME_OPPORTUNITY_SKIPPED"
            else:
                outcome = "YES"
                token_id = self._resolve_stage0_token_id(market_id, outcome)
                if not token_id:
                    reject_reason = "MISSING_TOKEN_ID"
                elif self._is_live_stage0_untradeable_suppressed({"opportunity_key": opportunity_key}, market_id, outcome, token_id):
                    reject_reason = "UNTRADEABLE_COOLDOWN"
                elif not self._is_live_stage0_market_tradeable(market_id, outcome, token_id):
                    self._record_live_stage0_untradeable_suppression(
                        {"opportunity_key": opportunity_key},
                        market_id,
                        outcome,
                        token_id,
                        reason="UNTRADEABLE_MARKET",
                    )
                    reject_reason = "UNTRADEABLE_MARKET"
                else:
                    paper_reason = str(cand.get("paper_reason") or "TOP_SCOUT_CANDIDATE").strip().upper() or "TOP_SCOUT_CANDIDATE"
                    signature = f"OPEN|{paper_reason}|{market_id}"
                    ctx = getattr(self, "_paper_pipeline_ctx", None)
                    if isinstance(ctx, dict):
                        ctx["last_signature"] = signature
                        ctx["last_consumed_scout_key"] = consumed_key
                        ctx["last_consumed_opportunity_key"] = opportunity_key
                        ctx["cluster_mode"] = "MM" if paper_reason == "TOP_MM_CANDIDATE" else "ARB"
                    log.info(
                        "LIVE_STAGE0_CANDIDATE_FALLBACK opportunity_key=%s market_id=%s fallback_index=%s selected=1",
                        opportunity_key or "-",
                        market_id,
                        idx,
                    )
                    return {
                        **out,
                        "last": f"OPEN/{paper_reason}",
                        "paper_action": "OPEN",
                        "paper_reason": paper_reason,
                        "paper_source": f"live_stage0.fallback.{str(cand.get('source') or 'ranked_pool')}",
                        "dedup_signature": signature,
                        "matched_prev_signature": "",
                        "selected": 1,
                        "skipped_as_stale": 0,
                        "consumed_key": consumed_key,
                        "opportunity_key": opportunity_key,
                        "same_opportunity_as_prev": 0,
                        "skipped_as_same_opportunity": 0,
                        "paper_market_id": market_id,
                        "cand_count": 1,
                        "candidate_pool_size": len(ranked),
                        "paper_strategy": str(cand.get("strategy") or "ARB").strip().upper() or "ARB",
                        "strategy_action": str(cand.get("strategy_action") or "OPEN_ARB"),
                        "cluster_mode": "MM" if paper_reason == "TOP_MM_CANDIDATE" else "ARB",
                        "mm_bid": cand.get("mm_bid"),
                        "mm_ask": cand.get("mm_ask"),
                        "mm_mid": cand.get("mm_mid"),
                        "mm_spread": cand.get("mm_spread"),
                        "mm_bid_size": cand.get("mm_bid_size"),
                        "mm_ask_size": cand.get("mm_ask_size"),
                        "mm_liquidity": cand.get("mm_liquidity"),
                        "mm_score": cand.get("mm_score"),
                        "mm_quote_mode": cand.get("mm_quote_mode"),
                        "mm_post_side": cand.get("mm_post_side"),
                        "mm_probe_bypass_untradeable": cand.get("mm_probe_bypass_untradeable", 0),
                        "mm_probe_untradeable_reason": cand.get("mm_probe_untradeable_reason", ""),
                        "mm_probe_ref_bid": cand.get("mm_probe_ref_bid"),
                        "mm_probe_ref_ask": cand.get("mm_probe_ref_ask"),
                        "mm_probe_ref_spread": cand.get("mm_probe_ref_spread"),
                    }
            last_reject_reason = reject_reason or last_reject_reason
            log.info(
                "LIVE_STAGE0_CANDIDATE_REJECTED opportunity_key=%s market_id=%s reject_reason=%s fallback_index=%s",
                opportunity_key or "-",
                market_id,
                reject_reason or "REJECTED",
                idx,
            )
        fallback_reason = last_reject_reason or "NO_USABLE_LIVE_CANDIDATES"
        return {
            **out,
            "last": f"HOLD/{fallback_reason}",
            "paper_action": "HOLD",
            "paper_reason": fallback_reason,
            "paper_source": "live_stage0.filtered_ranked_pool_exhausted",
            "selected": 0,
            "candidate_pool_size": len(ranked),
        }

    def _maybe_submit_stage0_open_from_pipeline(self, now: datetime) -> int:
        mode = str(getattr(self.settings, "execution_mode", "paper") or "paper").strip().lower()
        exec_style = self._live_exec_style()
        pipe = self._iter_pipe or {}
        action = str(pipe.get("paper_action", "") or "").strip().upper()
        signature = str(pipe.get("dedup_signature", "") or "").strip()
        strategy = str(pipe.get("paper_strategy") or "").strip().upper()
        if not strategy:
            strategy = "MM" if str(pipe.get("paper_reason") or "").strip().upper() == "TOP_MM_CANDIDATE" else "ARB"
        log.info(
            "PIPE_OPEN_BRIDGE_ENTER mode=%s style=%s action=%s dedup_signature=%s",
            mode or "-",
            exec_style,
            action or "NONE",
            signature or "-",
        )
        if mode != "live_stage0":
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=MODE_NOT_LIVE_STAGE0 mode=%s", mode or "-")
            return 0
        executor = getattr(self, "executor", None)
        if executor is None or not callable(getattr(executor, "place_order", None)):
            log.warning("PIPE_OPEN_BRIDGE_SKIP reason=EXECUTOR_UNAVAILABLE")
            return 0

        if action != "OPEN":
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=PIPE_ACTION_NOT_OPEN action=%s", action or "NONE")
            return 0

        if signature and signature == str(self._live_stage0_last_submit_signature or ""):
            if strategy == "MM":
                log.info(
                    "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=DEDUP",
                    str(pipe.get("paper_market_id") or "").strip() or "-",
                    "-" if pipe.get("mm_score") is None else f"{float(pipe.get('mm_score')):.6f}",
                    float(_mm_threshold()),
                )
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=DEDUP_SIGNATURE signature=%s", signature)
            return 0

        market_id = self._parse_open_market_id_from_pipe(pipe)
        if not market_id:
            log.warning("PIPE_OPEN_BRIDGE_SKIP reason=MISSING_MARKET_ID")
            return 0
        outcome = str(pipe.get("paper_outcome", "YES") or "YES").strip().upper() or "YES"

        gate = getattr(self.decision_engine, "_risk_gate", None)
        if gate is not None:
            try:
                verdict = gate.check_market(market_id)
                if verdict is not None and not getattr(verdict, "allow", True):
                    if strategy == "MM":
                        log.info(
                            "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=RISK_BLOCK",
                            market_id,
                            "-" if pipe.get("mm_score") is None else f"{float(pipe.get('mm_score')):.6f}",
                            float(_mm_threshold()),
                        )
                    log.info(
                        "PIPE_OPEN_BRIDGE_SKIP reason=RISK_GATE_BLOCK market_id=%s risk_kind=%s code=%s",
                        market_id,
                        str(getattr(verdict, "kind", "NONE") or "NONE").strip().upper() or "NONE",
                        str(getattr(verdict, "code", "GATE") or "GATE").strip().upper() or "GATE",
                    )
                    return 0
            except Exception:
                log.exception("PIPE_OPEN_BRIDGE_SKIP reason=RISK_GATE_CHECK_FAILED market_id=%s", market_id)
                return 0

        token_id = self._resolve_stage0_token_id(market_id, outcome)
        if not token_id:
            log.warning("PIPE_OPEN_BRIDGE_SKIP reason=MISSING_TOKEN_ID market_id=%s outcome=%s", market_id, outcome)
            return 0

        if strategy == "MM":
            log.info(
                "OPEN_MM_SELECTED market_id=%s mm_score=%s spread=%s bid_size=%s ask_size=%s",
                market_id,
                "-" if pipe.get("mm_score") is None else f"{float(pipe.get('mm_score')):.6f}",
                "-" if pipe.get("mm_spread") is None else f"{float(pipe.get('mm_spread')):.6f}",
                "-" if pipe.get("mm_bid_size") is None else f"{float(pipe.get('mm_bid_size')):.6f}",
                "-" if pipe.get("mm_ask_size") is None else f"{float(pipe.get('mm_ask_size')):.6f}",
            )
            return self._submit_live_stage0_mm_orders(
                now=now,
                executor=executor,
                pipe=pipe,
                signature=signature,
                market_id=market_id,
                outcome=outcome,
                token_id=token_id,
                exec_style=exec_style,
            )

        ttl_seconds = 0.0
        if exec_style == "human_limit":
            if self._is_live_stage0_untradeable_suppressed(pipe, market_id, outcome, token_id):
                log.info(
                    "PIPE_OPEN_BRIDGE_SKIP reason=UNTRADEABLE_COOLDOWN market_id=%s outcome=%s token_id=%s",
                    market_id,
                    outcome,
                    token_id,
                )
                return 0
            if not self._is_live_stage0_market_tradeable(market_id, outcome, token_id):
                self._record_live_stage0_untradeable_suppression(
                    pipe,
                    market_id,
                    outcome,
                    token_id,
                    reason="UNTRADEABLE_MARKET",
                )
                log.info(
                    "PIPE_OPEN_BRIDGE_SKIP reason=UNTRADEABLE_MARKET market_id=%s outcome=%s token_id=%s",
                    market_id,
                    outcome,
                    token_id,
                )
                return 0
            plan = self._build_human_limit_order_plan(market_id, outcome, token_id)
            if plan is None:
                log.info(
                    "PIPE_OPEN_BRIDGE_SKIP reason=HUMAN_LIMIT_BLOCKED market_id=%s outcome=%s token_id=%s",
                    market_id,
                    outcome,
                    token_id,
                )
                return 0
            price = float(plan["price"])
            qty = float(plan["qty"])
            notional = float(plan["notional"])
            ttl_seconds = float(plan["ttl_seconds"])
        else:
            price = self._resolve_stage0_order_price(market_id, outcome, token_id=token_id)
            if price is None:
                log.warning("PIPE_OPEN_BRIDGE_SKIP reason=MISSING_PRICE market_id=%s outcome=%s token_id=%s", market_id, outcome, token_id)
                return 0
            qty = self._resolve_stage0_order_qty(price)
            if qty is None:
                log.warning("PIPE_OPEN_BRIDGE_SKIP reason=BAD_QTY market_id=%s outcome=%s token_id=%s", market_id, outcome, token_id)
                return 0
            notional = float(qty) * float(price)

        log.info(
            "PIPE_OPEN_BRIDGE_RESOLVED market_id=%s token_id=%s outcome=%s style=%s price=%.6f qty=%.6f notional=%.6f",
            market_id,
            token_id,
            outcome,
            exec_style,
            price,
            qty,
            notional,
        )
        log.info(
            "PIPE_OPEN_BRIDGE_SUBMIT_ATTEMPT market_id=%s token_id=%s outcome=%s qty=%.6f price=%.6f notional=%.6f",
            market_id,
            token_id,
            outcome,
            qty,
            price,
            notional,
        )
        try:
            order_id = executor.place_order(
                market_id=token_id,
                outcome=outcome,
                side="BUY",
                qty=qty,
                limit_price=price,
                ttl_seconds=ttl_seconds,
                execution_style=exec_style,
                metadata={
                    "market_id": market_id,
                    "token_id": token_id,
                    "single_leg_smoke_mode": int(exec_style == "human_limit"),
                },
            )
            self._live_stage0_last_submit_signature = signature or f"OPEN|{market_id}|{outcome}"
            log.info(
                "PIPE_OPEN_BRIDGE_SUBMIT_OK market_id=%s token_id=%s outcome=%s style=%s order_id=%s",
                market_id,
                token_id,
                outcome,
                exec_style,
                str(order_id or "-")[:128],
            )
            self._queue_event(
                ts=now,
                level="INFO",
                component="live_stage0",
                message="order_submit_attempted",
                payload={"market_id": market_id, "token_id": token_id, "outcome": outcome, "style": exec_style},
            )
            return 1
        except Exception as e:
            safe_error = f"{type(e).__name__}: {e}"
            log.warning(
                "PIPE_OPEN_BRIDGE_SUBMIT_FAIL market_id=%s token_id=%s outcome=%s safe_error=%s",
                market_id,
                token_id,
                outcome,
                safe_error,
            )
            return 0

    def _submit_live_stage0_mm_orders(
        self,
        *,
        now: datetime,
        executor: Any,
        pipe: Dict[str, Any],
        signature: str,
        market_id: str,
        outcome: str,
        token_id: str,
        exec_style: str,
    ) -> int:
        if exec_style != "human_limit":
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_REQUIRES_HUMAN_LIMIT market_id=%s", market_id)
            return 0
        bid = self._safe_float(pipe.get("mm_bid"))
        ask = self._safe_float(pipe.get("mm_ask"))
        mid = self._safe_float(pipe.get("mm_mid"))
        spread = self._safe_float(pipe.get("mm_spread"))
        bid_size = self._safe_float(pipe.get("mm_bid_size"))
        ask_size = self._safe_float(pipe.get("mm_ask_size"))
        liquidity = self._safe_float(pipe.get("mm_liquidity"))
        quote_mode = str(pipe.get("mm_quote_mode") or "TWO_SIDED").strip().upper() or "TWO_SIDED"
        post_side = str(pipe.get("mm_post_side") or "BOTH").strip().upper() or "BOTH"
        probe_bypass = int(pipe.get("mm_probe_bypass_untradeable", 0) or 0) > 0 and self._mm_probe_allow_untradeable()
        final_probe = int(pipe.get("mm_final_probe", 0) or 0) > 0 and self._mm_final_probe_enabled()
        if liquidity is None:
            sizes = [float(size) for size in (bid_size, ask_size) if size is not None and float(size) > 0.0]
            liquidity = min(sizes) if sizes else None
        if mid is None or spread is None or liquidity is None:
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_MISSING_QUOTE market_id=%s", market_id)
            return 0
        if final_probe:
            side = "BUY" if ask is not None else "SELL" if bid is not None else ""
            if not side:
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_FINAL_PROBE_MISSING_SIDE market_id=%s", market_id)
                return 0
            price = self._clamp_price(float(mid) - (float(spread) * 0.25)) if side == "BUY" else self._clamp_price(float(mid) + (float(spread) * 0.25))
            if not (0.0 < price < 1.0):
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_BAD_PRICES market_id=%s buy_sell_price=%.6f", market_id, price)
                return 0
            min_submit_notional = self._env_float("PS_LIVE_HUMAN_MIN_NOTIONAL", 2.0)
            target_notional = max(2.0, float(min_submit_notional))
            risk_cfg = getattr(self.settings, "risk", None)
            cap_candidates = [
                self._safe_float(getattr(self.settings, "live_max_notional", None)),
                self._safe_float(getattr(risk_cfg, "max_notional_total", None)),
            ]
            positive_caps = [x for x in cap_candidates if x is not None and x > 0.0]
            available_capital = min(positive_caps) if positive_caps else target_notional
            if available_capital < target_notional:
                log.info(
                    "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=NO_CAPITAL",
                    market_id,
                    "-" if pipe.get("mm_score") is None else f"{float(pipe.get('mm_score')):.6f}",
                    float(_mm_threshold()),
                )
                return 0
            qty = target_notional / float(price)
            notional = float(qty) * float(price)
            diag = getattr(self, "_iter_decision_diag", None)
            if isinstance(diag, dict):
                diag["mm_final_probe_orders_attempted"] = int(diag.get("mm_final_probe_orders_attempted", 0) or 0) + 1
            log.info(
                "MM_FINAL_PROBE_ORDER market_id=%s side=%s price=%.6f qty=%.6f notional=%.6f ttl_sec=45.000",
                market_id,
                side,
                price,
                qty,
                notional,
            )
            log.info(
                "MM_ORDER_PLACE market_id=%s token_id=%s side=%s price=%.6f qty=%.6f ttl_seconds=45.000",
                market_id,
                token_id,
                side,
                price,
                qty,
            )
            try:
                order_id = executor.place_order(
                    market_id=token_id,
                    outcome=outcome,
                    side=side,
                    qty=qty,
                    limit_price=price,
                    ttl_seconds=45.0,
                    execution_style=exec_style,
                    metadata={
                        "market_id": market_id,
                        "token_id": token_id,
                        "single_leg_smoke_mode": 1,
                        "strategy": "MM",
                        "leg_side": side,
                        "final_probe": 1,
                    },
                )
            except Exception:
                if isinstance(diag, dict):
                    diag["mm_final_probe_orders_failed"] = int(diag.get("mm_final_probe_orders_failed", 0) or 0) + 1
                raise
            if isinstance(diag, dict):
                diag["mm_orders_placed"] = int(diag.get("mm_orders_placed", 0) or 0) + 1
            self._live_stage0_last_submit_signature = ""
            log.info(
                "MM_ORDER_PLACE_OK market_id=%s token_id=%s side=%s order_id=%s price=%.6f qty=%.6f",
                market_id,
                token_id,
                side,
                str(order_id or "-")[:128],
                price,
                qty,
            )
            self._queue_event(
                ts=now,
                level="INFO",
                component="live_stage0",
                message="mm_final_probe_order_submit_attempted",
                payload={"market_id": market_id, "token_id": token_id, "outcome": outcome, "style": exec_style},
            )
            return 1
        min_bid = self._env_float("PS_MM_MIN_BID", 0.001)
        max_ask = self._env_float("PS_MM_MAX_ASK", 0.999)
        max_spread = self._env_float("PS_MM_MAX_SPREAD", 0.5)
        if float(spread) < 0.02 or float(spread) > float(max_spread):
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_WIDE_SPREAD market_id=%s token_id=%s spread=%.6f max_spread=%.6f", market_id, token_id, float(spread), float(max_spread))
            return 0
        if quote_mode == "TWO_SIDED":
            if bid is None or ask is None:
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_MISSING_QUOTE market_id=%s", market_id)
                return 0
            if not (0.0 < float(bid) < float(ask) < 1.0):
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_INVALID_BOOK market_id=%s token_id=%s", market_id, token_id)
                return 0
            if float(bid) <= float(min_bid) or float(ask) >= float(max_ask):
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_BOUNDARY_BOOK market_id=%s token_id=%s", market_id, token_id)
                return 0
        elif quote_mode == "ASK_ONLY":
            if ask is None or not (0.0 < float(ask) < 1.0):
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_INVALID_BOOK market_id=%s token_id=%s", market_id, token_id)
                return 0
            if float(ask) >= float(max_ask):
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_BOUNDARY_BOOK market_id=%s token_id=%s", market_id, token_id)
                return 0
            post_side = "BUY"
        elif quote_mode == "BID_ONLY":
            if bid is None or not (0.0 < float(bid) < 1.0):
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_INVALID_BOOK market_id=%s token_id=%s", market_id, token_id)
                return 0
            if float(bid) <= float(min_bid):
                log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_BOUNDARY_BOOK market_id=%s token_id=%s", market_id, token_id)
                return 0
            post_side = "SELL"
        else:
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_INVALID_MODE market_id=%s quote_mode=%s", market_id, quote_mode)
            return 0
        if probe_bypass:
            post_side = self._mm_probe_post_side(pipe)
            log.info("MM_PROBE_POST_SIDE side=%s market_id=%s", post_side, market_id)
        try:
            base_notional = float(getattr(self.settings, "paper_fixed_notional", 0.0) or 0.0)
        except Exception:
            base_notional = 0.0
        if base_notional <= 0.0:
            base_notional = 1.0
        base_size = float(base_notional) / float(mid)
        size = min(float(base_size), float(liquidity) * 0.2)
        if size <= 0.0:
            log.info(
                "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=NO_CAPITAL",
                market_id,
                "-" if pipe.get("mm_score") is None else f"{float(pipe.get('mm_score')):.6f}",
                float(_mm_threshold()),
            )
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_BAD_SIZE market_id=%s liquidity=%s", market_id, liquidity)
            return 0
        buy_price = self._clamp_price(float(mid) - (float(spread) * 0.25))
        sell_price = self._clamp_price(float(mid) + (float(spread) * 0.25))
        if not (0.0 < buy_price < float(mid) < sell_price < 1.0):
            log.info("PIPE_OPEN_BRIDGE_SKIP reason=MM_BAD_PRICES market_id=%s buy=%.6f mid=%.6f sell=%.6f", market_id, buy_price, float(mid), sell_price)
            return 0
        ctx = getattr(self, "_paper_pipeline_ctx", None)
        if isinstance(ctx, dict) and str(ctx.get("cluster_mode") or "NONE").strip().upper() == "MM":
            log.info(
                "MM_REPRICE market_id=%s token_id=%s buy_price=%.6f sell_price=%.6f size=%.6f",
                market_id,
                token_id,
                buy_price,
                sell_price,
                size,
            )
        placed = 0
        sides_and_prices = [("BUY", buy_price), ("SELL", sell_price)]
        if post_side == "BUY":
            sides_and_prices = [("BUY", buy_price)]
        elif post_side == "SELL":
            sides_and_prices = [("SELL", sell_price)]
        for side, price in sides_and_prices:
            diag = getattr(self, "_iter_decision_diag", None)
            if isinstance(diag, dict):
                diag["mm_probe_orders_attempted"] = int(diag.get("mm_probe_orders_attempted", 0) or 0) + 1
            log.info(
                "MM_ORDER_PLACE market_id=%s token_id=%s side=%s price=%.6f qty=%.6f ttl_seconds=30.000",
                market_id,
                token_id,
                side,
                price,
                size,
            )
            try:
                order_id = executor.place_order(
                    market_id=token_id,
                    outcome=outcome,
                    side=side,
                    qty=size,
                    limit_price=price,
                    ttl_seconds=30.0,
                    execution_style=exec_style,
                    metadata={
                        "market_id": market_id,
                        "token_id": token_id,
                        "single_leg_smoke_mode": 0,
                        "strategy": "MM",
                        "leg_side": side,
                    },
                )
            except Exception:
                if isinstance(diag, dict):
                    diag["mm_probe_orders_failed"] = int(diag.get("mm_probe_orders_failed", 0) or 0) + 1
                log.info(
                    "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=NO_CAPITAL",
                    market_id,
                    "-" if pipe.get("mm_score") is None else f"{float(pipe.get('mm_score')):.6f}",
                    float(_mm_threshold()),
                )
                raise
            placed += 1
            if isinstance(diag, dict):
                diag["mm_orders_placed"] = int(diag.get("mm_orders_placed", 0) or 0) + 1
            log.info(
                "MM_ORDER_PLACE_OK market_id=%s token_id=%s side=%s order_id=%s price=%.6f qty=%.6f",
                market_id,
                token_id,
                side,
                str(order_id or "-")[:128],
                price,
                size,
            )
        if isinstance(ctx, dict):
            ctx["cluster_mode"] = "MM"
        # Allow the next loop to recompute and replace after TTL expiry.
        self._live_stage0_last_submit_signature = ""
        self._queue_event(
            ts=now,
            level="INFO",
            component="live_stage0",
            message="mm_order_submit_attempted",
            payload={"market_id": market_id, "token_id": token_id, "outcome": outcome, "style": exec_style},
        )
        return 1 if placed > 0 else 0

    def _maybe_release_stage0_candidate_suppression(self) -> None:
        mode = str(getattr(self.settings, "execution_mode", "paper") or "paper").strip().lower()
        if mode != "live_stage0":
            return
        if str(self._live_stage0_last_submit_signature or "").strip():
            return
        pipe = self._iter_pipe or {}
        action = str(pipe.get("paper_action", "") or "").strip().upper()
        reason = str(pipe.get("paper_reason", "") or "").strip().upper()
        if action != "HOLD":
            return
        if reason not in {"SAME_OPPORTUNITY_SKIPPED", "STALE_CANDIDATE_SKIPPED"}:
            return
        ctx = getattr(self, "_paper_pipeline_ctx", None)
        if not isinstance(ctx, dict):
            return
        if not any(
            str(ctx.get(k) or "").strip()
            for k in ("last_signature", "last_consumed_scout_key", "last_consumed_opportunity_key")
        ):
            return
        ctx["last_signature"] = ""
        ctx["last_consumed_scout_key"] = ""
        ctx["last_consumed_opportunity_key"] = ""
        log.info(
            "LIVE_STAGE0_PIPELINE_UNLOCK reason=NO_SUCCESSFUL_SUBMIT_YET hold_reason=%s",
            reason,
        )

    def _resolve_ingest_block_guard(self, eligible_for_ingest: bool) -> tuple[bool, bool]:
        raw_block = self._ingest_max_block_ms > 0 and self._last_ingest_wall_ms > self._ingest_max_block_ms
        if not raw_block:
            self._ingest_block_guard_skips = 0
            return False, False
        if not eligible_for_ingest:
            return True, False
        self._ingest_block_guard_skips = int(self._ingest_block_guard_skips or 0) + 1
        if self._ingest_block_guard_skips >= int(self._ingest_block_guard_skip_cap or 1):
            self._ingest_block_guard_skips = 0
            return False, True
        return True, False

    def _emit_freshness_diag(self, freshness: Dict[str, Any]) -> None:
        state_obj = freshness.get("state") or {}
        data_obj = state_obj.get("data") or {}
        book_obj = state_obj.get("book") or {}
        overall = str(state_obj.get("overall") or "STOP").upper()
        stale_reason = "OK" if overall == STATE_OK else f"FRESHNESS_{overall}"

        pulse_data_age_s = self._age_sec(self._last_ingest_done_utc or "")
        ingest_age_s = freshness.get("data_age_s")
        market_ts_age_s = freshness.get("market_ts_age_s")
        market_book_age_s = freshness.get("book_age_s")

        blockers: list[tuple[int, float, str, str]] = []

        def _pick(metric: str, st: str, age_s: Optional[float], warn_s: Optional[float], stop_s: Optional[float]) -> None:
            s = str(st or "").upper()
            if s not in {"WARN", "STOP"}:
                return
            age_txt = "-" if age_s is None else f"{float(age_s):.1f}"
            warn_txt = "-" if warn_s is None else f"{float(warn_s):.1f}"
            stop_txt = "-" if stop_s is None else f"{float(stop_s):.1f}"
            if age_s is None:
                over = 1e9
                expr = f"{metric}:{s}(age=none warn={warn_txt} stop={stop_txt})"
            else:
                over = (float(age_s) - float(stop_s or 0.0)) if s == "STOP" else (float(age_s) - float(warn_s or 0.0))
                expr = f"{metric}:{s}(age={age_txt} warn={warn_txt} stop={stop_txt})"
            sev = 2 if s == "STOP" else 1
            blockers.append((sev, over, metric, expr))

        _pick(
            "ingest_age",
            str(data_obj.get("state") or ""),
            data_obj.get("age_s"),
            data_obj.get("warn_s"),
            data_obj.get("stop_s"),
        )
        _pick(
            "market_book_age",
            str(book_obj.get("state") or ""),
            book_obj.get("age_s"),
            book_obj.get("warn_s"),
            book_obj.get("stop_s"),
        )
        blockers.sort(key=lambda x: (-int(x[0]), -float(x[1]), x[2]))
        winner = blockers[0][2] if blockers else "none"
        all_blockers = [b[3] for b in blockers]
        log.info(
            "FRESHNESS_DIAG overall_state=%s stale_reason=%s pulse_data_age=%s ingest_age=%s market_ts_age=%s "
            "market_book_age=%s warn_s=data:%s/book:%s stop_s=data:%s/book:%s winner=%s blockers=%s",
            overall,
            stale_reason,
            self._fmt_age_s(pulse_data_age_s),
            self._fmt_age_s(ingest_age_s),
            self._fmt_age_s(market_ts_age_s),
            self._fmt_age_s(market_book_age_s),
            "-" if data_obj.get("warn_s") is None else f"{float(data_obj.get('warn_s')):.1f}",
            "-" if book_obj.get("warn_s") is None else f"{float(book_obj.get('warn_s')):.1f}",
            "-" if data_obj.get("stop_s") is None else f"{float(data_obj.get('stop_s')):.1f}",
            "-" if book_obj.get("stop_s") is None else f"{float(book_obj.get('stop_s')):.1f}",
            winner,
            all_blockers,
        )

    def _db_freshness_ages(self) -> Dict[str, Any]:
        data_age_s: Optional[float] = None
        book_age_s: Optional[float] = None
        data_ts_max = ""
        book_ts_max = ""
        data_age_src = "snapshots.updated_at(MAX)"

        def _max_col_age(table: str, col: str) -> tuple[str, Optional[float]]:
            """Get MAX(col) and compute age in seconds. Preferred over rowid-based."""
            try:
                with self.repo.conn() as con:
                    row = con.execute(
                        f"""
                        SELECT MAX({col}) AS ts,
                               (julianday('now') - julianday(MAX({col}))) * 86400.0 AS age_s
                        FROM {table}
                        WHERE {col} IS NOT NULL AND {col} <> ''
                        """
                    ).fetchone()
                if not row or not row["ts"]:
                    return "", None
                ts = str(row["ts"])
                age_raw = row["age_s"]
                if age_raw is None:
                    return ts, None
                return ts, max(0.0, float(age_raw))
            except Exception:
                return "", None

        def _rowid_latest(table: str, col: str) -> tuple[str, Optional[float]]:
            try:
                with self.repo.conn() as con:
                    row = con.execute(
                        f"""
                        SELECT {col} AS ts, (julianday('now') - julianday({col})) * 86400.0 AS age_s
                        FROM {table}
                        WHERE {col} IS NOT NULL AND {col} <> ''
                        ORDER BY rowid DESC
                        LIMIT 1
                        """
                    ).fetchone()
                if not row or not row["ts"]:
                    return "", None
                ts = str(row["ts"])
                age_raw = row["age_s"]
                if age_raw is None:
                    return ts, None
                return ts, max(0.0, float(age_raw))
            except Exception:
                return "", None

        def _update_ingest_ema(ts: str) -> None:
            if not ts:
                return
            try:
                dt = datetime.fromisoformat(str(ts))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                cur = float(dt.timestamp())
            except Exception:
                return
            prev = self._last_data_ts_epoch
            if prev is not None and cur > prev:
                delta = max(0.0, cur - prev)
                if delta <= 600.0:
                    if (self._ingest_every_ema_sec is None) or float(self._ingest_every_ema_sec) <= 0.0:
                        self._ingest_every_ema_sec = max(10.0, min(600.0, float(delta)))
                    else:
                        ema = (self._ingest_every_ema_sec * 0.8) + (delta * 0.2)
                        self._ingest_every_ema_sec = max(10.0, min(600.0, float(ema)))
            self._last_data_ts_epoch = cur

        try:
            # PRIMARY: use updated_at (wall clock written at insert time) — immune to stale API ts
            ts, age_s = _max_col_age("snapshots", "updated_at")
            if ts and age_s is not None:
                data_ts_max = ts
                data_age_s = age_s
                data_age_src = "snapshots.updated_at(MAX)"
                _update_ingest_ema(ts)
            else:
                # FALLBACK: use ts (API timestamp) by rowid
                ts, age_s = _rowid_latest("snapshots", "ts")
                if ts and age_s is not None:
                    data_ts_max = ts
                    data_age_s = age_s
                    data_age_src = "snapshots.ts(rowid)"
                    _update_ingest_ema(ts)
                else:
                    # LAST RESORT: MAX(ts)
                    ts_fallback, age_fallback = _max_col_age("snapshots", "ts")
                    if ts_fallback and age_fallback is not None:
                        data_ts_max = ts_fallback
                        data_age_s = age_fallback
                        data_age_src = "snapshots.ts(MAX)"
                        _update_ingest_ema(ts_fallback)
        except Exception:
            data_age_s = None
        # Also capture raw market ts freshness (API upstream) separately for diagnostics
        market_ts_max = ""
        market_ts_age_s: Optional[float] = None
        try:
            market_ts_max, market_ts_age_s = _max_col_age("snapshots", "ts")
        except Exception:
            pass
        try:
            ts_book, age_book = _max_col_age("orderbook_snapshots", "ts_utc")
            if ts_book and age_book is not None:
                book_ts_max = ts_book
                book_age_s = age_book
        except Exception:
            book_age_s = None
        return {
            # ingest_age_s: how long ago the pipeline last wrote (wall clock, updated_at)
            "data_age_s": data_age_s,
            "data_ts_max": data_ts_max,
            "data_age_src": data_age_src,
            # market_ts_age_s: how old the actual market data is (API ts)
            "market_ts_age_s": market_ts_age_s,
            "market_ts_max": market_ts_max,
            "book_age_s": book_age_s,
            "book_ts_max": book_ts_max,
            "book_age_src": "orderbook_snapshots.ts_utc(MAX)",
        }

    def _attach_freshness_state(self, freshness: Dict[str, Any]) -> Dict[str, Any]:
        data_age_s = freshness.get("data_age_s")
        book_age_s = freshness.get("book_age_s")
        ingest_ema_s = self._ingest_every_ema_sec
        data_warn_s = max(45.0, 2.0 * float(ingest_ema_s or 0.0))
        data_stop_s = max(90.0, 3.0 * float(ingest_ema_s or 0.0))
        if data_warn_s >= data_stop_s:
            # Existing logic provides stop threshold; derive warn explicitly when needed.
            data_warn_s = max(1.0, 0.6 * data_stop_s)
        book_warn_s = float(self.BOOK_WARN_S)
        book_stop_s = float(self.BOOK_STOP_S)

        prev_data = self._freshness_prev_state.get("data")
        prev_book = self._freshness_prev_state.get("book")
        prev_overall = self._freshness_prev_state.get("overall")

        data_state = compute_freshness_state(
            prev_state=prev_data,
            age_s=data_age_s,
            warn_s=data_warn_s,
            stop_s=data_stop_s,
            hysteresis_s=float(self.FRESHNESS_HYSTERESIS_S),
        )
        book_state = compute_freshness_state(
            prev_state=prev_book,
            age_s=book_age_s,
            warn_s=book_warn_s,
            stop_s=book_stop_s,
            hysteresis_s=float(self.FRESHNESS_HYSTERESIS_S),
        )
        overall = freshness_max_severity(data_state, book_state)

        if prev_data is not None and data_state != prev_data:
            log.info(
                "FRESHNESS_STATE data %s->%s age_s=%s warn_s=%.1f stop_s=%.1f",
                prev_data,
                data_state,
                "-" if data_age_s is None else f"{float(data_age_s):.1f}",
                float(data_warn_s),
                float(data_stop_s),
            )
        if prev_book is not None and book_state != prev_book:
            log.info(
                "FRESHNESS_STATE book %s->%s age_s=%s warn_s=%.1f stop_s=%.1f",
                prev_book,
                book_state,
                "-" if book_age_s is None else f"{float(book_age_s):.1f}",
                float(book_warn_s),
                float(book_stop_s),
            )
        if prev_overall is not None and overall != prev_overall:
            log.info("FRESHNESS_STATE overall=%s data=%s book=%s", overall, data_state, book_state)

        self._freshness_prev_state["data"] = data_state
        self._freshness_prev_state["book"] = book_state
        self._freshness_prev_state["overall"] = overall

        freshness["state"] = {
            "data": {
                "state": data_state,
                "age_s": data_age_s,
                "warn_s": float(data_warn_s),
                "stop_s": float(data_stop_s),
            },
            "book": {
                "state": book_state,
                "age_s": book_age_s,
                "warn_s": float(book_warn_s),
                "stop_s": float(book_stop_s),
            },
            "overall": overall,
        }
        return freshness

    def _compute_iter_freshness(self) -> Dict[str, Any]:
        if self._iter_freshness is not None:
            return self._iter_freshness

        t0 = time.perf_counter()

        ages = self._db_freshness_ages()
        freshness = self._attach_freshness_state(ages)

        self._iter_stage_ms["db"] = (
                self._iter_stage_ms.get("db", 0.0)
                + ((time.perf_counter() - t0) * 1000.0)
        )

        self._iter_freshness = freshness
        return freshness

    def _record_stage_ok(self, stage: str, now: datetime) -> None:
        self._telemetry[f"{stage}_ok"] = int(self._telemetry.get(f"{stage}_ok", 0) or 0) + 1
        done_iso = self._iso_utc(datetime.now(timezone.utc))
        self._telemetry["last_ok"][stage] = done_iso
        if stage == "ingest":
            self._last_ingest_done_utc = done_iso
        elif stage == "book":
            self._last_book_done_utc = done_iso
        elif stage == "agent":
            self._last_agent_done_utc = done_iso

    def _record_stage_error(self, stage: str, exc: Exception, now: datetime) -> None:
        self._telemetry[f"{stage}_err"] = int(self._telemetry.get(f"{stage}_err", 0) or 0) + 1
        self._iter_errs += 1
        cls = exc.__class__.__name__
        msg = str(exc).replace("\n", " ").strip()
        if len(msg) > 160:
            msg = msg[:160]
        sig = f"{cls}:{msg}"
        prev_sig = self._telemetry["error_signature"].get(stage, "")
        if sig != prev_sig:
            self._telemetry["error_signature"][stage] = sig
            self._telemetry["error_repeat"][stage] = 1
            log.exception("%s stage failed: %s", stage, msg)
        else:
            self._telemetry["error_repeat"][stage] = int(self._telemetry["error_repeat"].get(stage, 1) or 1) + 1
            rep = self._telemetry["error_repeat"][stage]
            log.warning("%s stage failed: same error x%s (%s)", stage, rep, msg)
        self._telemetry["last_error"][stage] = {
            "ts": self._iso_utc(now),
            "exc_class": cls,
            "message_short": msg,
        }

    @staticmethod
    def _extract_http_status(exc: Exception) -> Optional[int]:
        try:
            code = getattr(exc, "code", None)
            if code is not None:
                return int(code)
        except Exception:
            pass
        try:
            reason = getattr(exc, "reason", None)
            code = getattr(reason, "code", None)
            if code is not None:
                return int(code)
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_errno(exc: Exception) -> Optional[int]:
        reason = getattr(exc, "reason", None)
        for obj in (exc, reason, getattr(exc, "__cause__", None), getattr(reason, "__cause__", None) if reason is not None else None):
            if obj is None:
                continue
            win_err = getattr(obj, "winerror", None)
            if isinstance(win_err, int):
                return win_err
            err_no = getattr(obj, "errno", None)
            if isinstance(err_no, int):
                return err_no
        return None

    def _emit_loop_status(self, now: datetime, *, force: bool = False, freshness: Optional[Dict[str, Any]] = None) -> None:
        mono = time.monotonic()
        if not force and (mono - self._last_loop_log_ts) < 5.0:
            return
        self._last_loop_log_ts = mono
        errs = int(self._iter_errs or 0)
        e_ing = self._telemetry.get("last_error", {}).get("ingest")
        e_book = self._telemetry.get("last_error", {}).get("book")
        e_agent = self._telemetry.get("last_error", {}).get("agent")
        err_age_ing = self._fmt_age((e_ing or {}).get("ts", ""))
        err_age_book = self._fmt_age((e_book or {}).get("ts", ""))
        err_age_agent = self._fmt_age((e_agent or {}).get("ts", ""))
        freshness = freshness or self._compute_iter_freshness()
        market_data_age_s = freshness.get("data_age_s")   # ingest pipeline age (updated_at)
        market_book_age_s = freshness.get("book_age_s")
        market_ts_age_s = freshness.get("market_ts_age_s")  # API upstream age (snapshots.ts)
        pulse_data_age_s = self._age_sec(self._last_ingest_done_utc or "")
        pulse_book_age_s = self._age_sec(self._last_book_done_utc or "")
        pulse_agent_age_s = self._age_sec(self._last_agent_done_utc or "")
        data_ts_max = str(freshness.get("data_ts_max") or "")
        book_ts_max = str(freshness.get("book_ts_max") or "")
        market_ts_max = str(freshness.get("market_ts_max") or "")
        data_age_src = str(freshness.get("data_age_src") or "snapshots.ts")
        book_age_src = str(freshness.get("book_age_src") or "orderbook_snapshots.ts_utc")
        pulse_data_age = self._fmt_age_s(pulse_data_age_s)
        pulse_book_age = self._fmt_age_s(pulse_book_age_s)
        pulse_agent_age = self._fmt_age_s(pulse_agent_age_s)
        market_data_age = self._fmt_age_s(market_data_age_s)
        market_book_age = self._fmt_age_s(market_book_age_s)
        market_ts_age = self._fmt_age_s(market_ts_age_s)
        pipe = self._iter_pipe or {}
        log.info(
            "LOOP t=%s iter=%s ingest=%.0fms book=%.0fms agent=%.0fms reconcile=%.0fms idle=%.0fms "
            "errs=%s pulse_data_age=%s pulse_book_age=%s pulse_agent_age=%s "
            "ingest_age=%s market_ts_age=%s market_book_age=%s ingest_ins=%s book_ins=%s "
            "pipe[cand=%s dec=%s last=%s] "
            "cnt[i_ok=%s i_err=%s b_ok=%s b_err=%s a_ok=%s a_err=%s sk_book0=%s] "
            "err_age[i=%s b=%s a=%s] "
            "ingest_ts_max=%s market_ts_max=%s data_age_src=%s book_ts_max=%s",
            now.strftime("%H:%M:%S"),
            self._iter,
            float(self._iter_stage_ms.get("ingest", 0.0)),
            float(self._iter_stage_ms.get("book", 0.0)),
            float(self._iter_stage_ms.get("agent", 0.0)),
            float(self._iter_stage_ms.get("reconcile", 0.0)),
            float(self._iter_stage_ms.get("idle", 0.0)),
            errs,
            pulse_data_age,
            pulse_book_age,
            pulse_agent_age,
            market_data_age,    # ingest pipeline liveness (updated_at)
            market_ts_age,      # actual market data freshness (API ts)
            market_book_age,
            int(self._telemetry.get("last_ingest_snapshots", 0) or 0),
            int(self._telemetry.get("last_book_inserted", 0) or 0),
            int(pipe.get("cand_count", 0) or 0),
            int(pipe.get("dec_count", 0) or 0),
            str(pipe.get("last") or "-"),
            int(self._telemetry.get("ingest_ok", 0) or 0),
            int(self._telemetry.get("ingest_err", 0) or 0),
            int(self._telemetry.get("book_ok", 0) or 0),
            int(self._telemetry.get("book_err", 0) or 0),
            int(self._telemetry.get("agent_ok", 0) or 0),
            int(self._telemetry.get("agent_err", 0) or 0),
            int(self._telemetry.get("skipped_book_no_targets", 0) or 0),
            err_age_ing,
            err_age_book,
            err_age_agent,
            data_ts_max or "none",
            market_ts_max or "none",
            data_age_src,
            book_ts_max or "none",
        )

    def _emit_summary(self, now: datetime) -> None:
        mono = time.monotonic()
        if (mono - self._last_summary_log_ts) < 10.0:
            return
        self._last_summary_log_ts = mono
        freshness = self._compute_iter_freshness()
        data_age_s = freshness.get("data_age_s")
        book_age_s = freshness.get("book_age_s")
        markets_cnt = 0
        snapshots_5m = 0
        open_positions = 0
        live_cases = 0
        live_case_rows = []
        total_cases = 0
        db_cases_live: Optional[int] = None
        status_parts = []
        paused = False
        pinned_count = 0
        try:
            markets_cnt = int(self.repo.count_markets())
        except Exception:
            markets_cnt = 0
        try:
            with self.repo.conn() as con:
                row = con.execute(
                    "SELECT COUNT(*) AS n FROM snapshots WHERE julianday(ts) >= julianday('now','-5 minutes')"
                ).fetchone()
            snapshots_5m = int(row["n"] or 0) if row else 0
        except Exception:
            snapshots_5m = 0
        try:
            with self.repo.conn() as con:
                row = con.execute("SELECT COUNT(*) AS n FROM paper_positions WHERE status='OPEN'").fetchone()
            open_positions = int(row["n"] or 0) if row else 0
        except Exception:
            open_positions = 0
        try:
            live_case_rows = self.repo.list_cases(minutes_signals=30, minutes_snaps=10) or []
            live_cases = len(live_case_rows)
            db_cases_live = live_cases
        except Exception:
            live_cases = 0
            db_cases_live = None
        try:
            with self.repo.conn() as con:
                row = con.execute("SELECT COUNT(*) AS n FROM cases").fetchone()
            total_cases = int(row["n"] or 0) if row else 0
        except Exception:
            total_cases = 0
        try:
            pinned = (os.getenv("PS_PINNED_MARKETS") or "").strip()
            pinned_count = len([x for x in pinned.split(",") if x.strip()]) if pinned else 0
        except Exception:
            pinned_count = 0
        if not self._db_path_logged:
            self._db_path_logged = True
            log.info("DB_PATH=%s", str(getattr(self.repo, "db_path", "") or ""))
        try:
            if hasattr(self.repo, "is_paused"):
                paused = bool(self.repo.is_paused())
        except Exception:
            paused = False
        if total_cases > 0 and live_cases == 0:
            try:
                with self.repo.conn() as con:
                    rows = con.execute(
                        """
                        SELECT COALESCE(NULLIF(TRIM(status), ''), 'UNKNOWN') AS status, COUNT(*) AS n
                        FROM cases
                        GROUP BY COALESCE(NULLIF(TRIM(status), ''), 'UNKNOWN')
                        ORDER BY n DESC
                        LIMIT 5
                        """
                    ).fetchall()
                status_parts = [f"{str(r['status'])}:{int(r['n'] or 0)}" for r in (rows or [])]
            except Exception:
                status_parts = []
        log.info(
            "CASES_SUMMARY total_cases=%s live_cases=%s open_positions=%s pinned=%s",
            total_cases,
            live_cases,
            open_positions,
            pinned_count,
        )
        log.info(
            "CASES_SUMMARY_DB db_cases_total=%s db_cases_live=%s",
            total_cases,
            db_cases_live if db_cases_live is not None else "NA",
        )
        log.info(
            "CASES_SOURCE live_cases_source=%s explain=%s",
            "repo.list_cases(minutes_signals=30, minutes_snaps=10)",
            "live_cases here counts active markets from recent signals/snapshots, not rows in cases table",
        )
        if total_cases == 0 and live_cases > 0:
            sample_ids = []
            for row in live_case_rows[:3]:
                try:
                    mid = str((row or {}).get("market_id") or "")
                    if mid:
                        sample_ids.append(mid)
                except Exception:
                    continue
            log.info("CASES_SUMMARY live_cases_sample=%s", sample_ids)
        if status_parts:
            log.info("CASES_STATUS sample: %s", " ".join(status_parts))
        reason = ""
        if live_cases == 0:
            if snapshots_5m == 0:
                reason = "likely=no data ingest"
            elif (book_age_s or 0.0) > 30.0:
                reason = "likely=no orderbook freshness"
            elif paused or ((data_age_s or 0.0) > 60.0):
                reason = "likely=trading disabled (expected)"
            else:
                reason = "likely=filters/guards produced no live cases"
        log.info(
            "LOOP SUMMARY t=%s markets=%s snapshots_5m=%s open_pos=%s live_cases=%s %s",
            now.strftime("%H:%M:%S"),
            markets_cnt,
            snapshots_5m,
            open_positions,
            live_cases,
            reason,
        )

    def _emit_stage_flags(
        self,
        now: datetime,
        *,
        ran_ingest: int,
        ran_book: int,
        ran_agent: int,
        freshness: Optional[Dict[str, Any]] = None,
    ) -> None:
        mono = time.monotonic()
        if (mono - self._last_stage_flags_log_ts) < 10.0:
            return
        self._last_stage_flags_log_ts = mono
        freshness = freshness or self._compute_iter_freshness()
        market_data_age_s = freshness.get("data_age_s")       # pipeline liveness (updated_at)
        market_ts_age_s = freshness.get("market_ts_age_s")    # API upstream freshness (snapshots.ts)
        market_book_age_s = freshness.get("book_age_s")
        db_book_ts_max = str(freshness.get("book_ts_max") or "")
        ingest_ts_max = str(freshness.get("data_ts_max") or "")     # updated_at max
        market_ts_max = str(freshness.get("market_ts_max") or "")   # snapshots.ts max
        pulse_data_age_s = self._age_sec(self._last_ingest_done_utc or "")
        pulse_book_age_s = self._age_sec(self._last_book_done_utc or "")
        paused = 0
        try:
            if hasattr(self.repo, "is_paused"):
                paused = 1 if bool(self.repo.is_paused()) else 0
        except Exception:
            paused = 0
        state_obj = freshness.get("state") or {}
        data_state_obj = state_obj.get("data") or {}
        book_state_obj = state_obj.get("book") or {}
        overall_state = str(state_obj.get("overall") or "STOP")
        stale = 0 if overall_state == STATE_OK else 1
        stale_reason = "OK" if stale == 0 else f"FRESHNESS_{overall_state}"
        ingest_ema_s = self._ingest_every_ema_sec
        data_warn_s = float(data_state_obj.get("warn_s") or 0.0)
        data_stop_s = float(data_state_obj.get("stop_s") or 0.0)
        try:
            book_age_ref = freshness.get("book_age_s")
            if (
                market_book_age_s is not None
                and book_age_ref is not None
                and abs(float(market_book_age_s) - float(book_age_ref)) > 1.0
                and (mono - self._last_freshness_diverge_log_ts) >= 10.0
            ):
                self._last_freshness_diverge_log_ts = mono
                log.warning(
                    "FRESHNESS_DIVERGE market_book_age_s=%s freshness_book_age_s=%s book_ts_max=%s",
                    float(market_book_age_s),
                    float(book_age_ref),
                    db_book_ts_max or "none",
                )
        except Exception:
            pass
        trading_enabled = 1 if (not paused and bool(getattr(self.settings, "enable_decision", True))) else 0
        log.info(
            "STAGES ran_ingest=%s ran_book=%s ran_agent=%s paused=%s stale=%s stale_reason=%s "
            "pulse_data_age=%s pulse_book_age=%s "
            "ingest_age_s=%s market_ts_age_s=%s market_book_age_s=%s "
            "ingest_ts_max=%s market_ts_max=%s db_book_ts_max=%s "
            "ingest_ema_s=%s data_warn_s=%s data_stop_s=%s trading_enabled=%s",
            int(ran_ingest),
            int(ran_book),
            int(ran_agent),
            int(paused),
            int(stale),
            stale_reason,
            self._fmt_age_s(pulse_data_age_s),
            self._fmt_age_s(pulse_book_age_s),
            "-" if market_data_age_s is None else f"{float(market_data_age_s):.1f}",
            "-" if market_ts_age_s is None else f"{float(market_ts_age_s):.1f}",
            "-" if market_book_age_s is None else f"{float(market_book_age_s):.1f}",
            ingest_ts_max or "none",
            market_ts_max or "none",
            db_book_ts_max or "none",
            "-" if ingest_ema_s is None else f"{float(ingest_ema_s):.1f}",
            f"{float(data_warn_s):.1f}",
            f"{float(data_stop_s):.1f}",
            int(trading_enabled),
        )

    def _active_orderbook_targets(self, top_n: int = 30) -> tuple[list[str], dict]:
        ids: list[tuple[str, str]] = []
        live_cases_count = 0
        try:
            cases = self.repo.list_cases(minutes_signals=30, minutes_snaps=10)
            live_cases_count = len(cases or [])
            for c in cases[:top_n]:
                mid = c.get("market_id") if isinstance(c, dict) else None
                if mid:
                    ids.append((str(mid), "cases"))
        except Exception:
            pass
        try:
            with self.repo.conn() as con:
                rows = con.execute(
                    "SELECT DISTINCT market_id AS market_id FROM paper_positions WHERE status='OPEN'"
                ).fetchall()
            for r in rows or []:
                mid = r["market_id"] if isinstance(r, dict) else r[0]
                if mid:
                    ids.append((str(mid), "positions"))
        except Exception:
            pass
        pinned = (os.getenv("PS_PINNED_MARKETS") or "").strip()
        if pinned:
            for mid in pinned.split(","):
                mid = mid.strip()
                if mid:
                    ids.append((mid, "pinned"))
        # unique, preserve order
        seen = set()
        unique: list[tuple[str, str]] = []
        for mid, src in ids:
            if mid and not mid.isdigit():
                continue
            if mid in seen:
                continue
            seen.add(mid)
            unique.append((mid, src))

        targets: list[str] = []
        dropped_unknown_market_id = 0
        dropped_no_tokens = 0
        dropped_no_clob_tokens = 0
        source_counts: dict[str, int] = {"cases": 0, "positions": 0, "pinned": 0}
        unknown_samples: list[str] = []
        backfill_enqueued = 0
        if not unique:
            return targets, {
                "sources": source_counts,
                "dropped_unknown_market_id": dropped_unknown_market_id,
                "dropped_no_tokens": dropped_no_tokens,
                "live_cases_count": live_cases_count,
            }
        try:
            qmarks = ",".join(["?"] * len(unique))
            with self.repo.conn() as con:
                rows = con.execute(
                    f"SELECT market_id, raw_json FROM markets WHERE market_id IN ({qmarks})",
                    tuple([m for m, _ in unique]),
                ).fetchall()
            raw_map = {r["market_id"]: r["raw_json"] for r in rows or []}
            for mid, src in unique:
                raw_json = raw_map.get(mid) or ""
                if not raw_json or raw_json.strip() == "":
                    dropped_unknown_market_id += 1
                    if len(unknown_samples) < 5:
                        unknown_samples.append(mid)
                    if hasattr(self, "ingestor") and hasattr(self.ingestor, "enqueue_backfill_market"):
                        try:
                            if self.ingestor.enqueue_backfill_market(mid):
                                backfill_enqueued += 1
                        except Exception:
                            pass
                    continue
                try:
                    raw = json.loads(raw_json)
                except Exception:
                    dropped_no_tokens += 1
                    continue
                tokens = _extract_tokens_from_row(raw)
                if not tokens:
                    dropped_no_clob_tokens += 1
                    continue
                for t in tokens:
                    tid = (
                        t.get("token_id")
                        or t.get("tokenId")
                        or t.get("clobTokenId")
                        or t.get("clob_token_id")
                        or t.get("id")
                    )
                    if tid is None:
                        continue
                    targets.append(str(tid))
                    source_counts[src] = source_counts.get(src, 0) + 1
        except Exception:
            log.exception("orderbook targets build failed")
        if dropped_unknown_market_id:
            msg = "orderbook targets: sources=%s total_ids=%s unknown_ids=%s sample=%s backfill_enqueued=%s"
            if dropped_unknown_market_id <= 2:
                log.info(msg, source_counts, len(unique), dropped_unknown_market_id, unknown_samples, backfill_enqueued)
            else:
                log.warning(msg, source_counts, len(unique), dropped_unknown_market_id, unknown_samples, backfill_enqueued)
        return targets, {
            "sources": source_counts,
            "dropped_unknown_market_id": dropped_unknown_market_id,
            "dropped_no_tokens": dropped_no_tokens,
            "dropped_no_clob_tokens": dropped_no_clob_tokens,
            "backfill_enqueued": backfill_enqueued,
            "live_cases_count": live_cases_count,
        }

    def stop(self) -> None:
        self._stop = True

    def _ctx(self, now):
        return AgentContext(
            run_id=self.run_id,
            now=now,
            repo=self.repo,
            settings=self.settings,
            data_provider=RepoAgentDataProvider(self.repo),
            repo_latest_snapshots=self._latest_snapshots_by_outcome,
            latest_snapshots=self._latest_snapshots_cache,
        )

    def _queue_event(
        self,
        *,
        ts: datetime,
        level: str,
        component: str,
        message: str,
        payload: dict | None = None,
    ) -> None:
        self._event_buffer.append(
            {
                "ts": ts,
                "level": level,
                "component": component,
                "message": message,
                "payload": payload or {},
            }
        )
        if len(self._event_buffer) >= 128:
            self._flush_events()

    def _flush_events(self) -> None:
        if not self._event_buffer:
            return
        if hasattr(self.repo, "log_events_batch"):
            try:
                self.repo.log_events_batch(self._event_buffer)
                self._event_buffer.clear()
                return
            except Exception:
                log.warning("log_events_batch failed; falling back to per-event logging", exc_info=True)
        for e in self._event_buffer:
            self.repo.log_event(
                ts=e["ts"],
                level=e["level"],
                component=e["component"],
                message=e["message"],
                payload=e["payload"],
            )
        self._event_buffer.clear()

    def _run_agents_for_market(self, ctx: AgentContext, market_id: str) -> None:
        t0 = time.perf_counter()
        local_errs = 0
        def _mark(name: str, started: float) -> None:
            self._iter_agent_timing[name] = self._iter_agent_timing.get(name, 0.0) + (
                (time.perf_counter() - started) * 1000.0
            )
        for agent in getattr(self, "fast_agents", []):
            agent_name = str(getattr(agent, "agent_id", "") or agent.__class__.__name__).lower()
            bucket = None
            if "scout" in agent_name:
                bucket = "scout"
            elif "logic" in agent_name:
                bucket = "logic"
            elif "risk" in agent_name:
                bucket = "risk"
            try:
                t_agent = time.perf_counter()
                signals = agent.propose(ctx, market_id=market_id)
                if bucket:
                    _mark(bucket, t_agent)
                n_signals = len(signals)
                self._iter_db_write_signals_count += int(n_signals)
                if n_signals:
                    self._iter_signals_buf.extend(signals)
                    if bucket in {"scout", "logic"}:
                        self._record_signal_batch_diag(bucket, signals)
                    if bucket == "scout":
                        self._iter_decision_diag["fast_scout_candidates"] = int(
                            self._iter_decision_diag.get("fast_scout_candidates", 0) or 0
                        ) + self._diag_candidate_count(signals)
            except Exception as e:
                if bucket:
                    _mark(bucket, t_agent if "t_agent" in locals() else time.perf_counter())
                local_errs += 1
                self._record_stage_error("agent", e, ctx.now)
                self._queue_event(
                    ts=ctx.now,
                    level="ERROR",
                    component=f"agent:{getattr(agent, 'agent_id', 'unknown')}",
                    message=str(e),
                    payload={"market_id": market_id},
                )
        if local_errs == 0:
            self._record_stage_ok("agent", ctx.now)
        self._iter_stage_ms["agent"] = self._iter_stage_ms.get("agent", 0.0) + ((time.perf_counter() - t0) * 1000.0)

    def _run_slow_agents(self, ctx: AgentContext) -> None:
        # Run once per reconcile
        t0 = time.perf_counter()
        local_errs = 0
        def _mark(name: str, started: float) -> None:
            self._iter_agent_timing[name] = self._iter_agent_timing.get(name, 0.0) + (
                (time.perf_counter() - started) * 1000.0
            )
        for agent in getattr(self, "slow_agents", []):
            agent_name = str(getattr(agent, "agent_id", "") or agent.__class__.__name__).lower()
            bucket = None
            if "scout" in agent_name:
                bucket = "scout"
            elif "logic" in agent_name:
                bucket = "logic"
            elif "risk" in agent_name:
                bucket = "risk"
            try:
                t_agent = time.perf_counter()
                # Prefer signature propose(ctx) for slow scans; fallback to per-market scan.
                try:
                    signals = agent.propose(ctx)  # type: ignore[arg-type]
                except TypeError:
                    signals = []
                    for m in self.repo.list_markets(limit=200):
                        signals.extend(agent.propose(ctx, market_id=m.market_id))
                if bucket:
                    _mark(bucket, t_agent)
                n_signals = len(signals)
                self._iter_db_write_signals_count += int(n_signals)
                if n_signals:
                    self._iter_signals_buf.extend(signals)
                    if bucket == "scout":
                        self._iter_decision_diag["slow_scout_candidates"] = int(
                            self._iter_decision_diag.get("slow_scout_candidates", 0) or 0
                        ) + self._diag_candidate_count(signals)
                        self._merge_mm_scan_diag(agent)
                elif bucket == "scout":
                    self._merge_mm_scan_diag(agent)
            except Exception as e:
                if bucket:
                    _mark(bucket, t_agent if "t_agent" in locals() else time.perf_counter())
                local_errs += 1
                self._record_stage_error("agent", e, ctx.now)
                self._queue_event(
                    ts=ctx.now,
                    level="ERROR",
                    component=f"agent:{getattr(agent, 'agent_id', 'unknown')}",
                    message=str(e),
                    payload={},
                )
        if local_errs == 0:
            self._record_stage_ok("agent", ctx.now)
        self._iter_stage_ms["agent"] = self._iter_stage_ms.get("agent", 0.0) + ((time.perf_counter() - t0) * 1000.0)

    def _handle_event(self, ev) -> None:
        now = ev.ts
        ctx = self._ctx(now)

        if isinstance(ev, MarketTick) and self.settings.enable_agents:
            self._run_agents_for_market(ctx, ev.market_id)
        elif isinstance(ev, MarketTick):
            self._telemetry["skipped_agent_disabled"] = int(self._telemetry.get("skipped_agent_disabled", 0) or 0) + 1

        elif isinstance(ev, Timer):
            if ev.purpose == "reconcile":
                freshness = self._compute_iter_freshness()
                overall_state = str((freshness.get("state") or {}).get("overall") or "STOP")
                decision_mode = self._decision_mode_from_freshness(overall_state)
                self._iter_reconcile_diag["scheduled"] = 1
                self._iter_reconcile_diag["decision_mode"] = decision_mode
                if decision_mode in {DECISION_MODE_FULL, DECISION_MODE_SAFE}:
                    self._iter_reconcile_diag["allowed"] = 1
                    self._iter_reconcile_diag["skip_reason"] = "NONE"
                else:
                    self._iter_reconcile_diag["allowed"] = 0
                    self._iter_reconcile_diag["skip_reason"] = f"FRESHNESS_{overall_state}"
                # Slow agents first: generate cross-market signals before decisions
                if self.settings.enable_agents and decision_mode in {DECISION_MODE_FULL, DECISION_MODE_SAFE}:
                    self._run_slow_agents(ctx)
                if decision_mode == DECISION_MODE_HALTED:
                    log.info(
                        "CASE_LIFECYCLE_SKIP_SUMMARY ts=%s run_id=%s freshness_reason=FRESHNESS_STOP_HALTED "
                        "decision_mode=HALTED written=0",
                        now.isoformat(timespec="seconds"),
                        str(self.run_id or "-"),
                    )
                    return
                t0 = time.perf_counter()
                n = self.decision_engine.reconcile(self.run_id)

                x = 0
                try:
                    x = reconcile_paper(self.repo, self.run_id)
                except Exception as e:
                    log.exception(f"paper reconcile failed: {e}")
                    self._queue_event(
                        ts=now,
                        level="ERROR",
                        component="paper",
                        message=f"paper reconcile failed: {e}",
                        payload={},
                    )
                live_n = 0
                try:
                    live_n = self._maybe_submit_stage0_open_from_pipeline(now)
                except Exception:
                    log.exception("live_stage0 dispatch failed")
                if self._mm_final_probe_enabled():
                    self._emit_mm_final_probe_summary()
                else:
                    self._emit_mm_probe_summary()
                self._iter_stage_ms["reconcile"] = self._iter_stage_ms.get("reconcile", 0.0) + (
                    (time.perf_counter() - t0) * 1000.0
                )

                self._queue_event(
                    ts=now,
                    level="INFO",
                    component="decision",
                    message=f"decisions written: {n} | paper executed: {x} | live submitted: {live_n}",
                    payload={},
                )

        elif isinstance(ev, Alert):
            self._queue_event(
                ts=now,
                level=ev.severity,
                component="alert",
                message=f"{ev.code}: {ev.message}",
                payload={},
            )

    def run_forever(self) -> None:
        while not self._stop:
            iter_start = time.perf_counter()
            self._iter += 1
            self._iter_stage_ms = {
                "ingest": 0.0,
                "db": 0.0,
                "book": 0.0,
                "agent": 0.0,
                "reconcile": 0.0,
                "ui": 0.0,
                "idle": 0.0,
                "total": 0.0,
            }
            self._iter_errs = 0
            self._iter_freshness = None
            self._iter_pipe = {"cand_count": 0, "dec_count": 0, "last": "HOLD/NO_CANDIDATES"}
            self._iter_reconcile_diag = {
                "scheduled": 0,
                "allowed": 0,
                "skip_reason": "NOT_SCHEDULED",
                "decision_mode": DECISION_MODE_HALTED,
                "open_blocked_by_freshness": 0,
            }
            self._iter_decision_diag = {
                "scout_raw": 0,
                "scout_kept_ids": set(),
                "logic_pass": 0,
                "logic_hold": 0,
                "fast_scout_candidates": 0,
                "slow_scout_candidates": 0,
                "logic_reason_counts": {},
                "paper_reason_counts": {},
                "paper_action_counts": {},
                "hold_reason_counts": {},
                "mm_markets_raw": 0,
                "mm_markets_eligible": 0,
                "mm_candidates_found": 0,
                "mm_decision_accepted": 0,
                "mm_orders_placed": 0,
                "mm_probe_bypass_untradeable": 0,
                "mm_probe_orders_attempted": 0,
                "mm_probe_orders_failed": 0,
                "mm_probe_orders_filled": 0,
                "mm_final_probe_candidates_seen": 0,
                "mm_final_probe_candidates_selected": 0,
                "mm_final_probe_orders_attempted": 0,
                "mm_final_probe_orders_failed": 0,
            }
            self._iter_db_write_signals_count = 0
            self._iter_db_write_calls = 0
            self._iter_signals_buf.clear()
            self._iter_signal_flush_timing = {
                "total_ms": 0.0,
                "build_ms": 0.0,
                "call_ms": 0.0,
                "post_ms": 0.0,
                "exec_ms": 0.0,
                "rows": 0.0,
                "chunks": 0.0,
                "calls": 0.0,
            }
            self._iter_agent_timing = {
                "cases": 0.0,
                "scout": 0.0,
                "logic": 0.0,
                "risk": 0.0,
                "paper": 0.0,
                "explain": 0.0,
            }
            ran_ingest = 0
            ran_book = 0
            now = datetime.now(timezone.utc)
            do_poll, do_reconcile = self.scheduler.tick(now)
            self._iter_reconcile_diag = {
                "scheduled": int(bool(do_reconcile)),
                "allowed": 0,
                "skip_reason": "NONE" if bool(do_reconcile) else "NOT_SCHEDULED",
                "decision_mode": DECISION_MODE_HALTED,
                "open_blocked_by_freshness": 0,
            }

            mono = time.monotonic()
            if self._net_ping_enabled and (mono - self._last_net_ping_ts) >= 60.0:
                self._last_net_ping_ts = mono
                t_ping0 = time.perf_counter()
                try:
                    req = Request(
                        url=f"{GAMMA_BASE}/markets?closed=false&limit=1&offset=0",
                        method="GET",
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                    )
                    with urlopen(req, timeout=2) as resp:
                        try:
                            resp.read(1)
                        except Exception:
                            pass
                    log.info("NET_PING ok=1 ms=%.0f", (time.perf_counter() - t_ping0) * 1000.0)
                except Exception as e:
                    err_no = self._extract_errno(e)
                    reason = getattr(e, "reason", None)
                    err_type = type(reason).__name__ if reason is not None else type(e).__name__
                    log.info("NET_PING ok=0 errno=%s err_type=%s", err_no if err_no is not None else "-", err_type)
            ingest_guard_eligible = (
                bool(do_poll)
                and bool(self.settings.enable_ingest)
                and mono >= self._next_ingest_ts
                and mono >= self._ingest_neterr_until
            )
            block_guard, block_guard_reset = self._resolve_ingest_block_guard(ingest_guard_eligible)
            if block_guard_reset:
                log.info(
                    "INGEST_BLOCK_GUARD_RESET last_ms=%.0f max_ms=%.0f skip_cap=%s",
                    float(self._last_ingest_wall_ms),
                    float(self._ingest_max_block_ms),
                    int(self._ingest_block_guard_skip_cap),
                )
            if ingest_guard_eligible and not block_guard:
                t0 = time.perf_counter()
                try:
                    print("INGEST TICK", now)
                    log.info("INGEST_CALL iter=%s will_run=%s reason=%s", self._iter, 1, "RUN")
                    ran_ingest = 1
                    m_cnt, s_cnt = self.ingestor.ingest()
                    ingest_stats = getattr(getattr(self.ingestor, "client", None), "last_snapshot_stats", {}) or {}
                    fetched_n = int(ingest_stats.get("fetched_ok", 0) or 0)
                    parsed_n = int(ingest_stats.get("parsed", 0) or 0)
                    inserted_n = int(ingest_stats.get("inserted", s_cnt or 0) or 0)
                    self._ingest_failures = 0
                    self._next_ingest_ts = 0.0
                    self._telemetry["last_ingest_snapshots"] = inserted_n
                    self._record_stage_ok("ingest", now)
                    # Flush write buffer immediately so freshness reads see new data
                    if hasattr(self.repo, "flush_writes"):
                        try:
                            self.repo.flush_writes()
                        except Exception as _fe:
                            log.warning("flush_writes after ingest failed: %s", _fe)
                    log.info(
                        "INGEST_OK fetched=%s parsed=%s inserted=%s markets=%s",
                        fetched_n,
                        parsed_n,
                        inserted_n,
                        int(m_cnt or 0),
                    )
                    now_mono = time.monotonic()
                    if (now_mono - self._last_ts_parse_diag_log_ts) >= 60.0:
                        self._last_ts_parse_diag_log_ts = now_mono
                        try:
                            with self.repo.conn() as con:
                                row = con.execute(
                                    """
                                    SELECT
                                      COUNT(*) AS total,
                                      SUM(CASE WHEN ts IS NULL OR ts='' THEN 1 ELSE 0 END) AS empty_ts,
                                      SUM(CASE WHEN ts IS NOT NULL AND ts<>'' AND julianday(ts) IS NULL THEN 1 ELSE 0 END) AS bad_ts,
                                      SUM(CASE WHEN julianday(ts) IS NOT NULL THEN 1 ELSE 0 END) AS ok_ts,
                                      SUM(CASE WHEN updated_at IS NOT NULL AND updated_at <> '' THEN 1 ELSE 0 END) AS has_updated_at,
                                      MAX(updated_at) AS max_updated_at,
                                      MAX(ts) AS max_ts
                                    FROM snapshots
                                    """
                                ).fetchone()
                            if row:
                                log.info(
                                    "SNAPSHOTS_TS_PARSE total=%s empty_ts=%s bad_ts=%s ok_ts=%s has_updated_at=%s max_updated_at=%s max_ts=%s",
                                    int(row["total"] or 0),
                                    int(row["empty_ts"] or 0),
                                    int(row["bad_ts"] or 0),
                                    int(row["ok_ts"] or 0),
                                    int(row["has_updated_at"] or 0),
                                    str(row["max_updated_at"] or "none"),
                                    str(row["max_ts"] or "none"),
                                )
                        except Exception:
                            log.debug("SNAPSHOTS_TS_PARSE failed", exc_info=True)
                        # Rowid diagnostic: verify newest rows (by rowid) actually carry fresh ts
                        # If rowid grows but ts stays frozen → upstream API returning stale timestamps
                        try:
                            with self.repo.conn() as con:
                                rowid_rows = con.execute(
                                    """
                                    SELECT rowid, ts, updated_at, market_id, outcome
                                    FROM snapshots
                                    ORDER BY rowid DESC
                                    LIMIT 5
                                    """
                                ).fetchall()
                            if rowid_rows:
                                entries = [
                                    f"rowid={r['rowid']} ts={r['ts']} ua={r['updated_at'] or '-'} mid={r['market_id']}/{r['outcome']}"
                                    for r in rowid_rows
                                ]
                                log.info("SNAPSHOTS_ROWID_CHECK (newest 5): %s", " | ".join(entries))
                        except Exception:
                            log.debug("SNAPSHOTS_ROWID_CHECK failed", exc_info=True)
                    log.info(f"ingest: markets={m_cnt} snapshots={s_cnt}")
                    markets = self.repo.list_markets(limit=200)
                    market_ids = [m.market_id for m in markets]
                    self._latest_snapshots_cache = {}
                    if market_ids and hasattr(self.repo, "get_latest_snapshots_batch"):
                        try:
                            self._latest_snapshots_cache = self.repo.get_latest_snapshots_batch(market_ids)
                        except Exception:
                            log.warning("get_latest_snapshots_batch failed; using empty cache", exc_info=True)
                            self._latest_snapshots_cache = {}
                    for m in markets:
                        self.bus.publish(MarketTick(ts=now, market_id=m.market_id))
                except Exception as e:
                    err_no = self._extract_errno(e)
                    net_kind = None
                    net_code: Any = "-"
                    if err_no in {10013, 10051, 11001, 11002, 11004}:
                        net_kind = "errno"
                        net_code = err_no
                    elif isinstance(e, URLError):
                        net_kind = "urlerror"
                        net_code = "-"
                    elif isinstance(e, HTTPError) and int(getattr(e, "code", 0) or 0) in {429, 500, 502, 503, 504}:
                        net_kind = "http"
                        net_code = int(getattr(e, "code", 0) or 0)
                    if net_kind is not None:
                        try:
                            cooldown_s = float(os.getenv("PS_INGEST_NETERR_COOLDOWN_S", "60") or 60.0)
                        except Exception:
                            cooldown_s = 60.0
                        cooldown_s = max(1.0, cooldown_s)
                        self._ingest_neterr_until = time.monotonic() + cooldown_s
                        ran_ingest = 0
                        cooldown_until = self._ingest_neterr_until
                        remaining = max(0.0, cooldown_until - time.monotonic())
                        log.info(
                            "INGEST_NETERR kind=%s code=%s cooldown_s=%s skip_for_s=%.1f",
                            net_kind,
                            net_code,
                            cooldown_s,
                            remaining,
                        )
                    else:
                        self._ingest_failures += 1
                        retry_in = min(30.0, 0.5 * (2 ** (self._ingest_failures - 1)))
                        self._next_ingest_ts = time.monotonic() + retry_in
                        self._record_stage_error("ingest", e, now)
                        ingest_stats = getattr(getattr(self.ingestor, "client", None), "last_snapshot_stats", {}) or {}
                        fetched_n = int(ingest_stats.get("fetched_ok", 0) or 0)
                        parsed_n = int(ingest_stats.get("parsed", 0) or 0)
                        inserted_n = int(ingest_stats.get("inserted", 0) or 0)
                        http_status = self._extract_http_status(e)
                        if (time.monotonic() - self._last_ingest_fail_log_ts) >= 5.0:
                            self._last_ingest_fail_log_ts = time.monotonic()
                            msg = str(e).replace("\n", " ").strip()
                            if len(msg) > 160:
                                msg = msg[:160]
                            log.warning(
                                "INGEST_FAIL exc=%s msg=%s http=%s fetched=%s parsed=%s inserted=%s",
                                e.__class__.__name__,
                                msg,
                                http_status if http_status is not None else "-",
                                fetched_n,
                                parsed_n,
                                inserted_n,
                            )
                        self.bus.publish(
                            Alert(
                                ts=now,
                                severity="ERROR",
                                code="INGEST_FAIL",
                                message=f"{e} | retry in {retry_in:.1f}s",
                            )
                        )
                finally:
                    self._iter_stage_ms["ingest"] = (time.perf_counter() - t0) * 1000.0
                    self._last_ingest_wall_ms = float(self._iter_stage_ms["ingest"])
                    log.info("INGEST_PHASES iter=%s call=%.0fms", self._iter, float(self._iter_stage_ms["ingest"]))
            else:
                self._telemetry["skipped_ingest_guard"] = int(self._telemetry.get("skipped_ingest_guard", 0) or 0) + 1
                if mono < self._ingest_neterr_until:
                    reason = "NETERR_COOLDOWN"
                elif block_guard:
                    reason = "MAX_BLOCK_MS"
                elif not do_poll:
                    reason = "SCHEDULER_NOT_POLL"
                elif not self.settings.enable_ingest:
                    reason = "INGEST_DISABLED"
                elif mono < self._next_ingest_ts:
                    reason = "BACKOFF_WAIT"
                else:
                    reason = "GUARD_BLOCKED"
                last_reason_ts = float(self._last_ingest_skip_reason_log_ts.get(reason, 0.0) or 0.0)
                if (time.monotonic() - last_reason_ts) >= 10.0:
                    now_mono = time.monotonic()
                    self._last_ingest_skip_reason_log_ts[reason] = now_mono
                    self._last_ingest_skip_log_ts = now_mono
                    if reason == "NETERR_COOLDOWN":
                        log.info(
                            "INGEST_SKIPPED reason=NETERR_COOLDOWN until_in_s=%.1f",
                            max(0.0, float(self._ingest_neterr_until) - float(mono)),
                        )
                    elif reason == "MAX_BLOCK_MS":
                        log.info(
                            "INGEST_SKIPPED reason=MAX_BLOCK_MS last_ms=%.0f max_ms=%.0f skip_n=%s skip_cap=%s",
                            float(self._last_ingest_wall_ms),
                            float(self._ingest_max_block_ms),
                            int(self._ingest_block_guard_skips or 0),
                            int(self._ingest_block_guard_skip_cap),
                        )
                    else:
                        log.info(
                            "INGEST_SKIP reason=%s enable_ingest=%s do_poll=%s wait_s=%.1f",
                            reason,
                            bool(self.settings.enable_ingest),
                            bool(do_poll),
                            max(0.0, float(self._next_ingest_ts) - float(mono)),
                        )

            # Orderbook collector (separate cadence)
            if mono >= self._next_book_ts:
                t0 = time.perf_counter()
                try:
                    orderbook_enabled_raw = str(os.getenv("PS_ORDERBOOK_ENABLED", "1") or "1").strip().lower()
                    orderbook_enabled = orderbook_enabled_raw not in {"0", "false", "no"}
                    if not orderbook_enabled:
                        self._next_book_ts = mono + 3.0
                        log.info("ORDERBOOK_STAGE skipped by PS_ORDERBOOK_ENABLED=0")
                    else:
                        print("BOOK TICK", now)
                        ran_book = 1
                        active_ids, target_stats = self._active_orderbook_targets(top_n=30)
                        selected_ids = list(active_ids or [])
                        if self._book_stale_sec > 0 and selected_ids:
                            selected_ids = [
                                mid for mid in selected_ids
                                if (mid not in self._book_last_fetch_mono)
                                or ((mono - float(self._book_last_fetch_mono.get(mid, 0.0))) >= float(self._book_stale_sec))
                            ]
                        rr_cursor_before = int(self._book_rr_cursor or 0)
                        targets_total = len(active_ids or [])
                        if self._book_target_limit > 0 and len(selected_ids) > self._book_target_limit:
                            n = len(selected_ids)
                            start = rr_cursor_before % n
                            take = int(self._book_target_limit)
                            end = start + take
                            if end <= n:
                                selected_ids = selected_ids[start:end]
                            else:
                                selected_ids = selected_ids[start:] + selected_ids[: end - n]
                            self._book_rr_cursor = (start + take) % n
                        if not active_ids:
                            self._telemetry["skipped_book_no_targets"] = int(
                                self._telemetry.get("skipped_book_no_targets", 0) or 0
                            ) + 1
                            if (time.monotonic() - self._last_book_skip_log_ts) >= 10.0:
                                self._last_book_skip_log_ts = time.monotonic()
                                sources = (target_stats or {}).get("sources") or {}
                                live_cases_count = int((target_stats or {}).get("live_cases_count", 0) or 0)
                                log.info(
                                    "BOOK_SKIP targets=0 sources={cases:%s,positions:%s,pinned:%s} live_cases=%s",
                                    int(sources.get("cases", 0) or 0),
                                    int(sources.get("positions", 0) or 0),
                                    int(sources.get("pinned", 0) or 0),
                                    live_cases_count,
                                )
                        book_conc = getattr(getattr(self.book_collector, "client", None), "book_concurrency", "-")
                        sample_ids = ",".join(selected_ids[:3]) if selected_ids else "-"
                        log.info(
                            "BOOK_PLAN targets=%s selected=%s rr_cursor=%s stale_sec=%s conc=%s sample=%s",
                            targets_total,
                            len(selected_ids),
                            rr_cursor_before,
                            int(self._book_stale_sec) if self._book_stale_sec > 0 else 0,
                            book_conc,
                            sample_ids,
                        )
                        stats = self.book_collector.collect(selected_ids)
                        for mid in selected_ids:
                            self._book_last_fetch_mono[mid] = mono
                        stats["targets"] = target_stats
                        self._book_failures = 0
                        self._next_book_ts = mono + 3.0
                        self._telemetry["last_book_inserted"] = int(stats.get("inserted", 0) or 0)
                        self._record_stage_ok("book", now)
                        try:
                            last_map = stats.get("last_book_ts") or {}
                            last_count = len(last_map)
                            max_age_s = None
                            if last_map:
                                max_ts = None
                                for v in last_map.values():
                                    try:
                                        dt = datetime.fromisoformat(str(v))
                                        if dt.tzinfo is None:
                                            dt = dt.replace(tzinfo=timezone.utc)
                                        if max_ts is None or dt > max_ts:
                                            max_ts = dt
                                    except Exception:
                                        continue
                                if max_ts:
                                    max_age_s = (datetime.now(timezone.utc) - max_ts).total_seconds()
                            else:
                                try:
                                    with self.repo.conn() as con:
                                        row = con.execute(
                                            "SELECT COUNT(DISTINCT market_id) AS n, MAX(ts_utc) AS max_ts FROM orderbook_snapshots"
                                        ).fetchone()
                                    last_count = int(row["n"] or 0) if row else 0
                                    max_ts_raw = row["max_ts"] if row else None
                                    if max_ts_raw:
                                        dt = datetime.fromisoformat(str(max_ts_raw))
                                        if dt.tzinfo is None:
                                            dt = dt.replace(tzinfo=timezone.utc)
                                        max_age_s = (datetime.now(timezone.utc) - dt).total_seconds()
                                except Exception:
                                    pass
                            total = stats.get("total", 0)
                            inserted = stats.get("inserted", 0)
                            errors = stats.get("errors", 0)
                            dropped_no_clob = (stats.get("targets") or {}).get("dropped_no_clob_tokens", 0)
                            skipped_missing = stats.get("skipped_missing", 0)
                            should_info = bool(errors or inserted == 0 or (mono - self._last_orderbook_log) >= 60.0)
                            if should_info:
                                log.info(
                                    "orderbook: total=%s inserted=%s errors=%s dropped_no_clob=%s skipped_missing=%s "
                                    "last_book_count=%s max_age_s=%s",
                                    total,
                                    inserted,
                                    errors,
                                    dropped_no_clob,
                                    skipped_missing,
                                    last_count,
                                    None if max_age_s is None else round(max_age_s, 1),
                                )
                                self._last_orderbook_log = mono
                            else:
                                log.debug(
                                    "orderbook: total=%s inserted=%s errors=%s dropped_no_clob=%s skipped_missing=%s "
                                    "last_book_count=%s max_age_s=%s",
                                    total,
                                    inserted,
                                    errors,
                                    dropped_no_clob,
                                    skipped_missing,
                                    last_count,
                                    None if max_age_s is None else round(max_age_s, 1),
                                )
                        except Exception:
                            log.debug("orderbook: summary failed", exc_info=True)
                        if stats.get("errors"):
                            log.warning(f"orderbook: {stats}")
                            self._queue_event(
                                ts=now,
                                level="ERROR",
                                component="orderbook",
                                message="orderbook_errors",
                                payload=stats,
                            )
                except Exception as e:
                    self._book_failures += 1
                    retry_in = min(30.0, 0.5 * (2 ** (self._book_failures - 1)))
                    self._next_book_ts = mono + retry_in
                    self._record_stage_error("book", e, now)
                    self._queue_event(
                        ts=now,
                        level="ERROR",
                        component="orderbook",
                        message=str(e),
                        payload={},
                    )
                finally:
                    self._iter_stage_ms["book"] = (time.perf_counter() - t0) * 1000.0
                    log.info("BOOK_PHASES iter=%s call=%.0fms", self._iter, float(self._iter_stage_ms["book"]))

            agent_t0 = time.perf_counter()
            iter_freshness = self._compute_iter_freshness()
            state_obj = iter_freshness.get("state") or {}
            overall_state = str(state_obj.get("overall") or "STOP")
            decision_mode = self._decision_mode_from_freshness(overall_state)
            self._iter_reconcile_diag["decision_mode"] = decision_mode
            self._iter_reconcile_diag["open_blocked_by_freshness"] = 0
            self._paper_pipeline_ctx["now"] = now
            t_paper = time.perf_counter()
            if decision_mode == DECISION_MODE_HALTED:
                self._iter_pipe = {
                    "cand_count": 0,
                    "dec_count": 0,
                    "last": "ABORT/FRESHNESS_STOP",
                    "paper_action": "ABORT",
                    "paper_reason": "FRESHNESS_STOP",
                    "freshness_reason": "FRESHNESS_STOP_HALTED",
                    "paper_source": "freshness.overall_stop.halted_mode",
                    "dedup_signature": "",
                    "matched_prev_signature": "",
                    "selected": 0,
                    "skipped_as_stale": 0,
                    "consumed_key": "",
                    "opportunity_key": "",
                    "same_opportunity_as_prev": 0,
                    "skipped_as_same_opportunity": 0,
                }
                log.info("DECISION_SAFE_MODE freshness=FRESHNESS_STOP decision_mode=HALTED")
            else:
                effective_freshness_state = dict(state_obj)
                if decision_mode == DECISION_MODE_SAFE:
                    # Evaluate candidates, then block OPEN at loop level.
                    effective_freshness_state["overall"] = STATE_OK
                raw_pipe = run_paper_pipeline(
                    repo=self.repo,
                    freshness_state=effective_freshness_state,
                    context=self._paper_pipeline_ctx,
                )
                gated_pipe, open_blocked = self._apply_paper_action_freshness_gate(raw_pipe, decision_mode)
                gated_pipe = self._apply_live_stage0_untradeable_suppression_to_pipe(gated_pipe)
                gated_pipe = self._apply_live_stage0_candidate_fallback(gated_pipe)
                self._iter_pipe = gated_pipe
                self._maybe_release_stage0_candidate_suppression()
                self._iter_reconcile_diag["open_blocked_by_freshness"] = int(open_blocked)
                if decision_mode == DECISION_MODE_SAFE:
                    log.info(
                        "DECISION_SAFE_MODE freshness=FRESHNESS_WARN decision_mode=SAFE open_blocked_by_freshness=%s",
                        int(open_blocked),
                    )
            self._iter_pipe["decision_mode"] = str(decision_mode or DECISION_MODE_HALTED).upper()
            self._iter_pipe["open_blocked_by_freshness"] = int(
                self._iter_reconcile_diag.get("open_blocked_by_freshness", 0) or 0
            )
            self._iter_pipe["freshness_reason"] = str(self._iter_pipe.get("freshness_reason", "NONE") or "NONE").upper()
            paper_action = str(self._iter_pipe.get("paper_action", "") or "").strip().upper()
            paper_reason = str(self._iter_pipe.get("paper_reason", "") or "").strip().upper()
            paper_strategy = str(self._iter_pipe.get("paper_strategy", "") or "").strip().upper()
            if paper_action == "OPEN" and paper_strategy == "MM":
                self._iter_decision_diag["mm_decision_accepted"] = 1
            freshness_reason = str(self._iter_pipe.get("freshness_reason", "NONE") or "NONE").strip().upper()
            paper_source = str(self._iter_pipe.get("paper_source", "") or "").strip() or "-"
            dedup_sig = str(self._iter_pipe.get("dedup_signature", "") or "").strip() or "-"
            matched_prev = str(self._iter_pipe.get("matched_prev_signature", "") or "").strip() or "-"
            consumed_key = str(self._iter_pipe.get("consumed_key", "") or "").strip() or "-"
            opportunity_key = str(self._iter_pipe.get("opportunity_key", "") or "").strip() or "-"
            same_opportunity_as_prev = int(self._iter_pipe.get("same_opportunity_as_prev", 0) or 0)
            skipped_as_same_opportunity = int(self._iter_pipe.get("skipped_as_same_opportunity", 0) or 0)
            selected = int(self._iter_pipe.get("selected", 1 if int(self._iter_pipe.get("cand_count", 0) or 0) > 0 else 0) or 0)
            skipped_as_stale = int(self._iter_pipe.get("skipped_as_stale", 0) or 0)
            matched_prev_bool = str(
                bool(
                    matched_prev != "-"
                    and dedup_sig != "-"
                    and matched_prev == dedup_sig
                )
            ).lower()
            paper_candidate = 1 if int(self._iter_pipe.get("cand_count", 0) or 0) > 0 else 0
            paper_action_summary = paper_action if paper_action in {"OPEN", "HOLD", "CLOSE"} else "NONE"
            if paper_action:
                self._diag_inc(self._iter_decision_diag.get("paper_action_counts", {}), paper_action)
            if paper_reason:
                self._diag_inc(self._iter_decision_diag.get("paper_reason_counts", {}), paper_reason)
            if paper_action == "HOLD" or paper_reason in {"DEDUP", "NO_DECISION"}:
                self._diag_inc(self._iter_decision_diag.get("hold_reason_counts", {}), paper_reason or "HOLD")
            log.info(
                "PAPER_SUMMARY source=%s candidate_origin=%s candidate=%s selected=%s action=%s reason=%s "
                "dedup_sig=%s matched_prev=%s skipped_as_stale=%s consumed_key=%s opportunity_key=%s "
                "same_opportunity_as_prev=%s skipped_as_same_opportunity=%s freshness_reason=%s decision_mode=%s",
                paper_source,
                "db_latest_scout_signal",
                paper_candidate,
                selected,
                paper_action_summary,
                paper_reason or "-",
                dedup_sig,
                matched_prev_bool,
                skipped_as_stale,
                consumed_key,
                opportunity_key,
                same_opportunity_as_prev,
                skipped_as_same_opportunity,
                freshness_reason,
                str(decision_mode or DECISION_MODE_HALTED).upper(),
            )
            self._iter_agent_timing["paper"] = self._iter_agent_timing.get("paper", 0.0) + (
                (time.perf_counter() - t_paper) * 1000.0
            )
            setattr(self.repo, "_runtime_freshness_state", state_obj)
            setattr(self.repo, "_runtime_pipeline_stats", dict(self._iter_pipe))
            setattr(self.repo, "_runtime_reconcile_diag", dict(self._iter_reconcile_diag))
            if decision_mode == DECISION_MODE_FULL:
                try:
                    self._auto_agent.maybe_tick(repo=self.repo, run_id=self.run_id, now=now)
                except Exception as e:
                    log.exception(f"auto_paper_agent tick failed: {e}")
            self._iter_stage_ms["agent"] = self._iter_stage_ms.get("agent", 0.0) + (
                (time.perf_counter() - agent_t0) * 1000.0
            )

            if do_reconcile:
                self.bus.publish(Timer(ts=now, purpose="reconcile"))

            for _ in range(500):
                ev = self.bus.pop()
                if ev is None:
                    break
                self._handle_event(ev)
            if self._iter_signals_buf:
                try:
                    t_build0 = time.perf_counter()
                    buf_rows = int(len(self._iter_signals_buf))
                    buf_chunks = (buf_rows + 499) // 500 if buf_rows > 0 else 0
                    build_ms = (time.perf_counter() - t_build0) * 1000.0

                    t_call0 = time.perf_counter()
                    stats = self.repo.signals.insert_signals(self._iter_signals_buf, chunk_size=500)
                    call_ms = (time.perf_counter() - t_call0) * 1000.0

                    t_post0 = time.perf_counter()

                    exec_ms = 0.0
                    rows_ok = 0
                    chunks = 0
                    if isinstance(stats, dict):
                        exec_ms = float(
                            stats.get("exec_ms", stats.get("exec", stats.get("elapsed_ms", 0.0))) or 0.0
                        )
                        rows_ok = int(stats.get("rows_ok", stats.get("rows", stats.get("inserted", 0))) or 0)
                        chunks = int(stats.get("chunks", stats.get("chunk_count", 0)) or 0)
                    elif isinstance(stats, (tuple, list)):
                        if len(stats) > 0:
                            try:
                                rows_ok = int(stats[0] or 0)
                            except Exception:
                                rows_ok = 0
                        if len(stats) > 1:
                            try:
                                exec_ms = float(stats[1] or 0.0)
                            except Exception:
                                exec_ms = 0.0
                        if len(stats) > 2:
                            try:
                                chunks = int(stats[2] or 0)
                            except Exception:
                                chunks = 0
                    if rows_ok <= 0:
                        rows_ok = buf_rows
                    if chunks <= 0:
                        chunks = buf_chunks if buf_chunks > 0 else ((rows_ok + 499) // 500 if rows_ok > 0 else 0)
                    post_ms = (time.perf_counter() - t_post0) * 1000.0
                    flush_ms = build_ms + call_ms + post_ms
                    self._iter_db_write_calls = 1
                    self._iter_signal_flush_timing["total_ms"] = (
                        self._iter_signal_flush_timing.get("total_ms", 0.0) + flush_ms
                    )
                    self._iter_signal_flush_timing["build_ms"] = (
                        self._iter_signal_flush_timing.get("build_ms", 0.0) + build_ms
                    )
                    self._iter_signal_flush_timing["call_ms"] = (
                        self._iter_signal_flush_timing.get("call_ms", 0.0) + call_ms
                    )
                    self._iter_signal_flush_timing["post_ms"] = (
                        self._iter_signal_flush_timing.get("post_ms", 0.0) + post_ms
                    )
                    self._iter_signal_flush_timing["exec_ms"] = (
                        self._iter_signal_flush_timing.get("exec_ms", 0.0) + exec_ms
                    )
                    self._iter_signal_flush_timing["rows"] = (
                        self._iter_signal_flush_timing.get("rows", 0.0) + float(rows_ok)
                    )
                    self._iter_signal_flush_timing["chunks"] = (
                        self._iter_signal_flush_timing.get("chunks", 0.0) + float(chunks)
                    )
                    self._iter_signal_flush_timing["calls"] = 1.0
                except Exception as e:
                    self._record_stage_error("agent", e, now)
                    self._queue_event(
                        ts=now,
                        level="ERROR",
                        component="agent:db_write",
                        message=str(e),
                        payload={"signals": int(len(self._iter_signals_buf))},
                    )
            self._flush_events()
            if hasattr(self.repo, "flush_if_due"):
                try:
                    self.repo.flush_if_due()
                except Exception as e:
                    log.warning("repo.flush_if_due failed: %s", e)

            sleep_start = time.perf_counter()
            time.sleep(getattr(self.settings, "dispatcher_tick_sec", 1.0))
            self._iter_stage_ms["idle"] = (time.perf_counter() - sleep_start) * 1000.0
            iter_freshness = self._compute_iter_freshness()
            self._emit_loop_status(now, force=(self._iter_errs > 0), freshness=iter_freshness)
            ui_t0 = time.perf_counter()
            self._emit_summary(now)
            ran_agent = 1 if self._iter_stage_ms.get("agent", 0.0) > 0.0 else 0
            self._emit_stage_flags(
                now,
                ran_ingest=ran_ingest,
                ran_book=ran_book,
                ran_agent=ran_agent,
                freshness=iter_freshness,
            )
            self._emit_freshness_diag(iter_freshness)
            self._iter_stage_ms["ui"] = (time.perf_counter() - ui_t0) * 1000.0
            self._iter_stage_ms["total"] = (time.perf_counter() - iter_start) * 1000.0
            agent_stage_ms = float(self._iter_stage_ms.get("agent", 0.0))
            agent_cases = float(self._iter_agent_timing.get("cases", 0.0))
            agent_scout = float(self._iter_agent_timing.get("scout", 0.0))
            agent_logic = float(self._iter_agent_timing.get("logic", 0.0))
            agent_risk = float(self._iter_agent_timing.get("risk", 0.0))
            agent_paper = float(self._iter_agent_timing.get("paper", 0.0))
            agent_explain = float(self._iter_agent_timing.get("explain", 0.0))
            known_sum = agent_cases + agent_scout + agent_logic + agent_risk + agent_paper + agent_explain
            agent_other = max(0.0, agent_stage_ms - known_sum)
            top_parts = [
                f"Scout:{agent_scout:.0f}ms(out=?)",
                f"Logic:{agent_logic:.0f}ms(out=?)",
                f"Risk:{agent_risk:.0f}ms(out=?)",
                f"Paper:{agent_paper:.0f}ms(out=?)",
                f"Explain:{agent_explain:.0f}ms(out=?)",
            ]
            flush_ms = float(self._iter_signal_flush_timing.get("total_ms", 0.0))
            flush_build_ms = float(self._iter_signal_flush_timing.get("build_ms", 0.0))
            flush_call_ms = float(self._iter_signal_flush_timing.get("call_ms", 0.0))
            flush_post_ms = float(self._iter_signal_flush_timing.get("post_ms", 0.0))
            db_exec = float(self._iter_signal_flush_timing.get("exec_ms", 0.0))
            db_rows_ok = int(self._iter_signal_flush_timing.get("rows", 0.0) or 0.0)
            db_chunks = int(self._iter_signal_flush_timing.get("chunks", 0.0) or 0.0)
            db_calls = int(self._iter_signal_flush_timing.get("calls", 0.0) or 0.0)
            db_signals = int(self._iter_db_write_signals_count or 0)
            db_ms_per_signal = db_exec / max(1, (db_rows_ok if db_calls == 1 else db_signals))
            log.info(
                "AGENT_TIMING iter=%s cases=%.0fms scout=%.0fms logic=%.0fms risk=%.0fms paper=%.0fms "
                "explain=%.0fms other=%.0fms total=%.0fms sum=%.0fms top=%s",
                self._iter,
                agent_cases,
                agent_scout,
                agent_logic,
                agent_risk,
                agent_paper,
                agent_explain,
                agent_other,
                agent_stage_ms,
                known_sum,
                ",".join(top_parts),
            )
            live_cases = self._emit_fast_agent_diag_summary()
            self._emit_pipeline_obs(live_cases)
            if db_calls == 1 and db_rows_ok > 0:
                log.info(
                    "SIGNAL_FLUSH_TIMING iter=%s total=%.0fms exec=%.0fms rows=%s chunks=%s",
                    self._iter,
                    flush_ms,
                    db_exec,
                    db_rows_ok,
                    db_chunks,
                )
            if db_calls == 1 and db_rows_ok > 0:
                log.info(
                    "SIGNAL_FLUSH_PHASES iter=%s build=%.0fms call=%.0fms post=%.0fms total=%.0fms exec=%.0fms rows=%s chunks=%s",
                    self._iter,
                    flush_build_ms,
                    flush_call_ms,
                    flush_post_ms,
                    flush_ms,
                    db_exec,
                    db_rows_ok,
                    db_chunks,
                )
            if db_calls == 1 and db_rows_ok > 0:
                log.info(
                    "DB_WRITE_DETAIL iter=%s calls=%s signals=%s prep=%.0fms exec=%.0fms chunks=%s ms_per_signal=%.3f",
                    self._iter,
                    db_calls,
                    db_rows_ok,
                    0.0,
                    db_exec,
                    db_chunks,
                    db_ms_per_signal,
                )
            log.info(
                "ITER_TIMING ingest=%.0fms db=%.0fms book=%.0fms agent=%.0fms ui=%.0fms total=%.0fms",
                float(self._iter_stage_ms.get("ingest", 0.0)),
                float(self._iter_stage_ms.get("db", 0.0)),
                float(self._iter_stage_ms.get("book", 0.0)),
                float(self._iter_stage_ms.get("agent", 0.0)),
                float(self._iter_stage_ms.get("ui", 0.0)),
                float(self._iter_stage_ms.get("total", 0.0)),
            )
            if self._wal_ck_enabled:
                ck_now = time.monotonic()
                if (ck_now - float(self._last_wal_ck_ts)) >= float(self._wal_ck_every_s):
                    ck_ms = 0.0
                    ck_busy = 0
                    ck_log = 0
                    ck_done = 0
                    try:
                        t_ck0 = time.perf_counter()
                        with self.repo.conn() as con:
                            row = con.execute(f"PRAGMA wal_checkpoint({self._wal_ck_mode})").fetchone()
                        ck_ms = (time.perf_counter() - t_ck0) * 1000.0
                        if row is not None:
                            vals = list(row)
                            if len(vals) >= 3:
                                ck_busy = int(vals[0] or 0)
                                ck_log = int(vals[1] or 0)
                                ck_done = int(vals[2] or 0)
                    except Exception:
                        log.warning("WAL_CHECKPOINT failed mode=%s", self._wal_ck_mode, exc_info=True)
                    else:
                        log.info(
                            "WAL_CHECKPOINT mode=%s ms=%.0f busy=%s log=%s done=%s",
                            self._wal_ck_mode,
                            ck_ms,
                            ck_busy,
                            ck_log,
                            ck_done,
                        )
                    self._last_wal_ck_ts = ck_now
        self._flush_events()
        if hasattr(self.repo, "flush_writes"):
            try:
                self.repo.flush_writes()
            except Exception:
                log.warning("repo.flush_writes failed", exc_info=True)

    def _latest_snapshots_by_outcome(self, market_id: str) -> dict:
        """outcome -> {bid, ask, mid, spread, liquidity}

        Берём самые свежие строки по каждому outcome.
        """
        if market_id in self._latest_snapshots_cache:
            return self._latest_snapshots_cache.get(market_id, {})
        with self.repo.conn() as con:
            rows = con.execute(
                """
                SELECT outcome, bid, ask, mid, spread, liquidity
                FROM snapshots
                WHERE market_id = ?
                ORDER BY ts DESC
                LIMIT 50
                """,
                (market_id,),
            ).fetchall()

        out = {}
        for outcome, bid, ask, mid, spread, liq in rows:
            if outcome not in out:
                out[outcome] = {
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "spread": spread,
                    "liquidity": liq,
                }
            if "YES" in out and "NO" in out:
                break
        return out


def build_dispatcher(settings, repo, bus, run_id) -> Dispatcher:
    """Canonical dispatcher constructor."""
    return MainLoop(settings=settings, repo=repo, bus=bus, run_id=run_id)
