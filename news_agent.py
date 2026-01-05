#!/usr/bin/env python3
"""
Quantum Sniper - News Agent (Daily Risk Check)
==============================================
Scans crypto RSS feeds and uses Google Gemini AI to generate
a risk score for trading decisions.

Runs daily at 08:00 UTC via GitHub Actions.

Usage:
  python news_agent.py
"""

import os
import sys
import json
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

# Keywords to filter relevant news
KEYWORDS = [
    "Cosmos", "ATOM",
    "Polkadot", "DOT",
    "Curve", "CRV", "CVX", "Convex",
    "Sandbox", "SAND",
    "Decentraland", "MANA",
    "Hack", "Exploit", "Vulnerability",
    "SEC", "Regulation", "Ban",
    "Crash", "Dump", "Liquidation",
    "Binance", "Exchange",
]

# RSS Feeds to scan
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://cryptonews.com/news/feed/",
    "https://decrypt.co/feed",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://bitcoinist.com/feed/",
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
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

    log_info(f"Scanning {len(RSS_FEEDS)} RSS feeds...")

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source = feed.feed.get("title", feed_url)

            for entry in feed.entries[:20]:  # Last 20 entries per feed
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

    log_success(f"Found {len(headlines)} relevant headlines")
    return headlines


# ============================================================================
# GEMINI AI ANALYSIS
# ============================================================================

def configure_gemini() -> bool:
    """Configure Google Generative AI with API key."""
    if not GEMINI_API_KEY:
        log_error("GEMINI_API_KEY not found in environment")
        return False

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        log_success("Gemini AI configured")
        return True
    except Exception as e:
        log_error(f"Failed to configure Gemini: {e}")
        return False


def analyze_with_gemini(headlines: list[dict]) -> Optional[dict]:
    """
    Send headlines to Gemini for risk analysis.
    Returns {risk_score: 0-100, sentiment: str, summary: str}.
    """
    import google.generativeai as genai

    if not headlines:
        log_info("No relevant headlines found. Using baseline risk.")
        return {
            "risk_score": 30,
            "sentiment": "SAFE",
            "summary": "No significant news detected for monitored assets. Market conditions appear stable."
        }

    # Prepare headlines text
    headlines_text = "\n".join([
        f"- {h['title']} (Source: {h['source']})"
        for h in headlines[:15]  # Limit to 15 headlines
    ])

    prompt = f"""You are a crypto market risk analyst. Analyze the following news headlines and provide a risk assessment for trading the following pairs: ATOM/DOT, SAND/MANA, CRV/CVX.

HEADLINES:
{headlines_text}

Respond ONLY with a valid JSON object (no markdown, no code blocks):
{{
    "risk_score": <integer 0-100, where 0=no risk, 100=extreme risk>,
    "sentiment": "<SAFE|CAUTION|CRITICAL>",
    "summary": "<2-3 sentence summary of market conditions and key risks>"
}}

Risk scoring guide:
- 0-30: SAFE - Normal market conditions, no significant threats
- 31-50: SAFE - Minor concerns, proceed with normal trading
- 51-75: CAUTION - Elevated risk, reduce position sizes
- 76-100: CRITICAL - High risk detected (hacks, regulatory action, market crash), halt trading

Focus on:
1. Security threats (hacks, exploits)
2. Regulatory news (SEC actions, bans)
3. Market crashes or liquidations
4. Specific news about ATOM, DOT, SAND, MANA, CRV, CVX
"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)

        # Extract text and parse JSON
        response_text = response.text.strip()

        # Clean up response if it has markdown code blocks
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        # Validate response structure
        if "risk_score" not in result:
            raise ValueError("Missing risk_score in response")

        # Ensure risk_score is valid
        result["risk_score"] = max(0, min(100, int(result["risk_score"])))

        # Ensure sentiment is valid
        if result.get("sentiment") not in ["SAFE", "CAUTION", "CRITICAL"]:
            if result["risk_score"] <= 50:
                result["sentiment"] = "SAFE"
            elif result["risk_score"] <= 75:
                result["sentiment"] = "CAUTION"
            else:
                result["sentiment"] = "CRITICAL"

        log_success(f"Gemini analysis complete: Risk={result['risk_score']}, Sentiment={result['sentiment']}")
        return result

    except json.JSONDecodeError as e:
        log_error(f"Failed to parse Gemini response as JSON: {e}")
        log_warning(f"Raw response: {response_text[:500]}")
        return None
    except Exception as e:
        log_error(f"Gemini analysis failed: {e}")
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
    print(f"{Colors.BOLD}  QUANTUM SNIPER - NEWS AGENT{Colors.ENDC}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{Colors.HEADER}{'='*70}{Colors.ENDC}\n")

    # Step 1: Configure Gemini
    if not configure_gemini():
        log_error("Cannot proceed without Gemini API")
        sys.exit(1)

    # Step 2: Fetch RSS headlines
    print()
    headlines = fetch_rss_headlines()

    # Log sample headlines
    if headlines:
        print(f"\n{Colors.BLUE}Sample Headlines:{Colors.ENDC}")
        for h in headlines[:5]:
            print(f"  - {h['title'][:70]}...")

    # Step 3: Analyze with Gemini
    print()
    analysis = analyze_with_gemini(headlines)

    if not analysis:
        log_warning("Using fallback risk score due to analysis failure")
        analysis = {
            "risk_score": 50,
            "sentiment": "CAUTION",
            "summary": "Analysis failed. Using default caution level."
        }

    # Step 4: Display results
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

    # Step 5: Save to Supabase
    print()
    if not save_to_supabase(analysis):
        log_warning("Results not saved to database")
        sys.exit(1)

    print(f"\n{Colors.GREEN}News Agent completed successfully.{Colors.ENDC}\n")


if __name__ == "__main__":
    main()
