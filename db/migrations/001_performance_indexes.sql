-- Database Performance Optimization Migration
-- Version: 2.0
-- Date: 2026-02-14
-- Sprint: 2 (Performance)

-- Enable performance monitoring
PRAGMA optimize;

-- ============================================================================
-- COMPOSITE INDEXES FOR HOT QUERIES
-- ============================================================================

-- Snapshots: Most accessed table
-- Used by: get_latest_snapshots, agent processing
CREATE INDEX IF NOT EXISTS idx_snapshots_market_outcome_ts 
  ON snapshots(market_id, outcome, ts DESC);

-- Combined index for filtering and sorting
CREATE INDEX IF NOT EXISTS idx_snapshots_ts_market 
  ON snapshots(ts DESC, market_id);

-- Decisions: Frequently queried by market and time
CREATE INDEX IF NOT EXISTS idx_decisions_v0_market_ts 
  ON decisions_v0(market_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_decisions_v0_run_ts 
  ON decisions_v0(run_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_decisions_v0_status_ts 
  ON decisions_v0(status, ts DESC);

-- Signals: Queried by kind, time, and market
CREATE INDEX IF NOT EXISTS idx_signals_kind_ts 
  ON signals(kind, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_run_ts 
  ON signals(run_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_signals_market_ts 
  ON signals(scope_market_id, ts DESC)
  WHERE scope_market_id IS NOT NULL;

-- Positions: Critical for risk checks
CREATE INDEX IF NOT EXISTS idx_positions_state_market 
  ON positions(state, market_id);

CREATE INDEX IF NOT EXISTS idx_positions_portfolio_state 
  ON positions(portfolio_id, state);

-- Orders: For execution tracking
CREATE INDEX IF NOT EXISTS idx_orders_status_created 
  ON orders(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_market_status 
  ON orders(market_id, status);

-- ============================================================================
-- MATERIALIZED VIEW FOR HOT DATA
-- ============================================================================

-- Latest snapshots per market/outcome (most frequently accessed)
DROP TABLE IF EXISTS latest_snapshots;

CREATE TABLE latest_snapshots AS
  SELECT 
    market_id,
    outcome,
    bid,
    ask,
    mid,
    spread,
    liquidity,
    volume,
    implied_prob,
    ts
  FROM (
    SELECT *,
      ROW_NUMBER() OVER (
        PARTITION BY market_id, outcome 
        ORDER BY ts DESC
      ) as rn
    FROM snapshots
  )
  WHERE rn = 1;

CREATE UNIQUE INDEX idx_latest_snapshots_pk 
  ON latest_snapshots(market_id, outcome);

CREATE INDEX idx_latest_snapshots_ts 
  ON latest_snapshots(ts DESC);

-- ============================================================================
-- TRIGGER TO MAINTAIN MATERIALIZED VIEW
-- ============================================================================

-- Trigger to update latest_snapshots on insert
DROP TRIGGER IF EXISTS trg_snapshots_after_insert;

CREATE TRIGGER trg_snapshots_after_insert
AFTER INSERT ON snapshots
BEGIN
  -- Delete old entry if exists
  DELETE FROM latest_snapshots
  WHERE market_id = NEW.market_id 
    AND outcome = NEW.outcome;
  
  -- Insert new latest
  INSERT INTO latest_snapshots(
    market_id, outcome, bid, ask, mid, spread, 
    liquidity, volume, implied_prob, ts
  )
  VALUES (
    NEW.market_id, NEW.outcome, NEW.bid, NEW.ask, NEW.mid, NEW.spread,
    NEW.liquidity, NEW.volume, NEW.implied_prob, NEW.ts
  );
END;

-- ============================================================================
-- STATISTICS TABLE FOR MONITORING
-- ============================================================================

CREATE TABLE IF NOT EXISTS query_stats (
  stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
  query_name TEXT NOT NULL,
  execution_count INTEGER DEFAULT 0,
  total_time_ms REAL DEFAULT 0,
  avg_time_ms REAL DEFAULT 0,
  last_run TEXT,
  UNIQUE(query_name)
);

-- Helper view for cache hit rate
CREATE VIEW IF NOT EXISTS cache_performance AS
SELECT 
  'latest_snapshots' as cache_name,
  COUNT(*) as entries,
  MAX(ts) as last_update,
  (SELECT COUNT(*) FROM snapshots) as source_rows,
  ROUND(100.0 * COUNT(*) / NULLIF((SELECT COUNT(DISTINCT market_id || outcome) FROM snapshots), 0), 2) as coverage_pct
FROM latest_snapshots;

-- ============================================================================
-- QUERY PLAN ANALYSIS HELPERS
-- ============================================================================

-- View to check index usage
CREATE VIEW IF NOT EXISTS index_usage AS
SELECT 
  m.name as table_name,
  il.name as index_name,
  il.origin as index_type
FROM sqlite_master m
LEFT JOIN pragma_index_list(m.name) il
WHERE m.type = 'table'
  AND m.name NOT LIKE 'sqlite_%'
ORDER BY m.name, il.name;

-- ============================================================================
-- ANALYZE FOR QUERY OPTIMIZER
-- ============================================================================

-- Update statistics for query optimizer
ANALYZE;

-- Verify indexes were created
SELECT 
  name,
  tbl_name,
  sql
FROM sqlite_master
WHERE type = 'index'
  AND name LIKE 'idx_%'
ORDER BY tbl_name, name;
