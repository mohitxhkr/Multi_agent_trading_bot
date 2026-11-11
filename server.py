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
_active_orchestrator = None


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        if self.path in ["/", "/health", "/status", "/ping"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path in ["/", "/health", "/status", "/ping"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

            conn_auth = False
            conn_msg = "Not tested"
            pos_success = False
            active = []
            pos_error = None

            try:
                client = DeltaExchangeClient()
                conn = client.test_connection()
                conn_auth = conn.get("authenticated", False)
                conn_msg = conn.get("message", "")
                
                pos = client.get_positions()
                pos_success = pos.get("success", False)
                if pos_success:
                    raw_pos = pos.get("result", [])
                    active = [p for p in raw_pos if abs(float(p.get("size", 0.0) or 0.0)) > 0]
                else:
                    pos_error = str(pos.get("error"))
            except Exception as e:
                conn_msg = f"Diagnostics error: {str(e)}"
                pos_error = str(e)

            sentiment_data = None
            try:
                sentiment_file = os.path.join(BASE_DIR, "state", "market_sentiment_state.json")
                if os.path.exists(sentiment_file):
                    with open(sentiment_file, "r", encoding="utf-8") as sf:
                        s_raw = json.load(sf)
                        sentiment_data = {
                            "composite_score": s_raw.get("composite_score"),
                            "regime": s_raw.get("sentiment_regime"),
                            "fear_greed_index": s_raw.get("fear_greed_index"),
                            "fear_greed_classification": s_raw.get("fear_greed_classification"),
                            "articles_analyzed": s_raw.get("total_articles_analyzed"),
                            "posture_recommendation": s_raw.get("trading_posture_recommendation", "").split(":")[0]
                        }
            except Exception:
                pass

            response_data = {
                "bot": "Delta Exchange Multi-Agent 24/7 Trading Bot",
                "version": "2.0.0-institutional",
                "architecture": "6-Layer 11-Agent System",
                "status": scanner_status["status"],
                "cycles_completed": scanner_status["cycle_count"],
                "last_scan": scanner_status["last_scan_time"],
                "uptime_started": scanner_status["uptime_started"],
                "authenticated": conn_auth,
                "auth_message": conn_msg,
                "news_sentiment": sentiment_data,
                "positions_success": pos_success,
                "active_positions_count": len(active),
                "active_symbols": [p.get("product_symbol") or p.get("symbol") for p in active],
                "positions_error": pos_error
            }
            self.wfile.write(json.dumps(response_data, indent=2).encode("utf-8"))
        elif self.path == "/trigger-morning-news":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            ok = False
            try:
                if _active_orchestrator:
                    ok = _active_orchestrator.check_and_dispatch_daily_morning_briefing(force=True)
            except Exception as ex:
                logger.error(f"/trigger-morning-news error: {ex}")
            self.wfile.write(json.dumps({"triggered": True, "dispatched": bool(ok)}).encode("utf-8"))
        elif self.path == "/trigger-levels":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            ok = False
            try:
                if _active_orchestrator:
                    ok = _active_orchestrator.check_and_dispatch_daily_market_levels(force=True)
            except Exception as ex:
                logger.error(f"/trigger-levels error: {ex}")
            self.wfile.write(json.dumps({"triggered": True, "dispatched": bool(ok)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence routine healthcheck logs to keep console clean
        return


def run_telegram_command_listener(orchestrator):
    """
    Dedicated background listener thread that polls and responds to Telegram
    slash commands (/chart, /levels, /news, /scan, /status, /positions, etc.)
    instantaneously without waiting for 24/7 market analysis cycles or confirmation windows.
    """
    logger.info("Dedicated Telegram command listener thread active (polling every 1.0s).")
    while True:
        try:
            orchestrator.telegram_bot.process_incoming_commands(orchestrator)
        except Exception as e:
            logger.error(f"Telegram command listener loop error: {e}")
        time.sleep(1.0)


def _check_scheduled_broadcasts(orchestrator):
    """Check and dispatch Daily Morning News (10:00 AM IST + catch-up) and Daily Key Levels Radar."""
    try:
        orchestrator.check_and_dispatch_daily_morning_briefing()
    except Exception as me:
        logger.warning(f"Scheduled morning news check error: {me}")
    try:
        orchestrator.check_and_dispatch_daily_market_levels()
    except Exception as ke:
        logger.warning(f"Scheduled key levels check error: {ke}")


def run_scanner_loop():
    """Background scanner thread that runs the 24/7 multi-agent trading loop."""
    global _active_orchestrator
    time.sleep(3)  # Wait for server to bind port
    client = DeltaExchangeClient()
    telegram = TelegramNotifier()
    orchestrator = MultiAgentTradingOrchestrator(client=client, interactive=False)
    _active_orchestrator = orchestrator

    # Start dedicated Telegram command listener thread so slash commands (/chart, /status, etc.)
    # are handled instantaneously even while trading cycles or order proposals are active.
    tg_thread = threading.Thread(target=run_telegram_command_listener, args=(orchestrator,), daemon=True)
    tg_thread.start()

    interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "120"))
    scanner_status["status"] = "ACTIVE_SCANNING"
    logger.info(f"24/7 Scanner thread active. Scan cadence: every {interval}s.")

    # Send startup confirmation to Telegram
    startup_msg = (
        "🤖 <b>[DELTA MULTI-AGENT BOT ONLINE & 24/7 SCANNING]</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "• <b>Status:</b> 🟢 <b>RUNNING ON CLOUD</b>\n"
        "• <b>Primary Focus:</b> 🌟 <b>BTC, ETH, XAU (Gold)</b>\n"
        "• <b>2-Way Confirmation:</b> ✅ <b>STRICTLY REQUIRED</b>\n"
        "  <i>(Zero trades will execute without your Telegram click)</i>\n"
        "• <b>Trailing Stop Loss:</b> 🛡️ <b>ACTIVE (10s Loop)</b>\n"
        "  <i>(1:1 -> Breakeven, 1:2 -> Lock +1R & trail to 1:3, 1:5)</i>\n"
        "• <b>Interactive Commands Active:</b>\n"
        "  Type <code>/trade</code>, <code>/levels</code>, <code>/chart</code>, <code>/news</code>, <code>/status</code>, <code>/positions</code> anytime!\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <i>Actively scanning charts 24/7. Capital is protected.</i>"
    )
    telegram.send_message(startup_msg)

    # Immediately verify scheduled daily news / levels broadcasts on startup
    _check_scheduled_broadcasts(orchestrator)

    logger.info("Silent 24/7 background scanner engaged. Push notifications sent ONLY on trade proposals & execution exits.")

    while True:
        try:
            scanner_status["cycle_count"] += 1
            scanner_status["last_scan_time"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

            # Runs market cycle: only alerts Telegram when a qualified setup (score >= 75) is found!
            result = orchestrator.run_trading_cycle()
            scanner_status["last_result"] = result
        except Exception as e:
            logger.error(f"Scanner exception: {e}", exc_info=True)

        # Monitor trailing stops (10s) & scheduled news/levels broadcasts (30s)
        elapsed = 0
        trailing_tick = 0
        broadcast_tick = 0
        while elapsed < interval:
            time.sleep(2)
            elapsed += 2
            trailing_tick += 2
            broadcast_tick += 2
            try:
                if trailing_tick >= 10:
                    orchestrator.trailing_stop_manager.check_and_update_trailing_stops()
                    trailing_tick = 0
                if broadcast_tick >= 30:
                    _check_scheduled_broadcasts(orchestrator)
                    broadcast_tick = 0
            except Exception as e:
                logger.error(f"Background tick error: {e}")


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

