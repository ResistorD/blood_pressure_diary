from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import deque
import json
import threading
import time

from utils.orderbook_math import calc_preview_warnings, calc_vwap_fill, calc_max_safe_size


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


GUARD_SPREAD_MAX = 8.0
GUARD_BOOK_AGE_MAX = 20.0
GUARD_MAX_SLIP_BPS = 150.0
HOLD_MINUTES = 3.0
EXPLAIN_MIN_EDGE_PCT = 1.5
EXPLAIN_TTL_SEC = 15
EXPLAIN_TOP_K = 10
EXPLAIN_SCORE_WEIGHTS = {
    "MX": 1.00,
    "IMPL": 0.90,
    "OVERROUND": 0.70,
    "DIVERGENCE": 0.60,
    "NONE": 0.00,
}
EVID_DAYS = 7
EVID_TTL_SEC = 120
EVID_MIN_N = 8
EVID_MIN_WINRATE = 0.50
EVID_MIN_AVG_PNL = 0.00


@dataclass
class AutoPaperConfig:
    cadence_sec: int = 10
    max_positions: int = 1
    size_preset: int = 1
    close_min_chunk: int = 1
    close_hold_minutes: int = 3
    emergency_hold_minutes: int = 10
    close_allow_guarded: bool = True
    close_allow_when_stale: bool = False


class AutoPaperAgent:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._enabled: bool = False
        self._mode: str = "paper"
        self._config = AutoPaperConfig()
        self._current: Dict[str, Any] | None = None
        self._last_tick_ts: str = ""
        self._last_tick_mono: float = 0.0
        self._last_error: str | None = None
        self._stats = {"opens": 0, "closes": 0, "skips": 0, "errors": 0}
        self._events: deque[Dict[str, Any]] = deque(maxlen=200)
        self._explain_cache: Dict[str, Dict[str, Any]] = {}
        self._evid_cache: Dict[str, Any] = {"ts": 0.0, "by_type": {}, "summary": {}}

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "mode": self._mode,
                "cadence_sec": int(self._config.cadence_sec),
                "max_positions": int(self._config.max_positions),
                "size_preset": int(self._config.size_preset),
                "close_min_chunk": int(self._config.close_min_chunk),
                "close_hold_minutes": int(self._config.close_hold_minutes),
                "emergency_hold_minutes": int(self._config.emergency_hold_minutes),
                "close_allow_guarded": bool(self._config.close_allow_guarded),
                "close_allow_when_stale": bool(self._config.close_allow_when_stale),
                "current": self._current,
                "last_tick_ts": self._last_tick_ts,
                "stats": dict(self._stats),
                "last_error": self._last_error,
            }

    def get_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        lim = max(1, min(int(limit or 100), 200))
        with self._lock:
            items = list(self._events)[-lim:]
        return items

    def start(self, **kwargs: Any) -> Dict[str, Any]:
        with self._lock:
            self._enabled = True
            self._apply_config_locked(**kwargs)
            self._log_event_locked("START", detail={"config": self._config.__dict__})
        return self.get_state()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._enabled = False
            self._log_event_locked("STOP", detail={})
        return self.get_state()

    def update_config(self, **kwargs: Any) -> Dict[str, Any]:
        with self._lock:
            self._apply_config_locked(**kwargs)
            self._log_event_locked("CONFIG", detail={"config": self._config.__dict__})
        return self.get_state()

    def maybe_tick(self, *, repo: Any, run_id: str, now: Optional[datetime] = None) -> None:
        if now is None:
            now = datetime.now(timezone.utc)
        with self._lock:
            if not self._enabled:
                return
            cadence = max(1, int(self._config.cadence_sec))
            mono = time.monotonic()
            if mono - self._last_tick_mono < float(cadence):
                return
            self._last_tick_mono = mono
            self._last_tick_ts = now.isoformat(timespec="seconds")
        try:
            self._tick(repo=repo, run_id=run_id, now=now)
        except Exception as e:
            with self._lock:
                self._stats["errors"] += 1
                self._last_error = str(e)
                self._log_event_locked("ERROR", detail={"error": str(e)})

    # --- internals ---
    def _tick(self, *, repo: Any, run_id: str, now: datetime) -> None:
        if self._is_paused(repo):
            self._record_skip("PAUSED")
            return

        self._sync_current_from_repo(repo)

        current = self._get_current()
        if self._is_stale(repo, max_age_sec=60):
            with self._lock:
                allow_when_stale = bool(self._config.close_allow_when_stale)
            if current and allow_when_stale:
                pass
            else:
                self._record_skip("STALE_DATA")
                return
        if current:
            self._handle_existing_position(repo=repo, run_id=run_id, now=now, current=current)
            return

        if not self._can_open_more(repo):
            self._record_skip("MAX_POSITIONS")
            return

        candidate, meta = self._pick_candidate(repo)
        if meta:
            self._log_event("TICK", detail=meta)
        if not candidate:
            reason = (meta or {}).get("reason") or "NO_CANDIDATE"
            detail = {k: v for k, v in (meta or {}).items() if k != "reason"}
            if reason == "EVIDENCE_BLOCKED":
                self._record_skip("EVIDENCE_BLOCKED", detail=detail)
            elif reason == "NO_EXPLAIN_EDGE":
                self._record_skip("NO_EXPLAIN_EDGE", detail=detail)
            else:
                self._record_skip("NO_CANDIDATE", detail=detail)
            return

        self._attempt_open(repo=repo, run_id=run_id, now=now, candidate=candidate)

    def _apply_config_locked(self, **kwargs: Any) -> None:
        if "cadence_sec" in kwargs and kwargs["cadence_sec"] is not None:
            self._config.cadence_sec = max(1, int(kwargs["cadence_sec"]))
        if "max_positions" in kwargs and kwargs["max_positions"] is not None:
            self._config.max_positions = max(1, int(kwargs["max_positions"]))
        if "size_preset" in kwargs and kwargs["size_preset"] is not None:
            self._config.size_preset = max(1, int(kwargs["size_preset"]))
        if "close_min_chunk" in kwargs and kwargs["close_min_chunk"] is not None:
            self._config.close_min_chunk = max(1, int(kwargs["close_min_chunk"]))
        if "close_hold_minutes" in kwargs and kwargs["close_hold_minutes"] is not None:
            self._config.close_hold_minutes = max(1, int(kwargs["close_hold_minutes"]))
        if "emergency_hold_minutes" in kwargs and kwargs["emergency_hold_minutes"] is not None:
            self._config.emergency_hold_minutes = max(1, int(kwargs["emergency_hold_minutes"]))
        if "close_allow_guarded" in kwargs and kwargs["close_allow_guarded"] is not None:
            self._config.close_allow_guarded = bool(kwargs["close_allow_guarded"])
        if "close_allow_when_stale" in kwargs and kwargs["close_allow_when_stale"] is not None:
            self._config.close_allow_when_stale = bool(kwargs["close_allow_when_stale"])

    def _log_event_locked(
        self,
        event_type: str,
        *,
        case_id: str | None = None,
        market_id: str | None = None,
        detail: Dict[str, Any] | None = None,
        ) -> None:
        self._events.append(
            {
                "ts": _now_iso(),
                "type": str(event_type),
                "case_id": case_id,
                "market_id": market_id,
                "detail": detail or {},
            }
        )

    def _log_event(
        self,
        event_type: str,
        *,
        case_id: str | None = None,
        market_id: str | None = None,
        detail: Dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._log_event_locked(event_type, case_id=case_id, market_id=market_id, detail=detail)

    def _record_skip(self, reason: str, *, detail: Dict[str, Any] | None = None) -> None:
        with self._lock:
            self._stats["skips"] += 1
            self._log_event_locked("SKIP", detail={"reason": reason, **(detail or {})})

    def _get_current(self) -> Dict[str, Any] | None:
        with self._lock:
            return self._current

    def _set_current(self, current: Dict[str, Any] | None) -> None:
        with self._lock:
            self._current = current

    def _can_open_more(self, repo: Any) -> bool:
        try:
            if hasattr(repo, "count_paper_positions_filtered"):
                open_cnt = int(repo.count_paper_positions_filtered(status="OPEN"))
            else:
                open_cnt = int(repo.count_paper_positions())
        except Exception:
            open_cnt = 0
        with self._lock:
            return open_cnt < int(self._config.max_positions)

    def _is_paused(self, repo: Any) -> bool:
        try:
            if hasattr(repo, "is_paused"):
                return bool(repo.is_paused())
        except Exception:
            return False
        return False

    def _last_data_ts(self, repo: Any) -> str:
        last_snapshot_ts = ""
        last_signal_ts = ""
        try:
            with repo.conn() as con:
                row = con.execute("SELECT MAX(ts) AS ts FROM snapshots").fetchone()
            last_snapshot_ts = str(row["ts"]) if row and row["ts"] else ""
        except Exception:
            last_snapshot_ts = ""
        try:
            with repo.conn() as con:
                row = con.execute("SELECT MAX(ts) AS ts FROM signals").fetchone()
            last_signal_ts = str(row["ts"]) if row and row["ts"] else ""
        except Exception:
            last_signal_ts = ""
        if last_snapshot_ts or last_signal_ts:
            return max(last_snapshot_ts, last_signal_ts)
        return ""

    def _is_stale(self, repo: Any, *, max_age_sec: int = 60) -> bool:
        ts = self._last_data_ts(repo)
        if not ts:
            return True
        try:
            dt = datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            return age > float(max_age_sec)
        except Exception:
            return True

    def _parse_levels(self, raw: str | None) -> List[Dict[str, float]]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []
        out: List[Dict[str, float]] = []
        for x in data or []:
            try:
                px = float(x.get("price"))
                sz = float(x.get("size"))
                if sz <= 0:
                    continue
                out.append({"price": px, "size": sz})
            except Exception:
                continue
        return out

    def _load_orderbook(self, repo: Any, market_id: str) -> Dict[str, Any] | None:
        if hasattr(repo, "get_latest_orderbook_snapshot"):
            try:
                return repo.get_latest_orderbook_snapshot(market_id)
            except Exception:
                return None
        return None

    def _book_age_s(self, book: Dict[str, Any] | None) -> float | None:
        if not book:
            return None
        ts = book.get("ts_utc") or ""
        try:
            dt = datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except Exception:
            return None

    def _get_position_qty(self, repo: Any, market_id: str, outcome: str) -> float:
        try:
            with repo.conn() as con:
                row = con.execute(
                    """
                    SELECT qty
                    FROM paper_positions
                    WHERE market_id = ?
                      AND outcome = ?
                      AND status = 'OPEN' LIMIT 1
                    """,
                    (market_id, outcome),
                ).fetchone()
            if row:
                return float(row["qty"] or 0.0)
        except Exception:
            return 0.0
        return 0.0

    def _spread_pct_from_book(self, book: Dict[str, Any] | None) -> float | None:
        if not book:
            return None
        bid = book.get("best_bid")
        ask = book.get("best_ask")
        mid = book.get("mid")
        try:
            if mid is None and bid is not None and ask is not None:
                mid = (float(bid) + float(ask)) / 2.0
            if bid is None or ask is None or mid is None or float(mid) <= 0:
                return None
            spread_abs = max(0.0, float(ask) - float(bid))
            return (spread_abs / float(mid)) * 100.0
        except Exception:
            return None

    def _age_sec_from_ts(self, ts: str | None) -> float | None:
        if not ts:
            return None
        try:
            dt = datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except Exception:
            return None

    def _get_latest_mid(self, repo: Any, market_id: str, outcome: str) -> float | None:
        if not hasattr(repo, "get_latest_snapshots"):
            return None
        try:
            latest = repo.get_latest_snapshots(market_id)
        except Exception:
            return None
        if not isinstance(latest, dict):
            return None
        data = latest.get(outcome, {}) if isinstance(latest.get(outcome, {}), dict) else {}
        val = data.get("mid")
        if val is None:
            val = data.get("implied_prob")
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    def _calc_excursions(self, entry_mid: float, best_mid: float, worst_mid: float, current_mid: float, outcome: str) -> dict:
        if entry_mid <= 0:
            return {}
        if str(outcome).upper() == "NO":
            pnl = (entry_mid - current_mid) / entry_mid * 100.0
            best_runup = (entry_mid - worst_mid) / entry_mid * 100.0
            worst_draw = (entry_mid - best_mid) / entry_mid * 100.0
        else:
            pnl = (current_mid - entry_mid) / entry_mid * 100.0
            best_runup = (best_mid - entry_mid) / entry_mid * 100.0
            worst_draw = (worst_mid - entry_mid) / entry_mid * 100.0
        return {
            "pnl_pct": pnl,
            "best_runup_pct": best_runup,
            "worst_drawdown_pct": worst_draw,
        }

    def _update_excursion_open(self, repo: Any, market_id: str, outcome: str, current_mid: float) -> dict | None:
        if current_mid is None:
            return None
        try:
            with repo.conn() as con:
                row = con.execute(
                    """
                    SELECT position_id, entry_mid, best_mid_seen, worst_mid_seen
                    FROM paper_positions
                    WHERE market_id = ?
                      AND outcome = ?
                      AND status = 'OPEN' LIMIT 1
                    """,
                    (market_id, outcome),
                ).fetchone()
                if not row:
                    return None
                entry_mid = float(row["entry_mid"]) if row["entry_mid"] is not None else float(current_mid)
                best_mid = float(row["best_mid_seen"]) if row["best_mid_seen"] is not None else entry_mid
                worst_mid = float(row["worst_mid_seen"]) if row["worst_mid_seen"] is not None else entry_mid
                best_mid = max(best_mid, float(current_mid))
                worst_mid = min(worst_mid, float(current_mid))
                con.execute(
                    """
                    UPDATE paper_positions
                    SET entry_mid=?,
                        best_mid_seen=?,
                        worst_mid_seen=?
                    WHERE position_id=?
                    """,
                    (entry_mid, best_mid, worst_mid, row["position_id"]),
                )
        except Exception:
            return None
        metrics = {
            "entry_mid": entry_mid,
            "best_mid_seen": best_mid,
            "worst_mid_seen": worst_mid,
        }
        metrics.update(self._calc_excursions(entry_mid, best_mid, worst_mid, float(current_mid), outcome))
        return metrics

    def _median(self, vals: list[float]) -> float | None:
        if not vals:
            return None
        vals = sorted(vals)
        mid = len(vals) // 2
        if len(vals) % 2 == 1:
            return float(vals[mid])
        return (float(vals[mid - 1]) + float(vals[mid])) / 2.0

    def _ts_from_iso(self, raw: str | None) -> float | None:
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None

    def _fetch_evidence_rows(self, repo: Any, days: int = EVID_DAYS) -> list[dict]:
        days = max(1, min(int(days or EVID_DAYS), 365))
        now_ts = datetime.now(timezone.utc).timestamp()
        from_ts = now_ts - float(days) * 86400.0
        try:
            with repo.conn() as con:
                rows = con.execute(
                    """
                    SELECT explain_type, explain_edge_pct, realized_pnl_pct, best_runup_pct,
                           worst_drawdown_pct, opened_ts, closed_ts, opened_at
                    FROM paper_positions
                    WHERE status='CLOSED'
                      AND closed_ts IS NOT NULL
                      AND closed_ts BETWEEN ? AND ?
                    """,
                    (from_ts, now_ts),
                ).fetchall()
        except Exception:
            rows = []

        buckets: dict[str, dict[str, Any]] = {}
        for rrow in rows or []:
            etype = str(rrow["explain_type"] or "NONE").upper()
            b = buckets.setdefault(
                etype,
                {
                    "pnl": [],
                    "best": [],
                    "worst": [],
                    "edge": [],
                    "holds": [],
                    "wins": 0,
                    "n": 0,
                },
            )
            pnl = rrow["realized_pnl_pct"]
            best = rrow["best_runup_pct"]
            worst = rrow["worst_drawdown_pct"]
            edge = rrow["explain_edge_pct"]
            opened_ts = rrow["opened_ts"]
            closed_ts = rrow["closed_ts"]
            if opened_ts is None:
                opened_ts = self._ts_from_iso(rrow["opened_at"])
            if pnl is not None:
                b["pnl"].append(float(pnl))
                if float(pnl) > 0:
                    b["wins"] += 1
            if best is not None:
                b["best"].append(float(best))
            if worst is not None:
                b["worst"].append(float(worst))
            if edge is not None:
                b["edge"].append(float(edge))
            if opened_ts is not None and closed_ts is not None:
                try:
                    b["holds"].append(float(closed_ts) - float(opened_ts))
                except Exception:
                    pass
            b["n"] += 1

        out_rows = []
        for etype, b in buckets.items():
            n = int(b["n"] or 0)
            if n <= 0:
                continue
            pnl_list = b["pnl"]
            best_list = b["best"]
            worst_list = b["worst"]
            edge_list = b["edge"]
            holds = b["holds"]
            winrate = float(b["wins"] or 0) / float(n) if n else 0.0
            out_rows.append(
                {
                    "explain_type": etype,
                    "n": n,
                    "winrate": winrate,
                    "avg_pnl_pct": (sum(pnl_list) / len(pnl_list)) if pnl_list else None,
                    "median_pnl_pct": self._median(pnl_list),
                    "avg_best_pct": (sum(best_list) / len(best_list)) if best_list else None,
                    "avg_worst_pct": (sum(worst_list) / len(worst_list)) if worst_list else None,
                    "avg_hold_sec": (sum(holds) / len(holds)) if holds else None,
                    "avg_edge_pct": (sum(edge_list) / len(edge_list)) if edge_list else None,
                }
            )
        return out_rows

    def _compute_evidence_policy(self, rows: list[dict]) -> dict[str, dict[str, Any]]:
        policy: dict[str, dict[str, Any]] = {}
        for r in rows or []:
            etype = str(r.get("explain_type") or "NONE").upper()
            n = int(r.get("n") or 0)
            win = float(r.get("winrate") or 0.0)
            avg = r.get("avg_pnl_pct")
            avg_val = float(avg) if avg is not None else None
            mode = "UNKNOWN"
            mult = 1.0
            if n >= EVID_MIN_N and avg_val is not None:
                if avg_val < float(EVID_MIN_AVG_PNL) and win < float(EVID_MIN_WINRATE):
                    mode = "HARD"
                    mult = 0.0
                elif avg_val < 0:
                    mode = "SOFT"
                    mult = 0.5
                elif avg_val > 0.5 and win >= 0.55:
                    mode = "BONUS"
                    mult = 1.2
                else:
                    mode = "NEUTRAL"
                    mult = 1.0
            policy[etype] = {
                "mode": mode,
                "mult": mult,
                "n": n,
                "avg": avg_val,
                "win": win,
            }
        return policy

    def _get_evidence_policy(self, repo: Any) -> dict[str, dict[str, Any]]:
        now = time.time()
        cached = self._evid_cache or {}
        if cached.get("by_type") and (now - float(cached.get("ts") or 0.0)) < float(EVID_TTL_SEC):
            return dict(cached.get("by_type") or {})
        rows = self._fetch_evidence_rows(repo, days=EVID_DAYS)
        policy = self._compute_evidence_policy(rows)
        summary = {}
        for k, v in policy.items():
            avg = v.get("avg")
            win = v.get("win")
            n = v.get("n")
            mult = v.get("mult")
            mode = v.get("mode")
            avg_txt = f"{avg:.2f}" if isinstance(avg, float) else "—"
            win_txt = f"{win:.2f}" if isinstance(win, float) else "—"
            mult_txt = f"{mult:.2f}" if isinstance(mult, float) else "—"
            summary[k] = f"{mode} n={n} avg={avg_txt} win={win_txt} mult={mult_txt}"
        self._evid_cache = {"ts": now, "by_type": policy, "summary": summary}
        self._log_event(
            "EVIDENCE_POLICY",
            detail={"days": EVID_DAYS, "min_n": EVID_MIN_N, "summary": summary},
        )
        return policy

    def _finalize_excursion(self, repo: Any, market_id: str, outcome: str, exit_mid: float | None) -> dict | None:
        if exit_mid is None:
            return None
        try:
            with repo.conn() as con:
                row = con.execute(
                    """
                    SELECT position_id, entry_mid, best_mid_seen, worst_mid_seen
                    FROM paper_positions
                    WHERE market_id = ?
                      AND outcome = ?
                    ORDER BY opened_at DESC LIMIT 1
                    """,
                    (market_id, outcome),
                ).fetchone()
                if not row:
                    return None
                entry_mid = float(row["entry_mid"]) if row["entry_mid"] is not None else float(exit_mid)
                best_mid = float(row["best_mid_seen"]) if row["best_mid_seen"] is not None else entry_mid
                worst_mid = float(row["worst_mid_seen"]) if row["worst_mid_seen"] is not None else entry_mid
                best_mid = max(best_mid, float(exit_mid))
                worst_mid = min(worst_mid, float(exit_mid))
                metrics = self._calc_excursions(entry_mid, best_mid, worst_mid, float(exit_mid), outcome)
                con.execute(
                    """
                    UPDATE paper_positions
                    SET exit_mid=?,
                        realized_pnl_pct=?,
                        best_runup_pct=?,
                        worst_drawdown_pct=?,
                        best_mid_seen=?,
                        worst_mid_seen=?
                    WHERE position_id=?
                    """,
                    (
                        float(exit_mid),
                        metrics.get("pnl_pct"),
                        metrics.get("best_runup_pct"),
                        metrics.get("worst_drawdown_pct"),
                        best_mid,
                        worst_mid,
                        row["position_id"],
                    ),
                )
        except Exception:
            return None
        metrics.update(
            {
                "entry_mid": entry_mid,
                "best_mid_seen": best_mid,
                "worst_mid_seen": worst_mid,
            }
        )
        return metrics

    def _extract_prob(self, latest: dict) -> float | None:
        yes = latest.get("YES", {}) if isinstance(latest, dict) else {}
        val = yes.get("mid") if isinstance(yes, dict) else None
        if val is None and isinstance(yes, dict):
            val = yes.get("implied_prob")
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    def _is_mutex_pair(self, title_a: str, title_b: str) -> bool:
        a = title_a.lower()
        b = title_b.lower()
        patterns = [
            ("wins", "loses"),
            ("republican wins", "democrat wins"),
            ("increase", "decrease"),
            ("above", "below"),
        ]
        for pa, pb in patterns:
            if pa in a and pb in b:
                return True
            if pb in a and pa in b:
                return True
        return False

    def _is_implication_pair(self, title_a: str, title_b: str) -> tuple[bool, int]:
        a = title_a.lower()
        b = title_b.lower()
        if "wins" in a and "candidate" in b:
            return True, 0
        if "candidate" in a and "wins" in b:
            return True, 1
        return False, 0

    def _explain_case(self, repo: Any, case_id: str) -> Dict[str, Any]:
        group_key = None
        try:
            with repo.conn() as con:
                row = con.execute(
                    "SELECT group_key FROM markets WHERE market_id = ?",
                    (case_id,),
                ).fetchone()
            group_key = row["group_key"] if row else None
        except Exception:
            group_key = None

        if not group_key:
            return {"case_id": case_id, "type": "NONE", "edge_pct": None, "detail": {}}

        try:
            markets = repo.list_markets_by_group(group_key, limit=50)
        except Exception:
            markets = []
        if not markets:
            return {"case_id": case_id, "type": "NONE", "edge_pct": None, "detail": {}}

        market_ids = [m.market_id for m in markets]
        try:
            latest_map = repo.get_latest_snapshots_batch(market_ids)
        except Exception:
            latest_map = {}

        probs: dict[str, float] = {}
        titles: dict[str, str] = {}
        for m in markets:
            titles[m.market_id] = m.title or m.market_id
            p = self._extract_prob(latest_map.get(m.market_id, {}))
            if p is not None:
                probs[m.market_id] = p

        if len(market_ids) == 2:
            a, b = market_ids[0], market_ids[1]
            pa = probs.get(a)
            pb = probs.get(b)
            if pa is not None and pb is not None:
                if self._is_mutex_pair(titles.get(a, ""), titles.get(b, "")):
                    gap = pa + pb - 1.0
                    if gap > 0.02:
                        return {
                            "case_id": case_id,
                            "type": "MX",
                            "edge_pct": gap * 100.0,
                            "detail": {"pa": pa, "pb": pb, "gap": gap},
                        }
                is_impl, flip = self._is_implication_pair(titles.get(a, ""), titles.get(b, ""))
                if is_impl:
                    if flip == 0:
                        diff = pa - pb
                        if diff > 0.02:
                            return {
                                "case_id": case_id,
                                "type": "IMPL",
                                "edge_pct": diff * 100.0,
                                "detail": {"pa": pa, "pb": pb, "diff": diff},
                            }
                    else:
                        diff = pb - pa
                        if diff > 0.02:
                            return {
                                "case_id": case_id,
                                "type": "IMPL",
                                "edge_pct": diff * 100.0,
                                "detail": {"pa": pb, "pb": pa, "diff": diff},
                            }

                diff = abs(pa - pb)
                if diff > 0.05:
                    return {
                        "case_id": case_id,
                        "type": "DIVERGENCE",
                        "edge_pct": diff * 100.0,
                        "detail": {"pa": pa, "pb": pb, "diff": diff},
                    }

        if len(market_ids) >= 3:
            vals = [probs.get(mid) for mid in market_ids if probs.get(mid) is not None]
            if vals:
                overround = sum(vals) - 1.0
                if overround > 0.03:
                    return {
                        "case_id": case_id,
                        "type": "OVERROUND",
                        "edge_pct": overround * 100.0,
                        "detail": {"sum_p": sum(vals), "overround": overround},
                    }

        return {"case_id": case_id, "type": "NONE", "edge_pct": None, "detail": {}}

    def _get_explain(self, repo: Any, case_id: str) -> Dict[str, Any]:
        now = time.time()
        cached = self._explain_cache.get(case_id)
        if cached and (now - float(cached.get("ts") or 0.0)) < float(EXPLAIN_TTL_SEC):
            return dict(cached.get("data") or {})
        data = self._explain_case(repo, case_id)
        self._explain_cache[case_id] = {"ts": now, "data": data}
        return data

    def _score_explain(self, explain: Dict[str, Any], evid: dict | None = None) -> tuple[float, float, str, float]:
        typ = str(explain.get("type") or "NONE")
        weight = float(EXPLAIN_SCORE_WEIGHTS.get(typ, 0.0))
        edge = explain.get("edge_pct")
        try:
            edge_val = float(edge) if edge is not None else 0.0
        except Exception:
            edge_val = 0.0
        if edge_val < float(EXPLAIN_MIN_EDGE_PCT) or weight <= 0:
            return 0.0, 0.0, "NONE", 0.0
        base = edge_val * weight
        evid_mult = 1.0
        mode = "NONE"
        if evid:
            mode = str(evid.get("mode") or "NONE")
            evid_mult = float(evid.get("mult") or 1.0)
            if mode == "HARD":
                return 0.0, base, mode, evid_mult
        return base * evid_mult, base, mode, evid_mult

    def _pick_candidate(self, repo: Any) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
        try:
            rows = repo.list_cases(minutes_signals=30, minutes_snaps=10)
            if rows and not isinstance(rows[0], dict):
                rows = [dict(x) for x in rows]
        except Exception:
            rows = []
        if not rows:
            return None, {"reason": "NO_CANDIDATE", "candidates_checked": 0}
        filtered = []
        for c in rows:
            mid = c.get("market_id")
            if not mid:
                continue
            status = (c.get("status") or "").upper()
            if status in {"BLOCKED", "CLOSED"}:
                continue
            age = self._age_sec_from_ts(c.get("last_signal_ts") or c.get("last_snapshot_ts"))
            if age is not None and age > 60:
                continue
            liq = c.get("liq")
            try:
                if liq is not None and float(liq) <= 0:
                    continue
            except Exception:
                continue
            filtered.append(c)
        if not filtered:
            return None, {"reason": "NO_CANDIDATE", "candidates_checked": 0}

        def _score(c: Dict[str, Any]) -> tuple:
            prio = c.get("prio")
            if prio is None:
                prio = float(c.get("signal_count") or 0.0)
            ts = c.get("last_signal_ts") or c.get("last_snapshot_ts") or ""
            return (float(prio or 0.0), str(ts))

        filtered.sort(key=_score, reverse=True)
        shortlist = filtered[: int(EXPLAIN_TOP_K)]
        evid_policy = self._get_evidence_policy(repo)
        scored = []
        blocked_types = set()
        for c in shortlist:
            market_id = str(c.get("market_id") or "")
            explain = self._get_explain(repo, market_id)
            etype = str(explain.get("type") or "NONE").upper()
            evid = evid_policy.get(etype)
            score, base_score, evid_mode, evid_mult = self._score_explain(explain, evid)
            if evid_mode == "HARD":
                blocked_types.add(etype)
            prio = float(c.get("prio") or c.get("signal_count") or 0.0)
            spread = c.get("spread")
            liq = c.get("liq")
            age = self._age_sec_from_ts(c.get("last_signal_ts") or c.get("last_snapshot_ts"))
            try:
                spread_val = float(spread) if spread is not None else None
            except Exception:
                spread_val = None
            try:
                liq_val = float(liq) if liq is not None else None
            except Exception:
                liq_val = None
            tie = (
                score,
                -(age if age is not None else 0.0),
                liq_val if liq_val is not None else 0.0,
                -(spread_val if spread_val is not None else 0.0),
                prio,
            )
            scored.append((tie, c, explain, score, base_score, evid_mode, evid_mult))

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0] if scored else None
        if not best or best[3] <= 0:
            reason = "NO_EXPLAIN_EDGE"
            detail = {"candidates_checked": len(shortlist)}
            if blocked_types:
                reason = "EVIDENCE_BLOCKED"
                detail.update(
                    {
                        "blocked_types": sorted(blocked_types),
                        "days": EVID_DAYS,
                        "min_n": EVID_MIN_N,
                    }
                )
            return None, {"reason": reason, **detail}
        _, candidate, explain, score, base_score, evid_mode, evid_mult = best
        candidate = dict(candidate)
        candidate["_explain"] = explain
        candidate["_explain_score"] = score
        candidate["_explain_base_score"] = base_score
        candidate["_evid_mode"] = evid_mode
        candidate["_evid_mult"] = evid_mult
        return candidate, {
            "chosen_case_id": candidate.get("market_id"),
            "explain_type": explain.get("type"),
            "edge_pct": explain.get("edge_pct"),
            "base_score": base_score,
            "evid_mult": evid_mult,
            "final_score": score,
            "candidates_checked": len(shortlist),
        }

    def _sync_current_from_repo(self, repo: Any) -> None:
        if self._get_current() is not None:
            return
        try:
            if hasattr(repo, "list_paper_positions_filtered"):
                rows = repo.list_paper_positions_filtered(limit=1, status="OPEN", sort_by="opened_at", sort_dir="desc")
            else:
                rows = repo.list_paper_positions(limit=1)
        except Exception:
            rows = []
        if not rows:
            return
        row = rows[0]
        try:
            if isinstance(row, dict):
                market_id = row.get("market_id")
                outcome = row.get("outcome")
                qty = float(row.get("qty") or 0.0)
                opened_at = row.get("opened_at") or ""
                entry_mid = row.get("entry_mid")
                best_mid = row.get("best_mid_seen")
                worst_mid = row.get("worst_mid_seen")
            else:
                opened_at, market_id, outcome, qty, _avg_price, _status = row
                entry_mid = None
                best_mid = None
                worst_mid = None
        except Exception:
            return
        if not market_id:
            return
        if entry_mid is None and hasattr(repo, "conn"):
            try:
                with repo.conn() as con:
                    erow = con.execute(
                        """
                        SELECT entry_mid, best_mid_seen, worst_mid_seen
                        FROM paper_positions
                        WHERE market_id = ?
                          AND outcome = ?
                          AND status = 'OPEN' LIMIT 1
                        """,
                        (market_id, outcome or "YES"),
                    ).fetchone()
                if erow:
                    entry_mid = erow["entry_mid"]
                    best_mid = erow["best_mid_seen"]
                    worst_mid = erow["worst_mid_seen"]
            except Exception:
                pass
        current = {
            "case_id": str(market_id),
            "market_id": str(market_id),
            "side": str(outcome or "YES"),
            "size": float(qty or 0.0),
            "opened_ts": str(opened_at or _now_iso()),
            "entry_mid": entry_mid,
            "best_mid_seen": best_mid,
            "worst_mid_seen": worst_mid,
            "entry_est_vwap": None,
            "entry_spread_pct": None,
            "entry_book_age_s": None,
            "entry_slip_bps": None,
            "rationale": ["Синхронизация позиции из БД"],
        }
        self._set_current(current)

    def _handle_existing_position(self, *, repo: Any, run_id: str, now: datetime, current: Dict[str, Any]) -> None:
        market_id = str(current.get("market_id") or "")
        if not market_id:
            self._set_current(None)
            self._record_skip("NO_MARKET_ID")
            return
        try:
            has_open = bool(repo.paper_has_open_position(market_id))
        except Exception:
            has_open = True
        if not has_open:
            self._set_current(None)
            self._record_skip("POSITION_GONE")
            return

        outcome = str(current.get("side") or "YES")
        latest_mid = self._get_latest_mid(repo, market_id, outcome)
        if latest_mid is not None:
            metrics = self._update_excursion_open(repo, market_id, outcome, latest_mid)
            if metrics:
                cur = dict(current)
                cur.update(metrics)
                self._set_current(cur)

        opened_ts = current.get("opened_ts") or ""
        opened_dt = None
        try:
            opened_dt = datetime.fromisoformat(str(opened_ts))
            if opened_dt.tzinfo is None:
                opened_dt = opened_dt.replace(tzinfo=timezone.utc)
        except Exception:
            opened_dt = None

        with self._lock:
            close_hold_min = int(self._config.close_hold_minutes)
            emergency_min = int(self._config.emergency_hold_minutes)
            close_min_chunk = int(self._config.close_min_chunk)
            allow_guarded = bool(self._config.close_allow_guarded)
            allow_when_stale = bool(self._config.close_allow_when_stale)

        if opened_dt is not None:
            hold_sec = float(close_hold_min) * 60.0
            emergency_sec = float(emergency_min) * 60.0
            elapsed = (now - opened_dt).total_seconds()
        else:
            hold_sec = float(close_hold_min) * 60.0
            emergency_sec = float(emergency_min) * 60.0
            elapsed = 0.0

        emergency = elapsed >= emergency_sec
        should_close = elapsed >= hold_sec

        if not should_close:
            self._record_skip("HOLDING", detail={"market_id": market_id})
            return

        if self._is_stale(repo, max_age_sec=60) and not allow_when_stale:
            self._record_skip("STALE_DATA", detail={"market_id": market_id})
            return

        size = self._get_position_qty(repo, market_id, str(current.get("side") or "YES"))
        if size <= 0:
            self._record_skip("NO_SIZE", detail={"market_id": market_id})
            return

        book = self._load_orderbook(repo, market_id)
        if not book:
            if emergency:
                self._log_event(
                    "WARN",
                    case_id=market_id,
                    market_id=market_id,
                    detail={"reason": "NO_ORDERBOOK", "mode": "EMERGENCY_UNWIND"},
                )
            else:
                self._record_skip("NO_ORDERBOOK", detail={"market_id": market_id, "phase": "close"})
                return
        bids = self._parse_levels(book.get("bids_json")) if book else []
        bid = book.get("best_bid") if book else None
        ask = book.get("best_ask") if book else None
        mid = book.get("mid") if book else None
        if mid is None and bid is not None and ask is not None:
            try:
                mid = (float(bid) + float(ask)) / 2.0
            except Exception:
                mid = None
        book_age_s = self._book_age_s(book)
        spread_pct = self._spread_pct_from_book(book)

        safe_sell = None
        if mid is not None and book:
            try:
                safe_sell = calc_max_safe_size(bids, mid=mid, max_slip_bps=GUARD_MAX_SLIP_BPS, side="sell")
            except Exception:
                safe_sell = None

        chunk = min(float(close_min_chunk), float(size))
        if safe_sell is None or safe_sell <= 0:
            if emergency:
                chunk = min(float(close_min_chunk), float(size))
            else:
                self._record_skip("NO_SAFE_CLOSE", detail={"market_id": market_id, "safe_max_size_sell": safe_sell})
                return
        else:
            chunk = min(chunk, float(safe_sell))
        if chunk <= 0:
            self._record_skip("NO_CHUNK", detail={"market_id": market_id})
            return

        vwap_result = calc_vwap_fill(bids, chunk, side="bid") if book else {"vwap": None, "filled": 0.0}
        est_vwap = vwap_result["vwap"]
        filled = float(vwap_result["filled"] or 0.0)
        warnings = calc_preview_warnings(
            size_shares=chunk,
            book_present=bool(book),
            filled_shares=filled,
            book_age_s=book_age_s,
            top_of_book=False,
            stale_threshold_sec=GUARD_BOOK_AGE_MAX,
        )
        slip_bps = None
        try:
            if mid is not None and est_vwap is not None:
                slip_bps = (abs(float(mid) - float(est_vwap)) / float(mid)) * 10000.0 if float(mid) else None
        except Exception:
            slip_bps = None

        if not emergency and book_age_s is not None and book_age_s > GUARD_BOOK_AGE_MAX:
            self._record_skip("STALE_BOOK", detail={"market_id": market_id, "book_age_s": book_age_s})
            return

        if not allow_guarded:
            guard_reasons = []
            if spread_pct is None or spread_pct > GUARD_SPREAD_MAX:
                guard_reasons.append("WIDE_SPREAD")
            if slip_bps is None or abs(slip_bps) > GUARD_MAX_SLIP_BPS:
                guard_reasons.append("HIGH_IMPACT")
            if "INSUFFICIENT_DEPTH" in warnings:
                guard_reasons.append("INSUFFICIENT_DEPTH")
            if guard_reasons:
                self._record_skip(
                    "GUARDED",
                    detail={"market_id": market_id, "guard_reasons": guard_reasons},
                )
                return

        price = est_vwap if est_vwap is not None else mid
        if price is None:
            if emergency:
                price = 0.50
            else:
                self._record_skip("NO_PRICE", detail={"market_id": market_id})
                return

        close_result = repo.paper_close(
            run_id=run_id,
            market_id=market_id,
            outcome=str(current.get("side") or "YES"),
            price=float(price),
            qty=float(chunk),
            note="auto_agent:close",
        )
        if isinstance(close_result, dict) and not close_result.get("ok", True):
            self._record_skip(
                "CLOSE_FAILED",
                detail={"market_id": market_id, "error": close_result.get("error")},
            )
            return
        closed_qty = float(close_result.get("closed_qty") or 0.0) if isinstance(close_result, dict) else float(chunk)
        remaining = None
        if isinstance(close_result, dict):
            remaining = close_result.get("remaining_qty")
        if remaining is None:
            remaining = max(0.0, float(size) - float(closed_qty))

        self._log_event(
            "CLOSE_CHUNK",
            case_id=market_id,
            market_id=market_id,
            detail={
                "mode": "EMERGENCY_UNWIND" if emergency else "NORMAL",
                "qty": closed_qty,
                "remaining": remaining,
                "slip_bps": slip_bps,
                "safe_max_sell": safe_sell,
                "warnings": warnings,
            },
        )

        if remaining <= 0:
            self._set_current(None)
            exit_mid = mid if mid is not None else price
            metrics = self._finalize_excursion(repo, market_id, outcome, exit_mid)
            with self._lock:
                self._stats["closes"] += 1
                self._log_event_locked(
                    "CLOSE_DONE",
                    case_id=market_id,
                    market_id=market_id,
                    detail={
                        "mode": "EMERGENCY_UNWIND" if emergency else "NORMAL",
                        "total_closed": float(size),
                        "held_sec": float(elapsed),
                        "spread_pct": spread_pct,
                        "book_age_s": book_age_s,
                        "ignored_guards": bool(allow_guarded),
                        "realized_pnl_pct": metrics.get("pnl_pct") if metrics else None,
                        "best_runup_pct": metrics.get("best_runup_pct") if metrics else None,
                        "worst_drawdown_pct": metrics.get("worst_drawdown_pct") if metrics else None,
                    },
                )
        else:
            cur = dict(current)
            cur["size"] = remaining
            self._set_current(cur)

    def _attempt_open(self, *, repo: Any, run_id: str, now: datetime, candidate: Dict[str, Any]) -> None:
        market_id = str(candidate.get("market_id") or "")
        if not market_id:
            self._record_skip("NO_MARKET_ID")
            return
        try:
            if repo.paper_has_open_position(market_id):
                self._record_skip("ALREADY_OPEN", detail={"market_id": market_id})
                return
        except Exception:
            pass

        book = self._load_orderbook(repo, market_id)
        if not book:
            self._record_skip("NO_ORDERBOOK", detail={"market_id": market_id, "phase": "open"})
            return
        bids = self._parse_levels(book.get("bids_json"))
        asks = self._parse_levels(book.get("asks_json"))
        bid = book.get("best_bid")
        ask = book.get("best_ask")
        mid = book.get("mid")
        if mid is None and bid is not None and ask is not None:
            try:
                mid = (float(bid) + float(ask)) / 2.0
            except Exception:
                mid = None
        book_age_s = self._book_age_s(book)
        spread_pct = self._spread_pct_from_book(book)

        with self._lock:
            size_preset = int(self._config.size_preset)
        if size_preset <= 0:
            size_preset = 1

        safe_buy = None
        if mid is not None:
            try:
                safe_buy = calc_max_safe_size(asks, mid=mid, max_slip_bps=GUARD_MAX_SLIP_BPS, side="buy")
            except Exception:
                safe_buy = None

        if safe_buy is None or safe_buy <= 0:
            self._record_skip(
                "SAFE_SIZE_TOO_SMALL",
                detail={"market_id": market_id, "safe_max_size_buy": safe_buy},
            )
            return

        size = float(min(size_preset, safe_buy))

        vwap_result = calc_vwap_fill(asks, size, side="ask")
        est_vwap = vwap_result["vwap"]
        filled = float(vwap_result["filled"] or 0.0)
        warnings = calc_preview_warnings(
            size_shares=size,
            book_present=True,
            filled_shares=filled,
            book_age_s=book_age_s,
            top_of_book=False,
            stale_threshold_sec=GUARD_BOOK_AGE_MAX,
        )

        slip_bps = None
        try:
            if mid is not None and est_vwap is not None:
                slip_bps = (abs(float(est_vwap) - float(mid)) / float(mid)) * 10000.0 if float(mid) else None
        except Exception:
            slip_bps = None

        if spread_pct is None or spread_pct > GUARD_SPREAD_MAX:
            self._record_skip("WIDE_SPREAD", detail={"market_id": market_id, "spread_pct": spread_pct})
            return
        if book_age_s is None or book_age_s > GUARD_BOOK_AGE_MAX:
            self._record_skip("STALE_BOOK", detail={"market_id": market_id, "book_age_s": book_age_s})
            return
        if "INSUFFICIENT_DEPTH" in warnings:
            self._record_skip("INSUFFICIENT_DEPTH", detail={"market_id": market_id})
            return
        if slip_bps is None or abs(slip_bps) > GUARD_MAX_SLIP_BPS:
            self._record_skip("HIGH_IMPACT", detail={"market_id": market_id, "slip_bps": slip_bps})
            return

        price = est_vwap if est_vwap is not None else mid
        if price is None:
            self._record_skip("NO_PRICE", detail={"market_id": market_id})
            return

        explain = candidate.get("_explain") or {}
        score = candidate.get("_explain_score")
        base_score = candidate.get("_explain_base_score")
        evid_mult = candidate.get("_evid_mult")
        meta = {}
        if explain:
            meta = {
                "explain_type": explain.get("type"),
                "explain_edge_pct": explain.get("edge_pct"),
                "explain_score": score,
            }
        repo.paper_buy(
            run_id=run_id,
            market_id=market_id,
            outcome="YES",
            qty=float(size),
            price=float(price),
            note="auto_agent:open",
            meta=meta if meta else None,
        )
        current = {
            "case_id": market_id,
            "market_id": market_id,
            "side": "YES",
            "size": float(size),
            "opened_ts": now.isoformat(timespec="seconds"),
            "entry_mid": mid,
            "entry_est_vwap": est_vwap,
            "entry_spread_pct": spread_pct,
            "entry_book_age_s": book_age_s,
            "entry_slip_bps": slip_bps,
            "rationale": [
                "Picked by explain score",
                f"Safe size buy={safe_buy}, chosen={int(size)}",
                f"Preview slip={slip_bps:.0f}bps <= {GUARD_MAX_SLIP_BPS:.0f}bps" if slip_bps is not None else "No slip calc",
                f"Spread={spread_pct:.2f}% OK" if spread_pct is not None else "Spread unknown",
                f"Book={book_age_s:.0f}s OK" if book_age_s is not None else "Book age unknown",
            ],
        }
        if mid is not None:
            metrics = self._update_excursion_open(repo, market_id, "YES", float(mid))
            if metrics:
                current.update(metrics)
        if explain:
            et = explain.get("type") or "NONE"
            ep = explain.get("edge_pct")
            try:
                ep_txt = f"{float(ep):.1f}%"
            except Exception:
                ep_txt = "—"
            current["rationale"].insert(1, f"Picked by explain: {et} edge {ep_txt} (score {score:.2f})" if score is not None else f"Picked by explain: {et} edge {ep_txt}")
        self._set_current(current)
        with self._lock:
            self._stats["opens"] += 1
            self._log_event_locked(
                "OPEN",
                case_id=market_id,
                market_id=market_id,
                detail={
                    "size": size,
                    "mid": mid,
                    "est_vwap": est_vwap,
                    "slip_bps": slip_bps,
                    "spread_pct": spread_pct,
                    "book_age_s": book_age_s,
                    "safe_max_size_buy": safe_buy,
                    "picked_by_explain": True,
                    "why": current["rationale"][1] if len(current["rationale"]) > 1 else "",
                    "score": score,
                    "base_score": base_score,
                    "evid_mult": evid_mult,
                    "rationale": list(current.get("rationale") or []),
                },
            )


_AUTO_AGENT: AutoPaperAgent | None = None


def get_auto_paper_agent() -> AutoPaperAgent:
    global _AUTO_AGENT
    if _AUTO_AGENT is None:
        _AUTO_AGENT = AutoPaperAgent()
    return _AUTO_AGENT
