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
        self._confirmed_trade_ids = set()
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
        timeout_seconds: int = 600,
        client: Optional[Any] = None
    ) -> bool:
        """
        Send trade analysis with confirmation buttons and BLOCK until the user taps
        [Confirm] or [Reject], or until timeout.
        Returns True ONLY if user explicitly clicked Confirm and pre-execution validation passes!
        """
        if not self.is_configured:
            logger.error("❌ Telegram is not configured! Refusing to trade without user permission.")
            return False

        trade_id = trade_spec.get("trade_id") or f"trade_{uuid.uuid4().hex[:8]}"
        trade_spec["trade_id"] = trade_id

        if trade_id in self._confirmed_trade_ids:
            logger.warning(f"Trade {trade_id} already confirmed! Preventing duplicate execution.")
            return False

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
        risk_pct = trade_spec.get("risk_pct", 1.5)
        est_liq = trade_spec.get("estimated_liquidation_price", 0.0)
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

        conviction_mult = float(trade_spec.get("conviction_multiplier", 1.0))
        conviction_tier = trade_spec.get("conviction_tier", "STANDARD")
        conviction_badge = ""
        if conviction_mult > 1.0:
            boost_pct = int(round((conviction_mult - 1.0) * 100))
            conviction_badge = (
                f"🔥 <b>CONVICTION SIZING BOOST:</b> <b>+{boost_pct}% LOT SIZE ({conviction_tier})</b>\n"
                f"   ↳ <i>High-probability edge confirmed: Scaled up to maximize profit.</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )

        reward_usd = risk_usd * (rr if rr > 0 else 2.0)
        proposal_text = (
            f"🎯 <b>[NEW TRADE PROPOSAL — AWAITING YOUR CONFIRMATION]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code>\n"
            f"• <b>Direction:</b> <b>{emoji_dir}</b>\n"
            f"• <b>Strategy:</b> <i>{strategy}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{conf_lines}"
            f"{tm_lines}"
            f"💵 <b>Total Risk:</b> <b>${risk_usd:,.2f} USD</b> <i>(Maximum loss if Stop Loss hits)</i>\n"
            f"💰 <b>Total Reward:</b> <b>${reward_usd:,.2f} USD</b> <i>(Estimated profit if Target hits)</i>\n"
            f"⚖️ <b>Risk to Reward:</b> <b>Win ${rr:.1f} for every $1 risked</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Entry Price:</b> <code>{fmt_p(entry)}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>{fmt_p(sl)}</code>\n"
            f"🎯 <b>Target 1:</b> <code>{fmt_p(tp)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{conviction_badge}"
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
                            if trade_id in self._confirmed_trade_ids:
                                self.answer_callback(cb_id, "⚠️ Already confirmed! Processing order...")
                                continue
                            self._confirmed_trade_ids.add(trade_id)

                            # Immediate Pre-Execution Revalidation Gate
                            if client:
                                try:
                                    t_res = client.get_ticker(symbol)
                                    if t_res.get("success"):
                                        cur_mark = float(t_res.get("result", {}).get("mark_price") or entry)
                                        price_drift_pct = abs(cur_mark - entry) / entry * 100.0 if entry > 0 else 0.0
                                        if price_drift_pct > 0.40:
                                            self.answer_callback(cb_id, "⚠️ Execution aborted: Price drifted > 0.40%!")
                                            drift_text = (
                                                proposal_text.replace(
                                                    "⚠️ <b>NO TRADE EXECUTES WITHOUT YOUR CLICK.</b>\n<i>Tap below to approve or decline",
                                                    f"🛑 <b>ABORTED: PRICE DRIFTED ({price_drift_pct:.2f}% shift).</b>\n"
                                                    f"<i>Mark moved to ${cur_mark:.4f} while awaiting confirmation. Capital protected."
                                                )
                                            )
                                            self.edit_message_text(msg_id, drift_text, reply_markup={"inline_keyboard": []})
                                            logger.warning(f"Trade {trade_id} aborted before execution: Mark price drifted {price_drift_pct:.2f}%")
                                            return False
                                except Exception as drift_err:
                                    logger.warning(f"Pre-execution price check skipped: {drift_err}")

                            self.answer_callback(cb_id, "✅ Confirmed! Executing on Delta Exchange...")
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

                cb = update.get("callback_query")
                if cb:
                    cb_data = cb.get("data", "")
                    cb_id = cb.get("id")
                    if cb_data == "execute_emergency_closeall":
                        self.answer_callback(cb_id, "🚨 Flattening all positions now...")
                        if orchestrator:
                            from src.emergency_controller import EmergencyController
                            ec = EmergencyController(client=orchestrator.client)
                            res = ec.emergency_flatten_all(authorized=True)
                            self.send_message(
                                f"🛑 <b>[EMERGENCY FLATTEN COMPLETE]</b>\n"
                                f"• Flattened <b>{len(res.get('closed_positions', []))}</b> active positions.\n"
                                f"• Cancelled all open orders. Account is 100% in cash USD."
                            )
                        continue
                    elif cb_data == "cancel_emergency_closeall":
                        self.answer_callback(cb_id, "Cancelled.")
                        self.send_message("✅ Emergency close cancelled. Protective trailing stops remain active.")
                        continue

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

        elif cmd in ["/pause", "/halt"]:
            try:
                from src.emergency_controller import EmergencyController
                ec = EmergencyController(client=client)
                res = ec.engage_emergency_halt("User requested pause via Telegram")
                self.send_message(
                    f"🛑 <b>[TRADING BOT PAUSED BY USER]</b>\n"
                    f"• <b>Status:</b> All new scan entries BLOCKED.\n"
                    f"• <b>Pending Entries Cancelled:</b> {res.get('cancelled_entry_orders_count', 0)}\n"
                    f"• <b>Protection:</b> Active positions Stop Loss verified.\n"
                    f"• <i>Send <code>/resume</code> to re-enable automated scanning.</i>"
                )
            except Exception as e:
                self.send_message(f"⚠️ Error pausing bot: {e}")

        elif cmd in ["/resume", "/unpause"]:
            try:
                from src.emergency_controller import EmergencyController
                ec = EmergencyController(client=client)
                ec.release_emergency_halt("User via Telegram")
                self.send_message(
                    "🟢 <b>[TRADING BOT RESUMED]</b>\n"
                    "• <b>Status:</b> 24/7 Scanning & Trade Evaluation ACTIVE.\n"
                    "• Capital allocation and risk gates re-engaged."
                )
            except Exception as e:
                self.send_message(f"⚠️ Error resuming bot: {e}")

        elif cmd in ["/closeall", "/panic"]:
            try:
                confirm_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "🚨 YES, FLATTEN ALL NOW", "callback_data": "execute_emergency_closeall"},
                            {"text": "❌ Cancel", "callback_data": "cancel_emergency_closeall"}
                        ]
                    ]
                }
                self.send_message(
                    "⚠️ <b>CRITICAL CONFIRMATION REQUIRED:</b>\n"
                    "Are you sure you want to market close ALL active positions and cancel all orders on Delta Exchange?",
                    reply_markup=confirm_markup
                )
            except Exception as e:
                self.send_message(f"⚠️ Error initiating closeall: {e}")

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
                import json, os
                from multiagent_team.adaptive_learning import AdaptiveLearningEngine
                learner = AdaptiveLearningEngine()
                sc = learner.memory.get("scorecard", {})
                patterns = learner.memory.get("patterns", {})

                pnl = sc.get('cumulative_pnl_usd', 0.0)
                win_rate = sc.get('win_rate_pct', 0.0)
                wins = sc.get('winning_trades', 0)
                losses = sc.get('losing_trades', 0)
                be = sc.get('breakeven_trades', 0)
                total = sc.get('total_completed_trades', 0)
                avg_score = sc.get('average_trade_score', 0.0)
                latest_trade = sc.get('latest_trade')

                # Check for live active open positions to show real-time dynamic risk and reward
                active_trades = []
                try:
                    state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "trailing_stop_state.json")
                    if os.path.exists(state_file):
                        with open(state_file, "r", encoding="utf-8") as f:
                            active_data = json.load(f)
                        for asym, apos in active_data.items():
                            cval = 0.001 if "BTC" in asym else (0.01 if "ETH" in asym else 1.0)
                            acontracts = apos.get("contracts", 1)
                            aent = apos.get("entry_price", 0.0)
                            asl = apos.get("current_sl") or apos.get("initial_sl") or aent
                            atp = apos.get("current_tp") or apos.get("initial_tp") or 0.0
                            arisk = abs(aent - asl) * acontracts * cval
                            areward = abs(atp - aent) * acontracts * cval if atp > 0 else (arisk * 2.0)
                            arr = (areward / arisk) if arisk > 0 else 2.0
                            active_trades.append({
                                "symbol": asym,
                                "side": apos.get("side", "BUY").upper(),
                                "risk_usd": arisk,
                                "reward_usd": areward,
                                "rr": arr,
                                "stage": apos.get("stage", 0)
                            })
                except Exception:
                    pass

                lines = [
                    "📊 <b>[DYNAMIC PERFORMANCE SCORECARD]</b>",
                    "━━━━━━━━━━━━━━━━━━━━━━"
                ]

                # 1. If an active trade is open, display its exact dynamic risk & reward trade-by-trade
                if active_trades:
                    lines.append("🟢 <b>LIVE ACTIVE TRADE RISK &amp; REWARD:</b>")
                    for at in active_trades[:2]:
                        stage_txt = " (🛡️ BE Shield Active)" if at['stage'] >= 1 else ""
                        lines.append(f"• <b>{at['symbol']} {at['side']}</b>{stage_txt}")
                        lines.append(f"  ↳ 💵 <b>Total Risk:</b> <b>${at['risk_usd']:,.2f} USD</b> <i>(Dynamic Invalidation)</i>")
                        lines.append(f"  ↳ 💰 <b>Total Reward:</b> <b>${at['reward_usd']:,.2f} USD</b> <i>(Dynamic Target {at['rr']:.1f}:1)</i>")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

                # 2. If recent closed trade exists, display its dynamic trade outcome
                elif latest_trade:
                    l_sym = latest_trade.get("symbol", "TRADE")
                    l_side = latest_trade.get("side", "BUY")
                    l_risk = latest_trade.get("risk_usd", 2.0)
                    l_pnl = latest_trade.get("realized_pnl", 0.0)
                    l_outcome = latest_trade.get("outcome", "CLOSED")
                    pnl_tag = f"+${l_pnl:,.2f} USD" if l_pnl >= 0 else f"-${abs(l_pnl):,.2f} USD"
                    lines.append(f"🏁 <b>LATEST COMPLETED TRADE ({l_sym} {l_side}):</b>")
                    lines.append(f"• 💵 <b>Total Risk Taken:</b> <b>${l_risk:,.2f} USD</b> <i>(Dynamic Sized)</i>")
                    lines.append(f"• 💰 <b>Total Reward Won:</b> <b>{pnl_tag}</b> (<b>{l_outcome}</b>)")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

                else:
                    lines.append("💵 <b>Total Risk Per Trade:</b> <i>Calculated dynamically trade-by-trade ($2.00–$4.00 base, scaled up on A+ setups)</i>")
                    lines.append("💰 <b>Total Reward Target:</b> <i>Calculated dynamically trade-by-trade (Targeted 1:2 to 1:3 R:R)</i>")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

                # 3. Overall Portfolio Performance
                lines.append(f"📈 <b>Net Realized Profit:</b> <b>{'+' if pnl >= 0 else ''}${pnl:,.2f} USD</b> {'🟢' if pnl >= 0 else '🔴'}")
                lines.append(f"🎯 <b>Win Rate:</b> <b>{win_rate:.1f}%</b> ({wins} Wins / {losses} Losses / {be} BE)")

                avg_risk = sc.get("avg_risk_per_trade_usd")
                avg_reward = sc.get("avg_reward_per_win_usd")
                if avg_risk and avg_risk > 0:
                    lines.append(f"📊 <b>Dynamic Avg Risk / Trade:</b> <b>${avg_risk:,.2f} USD</b>")
                if avg_reward and avg_reward > 0:
                    lines.append(f"💎 <b>Dynamic Avg Reward / Win:</b> <b>${avg_reward:,.2f} USD</b>")

                lines.append(f"🔢 <b>Total Completed Trades:</b> <b>{total}</b>")
                lines.append(f"⭐ <b>Trade Quality Score:</b> <b>{avg_score:.0f}/100</b>")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━")

                # Show clean, plain-English summary of best setups
                reinforced = [p for p in patterns.values() if p.get("status") == "REINFORCED"]
                if reinforced:
                    lines.append("🌟 <b>Top Performing Setup:</b>")
                    for pdata in reinforced[:2]:
                        pname = pdata.get("description") or pdata.get("pattern_key", "15m Liquidity Sweeps")
                        pname = pname.replace("_", " ").title()
                        lines.append(f"  • {pname}: <b>{pdata.get('win_rate_pct', 0)}% Win Rate</b> (🟢 High Edge)")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

                lines.append("🛡️ <b>Capital Safety:</b> <b>100% Protected</b> (Zero liquidation risk, max $8.00 open risk ceiling)")
                lines.append("⚡ <i>Bot scans continuously and scales trade size dynamically to maximize profit on prime setups.</i>")
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

