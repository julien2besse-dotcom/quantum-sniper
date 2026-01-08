-- ============================================================================
-- V3.0 PAIR MIGRATION - Supabase Database Update
-- ============================================================================
-- 
-- This script:
-- 1. Closes all existing positions gracefully (marks as EXIT)
-- 2. Deletes old pair states (ATOM/DOT, SAND/MANA, CRV/CVX)
-- 3. Inserts new pair states (AVAX/NEAR, SOL/LTC, NEAR/FIL)
--
-- Run this ONCE before deploying the new bot version.
-- ============================================================================

-- Step 1: Close existing positions (log final EXIT trades)
INSERT INTO trade_logs (timestamp, pair, type, side, price, z_score, pnl_percent, comment)
SELECT 
    NOW() AT TIME ZONE 'UTC',
    symbol,
    'EXIT',
    position_type,
    entry_ratio,  -- This goes into 'price' column
    0.0,  -- Final Z unknown, marking 0
    0.0,  -- PnL unknown at forced close
    'FORCED EXIT: Pair rotation to V3.0 portfolio'
FROM bot_state
WHERE is_active = true;

-- Step 2: Delete old pair states
DELETE FROM bot_state WHERE symbol IN ('ATOM/DOT', 'SAND/MANA', 'CRV/CVX');

-- Step 3: Insert new pair states (initialized as inactive)
INSERT INTO bot_state (symbol, is_active, position_type, entry_z, entry_ratio, last_updated)
VALUES 
    ('AVAX/NEAR', false, null, null, null, NOW() AT TIME ZONE 'UTC'),
    ('SOL/LTC', false, null, null, null, NOW() AT TIME ZONE 'UTC'),
    ('NEAR/FIL', false, null, null, null, NOW() AT TIME ZONE 'UTC')
ON CONFLICT (symbol) DO NOTHING;

-- Step 4: Log migration event
INSERT INTO system_logs (timestamp, level, source, message, details)
VALUES (
    NOW() AT TIME ZONE 'UTC',
    'INFO',
    'SYSTEM',
    'V3.0 Portfolio Migration Complete',
    'Closed old positions. Initialized: AVAX/NEAR, SOL/LTC, NEAR/FIL'
);

-- Verify
SELECT symbol, is_active FROM bot_state ORDER BY symbol;
