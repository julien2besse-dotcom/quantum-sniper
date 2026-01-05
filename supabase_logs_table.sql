-- ============================================================================
-- QUANTUM SNIPER - SYSTEM LOGS TABLE
-- Run this in Supabase SQL Editor
-- ============================================================================

-- Table for system logs (errors, info, warnings)
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    level TEXT NOT NULL,  -- 'INFO', 'WARNING', 'ERROR', 'SUCCESS'
    source TEXT NOT NULL, -- 'NEWS_AGENT', 'TRADING_BOT', 'SYSTEM'
    message TEXT NOT NULL,
    details TEXT
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level);

-- Insert initial log
INSERT INTO system_logs (level, source, message, details) VALUES
    ('INFO', 'SYSTEM', 'System logs table initialized', 'Ready to capture bot activity');
