#!/usr/bin/env python3
"""
Daily Morning Crypto News & Sentiment Dispatcher.
Dispatches a curated morning briefing to Telegram every day between 10:00 AM and 11:00 AM IST.
Features:
  - Fear & Greed Index with visual meter
  - Composite Market Sentiment & Multi-Agent Posture
  - Top 2-3 highest-impact crypto news catalysts with links & summaries
  - Actionable morning session gameplan

Usage:
  python send_morning_news.py --now      # Force-send briefing immediately (for preview / manual send)
  python send_morning_news.py --preview  # Print card text locally without sending to Telegram
  python send_morning_news.py            # Standard scheduled run (sends only if 10-11 AM IST and not sent today)
  python send_morning_news.py --daemon   # Standalone 24/7 background scheduler (checks every 60s)
"""

import sys
import os
import time
import argparse
import logging
from datetime import datetime, timezone, timedelta

# Windows UTF-8 configuration
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.telegram_notifier import TelegramNotifier
from multiagent_team.news_sentiment_agent import NewsSentimentAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("morning-news-dispatcher")


def get_current_ist_time():
    ist_zone = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist_zone)


def main():
    parser = argparse.ArgumentParser(description="Daily Morning Crypto News Briefing Dispatcher (10:00 - 11:00 AM IST)")
    parser.add_argument("--now", action="store_true", help="Force send immediately to Telegram regardless of time or past dispatches")
    parser.add_argument("--preview", action="store_true", help="Generate and print briefing card locally without sending to Telegram")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in background, checking every 60s for the 10-11 AM IST window")
    parser.add_argument("--min-hour", type=int, default=10, help="Window start hour in IST (default: 10 for 10:00 AM)")
    parser.add_argument("--max-hour", type=int, default=11, help="Window end hour in IST (default: 11 for 11:00 AM)")
    args = parser.parse_args()

    agent = NewsSentimentAgent()
    telegram = TelegramNotifier()

    print("\n" + "=" * 70)
    print("🌅 DAILY CRYPTO MORNING BRIEFING & SENTIMENT DISPATCHER")
    print("=" * 70)
    now_ist = get_current_ist_time()
    print(f" • Current IST Time : {now_ist.strftime('%A, %d %b %Y · %I:%M:%S %p IST')}")
    print(f" • Target Window    : {args.min_hour}:00 AM - {args.max_hour}:00 AM IST")
    print(f" • Telegram Alerts  : {'Configured & Active' if telegram.enabled else 'Disabled / Missing token'}")
    print("=" * 70 + "\n")

    if args.preview:
        print("🔍 Generating Preview of Morning Crypto Briefing...")
        report = agent.generate_sentiment_report()
        card = agent.format_daily_morning_briefing(report)
        print("\n" + card + "\n")
        print("✅ Preview generated successfully.")
        return

    if args.now:
        print("🚀 Force dispatching Daily Morning Briefing to Telegram right now...")
        report = agent.generate_sentiment_report()
        card = agent.format_daily_morning_briefing(report)
        sent = telegram.send_daily_morning_briefing(card)
        if sent:
            print("🎉 Successfully dispatched Daily Morning Briefing to Telegram!")
        else:
            print("⚠️ Failed to dispatch message. Check Telegram bot credentials and network connection.")
        return

    if args.daemon:
        print("⏳ Running in Daemon Mode. Monitoring daily morning window (10:00 - 11:00 AM IST)...")
        print("   (Press Ctrl+C to halt)")
        try:
            while True:
                now_ist = get_current_ist_time()
                dispatched = agent.check_and_dispatch_morning_briefing(
                    notifier=telegram,
                    force=False,
                    min_hour=args.min_hour,
                    max_hour=args.max_hour
                )
                if dispatched:
                    print(f"[{now_ist.strftime('%H:%M:%S IST')}] 🌅 Daily Morning Briefing successfully dispatched!")
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n🛑 Daemon stopped by user.")
            return

    # Standard one-shot run (e.g. from scheduler / cron)
    dispatched = agent.check_and_dispatch_morning_briefing(
        notifier=telegram,
        force=False,
        min_hour=args.min_hour,
        max_hour=args.max_hour
    )
    if dispatched:
        print("🎉 Daily Morning Briefing successfully dispatched to Telegram!")
    else:
        now_ist = get_current_ist_time()
        if not (args.min_hour <= now_ist.hour < args.max_hour):
            print(f"ℹ️ Outside target window ({args.min_hour}:00 - {args.max_hour}:00 AM IST). Current hour is {now_ist.hour} IST.")
            print("   Tip: Use 'python send_morning_news.py --now' to force send immediately.")
        else:
            print("ℹ️ Briefing has already been dispatched today. Will trigger again tomorrow at 10:00 AM IST.")


if __name__ == "__main__":
    main()
