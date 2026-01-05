#!/usr/bin/env python3
"""
Quantum Sniper - Database Setup & Verification
===============================================
Verifies Supabase tables exist and displays current state.

FIRST: Run supabase_schema.sql in Supabase SQL Editor!
THEN: Run this script to verify: python setup_db.py

Usage:
  python setup_db.py
"""

import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

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


def log_info(msg: str) -> None:
    print(f"{Colors.CYAN}[INFO]{Colors.ENDC} {msg}")


def log_success(msg: str) -> None:
    print(f"{Colors.GREEN}[OK]{Colors.ENDC} {msg}")


def log_error(msg: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.ENDC} {msg}")


def log_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.ENDC} {msg}")


# ============================================================================
# SUPABASE CONNECTION
# ============================================================================

def validate_environment() -> bool:
    """Check that required environment variables are set."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")

    if missing:
        log_error(f"Missing environment variables: {', '.join(missing)}")
        log_info("Please create a .env file with SUPABASE_URL and SUPABASE_KEY")
        return False
    return True


def connect_supabase():
    """Create Supabase client connection."""
    try:
        from supabase import create_client, Client
        client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log_success("Connected to Supabase")
        return client
    except Exception as e:
        log_error(f"Failed to connect to Supabase: {e}")
        return None


# ============================================================================
# TABLE VERIFICATION
# ============================================================================

def verify_bot_state(client) -> bool:
    """Verify bot_state table exists and has data."""
    try:
        result = client.table("bot_state").select("*").execute()

        if result.data:
            log_success(f"bot_state: {len(result.data)} pairs found")
            for row in result.data:
                status = "ACTIVE" if row.get("is_active") else "SCANNING"
                print(f"    - {row['symbol']}: {status}")
            return True
        else:
            log_warning("bot_state: Table exists but is empty")
            return False

    except Exception as e:
        log_error(f"bot_state: Table not found or error - {e}")
        return False


def verify_trade_logs(client) -> bool:
    """Verify trade_logs table exists."""
    try:
        result = client.table("trade_logs").select("*").order("timestamp", desc=True).limit(5).execute()

        log_success(f"trade_logs: {len(result.data)} recent entries")
        for row in result.data:
            print(f"    - [{row['type']}] {row['pair']}: {row.get('comment', '')[:50]}")
        return True

    except Exception as e:
        log_error(f"trade_logs: Table not found or error - {e}")
        return False


def verify_market_sentiment(client) -> bool:
    """Verify market_sentiment table exists."""
    try:
        result = client.table("market_sentiment").select("*").order("timestamp", desc=True).limit(1).execute()

        if result.data:
            latest = result.data[0]
            risk = latest.get("risk_score", 0)
            sentiment = latest.get("sentiment", "UNKNOWN")

            # Color code risk
            if risk <= 50:
                risk_color = Colors.GREEN
            elif risk <= 75:
                risk_color = Colors.YELLOW
            else:
                risk_color = Colors.RED

            log_success(f"market_sentiment: Latest risk = {risk_color}{risk}/100 ({sentiment}){Colors.ENDC}")
            return True
        else:
            log_warning("market_sentiment: Table exists but is empty")
            return False

    except Exception as e:
        log_error(f"market_sentiment: Table not found or error - {e}")
        return False


def print_setup_instructions():
    """Print instructions for setting up tables."""
    print(f"\n{Colors.YELLOW}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  SETUP INSTRUCTIONS{Colors.ENDC}")
    print(f"{Colors.YELLOW}{'='*70}{Colors.ENDC}")
    print(f"""
  1. Go to your Supabase Dashboard:
     {Colors.CYAN}https://supabase.com/dashboard{Colors.ENDC}

  2. Select your project and go to {Colors.BOLD}SQL Editor{Colors.ENDC}

  3. Copy-paste the contents of {Colors.GREEN}supabase_schema.sql{Colors.ENDC}

  4. Click {Colors.GREEN}Run{Colors.ENDC} to execute

  5. Run this script again to verify:
     {Colors.CYAN}python setup_db.py{Colors.ENDC}
""")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  QUANTUM SNIPER - DATABASE VERIFICATION{Colors.ENDC}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}\n")

    # Validate environment
    if not validate_environment():
        sys.exit(1)

    # Connect to Supabase
    client = connect_supabase()
    if not client:
        print_setup_instructions()
        sys.exit(1)

    print()

    # Verify each table
    results = {
        "bot_state": verify_bot_state(client),
        "trade_logs": verify_trade_logs(client),
        "market_sentiment": verify_market_sentiment(client),
    }

    # Summary
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  VERIFICATION SUMMARY{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}\n")

    all_ok = all(results.values())

    for table, ok in results.items():
        status = f"{Colors.GREEN}OK{Colors.ENDC}" if ok else f"{Colors.RED}FAILED{Colors.ENDC}"
        print(f"  {table}: [{status}]")

    if all_ok:
        print(f"\n{Colors.GREEN}{Colors.BOLD}  All tables verified! Database is ready.{Colors.ENDC}")
        print(f"\n  Next steps:")
        print(f"    1. Run news agent: {Colors.CYAN}python news_agent.py{Colors.ENDC}")
        print(f"    2. Run trading bot: {Colors.CYAN}python main.py{Colors.ENDC}")
        print()
    else:
        print(f"\n{Colors.RED}  Some tables are missing or empty.{Colors.ENDC}")
        print_setup_instructions()
        sys.exit(1)


if __name__ == "__main__":
    main()
