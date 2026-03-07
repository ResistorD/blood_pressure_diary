# Paper Pipeline Semantics

## Inputs consumed by paper
- Source: latest scout-derived row from `signals` (`agent_id LIKE 'scout%'`), ordered by `ts DESC, rowid DESC`.
- Physical identity: `consumed_key` (`rowid:<id>` preferred; fallback `ts:<ts>|ref:<market_id>`).
- Logical identity: `opportunity_key` from `claim_json["opportunity_key"]` (empty if missing/invalid).

## Decision order (current behavior)
When freshness allows paper processing (`overall=OK`), branches are evaluated in this order:

1. No scout candidate row found:
   - `reason=NO_CANDIDATES`
2. Same physical row as last consumed (`consumed_key` match):
   - `reason=STALE_CANDIDATE_SKIPPED`
3. New physical row, but same non-empty logical opportunity as previous consumed (`opportunity_key` match):
   - `reason=SAME_OPPORTUNITY_SKIPPED`
4. Otherwise:
   - `reason=TOP_SCOUT_CANDIDATE`
   - normal paper decision flow continues

## Intentionally not used
- No heuristic meaningful-change logic over `features_json`.
- No heuristic meaningful-change logic over `explain_short` / `explain_long`.
- No suppression by dedup for logical-opportunity repetition (suppression is pre-decision).
- No architecture changes to ingest/freshness/strategy subsystems.

## PAPER_SUMMARY observability fields
- `selected`
- `reason`
- `skipped_as_stale`
- `skipped_as_same_opportunity`
- `consumed_key`
- `opportunity_key`
- `same_opportunity_as_prev`

## Design intent
- Physical novelty (`consumed_key`) alone is not sufficient.
- Repeated logical opportunity (`opportunity_key`) should be suppressed.
- Suppression happens before candidate enters decision/dedup flow.

## Regression coverage
- Behavior is regression-tested in:
  - `tests/unit/test_paper_decision_pipeline.py`
