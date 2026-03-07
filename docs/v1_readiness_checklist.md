# V1 Readiness Checklist

## Core Decision/Risk Behavior
- `DONE` Freshness tiers implemented: `FULL/SAFE/HALTED` with expected gating.
- `DONE` Risk precedence and kill attribution (`risk_kind`, `kill_kind`) are explicit.
- `DONE` Focused scenario harness covers key live risk families incl. masked limit paths.
- `GOOD_ENOUGH_FOR_V1` Some limit families are mainly exercised via masked kill path; acceptable for v1 with current precedence.

## Observability/Explainability
- `DONE` Loop-level telemetry: `PIPELINE_OBS`, reconcile gate, freshness/decision mode fields.
- `DONE` Case-level telemetry: `CASE_LIFECYCLE_SUMMARY`, `CASE_OBS_SUMMARY`, `DECISION_QUALITY_SUMMARY`.
- `DONE` Case details include compact "why this decision" block.
- `DONE` Cases list includes compact reason badges (KILL/RISK/FRESHNESS/NORMAL + detail).
- `DONE` Dashboard v2 includes compact operator `System status` block.

## Operator Usability
- `DONE` Main operator page surfaces freshness, decision mode, reconcile state, open freshness block, paper last/candidate/decision.
- `GOOD_ENOUGH_FOR_V1` Core operator actions exist (pause/resume, paper controls, agent controls).
- `LATER` Consolidated one-page operator playbook (incident steps) could reduce on-call friction.

## Robustness/Failure Modes
- `DONE` SAFE mode blocks OPEN while allowing reconcile path.
- `DONE` HALTED mode skips decision execution and remains observable.
- `GOOD_ENOUGH_FOR_V1` Runtime telemetry is in-memory process state; restart continuity of runtime-only fields is not guaranteed.

## Run/Ops Hygiene
- `DONE` Run modes and fast-dev entrypoints exist (`psrun-fast/full/prod`, `run_dev_fast.sh`).
- `DONE` Health and freshness endpoints/fields exist (`/health/state` with paper pipeline/freshness).
- `GOOD_ENOUGH_FOR_V1` Local run docs exist (`README_RUN.md`, diagnostics docs).

## Testing/Confidence
- `DONE` Full test suite currently green.
- `DONE` Narrow tests exist for freshness gating, decision/case attribution, dashboard system status summarization.
- `LATER` Add higher-level smoke test that checks operator-critical HTML context fields end-to-end.

## Remaining Real Blockers
1. `BLOCKER` Mutable operator endpoints are not consistently admin-protected.
   - Evidence: only some control endpoints use `_require_admin_token`; several mutation endpoints remain open (e.g. paper action/batch/unwind, agent start/stop/config).
   - Why blocker: product-like v1 cannot credibly run outside a trusted boundary with unauthenticated write paths.

## Verdict
`READY_FOR_V1_AFTER_SMALL_FIXES`

## Minimal Next Tasks
1. Protect all mutable operator endpoints with the same admin token dependency (or equivalent auth gate).
2. Add one regression test asserting auth is required for mutable endpoints.
