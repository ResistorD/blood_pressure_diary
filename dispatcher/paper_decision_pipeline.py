from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class Candidate:
    ref_id: str
    reason: str


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
                SELECT scope_market_id AS market_id
                FROM signals
                WHERE scope_market_id IS NOT NULL
                  AND scope_market_id <> ''
                  AND lower(agent_id) LIKE 'scout%'
                ORDER BY ts DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        market_id = str(row["market_id"] or "").strip()
        if not market_id:
            return None
        return Candidate(ref_id=market_id, reason="TOP_SCOUT_CANDIDATE")
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
        return {"cand_count": 0, "dec_count": 0, "last": "ABORT/FRESHNESS_STOP"}

    if overall == "WARN":
        candidate = _top_scout_candidate(repo)
        cand_count = 1 if candidate is not None else 0
        decision = Decision(action="ABORT", reason="FRESHNESS_WARN_OBSERVE_ONLY", ref_id=(candidate.ref_id if candidate else ""))
        _persist_decision_if_changed(repo, context, decision)
        return {"cand_count": cand_count, "dec_count": 0, "last": "ABORT/FRESHNESS_WARN_OBSERVE_ONLY"}

    candidate = _top_scout_candidate(repo)
    if candidate is None:
        decision = Decision(action="HOLD", reason="NO_CANDIDATES")
        dec = _persist_decision_if_changed(repo, context, decision)
        return {"cand_count": 0, "dec_count": int(dec), "last": "HOLD/NO_CANDIDATES"}

    decision = Decision(action="OPEN", reason="TOP_SCOUT_CANDIDATE", ref_id=candidate.ref_id)
    signature = f"{decision.action}|{decision.reason}|{decision.ref_id}"
    prev_signature = str(context.get("last_signature") or "")
    dec = _persist_decision_if_changed(repo, context, decision)
    if int(dec) >= 1:
        return {"cand_count": 1, "dec_count": int(dec), "last": "OPEN/TOP_SCOUT_CANDIDATE"}
    if prev_signature == signature:
        return {"cand_count": 1, "dec_count": 0, "last": "HOLD/DEDUP"}
    return {"cand_count": 1, "dec_count": 0, "last": "HOLD/NO_DECISION"}
