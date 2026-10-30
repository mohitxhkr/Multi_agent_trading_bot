#!/usr/bin/env python3
"""
24/7 Autonomous Multi-Agent Trading Scanner with Telegram Alerts & Execution.
Continuously scans Delta Exchange for high-probability setups and Liquidity Sweeps,
dispatches instant Telegram alerts, and executes protective bracket orders.
"""

import sys
import os
import time
import argparse
import logging
from datetime import datetime

# Windows UTF-8 stdout configuration
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, "state", "scanner_247.log"), encoding="utf-8")
    ]
)
logger = logging.getLogger("247-scanner")


def main():
    parser = argparse.ArgumentParser(description="24/7 Autonomous Delta Exchange Trading Scanner")
    parser.add_argument("--interval", type=int, default=120, help="Scan interval in seconds (default: 120s)")
    parser.add_argument("--interactive", action="store_true", help="Prompt before execution instead of auto-executing")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols to scan (e.g. BTCUSD,ETHUSD)")
    args = parser.parse_args()

    symbols_list = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    print("\n" + "=" * 70)
    print(" 🚀 DELTA EXCHANGE 24/7 AUTONOMOUS MULTI-AGENT SCANNER")
    print("=" * 70)
    print(f" • Mode: {'Semi-Automated (Confirmation Prompt)' if args.interactive else 'Full Autonomous (Telegram Alert & Execute)'}")
    print(f" • Scan Interval: Every {args.interval} seconds")
    print(f" • Sizing: 75% to 100% Capital Allocation")
    print(f" • Leverage: 50x (BTC) | 25x (ETH, SOL, PAXG / Gold)")
    print("=" * 70 + "\n")

    client = DeltaExchangeClient()
    telegram = TelegramNotifier()

    # Diagnostics
    conn = client.test_connection()
    if not conn.get("public_api_connected"):
        logger.error(f"Cannot connect to Delta Exchange: {conn.get('message')}")
        sys.exit(1)

    print(f"✅ Delta Exchange API: Connected ({conn.get('environment')})")
    
    tg_status = telegram.test_connection()
    if tg_status.get("success"):
        print(f"✅ Telegram Alerts: Connected ({tg_status.get('bot_username')})")
    else:
        print(f"⚠️ Telegram Alerts: {tg_status.get('error')}")
        print("   (Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env to receive push notifications)\n")

    orchestrator = MultiAgentTradingOrchestrator(
        client=client,
        symbols=symbols_list,
        interactive=args.interactive
    )

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[Cycle #{cycle_count} · {now_str}] Running Multi-Agent Scan...")
            
            try:
                cycle_result = orchestrator.run_trading_cycle()
                executed = cycle_result.get("executed_trades_count", 0)
                if executed > 0:
                    print(f"\n🎉 [Cycle #{cycle_count}] Executed {executed} trade(s) successfully!")
            except Exception as e:
                logger.error(f"Error during scan cycle #{cycle_count}: {e}", exc_info=True)

            print(f"⏳ Sleeping {args.interval}s until next scan cycle... (Press Ctrl+C to halt)")
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n🛑 24/7 Multi-Agent Scanner safely halted by user.")


if __name__ == "__main__":
    main()

