# Live Executor Setup (Current Code Path)

This document describes the **current** PolySyndicate `LIVE_STAGE0` executor wiring.

## Scope reality check
- The current executor class is `execution/polymarket_executor.py`.
- It now performs real credential bootstrap with official `py-clob-client` derivation flow.
- It still raises `NotImplementedError` for order placement/cancel.
- So this setup is about **auth/bootstrap readiness and gating**, not full live routing yet.

## Required values for LIVE_STAGE0 readiness

### Mandatory for coherent live readiness
- `EXECUTION_MODE=live_stage0`
- `PS_ENABLE_EXECUTION=1`
- `LIVE_DRY_RUN=0`
- `PRIVATE_KEY` (non-empty)
- `POLYMARKET_API_URL` (non-empty)
- `LIVE_MAX_NOTIONAL>0`
- `LIVE_MAX_ORDERS_PER_DAY>0`
- `PAPER_FIXED_NOTIONAL>0`
- `RISK_MAX_NOTIONAL_TOTAL>0` (from runtime risk config)
- `ADMIN_TOKEN` (required for admin-protected live controls and full ready state)

### Credential source options
- **Preferred (official SDK derivation):**
  - provide `PRIVATE_KEY` + `POLYMARKET_API_URL`
  - bootstrap derives API creds via `py-clob-client` (`create_or_derive_api_creds` / equivalent)
- **Static bundle (supported):**
  - provide all three:
    - `POLYMARKET_KEY`
    - `POLYMARKET_SECRET`
    - `POLYMARKET_PASSPHRASE`
  - used directly as runtime credential bundle

### Optional / non-blocking for buildability
- `APP_ENV` profile (`dev|stage|live`) is strongly recommended for clarity (`live` for launch), but profile mismatch currently warns rather than hard-fails by itself.

## Credential meanings and expected formats

### `PRIVATE_KEY`
- Meaning: backend wallet signing identity used by Python runtime (server-side key material).
- Current code requirement: **non-empty string**.
- Practical format expectation: Ethereum-style private key string used for signing (`0x...` hex) managed as server secret.

### `POLYMARKET_KEY` / `POLYMARKET_SECRET` / `POLYMARKET_PASSPHRASE`
- Meaning: Polymarket CLOB L2 API credential bundle.
- Current code requirement:
  - not required when SDK derivation succeeds from `PRIVATE_KEY`
  - required only if you choose static bundle mode.
- Practical format expectation: values returned by official CLOB API credential creation/derivation flow.

### `POLYMARKET_API_URL`
- Meaning: base URL for Polymarket API endpoint used by live execution path.
- Current code requirement: **non-empty string**.
- Practical format expectation: HTTPS base URL (for example `https://...`).

## Identity model: wallet vs API
- Wallet signing identity: `PRIVATE_KEY`
- API identity/access bundle: `POLYMARKET_KEY` + `POLYMARKET_SECRET` + `POLYMARKET_PASSPHRASE`
- API endpoint target: `POLYMARKET_API_URL`

These are distinct controls in runtime validation and preflight.

## MetaMask clarification
Browser MetaMask login is **not** sufficient for Python live executor readiness.

Reason:
- `LIVE_STAGE0` executor runs in backend Python process.
- It reads server runtime config/env values (`PRIVATE_KEY`, `POLYMARKET_KEY`, `POLYMARKET_API_URL`).
- Browser wallet sessions are not consumed by this backend executor path.

## How to verify safely (without exposing secrets)

### 1) Use preflight endpoint
- `GET /health/preflight`
- Confirm booleans and missing list only:
  - `live_requirements.private_key_configured == true`
  - `live_requirements.polymarket_key_configured == true`
  - `live_requirements.api_url_configured == true`
  - `live_requirements.dry_run == false`
  - `execution_mode == "LIVE_STAGE0"`
  - `live_missing == []`
  - `ready_for_live == true` (when executor present + admin token protected + full config coherence)

### 2) Use `/control/live` read-only requirement tiles
- Check configured/missing statuses only.
- No secret values are displayed.

### 3) Check startup diagnostics
Look for:
- `CONFIG_PROFILE ...`
- `CONFIG_VALIDATION status=...`
- `CONFIG_WARNING ...`
- `CONFIG_ERROR ...`

## Source files for this behavior
- `execution/polymarket_executor.py`
- `app/main.py` (`build_executor` gating)
- `app/runtime_config.py` (secret resolution + validation)
- `app/config.py` (env aliases for credential fields)
- `api/http.py` (`/health/preflight` and live control readiness output)

## Bootstrap flow now implemented
- Runtime bootstrap attempts one of:
  1. static bundle mode (`POLYMARKET_KEY` + `POLYMARKET_SECRET` + `POLYMARKET_PASSPHRASE`)
  2. official SDK derivation mode (`py-clob-client` from `PRIVATE_KEY`, host, chain/sig params)
- Preflight/control surfaces:
  - attempted/success
  - bootstrap mode
  - safe bootstrap error
  - missing pieces

## Account type / signature assumptions
- Current default assumes EOA flow:
  - `POLYMARKET_SIGNATURE_TYPE=0`
  - chain id default `137`
- Non-EOA signature types require `POLYMARKET_FUNDER`.
- place/cancel logic is still intentionally unimplemented.

### Important distinction from ingest path
- Ingest/read-side CLOB calls use `PS_CLOB_API_KEY` / `CLOB_API_KEY` for optional `X-API-KEY` headers.
- Live executor bootstrap/readiness uses `PRIVATE_KEY` + `POLYMARKET_API_URL` (derivation path) or static L2 bundle.
- No automatic bridging/mapping exists between ingest `CLOB_API_KEY` and live executor L2 bundle.

## Practical conclusion
- Credential bootstrap is now real and SDK-backed, but this does **not** provide end-to-end live execution by itself.
- Order placement/cancel integration remains to be implemented.
