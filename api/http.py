from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
from collections import deque

import os
import json
import uuid
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, quote_plus

from fastapi import Depends, FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from execution.reconcile import reconcile_paper
from app.utils.static_version import get_static_version
from utils.logging import warn_exc
from utils.orderbook_math import calc_book_warnings, calc_depth, calc_preview_warnings, calc_vwap_fill, calc_max_safe_size

import logging

from agents.auto_paper_agent import get_auto_paper_agent

logger = logging.getLogger("api.http")

# ----- LAG detection (in-memory price history) -----
PRICE_HIST_WINDOW_SEC = 300.0
PRICE_HIST_MAXLEN = 600
price_hist: Dict[str, deque[tuple[float, float]]] = {}
_last_lag_log_ts = 0.0

GUARD_SPREAD_MAX = 8.0
GUARD_DEPTH_MIN_USD = 500.0
GUARD_BOOK_AGE_MAX = 20.0
STATIC_V = get_static_version()


def _is_dev_mode() -> bool:
    v = (os.getenv("PS_DEV") or "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _resolve_kill_kind_from_reason(kill_switch_reason: str) -> str:
    up = str(kill_switch_reason or "").strip().upper()
    if not up.startswith("AUTO:"):
        return "MANUAL" if up else "NONE"
    tail = str(kill_switch_reason or "").split(":", 1)[1].strip() if ":" in str(kill_switch_reason or "") else ""
    if tail == "слишком много открытых paper-позиций":
        return "AUTO_LIMIT_MAX_OPEN_POSITIONS"
    if tail == "исчерпан общий лимит капитала (paper)":
        return "AUTO_LIMIT_MAX_NOTIONAL_TOTAL"
    if tail.startswith("capital usage "):
        return "AUTO_LIMIT_MAX_CAPITAL_USAGE_PCT"
    if tail == "исчерпан лимит экспозиции по кластеру":
        return "AUTO_LIMIT_MAX_NOTIONAL_PER_GROUP"
    if tail == "уже есть открытая paper-позиция по рынку":
        return "AUTO_LIMIT_MARKET_ALREADY_OPEN"
    return "AUTO_OTHER"


def _infer_risk_kind_from_decision(reason: str, status: str) -> str:
    st = str(status or "").strip().upper()
    if st != "BLOCKED":
        return "NONE"
    txt = str(reason or "").strip()
    up = txt.upper()
    if up.startswith("KILL:"):
        return "KILL_SWITCH"
    if up.startswith("RISK:"):
        return "RISK_CONSTRAINT_SIGNAL"
    if up.startswith("DATA:"):
        return "QUALITY_ALERT_SIGNAL"
    if up.startswith("LIMIT:"):
        low = txt.lower()
        if "по рынку" in low:
            return "LIMIT_MARKET_ALREADY_OPEN"
        if "по кластеру" in low:
            return "LIMIT_MAX_NOTIONAL_PER_GROUP"
        if "открытых paper-позиций" in low:
            return "LIMIT_MAX_OPEN_POSITIONS"
        if "общий лимит капитала" in low:
            return "LIMIT_MAX_NOTIONAL_TOTAL"
        if "capital usage" in low:
            return "LIMIT_MAX_CAPITAL_USAGE_PCT"
    return "NONE"


def _infer_freshness_gate(reason: str) -> str:
    up = str(reason or "").strip().upper()
    if "FRESHNESS_WARN_OPEN_BLOCKED" in up:
        return "OPEN_BLOCKED_WARN"
    if "FRESHNESS_STOP_HALTED" in up or "FRESHNESS_STOP" in up:
        return "HALTED_STOP"
    return "NONE"


def build_case_decision_why(
    latest_decision: Dict[str, Any] | None,
    runtime_pipe: Dict[str, Any] | None,
    kill_switch_reason: str = "",
) -> Dict[str, Any]:
    ld = latest_decision or {}
    rp = runtime_pipe or {}
    decision_status = str(ld.get("status") or "—").strip().upper() or "—"
    decision_reason = str(ld.get("reason") or "").strip() or "—"
    risk_kind = _infer_risk_kind_from_decision(decision_reason, decision_status)
    kill_kind = "NONE"
    if risk_kind == "KILL_SWITCH":
        kill_kind = _resolve_kill_kind_from_reason(kill_switch_reason)
    freshness_reason = str(rp.get("freshness_reason") or "").strip().upper()
    if not freshness_reason or freshness_reason == "NONE":
        if "FRESHNESS_WARN_OPEN_BLOCKED" in decision_reason.upper():
            freshness_reason = "FRESHNESS_WARN_OPEN_BLOCKED"
        elif "FRESHNESS_STOP" in decision_reason.upper():
            freshness_reason = "FRESHNESS_STOP_HALTED"
        else:
            freshness_reason = "NONE"
    decision_mode = str(rp.get("decision_mode") or "").strip().upper()
    if not decision_mode:
        if freshness_reason == "FRESHNESS_WARN_OPEN_BLOCKED":
            decision_mode = "SAFE"
        elif freshness_reason == "FRESHNESS_STOP_HALTED":
            decision_mode = "HALTED"
        else:
            decision_mode = "FULL"
    open_blocked_by_freshness = int(rp.get("open_blocked_by_freshness", 0) or 0)
    freshness_gate = _infer_freshness_gate(decision_reason)
    return {
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "risk_kind": risk_kind,
        "kill_kind": kill_kind,
        "freshness_gate": freshness_gate,
        "freshness_reason": freshness_reason,
        "decision_mode": decision_mode,
        "open_blocked_by_freshness": open_blocked_by_freshness,
    }


def build_case_reason_summary(decision_why: Dict[str, Any] | None, fallback_reason: str = "") -> Dict[str, str]:
    w = decision_why or {}
    kill_kind = str(w.get("kill_kind") or "NONE").strip().upper()
    risk_kind = str(w.get("risk_kind") or "NONE").strip().upper()
    freshness_gate = str(w.get("freshness_gate") or "NONE").strip().upper()
    freshness_reason = str(w.get("freshness_reason") or "NONE").strip().upper()
    decision_status = str(w.get("decision_status") or "").strip().upper()
    decision_reason = str(w.get("decision_reason") or "").strip()

    if kill_kind and kill_kind != "NONE":
        return {"primary": "KILL", "secondary": kill_kind, "kind": "danger", "secondary_kind": "muted"}
    if risk_kind and risk_kind != "NONE":
        return {"primary": "RISK", "secondary": risk_kind, "kind": "warning", "secondary_kind": "muted"}
    if (freshness_gate and freshness_gate != "NONE") or (freshness_reason and freshness_reason != "NONE"):
        secondary = freshness_gate if freshness_gate != "NONE" else freshness_reason
        return {"primary": "FRESHNESS", "secondary": secondary, "kind": "warning", "secondary_kind": "muted"}
    if decision_status == "BLOCKED":
        code = decision_reason.split(":", 1)[0].strip().upper() if decision_reason else "BLOCKED"
        return {"primary": "BLOCKED", "secondary": code or "BLOCKED", "kind": "danger", "secondary_kind": "muted"}
    if decision_reason:
        code = decision_reason.split(":", 1)[0].strip().upper() or "NORMAL"
        return {"primary": "NORMAL", "secondary": code, "kind": "success", "secondary_kind": "muted"}
    if fallback_reason:
        code = str(fallback_reason).split(":", 1)[0].strip().upper() or "NORMAL"
        return {"primary": "NORMAL", "secondary": code, "kind": "success", "secondary_kind": "muted"}
    return {"primary": "NORMAL", "secondary": "—", "kind": "success", "secondary_kind": "muted"}


def _record_price(market_id: str, mid: float, ts: float | None = None) -> None:
    if not market_id or mid is None:
        return
    now = float(ts or time.time())
    dq = price_hist.get(market_id)
    if dq is None:
        dq = deque(maxlen=PRICE_HIST_MAXLEN)
        price_hist[market_id] = dq
    dq.append((now, float(mid)))
    while dq and (now - dq[0][0]) > PRICE_HIST_WINDOW_SEC:
        dq.popleft()


def _get_price_ago(market_id: str, seconds: int = 60) -> float | None:
    dq = price_hist.get(market_id)
    if not dq:
        return None
    target = time.time() - float(seconds)
    for ts, price in reversed(dq):
        if ts <= target:
            return float(price)
    return None


def _micro_guard_ok(r, market_id: str) -> bool:
    book = _load_orderbook(r, market_id)
    if not book:
        return False
    bids = _parse_levels(book.get("bids_json"))
    asks = _parse_levels(book.get("asks_json"))
    bid = book.get("best_bid")
    ask = book.get("best_ask")
    mid = book.get("mid")
    if mid is None and bid is not None and ask is not None:
        try:
            mid = (float(bid) + float(ask)) / 2.0
        except Exception:
            mid = None
    try:
        if bid is None or ask is None or mid is None:
            return False
        spread_abs = max(0.0, float(ask) - float(bid))
        spread_pct = (spread_abs / float(mid)) * 100.0 if mid else None
    except Exception:
        spread_pct = None
    if spread_pct is None or spread_pct > GUARD_SPREAD_MAX:
        return False
    try:
        dt = datetime.fromisoformat(str(book.get("ts_utc")))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        book_age_s = (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        book_age_s = None
    if book_age_s is None or book_age_s > GUARD_BOOK_AGE_MAX:
        return False
    if mid:
        try:
            depth_ask_1 = calc_depth(asks, mid=mid, pct=0.01, side="ask")
            depth_bid_1 = calc_depth(bids, mid=mid, pct=0.01, side="bid")
        except Exception:
            depth_ask_1 = None
            depth_bid_1 = None
        if depth_ask_1 is None or depth_bid_1 is None:
            return False
        if min(float(depth_ask_1), float(depth_bid_1)) < GUARD_DEPTH_MIN_USD:
            return False
    return True

# Optional enhanced dashboard (v2)
try:
    from api.dashboard_v2 import router as dashboard_v2_router
except Exception:  # pragma: no cover
    dashboard_v2_router = None  # type: ignore

try:
    from app.risk_gate import RiskGate
except Exception:  # pragma: no cover
    RiskGate = None  # type: ignore


def create_app(*, settings, repo, bus) -> FastAPI:
    """FastAPI app factory.

    Важно: роуты регистрируются внутри функции, чтобы не было module-global `app`.
    """
    app = FastAPI()

    app.state.settings = settings
    app.state.repo = repo
    app.state.bus = bus
    app.state.exec_stats = {"samples": []}
    app.state.dev_mode = bool(getattr(settings, "dev_mode", False)) or _is_dev_mode()
    app.state.static_v = STATIC_V

    def _template_ctx(request: Request) -> Dict[str, str]:
        if getattr(request.app.state, "dev_mode", False):
            return {"static_v": str(int(time.time()))}
        return {"static_v": str(getattr(request.app.state, "static_v", STATIC_V))}

    templates = Jinja2Templates(directory="ui/templates", context_processors=[_template_ctx])
    app.mount("/static", StaticFiles(directory="ui/static"), name="static")

    if app.state.dev_mode:
        @app.middleware("http")
        async def _dev_no_cache(request: Request, call_next):
            response = await call_next(request)
            content_type = (response.headers.get("content-type") or "").lower()
            is_html = "text/html" in content_type
            is_static = request.url.path.startswith("/static/")
            if is_html or is_static:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            return response

    # Mount v2 dashboard API if available
    if dashboard_v2_router is not None:
        app.include_router(dashboard_v2_router)

    @app.on_event("startup")
    def _log_db_startup() -> None:
        db_path = getattr(repo, "db_path", "unknown")
        logger.info(f"DB path (repo): {db_path}")
        for table in ("markets", "signals", "snapshots"):
            try:
                with repo.conn() as con:
                    row = con.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
                n = int(row["n"]) if row else 0
                logger.info(f"DB count {table}: {n}")
            except Exception as e:
                logger.error(f"DB count failed for {table}: {e}")

    # ---------- UI helpers (RU labels) ----------
    RU_STATUS = {
        "OK": "ОК",
        "OPPORTUNITY": "Возможность",
        "INVESTIGATE": "Проверить",
        "BLOCKED": "Заблокировано",
    }
    RU_KIND = {
        "ANOMALY": "Связь/кластер",
        "PAIR_ARB": "Арбитраж пары",
        "QUALITY_ALERT": "Качество данных",
        "RISK_CONSTRAINT": "Ограничение риска",
    }
    RU_DECISION_ACTION = {
        "HOLD": "Наблюдать",
        "INVESTIGATE": "Проверить",
        "BUY": "Купить",
        "SELL": "Продать",
        "PAPER_BUY": "Открыть (paper)",
        "PAPER_CLOSE": "Закрыть (paper)",
        "PAPER_BUY_BOTH": "Открыть paper (обе стороны)",
        "PAPER_CLOSE_BOTH": "Закрыть paper (обе стороны)",
    }

    def ru_status(s: str) -> str:
        return RU_STATUS.get((s or "").upper(), s or "")

    def ru_kind(k: str) -> str:
        return RU_KIND.get((k or "").upper(), k or "")

    def ru_action(a: str) -> str:
        return RU_DECISION_ACTION.get((a or "").upper(), a or "")

    def fnum(x: Any, nd: int = 3) -> str:
        try:
            if x is None:
                return ""
            return f"{float(x):.{nd}f}"
        except Exception:
            return str(x)

    def _repo(request: Request):
        return request.app.state.repo

    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default

    def _int_arg(request: Request, key: str, default: int, min_v: int, max_v: int) -> int:
        try:
            v = int(request.query_params.get(key, str(default)))
        except Exception:
            v = default
        return max(min_v, min(max_v, v))

    def _build_pager(
        request: Request,
        *,
        total: int,
        page: int,
        size: int,
        page_key: str = "page",
        size_key: str = "size",
    ) -> Dict[str, Any]:
        pages = max(1, (int(total) + int(size) - 1) // int(size))
        page = max(1, min(page, pages))
        base_params = dict(request.query_params)
        base_params[size_key] = str(size)
        prev_url = None
        next_url = None
        if page > 1:
            p = dict(base_params)
            p[page_key] = str(page - 1)
            prev_url = f"{request.url.path}?{urlencode(p)}"
        if page < pages:
            p = dict(base_params)
            p[page_key] = str(page + 1)
            next_url = f"{request.url.path}?{urlencode(p)}"
        return {
            "total": int(total),
            "page": page,
            "size": int(size),
            "pages": pages,
            "prev_url": prev_url,
            "next_url": next_url,
        }

    def _nav_counts(
        request: Request,
        *,
        markets_total: int | None = None,
        signals_total: int | None = None,
        cases_total: int | None = None,
        decisions_total: int | None = None,
        positions_total: int | None = None,
    ) -> Dict[str, int]:
        r = _repo(request)
        counts: Dict[str, int] = {}

        def _set(name: str, value: int | None, fallback_fn) -> None:
            if value is not None:
                counts[name] = int(value)
                return
            try:
                v = fallback_fn()
                counts[name] = int(v) if v is not None else 0
            except Exception:
                counts[name] = 0

        _set("markets", markets_total, lambda: getattr(r, "count_markets")())
        _set("signals", signals_total, lambda: getattr(r, "count_signals")())
        _set("cases", cases_total, lambda: getattr(r, "count_cases")())
        _set("decisions", decisions_total, lambda: getattr(r, "count_decisions_v0")())
        if positions_total is not None:
            counts["positions"] = int(positions_total)
        else:
            try:
                if hasattr(r, "count_paper_positions_filtered"):
                    counts["positions"] = int(r.count_paper_positions_filtered(status="OPEN"))
                else:
                    counts["positions"] = int(getattr(r, "count_paper_positions")())
            except Exception:
                counts["positions"] = 0
        return counts

    def build_nav_context(
        request: Request,
        active: str,
        *,
        markets_total: int | None = None,
        signals_total: int | None = None,
        cases_total: int | None = None,
        decisions_total: int | None = None,
        positions_total: int | None = None,
    ) -> Dict[str, Any]:
        return {
            "nav_active": active,
            "nav_counts": _nav_counts(
                request,
                markets_total=markets_total,
                signals_total=signals_total,
                cases_total=cases_total,
                decisions_total=decisions_total,
                positions_total=positions_total,
            ),
        }

    def _as_tuples(rows) -> List[Tuple]:
        out: List[Tuple] = []
        for r in rows or []:
            try:
                out.append(tuple(r))
            except Exception:
                out.append((r,))
        return out

    def _get_gate(request: Request):
        if RiskGate is None:
            return None
        r = _repo(request)
        s = request.app.state.settings
        try:
            return RiskGate(r, s)
        except TypeError:
            try:
                return RiskGate(repo=r, settings=s)
            except Exception:
                try:
                    return RiskGate(r)
                except Exception:
                    warn_exc(logger, "risk gate init failed (fallback)")
                    return None
        except Exception:
            warn_exc(logger, "risk gate init failed")
            return None

    def _reconcile_now(r):
        # UI не должен падать из-за reconcile.
        try:
            reconcile_paper(r, run_id="ui")
        except Exception:
            warn_exc(logger, "reconcile_paper failed from UI")

    def _require_admin_token(request: Request) -> None:
        token = (request.headers.get("x-admin-token") or "").strip()
        if not token:
            auth = (request.headers.get("authorization") or "").strip()
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
        expected = (os.getenv("ADMIN_TOKEN") or "").strip()
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ADMIN_TOKEN is not configured",
            )
        if token != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin token",
            )

    def _health_state(r) -> Dict[str, Any]:
        last_snapshot_ts = ""
        last_signal_ts = ""
        last_ingest_ts = ""
        last_ingest_row_count_5m = 0
        table_used = "snapshots"
        column_used = "updated_at"
        last_ingest_ts_source = "db.snapshots.max(updated_at)"
        try:
            with r.conn() as con:
                # PRIMARY: use updated_at (wall clock) — immune to frozen API timestamps
                row = con.execute(
                    """
                    SELECT
                        MAX(updated_at) AS ts,
                        SUM(CASE WHEN julianday(updated_at) >= julianday('now','-5 minutes') THEN 1 ELSE 0 END) AS n5m
                    FROM snapshots
                    WHERE updated_at IS NOT NULL AND updated_at <> ''
                    """
                ).fetchone()
            if row and row["ts"]:
                last_snapshot_ts = str(row["ts"])
                last_ingest_ts = last_snapshot_ts
                last_ingest_row_count_5m = int(row["n5m"] or 0)
                column_used = "updated_at"
                last_ingest_ts_source = "db.snapshots.max(updated_at)"
            else:
                # FALLBACK: use ts (API timestamp)
                with r.conn() as con:
                    row = con.execute(
                        """
                        SELECT
                            MAX(ts) AS ts,
                            SUM(CASE WHEN julianday(ts) >= julianday('now','-5 minutes') THEN 1 ELSE 0 END) AS n5m
                        FROM snapshots
                        """
                    ).fetchone()
                last_snapshot_ts = str(row["ts"]) if row and row["ts"] else ""
                last_ingest_ts = last_snapshot_ts
                last_ingest_row_count_5m = int(row["n5m"] or 0) if row else 0
                column_used = "ts"
                last_ingest_ts_source = "db.snapshots.max(ts)"
        except Exception:
            last_snapshot_ts = ""
            last_ingest_ts = ""
            last_ingest_row_count_5m = 0
        try:
            with r.conn() as con:
                row = con.execute("SELECT MAX(ts) AS ts FROM signals").fetchone()
            last_signal_ts = str(row["ts"]) if row and row["ts"] else ""
        except Exception:
            last_signal_ts = ""
        last_data_ts = max(last_ingest_ts, last_signal_ts) if (last_ingest_ts or last_signal_ts) else ""
        return {
            "last_snapshot_ts": last_snapshot_ts,
            "last_ingest_ts": last_ingest_ts,
            "last_signal_ts": last_signal_ts,
            "last_data_ts": last_data_ts,
            "_last_ingest_ts_source": last_ingest_ts_source,
            "_last_ingest_row_count_5m": last_ingest_row_count_5m,
            "_last_ingest_ts_value": last_ingest_ts,
            "_last_ingest_table_used": table_used,
            "_last_ingest_column_used": column_used,
        }

    def _debug_enabled(request: Request) -> bool:
        if (os.getenv("PS_DEBUG") or "").strip() == "1":
            return True
        return (request.query_params.get("debug", "") or "").strip() == "1"

    def _count_tokens(r) -> int:
        try:
            with r.conn() as con:
                rows = con.execute("SELECT raw_json FROM markets").fetchall()
        except Exception:
            return 0
        total = 0
        for r0 in rows or []:
            raw_json = r0["raw_json"] or ""
            if not raw_json:
                continue
            try:
                raw = json.loads(raw_json)
            except Exception:
                continue
            tokens = raw.get("tokens") or []
            if isinstance(tokens, list) and tokens:
                total += len(tokens)
                continue
            outcomes = raw.get("outcomes") or []
            clob_ids = raw.get("clobTokenIds") or raw.get("clob_token_ids") or []
            if isinstance(outcomes, list) and isinstance(clob_ids, list) and len(outcomes) == len(clob_ids):
                total += len(outcomes)
                continue
            if raw.get("yesTokenId") or raw.get("noTokenId"):
                total += int(bool(raw.get("yesTokenId"))) + int(bool(raw.get("noTokenId")))
        return total

    def _record_exec(request: Request, rtt_ms: float, ok: bool) -> None:
        stats = getattr(request.app.state, "exec_stats", {"samples": []})
        samples = stats.get("samples", [])
        now = time.time()
        samples.append({"ts": now, "rtt_ms": float(rtt_ms), "ok": bool(ok)})
        # keep short window
        cutoff = now - 120
        samples[:] = [s for s in samples if s.get("ts", 0) >= cutoff]
        if len(samples) > 500:
            del samples[: len(samples) - 500]
        stats["samples"] = samples
        request.app.state.exec_stats = stats

    def _exec_health(request: Request) -> Dict[str, Any]:
        stats = getattr(request.app.state, "exec_stats", {"samples": []})
        samples = stats.get("samples", [])
        now = time.time()
        window = [s for s in samples if now - float(s.get("ts", 0)) <= 60]
        errors = sum(1 for s in window if not s.get("ok", True))
        rtts = sorted([float(s.get("rtt_ms", 0)) for s in window if s.get("ok", True)])
        p50 = None
        p95 = None
        if rtts:
            def _pct(p):
                idx = int((p / 100) * (len(rtts) - 1))
                return rtts[max(0, min(idx, len(rtts) - 1))]
            p50 = _pct(50)
            p95 = _pct(95)
        return {"exec_rtt_ms_p50": p50, "exec_rtt_ms_p95": p95, "errors_1m": errors}

    def _load_orderbook(r, market_id: str) -> Dict[str, Any] | None:
        if hasattr(r, "get_latest_orderbook_snapshot"):
            try:
                return r.get_latest_orderbook_snapshot(market_id)
            except Exception:
                return None
        return None

    def _parse_levels(raw: str | None) -> List[Dict[str, float]]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []
        out = []
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

    BOOK_STALE_SEC = 15.0
    RISK_MAX_SLIP_BPS = 150.0  # sync with UI GUARD_MAX_SLIP_BPS

    def _stale_age_sec(r, state: Optional[Dict[str, Any]] = None) -> Optional[float]:
        state = state or _health_state(r)
        ts = state.get("last_ingest_ts") or state.get("last_snapshot_ts") or state.get("last_data_ts") or ""
        if not ts:
            return None
        try:
            dt = datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            return age
        except Exception:
            return None

    def _is_stale(r, max_age_sec: int = 60) -> bool:
        age = _stale_age_sec(r)
        if age is None:
            return True
        return age > float(max_age_sec)

    @app.get("/about", response_class=HTMLResponse)
    def about(request: Request):
        ctx = {"request": request}
        ctx.update(build_nav_context(request, ""))
        return templates.TemplateResponse("about.html", ctx)

    @app.get("/deprioritize", response_class=HTMLResponse)
    def deprioritize_rules(request: Request):
        r = _repo(request)
        if (os.getenv("ADMIN_TOKEN") or "").strip():
            _require_admin_token(request)
        rules = _safe(lambda: getattr(r, "get_deprioritize_rules")(), [])
        deprioritize_mode = (getattr(request.app.state.settings, "deprioritize_mode", "ui") or "ui")
        return templates.TemplateResponse(
            "deprioritize.html",
            {
                "request": request,
                "rules": rules,
                "deprioritize_mode": deprioritize_mode,
                **build_nav_context(request, "deprioritize"),
            },
        )

    # Dashboard v2 — SPA, все данные грузятся через /api/v2/* (fetch)
    @app.get("/dashboard-v2", response_class=HTMLResponse)
    def dashboard_v2(request: Request):
        r = _repo(request)
        from datetime import datetime

        month_map = {
            "Jan": "янв",
            "Feb": "фев",
            "Mar": "мар",
            "Apr": "апр",
            "May": "май",
            "Jun": "июн",
            "Jul": "июл",
            "Aug": "авг",
            "Sep": "сен",
            "Oct": "окт",
            "Nov": "ноя",
            "Dec": "дек",
        }
        now = datetime.utcnow()
        mon = month_map.get(now.strftime("%b"), now.strftime("%b"))
        updated_ts = f"{now.strftime('%d')} {mon} {now.strftime('%Y')} · {now.strftime('%H:%M:%S')}"
        boot: Dict[str, Any] = {"kpis": {}, "counts": {}, "markets": [], "signals": [], "signals_recent": []}
        runtime_freshness = getattr(r, "_runtime_freshness_state", None)
        runtime_pipe = getattr(r, "_runtime_pipeline_stats", None)
        runtime_reconcile = getattr(r, "_runtime_reconcile_diag", None)
        rf = runtime_freshness if isinstance(runtime_freshness, dict) else {}
        rp = runtime_pipe if isinstance(runtime_pipe, dict) else {}
        rr = runtime_reconcile if isinstance(runtime_reconcile, dict) else {}
        freshness_overall = str(rf.get("overall") or "STOP").strip().upper()
        decision_mode = str(rp.get("decision_mode") or rr.get("decision_mode") or "").strip().upper()
        if not decision_mode:
            decision_mode = "FULL" if freshness_overall == "OK" else ("SAFE" if freshness_overall == "WARN" else "HALTED")
        reconcile_scheduled = int(rr.get("scheduled", 0) or 0)
        reconcile_allowed = int(rr.get("allowed", 0) or 0)
        reconcile_skip_reason = str(rr.get("skip_reason") or "NOT_SCHEDULED").strip().upper()
        reconcile_state = (
            "NOT_SCHEDULED"
            if reconcile_scheduled == 0
            else ("ALLOWED" if reconcile_allowed == 1 else "BLOCKED")
        )
        open_blocked = int(rp.get("open_blocked_by_freshness", rr.get("open_blocked_by_freshness", 0)) or 0)
        system_status = {
            "freshness": f"FRESHNESS_{freshness_overall}",
            "decision_mode": decision_mode,
            "reconcile_state": reconcile_state,
            "reconcile_allowed": reconcile_allowed,
            "reconcile_skip_reason": reconcile_skip_reason,
            "open_blocked_by_freshness": open_blocked,
            "opens_state": "BLOCKED_BY_FRESHNESS" if open_blocked else "ALLOWED",
            "paper_last": str(rp.get("last") or "—"),
            "paper_candidate": int(rp.get("cand_count", 0) or 0),
            "paper_decision": int(rp.get("dec_count", 0) or 0),
            "freshness_reason": str(rp.get("freshness_reason") or "NONE").strip().upper() or "NONE",
        }
        try:
            # KPIs
            markets_count = _safe(lambda: getattr(r, "count_markets")(), 0)
            signals_24h = 0
            try:
                with r.conn() as con:
                    row = con.execute(
                        "SELECT COUNT(*) AS n FROM signals WHERE ts >= datetime('now', '-24 hours')"
                    ).fetchone()
                signals_24h = int(row["n"]) if row else 0
            except Exception:
                signals_24h = 0
            positions_open = 0
            try:
                if hasattr(r, "count_paper_positions_filtered"):
                    positions_open = int(r.count_paper_positions_filtered(status="OPEN"))
                else:
                    with r.conn() as con:
                        row = con.execute(
                            "SELECT COUNT(*) AS n FROM paper_positions WHERE status='OPEN'"
                        ).fetchone()
                    positions_open = int(row["n"]) if row else 0
            except Exception:
                positions_open = 0
            pnl_total = 0.0
            try:
                if hasattr(r, "get_paper_metrics"):
                    pm = r.get_paper_metrics()
                    pnl_total = float(pm.get("pnl_total") or 0.0)
            except Exception:
                pnl_total = 0.0
            cache_hit_rate = 0
            cache_speedup = "1"
            try:
                if hasattr(r, "get_cache_summary"):
                    summary = r.get_cache_summary() or {}
                    cache_hit_rate = int(float(summary.get("overall_hit_rate", 0.0)) * 100)
            except Exception:
                cache_hit_rate = 0

            boot["kpis"] = {
                "markets": markets_count,
                "signals_24h": signals_24h,
                "positions": positions_open,
                "pnl": pnl_total,
                "pnl_display": f"${pnl_total:.2f}",
                "cache_hit_rate": cache_hit_rate,
                "cache_speedup": cache_speedup,
            }
            boot["decision_quality"] = _safe(lambda: getattr(r, "get_quality_metrics")(), {})
            boot["quality_by_action"] = _safe(lambda: getattr(r, "get_quality_breakdown")("action"), [])
            boot["quality_by_agent"] = _safe(lambda: getattr(r, "get_quality_breakdown")("agent"), [])
            boot["top_winners"] = _safe(lambda: getattr(r, "get_top_decisions")(10, "winners"), [])
            boot["top_losers"] = _safe(lambda: getattr(r, "get_top_decisions")(10, "losers"), [])
            boot["market_best"] = _safe(lambda: getattr(r, "get_market_quality")(15, "best"), [])
            boot["market_worst"] = _safe(lambda: getattr(r, "get_market_quality")(15, "worst"), [])
            boot["market_worst_winrate"] = _safe(lambda: getattr(r, "get_market_worst_by_win_rate")(15, 5), [])
            boot["quality_coverage"] = _safe(lambda: getattr(r, "get_quality_coverage")(), {})

            # Markets table (first page)
            with r.conn() as con:
                mrows = con.execute(
                    """
                    SELECT market_id, title, group_key
                    FROM markets
                    ORDER BY rowid DESC
                    LIMIT 50
                    """
                ).fetchall()
            boot["markets"] = [
                {"market_id": mr["market_id"], "title": mr["title"], "group_key": mr["group_key"]}
                for mr in mrows or []
            ]
            boot["counts"]["markets"] = len(boot["markets"]) if boot["markets"] else markets_count

            # Signals table (first page)
            try:
                srows = _as_tuples(
                    r.list_recent_signals_filtered(
                        limit=50,
                        offset=0,
                        agent=None,
                        kind=None,
                        market_id=None,
                        q=None,
                        sort_by="ts",
                        sort_dir="desc",
                    )
                )
            except Exception:
                srows = []
            boot["signals"] = [
                {"ts": s[0], "agent_id": s[1], "kind": s[2], "market_id": s[3], "explain": s[4]}
                for s in srows or []
            ]
            boot["counts"]["signals"] = len(boot["signals"]) if boot["signals"] else signals_24h

            # Overview recent signals
            boot["signals_recent"] = boot["signals"][:6]
        except Exception as e:
            logger.exception("Failed to prepare dashboard_v2 boot data", exc_info=e)

        return templates.TemplateResponse(
            "dashboard_v2.html",
            {
                "request": request,
                "boot": boot,
                "updated_ts": updated_ts,
                "system_status": system_status,
                **build_nav_context(
                    request,
                    "overview",
                    markets_total=boot.get("kpis", {}).get("markets"),
                    signals_total=boot.get("kpis", {}).get("signals_24h"),
                    positions_total=boot.get("kpis", {}).get("positions"),
                ),
            },
            headers={"Cache-Control": "no-store"},
        )

    # ---------- Pages ----------
    @app.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/dashboard-v2", status_code=302)

    @app.get("/overview", include_in_schema=False)
    def overview_redirect():
        return RedirectResponse(url="/dashboard-v2", status_code=302)

    @app.get("/overview-legacy", response_class=HTMLResponse)
    def overview(request: Request):
        r = _repo(request)

        ctx: Dict[str, Any] = {
            "request": request,
            "settings": request.app.state.settings,
            "paused": _safe(lambda: getattr(r, "is_paused")(), False) if hasattr(r, "is_paused") else False,
            "paused_updated_at": _safe(lambda: getattr(r, "get_setting_updated_at")("paused"), ""),
            "markets_count": _safe(lambda: getattr(r, "count_markets")(), 0),
            "snapshots_count": _safe(lambda: getattr(r, "count_snapshots")(), 0),
            "signals_count": _safe(lambda: getattr(r, "count_signals")(), 0),
            "cases_count": _safe(lambda: getattr(r, "count_cases")(), 0),
            "decisions_v0_count": _safe(lambda: getattr(r, "count_decisions_v0")(), 0),
            "paper_positions_count": _safe(lambda: getattr(r, "count_paper_positions")(), 0),
            "paper_metrics": _safe(lambda: getattr(r, "get_paper_metrics")(), {}),
            "paper_pnl_timeseries": _safe(lambda: getattr(r, "get_paper_pnl_timeseries")(limit=120), []),
            "tradeability_metrics": _safe(lambda: getattr(r, "get_tradeability_metrics")(hours=24), {}),
            "ru_status": ru_status,
            "ru_kind": ru_kind,
            "ru_action": ru_action,
            "fnum": fnum,
        }

        todo = []
        if hasattr(r, "list_cases"):
            try:
                all_cases = r.list_cases(minutes_signals=60, minutes_snaps=30)
                todo = [c for c in (all_cases or []) if isinstance(c, dict) and c.get("last_ts")]
                pr = {"OPPORTUNITY": 0, "INVESTIGATE": 1, "BLOCKED": 2, "OK": 9}
                todo.sort(key=lambda c: pr.get((c.get("status") or "").upper(), 9))
                todo = todo[:8]
            except Exception:
                todo = []
        ctx["todo"] = todo

        ctx.update(
            build_nav_context(
                request,
                "overview",
                markets_total=ctx.get("markets_count"),
                signals_total=ctx.get("signals_count"),
                cases_total=ctx.get("cases_count"),
                decisions_total=ctx.get("decisions_v0_count"),
                positions_total=ctx.get("paper_positions_count"),
            )
        )

        return templates.TemplateResponse("overview.html", ctx)

    @app.get("/markets", response_class=HTMLResponse)
    def markets(request: Request):
        r = _repo(request)
        rows = []
        error = ""
        try:
            ms = r.list_markets(limit=200)
            for m in ms:
                rows.append((m.market_id, getattr(m, "slug", ""), getattr(m, "title", ""), getattr(m, "group_key", "")))
        except Exception as e:
            logger.exception("Failed to load markets list", exc_info=e)
            error = "Ошибка запроса рынков (см. лог)."
            rows = []
        if not rows:
            # Fallback direct SQL to surface data even if repo path/method misbehaves.
            try:
                with r.conn() as con:
                    direct = con.execute(
                        """
                        SELECT market_id, slug, title, group_key
                        FROM markets
                        ORDER BY rowid DESC
                        LIMIT 200
                        """
                    ).fetchall()
                if direct:
                    rows = [(d["market_id"], d["slug"], d["title"], d["group_key"]) for d in direct]
                    if error:
                        error = f"{error} Показаны данные прямым запросом."
                else:
                    with r.conn() as con:
                        cnt = con.execute("SELECT COUNT(*) AS n FROM markets").fetchone()
                    n = int(cnt["n"]) if cnt else 0
                    if n > 0 and not error:
                        error = "В БД есть данные, но запрос вернул 0 строк (см. лог)."
                        logger.error("Markets empty on page but DB count=%s", n)
            except Exception as e:
                logger.exception("Markets fallback query failed", exc_info=e)
                if not error:
                    error = "Ошибка запроса рынков (см. лог)."
        return templates.TemplateResponse(
            "markets.html",
            {
                "request": request,
                "rows": rows,
                "error": error,
                **build_nav_context(request, "markets"),
            },
        )

    @app.get("/opportunities", response_class=HTMLResponse)
    @app.get("/cases", response_class=HTMLResponse)
    @app.head("/cases", response_class=HTMLResponse)
    def cases(request: Request):
        r = _repo(request)
        deprioritize_active = 0
        try:
            with r.conn() as con:
                row = con.execute(
                    """
                    SELECT COUNT(1) AS n
                    FROM deprioritize_rules
                    WHERE is_enabled=1
                      AND (expires_ts IS NULL OR expires_ts='' OR expires_ts > datetime('now'))
                    """
                ).fetchone()
            deprioritize_active = int(row["n"]) if row else 0
        except Exception:
            deprioritize_active = 0
        page = _int_arg(request, "page", 1, 1, 10000)
        size = _int_arg(request, "size", 50, 10, 200)
        status_q = (request.query_params.get("status", "") or "").strip().upper()
        q = (request.query_params.get("q", "") or "").strip().lower()
        sort = (request.query_params.get("sort", "activity") or "activity").strip().lower()
        direction = (request.query_params.get("dir", "desc") or "desc").strip().lower()
        if direction not in {"asc", "desc"}:
            direction = "desc"
        rows: List[Dict[str, Any]] = []
        try:
            rows = r.list_cases(minutes_signals=30, minutes_snaps=10)
            if rows and not isinstance(rows[0], dict):
                rows = [dict(x) for x in rows]  # type: ignore[arg-type]
        except Exception:
            rows = []
        if status_q:
            rows = [x for x in rows if str(x.get("status", "")).upper() == status_q]
        if q:
            rows = [
                x for x in rows
                if q in str(x.get("title", "")).lower()
                or q in str(x.get("market_id", "")).lower()
                or q in str(x.get("reason", "")).lower()
            ]
        if rows:
            for c in rows:
                mid = c.get("market_id")
                if not mid:
                    c["deprioritize_weight"] = 1.0
                    c["deprioritize_reason"] = ""
                    c["deprioritize_rules_count"] = 0
                    c["prio"] = 1.0
                    c["prio_reason"] = ""
                    c["prio_matched"] = 0
                    continue
                try:
                    action = c.get("action") or None
                    w = r.get_deprioritize_weight(mid, action)
                    weight = float(w.get("weight", 1.0))
                    reason = w.get("reason", "")
                    matched = int(w.get("matched_rules_count", 0))
                    c["deprioritize_weight"] = weight
                    c["deprioritize_reason"] = reason
                    c["deprioritize_rules_count"] = matched
                    c["prio"] = weight
                    c["prio_reason"] = reason
                    c["prio_matched"] = matched
                except Exception:
                    c["deprioritize_weight"] = 1.0
                    c["deprioritize_reason"] = ""
                    c["deprioritize_rules_count"] = 0
                    c["prio"] = 1.0
                    c["prio_reason"] = ""
                    c["prio_matched"] = 0

        def _weight(c: Dict[str, Any]) -> float:
            try:
                return float(c.get("prio", 1.0) or 1.0)
            except Exception:
                return 1.0

        def _get_score(c: Dict[str, Any]) -> float | None:
            for key in ("score", "rank_score", "priority"):
                if key not in c:
                    continue
                try:
                    v = c.get(key)
                    if v is None:
                        continue
                    return float(v)
                except Exception:
                    continue
            return None

        def _apply_prio_sort() -> None:
            has_score = any(_get_score(c) is not None for c in rows)
            if has_score:
                def _score_weight(c: Dict[str, Any]) -> tuple[float, int]:
                    score = _get_score(c)
                    if score is None:
                        return (float("-inf"), int(c.get("_base_order", 0)))
                    return (score * _weight(c), int(c.get("_base_order", 0)))
                rows.sort(key=_score_weight, reverse=True)
            else:
                # Stable sort by prio desc, preserve current order within same weight.
                rows.sort(key=_weight, reverse=True)

        if sort == "status":
            pr = {"OPPORTUNITY": 0, "INVESTIGATE": 1, "BLOCKED": 2, "OK": 9}
            rows.sort(
                key=lambda c: (pr.get((c.get("status") or "").upper(), 9), c.get("last_signal_ts") or ""),
                reverse=(direction == "desc"),
            )
        elif sort == "market":
            rows.sort(key=lambda c: str(c.get("market_id") or "").lower(), reverse=(direction == "desc"))
        elif sort == "spread":
            rows.sort(key=lambda c: float(c.get("spread") or 0.0), reverse=(direction == "desc"))
        elif sort == "liq":
            rows.sort(key=lambda c: float(c.get("liq") or 0.0), reverse=(direction == "desc"))
        elif sort == "sum_mid":
            rows.sort(key=lambda c: float(c.get("sum_mid") or 0.0), reverse=(direction == "desc"))
        else:
            rows.sort(
                key=lambda c: c.get("last_signal_ts") or c.get("last_snapshot_ts") or "",
                reverse=(direction == "desc"),
            )
        for idx, c in enumerate(rows):
            c["_base_order"] = idx
        _apply_prio_sort()
        if os.getenv("PS_DEMO") != "1":
            rows = [
                x for x in rows
                if str(x.get("group_key") or "").lower() != "demo_cluster"
                and "demo market" not in str(x.get("title") or "").lower()
            ]
        total = len(rows)
        start = (page - 1) * size
        rows = rows[start:start + size]
        kill_switch_reason = ""
        try:
            kill_switch_reason = str(getattr(r, "get_setting")("kill_switch_reason", "") or "")
        except Exception:
            kill_switch_reason = ""
        for c in rows:
            mid = str(c.get("market_id") or "").strip()
            latest_decision = None
            if mid and hasattr(r, "get_latest_decision_v0_row"):
                try:
                    latest_decision = r.get_latest_decision_v0_row(mid)
                except Exception:
                    latest_decision = None
            decision_why = build_case_decision_why(
                latest_decision if isinstance(latest_decision, dict) else None,
                None,
                kill_switch_reason=kill_switch_reason,
            )
            reason_summary = build_case_reason_summary(decision_why, fallback_reason=str(c.get("reason") or ""))
            c["decision_why"] = decision_why
            c["reason_primary"] = str(reason_summary.get("primary") or "NORMAL")
            c["reason_secondary"] = str(reason_summary.get("secondary") or "—")
            c["reason_kind"] = str(reason_summary.get("kind") or "muted")
            c["reason_secondary_kind"] = str(reason_summary.get("secondary_kind") or "muted")
        pager = _build_pager(request, total=total, page=page, size=size)
        return templates.TemplateResponse(
            "cases.html",
            {
                "request": request,
                "rows": rows,
                "ru_status": ru_status,
                "ru_action": ru_action,
                "fnum": fnum,
                "deprioritize_active": deprioritize_active,
                "pager": pager,
                "filters": {"status": status_q, "q": q, "sort": sort, "dir": direction},
                **build_nav_context(request, "cases", cases_total=total),
            },
        )

    @app.get("/cases/live")
    def cases_live(request: Request, limit: int = 30):
        r = _repo(request)
        limit = max(1, min(int(limit or 30), 100))
        ids_raw = (request.query_params.get("ids") or "").strip()
        ids = [x for x in (ids_raw.split(",") if ids_raw else []) if x.strip()]
        rows = []
        try:
            rows = r.list_cases(minutes_signals=30, minutes_snaps=10)
            if rows and not isinstance(rows[0], dict):
                rows = [dict(x) for x in rows]
        except Exception:
            rows = []
        if os.getenv("PS_DEMO") != "1":
            rows = [
                x for x in rows
                if str(x.get("group_key") or x.get("cluster_id") or "").lower() != "demo_cluster"
            ]
        if os.getenv("PS_DEMO") != "1":
            rows = [
                x for x in rows
                if str(x.get("group_key") or "").lower() != "demo_cluster"
                and "demo market" not in str(x.get("title") or "").lower()
            ]

        by_id = {str(c.get("market_id")): c for c in (rows or []) if c.get("market_id")}
        items = []
        pick_ids = ids if ids else list(by_id.keys())[:limit]
        for mid in pick_ids[:limit]:
            c = by_id.get(mid)
            if not c:
                continue
            spread = c.get("spread")
            try:
                spread_pct = float(spread) * 100.0 if spread is not None else None
            except Exception:
                spread_pct = None
            items.append(
                {
                    "case_id": mid,
                    "title": c.get("title") or c.get("question") or c.get("slug") or mid,
                    "sum_mid": c.get("sum_mid"),
                    "spread_pct": spread_pct,
                    "liq_usd": c.get("liq"),
                    "status": c.get("status"),
                    "prio": c.get("prio", 1.0),
                    "updated_ts": c.get("last_signal_ts") or c.get("last_snapshot_ts") or "",
                }
            )

        return {
            "as_of": _health_state(r).get("last_data_ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": items,
        }

    def _extract_prob(latest: dict) -> float | None:
        yes = latest.get("YES", {}) if isinstance(latest, dict) else {}
        val = yes.get("mid") if isinstance(yes, dict) else None
        if val is None and isinstance(yes, dict):
            val = yes.get("implied_prob")
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    def _is_mutex_pair(title_a: str, title_b: str) -> bool:
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

    def _is_implication_pair(title_a: str, title_b: str) -> tuple[bool, int]:
        a = title_a.lower()
        b = title_b.lower()
        if "wins" in a and "candidate" in b:
            return True, 0
        if "candidate" in a and "wins" in b:
            return True, 1
        return False, 0

    @app.get("/cases/explain")
    def cases_explain(request: Request, case_id: str):
        r = _repo(request)
        case_id = (case_id or "").strip()
        if not case_id:
            raise HTTPException(status_code=400, detail="case_id required")

        group_key = None
        markets = []
        try:
            with r.conn() as con:
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
            markets = r.list_markets_by_group(group_key, limit=50)
        except Exception:
            markets = []

        if not markets:
            return {"case_id": case_id, "type": "NONE", "edge_pct": None, "detail": {}}

        market_ids = [m.market_id for m in markets]
        try:
            latest_map = r.get_latest_snapshots_batch(market_ids)
        except Exception:
            latest_map = {}

        probs: dict[str, float] = {}
        titles: dict[str, str] = {}
        for m in markets:
            titles[m.market_id] = m.title or m.market_id
            p = _extract_prob(latest_map.get(m.market_id, {}))
            if p is not None:
                probs[m.market_id] = p
                _record_price(m.market_id, p)

        lag_pairs = 0
        lag_emitted = 0
        best_lag = None
        best_window = None
        if len(market_ids) >= 2 and case_id in market_ids:
            pa_now = probs.get(case_id)
            pa_ago_300 = _get_price_ago(case_id, 300)
            pa_ago_180 = _get_price_ago(case_id, 180)
            for other in market_ids:
                if other == case_id:
                    continue
                lag_pairs += 1
                pb_now = probs.get(other)
                pb_ago_300 = _get_price_ago(other, 300)
                pb_ago_180 = _get_price_ago(other, 180)
                if pa_now is None or pb_now is None:
                    continue
                use_300 = pa_ago_300 is not None and pb_ago_300 is not None
                use_180 = pa_ago_180 is not None and pb_ago_180 is not None
                if not use_300 and not use_180:
                    continue
                window_s = 300 if use_300 else 180
                pa_ago = pa_ago_300 if use_300 else pa_ago_180
                pb_ago = pb_ago_300 if use_300 else pb_ago_180
                if pa_ago is None or pb_ago is None:
                    continue
                dA = float(pa_now) - float(pa_ago)
                dB = float(pb_now) - float(pb_ago)
                divergence = abs(dA - dB)
                leader_move = max(abs(dA), abs(dB))
                if leader_move < 0.01 or divergence < 0.015:
                    continue
                if not _micro_guard_ok(r, case_id) or not _micro_guard_ok(r, other):
                    continue
                leader = case_id if abs(dA) >= abs(dB) else other
                lagger = other if leader == case_id else case_id
                score = divergence
                if best_lag is None or score > best_lag["score"]:
                    best_lag = {
                        "score": score,
                        "leader": leader,
                        "lagger": lagger,
                        "d_leader": dA if leader == case_id else dB,
                        "d_lagger": dB if leader == case_id else dA,
                        "divergence": divergence,
                    }
                    best_window = window_s

        if best_lag:
            lag_emitted = 1

        now_ts = time.time()
        global _last_lag_log_ts
        if now_ts - _last_lag_log_ts > 30:
            _last_lag_log_ts = now_ts
            logger.info("lag_v2: checked_pairs=%s emitted=%s window=%s", lag_pairs, lag_emitted, best_window or "—")
            if os.getenv("PS_DEBUG") == "1" and best_lag:
                logger.debug(
                    "lag_v2 sample: case=%s leader=%s lagger=%s div=%.3f",
                    case_id,
                    best_lag["leader"],
                    best_lag["lagger"],
                    best_lag["divergence"],
                )

        if best_lag:
            return {
                "case_id": case_id,
                "type": "LAG",
                "edge_pct": float(best_lag["divergence"]) * 100.0,
                "detail": {
                    "lag_leader_id": best_lag["leader"],
                    "lagger_id": best_lag["lagger"],
                    "window_s": best_window,
                    "d_leader": best_lag["d_leader"],
                    "d_lagger": best_lag["d_lagger"],
                    "divergence": best_lag["divergence"],
                },
            }

        if len(market_ids) == 2:
            a, b = market_ids[0], market_ids[1]
            pa = probs.get(a)
            pb = probs.get(b)
            if pa is not None and pb is not None:
                if _is_mutex_pair(titles.get(a, ""), titles.get(b, "")):
                    gap = pa + pb - 1.0
                    if gap > 0.02:
                        return {
                            "case_id": case_id,
                            "type": "MX",
                            "edge_pct": gap * 100.0,
                            "detail": {"pa": pa, "pb": pb, "gap": gap},
                        }
                is_impl, flip = _is_implication_pair(titles.get(a, ""), titles.get(b, ""))
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


    @app.get("/case/{market_id}", include_in_schema=False)
    def case_redirect(market_id: str):
        return RedirectResponse(url=f"/cases/{market_id}", status_code=302)

    @app.get("/cases/{market_id}", response_class=HTMLResponse)
    def case_details(request: Request, market_id: str):
        r = _repo(request)
        d: Dict[str, Any] = {"market_id": market_id}
        runtime_pipe = getattr(r, "_runtime_pipeline_stats", None)
        kill_switch_reason = ""
        try:
            kill_switch_reason = str(getattr(r, "get_setting")("kill_switch_reason", "") or "")
        except Exception:
            kill_switch_reason = ""
        try:
            d = r.get_case_details(market_id)
        except Exception:
            warn_exc(logger, "case_details: get_case_details failed", market_id=market_id)
        try:
            ld = r.get_latest_decision_v0_row(market_id)
            if ld:
                d["latest_decision"] = ld
                if isinstance(ld.get("reason_json"), dict):
                    d["reason_json"] = ld.get("reason_json")
                decision_id = ld.get("decision_id")
                if decision_id:
                    try:
                        d["decision_outcome"] = r.get_decision_outcome(decision_id)
                    except Exception:
                        warn_exc(logger, "case_details: decision_outcome failed", market_id=market_id)
                        d["decision_outcome"] = None
        except Exception:
            warn_exc(logger, "case_details: latest decision load failed", market_id=market_id)
        try:
            d["narrative"] = r.get_case_narrative(market_id, minutes=240)
        except Exception:
            warn_exc(logger, "case_details: narrative load failed", market_id=market_id)
            d["narrative"] = {}
        # neighbors (cluster) for UI: show structure, not a single market
        try:
            m = d.get("market") if isinstance(d, dict) else None
            gk = getattr(m, "group_key", None) if m else None
            if gk:
                cd = r.get_cluster_details_v2(
                    gk,
                    limit_markets=500,
                    selected_market_id=market_id,
                    neighbor_sort="closest",
                )
                d["neighbors"] = (cd.get("neighbors") or [])[:12]
        except Exception:
            warn_exc(logger, "case_details: neighbors load failed", market_id=market_id)
        try:
            d["decision_why"] = build_case_decision_why(
                d.get("latest_decision") if isinstance(d, dict) else None,
                runtime_pipe if isinstance(runtime_pipe, dict) else None,
                kill_switch_reason=kill_switch_reason,
            )
        except Exception:
            warn_exc(logger, "case_details: decision_why build failed", market_id=market_id)
            d["decision_why"] = {
                "decision_status": "—",
                "decision_reason": "—",
                "risk_kind": "NONE",
                "kill_kind": "NONE",
                "freshness_gate": "NONE",
                "freshness_reason": "NONE",
                "decision_mode": "FULL",
                "open_blocked_by_freshness": 0,
            }

        return templates.TemplateResponse(
            "case_details.html",
            {
                "request": request,
                "d": d,
                "ru_kind": ru_kind,
                "ru_status": ru_status,
                "ru_action": ru_action,
                "fnum": fnum,
                **build_nav_context(request, "cases"),
            },
        )


    @app.get("/cluster/{group_key}", response_class=HTMLResponse)
    def cluster_page(request: Request, group_key: str, m: str | None = None, sort: str = "closest"):
        r = _repo(request)
        mode = (sort or "closest").strip().lower()
        if mode not in {"closest", "conflict"}:
            mode = "closest"
        d = r.get_cluster_details_v2(
            group_key,
            limit_markets=500,
            selected_market_id=m,
            neighbor_sort=mode,
        )
        return templates.TemplateResponse(
            "cluster.html",
            {
                "request": request,
                "d": d,
                "fnum": fnum,
                "selected_market_id": m,
                "neighbor_sort": mode,
                **build_nav_context(request, "markets"),
            },
        )

    @app.get("/decisions", response_class=HTMLResponse)
    def decisions(request: Request):
        r = _repo(request)
        page = _int_arg(request, "page", 1, 1, 10000)
        size = _int_arg(request, "size", 50, 10, 200)
        action = (request.query_params.get("action", "") or "").strip().upper() or None
        status = (request.query_params.get("status", "") or "").strip().upper() or None
        market_id = (request.query_params.get("market_id", "") or "").strip() or None
        q = (request.query_params.get("q", "") or "").strip() or None
        sort = (request.query_params.get("sort", "ts") or "ts").strip().lower()
        direction = (request.query_params.get("dir", "desc") or "desc").strip().lower()
        if direction not in {"asc", "desc"}:
            direction = "desc"
        rows: List[Tuple] = []
        try:
            offset = (page - 1) * size
            if hasattr(r, "list_recent_decisions_v0_filtered"):
                rows = _as_tuples(
                    r.list_recent_decisions_v0_filtered(
                        limit=size,
                        offset=offset,
                        action=action,
                        status=status,
                        market_id=market_id,
                        q=q,
                        sort_by=sort,
                        sort_dir=direction,
                    )
                )
                total = int(r.count_decisions_v0_filtered(action=action, status=status, market_id=market_id, q=q))
            else:
                rows = _as_tuples(r.list_recent_decisions_v0(limit=200))
                total = len(rows)
        except Exception:
            rows = []
            total = 0
        pager = _build_pager(request, total=total, page=page, size=size)
        return templates.TemplateResponse(
            "decisions.html",
            {
                "request": request,
                "rows": rows,
                "ru_action": ru_action,
                "pager": pager,
                "filters": {
                    "action": action or "",
                    "status": status or "",
                    "market_id": market_id or "",
                    "q": q or "",
                    "sort": sort,
                    "dir": direction,
                },
                **build_nav_context(request, "decisions", decisions_total=total),
            },
        )

    @app.get("/signals", response_class=HTMLResponse)
    def signals(request: Request):
        r = _repo(request)
        page = _int_arg(request, "page", 1, 1, 10000)
        size = _int_arg(request, "size", 50, 10, 200)
        agent = (request.query_params.get("agent", "") or "").strip() or None
        kind = (request.query_params.get("kind", "") or "").strip().upper() or None
        market_id = (request.query_params.get("market_id", "") or "").strip() or None
        q = (request.query_params.get("q", "") or "").strip() or None
        sort = (request.query_params.get("sort", "ts") or "ts").strip().lower()
        direction = (request.query_params.get("dir", "desc") or "desc").strip().lower()
        if direction not in {"asc", "desc"}:
            direction = "desc"
        rows: List[Tuple] = []
        error = ""
        try:
            offset = (page - 1) * size
            if hasattr(r, "list_recent_signals_filtered"):
                rows = _as_tuples(
                    r.list_recent_signals_filtered(
                        limit=size,
                        offset=offset,
                        agent=agent,
                        kind=kind,
                        market_id=market_id,
                        q=q,
                        sort_by=sort,
                        sort_dir=direction,
                    )
                )
                total = int(r.count_signals_filtered(agent=agent, kind=kind, market_id=market_id, q=q))
            else:
                rows = _as_tuples(r.list_recent_signals(limit=200))
                total = len(rows)
        except Exception as e:
            logger.exception("Failed to load signals list", exc_info=e)
            error = "Ошибка запроса сигналов (см. лог)."
            rows = []
            total = 0
        if rows and os.getenv("PS_DEMO") != "1":
            rows = [r0 for r0 in rows if (not r0[3]) or str(r0[3]).isdigit()]
        if not rows:
            # Fallback direct SQL in case repo layer fails silently.
            try:
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
                    where.append(
                        "(LOWER(COALESCE(explain_short, '')) LIKE ? OR LOWER(COALESCE(scope_market_id, '')) LIKE ?)"
                    )
                    like = f"%{q.lower()}%"
                    params.extend([like, like])
                where_sql = f"WHERE {' AND '.join(where)}" if where else ""
                order_map = {"ts": "ts", "agent": "agent_id", "kind": "kind", "market": "scope_market_id"}
                order_col = order_map.get((sort or "ts").lower(), "ts")
                order_dir = "ASC" if direction == "asc" else "DESC"
                with r.conn() as con:
                    direct = con.execute(
                        f"""
                        SELECT ts, agent_id, kind, scope_market_id, explain_short
                        FROM signals
                        {where_sql}
                        ORDER BY {order_col} {order_dir}, ts DESC
                        LIMIT ? OFFSET ?
                        """,
                        (*params, int(size), int((page - 1) * size)),
                    ).fetchall()
                    cnt = con.execute(
                        f"SELECT COUNT(*) AS n FROM signals {where_sql}",
                        tuple(params),
                    ).fetchone()
                total = int(cnt["n"]) if cnt else total
                if direct:
                    rows = [(d["ts"], d["agent_id"], d["kind"], d["scope_market_id"], d["explain_short"]) for d in direct]
                    if error:
                        error = f"{error} Показаны данные прямым запросом."
                else:
                    if total > 0 and not error:
                        error = "В БД есть данные, но запрос вернул 0 строк (см. лог)."
                        logger.error("Signals empty on page but DB count=%s", total)
            except Exception as e:
                logger.exception("Signals fallback query failed", exc_info=e)
                if not error:
                    error = "Ошибка запроса сигналов (см. лог)."
        pager = _build_pager(request, total=total, page=page, size=size)
        return templates.TemplateResponse(
            "signals.html",
            {
                "request": request,
                "rows": rows,
                "ru_kind": ru_kind,
                "pager": pager,
                "error": error,
                "filters": {
                    "agent": agent or "",
                    "kind": kind or "",
                    "market_id": market_id or "",
                    "q": q or "",
                    "sort": sort,
                    "dir": direction,
                },
                **build_nav_context(request, "signals", signals_total=total),
            },
        )

    # ---------- Paper controls (UI) ----------
    @app.post("/cases/{market_id}/paper/buy", dependencies=[Depends(_require_admin_token)])
    def case_paper_buy(request: Request, market_id: str):
        wants_json = (request.headers.get("accept") or "").lower().find("application/json") >= 0
        r = _repo(request)
        try:
            if hasattr(r, "is_paused") and r.is_paused():
                if wants_json:
                    raise HTTPException(status_code=423, detail="Execution paused")
                msg = quote_plus("Исполнение на паузе")
                return RedirectResponse(url=f"/cases/{market_id}?flash={msg}", status_code=303)
        except HTTPException:
            raise
        except Exception:
            pass

        result = _case_paper_buy_impl(request, market_id)
        if wants_json:
            return {"status": result}
        return RedirectResponse(url=f"/cases/{market_id}", status_code=303)

    def _case_paper_buy_impl(request: Request, market_id: str):
        r = _repo(request)
        gate = _get_gate(request)

        # Gate before manual paper action
        if gate is not None:
            try:
                verdict = gate.check_market(market_id)
                if verdict is not None and not getattr(verdict, "allow", True):
                    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    r.insert_decision_v0(
                        decision_id=str(uuid.uuid4()),
                        ts=ts,
                        run_id="ui",
                        market_id=market_id,
                        action="HOLD",
                        status=getattr(verdict, "status", "BLOCKED") or "BLOCKED",
                        reason=f"{getattr(verdict, 'code', 'GATE')}: {getattr(verdict, 'reason', '')}".strip(),
                        payload_json=json.dumps({"via": "ui"}, ensure_ascii=False),
                    )
                    _reconcile_now(r)
                return "blocked"
            except Exception:
                # gate не должен ронять UI
                pass

        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        r.insert_decision_v0(
            decision_id=str(uuid.uuid4()),
            ts=ts,
            run_id="ui",
            market_id=market_id,
            action="PAPER_BUY_BOTH",
            status="OK",
            reason="Ручной запуск: бумажная сделка",
            payload_json=json.dumps({"via": "ui"}, ensure_ascii=False),
        )
        _reconcile_now(r)
        return "ok"

    @app.post("/cases/{market_id}/paper/close", dependencies=[Depends(_require_admin_token)])
    def case_paper_close(request: Request, market_id: str):
        wants_json = (request.headers.get("accept") or "").lower().find("application/json") >= 0
        r = _repo(request)
        try:
            if hasattr(r, "is_paused") and r.is_paused():
                if wants_json:
                    raise HTTPException(status_code=423, detail="Execution paused")
                msg = quote_plus("Исполнение на паузе")
                return RedirectResponse(url=f"/cases/{market_id}?flash={msg}", status_code=303)
        except HTTPException:
            raise
        except Exception:
            pass

        result = _case_paper_close_impl(request, market_id)
        if wants_json:
            return {"status": result}
        return RedirectResponse(url=f"/cases/{market_id}", status_code=303)

    def _case_paper_close_impl(request: Request, market_id: str):
        r = _repo(request)
        gate = _get_gate(request)

        if gate is not None:
            try:
                verdict = gate.check_market(market_id)
                if verdict is not None and not getattr(verdict, "allow", True):
                    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    r.insert_decision_v0(
                        decision_id=str(uuid.uuid4()),
                        ts=ts,
                        run_id="ui",
                        market_id=market_id,
                        action="HOLD",
                        status=getattr(verdict, "status", "BLOCKED") or "BLOCKED",
                        reason=f"{getattr(verdict, 'code', 'GATE')}: {getattr(verdict, 'reason', '')}".strip(),
                        payload_json=json.dumps({"via": "ui"}, ensure_ascii=False),
                    )
                    _reconcile_now(r)
                return "blocked"
            except Exception:
                warn_exc(logger, "case_paper_close: gate check failed", market_id=market_id)

        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        r.insert_decision_v0(
            decision_id=str(uuid.uuid4()),
            ts=ts,
            run_id="ui",
            market_id=market_id,
            action="PAPER_CLOSE_BOTH",
            status="OK",
            reason="Ручное закрытие: бумажная сделка",
            payload_json=json.dumps({"via": "ui"}, ensure_ascii=False),
        )
        _reconcile_now(r)
        return "ok"

    @app.post("/paper/action", dependencies=[Depends(_require_admin_token)])
    async def paper_action(request: Request):
        start_ts = time.perf_counter()
        r = _repo(request)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        case_id = (payload.get("case_id") or payload.get("market_id") or "").strip()
        action = (payload.get("action") or "").strip().lower()
        mode = (payload.get("mode") or "paper").strip().lower()
        manual_code = (payload.get("manual_code") or "").strip().lower()
        if mode != "paper":
            raise HTTPException(status_code=400, detail="Only paper mode is supported")
        if not case_id or action not in {"buy", "close"}:
            raise HTTPException(status_code=400, detail="Invalid action")
        if hasattr(r, "is_paused") and r.is_paused():
            try:
                get_auto_paper_agent()._log_event(
                    "BLOCKED_PAUSED",
                    case_id=case_id,
                    market_id=case_id,
                    detail={"src": "MANUAL", "reason": "PAUSED"},
                )
            except Exception:
                pass
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, False)
            return JSONResponse(status_code=423, content={"ok": False, "error": "PAUSED"})
        if _is_stale(r, max_age_sec=60):
            try:
                get_auto_paper_agent()._log_event(
                    "BLOCKED_STALE",
                    case_id=case_id,
                    market_id=case_id,
                    detail={"src": "MANUAL", "reason": "STALE"},
                )
            except Exception:
                pass
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, False)
            return JSONResponse(status_code=409, content={"ok": False, "error": "STALE"})

        if action == "buy":
            result = _case_paper_buy_impl(request, case_id)
        else:
            result = _case_paper_close_impl(request, case_id)

        has_open = False
        try:
            has_open = bool(getattr(r, "paper_has_open_position")(case_id))
        except Exception:
            has_open = False

        pos_info = None
        try:
            with r.conn() as con:
                row = con.execute(
                    """
                    SELECT qty, avg_price, outcome, status
                    FROM paper_positions
                    WHERE market_id = ?
                    ORDER BY opened_at DESC
                    LIMIT 1
                    """,
                    (case_id,),
                ).fetchone()
            if row:
                pos_info = {
                    "shares": float(row["qty"] or 0.0),
                    "avg_price": float(row["avg_price"] or 0.0),
                    "side": str(row["outcome"] or ""),
                    "status": str(row["status"] or ""),
                }
        except Exception:
            pos_info = None

        updated_badges = {
            "positions": _safe(lambda: getattr(r, "count_paper_positions_filtered")(status="OPEN"), 0)
            if hasattr(r, "count_paper_positions_filtered")
            else _safe(lambda: getattr(r, "count_paper_positions")(), 0),
            "cases": _safe(lambda: getattr(r, "count_cases")(), 0),
        }

        ok = True if result == "ok" else False
        try:
            agent = get_auto_paper_agent()
            size = payload.get("size")
            price = pos_info.get("avg_price") if isinstance(pos_info, dict) else None
            if ok:
                code_map = {"buy": "PAPER_BUY", "sell": "PAPER_SELL", "close": "PAPER_CLOSE"}
                if manual_code in code_map:
                    agent._log_event(
                        code_map[manual_code],
                        case_id=case_id,
                        market_id=case_id,
                        detail={"src": "MANUAL", "size": size, "price": price},
                    )
                else:
                    agent._log_event(
                        "BLOCKED_NO_MANUAL_CODE",
                        case_id=case_id,
                        market_id=case_id,
                        detail={"src": "MANUAL", "reason": "NO_MANUAL_CODE"},
                    )
            else:
                agent._log_event(
                    "BLOCKED_GUARD",
                    case_id=case_id,
                    market_id=case_id,
                    detail={"src": "MANUAL", "reason": "GUARD"},
                )
        except Exception:
            pass
        _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, ok)
        return {
            "ok": ok,
            "error": None if ok else "BLOCKED",
            "case_id": case_id,
            "new_status": "OPEN" if has_open else "CLOSED",
            "position": pos_info,
            "pnl": {"realized": None, "unrealized": None},
            "updated_badges": updated_badges,
            "as_of": _health_state(r).get("last_data_ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.post("/paper/batch", dependencies=[Depends(_require_admin_token)])
    async def paper_batch(request: Request):
        start_ts = time.perf_counter()
        r = _repo(request)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        mode = (payload.get("mode") or "paper").strip().lower()
        op = (payload.get("op") or "").strip().lower()
        if mode != "paper":
            raise HTTPException(status_code=400, detail="Only paper mode is supported")
        if hasattr(r, "is_paused") and r.is_paused():
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, False)
            return JSONResponse(status_code=423, content={"ok": False, "error": "PAUSED"})
        if _is_stale(r, max_age_sec=60):
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, False)
            return JSONResponse(status_code=409, content={"ok": False, "error": "STALE"})

        market_ids: List[str] = []
        if op == "close_all_in_group":
            group_id = (payload.get("group_id") or "").strip()
            if not group_id:
                raise HTTPException(status_code=400, detail="group_id required")
            try:
                with r.conn() as con:
                    rows = con.execute(
                        """
                        SELECT DISTINCT p.market_id AS market_id
                        FROM paper_positions p
                        JOIN markets m ON m.market_id = p.market_id
                        WHERE p.status='OPEN' AND m.group_key = ?
                        """,
                        (group_id,),
                    ).fetchall()
                market_ids = [str(row["market_id"]) for row in rows or [] if row and row["market_id"]]
            except Exception:
                market_ids = []
        elif op == "close_all":
            try:
                with r.conn() as con:
                    rows = con.execute(
                        "SELECT DISTINCT market_id AS market_id FROM paper_positions WHERE status='OPEN'"
                    ).fetchall()
                market_ids = [str(row["market_id"]) for row in rows or [] if row and row["market_id"]]
            except Exception:
                market_ids = []
        else:
            raise HTTPException(status_code=400, detail="Unsupported op")

        closed = 0
        failed = 0
        errors: List[Dict[str, Any]] = []
        for mid in market_ids:
            try:
                res = _case_paper_close_impl(request, mid)
                if res == "ok":
                    closed += 1
                else:
                    failed += 1
                    errors.append({"case_id": mid, "error": "BLOCKED"})
            except Exception as e:
                failed += 1
                errors.append({"case_id": mid, "error": str(e)})

        updated_badges = {
            "positions": _safe(lambda: getattr(r, "count_paper_positions_filtered")(status="OPEN"), 0)
            if hasattr(r, "count_paper_positions_filtered")
            else _safe(lambda: getattr(r, "count_paper_positions")(), 0),
            "cases": _safe(lambda: getattr(r, "count_cases")(), 0),
        }
        _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, True)
        return {
            "ok": True,
            "closed": closed,
            "failed": failed,
            "errors": errors,
            "updated_badges": updated_badges,
            "as_of": _health_state(r).get("last_data_ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.post("/paper/close_all", dependencies=[Depends(_require_admin_token)])
    async def paper_close_all(request: Request):
        start_ts = time.perf_counter()
        r = _repo(request)
        agent = get_auto_paper_agent()
        stale = _is_stale(r, max_age_sec=60)
        paused = hasattr(r, "is_paused") and r.is_paused()
        try:
            agent._log_event(
                "CLOSE_ALL_START",
                detail={"src": "MANUAL", "reason": "STALE_EXIT" if stale else ("PAUSED_EXIT" if paused else "")},
            )
        except Exception:
            pass
        try:
            with r.conn() as con:
                rows = con.execute(
                    "SELECT DISTINCT market_id AS market_id FROM paper_positions WHERE status='OPEN'"
                ).fetchall()
            market_ids = [str(row["market_id"]) for row in rows or [] if row and row["market_id"]]
        except Exception:
            market_ids = []
        closed = 0
        failed = 0
        errors: List[Dict[str, Any]] = []
        for mid in market_ids:
            try:
                res = _case_paper_close_impl(request, mid)
                if res == "ok":
                    closed += 1
                    try:
                        agent._log_event(
                            "CLOSE_ALL_CHUNK",
                            case_id=mid,
                            market_id=mid,
                            detail={"src": "MANUAL", "result": "ok"},
                        )
                    except Exception:
                        pass
                else:
                    failed += 1
                    errors.append({"case_id": mid, "error": "BLOCKED"})
                    try:
                        agent._log_event(
                            "CLOSE_ALL_ERR",
                            case_id=mid,
                            market_id=mid,
                            detail={"src": "MANUAL", "error": "BLOCKED"},
                        )
                    except Exception:
                        pass
            except Exception as e:
                failed += 1
                errors.append({"case_id": mid, "error": str(e)})
                try:
                    agent._log_event(
                        "CLOSE_ALL_ERR",
                        case_id=mid,
                        market_id=mid,
                        detail={"src": "MANUAL", "error": str(e)},
                    )
                except Exception:
                    pass
        updated_badges = {
            "positions": _safe(lambda: getattr(r, "count_paper_positions_filtered")(status="OPEN"), 0)
            if hasattr(r, "count_paper_positions_filtered")
            else _safe(lambda: getattr(r, "count_paper_positions")(), 0),
            "cases": _safe(lambda: getattr(r, "count_cases")(), 0),
        }
        try:
            agent._log_event(
                "CLOSE_ALL_DONE",
                detail={"src": "MANUAL", "closed": closed, "failed": failed},
            )
        except Exception:
            pass
        _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, True)
        return {
            "ok": True,
            "closed": closed,
            "failed": failed,
            "errors": errors,
            "updated_badges": updated_badges,
            "as_of": _health_state(r).get("last_data_ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.post("/paper/unwind", dependencies=[Depends(_require_admin_token)])
    async def paper_unwind(request: Request):
        start_ts = time.perf_counter()
        r = _repo(request)
        agent = get_auto_paper_agent()
        stale = _is_stale(r, max_age_sec=60)
        paused = hasattr(r, "is_paused") and r.is_paused()
        try:
            agent._log_event(
                "UNWIND_START",
                detail={"src": "MANUAL", "reason": "STALE_EXIT" if stale else ("PAUSED_EXIT" if paused else "")},
            )
        except Exception:
            pass
        try:
            with r.conn() as con:
                rows = con.execute(
                    "SELECT DISTINCT market_id AS market_id FROM paper_positions WHERE status='OPEN'"
                ).fetchall()
            market_ids = [str(row["market_id"]) for row in rows or [] if row and row["market_id"]]
        except Exception:
            market_ids = []
        closed = 0
        failed = 0
        errors: List[Dict[str, Any]] = []
        for mid in market_ids:
            try:
                res = _case_paper_close_impl(request, mid)
                if res == "ok":
                    closed += 1
                    try:
                        agent._log_event(
                            "UNWIND_CHUNK",
                            case_id=mid,
                            market_id=mid,
                            detail={"src": "MANUAL", "result": "ok"},
                        )
                    except Exception:
                        pass
                else:
                    failed += 1
                    errors.append({"case_id": mid, "error": "BLOCKED"})
                    try:
                        agent._log_event(
                            "UNWIND_ERR",
                            case_id=mid,
                            market_id=mid,
                            detail={"src": "MANUAL", "error": "BLOCKED"},
                        )
                    except Exception:
                        pass
            except Exception as e:
                failed += 1
                errors.append({"case_id": mid, "error": str(e)})
                try:
                    agent._log_event(
                        "UNWIND_ERR",
                        case_id=mid,
                        market_id=mid,
                        detail={"src": "MANUAL", "error": str(e)},
                    )
                except Exception:
                    pass
        updated_badges = {
            "positions": _safe(lambda: getattr(r, "count_paper_positions_filtered")(status="OPEN"), 0)
            if hasattr(r, "count_paper_positions_filtered")
            else _safe(lambda: getattr(r, "count_paper_positions")(), 0),
            "cases": _safe(lambda: getattr(r, "count_cases")(), 0),
        }
        try:
            agent._log_event(
                "UNWIND_DONE",
                detail={"src": "MANUAL", "closed": closed, "failed": failed},
            )
        except Exception:
            pass
        _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, True)
        return {
            "ok": True,
            "closed": closed,
            "failed": failed,
            "errors": errors,
            "updated_badges": updated_badges,
            "as_of": _health_state(r).get("last_data_ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.get("/positions", response_class=HTMLResponse)
    def positions(request: Request):
        r = _repo(request)
        pos_page = _int_arg(request, "pos_page", _int_arg(request, "page", 1, 1, 10000), 1, 10000)
        trd_page = _int_arg(request, "trd_page", _int_arg(request, "page", 1, 1, 10000), 1, 10000)
        size = _int_arg(request, "size", 50, 10, 200)
        status = (request.query_params.get("status", "") or "").strip().upper() or None
        side = (request.query_params.get("side", "") or "").strip().upper() or None
        market_id = (request.query_params.get("market_id", "") or "").strip() or None
        pos_sort = (request.query_params.get("pos_sort", "opened_at") or "opened_at").strip().lower()
        pos_dir = (request.query_params.get("pos_dir", "desc") or "desc").strip().lower()
        trd_sort = (request.query_params.get("trd_sort", "ts") or "ts").strip().lower()
        trd_dir = (request.query_params.get("trd_dir", "desc") or "desc").strip().lower()
        if pos_dir not in {"asc", "desc"}:
            pos_dir = "desc"
        if trd_dir not in {"asc", "desc"}:
            trd_dir = "desc"
        positions_rows: List[Tuple] = []
        trades_rows: List[Tuple] = []
        paper_metrics: Dict[str, Any] = {}
        tradeability_metrics: Dict[str, Any] = {}
        paper_pnl_timeseries: List[Dict[str, Any]] = []
        try:
            offset = (pos_page - 1) * size
            if hasattr(r, "list_paper_positions_filtered"):
                positions_rows = _as_tuples(
                    r.list_paper_positions_filtered(
                        limit=size,
                        offset=offset,
                        status=status,
                        market_id=market_id,
                        sort_by=pos_sort,
                        sort_dir=pos_dir,
                    )
                )
                total_positions = int(r.count_paper_positions_filtered(status=status, market_id=market_id))
            else:
                positions_rows = _as_tuples(r.list_paper_positions(limit=200))
                total_positions = len(positions_rows)
        except Exception:
            positions_rows = []
            total_positions = 0
        try:
            offset = (trd_page - 1) * size
            if hasattr(r, "list_paper_trades_filtered"):
                trades_rows = _as_tuples(
                    r.list_paper_trades_filtered(
                        limit=size,
                        offset=offset,
                        side=side,
                        market_id=market_id,
                        sort_by=trd_sort,
                        sort_dir=trd_dir,
                    )
                )
                total_trades = int(r.count_paper_trades_filtered(side=side, market_id=market_id))
            else:
                trades_rows = _as_tuples(r.list_paper_trades(limit=200))
                total_trades = len(trades_rows)
        except Exception:
            trades_rows = []
            total_trades = 0
        try:
            paper_metrics = r.get_paper_metrics()
        except Exception:
            paper_metrics = {}
        try:
            tradeability_metrics = r.get_tradeability_metrics(hours=24)
        except Exception:
            tradeability_metrics = {}
        try:
            paper_pnl_timeseries = r.get_paper_pnl_timeseries(limit=120)
        except Exception:
            paper_pnl_timeseries = []
        pager_positions = _build_pager(
            request, total=total_positions, page=pos_page, size=size, page_key="pos_page", size_key="size"
        )
        pager_trades = _build_pager(
            request, total=total_trades, page=trd_page, size=size, page_key="trd_page", size_key="size"
        )
        return templates.TemplateResponse(
            "positions.html",
            {
                "request": request,
                "positions": positions_rows,
                "trades": trades_rows,
                "paper_metrics": paper_metrics,
                "tradeability_metrics": tradeability_metrics,
                "paper_pnl_timeseries": paper_pnl_timeseries,
                "fnum": fnum,
                "pager_positions": pager_positions,
                "pager_trades": pager_trades,
                "filters": {
                    "status": status or "",
                    "side": side or "",
                    "market_id": market_id or "",
                    "pos_sort": pos_sort,
                    "pos_dir": pos_dir,
                    "trd_sort": trd_sort,
                    "trd_dir": trd_dir,
                },
                **build_nav_context(request, "positions", positions_total=total_positions),
            },
        )

    @app.get("/reports/edge_pnl")
    def report_edge_pnl(request: Request, days: int = 7):
        r = _repo(request)
        days = max(1, min(int(days or 7), 365))
        now_ts = datetime.now(timezone.utc).timestamp()
        from_ts = now_ts - float(days) * 86400.0

        def _median(vals: list[float]) -> float | None:
            if not vals:
                return None
            vals = sorted(vals)
            mid = len(vals) // 2
            if len(vals) % 2 == 1:
                return float(vals[mid])
            return (float(vals[mid - 1]) + float(vals[mid])) / 2.0

        def _ts_from_iso(raw: str | None) -> float | None:
            if not raw:
                return None
            try:
                dt = datetime.fromisoformat(str(raw))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                return None

        try:
            with r.conn() as con:
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
                opened_ts = _ts_from_iso(rrow["opened_at"])
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
                    "median_pnl_pct": _median(pnl_list),
                    "avg_best_pct": (sum(best_list) / len(best_list)) if best_list else None,
                    "avg_worst_pct": (sum(worst_list) / len(worst_list)) if worst_list else None,
                    "avg_hold_sec": (sum(holds) / len(holds)) if holds else None,
                    "avg_edge_pct": (sum(edge_list) / len(edge_list)) if edge_list else None,
                }
            )

        out_rows.sort(key=lambda x: (int(x.get("n") or 0), float(x.get("avg_pnl_pct") or 0.0)), reverse=True)
        return {
            "from_ts": from_ts,
            "to_ts": now_ts,
            "rows": out_rows,
        }

    @app.get("/reports/edge_trades")
    def report_edge_trades(request: Request, days: int = 7, type: str | None = None, limit: int = 20):
        r = _repo(request)
        days = max(1, min(int(days or 7), 365))
        limit = max(1, min(int(limit or 20), 200))
        typ = (type or "NONE").strip().upper() or "NONE"
        now_ts = datetime.now(timezone.utc).timestamp()
        from_ts = now_ts - float(days) * 86400.0
        try:
            with r.conn() as con:
                rows = con.execute(
                    """
                    SELECT closed_ts, market_id, outcome, qty, realized_pnl_pct,
                           best_runup_pct, worst_drawdown_pct, explain_edge_pct, explain_score,
                           opened_ts, opened_at
                    FROM paper_positions
                    WHERE status='CLOSED'
                      AND closed_ts IS NOT NULL
                      AND closed_ts >= ?
                      AND COALESCE(NULLIF(explain_type,''), 'NONE') = ?
                    ORDER BY closed_ts DESC
                    LIMIT ?
                    """,
                    (from_ts, typ, int(limit)),
                ).fetchall()
        except Exception:
            rows = []

        def _ts_from_iso(raw: str | None) -> float | None:
            if not raw:
                return None
            try:
                dt = datetime.fromisoformat(str(raw))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                return None

        out_rows = []
        for rrow in rows or []:
            opened_ts = rrow["opened_ts"]
            if opened_ts is None:
                opened_ts = _ts_from_iso(rrow["opened_at"])
            hold_sec = None
            if opened_ts is not None and rrow["closed_ts"] is not None:
                try:
                    hold_sec = float(rrow["closed_ts"]) - float(opened_ts)
                except Exception:
                    hold_sec = None
            out_rows.append(
                {
                    "closed_ts": rrow["closed_ts"],
                    "case_id": rrow["market_id"],
                    "market_id": rrow["market_id"],
                    "side": rrow["outcome"],
                    "size": rrow["qty"],
                    "hold_sec": hold_sec,
                    "pnl_pct": rrow["realized_pnl_pct"],
                    "best_pct": rrow["best_runup_pct"],
                    "worst_pct": rrow["worst_drawdown_pct"],
                    "edge_pct": rrow["explain_edge_pct"],
                    "score": rrow["explain_score"],
                }
            )

        return {"type": typ, "days": days, "rows": out_rows}

    # ---------- Controls ----------
    @app.post("/control/toggle_paused", dependencies=[Depends(_require_admin_token)])
    def toggle_paused(request: Request):
        r = _repo(request)
        try:
            r.toggle_paused()
        except Exception:
            warn_exc(logger, "toggle_paused failed")
        return RedirectResponse(url="/", status_code=303)

    @app.post("/control/pause", dependencies=[Depends(_require_admin_token)])
    def pause_execution(request: Request):
        r = _repo(request)
        try:
            r.set_paused(True)
        except Exception:
            warn_exc(logger, "pause_execution failed")
        return {
            "paused": _safe(lambda: getattr(r, "is_paused")(), True),
            "paused_at": _safe(lambda: getattr(r, "get_setting_updated_at")("paused"), ""),
            "mode": str(getattr(request.app.state.settings, "mode", "")).lower(),
            "server_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.post("/control/resume", dependencies=[Depends(_require_admin_token)])
    def resume_execution(request: Request):
        r = _repo(request)
        try:
            r.set_paused(False)
        except Exception:
            warn_exc(logger, "resume_execution failed")
        return {
            "paused": _safe(lambda: getattr(r, "is_paused")(), False),
            "paused_at": _safe(lambda: getattr(r, "get_setting_updated_at")("paused"), ""),
            "mode": str(getattr(request.app.state.settings, "mode", "")).lower(),
            "server_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.get("/control/state")
    def control_state(request: Request):
        r = _repo(request)
        return {
            "paused": _safe(lambda: getattr(r, "is_paused")(), False) if hasattr(r, "is_paused") else False,
            "paused_at": _safe(lambda: getattr(r, "get_setting_updated_at")("paused"), ""),
            "mode": str(getattr(request.app.state.settings, "mode", "")).lower(),
            "server_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.get("/health/ping")
    def health_ping():
        return {"status": "ok"}

    @app.get("/health/state")
    def health_state(request: Request):
        r = _repo(request)
        state = _health_state(r)
        last_ingest_ts_source = str(state.pop("_last_ingest_ts_source", "db.snapshots.max(ts)"))
        last_ingest_row_count_5m = int(state.pop("_last_ingest_row_count_5m", 0) or 0)
        last_ingest_ts_value = str(state.pop("_last_ingest_ts_value", "") or "")
        table_used = str(state.pop("_last_ingest_table_used", "snapshots"))
        column_used = str(state.pop("_last_ingest_column_used", "ts"))
        markets_count = _safe(lambda: getattr(r, "count_markets")(), 0)
        tokens_count = _count_tokens(r) if markets_count else 0
        issues = []
        if markets_count and tokens_count == 0:
            issues.append("NO_TOKENS")
        stale_age = _stale_age_sec(r, state=state)
        state["stale_age_s"] = stale_age
        state["stale"] = bool(stale_age is None or stale_age > 60)
        fallback_overall = "STOP" if bool(state["stale"]) else "OK"
        data_warn_s_default = 45.0
        data_stop_s_default = 90.0
        book_warn_s_default = 2.5
        book_stop_s_default = 7.0
        state["freshness"] = {
            "state": {
                "data": {
                    "state": fallback_overall,
                    "age_s": stale_age,
                    "warn_s": data_warn_s_default,
                    "stop_s": data_stop_s_default,
                },
                "book": {
                    "state": fallback_overall,
                    "age_s": None,
                    "warn_s": book_warn_s_default,
                    "stop_s": book_stop_s_default,
                },
                "overall": fallback_overall,
            }
        }
        runtime_freshness = getattr(r, "_runtime_freshness_state", None)
        if isinstance(runtime_freshness, dict):
            state["freshness"] = {"state": runtime_freshness}
        try:
            fr_state = state.get("freshness", {}).get("state", {})
            data_state = fr_state.get("data", {})
            book_state = fr_state.get("book", {})
            if isinstance(data_state, dict):
                if data_state.get("warn_s") is None:
                    data_state["warn_s"] = data_warn_s_default
                if data_state.get("stop_s") is None:
                    data_state["stop_s"] = data_stop_s_default
            if isinstance(book_state, dict):
                if book_state.get("warn_s") is None:
                    book_state["warn_s"] = book_warn_s_default
                if book_state.get("stop_s") is None:
                    book_state["stop_s"] = book_stop_s_default
        except Exception:
            pass
        state["paper_pipeline"] = {"cand_count": 0, "dec_count": 0, "last": ""}
        runtime_pipe = getattr(r, "_runtime_pipeline_stats", None)
        if isinstance(runtime_pipe, dict):
            state["paper_pipeline"] = {
                "cand_count": int(runtime_pipe.get("cand_count", 0) or 0),
                "dec_count": int(runtime_pipe.get("dec_count", 0) or 0),
                "last": str(runtime_pipe.get("last") or ""),
                "decision_mode": str(runtime_pipe.get("decision_mode") or ""),
                "open_blocked_by_freshness": int(runtime_pipe.get("open_blocked_by_freshness", 0) or 0),
                "freshness_reason": str(runtime_pipe.get("freshness_reason") or ""),
            }
        state["paused"] = _safe(lambda: getattr(r, "is_paused")(), False) if hasattr(r, "is_paused") else False
        state["paused_at"] = _safe(lambda: getattr(r, "get_setting_updated_at")("paused"), "")
        state["markets_count"] = markets_count
        state["tokens_count"] = tokens_count
        state["issues"] = issues
        state["server_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if _debug_enabled(request):
            state["server_now_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            state["db_path"] = str(getattr(r, "db_path", "") or "")
            state["last_ingest_ts_source"] = last_ingest_ts_source
            state["last_ingest_row_count_5m"] = last_ingest_row_count_5m
            state["last_ingest_ts_value"] = last_ingest_ts_value
            state["table_used"] = table_used
            state["column_used"] = column_used
        return state

    # ---------- Auto Paper Agent (backend runtime) ----------
    @app.get("/agent/state")
    def agent_state(request: Request):
        _ = _repo(request)
        agent = get_auto_paper_agent()
        return {"ok": True, "state": agent.get_state()}

    @app.get("/agent/events")
    def agent_events(request: Request, limit: int = 100):
        _ = _repo(request)
        agent = get_auto_paper_agent()
        return {"ok": True, "events": agent.get_events(limit=limit)}

    @app.post("/agent/start", dependencies=[Depends(_require_admin_token)])
    async def agent_start(request: Request):
        agent = get_auto_paper_agent()
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        state = agent.start(
            cadence_sec=payload.get("cadence_sec"),
            max_positions=payload.get("max_positions"),
            size_preset=payload.get("size_preset"),
            close_min_chunk=payload.get("close_min_chunk"),
            close_hold_minutes=payload.get("close_hold_minutes"),
            emergency_hold_minutes=payload.get("emergency_hold_minutes"),
            close_allow_guarded=payload.get("close_allow_guarded"),
            close_allow_when_stale=payload.get("close_allow_when_stale"),
        )
        return {"ok": True, "state": state}

    @app.post("/agent/stop", dependencies=[Depends(_require_admin_token)])
    def agent_stop(request: Request):
        agent = get_auto_paper_agent()
        state = agent.stop()
        return {"ok": True, "state": state}

    @app.post("/agent/config", dependencies=[Depends(_require_admin_token)])
    async def agent_config(request: Request):
        agent = get_auto_paper_agent()
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        state = agent.update_config(
            cadence_sec=payload.get("cadence_sec"),
            max_positions=payload.get("max_positions"),
            size_preset=payload.get("size_preset"),
            close_min_chunk=payload.get("close_min_chunk"),
            close_hold_minutes=payload.get("close_hold_minutes"),
            emergency_hold_minutes=payload.get("emergency_hold_minutes"),
            close_allow_guarded=payload.get("close_allow_guarded"),
            close_allow_when_stale=payload.get("close_allow_when_stale"),
        )
        return {"ok": True, "state": state}

    @app.get("/health/exec")
    def health_exec(request: Request):
        data = _exec_health(request)
        data["as_of"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return data

    @app.get("/health/orderbook")
    def health_orderbook(request: Request):
        r = _repo(request)
        snapshots_per_min = 0
        active_markets = 0
        last_book_ts: Dict[str, str] = {}
        max_age_s: Optional[float] = None
        errors_1m = 0
        last_book_ts_source = "db.orderbook_snapshots.max(ts_utc)"
        try:
            with r.conn() as con:
                row = con.execute(
                    "SELECT COUNT(*) AS n FROM orderbook_snapshots WHERE julianday(ts_utc) >= julianday('now','-60 seconds')"
                ).fetchone()
            snapshots_per_min = int(row["n"] or 0) if row else 0
        except Exception:
            snapshots_per_min = 0
        try:
            with r.conn() as con:
                row = con.execute(
                    "SELECT COUNT(DISTINCT market_id) AS n FROM orderbook_snapshots WHERE julianday(ts_utc) >= julianday('now','-60 seconds')"
                ).fetchone()
            active_markets = int(row["n"] or 0) if row else 0
        except Exception:
            active_markets = 0
        try:
            with r.conn() as con:
                rows = con.execute(
                    """
                    SELECT market_id, MAX(ts_utc) AS ts
                    FROM orderbook_snapshots
                    GROUP BY market_id
                    ORDER BY ts DESC
                    LIMIT 20
                    """
                ).fetchall()
            for row in rows or []:
                last_book_ts[str(row["market_id"])] = str(row["ts"])
        except Exception:
            last_book_ts = {}
        try:
            with r.conn() as con:
                row = con.execute("SELECT MAX(ts_utc) AS ts FROM orderbook_snapshots").fetchone()
            max_ts_raw = str(row["ts"]) if row and row["ts"] else ""
            if max_ts_raw:
                dt = datetime.fromisoformat(max_ts_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                max_age_s = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
        except Exception:
            max_age_s = None
        try:
            with r.conn() as con:
                row = con.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM events_log
                    WHERE component='orderbook' AND level='ERROR'
                      AND ts >= datetime('now','-60 seconds')
                    """
                ).fetchone()
            errors_1m = int(row["n"] or 0) if row else 0
        except Exception:
            errors_1m = 0
        return {
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "snapshots_per_min": snapshots_per_min,
            "errors_1m": errors_1m,
            "active_markets": active_markets,
            "last_book_ts": last_book_ts,
            "max_age_s": max_age_s,
            **(
                {
                    "server_now_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "db_path": str(getattr(r, "db_path", "") or ""),
                    "last_book_ts_source": last_book_ts_source,
                }
                if _debug_enabled(request)
                else {}
            ),
        }

    @app.get("/market/micro")
    def market_micro(request: Request, market_id: str):
        r = _repo(request)
        warnings: List[str] = []
        book = _load_orderbook(r, market_id)
        if book:
            bids = _parse_levels(book.get("bids_json"))
            asks = _parse_levels(book.get("asks_json"))
            bid = book.get("best_bid")
            ask = book.get("best_ask")
            mid = book.get("mid")
            if mid is None and bid is not None and ask is not None:
                try:
                    mid = (float(bid) + float(ask)) / 2.0
                except Exception:
                    mid = None
            spread_abs = None
            spread_pct = None
            try:
                if bid is not None and ask is not None:
                    spread_abs = max(0.0, float(ask) - float(bid))
                    if mid:
                        spread_pct = (spread_abs / float(mid)) * 100.0
            except Exception:
                spread_abs = None
                spread_pct = None
            depth_ask_1 = None
            depth_bid_1 = None
            depth_ask_2 = None
            depth_bid_2 = None
            safe_buy = None
            safe_sell = None
            if mid:
                depth_ask_1 = calc_depth(asks, mid=mid, pct=0.01, side="ask")
                depth_bid_1 = calc_depth(bids, mid=mid, pct=0.01, side="bid")
                depth_ask_2 = calc_depth(asks, mid=mid, pct=0.02, side="ask")
                depth_bid_2 = calc_depth(bids, mid=mid, pct=0.02, side="bid")
                safe_buy = calc_max_safe_size(asks, mid=mid, max_slip_bps=RISK_MAX_SLIP_BPS, side="buy")
                safe_sell = calc_max_safe_size(bids, mid=mid, max_slip_bps=RISK_MAX_SLIP_BPS, side="sell")
            book_age_s = None
            try:
                dt = datetime.fromisoformat(str(book.get("ts_utc")))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                book_age_s = (datetime.now(timezone.utc) - dt).total_seconds()
            except Exception:
                book_age_s = None
            return {
                "market_id": market_id,
                "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "mid": mid,
                "bid": bid,
                "ask": ask,
                "spread_abs": spread_abs,
                "spread_pct": spread_pct,
                "depth_ask_1pct_usd": depth_ask_1,
                "depth_bid_1pct_usd": depth_bid_1,
                "depth_ask_2pct_usd": depth_ask_2,
                "depth_bid_2pct_usd": depth_bid_2,
                "safe_max_size_buy": safe_buy,
                "safe_max_size_sell": safe_sell,
                "book_age_s": book_age_s,
                "warnings": warnings,
            }
        snaps: Dict[str, Any] = {}
        if hasattr(r, "get_latest_snapshots"):
            try:
                snaps = r.get_latest_snapshots(market_id) or {}
            except Exception:
                snaps = {}
        outcome_key = None
        for k in snaps.keys():
            if str(k).upper() == "YES":
                outcome_key = k
                break
        if outcome_key is None and snaps:
            outcome_key = next(iter(snaps.keys()))
        snap = snaps.get(outcome_key, {}) if outcome_key else {}
        bid = snap.get("bid")
        ask = snap.get("ask")
        mid = snap.get("mid")
        if mid is None and bid is not None and ask is not None:
            try:
                mid = (float(bid) + float(ask)) / 2.0
            except Exception:
                mid = None
        spread_abs = None
        spread_pct = None
        try:
            if bid is not None and ask is not None:
                spread_abs = max(0.0, float(ask) - float(bid))
                if mid:
                    spread_pct = (spread_abs / float(mid)) * 100.0
        except Exception:
            spread_abs = None
            spread_pct = None
        book_age_s = None
        try:
            with r.conn() as con:
                row = con.execute(
                    "SELECT MAX(ts) AS ts FROM snapshots WHERE market_id = ?",
                    (market_id,),
                ).fetchone()
            ts = row["ts"] if row else None
            if ts:
                dt = datetime.fromisoformat(str(ts))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                book_age_s = (datetime.now(timezone.utc) - dt).total_seconds()
        except Exception:
            book_age_s = None
        return {
            "market_id": market_id,
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "spread_abs": spread_abs,
            "spread_pct": spread_pct,
            "depth_ask_1pct_usd": None,
            "depth_bid_1pct_usd": None,
            "depth_ask_2pct_usd": None,
            "depth_bid_2pct_usd": None,
            "safe_max_size_buy": None,
            "safe_max_size_sell": None,
            "book_age_s": book_age_s,
            "warnings": ["NO_ORDERBOOK"],
        }

    @app.post("/exec/preview")
    async def exec_preview(request: Request):
        start_ts = time.perf_counter()
        r = _repo(request)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        market_id = (payload.get("market_id") or "").strip()
        action = (payload.get("action") or "").strip().lower()
        side = (payload.get("side") or "YES").strip().upper()
        size_raw = payload.get("size_shares", None)
        size = None
        if size_raw is not None and size_raw != "":
            try:
                size = float(size_raw)
            except Exception:
                size = None
        if not market_id or action not in {"buy", "close"}:
            raise HTTPException(status_code=400, detail="Invalid request")
        if hasattr(r, "is_paused") and r.is_paused():
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, False)
            return JSONResponse(status_code=423, content={"ok": False, "error": "PAUSED"})
        if _is_stale(r, max_age_sec=60):
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, False)
            return JSONResponse(status_code=409, content={"ok": False, "error": "STALE"})

        warnings: List[str] = []
        book = _load_orderbook(r, market_id) if size is not None else None
        book_age_s = None
        if book:
            bids = _parse_levels(book.get("bids_json"))
            asks = _parse_levels(book.get("asks_json"))
            bid = book.get("best_bid")
            ask = book.get("best_ask")
            mid = book.get("mid")
            if mid is None and bid is not None and ask is not None:
                try:
                    mid = (float(bid) + float(ask)) / 2.0
                except Exception:
                    mid = None
            try:
                dt = datetime.fromisoformat(str(book.get("ts_utc")))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                book_age_s = (datetime.now(timezone.utc) - dt).total_seconds()
            except Exception:
                book_age_s = None
            levels = asks if action == "buy" else bids
            side_key = "ask" if action == "buy" else "bid"
            vwap_result = calc_vwap_fill(levels, float(size), side=side_key)
            est_vwap = vwap_result["vwap"]
            filled = float(vwap_result["filled"])
            fills = vwap_result["levels_used"]
            warnings = calc_preview_warnings(
                size_shares=size,
                book_present=True,
                filled_shares=filled,
                book_age_s=book_age_s,
                top_of_book=False,
                stale_threshold_sec=BOOK_STALE_SEC,
            )
            slip_abs = None
            slip_bps = None
            try:
                if mid is not None and est_vwap is not None:
                    slip_abs = abs(float(est_vwap) - float(mid))
                    slip_bps = (slip_abs / float(mid)) * 10000.0 if float(mid) else None
            except Exception:
                slip_abs = None
                slip_bps = None
            safe_buy = None
            safe_sell = None
            if mid is not None:
                try:
                    safe_buy = calc_max_safe_size(asks, mid=mid, max_slip_bps=RISK_MAX_SLIP_BPS, side="buy")
                    safe_sell = calc_max_safe_size(bids, mid=mid, max_slip_bps=RISK_MAX_SLIP_BPS, side="sell")
                except Exception:
                    safe_buy = None
                    safe_sell = None
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, True)
        return {
            "ok": True,
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mid": mid,
            "est_vwap": est_vwap,
            "slip_abs": slip_abs,
            "slip_bps": slip_bps,
            "fill": {"levels": fills},
            "filled_shares": filled,
            "book_age_s": book_age_s,
            "safe_max_size_buy": safe_buy,
            "safe_max_size_sell": safe_sell,
            "warnings": warnings,
        }

        # Fallback: top-of-book only
        warnings = calc_preview_warnings(
            size_shares=size,
            book_present=False,
            filled_shares=None,
            book_age_s=None,
            top_of_book=True,
            stale_threshold_sec=BOOK_STALE_SEC,
        )
        snap = {}
        if hasattr(r, "get_latest_snapshots"):
            try:
                snap = (r.get_latest_snapshots(market_id) or {}).get(side, {})
            except Exception:
                snap = {}
        bid = snap.get("bid")
        ask = snap.get("ask")
        mid = snap.get("mid")
        if mid is None and bid is not None and ask is not None:
            try:
                mid = (float(bid) + float(ask)) / 2.0
            except Exception:
                mid = None
        px = ask if action == "buy" else bid
        if px is None:
            _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, False)
            return {"ok": False, "error": "NO_BOOK"}
        est_vwap = float(px)
        slip_abs = None
        slip_bps = None
        try:
            if mid is not None:
                slip_abs = abs(float(est_vwap) - float(mid))
                slip_bps = (slip_abs / float(mid)) * 10000.0 if float(mid) else None
        except Exception:
            slip_abs = None
            slip_bps = None
        _record_exec(request, (time.perf_counter() - start_ts) * 1000.0, True)
        return {
            "ok": True,
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mid": mid,
            "est_vwap": est_vwap,
            "slip_abs": slip_abs,
            "slip_bps": slip_bps,
            "fill": {"levels": [{"price": est_vwap, "shares": size}] if size is not None else []},
            "safe_max_size_buy": None,
            "safe_max_size_sell": None,
            "warnings": warnings,
        }

    @app.get("/risk/summary")
    def risk_summary(request: Request):
        r = _repo(request)
        settings = request.app.state.settings
        risk_cfg = getattr(settings, "risk", None)
        budget_total = float(getattr(risk_cfg, "max_notional_total", 0.0) or 0.0) if risk_cfg else 0.0
        budget_group = float(getattr(risk_cfg, "max_notional_per_group", 0.0) or 0.0) if risk_cfg else 0.0

        gross = 0.0
        net = 0.0
        group_map: Dict[str, Dict[str, float]] = {}
        try:
            with r.conn() as con:
                rows = con.execute(
                    """
                    SELECT p.market_id, p.outcome, p.qty, p.avg_price, COALESCE(m.group_key,'') AS group_key,
                           (
                             SELECT s.mid
                             FROM snapshots s
                             WHERE s.market_id = p.market_id AND s.outcome = p.outcome
                             ORDER BY s.ts DESC
                             LIMIT 1
                           ) AS last_mid
                    FROM paper_positions p
                    LEFT JOIN markets m ON m.market_id = p.market_id
                    WHERE p.status='OPEN'
                    """
                ).fetchall()
            for row in rows or []:
                qty = float(row["qty"] or 0.0)
                avg = float(row["avg_price"] or 0.0)
                last_mid = row["last_mid"]
                try:
                    px = float(last_mid) if last_mid is not None else avg
                except Exception:
                    px = avg
                notional = max(0.0, qty * px)
                gross += notional
                sign = 1.0 if str(row["outcome"] or "").upper() == "YES" else -1.0
                net += notional * sign
                gk = str(row["group_key"] or "")
                gm = group_map.setdefault(gk, {"gross": 0.0, "net": 0.0})
                gm["gross"] += notional
                gm["net"] += notional * sign
        except Exception:
            gross = 0.0
            net = 0.0
            group_map = {}

        used_pct = (gross / budget_total * 100.0) if budget_total > 0 else 0.0
        by_group = []
        for gk, g in group_map.items():
            g_used = (g["gross"] / budget_group * 100.0) if budget_group > 0 else 0.0
            by_group.append(
                {"group": gk or "—", "gross": g["gross"], "net": g["net"], "used_pct": g_used}
            )
        by_group.sort(key=lambda x: float(x.get("gross") or 0.0), reverse=True)

        return {
            "gross_usd": gross,
            "net_usd": net,
            "budget_usd": budget_total,
            "used_pct": used_pct,
            "by_group": by_group[:6],
            "as_of": _health_state(r).get("last_data_ts") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    @app.post("/control/mode", dependencies=[Depends(_require_admin_token)])
    async def set_mode(request: Request):
        """Runtime mode switch for demo.

        Modes:
        - DEMO: show everything, allow paper buttons, but never place real orders
        - DRY_RUN: pipeline runs, execution stays off
        - LIVE: placeholder (UI only)
        """
        from domain.enums import Mode

        # Avoid python-multipart dependency: parse x-www-form-urlencoded manually
        from urllib.parse import parse_qs
        body = (await request.body()).decode("utf-8", errors="ignore")
        data = parse_qs(body)
        raw = ((data.get("mode", [""])[0]) or "").strip().upper()

        try:
            new_mode = Mode(raw) if raw in Mode.__members__ or raw in [m.value for m in Mode] else None
        except Exception:
            new_mode = None

        if new_mode is not None:
            s = request.app.state.settings
            try:
                s.mode = new_mode
            except Exception:
                warn_exc(logger, "set_mode: failed to set mode", mode=str(new_mode))

            # Minimal behavior tweaks (keep it predictable)
            try:
                if new_mode == Mode.DEMO:
                    s.enable_execution = False
                if new_mode == Mode.DRY_RUN:
                    s.enable_execution = False
                if new_mode == Mode.LIVE:
                    s.enable_execution = False  # stub
            except Exception:
                warn_exc(logger, "set_mode: failed to apply mode flags", mode=str(new_mode))

        return RedirectResponse(url="/", status_code=303)

    return app
