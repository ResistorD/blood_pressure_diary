# Decision Quality Scenario Runner

## Purpose
`scripts/diagnostics/decision_quality_scenario_runner.py` drives a controlled multi-phase synthetic market sequence in the local DB to evaluate:
- decision adaptation
- case evolution and anti-spam behavior
- risk-gate observability

It is tooling only. Production logic is unchanged.

## Phases
The runner emits `SCENARIO_PHASE` markers and applies these phases in order:
1. `STABLE_BASELINE`
2. `OPPORTUNITY_APPEARS`
3. `OPPORTUNITY_STRENGTHENS`
4. `RISK_SAFE`
5. `RISK_EDGE`
6. `RISK_BLOCK`
7. `RISK_RECOVER`
8. `LIMIT_MARKET_ALREADY_OPEN_BLOCK`
9. `LIMIT_MARKET_ALREADY_OPEN_RECOVER`
10. `NEW_OR_OPPOSITE_OPPORTUNITY`

Per phase it updates existing YES/NO snapshot rows, keeps orderbook freshness alive, and inserts scout markers.

Paper-candidate identity is now intentionally phase-specific:
- phase 2 introduces `opp_a` on a selected market
- phase 3 continues the same `opp_a` with frequent refresh rows (same logical opportunity, new physical rows)
- phases 4-7 keep one stable market/opportunity line (`scenario:risk_line:<market0>`) for explicit risk transition diagnostics
- phase 8 forces a different market plus distinct `opp_z_opposite` key
- phase logs include `signal_plan=<market|opportunity_key|every=...>` for correlation

Risk-transition behavior is harness-driven (tooling only) and targets the same case line:
- `RISK_SAFE`: ages out scenario-owned `RISK_CONSTRAINT` rows for the risk market
- `RISK_EDGE`: keeps the same risk-line opportunity without adding new risk constraints
- `RISK_BLOCK`: inserts a fresh scenario-owned `RISK_CONSTRAINT`
- `RISK_RECOVER`: ages out scenario-owned `RISK_CONSTRAINT` rows again

Limit-rule behavior (additional target beyond signal-based blocking):
- `LIMIT_MARKET_ALREADY_OPEN_BLOCK`: injects a synthetic OPEN `paper_positions` row for `limit_market` so risk gate can emit `LIMIT_MARKET_ALREADY_OPEN`.
- `LIMIT_MARKET_ALREADY_OPEN_RECOVER`: removes previously injected synthetic OPEN position rows.

Kill-switch masking isolation (for limit phases):
- Limit phases set `kill_isolation=1` in phase markers.
- Harness applies a narrow reset only when `kill_switch=1` and `kill_switch_reason` starts with `AUTO:` (scenario/test induced path).
- Reset marker:
  - `SCENARIO_KILL_RESET phase=... previous_value=1 previous_reason=\"AUTO: ...\"`
- Manual/operator kill-switch reasons are not reset by the harness.

`SCENARIO_PHASE` now includes:
- `risk_state=<NONE|SAFE|EDGE|BLOCK|RECOVER>`
- `risk_market=<market_id>`
- `target_risk_kind=<...>`
- `limit_market=<market_id>`
- `kill_isolation=<0|1>`
- `driven_markets=<comma-separated-market-ids>`

Additional runner markers:
- `SCENARIO_LIMIT_ISOLATION ... mode=bounded_overlap inject_i=... clear_i=...`
- Focus mode marker fields:
  - `SCENARIO_PHASE ... focus_limit_mode=1 ...`
  - `SCENARIO_PHASE ... focus_group_mode=1 ...`
  - `SCENARIO_PHASE ... focus_quality_mode=1 ...`
  - `SCENARIO_PHASE ... focus_open_positions_mode=1 ...`
  - `SCENARIO_PHASE ... focus_notional_total_mode=1 ...`
  - `SCENARIO_LIMIT_ISOLATION ... mode=focused_overlap ...`
- Group-limit focus markers:
  - `SCENARIO_GROUP_LIMIT_PREP ... group_key=...`
  - `SCENARIO_GROUP_LIMIT_ISOLATION ... mode=focused_group_overlap ...`
  - `SCENARIO_GROUP_LIMIT_INJECT ... target_risk_kind=LIMIT_MAX_NOTIONAL_PER_GROUP ...`
  - `SCENARIO_GROUP_LIMIT_CLEAR ...`
- `SCENARIO_LIMIT_INJECT ... target_risk_kind=LIMIT_MARKET_ALREADY_OPEN ...`
- `SCENARIO_LIMIT_CLEAR ...`
- Quality-alert focus markers:
  - `SCENARIO_QUALITY_INJECT ... target_risk_kind=QUALITY_ALERT_SIGNAL ...`
  - `SCENARIO_QUALITY_CLEAR ...`
- Max-open-positions focus markers:
  - `SCENARIO_OPENPOS_ISOLATION ... mode=focused_openpos_overlap ...`
  - `SCENARIO_OPENPOS_INJECT ... target_risk_kind=LIMIT_MAX_OPEN_POSITIONS ...`
  - `SCENARIO_OPENPOS_CLEAR ...`
- Max-notional-total focus markers:
  - `SCENARIO_NOTIONAL_TOTAL_ISOLATION ... mode=focused_notional_total_overlap ...`
  - `SCENARIO_NOTIONAL_TOTAL_INJECT ... target_risk_kind=LIMIT_MAX_NOTIONAL_TOTAL ...`
  - `SCENARIO_NOTIONAL_TOTAL_CLEAR ...`

## How To Run
Terminal 1:
```bash
scripts/run_modes/psrun-fast
```

Terminal 2:
```bash
python scripts/diagnostics/decision_quality_scenario_runner.py \
  --db-path polysyndicate.db \
  --markets 3 \
  --phase-seconds 75 \
  --tick-seconds 1.0

# Focused LIMIT_MARKET_ALREADY_OPEN validation mode:
python scripts/diagnostics/decision_quality_scenario_runner.py \
  --db-path polysyndicate.db \
  --markets 3 \
  --phase-seconds 75 \
  --tick-seconds 1.0 \
  --focus-limit-market

# Focused LIMIT_MAX_NOTIONAL_PER_GROUP validation mode:
python scripts/diagnostics/decision_quality_scenario_runner.py \
  --db-path polysyndicate.db \
  --markets 3 \
  --phase-seconds 75 \
  --tick-seconds 1.0 \
  --focus-group-limit

# Focused QUALITY_ALERT_SIGNAL validation mode:
python scripts/diagnostics/decision_quality_scenario_runner.py \
  --db-path polysyndicate.db \
  --markets 3 \
  --phase-seconds 75 \
  --tick-seconds 1.0 \
  --focus-quality-alert

# Focused LIMIT_MAX_OPEN_POSITIONS validation mode:
python scripts/diagnostics/decision_quality_scenario_runner.py \
  --db-path polysyndicate.db \
  --markets 3 \
  --phase-seconds 75 \
  --tick-seconds 1.0 \
  --focus-max-open-positions

# Focused LIMIT_MAX_NOTIONAL_TOTAL validation mode:
python scripts/diagnostics/decision_quality_scenario_runner.py \
  --db-path polysyndicate.db \
  --markets 3 \
  --phase-seconds 75 \
  --tick-seconds 1.0 \
  --focus-max-notional-total
```

## Telemetry To Inspect
- `PIPELINE_OBS` (reconcile gate)
- `PAPER_SUMMARY`
- `CASE_LIFECYCLE_SUMMARY`
- `CASE_OBS_SUMMARY`
- `DECISION_QUALITY_SUMMARY`

## Notes
- Runner requires local DB with paired YES/NO snapshot rows.
- Output includes `SCENARIO_START`, `SCENARIO_PHASE`, `SCENARIO_TICK`, `SCENARIO_DONE` markers for alignment with loop logs.
- Runner now retries transient SQLite `OperationalError` failures (including open/lock I/O errors) with bounded backoff and logs `SCENARIO_DB_RETRY op=... attempt=...`.
