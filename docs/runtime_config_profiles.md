# Runtime Config Profiles

PolySyndicate resolves runtime profile with `APP_ENV` (`dev|stage|live`).

## Profile intent
- `dev`: permissive local defaults, paper-first.
- `stage`: realistic checks, non-live by default.
- `live`: strict profile; intended for coherent `LIVE_STAGE0` setups.

## Env loading order
At startup (`python -m app.main`), env files are loaded in this order:
1. `.env`
2. `.env.<profile>` (for resolved profile)

Files are loaded with `override=False`; shell env still wins.
Startup logs include:
- `CONFIG_PROFILE ...`
- `CONFIG_VALIDATION ...`
- `CONFIG_WARNING ...`
- `CONFIG_ERROR ...`

## Common fields
- `APP_ENV`
- `EXECUTION_MODE`
- `PS_ENABLE_EXECUTION`
- `ADMIN_TOKEN`
- `PAPER_FIXED_NOTIONAL`
- `LIVE_MAX_NOTIONAL`
- `LIVE_MAX_ORDERS_PER_DAY`

## Live-only required fields (`EXECUTION_MODE=live_stage0`)
- `PRIVATE_KEY`
- `POLYMARKET_KEY`
- `POLYMARKET_API_URL`
- `LIVE_DRY_RUN=0`
- positive `LIVE_MAX_NOTIONAL`, `LIVE_MAX_ORDERS_PER_DAY`, `PAPER_FIXED_NOTIONAL`
- positive `risk.max_notional_total` in runtime settings
