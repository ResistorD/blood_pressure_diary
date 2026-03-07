# Case Observability And Anti-Spam Semantics

## Placement In Pipeline
- Reconcile gate is exposed in `PIPELINE_OBS` (loop-level).
- Final per-case decision outcome is exposed in `CASE_LIFECYCLE_SUMMARY` (decision engine write/suppress point).
- Rolling aggregate anti-spam distribution is exposed in `CASE_OBS_SUMMARY` (in-memory counters, process lifetime).

## How Main Log Lines Relate
- `PIPELINE_OBS`: shows whether reconcile/case path could run this iteration.
- `CASE_LIFECYCLE_SUMMARY`: one line per case decision outcome (written or suppressed).
- `CASE_OBS_SUMMARY`: compact aggregate counts across lifecycle events, emitted periodically.

## PIPELINE_OBS Reconcile Gate Fields
- `reconcile_allowed`: `1` if reconcile path is allowed this iteration, else `0`.
- `reconcile_skip_reason`: explicit gate reason.

Common values:
- `NONE`: reconcile allowed.
- `NOT_SCHEDULED`: reconcile timer not due this iteration.
- `FRESHNESS_STOP`: reconcile blocked by freshness stop state.

## CASE_LIFECYCLE_SUMMARY Key Fields
- `case_id`: market/case identity.
- `current_status`: derived case state for action (`OPEN`, `HOLD`, `CLOSED`, ...).
- `decision_action`: concrete decision action (`PAPER_BUY_BOTH`, `HOLD`, ...).
- `decision_reason`: compact reason code.
- `decision_status`: decision status (`OK`, `BLOCKED`, `INVESTIGATE`, ...).
- `dedup`: `1` if suppressed by anti-spam/dedup, else `0`.
- `dedup_kind`: exact suppression kind.
- `risk_block`: `1` when decision status is `BLOCKED`, else `0`.
- `paused`: pause/kill-switch context flag.
- `written`: `1` if persisted, `0` if suppressed.

## dedup_kind Values (Current)
- `NONE`: no suppression, decision persisted.
- `MIN_INTERVAL`: same non-HOLD decision repeated within `min_emit_interval_sec` window.
- `HOLD_SPAM`: same HOLD decision suppressed unconditionally.
- `DUP_PARSE_ERROR`: duplicate path where previous timestamp parse failed, conservative suppression.

## CASE_OBS_SUMMARY Aggregate Counters
- `total`: total lifecycle events observed.
- `written`: persisted outcomes count.
- `dedup`: suppressed outcomes count.
- `none`: lifecycle events with `dedup_kind=NONE`.
- `min_interval`: lifecycle events with `dedup_kind=MIN_INTERVAL`.
- `hold_spam`: lifecycle events with `dedup_kind=HOLD_SPAM`.
- `dup_parse_error`: lifecycle events with `dedup_kind=DUP_PARSE_ERROR`.
- `risk_block`: lifecycle events where `risk_block=1`.

## Design Intent
- Absence of `CASE_LIFECYCLE_SUMMARY` must be explainable from `PIPELINE_OBS` reconcile gate fields.
- Each per-case suppression must be attributable from one lifecycle line (`dedup` + `dedup_kind`).
- Aggregate anti-spam distribution must be visible without manual line-by-line counting.

## Current Operational Conclusion
- In observed active reconcile windows, `MIN_INTERVAL` is the dominant case anti-spam path.
- Under current reconcile cadence, this is expected behavior and does not alone justify tuning.

## Test Coverage Reference
- `tests/test_decision_engine.py`
