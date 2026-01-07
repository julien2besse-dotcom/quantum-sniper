#!/usr/bin/env python3
"""
Quantum Sniper - Main Trading Engine (Simulation Mode)
======================================================
Pairs trading bot using Z-Score mean reversion strategy.

SIMULATION MODE: No real trades executed. All entries/exits
are logged to database for backtesting and analysis.

Runs hourly via GitHub Actions.

Usage:
  python main.py
"""

import os
import sys
from datetime import datetime, timezone
from typing import Optional
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Trading Parameters
TIMEFRAME = "1h"
OHLCV_LIMIT = 100
ZSCORE_WINDOW = 50
Z_ENTRY_THRESHOLD = 2.0
Z_EXIT_THRESHOLD = 0.0
Z_STOP_LOSS = 4.0  # Hard stop if Z exceeds this
MAX_RISK_SCORE = 75  # Don't trade if risk > 75

# The Survivor Basket - 3 Trading Pairs
PAIRS = [
    {
        "symbol": "ATOM/DOT",
        "asset_a": "ATOM/USDT",
        "asset_b": "DOT/USDT",
        "allocation": 0.40,
        "name": "The Shield",
    },
    {
        "symbol": "SAND/MANA",
        "asset_a": "SAND/USDT",
        "asset_b": "MANA/USDT",
        "allocation": 0.35,
        "name": "The Stability",
    },
    {
        "symbol": "CRV/CVX",
        "asset_a": "CRV/USDT",
        "asset_b": "CVX/USDT",
        "allocation": 0.25,
        "name": "The Rocket",
    },
]


# ============================================================================
# COLORS FOR CONSOLE OUTPUT
# ============================================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


def log_to_supabase(level: str, source: str, message: str, details: str = None) -> None:
    """Write log entry to Supabase system_logs table."""
    try:
        from supabase import create_client
        if not SUPABASE_URL or not SUPABASE_KEY:
            return

        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "source": source,
            "message": message,
            "details": details
        }
        client.table("system_logs").insert(data).execute()
    except Exception as e:
        print(f"{Colors.RED}[LOG ERROR] Failed to write to Supabase: {e}{Colors.ENDC}")

def log_info(msg: str, source: str = "BOT", details: str = None) -> None:
    print(f"{Colors.CYAN}[INFO]{Colors.ENDC} {msg}")
    log_to_supabase("INFO", source, msg, details)


def log_success(msg: str, source: str = "BOT", details: str = None) -> None:
    print(f"{Colors.GREEN}[OK]{Colors.ENDC} {msg}")
    log_to_supabase("SUCCESS", source, msg, details)


def log_error(msg: str, source: str = "BOT", details: str = None) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.ENDC} {msg}")
    log_to_supabase("ERROR", source, msg, details)


def log_warning(msg: str, source: str = "BOT", details: str = None) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} {msg}")
    log_to_supabase("WARNING", source, msg, details)


def log_trade(msg: str) -> None:
    print(f"{Colors.GREEN}{Colors.BOLD}[TRADE]{Colors.ENDC} {msg}")


def log_signal(msg: str) -> None:
    print(f"{Colors.BLUE}[SIGNAL]{Colors.ENDC} {msg}")


# ============================================================================
# EXCHANGE CONNECTION (PUBLIC API - NO KEYS)
# ============================================================================

def create_exchange():
    """
    Create CCXT exchange instance (public mode).
    Tries multiple exchanges in case one is blocked (e.g., Binance in US).
    """
    import ccxt
    
    # List of exchanges to try (in order of preference)
    exchanges_to_try = [
        ("binance", {
            "enableRateLimit": True,
            "options": {"defaultType": "spot", "adjustForTimeDifference": True},
        }),
        ("bybit", {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }),
        ("okx", {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }),
        ("kraken", {
            "enableRateLimit": True,
        }),
    ]
    
    for exchange_id, config in exchanges_to_try:
        try:
            exchange_class = getattr(ccxt, exchange_id)
            exchange = exchange_class(config)
            exchange.load_markets()
            log_success(f"Connected to {exchange_id.upper()} (Public API)")
            return exchange
        except Exception as e:
            log_warning(f"Failed to connect to {exchange_id}: {e}")
            continue
    
    log_error("All exchanges failed. Cannot proceed.")
    return None


def normalize_symbol(exchange, symbol: str) -> str:
    """Normalize symbol format for different exchanges."""
    # Most exchanges use ATOM/USDT format
    # Some may need different formatting
    exchange_id = exchange.id.lower()
    
    if exchange_id == "kraken":
        # Kraken uses XBT instead of BTC, and different format
        symbol = symbol.replace("BTC/", "XBT/")
    
    return symbol


def fetch_ohlcv(exchange, symbol: str, timeframe: str = "1h", limit: int = 100) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from exchange."""
    try:
        # Normalize symbol for this exchange
        normalized = normalize_symbol(exchange, symbol)
        ohlcv = exchange.fetch_ohlcv(normalized, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        log_warning(f"Failed to fetch OHLCV for {symbol}: {e}")
        # Try alternative symbol format
        try:
            alt_symbol = symbol.replace("/USDT", "/USD")
            ohlcv = exchange.fetch_ohlcv(alt_symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            log_info(f"Using alternative symbol: {alt_symbol}")
            return df
        except Exception:
            log_error(f"Failed to fetch OHLCV for {symbol} (all formats)")
            return None


# ============================================================================
# Z-SCORE CALCULATION
# ============================================================================

def calculate_zscore(price_a: pd.Series, price_b: pd.Series, window: int = 50) -> pd.Series:
    """
    Calculate Z-Score of the LOG price ratio (A/B).

    Using log-ratio ensures mathematical symmetry for Long/Short signals.
    Z = (log_ratio - rolling_mean) / rolling_std

    Positive Z: A is expensive relative to B (Short A, Long B)
    Negative Z: A is cheap relative to B (Long A, Short B)
    """
    # Use LOG-RATIO for symmetric signals (V2.0 upgrade)
    log_ratio = np.log(price_a / price_b)
    rolling_mean = log_ratio.rolling(window=window).mean()
    rolling_std = log_ratio.rolling(window=window).std()

    zscore = (log_ratio - rolling_mean) / rolling_std
    return zscore


def calculate_lambda(log_ratio: pd.Series) -> float:
    """
    Calculate Lambda (mean-reversion speed) via OLS on spread changes.
    
    Lambda < 0 indicates mean reversion (GOOD).
    Lambda >= 0 indicates trending/divergence (REJECT - risk of ruin).
    
    Formula: spread_diff = alpha + lambda * spread_lag + epsilon
    """
    spread_lag = log_ratio.shift(1).dropna()
    spread_diff = log_ratio.diff().dropna()
    
    # Align indices
    spread_lag = spread_lag.iloc[1:]
    spread_diff = spread_diff.iloc[1:]
    
    if len(spread_lag) < 10:
        return 0.0  # Not enough data, fail safe
    
    # OLS: Lambda = cov(diff, lag) / var(lag)
    cov_matrix = np.cov(spread_diff, spread_lag)
    variance = np.var(spread_lag)
    
    if variance == 0:
        return 0.0  # Avoid division by zero
    
    lambda_coef = cov_matrix[0, 1] / variance
    return lambda_coef


def get_current_zscore(exchange, pair: dict) -> Optional[tuple[float, float]]:
    """
    Get current Z-Score and log-ratio for a trading pair.
    Returns (zscore, log_ratio) or None on error.
    
    SAFETY: Rejects pairs where Lambda >= 0 (non-mean-reverting).
    """
    # Fetch OHLCV for both assets
    df_a = fetch_ohlcv(exchange, pair["asset_a"], TIMEFRAME, OHLCV_LIMIT)
    df_b = fetch_ohlcv(exchange, pair["asset_b"], TIMEFRAME, OHLCV_LIMIT)

    if df_a is None or df_b is None:
        return None

    # Calculate log-ratio for Lambda check
    log_ratio = np.log(df_a["close"] / df_b["close"])
    
    # LAMBDA SAFETY CHECK (V2.0)
    lambda_coef = calculate_lambda(log_ratio)
    if lambda_coef >= 0:
        log_warning(f"{pair['symbol']}: Lambda={lambda_coef:.4f} >= 0 (TRENDING). Skipping pair.")
        return None
    
    # Log Lambda for monitoring (informational)
    half_life = -np.log(2) / lambda_coef if lambda_coef < 0 else float('inf')
    log_info(f"{pair['symbol']}: Lambda={lambda_coef:.4f}, Half-Life={half_life:.1f}h (mean-reverting ✓)")

    # Calculate Z-Score
    zscore_series = calculate_zscore(df_a["close"], df_b["close"], ZSCORE_WINDOW)

    if zscore_series.isna().all():
        log_warning(f"Not enough data for Z-Score calculation")
        return None

    current_zscore = zscore_series.iloc[-1]
    current_log_ratio = log_ratio.iloc[-1]

    return (current_zscore, current_log_ratio)


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def get_supabase_client():
    """Create Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log_error("Supabase credentials not found")
        return None

    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        log_error(f"Failed to connect to Supabase: {e}")
        return None


def check_risk_score(client) -> Optional[int]:
    """Get latest risk score from market_sentiment table."""
    try:
        result = client.table("market_sentiment") \
            .select("risk_score, sentiment") \
            .order("timestamp", desc=True) \
            .limit(1) \
            .execute()

        if result.data:
            risk = result.data[0]["risk_score"]
            sentiment = result.data[0]["sentiment"]
            return risk
        else:
            log_warning("No sentiment data found. Using default risk=50")
            return 50

    except Exception as e:
        log_error(f"Failed to fetch risk score: {e}")
        return None


def get_bot_state(client, symbol: str) -> Optional[dict]:
    """Get current bot state for a trading pair."""
    try:
        result = client.table("bot_state") \
            .select("*") \
            .eq("symbol", symbol) \
            .execute()

        if result.data:
            return result.data[0]
        return None

    except Exception as e:
        log_error(f"Failed to get bot state for {symbol}: {e}")
        return None


def update_bot_state(client, symbol: str, updates: dict) -> bool:
    """Update bot state in database."""
    try:
        updates["last_updated"] = datetime.now(timezone.utc).isoformat()
        client.table("bot_state") \
            .update(updates) \
            .eq("symbol", symbol) \
            .execute()
        return True
    except Exception as e:
        log_error(f"Failed to update bot state: {e}")
        return False


def log_trade_to_db(client, pair: str, trade_type: str, side: str,
                    price: float, zscore: float, pnl: float, comment: str) -> bool:
    """Log a trade (entry or exit) to the database."""
    try:
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pair": pair,
            "type": trade_type,
            "side": side,
            "price": price,
            "z_score": zscore,
            "pnl_percent": pnl,
            "comment": comment,
        }
        client.table("trade_logs").insert(data).execute()
        return True
    except Exception as e:
        log_error(f"Failed to log trade: {e}")
        return False


# ============================================================================
# TRADING LOGIC (SIMULATION)
# ============================================================================

def process_pair(exchange, client, pair: dict) -> None:
    """
    Process a single trading pair:
    1. Calculate current Z-Score
    2. Check for entry/exit signals
    3. Update database (SIMULATION - no real trades)
    """
    symbol = pair["symbol"]
    print(f"\n{Colors.BLUE}{'─'*50}{Colors.ENDC}")
    print(f"{Colors.BOLD}  Processing: {symbol} ({pair['name']}){Colors.ENDC}")
    print(f"{Colors.BLUE}{'─'*50}{Colors.ENDC}")

    # Get current Z-Score
    result = get_current_zscore(exchange, pair)
    if result is None:
        log_error(f"Could not calculate Z-Score for {symbol}")
        return

    zscore, ratio = result
    log_info(f"Z-Score calculated: {zscore:.4f} (no signal)", source=symbol, details=f"Ratio: {ratio:.4f}")

    # Update current Z-Score in database (for dashboard display)
    try:
         update_bot_state(client, symbol, {"current_z": float(zscore)})
    except Exception:
         pass # Ignore if column missing

    # Get current bot state
    state = get_bot_state(client, symbol)
    if state is None:
        log_warning(f"No state found for {symbol}. Skipping.", source=symbol)
        return

    is_active = state.get("is_active", False)
    entry_z = state.get("entry_z")
    entry_ratio = state.get("entry_ratio")
    position_type = state.get("position_type")

    # ========================================================================
    # ENTRY LOGIC
    # ========================================================================
    if not is_active:
        # log_info(f"Status: SCANNING (no position)") # Start logging this only if necessary to avoid noise

        # Check for SHORT A / LONG B signal (Z > threshold)
        if zscore > Z_ENTRY_THRESHOLD:
            position = "SHORT_A_LONG_B"
            log_signal(f"Z={zscore:.2f} > {Z_ENTRY_THRESHOLD} → {position}")

            # Update state
            update_bot_state(client, symbol, {
                "is_active": True,
                "position_type": position,
                "entry_z": zscore,
                "entry_ratio": ratio,
            })

            # Log trade
            log_trade_to_db(
                client, symbol, "ENTRY", position,
                ratio, zscore, 0.0,
                f"SIMULATED ENTRY: Z={zscore:.2f}, Ratio={ratio:.4f}"
            )

            log_trade(f"SIMULATED ENTRY → {position} @ Z={zscore:.2f}")

        # Check for LONG A / SHORT B signal (Z < -threshold)
        elif zscore < -Z_ENTRY_THRESHOLD:
            position = "LONG_A_SHORT_B"
            log_signal(f"Z={zscore:.2f} < -{Z_ENTRY_THRESHOLD} → {position}")

            # Update state
            update_bot_state(client, symbol, {
                "is_active": True,
                "position_type": position,
                "entry_z": zscore,
                "entry_ratio": ratio,
            })

            # Log trade
            log_trade_to_db(
                client, symbol, "ENTRY", position,
                ratio, zscore, 0.0,
                f"SIMULATED ENTRY: Z={zscore:.2f}, Ratio={ratio:.4f}"
            )

            log_trade(f"SIMULATED ENTRY → {position} @ Z={zscore:.2f}")


        else:
            log_info(f"No signal. Z={zscore:.2f} within [-{Z_ENTRY_THRESHOLD}, +{Z_ENTRY_THRESHOLD}]")

    # ========================================================================
    # EXIT LOGIC
    # ========================================================================
    else:
        log_info(f"Status: IN POSITION ({position_type})")
        log_info(f"Entry Z: {entry_z:.4f} | Entry Ratio: {entry_ratio:.4f}")

        should_exit = False
        exit_reason = ""

        # Mean reversion exit (Z crosses 0)
        if position_type == "SHORT_A_LONG_B" and zscore <= Z_EXIT_THRESHOLD:
            should_exit = True
            exit_reason = f"Mean reversion: Z={zscore:.2f} crossed below {Z_EXIT_THRESHOLD}"

        elif position_type == "LONG_A_SHORT_B" and zscore >= Z_EXIT_THRESHOLD:
            should_exit = True
            exit_reason = f"Mean reversion: Z={zscore:.2f} crossed above {Z_EXIT_THRESHOLD}"

        # Stop loss exit (Z moves further against position)
        elif abs(zscore) > Z_STOP_LOSS:
            should_exit = True
            exit_reason = f"STOP LOSS: Z={zscore:.2f} exceeded {Z_STOP_LOSS}"

        if should_exit:
            # Calculate PnL
            if entry_ratio and entry_ratio > 0:
                if position_type == "SHORT_A_LONG_B":
                    # Profit if ratio decreased
                    pnl_percent = ((entry_ratio - ratio) / entry_ratio) * 100
                else:
                    # Profit if ratio increased
                    pnl_percent = ((ratio - entry_ratio) / entry_ratio) * 100
            else:
                pnl_percent = 0.0

            log_signal(exit_reason)

            # Update state
            update_bot_state(client, symbol, {
                "is_active": False,
                "position_type": None,
                "entry_z": None,
                "entry_ratio": None,
            })

            # Log trade
            pnl_color = Colors.GREEN if pnl_percent >= 0 else Colors.RED
            log_trade_to_db(
                client, symbol, "EXIT", position_type,
                ratio, zscore, pnl_percent,
                f"SIMULATED EXIT: {exit_reason}"
            )

            log_trade(f"SIMULATED EXIT @ Z={zscore:.2f} | PnL: {pnl_color}{pnl_percent:+.2f}%{Colors.ENDC}")

        else:
            z_change = zscore - entry_z if entry_z else 0
            log_info(f"Holding position. Z change: {z_change:+.2f}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  QUANTUM SNIPER - TRADING ENGINE (SIMULATION){Colors.ENDC}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}")

    # Connect to Supabase
    client = get_supabase_client()
    if not client:
        log_error("Cannot proceed without database connection")
        sys.exit(1)

    # Check risk score
    print(f"\n{Colors.CYAN}[RISK CHECK]{Colors.ENDC}")
    risk_score = check_risk_score(client)

    if risk_score is None:
        log_error("Could not fetch risk score. Aborting for safety.")
        sys.exit(1)

    if risk_score <= 50:
        risk_color = Colors.GREEN
        risk_label = "SAFE"
    elif risk_score <= 75:
        risk_color = Colors.YELLOW
        risk_label = "CAUTION"
    else:
        risk_color = Colors.RED
        risk_label = "CRITICAL"

    print(f"  Risk Score: {risk_color}{risk_score}/100 ({risk_label}){Colors.ENDC}")

    if risk_score > MAX_RISK_SCORE:
        print(f"\n{Colors.RED}{Colors.BOLD}  TRADING HALTED - Risk too high!{Colors.ENDC}")
        print(f"  Risk score {risk_score} exceeds threshold {MAX_RISK_SCORE}")
        print(f"  Exiting without processing trades.\n")
        sys.exit(0)

    # Connect to exchange
    exchange = create_exchange()
    if not exchange:
        sys.exit(1)

    # Process each pair
    for pair in PAIRS:
        try:
            process_pair(exchange, client, pair)
        except Exception as e:
            log_error(f"Error processing {pair['symbol']}: {e}")
            continue

    # Summary
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  EXECUTION COMPLETE{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"  Pairs processed: {len(PAIRS)}")
    print(f"  Mode: SIMULATION (no real trades)")
    print(f"  Next run: Top of the hour\n")


if __name__ == "__main__":
    main()
