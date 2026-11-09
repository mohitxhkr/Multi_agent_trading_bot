#!/usr/bin/env python3
"""
Dedicated Telegram Command Listener for Delta Exchange Multi-Agent Bot.
Polls Telegram every 1.5 seconds and immediately responds to all interactive slash commands:
  - /chart [symbol]   : Live Candlestick Chart with Breakout & Breakdown Overlays
  - /levels           : Comprehensive Multi-Asset Market Key Levels & Pre-Trade Plan
  - /news             : Daily Crypto Morning Briefing & Market Sentiment Card
  - /scan             : On-Demand Multi-Timeframe Regime Scan
  - /trade            : Scalp Execution Trigger (if verified A+ setup exists)
  - /status           : Wallet Balances & Cloud Bot Health
  - /positions        : Open Positions & Real-time PnL
  - /help             : Command Directory

Usage:
  python run_telegram_listener.py
"""

import sys
import os
import time
import logging

# Windows UTF-8 configuration
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.delta_client import DeltaExchangeClient
from multiagent_team.orchestrator import MultiAgentTradingOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("telegram-listener")


def main():
    print("\n" + "=" * 70)
    print("🤖 DELTA BOT DEDICATED TELEGRAM COMMAND LISTENER")
    print("=" * 70)
    print(" • Listening for /chart, /levels, /news, /scan, /trade, /status, /help...")
    print(" • Polling Interval: Every 1.5 seconds")
    print("=" * 70 + "\n")

    client = DeltaExchangeClient()
    orchestrator = MultiAgentTradingOrchestrator(client=client)

    bot = orchestrator.telegram_bot
    if not bot.is_configured:
        print("❌ Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing from .env.")
        sys.exit(1)

    print("🟢 Telegram Command Listener ACTIVE. Send any command in Telegram!")
    print("   (Press Ctrl+C to halt)\n")

    try:
        while True:
            bot.process_incoming_commands(orchestrator)
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n🛑 Telegram Command Listener halted by user.")


if __name__ == "__main__":
    main()

