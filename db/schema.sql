PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  mode TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  git_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS markets (
  market_id TEXT PRIMARY KEY,
  slug TEXT NOT NULL,
  title TEXT NOT NULL,
  close_time TEXT,
  rules_hash TEXT NOT NULL DEFAULT '',
  group_key TEXT,
  raw_json TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_markets_group_key ON markets(group_key);

CREATE TABLE IF NOT EXISTS snapshots (
  ts TEXT NOT NULL,
  market_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  bid REAL,
  ask REAL,
  mid REAL,
  spread REAL,
  liquidity REAL,
  volume REAL,
  implied_prob REAL,
  PRIMARY KEY (ts, market_id, outcome),
  FOREIGN KEY (market_id) REFERENCES markets(market_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_market_ts ON snapshots(market_id, ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_market_ts_desc ON snapshots(market_id, ts DESC);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  ts_utc TEXT NOT NULL,
  best_bid REAL,
  best_ask REAL,
  mid REAL,
  bids_json TEXT NOT NULL,
  asks_json TEXT NOT NULL,
  FOREIGN KEY (market_id) REFERENCES markets(market_id)
);

CREATE INDEX IF NOT EXISTS idx_orderbook_market_ts ON orderbook_snapshots(market_id, ts_utc DESC);

CREATE TABLE IF NOT EXISTS signals (
  signal_id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  run_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  kind TEXT NOT NULL,

  scope_market_id TEXT,
  scope_group_key TEXT,
  scope_pair_key TEXT,

  features_json TEXT NOT NULL,
  claim_json TEXT NOT NULL,
  candidates_json TEXT NOT NULL,

  explain_short TEXT NOT NULL DEFAULT '',
  explain_long TEXT NOT NULL DEFAULT '',

  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);
CREATE INDEX IF NOT EXISTS idx_signals_kind ON signals(kind);
CREATE INDEX IF NOT EXISTS idx_signals_market_ts ON signals(scope_market_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_signals_group_ts ON signals(scope_group_key, ts DESC);

CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  run_id TEXT NOT NULL,
  type TEXT NOT NULL,

  plan_json TEXT NOT NULL,
  risk_json TEXT NOT NULL,

  next_review_at TEXT,
  explain_short TEXT NOT NULL DEFAULT '',
  explain_long TEXT NOT NULL DEFAULT '',

  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS decision_signals (
  decision_id TEXT NOT NULL,
  signal_id TEXT NOT NULL,
  PRIMARY KEY (decision_id, signal_id),
  FOREIGN KEY (decision_id) REFERENCES decisions(decision_id),
  FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);

CREATE TABLE IF NOT EXISTS portfolios (
  portfolio_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
  position_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  portfolio_id TEXT NOT NULL,

  market_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  side TEXT NOT NULL,

  target_notional REAL NOT NULL,
  filled_notional REAL NOT NULL DEFAULT 0,
  avg_price REAL,

  state TEXT NOT NULL,
  opened_at TEXT,
  last_review_at TEXT,

  exit_plan_json TEXT NOT NULL DEFAULT '{}',

  FOREIGN KEY (run_id) REFERENCES runs(run_id),
  FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
  FOREIGN KEY (market_id) REFERENCES markets(market_id)
);

CREATE INDEX IF NOT EXISTS idx_positions_state ON positions(state);

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  portfolio_id TEXT NOT NULL,

  market_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  side TEXT NOT NULL,

  price REAL NOT NULL,
  size REAL NOT NULL,

  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL,

  created_at TEXT,
  updated_at TEXT,

  FOREIGN KEY (run_id) REFERENCES runs(run_id),
  FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
  FOREIGN KEY (market_id) REFERENCES markets(market_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  price REAL NOT NULL,
  size REAL NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS events_log (
  ts TEXT NOT NULL,
  level TEXT NOT NULL,
  component TEXT NOT NULL,
  message TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_log_ts ON events_log(ts);
CREATE INDEX IF NOT EXISTS idx_events_log_component_ts ON events_log(component, ts DESC);
