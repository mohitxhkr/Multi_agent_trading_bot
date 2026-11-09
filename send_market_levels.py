#!/usr/bin/env python3
"""
Market Key Levels & Breakout / Breakdown Pre-Trade Analysis Dispatcher.
Calculates high-confluence breakout resistance ceilings and breakdown support floors
for all monitored assets (BTC, ETH, XAU, etc.) with complete pre-trade analysis,
including target (TP), invalidation (SL), projected R:R, and order flow confirmation.

Usage:
  python send_market_levels.py --preview   # Inspect levels locally in terminal
  python send_market_levels.py --now       # Force dispatch levels card to Telegram
  python send_market_levels.py --symbols BTCUSD,ETHUSD,XAUUSD,SOLUSD
"""

import sys
import os
import argparse
import logging

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.delta_client import DeltaExchangeClient
from src.telegram_notifier import TelegramNotifier
from multiagent_team.orchestrator import MultiAgentTradingOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("market-levels-dispatcher")


def main():
    parser = argparse.ArgumentParser(description="Market Key Levels Breakout / Breakdown Pre-Trade Dispatcher")
    parser.add_argument("--now", action="store_true", help="Dispatch levels card directly to Telegram")
    parser.add_argument("--preview", action="store_true", help="Print levels card locally in terminal")
    parser.add_argument("--symbols", type=str, default="BTCUSD,ETHUSD,XAUUSD", help="Comma-separated symbols (default: BTCUSD,ETHUSD,XAUUSD)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print("\n" + "=" * 70)
    print("⚡ DELTA MULTI-AGENT MARKET KEY LEVELS & BREAKOUT / BREAKDOWN RADAR")
    print("=" * 70)
    print(f" • Monitored Assets : {', '.join(symbols)}")
    print("=" * 70 + "\n")

    client = DeltaExchangeClient()
    telegram = TelegramNotifier()
    orchestrator = MultiAgentTradingOrchestrator(client=client, symbols=symbols)

    card_text = orchestrator.format_market_levels_telegram(symbols=symbols)

    if args.preview or not args.now:
        print("\n" + card_text + "\n")
        print("✅ Preview generated successfully.")
        if not args.now:
            print("Tip: Use 'python send_market_levels.py --now' to dispatch this card to Telegram.")

    if args.now:
        print("\n🚀 Dispatching Market Key Levels Card to Telegram...")
        if not telegram.enabled:
            print("⚠️ Telegram is disabled or credentials not set in .env.")
            return

        sent = telegram.send_message(card_text, parse_mode="HTML")
        if sent:
            print("🎉 Successfully dispatched Market Key Levels Card to Telegram!")
        else:
            print("⚠️ Failed to dispatch message to Telegram. Check credentials or network.")


if __name__ == "__main__":
    main()
