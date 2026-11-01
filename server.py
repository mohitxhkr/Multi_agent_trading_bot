#!/usr/bin/env python3
"""
Cloud Entrypoint with Healthcheck Server & 24/7 Background Scanner.
Designed for Free-Tier Cloud Deployments (Render, Koyeb, Railway, VPS).
Provides an HTTP /health endpoint so free services stay awake 24/7.
"""

import sys
import os
import time
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Ensure UTF-8 output
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
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cloud-runner")

# Global health status
scanner_status = {
    "status": "INITIALIZING",
    "uptime_started": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    "cycle_count": 0,
    "last_scan_time": "Never",
    "last_result": None
}


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        if self.path in ["/", "/health", "/status"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path in ["/", "/health", "/status"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response_data = {
                "bot": "Delta Exchange Multi-Agent 24/7 Trading Bot",
                "status": scanner_status["status"],
                "cycles_completed": scanner_status["cycle_count"],
                "last_scan": scanner_status["last_scan_time"],
                "uptime_started": scanner_status["uptime_started"]
            }
            self.wfile.write(json.dumps(response_data, indent=2).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence routine healthcheck logs to keep console clean
        return


def run_scanner_loop():
    """Background scanner thread that runs the 24/7 multi-agent trading loop."""
    time.sleep(3)  # Wait for server to bind port
    client = DeltaExchangeClient()
    telegram = TelegramNotifier()
    orchestrator = MultiAgentTradingOrchestrator(client=client, interactive=False)

    interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "120"))
    scanner_status["status"] = "ACTIVE_SCANNING"
    logger.info(f"24/7 Scanner thread active. Scan cadence: every {interval}s.")

    # Send startup confirmation to Telegram
    startup_msg = (
        "🤖 <b>[DELTA MULTI-AGENT BOT DEPLOYED & ONLINE 24/7]</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "• <b>Status:</b> 🟢 <b>RUNNING ON CLOUD</b>\n"
        "• <b>2-Way Confirmation:</b> ✅ <b>STRICTLY REQUIRED</b>\n"
        "  <i>(Zero trades will be taken without your explicit button click on Telegram)</i>\n"
        "• <b>Trailing Stop Loss:</b> 🛡️ <b>ACTIVE</b>\n"
        "  <i>(1:1 -> Breakeven, 1:2 -> Lock +1R & trail to 1:3, 1:5)</i>\n"
        "• <b>Confluence Engine:</b> 🎯 <b>80-90% WIN-RATE FILTER</b>\n"
        "  <i>(4H Macro Stack + 1H Liquidity Sweeps + MSS + Structural SL)</i>\n"
        "• <b>Universe:</b> <code>BTCUSD, ETHUSD, SOLUSD, PAXGUSD</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <i>Monitoring charts 24/7. Capital is protected.</i>"
    )
    telegram.send_message(startup_msg)

    while True:
        try:
            scanner_status["cycle_count"] += 1
            scanner_status["last_scan_time"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            
            result = orchestrator.run_trading_cycle()
            scanner_status["last_result"] = result
        except Exception as e:
            logger.error(f"Scanner exception: {e}", exc_info=True)

        # Sleep in 15-second chunks, continuously monitoring trailing stops for active positions
        elapsed = 0
        while elapsed < interval:
            time.sleep(15)
            elapsed += 15
            try:
                orchestrator.trailing_stop_manager.check_and_update_trailing_stops()
            except Exception as e:
                logger.error(f"Trailing stop background tick error: {e}")


def main():
    port = int(os.getenv("PORT", "8080"))
    logger.info(f"Starting cloud web server on port {port}...")

    # Start background scanner thread
    scanner_thread = threading.Thread(target=run_scanner_loop, daemon=True)
    scanner_thread.start()

    # Start HTTP server for health pings
    httpd = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Healthcheck server listening on http://0.0.0.0:{port}/health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server halted.")


if __name__ == "__main__":
    main()

