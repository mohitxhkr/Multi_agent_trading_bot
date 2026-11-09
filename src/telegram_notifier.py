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


def fmt_p(p: float) -> str:
    """Format price with magnitude-aware precision."""
    if p < 0.001:
        return f"${p:,.7f}"
    elif p < 0.1:
        return f"${p:,.6f}"
    elif p < 1.0:
        return f"${p:,.5f}"
    elif p < 10.0:
        return f"${p:,.4f}"
    else:
        return f"${p:,.2f}"


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
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
        self.enabled = enabled and bool(self.bot_token and self.chat_id)
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""

        if not self.enabled:
            logger.info("TelegramNotifier: Disabled (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured in environment).")

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

    def send_photo(
        self,
        photo_path_or_bytes: Any,
        caption: Optional[str] = None,
        parse_mode: str = "HTML"
    ) -> bool:
        """
        Send candlestick chart photo to Telegram with optional HTML caption.
        Accepts file path (str) or binary buffer/bytes.
        """
        if not self.enabled:
            logger.debug("TelegramNotifier: Disabled. Skipping send_photo.")
            return False

        try:
            url = f"{self.base_url}/sendPhoto"
            data = {"chat_id": self.chat_id}
            if caption:
                # Telegram caption maximum length is 1024 characters
                data["caption"] = caption[:1020]
                data["parse_mode"] = parse_mode

            if isinstance(photo_path_or_bytes, (bytes, bytearray)):
                files = {"photo": ("candlestick_chart.png", photo_path_or_bytes, "image/png")}
                res = requests.post(url, data=data, files=files, timeout=25)
            elif isinstance(photo_path_or_bytes, str) and os.path.exists(photo_path_or_bytes):
                with open(photo_path_or_bytes, "rb") as f:
                    files = {"photo": (os.path.basename(photo_path_or_bytes), f, "image/png")}
                    res = requests.post(url, data=data, files=files, timeout=25)
            else:
                logger.error(f"TelegramNotifier: Invalid photo target '{photo_path_or_bytes}'")
                return False

            data_res = res.json()
            if data_res.get("ok"):
                return True
            logger.warning(f"Telegram sendPhoto failed: {data_res.get('description')}")
            return False
        except Exception as e:
            logger.error(f"Telegram sendPhoto network exception: {e}")
            return False

    def send_daily_morning_briefing(self, briefing_text: str) -> bool:
        """Send formatted Daily Morning Crypto News Briefing & Sentiment Card to Telegram."""
        return self.send_message(briefing_text, parse_mode="HTML")

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

    def notify_trade_execution(
        self,
        exec_result: Dict[str, Any],
        trade_spec: Dict[str, Any],
        wallet: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send instant receipt when order is submitted and live on Delta Exchange."""
        symbol = trade_spec.get("symbol", "N/A")
        side = trade_spec.get("side", "").upper()
        emoji_dir = "🟢 LONG" if side == "BUY" else "🔴 SHORT"
        contracts = trade_spec.get("contracts", 1)
        entry = trade_spec.get("entry_price", 0.0)
        sl = trade_spec.get("stop_loss_price", 0.0)
        tp = trade_spec.get("take_profit_price", 0.0)
        leverage = trade_spec.get("leverage", 25)
        margin = trade_spec.get("required_margin_usd", 0.0)
        risk = trade_spec.get("dollar_risk_usd", 0.0)

        message = (
            f"🚀 <b>[ORDER PLACED ON DELTA]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code> {emoji_dir}\n"
            f"• <b>Size:</b> <code>{contracts} contracts</code> ({leverage}x Isolated | Margin: ~${margin:,.2f})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Limit Entry:</b> <code>{fmt_p(entry)}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>{fmt_p(sl)}</code> (Risk: ${risk:,.2f})\n"
            f"🎯 <b>Take Profit:</b> <code>{fmt_p(tp)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <i>Orderbook bracket active. Trailing Stop Sentinel engaged.</i>"
        )
        return self.send_message(message)

    def notify_order_filled(
        self,
        symbol: str,
        side: str,
        fill_price: float,
        contracts: int,
        leverage: int,
        sl: float,
        tp: float,
        wallet: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send instant notification when a pending order is FILLED on the orderbook."""
        emoji_dir = "🟢 LONG" if side.upper() == "BUY" else "🔴 SHORT"
        message = (
            f"⚡ <b>[ORDER FILLED &amp; POSITION ACTIVE]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code> {emoji_dir}\n"
            f"• <b>Fill Price:</b> <code>{fmt_p(fill_price)}</code>\n"
            f"• <b>Size:</b> <code>{contracts} contracts</code> ({leverage}x Isolated)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛑 <b>Stop Loss:</b> <code>{fmt_p(sl)}</code>\n"
            f"🎯 <b>Take Profit:</b> <code>{fmt_p(tp)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <i>Position is live! Auto-Breakeven at +0.50R.</i>"
        )
        return self.send_message(message)

    def notify_take_profit_hit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        contracts: int,
        realized_pnl: float,
        return_pct: float,
        r_multiple: float,
        wallet: Optional[Dict[str, Any]] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send celebratory alert when Take Profit target is achieved!"""
        emoji_dir = "🟢 LONG" if side.upper() == "BUY" else "🔴 SHORT"
        pnl_line = f"+${realized_pnl:,.2f} USD (+{return_pct:.1f}%)"
        message = (
            f"🎉 <b>[TAKE PROFIT TARGET HIT!]</b> 🏆\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code> {emoji_dir}\n"
            f"• <b>Exit Price:</b> <code>{fmt_p(exit_price)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Profit Won:</b> 🟢 <b>{pnl_line}</b>\n"
            f"⚖️ <b>Payout:</b> <b>+{r_multiple:.2f}R Reward</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <i>Profit banked successfully! Searching for next setup.</i>"
        )
        return self.send_message(message)

    def notify_stop_loss_hit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        contracts: int,
        realized_pnl: float,
        return_pct: float,
        exit_stage: str,
        wallet: Optional[Dict[str, Any]] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send alert when Stop Loss is hit, detailing capital preservation."""
        emoji_dir = "🟢 LONG" if side.upper() == "BUY" else "🔴 SHORT"
        message = (
            f"🛑 <b>[STOP LOSS HIT — CAPITAL SAFE]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code> {emoji_dir}\n"
            f"• <b>Exit Price:</b> <code>{fmt_p(exit_price)}</code>\n"
            f"• <b>Realized Loss:</b> 🔴 <b>-${abs(realized_pnl):,.2f} USD</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <i>Disciplined stop executed. Risk strictly bounded.</i>"
        )
        return self.send_message(message)

    def notify_profit_trailing_exit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        contracts: int,
        realized_pnl: float,
        return_pct: float = 0.0,
        r_multiple: float = 0.0,
        wallet: Optional[Dict[str, Any]] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send alert when position exits in locked green profit from trailing stop."""
        emoji_dir = "🟢 LONG" if side.upper() == "BUY" else "🔴 SHORT"
        message = (
            f"💰 <b>[PROFIT SECURED — TRAILING EXIT]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code> {emoji_dir}\n"
            f"• <b>Exit Price:</b> <code>{fmt_p(exit_price)}</code>\n"
            f"• <b>Realized PnL:</b> 🟢 <b>+${realized_pnl:,.2f} USD</b> (+{return_pct:.1f}% | +{r_multiple:.2f}R)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎉 <i>Guaranteed profit locked in the bank!</i>"
        )
        return self.send_message(message)

    def notify_breakeven_exit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        contracts: int,
        realized_pnl: float,
        wallet: Optional[Dict[str, Any]] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send alert when position exits at Breakeven (0 downside risk)."""
        emoji_dir = "🟢 LONG" if side.upper() == "BUY" else "🔴 SHORT"
        message = (
            f"🛡️ <b>[BREAKEVEN EXIT — ZERO RISK ACHIEVED]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code> {emoji_dir}\n"
            f"• <b>Exit Price:</b> <code>{fmt_p(exit_price)}</code>\n"
            f"• <b>Realized PnL:</b> 🟢 <b>+${realized_pnl:,.2f} USD</b> (Fees Covered)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <i>Trade exited risk-free. Capital 100% intact!</i>"
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

