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
from dotenv import load_dotenv

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
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
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

        # Trailing roadmap calculation
        risk_per_unit = abs(entry - sl)
        be_price = round(entry + (risk_per_unit * 0.05) if side == "BUY" else entry - (risk_per_unit * 0.05), 2)
        r2_sl = round(entry + risk_per_unit if side == "BUY" else entry - risk_per_unit, 2)
        r3_tp = round(entry + (3.0 * risk_per_unit) if side == "BUY" else entry - (3.0 * risk_per_unit), 2)
        r5_tp = round(entry + (5.0 * risk_per_unit) if side == "BUY" else entry - (5.0 * risk_per_unit), 2)

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

        proposal_text = (
            f"🎯 <b>[NEW TRADE PROPOSAL — AWAITING YOUR CONFIRMATION]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code>\n"
            f"• <b>Direction:</b> <b>{emoji_dir}</b>\n"
            f"• <b>Strategy:</b> <i>{strategy}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{conf_lines}"
            f"📍 <b>Entry Price:</b> <code>${entry:,.2f}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>${sl:,.2f}</code> (Risk: ${risk_usd:,.2f})\n"
            f"🎯 <b>Target 1 (1:2 R:R):</b> <code>${tp:,.2f}</code> (Initial TP)\n"
            f"⚖️ <b>Initial R:R:</b> <b>{rr:.2f} : 1</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Trailing Stop Roadmap:</b>\n"
            f"  1️⃣ <b>At +1.0R:</b> SL moves to Breakeven (<code>${be_price:,.2f}</code> — Zero Risk)\n"
            f"  2️⃣ <b>At +2.0R:</b> SL locks +1.0R (<code>${r2_sl:,.2f}</code>), TP trails to 1:3 (<code>${r3_tp:,.2f}</code>)\n"
            f"  3️⃣ <b>At +3.0R:</b> SL locks +2.0R, TP trails to 1:5 (<code>${r5_tp:,.2f}</code>)\n"
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

