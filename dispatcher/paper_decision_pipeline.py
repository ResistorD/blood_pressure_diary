from __future__ import annotations

import uuid
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class Candidate:
    ref_id: str
    reason: str
    source: str = "UNKNOWN"
    consumed_key: str = ""
    opportunity_key: str = ""


@dataclass
class Decision:
    action: str  # OPEN | HOLD | CLOSE | ABORT
    reason: str
    ref_id: str = ""


def _now_iso(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _top_scout_candidate(repo: Any) -> Candidate | None:
    try:
        with repo.conn() as con:
            row = con.execute(
                """
                SELECT
                  rowid AS signal_rowid,
                  ts AS signal_ts,
                  scope_market_id AS market_id,
                  claim_json
                FROM signals
                WHERE scope_market_id IS NOT NULL
                  AND scope_market_id <> ''
                  AND lower(agent_id) LIKE 'scout%'
                ORDER BY ts DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        market_id = str(row["market_id"] or "").strip()
        if not market_id:
            return None
        rowid_raw = str(row["signal_rowid"] or "").strip()
        ts_raw = str(row["signal_ts"] or "").strip()
        claim_raw = row["claim_json"]
        opportunity_key = ""
        try:
            claim_obj = json.loads(str(claim_raw or ""))
            if isinstance(claim_obj, dict):
                opportunity_key = str(claim_obj.get("opportunity_key") or "").strip()
        except Exception:
            opportunity_key = ""
        if rowid_raw:
            consumed_key = f"rowid:{rowid_raw}"
        elif ts_raw:
            consumed_key = f"ts:{ts_raw}|ref:{market_id}"
        else:
            consumed_key = f"ref:{market_id}"
        return Candidate(
            ref_id=market_id,
            reason="TOP_SCOUT_CANDIDATE",
            source="signals.latest_scout_scope_market_id_by_ts",
            consumed_key=consumed_key,
            opportunity_key=opportunity_key,
        )
    except Exception:
        return None


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
        candidate = _top_scout_candidate(repo)
        cand_count = 1 if candidate is not None else 0
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
        }

    candidate = _top_scout_candidate(repo)
    if candidate is None:
        decision = Decision(action="HOLD", reason="NO_CANDIDATES")
        dec = _persist_decision_if_changed(repo, context, decision)
        return {
            "cand_count": 0,
            "dec_count": int(dec),
            "last": "HOLD/NO_CANDIDATES",
            "paper_action": "HOLD",
            "paper_reason": "NO_CANDIDATES",
            "paper_source": "freshness.overall_ok.no_top_scout_candidate",
            "dedup_signature": "",
            "matched_prev_signature": "",
            "selected": 0,
            "skipped_as_stale": 0,
            "consumed_key": "",
            "opportunity_key": "",
            "same_opportunity_as_prev": 0,
            "skipped_as_same_opportunity": 0,
        }
    last_consumed_key = str(context.get("last_consumed_scout_key") or "")
    if last_consumed_key and candidate.consumed_key and last_consumed_key == candidate.consumed_key:
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
        }

    decision = Decision(action="OPEN", reason="TOP_SCOUT_CANDIDATE", ref_id=candidate.ref_id)
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
    dec = _persist_decision_if_changed(repo, context, decision)
    if int(dec) >= 1:
        return {
            "cand_count": 1,
            "dec_count": int(dec),
            "last": "OPEN/TOP_SCOUT_CANDIDATE",
            "paper_action": "OPEN",
            "paper_reason": "TOP_SCOUT_CANDIDATE",
            "paper_source": f"freshness.overall_ok.{candidate.source}",
            "dedup_signature": signature,
            "matched_prev_signature": "",
            "selected": 1,
            "skipped_as_stale": 0,
            "consumed_key": candidate.consumed_key,
            "opportunity_key": candidate.opportunity_key,
            "same_opportunity_as_prev": same_opportunity_as_prev,
            "skipped_as_same_opportunity": 0,
        }
    if prev_signature == signature:
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
    }
