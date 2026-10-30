#!/usr/bin/env python3
"""
Delta Exchange Multi-Agent Trading System & MCP Server CLI.
Provides unified entry points for:
  - Starting the Model Context Protocol (MCP) server
  - Running API connectivity & credentials diagnostics
  - Launching the Multi-Agent Trading Team (Interactive or Autonomous)
  - Inspecting trade journal performance digests
"""

import sys
import os
import argparse
import json

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.delta_client import DeltaExchangeClient
from src.delta_mcp_server import main as run_mcp_server
from multiagent_team.orchestrator import MultiAgentTradingOrchestrator
from multiagent_team.portfolio_monitor import PortfolioMonitorAgent


def print_banner():
    banner = """
  ===================================================================
   DELTA EXCHANGE MULTI-AGENT TRADING TEAM & MCP SERVER
   Inspired by claude-trading-skills & Antigravity Architecture
  ===================================================================
    """
    print(banner)


def cmd_test_connection():
    print_banner()
    print("Testing connection to Delta Exchange...")
    client = DeltaExchangeClient()
    res = client.test_connection()
    print("\nConnection Results:")
    print("-" * 50)
    print(f"  Target Environment : {res.get('environment')}")
    print(f"  Base URL           : {res.get('base_url')}")
    print(f"  Public API Status  : {'[CONNECTED]' if res.get('public_api_connected') else '[FAILED]'}")
    print(f"  Authenticated Status: {'[SUCCESS]' if res.get('authenticated') else '[NOT AUTHENTICATED]'}")
    print(f"  Details            : {res.get('message')}")

    if res.get("account_balances"):
        print("\n  Live Account Balances:")
        for b in res.get("account_balances", []):
            print(f"   • {b.get('asset_symbol')}: Balance = {b.get('balance')} (Available: {b.get('available_balance')})")
    print("-" * 50)


def cmd_run_mcp():
    run_mcp_server()


def cmd_scan_market(symbols=None):
    print_banner()
    client = DeltaExchangeClient()
    orchestrator = MultiAgentTradingOrchestrator(client=client, symbols=symbols, interactive=True)
    orchestrator.run_trading_cycle()


def cmd_trade_interactive(symbols=None, leverage=5):
    print_banner()
    client = DeltaExchangeClient()
    orchestrator = MultiAgentTradingOrchestrator(client=client, symbols=symbols, interactive=True, leverage=leverage)
    orchestrator.run_trading_cycle()


def cmd_trade_auto(symbols=None, interval=300, leverage=5):
    print_banner()
    client = DeltaExchangeClient()
    orchestrator = MultiAgentTradingOrchestrator(client=client, symbols=symbols, interactive=False, leverage=leverage)
    orchestrator.run_continuous_loop(interval_seconds=interval)


def cmd_show_digest():
    print_banner()
    client = DeltaExchangeClient()
    monitor = PortfolioMonitorAgent(client)
    digest_text = monitor.generate_daily_digest()
    print(digest_text)


def main():
    parser = argparse.ArgumentParser(
        description="Delta Exchange MCP & Multi-Agent Trading Team",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  mcp       Launch the Model Context Protocol (MCP) server for Claude / Cursor / Antigravity
  test      Test Delta Exchange API connectivity and verify authentication credentials
  scan      Run a one-time multi-agent market scan and setup analysis
  trade     Run multi-agent trading team in Interactive Mode (requires user confirmation)
  auto      Run multi-agent trading team in Autonomous Loop Mode
  digest    Display daily performance journal digest and account summary
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    subparsers.add_parser("mcp", help="Launch the MCP server")
    subparsers.add_parser("test", help="Test API connectivity & credentials")
    
    scan_parser = subparsers.add_parser("scan", help="One-time market scan")
    scan_parser.add_argument("--symbols", type=str, help="Comma-separated symbols (e.g. BTCUSDT,ETHUSDT)")

    trade_parser = subparsers.add_parser("trade", help="Interactive trading mode")
    trade_parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    trade_parser.add_argument("--leverage", type=int, default=5, help="Leverage multiplier (default: 5)")

    auto_parser = subparsers.add_parser("auto", help="Autonomous loop trading mode")
    auto_parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    auto_parser.add_argument("--interval", type=int, default=300, help="Loop interval in seconds (default: 300)")
    auto_parser.add_argument("--leverage", type=int, default=5, help="Leverage multiplier (default: 5)")

    subparsers.add_parser("digest", help="View daily performance digest")

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if getattr(args, "symbols", None) else None

    if args.command == "mcp":
        cmd_run_mcp()
    elif args.command == "test":
        cmd_test_connection()
    elif args.command == "scan":
        cmd_scan_market(symbols=symbols)
    elif args.command == "trade":
        cmd_trade_interactive(symbols=symbols, leverage=args.leverage)
    elif args.command == "auto":
        cmd_trade_auto(symbols=symbols, interval=args.interval, leverage=args.leverage)
    elif args.command == "digest":
        cmd_show_digest()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
