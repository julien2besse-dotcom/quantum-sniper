#!/usr/bin/env python3
"""
Quantum Sniper - News Agent (Daily Risk Check)
==============================================
Scans crypto RSS feeds AND searches the internet using Google Gemini 3
to generate a risk score for trading decisions.

Runs daily at 08:00 UTC via GitHub Actions.

Usage:
  python news_agent.py
"""

import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Keywords to filter relevant news (for RSS pre-filtering)
# V3.0: New pairs - AVAX/NEAR, SOL/LTC, NEAR/FIL
KEYWORDS = [
    # Primary assets
    "Avalanche", "AVAX",
    "NEAR Protocol", "NEAR",
    "Solana", "SOL",
    "Litecoin", "LTC",
    "Filecoin", "FIL",
    # Risk keywords
    "Hack", "Exploit", "Vulnerability", "Breach",
    "SEC", "Regulation", "Ban", "Lawsuit",
    "Crash", "Dump", "Liquidation", "Collapse",
    "MEXC", "OKX", "Binance", "Exchange",
]

# RSS Feeds to scan (Initial context)
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://cryptonews.com/news/feed/",
    "https://decrypt.co/feed",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://bitcoinist.com/feed/",
]

# MOdel Configuration
GEMINI_MODEL = "gemini-3-flash-preview"

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
# RSS FEED SCANNER
# ============================================================================

def fetch_rss_headlines() -> list[dict]:
    """
    Fetch headlines from RSS feeds and filter by keywords.
    Returns list of {title, link, published, source}.
    """
    import feedparser

    headlines = []
    
    log_info(f"Scanning {len(RSS_FEEDS)} RSS feeds for initial context...")

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)

            for entry in feed.entries[:10]:  # Limit to 10 entries per feed to avoid noise
                title = entry.get("title", "")
                link = entry.get("link", "")

                # Check if any keyword matches
                title_lower = title.lower()
                is_relevant = any(kw.lower() in title_lower for kw in KEYWORDS)

                if is_relevant:
                    headlines.append({
                        "title": title,
                        "link": link,
                        "source": source,
                    })

        except Exception as e:
            log_warning(f"Failed to parse {feed_url}: {e}")
            continue

    log_success(f"Found {len(headlines)} relevant headlines from RSS")
    return headlines


# ============================================================================
# GEMINI AI ANALYSIS (WITH GOOGLE SEARCH)
# ============================================================================

def analyze_with_gemini(headlines: list[dict]) -> Optional[dict]:
    """
    Send headlines to Gemini 3 AND perform Google Search for real-time risk analysis.
    Returns {risk_score: 0-100, sentiment: str, summary: str}.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log_error("google-genai package not found. Please install it.")
        return None

    if not GEMINI_API_KEY:
        log_error("GEMINI_API_KEY not found")
        return None

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Prepare headlines context
    headlines_text = "N/A"
    if headlines:
        headlines_text = "\n".join([
            f"- {h['title']} (Source: {h['source']})"
            for h in headlines[:10]
        ])

    log_info(f"Connecting to {GEMINI_MODEL}...")
    log_info("Performing analysis with Google Search Grounding...")

    prompt = f"""
    You are a professional crypto market risk analyst for a pairs trading bot.
    
    Task:
    1. A list of recent RSS headlines is provided below for context.
    2. CRITICAL: Use your Google Search tool to find the VERY LATEST updates (last 24 hours) for these SPECIFIC assets:
       
       TARGET TRADING PAIRS (V3.0 Portfolio):
       - Avalanche (AVAX) + NEAR Protocol (NEAR) [The Pioneer - 40%]
       - Solana (SOL) + Litecoin (LTC) [The Classic - 30%]
       - NEAR Protocol (NEAR) + Filecoin (FIL) [The Storage - 30%]
    
    3. For EACH asset, search for:
       - Security breaches, hacks, or smart contract exploits
       - Network outages or performance issues
       - Major exchange delistings or liquidity problems
       - Regulatory enforcement actions (SEC, bans)
       - Large whale movements or unusual trading activity
       - Protocol upgrades or hard forks that could cause volatility
    
    RSS CONTEXT (Use as a starting point, but search for more recent info):
    {headlines_text}
    
    OUTPUT FORMAT:
    Respond ONLY with a valid JSON object. Do not include markdown formatting (like ```json).
    {{
        "risk_score": <integer 0-100, where 0=safe, 100=extreme panic>,
        "sentiment": "<SAFE|CAUTION|CRITICAL>",
        "summary": "<Structured summary with sections: [AVAX] ... [SOL] ... [NEAR] ... [LTC] ... [FIL] ... [MARKET] ...>"
    }}
    
    Risk Guide:
    - 0-30: SAFE (Normal volatility, all clear)
    - 31-50: SAFE (Minor news, no actionable risk)
    - 51-75: CAUTION (Notable concerns, monitor closely)
    - 76-100: CRITICAL (Active threats, consider pausing trading)
    """

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1, # Low temperature for factual analysis
            )
        )

        # Extract text
        response_text = response.text.strip()
        
        # Clean up markdown if present (Gemini might still add it despite instructions)
        if "```" in response_text:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if match:
                response_text = match.group(1).strip()

        result = json.loads(response_text)

        # Validate fields
        if "risk_score" not in result:
            raise ValueError("Missing risk_score")
        
        # Sanitize
        result["risk_score"] = int(result["risk_score"])
        if result["sentiment"] not in ["SAFE", "CAUTION", "CRITICAL"]:
             result["sentiment"] = "CAUTION" # Fallback

        log_success(f"Analysis complete: Risk={result['risk_score']} ({result['sentiment']})")
        return result

    except Exception as e:
        log_error(f"Gemini analysis failed: {e}")
        # Try to print more details about the error if it's a 400 or similar
        try:
             print(f"Raw response (if available): {response_text}")
        except:
            pass
        return None


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def save_to_supabase(analysis: dict) -> bool:
    """Save the risk analysis to Supabase market_sentiment table."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log_error("Supabase credentials not found")
        return False

    try:
        from supabase import create_client

        client = create_client(SUPABASE_URL, SUPABASE_KEY)

        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "risk_score": analysis["risk_score"],
            "sentiment": analysis["sentiment"],
            "summary": analysis.get("summary", "No summary available"),
        }

        client.table("market_sentiment").insert(data).execute()
        log_success("Analysis saved to Supabase")
        return True

    except Exception as e:
        log_error(f"Failed to save to Supabase: {e}")
        return False


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  QUANTUM SNIPER - NEWS AGENT (GEMINI 3 + SEARCH){Colors.ENDC}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}\n")

    # Step 1: Fetch RSS (Context)
    headlines = fetch_rss_headlines()

    # Step 2: Analyze with Gemini 3 (Search)
    print()
    analysis = analyze_with_gemini(headlines)

    if not analysis:
        log_warning("Using fallback risk score due to analysis failure")
        analysis = {
            "risk_score": 50,
            "sentiment": "CAUTION",
            "summary": "AI Analysis failed or timed out. System operating in default caution mode."
        }

    # Step 3: Display results
    print(f"\n{Colors.HEADER}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  RISK ANALYSIS RESULTS{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}\n")

    risk = analysis["risk_score"]
    sentiment = analysis["sentiment"]

    # Color-coded risk display
    if risk <= 50:
        risk_color = Colors.GREEN
    elif risk <= 75:
        risk_color = Colors.YELLOW
    else:
        risk_color = Colors.RED

    print(f"  Risk Score:  {risk_color}{risk}/100{Colors.ENDC}")
    print(f"  Sentiment:   {risk_color}{sentiment}{Colors.ENDC}")
    print(f"\n  Summary:")
    print(f"  {analysis.get('summary', 'N/A')}")

    if risk > 75:
        print(f"\n  {Colors.RED}{Colors.BOLD}TRADING HALTED - Risk too high!{Colors.ENDC}")

    # Step 4: Save to Supabase
    print()
    if not save_to_supabase(analysis):
        log_warning("Results not saved to database")
        sys.exit(1)

    print(f"\n{Colors.GREEN}News Agent completed successfully.{Colors.ENDC}\n")


if __name__ == "__main__":
    main()
