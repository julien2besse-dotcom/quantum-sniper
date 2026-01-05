-- ============================================================================
-- QUANTUM SNIPER - SUPABASE DATABASE SCHEMA
-- ============================================================================
-- Instructions:
-- 1. Go to your Supabase Dashboard
-- 2. Navigate to SQL Editor
-- 3. Copy-paste this entire file
-- 4. Click "Run" to execute
-- ============================================================================

-- Drop existing tables (for fresh start)
DROP TABLE IF EXISTS trade_logs CASCADE;
DROP TABLE IF EXISTS market_sentiment CASCADE;
DROP TABLE IF EXISTS bot_state CASCADE;

-- ============================================================================
-- TABLE 1: bot_state
-- Tracks position state for each trading pair
-- ============================================================================
CREATE TABLE bot_state (
    symbol TEXT PRIMARY KEY,
    is_active BOOLEAN DEFAULT FALSE,
    position_type TEXT,  -- 'LONG_A_SHORT_B' or 'SHORT_A_LONG_B'
    entry_z FLOAT,
    entry_ratio FLOAT,
    current_z FLOAT,  -- Current Z-Score (updated each run for dashboard)
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Insert initial pairs (inactive)
INSERT INTO bot_state (symbol, is_active, position_type, entry_z, entry_ratio, last_updated) VALUES
    ('ATOM/DOT', FALSE, NULL, NULL, NULL, NOW()),
    ('SAND/MANA', FALSE, NULL, NULL, NULL, NOW()),
    ('CRV/CVX', FALSE, NULL, NULL, NULL, NOW());

-- ============================================================================
-- TABLE 2: trade_logs
-- Records all simulated trades (entries and exits)
-- ============================================================================
CREATE TABLE trade_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    pair TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'ENTRY' or 'EXIT'
    side TEXT NOT NULL,  -- 'LONG_A_SHORT_B' or 'SHORT_A_LONG_B' or 'NONE'
    price FLOAT,
    z_score FLOAT,
    pnl_percent FLOAT DEFAULT 0,
    comment TEXT
);

-- Insert initialization log
INSERT INTO trade_logs (pair, type, side, price, z_score, pnl_percent, comment) VALUES
    ('SYSTEM', 'INIT', 'NONE', 0, 0, 0, 'Database initialized - Quantum Sniper ready for simulation');

-- ============================================================================
-- TABLE 3: market_sentiment
-- Stores AI risk analysis results from news scanning
-- ============================================================================
CREATE TABLE market_sentiment (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    risk_score INTEGER NOT NULL CHECK (risk_score >= 0 AND risk_score <= 100),
    sentiment TEXT NOT NULL,  -- 'SAFE', 'CAUTION', 'CRITICAL'
    summary TEXT
);

-- Insert baseline sentiment
INSERT INTO market_sentiment (risk_score, sentiment, summary) VALUES
    (35, 'SAFE', 'System initialized. Markets appear stable. Awaiting first news analysis from Gemini AI.');

-- ============================================================================
-- INDEXES (for faster queries)
-- ============================================================================
CREATE INDEX idx_trade_logs_timestamp ON trade_logs(timestamp DESC);
CREATE INDEX idx_trade_logs_pair ON trade_logs(pair);
CREATE INDEX idx_market_sentiment_timestamp ON market_sentiment(timestamp DESC);

-- ============================================================================
-- ROW LEVEL SECURITY (Optional - Enable for production)
-- ============================================================================
-- Uncomment these lines if you want to enable RLS:
-- ALTER TABLE bot_state ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE trade_logs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE market_sentiment ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Run these to verify tables were created correctly:

SELECT 'bot_state' as table_name, COUNT(*) as rows FROM bot_state
UNION ALL
SELECT 'trade_logs', COUNT(*) FROM trade_logs
UNION ALL
SELECT 'market_sentiment', COUNT(*) FROM market_sentiment;

-- ============================================================================
-- DONE! Your database is ready for Quantum Sniper.
-- ============================================================================
