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


def log_info(msg: str) -> None:
    print(f"{Colors.CYAN}[INFO]{Colors.ENDC} {msg}")


def log_success(msg: str) -> None:
    print(f"{Colors.GREEN}[OK]{Colors.ENDC} {msg}")


def log_error(msg: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.ENDC} {msg}")


def log_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} {msg}")


def log_trade(msg: str) -> None:
    print(f"{Colors.GREEN}{Colors.BOLD}[TRADE]{Colors.ENDC} {msg}")


def log_signal(msg: str) -> None:
    print(f"{Colors.BLUE}[SIGNAL]{Colors.ENDC} {msg}")


# ============================================================================
# EXCHANGE CONNECTION (PUBLIC API - NO KEYS)
# ============================================================================

def create_exchange():
    """Create CCXT Binance exchange instance (public mode)."""
    try:
        import ccxt
        exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
                "adjustForTimeDifference": True,
            },
        })
        exchange.load_markets()
        log_success("Connected to Binance (Public API)")
        return exchange
    except Exception as e:
        log_error(f"Failed to create exchange: {e}")
        return None


def fetch_ohlcv(exchange, symbol: str, timeframe: str = "1h", limit: int = 100) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from exchange."""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        log_error(f"Failed to fetch OHLCV for {symbol}: {e}")
        return None


# ============================================================================
# Z-SCORE CALCULATION
# ============================================================================

def calculate_zscore(price_a: pd.Series, price_b: pd.Series, window: int = 50) -> pd.Series:
    """
    Calculate Z-Score of the price ratio (A/B).

    Z = (ratio - rolling_mean) / rolling_std

    Positive Z: A is expensive relative to B (Short A, Long B)
    Negative Z: A is cheap relative to B (Long A, Short B)
    """
    ratio = price_a / price_b
    rolling_mean = ratio.rolling(window=window).mean()
    rolling_std = ratio.rolling(window=window).std()

    zscore = (ratio - rolling_mean) / rolling_std
    return zscore


def get_current_zscore(exchange, pair: dict) -> Optional[tuple[float, float]]:
    """
    Get current Z-Score and price ratio for a trading pair.
    Returns (zscore, ratio) or None on error.
    """
    # Fetch OHLCV for both assets
    df_a = fetch_ohlcv(exchange, pair["asset_a"], TIMEFRAME, OHLCV_LIMIT)
    df_b = fetch_ohlcv(exchange, pair["asset_b"], TIMEFRAME, OHLCV_LIMIT)

    if df_a is None or df_b is None:
        return None

    # Calculate Z-Score
    zscore_series = calculate_zscore(df_a["close"], df_b["close"], ZSCORE_WINDOW)

    if zscore_series.isna().all():
        log_warning(f"Not enough data for Z-Score calculation")
        return None

    current_zscore = zscore_series.iloc[-1]
    current_ratio = (df_a["close"].iloc[-1] / df_b["close"].iloc[-1])

    return (current_zscore, current_ratio)


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
    log_info(f"Z-Score: {zscore:.4f} | Ratio: {ratio:.4f}")

    # Get current bot state
    state = get_bot_state(client, symbol)
    if state is None:
        log_warning(f"No state found for {symbol}. Skipping.")
        return

    is_active = state.get("is_active", False)
    entry_z = state.get("entry_z")
    entry_ratio = state.get("entry_ratio")
    position_type = state.get("position_type")

    # ========================================================================
    # ENTRY LOGIC
    # ========================================================================
    if not is_active:
        log_info(f"Status: SCANNING (no position)")

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
