from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List


log = logging.getLogger("dispatcher.paper_decision_pipeline")


@dataclass
class Candidate:
    ref_id: str
    reason: str
    source: str = "UNKNOWN"
    consumed_key: str = ""
    opportunity_key: str = ""
    similarity: float | None = None
    strategy: str = "ARB"
    strategy_action: str = "OPEN_ARB"
    score: float | None = None
    mm_bid: float | None = None
    mm_ask: float | None = None
    mm_mid: float | None = None
    mm_spread: float | None = None
    mm_bid_size: float | None = None
    mm_ask_size: float | None = None
    mm_liquidity: float | None = None
    mm_score: float | None = None
    mm_quote_mode: str = "TWO_SIDED"
    mm_post_side: str = "BOTH"


@dataclass
class Decision:
    action: str  # OPEN | HOLD | CLOSE | ABORT
    reason: str
    ref_id: str = ""


def _now_iso(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _scout_pool_size() -> int:
    try:
        val = int(os.getenv("PS_PAPER_SCOUT_POOL_N", os.getenv("PAPER_SCOUT_POOL_N", "20")) or 20)
    except Exception:
        val = 20
    return max(1, min(200, int(val)))


def _paper_min_similarity() -> float:
    raw = os.getenv("PS_PAPER_MIN_SIMILARITY", os.getenv("PAPER_MIN_SIMILARITY", "0.22"))
    try:
        val = float(raw)
    except Exception:
        val = 0.22
    if val < 0:
        return 0.0
    if val > 1.0:
        return 1.0
    return float(val)


def _arb_threshold() -> float:
    raw = os.getenv("PS_ARB_THRESHOLD", os.getenv("ARB_THRESHOLD", ""))
    if not str(raw or "").strip():
        return _paper_min_similarity()
    try:
        val = float(raw)
    except Exception:
        return _paper_min_similarity()
    return max(0.0, min(1.0, float(val)))


def _mm_threshold() -> float:
    raw = os.getenv("PS_MM_MIN_EV")
    if not str(raw or "").strip():
        raw = os.getenv("PS_MM_THRESHOLD", os.getenv("MM_THRESHOLD", "-0.001"))
    try:
        val = float(raw)
    except Exception:
        val = -0.001
    return float(val)


def _parse_similarity(features_raw: Any, claim_raw: Any) -> float | None:
    def _to_float(v: Any) -> float | None:
        try:
            if v is None:
                return None
            f = float(v)
            if f != f:  # NaN
                return None
            return f
        except Exception:
            return None

    features_obj: dict[str, Any] = {}
    claim_obj: dict[str, Any] = {}
    try:
        parsed = json.loads(str(features_raw or ""))
        if isinstance(parsed, dict):
            features_obj = parsed
    except Exception:
        features_obj = {}
    try:
        parsed = json.loads(str(claim_raw or ""))
        if isinstance(parsed, dict):
            claim_obj = parsed
    except Exception:
        claim_obj = {}

    sim = _to_float(features_obj.get("similarity"))
    if sim is not None:
        return sim
    return _to_float(claim_obj.get("similarity"))


def _parse_opportunity_key(claim_raw: Any) -> str:
    try:
        claim_obj = json.loads(str(claim_raw or ""))
        if isinstance(claim_obj, dict):
            return str(claim_obj.get("opportunity_key") or "").strip()
    except Exception:
        return ""
    return ""


def _parse_claim_dict(claim_raw: Any) -> dict[str, Any]:
    try:
        claim_obj = json.loads(str(claim_raw or ""))
        if isinstance(claim_obj, dict):
            return claim_obj
    except Exception:
        return {}
    return {}


def _parse_features_dict(features_raw: Any) -> dict[str, Any]:
    try:
        features_obj = json.loads(str(features_raw or ""))
        if isinstance(features_obj, dict):
            return features_obj
    except Exception:
        return {}
    return {}


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _parse_strategy_kind(claim_raw: Any) -> str:
    claim = _parse_claim_dict(claim_raw)
    strategy = str(claim.get("strategy") or "").strip().upper()
    if strategy == "MM" or str(claim.get("type") or "").strip().lower() == "market_making":
        return "MM"
    return "ARB"


def _parse_mm_payload(features_raw: Any, claim_raw: Any) -> dict[str, Any]:
    claim = _parse_claim_dict(claim_raw)
    features = _parse_features_dict(features_raw)
    bid = _to_float(claim.get("bid"))
    ask = _to_float(claim.get("ask"))
    mid = _to_float(claim.get("mid"))
    spread = _to_float(claim.get("spread"))
    bid_size = _to_float(claim.get("bid_size"))
    ask_size = _to_float(claim.get("ask_size"))
    liquidity = _to_float(claim.get("liquidity"))
    mm_score = _to_float(features.get("mm_score"))
    if mm_score is None:
        mm_score = _to_float(claim.get("mm_score"))
    return {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "liquidity": liquidity if liquidity is not None else min(x for x in (bid_size, ask_size) if x is not None) if (bid_size is not None and ask_size is not None) else None,
        "mm_score": mm_score,
        "quote_mode": str(claim.get("quote_mode") or "TWO_SIDED").strip().upper() or "TWO_SIDED",
        "post_side": str(claim.get("post_side") or "BOTH").strip().upper() or "BOTH",
    }


def _top_scout_candidate(repo: Any) -> tuple[Candidate | None, int, float, float | None]:
    pool_n = _scout_pool_size()
    arb_threshold = _arb_threshold()
    mm_threshold = _mm_threshold()
    try:
        with repo.conn() as con:
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
        if not rows:
            return None, 0, arb_threshold, None
        parsed: list[dict[str, Any]] = []
        for row in rows:
            market_id = str(row["market_id"] or "").strip()
            if not market_id:
                continue
            rowid_raw = str(row["signal_rowid"] or "").strip()
            ts_raw = str(row["signal_ts"] or "").strip()
            claim_raw = row["claim_json"]
            features_raw = row["features_json"]
            similarity = _parse_similarity(features_raw, claim_raw)
            strategy = _parse_strategy_kind(claim_raw)
            mm_payload = _parse_mm_payload(features_raw, claim_raw)
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
            parsed.append(
                {
                    "ref_id": market_id,
                    "ts": ts_raw,
                    "rowid": rowid_num,
                    "consumed_key": consumed_key,
                    "opportunity_key": _parse_opportunity_key(claim_raw),
                    "similarity": similarity,
                    "strategy": strategy,
                    "score": mm_payload.get("mm_score") if strategy == "MM" else similarity,
                    "mm_payload": mm_payload,
                }
            )
        if not parsed:
            return None, 0, arb_threshold, None
        eligible: list[dict[str, Any]] = []
        best_score: float | None = None
        for c in parsed:
            strategy = str(c.get("strategy") or "ARB").strip().upper() or "ARB"
            score = _to_float(c.get("score"))
            if score is not None:
                best_score = score if best_score is None else max(best_score, score)
            if strategy == "MM":
                if float(score or 0.0) < float(mm_threshold):
                    log.info(
                        "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=MM_SCORE_BELOW_THRESHOLD",
                        str(c.get("ref_id") or "").strip() or "-",
                        "-" if score is None else f"{float(score):.6f}",
                        float(mm_threshold),
                    )
                    continue
                eligible.append(c)
                continue
            if c.get("similarity") is not None and float(c.get("similarity")) >= float(arb_threshold):
                eligible.append(c)
        if not eligible:
            return None, len(parsed), arb_threshold, best_score
        eligible.sort(
            key=lambda c: (
                1 if str(c.get("strategy") or "ARB").strip().upper() == "ARB" else 0,
                float(c.get("score") if c.get("score") is not None else -1.0),
                str(c.get("ts") or ""),
                int(c.get("rowid") or 0),
            ),
            reverse=True,
        )
        best = eligible[0]
        strategy = str(best.get("strategy") or "ARB").strip().upper() or "ARB"
        reason = "TOP_MM_CANDIDATE" if strategy == "MM" else "TOP_SCOUT_CANDIDATE"
        strategy_action = "OPEN_MM" if strategy == "MM" else "OPEN_ARB"
        mm_payload = best.get("mm_payload") or {}
        return (
            Candidate(
                ref_id=str(best.get("ref_id") or ""),
                reason=reason,
                source="signals.recent_scout_pool_ranked_by_similarity_ts_rowid",
                consumed_key=str(best.get("consumed_key") or ""),
                opportunity_key=str(best.get("opportunity_key") or ""),
                similarity=float(best.get("similarity")) if best.get("similarity") is not None else None,
                strategy=strategy,
                strategy_action=strategy_action,
                score=float(best.get("score")) if best.get("score") is not None else None,
                mm_bid=_to_float(mm_payload.get("bid")),
                mm_ask=_to_float(mm_payload.get("ask")),
                mm_mid=_to_float(mm_payload.get("mid")),
                mm_spread=_to_float(mm_payload.get("spread")),
                mm_bid_size=_to_float(mm_payload.get("bid_size")),
                mm_ask_size=_to_float(mm_payload.get("ask_size")),
                mm_liquidity=_to_float(mm_payload.get("liquidity")),
                mm_score=_to_float(mm_payload.get("mm_score")),
                mm_quote_mode=str(mm_payload.get("quote_mode") or "TWO_SIDED").strip().upper() or "TWO_SIDED",
                mm_post_side=str(mm_payload.get("post_side") or "BOTH").strip().upper() or "BOTH",
            ),
            len(parsed),
            arb_threshold,
            float(best.get("score")) if best.get("score") is not None else None,
        )
    except Exception:
        return None, 0, arb_threshold, None


def _persist_decision_if_changed(repo: Any, context: Dict[str, Any], decision: Decision) -> int:
    signature = f"{decision.action}|{decision.reason}|{decision.ref_id}"
    if str(context.get("last_signature") or "") == signature:
        return 0
    context["last_signature"] = signature
    if not hasattr(repo, "insert_decision_v0"):
        return 0
    run_id = str(context.get("run_id") or "")
    ts = _now_iso(context.get("now"))
    try:
        repo.insert_decision_v0(
            decision_id=str(uuid.uuid4()),
            ts=ts,
            run_id=run_id,
            market_id=str(decision.ref_id or ""),
            action=str(decision.action),
            status="OK" if decision.action != "ABORT" else "BLOCKED",
            reason=str(decision.reason),
            reason_json=None,
            payload_json='{"source":"paper_pipeline_freshness_gate"}',
        )
        return 1
    except Exception:
        return 0


def run_paper_pipeline(repo: Any, freshness_state: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    overall = str(freshness_state.get("overall") or "STOP").upper()
    if overall == "STOP":
        decision = Decision(action="ABORT", reason="FRESHNESS_STOP")
        _persist_decision_if_changed(repo, context, decision)
        return {
            "cand_count": 0,
            "dec_count": 0,
            "last": "ABORT/FRESHNESS_STOP",
            "paper_action": "ABORT",
            "paper_reason": "FRESHNESS_STOP",
            "paper_source": "freshness.overall_stop",
            "dedup_signature": "",
            "matched_prev_signature": "",
            "selected": 0,
            "skipped_as_stale": 0,
            "consumed_key": "",
            "opportunity_key": "",
            "same_opportunity_as_prev": 0,
            "skipped_as_same_opportunity": 0,
        }

    if overall == "WARN":
        candidate, pool_size, min_similarity, best_similarity = _top_scout_candidate(repo)
        cand_count = 1 if candidate is not None else 0
        if candidate is not None and candidate.strategy == "MM":
            log.info(
                "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=FRESHNESS_BLOCK",
                candidate.ref_id or "-",
                "-" if candidate.mm_score is None else f"{float(candidate.mm_score):.6f}",
                float(_mm_threshold()),
            )
        decision = Decision(action="ABORT", reason="FRESHNESS_WARN_OBSERVE_ONLY", ref_id=(candidate.ref_id if candidate else ""))
        _persist_decision_if_changed(repo, context, decision)
        return {
            "cand_count": cand_count,
            "dec_count": 0,
            "last": "ABORT/FRESHNESS_WARN_OBSERVE_ONLY",
            "paper_action": "ABORT",
            "paper_reason": "FRESHNESS_WARN_OBSERVE_ONLY",
            "paper_source": "freshness.overall_warn.observe_only",
            "dedup_signature": "",
            "matched_prev_signature": "",
            "selected": 0,
            "skipped_as_stale": 0,
            "consumed_key": "",
            "opportunity_key": "",
            "same_opportunity_as_prev": 0,
            "skipped_as_same_opportunity": 0,
            "candidate_pool_size": int(pool_size),
            "candidate_min_similarity": float(min_similarity),
            "candidate_similarity": best_similarity,
        }

    candidate, pool_size, min_similarity, best_similarity = _top_scout_candidate(repo)
    cluster_mode = str(context.get("cluster_mode") or "NONE").strip().upper() or "NONE"
    if candidate is None:
        no_candidate_reason = "NO_CANDIDATES_ABOVE_THRESHOLD" if int(pool_size) > 0 else "NO_CANDIDATES"
        decision = Decision(action="HOLD", reason=no_candidate_reason)
        dec = _persist_decision_if_changed(repo, context, decision)
        return {
            "cand_count": 0,
            "dec_count": int(dec),
            "last": f"HOLD/{no_candidate_reason}",
            "paper_action": "HOLD",
            "paper_reason": no_candidate_reason,
            "paper_source": "freshness.overall_ok.no_ranked_scout_candidate",
            "dedup_signature": "",
            "matched_prev_signature": "",
            "selected": 0,
            "skipped_as_stale": 0,
            "consumed_key": "",
            "opportunity_key": "",
            "same_opportunity_as_prev": 0,
            "skipped_as_same_opportunity": 0,
            "candidate_pool_size": int(pool_size),
            "candidate_min_similarity": float(min_similarity),
            "candidate_similarity": best_similarity,
            "cluster_mode": cluster_mode,
        }
    last_consumed_key = str(context.get("last_consumed_scout_key") or "")
    if last_consumed_key and candidate.consumed_key and last_consumed_key == candidate.consumed_key:
        if candidate.strategy == "MM":
            log.info(
                "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=DEDUP",
                candidate.ref_id or "-",
                "-" if candidate.mm_score is None else f"{float(candidate.mm_score):.6f}",
                float(_mm_threshold()),
            )
        decision = Decision(action="HOLD", reason="NO_CANDIDATES")
        dec = _persist_decision_if_changed(repo, context, decision)
        return {
            "cand_count": 0,
            "dec_count": int(dec),
            "last": "HOLD/NO_CANDIDATES",
            "paper_action": "HOLD",
            "paper_reason": "STALE_CANDIDATE_SKIPPED",
            "paper_source": f"freshness.overall_ok.{candidate.source}",
            "dedup_signature": "",
            "matched_prev_signature": "",
            "selected": 0,
            "skipped_as_stale": 1,
            "consumed_key": candidate.consumed_key,
            "opportunity_key": candidate.opportunity_key,
            "same_opportunity_as_prev": 0,
            "skipped_as_same_opportunity": 0,
            "candidate_pool_size": int(pool_size),
            "candidate_min_similarity": float(min_similarity),
            "candidate_similarity": candidate.similarity,
            "cluster_mode": cluster_mode,
        }
    prev_opportunity_key = str(context.get("last_consumed_opportunity_key") or "")
    if candidate.opportunity_key and prev_opportunity_key and candidate.opportunity_key == prev_opportunity_key:
        # Mark this scout row as seen to avoid re-processing the same physical row each loop.
        context["last_consumed_scout_key"] = candidate.consumed_key
        decision = Decision(action="HOLD", reason="SAME_OPPORTUNITY_SKIPPED")
        dec = _persist_decision_if_changed(repo, context, decision)
        return {
            "cand_count": 0,
            "dec_count": int(dec),
            "last": "HOLD/SAME_OPPORTUNITY_SKIPPED",
            "paper_action": "HOLD",
            "paper_reason": "SAME_OPPORTUNITY_SKIPPED",
            "paper_source": f"freshness.overall_ok.{candidate.source}",
            "dedup_signature": "",
            "matched_prev_signature": "",
            "selected": 0,
            "skipped_as_stale": 0,
            "consumed_key": candidate.consumed_key,
            "opportunity_key": candidate.opportunity_key,
            "same_opportunity_as_prev": 1,
            "skipped_as_same_opportunity": 1,
            "candidate_pool_size": int(pool_size),
            "candidate_min_similarity": float(min_similarity),
            "candidate_similarity": candidate.similarity,
            "cluster_mode": cluster_mode,
        }

    if cluster_mode == "ARB" and candidate.strategy == "MM":
        log.info(
            "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=CLUSTER_MODE_ARB",
            candidate.ref_id or "-",
            "-" if candidate.mm_score is None else f"{float(candidate.mm_score):.6f}",
            float(_mm_threshold()),
        )
        decision = Decision(action="HOLD", reason="MM_BLOCKED_BY_ARB_CLUSTER", ref_id=candidate.ref_id)
        dec = _persist_decision_if_changed(repo, context, decision)
        return {
            "cand_count": 0,
            "dec_count": int(dec),
            "last": "HOLD/MM_BLOCKED_BY_ARB_CLUSTER",
            "paper_action": "HOLD",
            "paper_reason": "MM_BLOCKED_BY_ARB_CLUSTER",
            "paper_source": f"freshness.overall_ok.{candidate.source}",
            "dedup_signature": "",
            "matched_prev_signature": "",
            "selected": 0,
            "skipped_as_stale": 0,
            "consumed_key": candidate.consumed_key,
            "opportunity_key": candidate.opportunity_key,
            "same_opportunity_as_prev": 0,
            "skipped_as_same_opportunity": 0,
            "candidate_pool_size": int(pool_size),
            "candidate_min_similarity": float(min_similarity),
            "candidate_similarity": candidate.score,
            "cluster_mode": cluster_mode,
        }

    decision = Decision(action="OPEN", reason=candidate.reason, ref_id=candidate.ref_id)
    signature = f"{decision.action}|{decision.reason}|{decision.ref_id}"
    prev_signature = str(context.get("last_signature") or "")
    same_opportunity_as_prev = int(
        bool(
            candidate.opportunity_key
            and prev_opportunity_key
            and candidate.opportunity_key == prev_opportunity_key
        )
    )
    context["last_consumed_scout_key"] = candidate.consumed_key
    if candidate.opportunity_key:
        context["last_consumed_opportunity_key"] = candidate.opportunity_key
    if candidate.strategy == "ARB":
        context["cluster_mode"] = "ARB"
    elif candidate.strategy == "MM":
        context["cluster_mode"] = "MM"
    dec = _persist_decision_if_changed(repo, context, decision)
    if int(dec) >= 1:
        if candidate.strategy == "MM":
            log.info(
                "MM_DECISION_ACCEPTED market_id=%s mm_score=%s threshold=%.6f reject_reason=-",
                candidate.ref_id or "-",
                "-" if candidate.mm_score is None else f"{float(candidate.mm_score):.6f}",
                float(_mm_threshold()),
            )
        return {
            "cand_count": 1,
            "dec_count": int(dec),
            "last": f"OPEN/{candidate.reason}",
            "paper_action": "OPEN",
            "paper_reason": candidate.reason,
            "paper_source": f"freshness.overall_ok.{candidate.source}",
            "dedup_signature": signature,
            "matched_prev_signature": "",
            "selected": 1,
            "skipped_as_stale": 0,
            "consumed_key": candidate.consumed_key,
            "opportunity_key": candidate.opportunity_key,
            "same_opportunity_as_prev": same_opportunity_as_prev,
            "skipped_as_same_opportunity": 0,
            "candidate_pool_size": int(pool_size),
            "candidate_min_similarity": float(min_similarity),
            "candidate_similarity": candidate.score,
            "paper_strategy": candidate.strategy,
            "strategy_action": candidate.strategy_action,
            "cluster_mode": str(context.get("cluster_mode") or "NONE"),
            "mm_bid": candidate.mm_bid,
            "mm_ask": candidate.mm_ask,
            "mm_mid": candidate.mm_mid,
            "mm_spread": candidate.mm_spread,
            "mm_bid_size": candidate.mm_bid_size,
            "mm_ask_size": candidate.mm_ask_size,
            "mm_liquidity": candidate.mm_liquidity,
            "mm_score": candidate.mm_score,
            "mm_quote_mode": candidate.mm_quote_mode,
            "mm_post_side": candidate.mm_post_side,
        }
    if prev_signature == signature:
        if candidate.strategy == "MM":
            log.info(
                "MM_DECISION_REJECTED market_id=%s mm_score=%s threshold=%.6f reject_reason=DEDUP",
                candidate.ref_id or "-",
                "-" if candidate.mm_score is None else f"{float(candidate.mm_score):.6f}",
                float(_mm_threshold()),
            )
        return {
            "cand_count": 1,
            "dec_count": 0,
            "last": "HOLD/DEDUP",
            "paper_action": "HOLD",
            "paper_reason": "DEDUP",
            "paper_source": f"freshness.overall_ok.{candidate.source}",
            "dedup_signature": signature,
            "matched_prev_signature": prev_signature,
            "selected": 1,
            "skipped_as_stale": 0,
            "consumed_key": candidate.consumed_key,
            "opportunity_key": candidate.opportunity_key,
            "same_opportunity_as_prev": same_opportunity_as_prev,
            "skipped_as_same_opportunity": 0,
            "candidate_pool_size": int(pool_size),
            "candidate_min_similarity": float(min_similarity),
            "candidate_similarity": candidate.score,
            "paper_strategy": candidate.strategy,
            "strategy_action": candidate.strategy_action,
            "cluster_mode": str(context.get("cluster_mode") or "NONE"),
        }
    return {
        "cand_count": 1,
        "dec_count": 0,
        "last": "HOLD/NO_DECISION",
        "paper_action": "HOLD",
        "paper_reason": "NO_DECISION",
        "paper_source": f"freshness.overall_ok.{candidate.source}",
        "dedup_signature": signature,
        "matched_prev_signature": prev_signature,
        "selected": 1,
        "skipped_as_stale": 0,
        "consumed_key": candidate.consumed_key,
        "opportunity_key": candidate.opportunity_key,
        "same_opportunity_as_prev": same_opportunity_as_prev,
        "skipped_as_same_opportunity": 0,
        "candidate_pool_size": int(pool_size),
        "candidate_min_similarity": float(min_similarity),
        "candidate_similarity": candidate.score,
        "paper_strategy": candidate.strategy,
        "strategy_action": candidate.strategy_action,
        "cluster_mode": str(context.get("cluster_mode") or "NONE"),
    }
