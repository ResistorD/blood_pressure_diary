from __future__ import annotations

import logging
import time
import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.settings import Settings
from db.repo import Repo
from dispatcher.bus import EventBus
from dispatcher.events import Alert, MarketTick, Timer
from dispatcher.scheduler import Scheduler
from ingest.ingestor import Ingestor
from ingest.polymarket_client import PolymarketClient, _extract_tokens_from_row
from ingest.orderbook_collector import OrderbookCollector
from db.agent_provider import RepoAgentDataProvider

from agents.enhanced_base import AgentContext
from agents.quant import QuantAgent
from decision.engine import DecisionEngineV0
from execution.reconcile import reconcile_paper
from app.risk_gate import RiskGate
from dispatcher.contract import Dispatcher
from agents.auto_paper_agent import get_auto_paper_agent

log = logging.getLogger("dispatcher.loop")


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
        self._db_path_logged = False
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
        self._last_ingest_done_utc: Optional[str] = None
        self._last_book_done_utc: Optional[str] = None
        self._last_agent_done_utc: Optional[str] = None

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

    def _db_freshness_ages(self) -> Dict[str, Any]:
        data_age_s: Optional[float] = None
        book_age_s: Optional[float] = None
        data_ts_max = ""
        book_ts_max = ""
        data_age_src = "snapshots.ts"
        book_age_src = "orderbook_snapshots.ts_utc"
        now = datetime.now(timezone.utc)
        try:
            with self.repo.conn() as con:
                row = con.execute("SELECT MAX(ts) AS ts FROM snapshots").fetchone()
            ts = str(row["ts"]) if row and row["ts"] else ""
            data_ts_max = ts
            if not ts:
                # Match /health/state compatibility fallback for legacy schemas.
                try:
                    with self.repo.conn() as con:
                        row = con.execute("SELECT MAX(updated_at) AS ts FROM snapshots").fetchone()
                    ts = str(row["ts"]) if row and row["ts"] else ""
                    data_ts_max = ts
                    data_age_src = "snapshots.updated_at"
                except Exception:
                    ts = ""
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                data_age_s = max(0.0, (now - dt).total_seconds())
        except Exception:
            data_age_s = None
        try:
            with self.repo.conn() as con:
                row = con.execute("SELECT MAX(ts_utc) AS ts FROM orderbook_snapshots").fetchone()
            ts = str(row["ts"]) if row and row["ts"] else ""
            book_ts_max = ts
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                book_age_s = max(0.0, (now - dt).total_seconds())
        except Exception:
            book_age_s = None
        return {
            "data_age_s": data_age_s,
            "book_age_s": book_age_s,
            "data_ts_max": data_ts_max,
            "book_ts_max": book_ts_max,
            "data_age_src": data_age_src,
            "book_age_src": book_age_src,
        }

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

    def _emit_loop_status(self, now: datetime, *, force: bool = False) -> None:
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
        freshness = self._db_freshness_ages()
        data_age_s = freshness.get("data_age_s")
        book_age_s = freshness.get("book_age_s")
        pulse_data_age_s = self._age_sec(self._last_ingest_done_utc or "")
        pulse_book_age_s = self._age_sec(self._last_book_done_utc or "")
        pulse_agent_age_s = self._age_sec(self._last_agent_done_utc or "")
        data_ts_max = str(freshness.get("data_ts_max") or "")
        book_ts_max = str(freshness.get("book_ts_max") or "")
        data_age_src = str(freshness.get("data_age_src") or "snapshots.ts")
        book_age_src = str(freshness.get("book_age_src") or "orderbook_snapshots.ts_utc")
        pulse_data_age = self._fmt_age_s(pulse_data_age_s)
        pulse_book_age = self._fmt_age_s(pulse_book_age_s)
        pulse_agent_age = self._fmt_age_s(pulse_agent_age_s)
        market_data_age = self._fmt_age_s(data_age_s)
        market_book_age = self._fmt_age_s(book_age_s)
        log.info(
            "LOOP t=%s iter=%s ingest=%.0fms book=%.0fms agent=%.0fms reconcile=%.0fms idle=%.0fms "
            "errs=%s pulse_data_age=%s pulse_book_age=%s pulse_agent_age=%s "
            "market_data_age=%s market_book_age=%s ingest_ins=%s book_ins=%s "
            "cnt[i_ok=%s i_err=%s b_ok=%s b_err=%s a_ok=%s a_err=%s sk_book0=%s] "
            "err_age[i=%s b=%s a=%s] "
            "data_ts_max=%s data_age_src=%s book_ts_max=%s book_age_src=%s",
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
            market_data_age,
            market_book_age,
            int(self._telemetry.get("last_ingest_snapshots", 0) or 0),
            int(self._telemetry.get("last_book_inserted", 0) or 0),
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
            data_age_src,
            book_ts_max or "none",
            book_age_src,
        )

    def _emit_summary(self, now: datetime) -> None:
        mono = time.monotonic()
        if (mono - self._last_summary_log_ts) < 10.0:
            return
        self._last_summary_log_ts = mono
        freshness = self._db_freshness_ages()
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

    def _emit_stage_flags(self, now: datetime, *, ran_ingest: int, ran_book: int, ran_agent: int) -> None:
        mono = time.monotonic()
        if (mono - self._last_stage_flags_log_ts) < 10.0:
            return
        self._last_stage_flags_log_ts = mono
        pulse_data_age_s = self._age_sec(self._last_ingest_done_utc or "")
        pulse_book_age_s = self._age_sec(self._last_book_done_utc or "")
        paused = 0
        try:
            if hasattr(self.repo, "is_paused"):
                paused = 1 if bool(self.repo.is_paused()) else 0
        except Exception:
            paused = 0
        stale = 0
        stale_reason = "OK"
        if pulse_data_age_s is None:
            stale = 1
            stale_reason = "NO_PULSE_DATA"
        elif pulse_data_age_s > 45.0:
            stale = 1
            stale_reason = "PULSE_DATA_GT_45S"
        elif pulse_book_age_s is None:
            stale = 1
            stale_reason = "NO_PULSE_BOOK"
        elif pulse_book_age_s > 7.0:
            stale = 1
            stale_reason = "PULSE_BOOK_GT_7S"
        trading_enabled = 1 if (not paused and bool(getattr(self.settings, "enable_decision", True))) else 0
        log.info(
            "STAGES ran_ingest=%s ran_book=%s ran_agent=%s paused=%s stale=%s stale_reason=%s "
            "pulse_data_age=%s pulse_book_age=%s trading_enabled=%s",
            int(ran_ingest),
            int(ran_book),
            int(ran_agent),
            int(paused),
            int(stale),
            stale_reason,
            self._fmt_age_s(pulse_data_age_s),
            self._fmt_age_s(pulse_book_age_s),
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
        for agent in getattr(self, "fast_agents", []):
            try:
                signals = agent.propose(ctx, market_id=market_id)
                for s in signals:
                    self.repo.insert_signal(s)
            except Exception as e:
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
        for agent in getattr(self, "slow_agents", []):
            try:
                # Prefer signature propose(ctx) for slow scans; fallback to per-market scan.
                try:
                    signals = agent.propose(ctx)  # type: ignore[arg-type]
                except TypeError:
                    signals = []
                    for m in self.repo.list_markets(limit=200):
                        signals.extend(agent.propose(ctx, market_id=m.market_id))
                for s in signals:
                    self.repo.insert_signal(s)
            except Exception as e:
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
                # Slow agents first: generate cross-market signals before decisions
                if self.settings.enable_agents:
                    self._run_slow_agents(ctx)
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
                self._iter_stage_ms["reconcile"] = self._iter_stage_ms.get("reconcile", 0.0) + (
                    (time.perf_counter() - t0) * 1000.0
                )

                self._queue_event(
                    ts=now,
                    level="INFO",
                    component="decision",
                    message=f"decisions written: {n} | paper executed: {x}",
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
            self._iter_stage_ms = {"ingest": 0.0, "book": 0.0, "agent": 0.0, "reconcile": 0.0, "idle": 0.0}
            self._iter_errs = 0
            ran_ingest = 0
            ran_book = 0
            now = datetime.now(timezone.utc)
            do_poll, do_reconcile = self.scheduler.tick(now)

            mono = time.monotonic()
            if do_poll and self.settings.enable_ingest and mono >= self._next_ingest_ts:
                t0 = time.perf_counter()
                try:
                    print("INGEST TICK", now)
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
                    log.info(
                        "INGEST_OK fetched=%s parsed=%s inserted=%s markets=%s",
                        fetched_n,
                        parsed_n,
                        inserted_n,
                        int(m_cnt or 0),
                    )
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
            else:
                self._telemetry["skipped_ingest_guard"] = int(self._telemetry.get("skipped_ingest_guard", 0) or 0) + 1
                if not do_poll:
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
                    print("BOOK TICK", now)
                    ran_book = 1
                    active_ids, target_stats = self._active_orderbook_targets(top_n=30)
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
                    stats = self.book_collector.collect(active_ids)
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
                                "orderbook: total=%s inserted=%s errors=%s dropped_no_clob=%s skipped_missing=%s last_book_count=%s max_age_s=%s",
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
                                "orderbook: total=%s inserted=%s errors=%s dropped_no_clob=%s skipped_missing=%s last_book_count=%s max_age_s=%s",
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

            try:
                self._auto_agent.maybe_tick(repo=self.repo, run_id=self.run_id, now=now)
            except Exception as e:
                log.exception(f"auto_paper_agent tick failed: {e}")

            if do_reconcile:
                self.bus.publish(Timer(ts=now, purpose="reconcile"))

            for _ in range(500):
                ev = self.bus.pop()
                if ev is None:
                    break
                self._handle_event(ev)
            self._flush_events()
            if hasattr(self.repo, "flush_if_due"):
                try:
                    self.repo.flush_if_due()
                except Exception as e:
                    log.warning("repo.flush_if_due failed: %s", e)

            sleep_start = time.perf_counter()
            time.sleep(getattr(self.settings, "dispatcher_tick_sec", 1.0))
            self._iter_stage_ms["idle"] = (time.perf_counter() - sleep_start) * 1000.0
            self._emit_loop_status(now, force=(self._iter_errs > 0))
            self._emit_summary(now)
            ran_agent = 1 if self._iter_stage_ms.get("agent", 0.0) > 0.0 else 0
            self._emit_stage_flags(now, ran_ingest=ran_ingest, ran_book=ran_book, ran_agent=ran_agent)
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
