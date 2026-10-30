"""
Telegram Notification Engine for Delta Exchange Multi-Agent Trading Bot.
Delivers real-time trade alerts, liquidity sweep notifications, execution receipts,
and portfolio health updates directly to your Telegram chat or channel.
"""

from typing import Dict, Any, Optional
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("telegram-notifier")


class TelegramNotifier:
    """
    Lightweight Telegram bot client using standard HTTP requests.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment or .env.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True
    ):
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.enabled = enabled and bool(self.bot_token and self.chat_id)
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""

        if not self.enabled and not (self.bot_token and self.chat_id):
            logger.info("TelegramNotifier: Disabled (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured).")

    def test_connection(self) -> Dict[str, Any]:
        """Test API connectivity with Telegram getMe endpoint."""
        if not self.bot_token:
            return {"success": False, "error": "TELEGRAM_BOT_TOKEN is not configured in .env"}

        try:
            url = f"{self.base_url}/getMe"
            res = requests.get(url, timeout=10)
            data = res.json()
            if data.get("ok"):
                bot_info = data.get("result", {})
                return {
                    "success": True,
                    "bot_name": bot_info.get("first_name"),
                    "bot_username": f"@{bot_info.get('username')}",
                    "chat_id_configured": bool(self.chat_id)
                }
            return {"success": False, "error": data.get("description", "Unknown Telegram API error")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send formatted text message to the configured Telegram chat."""
        if not self.enabled:
            logger.debug(f"TelegramNotifier (Simulated): {text[:80]}...")
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            res = requests.post(url, json=payload, timeout=10)
            data = res.json()
            if data.get("ok"):
                return True
            logger.warning(f"Telegram send failed: {data.get('description')}")
            return False
        except Exception as e:
            logger.error(f"Telegram network exception: {e}")
            return False

    def notify_perfect_trade_opportunity(self, trade_spec: Dict[str, Any]) -> bool:
        """
        Send instant notification when a high-probability trade opportunity is identified.
        """
        symbol = trade_spec.get("symbol", "N/A")
        side = trade_spec.get("side", "").upper()
        emoji_dir = "🟢 LONG" if side == "BUY" else "🔴 SHORT"
        entry = trade_spec.get("entry_price", 0.0)
        sl = trade_spec.get("stop_loss_price", 0.0)
        tp = trade_spec.get("take_profit_price", 0.0)
        rr = trade_spec.get("reward_to_risk_ratio", 2.0)
        contracts = trade_spec.get("contracts", 1)
        leverage = trade_spec.get("leverage", 5)
        strategy = trade_spec.get("strategy", "Technical Setup")
        margin = trade_spec.get("required_margin_usd", 0.0)
        thesis = trade_spec.get("thesis", "High probability edge verified.")

        message = (
            f"🎯 <b>[NEW TRADE OPPORTUNITY DETECTED]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code>\n"
            f"• <b>Direction:</b> <b>{emoji_dir}</b>\n"
            f"• <b>Strategy:</b> <i>{strategy}</i>\n"
            f"• <b>Leverage:</b> <code>{leverage}x</code>\n"
            f"• <b>Contracts:</b> <code>{contracts}</code> (Margin: ~${margin:.2f})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Entry:</b> <code>${entry:,.2f}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>${sl:,.2f}</code>\n"
            f"🎯 <b>Take Profit:</b> <code>${tp:,.2f}</code>\n"
            f"⚖️ <b>Reward/Risk:</b> <b>{rr:.2f} : 1</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>{thesis}</i>\n"
            f"⚡ <i>Automated execution in progress...</i>"
        )
        return self.send_message(message)

    def notify_trade_execution(self, exec_result: Dict[str, Any], trade_spec: Dict[str, Any]) -> bool:
        """
        Send instant receipt when order is submitted and live on Delta Exchange.
        """
        symbol = trade_spec.get("symbol", "N/A")
        side = trade_spec.get("side", "").upper()
        emoji_dir = "🟢 BOUGHT" if side == "BUY" else "🔴 SOLD"
        order_id = exec_result.get("order_id", "N/A")
        contracts = trade_spec.get("contracts", 1)
        entry = trade_spec.get("entry_price", 0.0)
        sl = trade_spec.get("stop_loss_price", 0.0)
        tp = trade_spec.get("take_profit_price", 0.0)
        leverage = trade_spec.get("leverage", 5)

        message = (
            f"🚀 <b>[TRADE EXECUTED ON DELTA EXCHANGE]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Status:</b> ✅ <b>ORDER PLACED &amp; ACTIVE</b>\n"
            f"• <b>Order ID:</b> <code>{order_id}</code>\n"
            f"• <b>Action:</b> {emoji_dir} <code>{contracts} contracts</code> of <b>{symbol}</b>\n"
            f"• <b>Leverage:</b> <code>{leverage}x Isolated</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Fill/Limit:</b> <code>${entry:,.2f}</code>\n"
            f"🛑 <b>Bracket SL:</b> <code>${sl:,.2f}</code>\n"
            f"🎯 <b>Bracket TP:</b> <code>${tp:,.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <i>Bracket orders active. Capital is protected.</i>"
        )
        return self.send_message(message)

    def notify_circuit_breaker(self, reason: str, drawdown_pct: float) -> bool:
        """Send urgent alert if circuit breaker halts trading."""
        message = (
            f"⚠️ <b>[CIRCUIT BREAKER ALERT — TRADING HALTED]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Drawdown:</b> <code>{drawdown_pct:.2f}%</code>\n"
            f"• <b>Reason:</b> <i>{reason}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛑 <i>New trades paused to protect capital.</i>"
        )
        return self.send_message(message)

