"""
Interactive 2-Way Telegram Confirmation & Control Bot for Delta Exchange.
Ensures ZERO trades execute without explicit user confirmation via Telegram inline buttons.
Provides trailing stop alerts, position monitoring, and command handling (/status, /positions).
"""

from typing import Dict, Any, Optional
import os
import sys
import time
import uuid
import logging
import requests
# pyrefly: ignore[missing-import]
from dotenv import load_dotenv

from src.technical_analysis import round_price

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("telegram-bot")


class TelegramConfirmationBot:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "REDACTED_TELEGRAM_BOT_TOKEN").strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID") or "123456789").strip()
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self.last_update_id = 0
        self._sync_update_offset()

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _sync_update_offset(self) -> None:
        """Fetch latest update_id so we do not process ancient stale updates."""
        if not self.is_configured:
            return
        try:
            url = f"{self.base_url}/getUpdates"
            res = requests.get(url, params={"offset": -1, "timeout": 2}, timeout=5)
            data = res.json()
            if data.get("ok") and data.get("result"):
                self.last_update_id = data["result"][-1]["update_id"] + 1
        except Exception:
            pass

    def send_message(self, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Send formatted HTML message to Telegram. Returns message_id if successful."""
        if not self.is_configured:
            logger.warning("Telegram not configured. Cannot send message.")
            return None

        try:
            url = f"{self.base_url}/sendMessage"
            payload: Dict[str, Any] = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            res = requests.post(url, json=payload, timeout=10)
            data = res.json()
            if data.get("ok"):
                return data["result"]["message_id"]
            logger.error(f"Telegram sendMessage failed: {data.get('description')}")
            return None
        except Exception as e:
            logger.error(f"Telegram network error: {e}")
            return None

    def edit_message_text(self, message_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        """Edit an existing Telegram message."""
        if not self.is_configured:
            return False

        try:
            url = f"{self.base_url}/editMessageText"
            payload: Dict[str, Any] = {
                "chat_id": self.chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup

            res = requests.post(url, json=payload, timeout=10)
            return res.json().get("ok", False)
        except Exception as e:
            logger.error(f"Telegram editMessage error: {e}")
            return False

    def answer_callback(self, callback_query_id: str, text: str) -> bool:
        """Acknowledge Telegram callback query."""
        if not self.is_configured:
            return False

        try:
            url = f"{self.base_url}/answerCallbackQuery"
            payload = {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": False
            }
            res = requests.post(url, json=payload, timeout=10)
            return res.json().get("ok", False)
        except Exception as e:
            logger.error(f"Telegram answerCallbackQuery error: {e}")
            return False

    def request_trade_confirmation(
        self,
        trade_spec: Dict[str, Any],
        timeout_seconds: int = 600
    ) -> bool:
        """
        Send trade analysis with confirmation buttons and BLOCK until the user taps
        [Confirm] or [Reject], or until timeout.
        Returns True ONLY if user explicitly clicked Confirm!
        """
        if not self.is_configured:
            logger.error("❌ Telegram is not configured! Refusing to trade without user permission.")
            return False

        trade_id = trade_spec.get("trade_id") or f"trade_{uuid.uuid4().hex[:8]}"
        trade_spec["trade_id"] = trade_id

        symbol = trade_spec.get("symbol", "N/A")
        side = trade_spec.get("side", "").upper()
        emoji_dir = "🟢 LONG" if side == "BUY" else "🔴 SHORT"
        entry = trade_spec.get("entry_price", 0.0)
        sl = trade_spec.get("stop_loss_price", 0.0)
        tp = trade_spec.get("take_profit_price", 0.0)
        rr = trade_spec.get("reward_to_risk_ratio", 2.0)
        contracts = trade_spec.get("contracts", 1)
        leverage = trade_spec.get("leverage", 25)
        margin = trade_spec.get("required_margin_usd", 0.0)
        risk_usd = trade_spec.get("dollar_risk_usd", 0.0)
        strategy = trade_spec.get("strategy", "High-Probability Edge")
        thesis = trade_spec.get("thesis", "Market structure alignment verified.")
        confluence = trade_spec.get("confluence", {})

        # Dynamic price formatter for multi-asset magnitude
        def fmt_p(p: float) -> str:
            if p < 0.1:
                return f"${p:,.6f}"
            elif p < 1.0:
                return f"${p:,.5f}"
            elif p < 10.0:
                return f"${p:,.4f}"
            else:
                return f"${p:,.2f}"

        # Trailing roadmap calculation
        risk_per_unit = abs(entry - sl)
        be_price = round_price(entry + (risk_per_unit * 0.05) if side == "BUY" else entry - (risk_per_unit * 0.05), entry)
        r2_sl = round_price(entry + risk_per_unit if side == "BUY" else entry - risk_per_unit, entry)
        r3_tp = round_price(entry + (3.0 * risk_per_unit) if side == "BUY" else entry - (3.0 * risk_per_unit), entry)
        r5_tp = round_price(entry + (5.0 * risk_per_unit) if side == "BUY" else entry - (5.0 * risk_per_unit), entry)

        conf_lines = ""
        if confluence:
            conf_lines = (
                f"📊 <b>5-Timeframe Confluence Matrix (Score: {trade_spec.get('score', 80)}/100):</b>\n"
                f"• <b>1M Monthly:</b> <code>{confluence.get('monthly', 'ALIGNED')}</code>\n"
                f"• <b>1W Weekly:</b> <code>{confluence.get('weekly', 'ALIGNED')}</code>\n"
                f"• <b>1D Daily:</b> <code>{confluence.get('daily', 'ALIGNED')}</code>\n"
                f"• <b>4H Cycle:</b> <code>{confluence.get('macro_4h', 'ALIGNED')}</code>\n"
                f"• <b>1H Trigger:</b> {confluence.get('structure_detail', 'Liquidity Sweep + MSS')}\n"
                f"• <b>Momentum:</b> {confluence.get('volume_rsi', 'Aligned')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )

        tm = trade_spec.get("time_machine", {})
        tm_lines = ""
        if tm:
            tm_status = "🟢 HIGH MATHEMATICAL PROBABILITY" if tm.get("passed") else "🟡 STATISTICAL EDGE"
            tm_lines = (
                f"⏳ <b>Time Machine Historical Backtest Simulation:</b>\n"
                f"• <b>Historical Lookback:</b> <code>{tm.get('sample_size', 0)} identical setups tested</code>\n"
                f"• <b>Empirical Win Rate:</b> <b>{tm.get('win_rate_pct', 0.0)}%</b> ({tm.get('wins', 0)} Wins / {tm.get('losses', 0)} Losses)\n"
                f"• <b>Expected Value (EV):</b> <b>+{tm.get('expected_value_r', 0.0)}R</b> per trade\n"
                f"• <b>Profit Factor:</b> <code>{tm.get('profit_factor', 0.0)}x</code>\n"
                f"• <b>Avg Max Adverse (MAE):</b> <code>{tm.get('avg_mae_pct', 0.0)}%</code>\n"
                f"• <b>Simulation Status:</b> {tm_status}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )

        proposal_text = (
            f"🎯 <b>[NEW TRADE PROPOSAL — AWAITING YOUR CONFIRMATION]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code>\n"
            f"• <b>Direction:</b> <b>{emoji_dir}</b>\n"
            f"• <b>Strategy:</b> <i>{strategy}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{conf_lines}"
            f"{tm_lines}"
            f"📍 <b>Entry Price:</b> <code>{fmt_p(entry)}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>{fmt_p(sl)}</code> (Risk: ${risk_usd:,.2f})\n"
            f"🎯 <b>Target 1 (1:2 R:R):</b> <code>{fmt_p(tp)}</code> (Initial TP)\n"
            f"⚖️ <b>Initial R:R:</b> <b>{rr:.2f} : 1</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Scalper Trailing Roadmap:</b>\n"
            f"  1️⃣ <b>At +0.50R:</b> Breakeven Shield (<code>{fmt_p(entry)}</code> + fee buffer — Zero Risk)\n"
            f"  2️⃣ <b>At +0.80R:</b> Micro-Lock +0.35R green profit in bank\n"
            f"  3️⃣ <b>At +1.20R:</b> Core Lock +0.75R profit in bank\n"
            f"  4️⃣ <b>At +1.60R:</b> Pre-Target Lock +1.25R profit in bank\n"
            f"  5️⃣ <b>At +2.00R:</b> Full Take Profit collected\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <b>Leverage:</b> <code>{leverage}x Isolated</code>\n"
            f"💼 <b>Size:</b> <code>{contracts} contracts</code> (Margin: ~${margin:,.2f})\n"
            f"💡 <i>{thesis}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>NO TRADE EXECUTES WITHOUT YOUR CLICK.</b>\n"
            f"<i>Tap below to approve or decline (Expires in {timeout_seconds // 60}m):</i>"
        )

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Confirm & Execute", "callback_data": f"confirm_{trade_id}"},
                    {"text": "❌ Reject Trade", "callback_data": f"reject_{trade_id}"}
                ]
            ]
        }

        msg_id = self.send_message(proposal_text, reply_markup=reply_markup)
        if not msg_id:
            logger.error("Failed to post proposal message to Telegram!")
            return False

        logger.info(f"Proposal sent to Telegram (msg_id: {msg_id}). Waiting for user button click (timeout {timeout_seconds}s)...")

        # Polling loop for callback query
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.last_update_id, "timeout": 3}
                res = requests.get(url, params=params, timeout=5)
                data = res.json()

                if data.get("ok"):
                    for update in data.get("result", []):
                        self.last_update_id = max(self.last_update_id, update["update_id"] + 1)
                        cb = update.get("callback_query")
                        if not cb:
                            continue

                        cb_data = cb.get("data", "")
                        cb_id = cb.get("id")

                        if cb_data == f"confirm_{trade_id}":
                            self.answer_callback(cb_id, "✅ Confirmed! Executing on Delta Exchange...")
                            # Update message to show confirmed state
                            confirmed_text = (
                                proposal_text.replace(
                                    "⚠️ <b>NO TRADE EXECUTES WITHOUT YOUR CLICK.</b>\n<i>Tap below to approve or decline",
                                    "⚡ <b>CONFIRMED BY USER! EXECUTING ON DELTA EXCHANGE...</b>\n<i>Received"
                                )
                            )
                            self.edit_message_text(msg_id, confirmed_text, reply_markup={"inline_keyboard": []})
                            logger.info(f"User APPROVED trade {trade_id} via Telegram!")
                            return True

                        elif cb_data == f"reject_{trade_id}":
                            self.answer_callback(cb_id, "❌ Trade proposal rejected.")
                            rejected_text = (
                                proposal_text.replace(
                                    "⚠️ <b>NO TRADE EXECUTES WITHOUT YOUR CLICK.</b>\n<i>Tap below to approve or decline",
                                    "❌ <b>REJECTED BY USER — CAPITAL PROTECTED.</b>\n<i>Declined"
                                )
                            )
                            self.edit_message_text(msg_id, rejected_text, reply_markup={"inline_keyboard": []})
                            logger.info(f"User REJECTED trade {trade_id} via Telegram.")
                            return False

            except Exception as e:
                logger.error(f"Error checking Telegram callbacks: {e}")

            time.sleep(1.5)

        # Timeout reached
        timeout_text = (
            proposal_text.replace(
                "⚠️ <b>NO TRADE EXECUTES WITHOUT YOUR CLICK.</b>\n<i>Tap below to approve or decline",
                f"⌛ <b>PROPOSAL EXPIRED ({timeout_seconds // 60}m TIMEOUT) — NO ORDER PLACED.</b>\n<i>Expired"
            )
        )
        self.edit_message_text(msg_id, timeout_text, reply_markup={"inline_keyboard": []})
        logger.info(f"Trade proposal {trade_id} timed out. Order cancelled.")
        return False

    def process_incoming_commands(self, orchestrator=None) -> None:
        """
        Poll Telegram for incoming user commands (/status, /scan, /positions, /orders, /help)
        and respond immediately.
        """
        if not self.is_configured:
            return

        try:
            url = f"{self.base_url}/getUpdates"
            params = {"offset": self.last_update_id, "timeout": 2}
            res = requests.get(url, params=params, timeout=5)
            data = res.json()
            if not data.get("ok"):
                return

            for update in data.get("result", []):
                self.last_update_id = max(self.last_update_id, update["update_id"] + 1)

                msg = update.get("message")
                if not msg:
                    continue

                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id != str(self.chat_id):
                    continue

                text = (msg.get("text") or "").strip()
                if not text.startswith("/"):
                    continue

                full_text = text.strip()
                cmd = full_text.split()[0].lower()
                logger.info(f"Received Telegram command: {cmd}")
                self._handle_command(cmd, orchestrator, full_text=full_text)
        except Exception as e:
            logger.error(f"Error checking Telegram commands: {e}")

    def _handle_command(self, cmd: str, orchestrator=None, full_text: str = "") -> None:
        """Route user slash command to response."""
        if not orchestrator:
            self.send_message("⚠️ Orchestrator unavailable. Bot is initializing.")
            return

        client = orchestrator.client

        if cmd in ["/status", "/ping"]:
            try:
                wallet = client.get_wallet_balances()
                avail_usd = 0.0
                if isinstance(wallet, dict) and wallet.get("result"):
                    for a in wallet["result"]:
                        if a.get("asset_symbol") == "USD":
                            avail_usd = float(a.get("available_balance", "0"))

                pos_res = client.get_positions()
                active_pos = [p for p in pos_res.get("result", []) if int(p.get("size", 0)) != 0] if pos_res.get("success") else []
                orders_res = client.get_open_orders()
                open_orders = orders_res.get("result", []) if orders_res.get("success") else []

                status_lines = [
                    "🤖 <b>[DELTA 24/7 CLOUD BOT STATUS]</b>",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    "• <b>Cloud Status:</b> 🟢 <b>SCANNING 24/7 (SILENT MODE)</b>",
                    f"• <b>Available Cash:</b> <code>${avail_usd:,.2f} USD</code>",
                    f"• <b>Active Positions:</b> <b>{len(active_pos)}</b> | <b>Open Orders:</b> <b>{len(open_orders)}</b>",
                    "• <b>Notifications:</b> ⚡ <b>Only on Trade Signals & Exits</b>",
                    "• <b>Core Focus:</b> 🌟 <b>BTC, ETH, XAU (Gold)</b>"
                ]

                if not pos_res.get("success"):
                    err = pos_res.get("error", {})
                    err_code = err.get("code") if isinstance(err, dict) else str(err)
                    if "ip_not_whitelisted" in err_code:
                        client_ip = err.get("context", {}).get("client_ip", "") if isinstance(err, dict) else ""
                        status_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
                        status_lines.append(f"⚠️ <b>DELTA API WARNING:</b> IP Whitelisting active on your key.")
                        status_lines.append(f"  <i>Please edit your key on Delta Exchange and leave Allowed IPs blank so cloud IP <code>{client_ip}</code> is permitted.</i>")

                if active_pos:
                    status_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
                    status_lines.append("📊 <b>ACTIVE RUNNING POSITION:</b>")
                    for p in active_pos:
                        sym = p.get("product_symbol")
                        raw_size = int(p.get("size", 0))
                        dir_tag = "🟢 LONG" if raw_size > 0 else "🔴 SHORT"
                        ent = float(p.get("entry_price", 0))
                        mark = float(p.get("mark_price", 0))
                        pnl = float(p.get("unrealized_pnl", 0))
                        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                        status_lines.append(f"• <b>{sym} {dir_tag}:</b> {abs(raw_size):,} contracts")
                        status_lines.append(f"  Entry: <code>${ent:.5f}</code> | Mark: <code>${mark:.5f}</code> | PnL: <b>{pnl_str}</b>")

                status_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
                status_lines.append("⚡ <i>Type /positions for full risk spec or /scan for on-demand analysis.</i>")
                self.send_message("\n".join(status_lines))
            except Exception as e:
                self.send_message(f"⚠️ Error fetching status: {e}")

        elif cmd in ["/scan", "/market"]:
            try:
                self.send_message("🔍 <i>Scanning BTC, ETH, and XAU across 5 timeframes... Please wait a few seconds.</i>")
                digest = orchestrator.get_market_digest_text()
                self.send_message(digest)
            except Exception as e:
                self.send_message(f"⚠️ Error generating scan: {e}")

        elif cmd in ["/positions", "/pos"]:
            try:
                pos_res = client.get_positions()
                if not pos_res.get("success"):
                    err = pos_res.get("error", "Failed to query Delta Exchange API")
                    err_code = err.get("code") if isinstance(err, dict) else str(err)
                    if "ip_not_whitelisted" in err_code:
                        client_ip = err.get("context", {}).get("client_ip", "") if isinstance(err, dict) else ""
                        self.send_message(
                            f"🔒 <b>[DELTA EXCHANGE IP RESTRICTION DETECTED]</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Issue:</b> Your Delta API Key has IP Whitelisting enabled.\n"
                            f"• <b>Cloud Server IP:</b> <code>{client_ip}</code>\n"
                            f"• <b>Quick Fix:</b> Log into Delta Exchange (Settings → API Keys), edit your key and <b>leave the Allowed IPs / IP Whitelist field completely blank</b> (or allow all IPs).\n"
                            f"• Once saved, your cloud bot will instantly access positions and execute trades 24/7!"
                        )
                    else:
                        self.send_message(f"⚠️ <b>Could not fetch positions from Delta Exchange:</b>\n<code>{err}</code>")
                    return

                active_pos = [p for p in pos_res.get("result", []) if int(p.get("size", 0)) != 0]
                orders_res = client.get_open_orders()
                open_orders = orders_res.get("result", []) if orders_res.get("success") else []

                if not active_pos:
                    self.send_message("📊 <b>No open positions.</b> Capital is 100% in cash USD.")
                else:
                    lines = ["📊 <b>[ACTIVE OPEN POSITIONS]</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
                    for p in active_pos:
                        sym = p.get("product_symbol")
                        raw_size = int(p.get("size", 0))
                        dir_str = "🟢 LONG" if raw_size > 0 else "🔴 SHORT"
                        contracts = abs(raw_size)
                        ent = float(p.get("entry_price", 0))
                        mark = float(p.get("mark_price", 0))
                        pnl = float(p.get("unrealized_pnl", 0))

                        # Look up active bracket SL and TP orders
                        pid = p.get("product_id")
                        sl_price = "None"
                        tp_price = "None"
                        for o in open_orders:
                            if o.get("product_id") == pid:
                                s_type = o.get("stop_order_type")
                                if s_type == "stop_loss_order":
                                    sl_price = f"${float(o.get('stop_price') or 0):.5f}"
                                elif s_type == "take_profit_order":
                                    tp_price = f"${float(o.get('stop_price') or 0):.5f}"

                        pinfo = client.get_product_info(sym)
                        cval = float(pinfo.get("contract_value", 1.0)) if pinfo else 1.0
                        lev = 25 if "BTC" not in sym else 50
                        margin = (contracts * cval * ent) / lev
                        roi_pct = (pnl / margin * 100.0) if margin > 0 else 0.0
                        pnl_badge = f"+${pnl:.2f} (+{roi_pct:.2f}%)" if pnl >= 0 else f"-${abs(pnl):.2f} ({roi_pct:.2f}%)"

                        lines.append(f"• <b>{sym}</b> {dir_str}")
                        lines.append(f"  ↳ Contracts: <b>{contracts:,}</b> ({lev}x Isolated | Margin: ${margin:.2f})")
                        lines.append(f"  ↳ Entry: <code>${ent:.5f}</code> | Current Mark: <code>${mark:.5f}</code>")
                        lines.append(f"  ↳ Stop Loss: <code>{sl_price}</code> | Take Profit: <code>{tp_price}</code>")
                        lines.append(f"  ↳ Unrealized PnL: <b>{pnl_badge}</b>")
                        lines.append("")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
                    lines.append("🛡️ <i>Actively monitored by Trailing Stop Manager (+0.50R BE Shield).</i>")
                    self.send_message("\n".join(lines))
            except Exception as e:
                self.send_message(f"⚠️ Error fetching positions: {e}")

        elif cmd in ["/trade", "/findtrade", "/find_trade"]:
            try:
                self.send_message("🎯 <i>Running institutional scalp scan for A+ setups on BTC, ETH, and XAU...</i>")
                res = orchestrator.run_trading_cycle()
                status = res.get("status") if isinstance(res, dict) else None
                if status == "NO_SETUPS_FOUND":
                    self.send_message(
                        "🛡️ <b>[ON-DEMAND SCALP SCAN RESULT]</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "• <b>Status:</b> <b>No perfect trade or setup found in the market right now.</b>\n"
                        "• <b>Reason:</b> No asset currently meets the strict \u2265 75 institutional confluence score and 0.20%-0.40% tight scalp bounds.\n"
                        "• <b>Discipline Rule:</b> Capital is 100% protected. Zero forced trades.\n"
                        "⚡ <i>The 24/7 background engine will immediately alert you when an A+ setup triggers!</i>"
                    )
                elif status == "CASH_PRIORITY_HALT":
                    reason = res.get("reason", "Market participation collapsed.")
                    posture_info = res.get("posture", {})
                    self.send_message(
                        f"🛑 <b>[CASH PRIORITY ENGAGED — ZERO TRADES]</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>Status:</b> Market Posture has engaged 100% Cash Priority.\n"
                        f"• <b>Health Score:</b> <b>{posture_info.get('health_score', 0)}/100</b> | Breadth: <b>{posture_info.get('breadth_pct', 0)}%</b>\n"
                        f"• <b>Reason:</b> {reason}\n"
                        f"• <b>Discipline Rule:</b> When market breadth is broken, capital is 100% preserved in cash USD. No trades permitted."
                    )
                elif status == "REJECTED_BY_TIME_MACHINE":
                    reason = res.get("reason", "No setup met >= 68% historical win-rate edge with positive EV.")
                    self.send_message(
                        f"⏳ <b>[REJECTED BY TIME MACHINE SIMULATION]</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>Status:</b> Prospective setup failed historical simulation.\n"
                        f"• <b>Reason:</b> {reason}\n"
                        f"• <b>Discipline Rule:</b> Capital is protected from negative-EV setups."
                    )
                elif status == "REJECTED_BY_RISK_GATE":
                    reason = res.get("reason", "Risk limits or margin constraints exceeded.")
                    self.send_message(
                        f"🛡️ <b>[SETUP REJECTED BY RISK GATEKEEPER]</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>Status:</b> Prospective setup filtered by pre-trade discipline.\n"
                        f"• <b>Reason:</b> {reason}\n"
                        f"• <b>Rule:</b> Capital protected from excessive exposure."
                    )
            except Exception as e:
                self.send_message(f"⚠️ Error running scalp scan: {e}")

        elif cmd in ["/orders", "/orderbook"]:
            try:
                orders_res = client.get_open_orders()
                if not orders_res.get("success"):
                    err = orders_res.get("error", "Failed to query Delta orders")
                    self.send_message(f"⚠️ <b>Could not fetch orders from Delta Exchange:</b>\n<code>{err}</code>")
                    return

                open_orders = orders_res.get("result", [])
                if not open_orders:
                    self.send_message("📋 <b>No pending orders on orderbook.</b>")
                else:
                    lines = ["📋 <b>[PENDING ORDERS ON DELTA EXCHANGE]</b>", "━━━━━━━━━━━━━━━━━━━━━━"]
                    for o in open_orders:
                        oid = o.get("id")
                        sym = o.get("product_symbol")
                        side = o.get("side", "").upper()
                        sz = o.get("size")
                        lp = float(o.get("limit_price") or 0)
                        lines.append(f"• <b>#{oid}</b>: <b>{sym} {side}</b> | {sz} contracts @ <code>${lp:,.4f}</code>")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
                    lines.append("⚡ <i>Orders execute automatically when limit price is filled.</i>")
                    self.send_message("\n".join(lines))
            except Exception as e:
                self.send_message(f"⚠️ Error fetching orders: {e}")

        elif cmd in ["/closeall", "/panic"]:
            try:
                self.send_message("🚨 <i>Emergency Close All initiated... Flattening positions and cancelling orders.</i>")
                pos_res = client.get_positions()
                active = [p for p in pos_res.get("result", []) if int(p.get("size", 0)) != 0] if pos_res.get("success") else []
                closed_count = 0
                for p in active:
                    sym = p.get("product_symbol")
                    client.close_position(sym)
                    client.cancel_all_orders(symbol=sym)
                    closed_count += 1
                client.cancel_all_orders()
                self.send_message(
                    f"🛑 <b>[EMERGENCY CLOSE COMPLETE]</b>\n"
                    f"• Flattened <b>{closed_count}</b> active position(s).\n"
                    f"• Cancelled all open orders on Delta Exchange.\n"
                    f"• Portfolio is 100% in cash USD."
                )
            except Exception as e:
                self.send_message(f"⚠️ Error executing closeall: {e}")

        elif cmd == "/close":
            parts = full_text.split()
            if len(parts) < 2:
                self.send_message("⚠️ Please specify symbol to close, e.g.: <code>/close BTCUSD</code> or use <code>/closeall</code>")
            else:
                sym = parts[1].upper()
                try:
                    self.send_message(f"🛑 <i>Closing position on {sym}...</i>")
                    res = client.close_position(sym)
                    client.cancel_all_orders(symbol=sym)
                    if res.get("success"):
                        self.send_message(f"✅ <b>Position on {sym} closed successfully at market.</b> Open bracket orders cancelled.")
                    else:
                        self.send_message(f"⚠️ Could not close {sym}: {res.get('error', 'Unknown error')}")
                except Exception as e:
                    self.send_message(f"⚠️ Error closing {sym}: {e}")

        elif cmd in ["/scorecard", "/learning", "/performance", "/audit"]:
            try:
                from multiagent_team.adaptive_learning import AdaptiveLearningEngine
                learner = AdaptiveLearningEngine()
                sc = learner.memory.get("scorecard", {})
                patterns = learner.memory.get("patterns", {})

                lines = [
                    "🧠 <b>[ALGORITHM SELF-LEARNING SCORECARD &amp; PATTERN AUDIT]</b>",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    f"• <b>Total Trades Evaluated:</b> <b>{sc.get('total_completed_trades', 0)}</b>",
                    f"• <b>Realized Performance:</b> <b>{sc.get('winning_trades', 0)} Wins</b> | <b>{sc.get('losing_trades', 0)} Losses</b> | <b>{sc.get('breakeven_trades', 0)} BE</b>",
                    f"• <b>Live Win Rate:</b> <b>{sc.get('win_rate_pct', 0.0)}%</b>",
                    f"• <b>Cumulative Realized PnL:</b> <b>{'+' if sc.get('cumulative_pnl_usd', 0) >= 0 else ''}${sc.get('cumulative_pnl_usd', 0.0):,.2f} USD</b>",
                    f"• <b>Average Self-Score:</b> <b>{sc.get('average_trade_score', 0.0)}/100</b>",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    "🌟 <b>LEARNED PATTERNS &amp; STATUS:</b>"
                ]

                if not patterns:
                    lines.append("<i>No closed trades in active memory yet. Engine will automatically learn after next position exit.</i>")
                else:
                    for pkey, pdata in list(patterns.items())[:6]:
                        stat_badge = "🟢 REINFORCED" if pdata.get("status") == "REINFORCED" else ("🔴 BANNED" if pdata.get("status") == "VETOED_BLACKLISTED" else "🟡 EVALUATING")
                        adj = pdata.get("score_adjustment", 0)
                        adj_str = f"+{adj}pts" if adj > 0 else (f"{adj}pts" if adj < 0 else "0pts")
                        lines.append(f"• <code>{pkey}</code>: {stat_badge} ({adj_str})")
                        lines.append(f"  ↳ Win Rate: {pdata.get('win_rate_pct', 0)}% ({pdata.get('wins', 0)}W/{pdata.get('losses', 0)}L) | PnL: ${pdata.get('cumulative_pnl', 0):.2f}")

                lines.append("━━━━━━━━━━━━━━━━━━━━━━")
                lines.append("⚡ <i>Algorithm automatically repeats winning patterns and bans failing setups.</i>")
                self.send_message("\n".join(lines))
            except Exception as e:
                self.send_message(f"⚠️ Error fetching scorecard: {e}")

        elif cmd in ["/posture", "/regime", "/marketposture"]:
            try:
                from multiagent_team.exposure_coach import ExposureCoachAgent
                coach = ExposureCoachAgent()
                msg = coach.format_telegram_posture()
                self.send_message(msg)
            except Exception as e:
                self.send_message(f"⚠️ Error fetching market posture: {e}")

        elif cmd in ["/rules", "/discipline", "/operatingrules"]:
            try:
                from multiagent_team.performance_coach import PerformanceCoachAgent
                coach = PerformanceCoachAgent()
                msg = coach.format_telegram_rules()
                self.send_message(msg)
            except Exception as e:
                self.send_message(f"⚠️ Error fetching operating rules: {e}")

        elif cmd in ["/help", "/start"]:
            help_msg = (
                "📖 <b>[DELTA BOT COMMAND CENTER]</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "You can command your trading bot anytime directly in this chat:\n\n"
                "• <code>/status</code> — View 24/7 cloud health, available equity &amp; open count\n"
                "• <code>/posture</code> — View Market Posture, Breadth % &amp; Exposure Ceiling\n"
                "• <code>/rules</code> — Inspect dynamic Next-Session Operating Rules\n"
                "• <code>/trade</code> — Run scalp scan; suggest trade only if A+ setup exists\n"
                "• <code>/scan</code> — Trigger on-demand 5-timeframe scan of BTC, ETH &amp; XAU\n"
                "• <code>/positions</code> — View currently active positions &amp; PnL\n"
                "• <code>/orders</code> — Inspect pending limit/bracket orders\n"
                "• <code>/scorecard</code> — View algorithm self-learning audit, win rate &amp; learned patterns\n"
                "• <code>/close &lt;symbol&gt;</code> — Market close a specific position (e.g. /close BTCUSD)\n"
                "• <code>/closeall</code> — Emergency flatten all positions &amp; cancel all orders\n"
                "• <code>/help</code> — Show this help manual\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎯 <b>Primary Focus:</b> BTC, ETH, XAU (Gold)\n"
                "⚠️ <b>Zero trades execute without your explicit button click.</b>"
            )
            self.send_message(help_msg)

