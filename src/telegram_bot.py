"""
Interactive 2-Way Telegram Confirmation & Control Bot for Delta Exchange.
Ensures ZERO trades execute without explicit user confirmation via Telegram inline buttons.
Provides trailing stop alerts, position monitoring, and command handling (/status, /positions).
"""

from typing import Dict, Any, Optional, Tuple, List
import os
import sys
import time
import threading
import uuid
import json
import hashlib
import logging
import requests
from dotenv import load_dotenv

from src.technical_analysis import round_price
from src.config import config

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("telegram-bot")


class TelegramConfirmationBot:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        authorized_users: Optional[list] = None,
        token: Optional[str] = None,
        authorized_chat_ids: Optional[list] = None
    ):
        actual_token = bot_token or token
        self.bot_token = (actual_token or config.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        self.chat_id = (chat_id or config.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID") or "").strip()

        # Construct set of authorized Telegram User IDs
        self.authorized_user_ids = set()
        users_list = authorized_users or authorized_chat_ids
        if users_list:
            for u in users_list:
                if str(u).lstrip('-').isdigit():
                    self.authorized_user_ids.add(int(u))
            # If chat_id not explicitly given, use first authorized chat ID
            if not self.chat_id and len(users_list) > 0:
                self.chat_id = str(users_list[0]).strip()

        if config.authorized_user_ids:
            self.authorized_user_ids.update(config.authorized_user_ids)
        if self.chat_id and self.chat_id.lstrip('-').isdigit():
            self.authorized_user_ids.add(int(self.chat_id))

        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self.last_update_id = 0
        self._poll_lock = threading.RLock()
        self._confirmed_trade_ids = set()
        self._processed_nonces = set()
        self._active_trade_confirmations: Dict[str, Dict[str, Any]] = {}
        self._proposal_cards: Dict[str, Dict[str, Any]] = {}
        self.max_price_drift_pct = config.max_price_drift_pct
        self.audit_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "telegram_approvals_audit.json")
        self._poller_last_seen = 0.0

        try:
            from src.telegram_subscriber_manager import TelegramSubscriberManager
            is_mock_token = (
                not self.bot_token
                or self.bot_token.startswith(("test", "TEST", "MOCK", "mock", "123:"))
                or ":" not in self.bot_token
            )
            if not is_mock_token:
                self.subscriber_manager = TelegramSubscriberManager()
                if self.chat_id:
                    self.subscriber_manager.register_subscriber(self.chat_id, {"first_name": "Admin"}, role="admin")
            else:
                self.subscriber_manager = None
        except Exception:
            self.subscriber_manager = None

        self._sync_update_offset()

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    @staticmethod
    def _normalize_chat_id(cid: Any) -> str:
        s = str(cid or "").strip()
        if s.startswith("-100"):
            return s[4:]
        if s.startswith("-"):
            return s[1:]
        return s

    def _is_user_authorized(self, user_info: Any, chat_id: Optional[Any] = None) -> bool:
        """Authenticate callback or command sender against authorized user IDs or configured chat."""
        if not user_info and not chat_id:
            return False

        uid = None
        if user_info:
            if isinstance(user_info, dict):
                uid = user_info.get("id")
            else:
                try:
                    uid = int(user_info)
                except (ValueError, TypeError):
                    uid = None

        pos_authorized = {u for u in self.authorized_user_ids if u > 0}

        if uid is not None:
            try:
                i_uid = int(uid)
                if pos_authorized:
                    if i_uid in pos_authorized:
                        return True
                    # If specific user IDs are set, do not permit unauthorized users unless chat matches and pos_authorized empty
                    return False
            except (ValueError, TypeError):
                pass

            # Check matching chat_id
            if self.chat_id and self._normalize_chat_id(uid) == self._normalize_chat_id(self.chat_id):
                return True

        # Check matching chat_id for group/channel contexts
        target = chat_id or getattr(self, "_active_command_chat_id", None)
        if target and self.chat_id and not pos_authorized:
            if self._normalize_chat_id(target) == self._normalize_chat_id(self.chat_id):
                return True

        return False

    def _record_approval_audit(
        self,
        trade_id: str,
        user_info: Optional[Dict[str, Any]],
        decision: str,
        reason: str,
        trade_spec: Dict[str, Any]
    ) -> None:
        """Append-only audit ledger for every approval, rejection, or veto."""
        try:
            os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
            records = []
            if os.path.exists(self.audit_log_path):
                try:
                    with open(self.audit_log_path, "r", encoding="utf-8") as f:
                        records = json.load(f)
                except Exception:
                    records = []
            records.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "epoch": time.time(),
                "trade_id": trade_id,
                "user_id": user_info.get("id") if user_info else None,
                "username": user_info.get("username") if user_info else None,
                "first_name": user_info.get("first_name") if user_info else None,
                "decision": decision,
                "reason": reason,
                "trade_params": {
                    "symbol": trade_spec.get("symbol"),
                    "side": trade_spec.get("side"),
                    "entry_price": trade_spec.get("entry_price"),
                    "stop_loss_price": trade_spec.get("stop_loss_price"),
                    "take_profit_price": trade_spec.get("take_profit_price"),
                    "contracts": trade_spec.get("contracts"),
                    "leverage": trade_spec.get("leverage"),
                    "dollar_risk_usd": trade_spec.get("dollar_risk_usd")
                }
            })
            with open(self.audit_log_path, "w", encoding="utf-8") as f:
                json.dump(records[-500:], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to record Telegram approval audit: {e}")

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

    def send_message(
        self,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        chat_id: Optional[str] = None
    ) -> Optional[int]:
        """Send formatted HTML message to Telegram. Returns message_id if successful."""
        if not self.is_configured:
            logger.warning("Telegram not configured. Cannot send message.")
            return None

        target_chat = chat_id or self.chat_id
        if not target_chat:
            logger.warning("No target chat_id available to send message.")
            return None

        try:
            url = f"{self.base_url}/sendMessage"
            payload: Dict[str, Any] = {
                "chat_id": str(target_chat),
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
            logger.error(f"Telegram sendMessage failed to {target_chat}: {data.get('description')}")
            return None
        except Exception as e:
            logger.error(f"Telegram network error: {e}")
            return None

    def send_alert(self, text: str, chat_id: Optional[str] = None) -> bool:
        """Alias for send_message to ensure compatibility with emergency alerts."""
        return bool(self.send_message(text, parse_mode="Markdown", chat_id=chat_id))

    def send_photo(
        self,
        photo_path_or_bytes: Any,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> Optional[int]:
        """
        Send candlestick chart photo to Telegram with optional HTML caption.
        Accepts file path (str) or binary buffer/bytes.
        """
        if not self.is_configured:
            logger.warning("Telegram not configured. Cannot send photo.")
            return None

        target_chat = chat_id or self.chat_id
        if not target_chat:
            logger.warning("No target chat_id available to send photo.")
            return None

        try:
            url = f"{self.base_url}/sendPhoto"
            data: Dict[str, Any] = {"chat_id": str(target_chat)}
            if caption:
                data["caption"] = caption[:1020]
                data["parse_mode"] = "HTML"

            if isinstance(photo_path_or_bytes, (bytes, bytearray)):
                files = {"photo": ("candlestick_chart.png", photo_path_or_bytes, "image/png")}
                res = requests.post(url, data=data, files=files, timeout=25)
            elif isinstance(photo_path_or_bytes, str) and os.path.exists(photo_path_or_bytes):
                with open(photo_path_or_bytes, "rb") as f:
                    files = {"photo": (os.path.basename(photo_path_or_bytes), f, "image/png")}
                    res = requests.post(url, data=data, files=files, timeout=25)
            else:
                logger.error(f"TelegramConfirmationBot: Invalid photo path: {photo_path_or_bytes}")
                return None

            data_res = res.json()
            if data_res.get("ok"):
                return data_res["result"]["message_id"]
            logger.warning(f"Telegram sendPhoto failed: {data_res.get('description')}")
            return None
        except Exception as e:
            logger.error(f"Telegram sendPhoto network exception: {e}")
            return None

    def broadcast_message(
        self,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        topic: Optional[str] = None
    ) -> int:
        """Broadcast message to primary admin and all active subscribers."""
        if not self.is_configured:
            return 0

        target_ids = set()
        if self.chat_id:
            target_ids.add(str(self.chat_id))

        if hasattr(self, "subscriber_manager") and self.subscriber_manager:
            for sub in self.subscriber_manager.get_active_subscribers(topic=topic):
                cid = str(sub.get("chat_id", "")).strip()
                if cid:
                    target_ids.add(cid)

        successful_sends = 0
        for cid in target_ids:
            mid = self.send_message(text, reply_markup=reply_markup, chat_id=cid)
            if mid:
                successful_sends += 1
        return successful_sends

    def broadcast_photo(
        self,
        photo_path_or_bytes: Any,
        caption: Optional[str] = None,
        topic: Optional[str] = None
    ) -> int:
        """Broadcast photo to primary admin and all active subscribers."""
        if not self.is_configured:
            return 0

        target_ids = set()
        if self.chat_id:
            target_ids.add(str(self.chat_id))

        if hasattr(self, "subscriber_manager") and self.subscriber_manager:
            for sub in self.subscriber_manager.get_active_subscribers(topic=topic):
                cid = str(sub.get("chat_id", "")).strip()
                if cid:
                    target_ids.add(cid)

        successful_sends = 0
        for cid in target_ids:
            mid = self.send_photo(photo_path_or_bytes, caption=caption, chat_id=cid)
            if mid:
                successful_sends += 1
        return successful_sends

    def edit_message_text(
        self,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        chat_id: Optional[str] = None
    ) -> bool:
        """Edit an existing Telegram message."""
        if not self.is_configured:
            return False

        target_chat = chat_id or getattr(self, "_active_command_chat_id", None) or self.chat_id
        try:
            url = f"{self.base_url}/editMessageText"
            payload: Dict[str, Any] = {
                "chat_id": target_chat,
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

    def format_trade_proposal_card(self, trade_spec: Dict[str, Any], timeout_seconds: int = 300) -> str:
        """Format an institutional trade proposal card for Telegram presentation."""
        symbol = trade_spec.get("symbol", "N/A")
        side = trade_spec.get("side", "").upper()
        emoji_dir = "🟢 LONG" if side == "BUY" else "🔴 SHORT"
        entry = float(trade_spec.get("entry_price") or trade_spec.get("entry") or 0.0)
        sl = float(trade_spec.get("stop_loss_price") or trade_spec.get("stop_loss") or 0.0)
        tp = float(trade_spec.get("take_profit_price") or trade_spec.get("take_profit") or 0.0)
        rr = float(trade_spec.get("reward_to_risk_ratio") or trade_spec.get("planned_rr_ratio") or 2.0)
        contracts = trade_spec.get("contracts", 1)
        leverage = trade_spec.get("leverage", 25)
        margin = float(trade_spec.get("required_margin_usd") or 0.0)
        risk_usd = float(trade_spec.get("dollar_risk_usd") or 2.0)
        risk_pct = float(trade_spec.get("risk_pct") or 1.5)
        strategy = trade_spec.get("strategy") or trade_spec.get("strategy_name") or "High-Probability Edge"
        confluence = trade_spec.get("confluence", {})

        def fmt_p(p: float) -> str:
            if p < 0.1:
                return f"${p:,.6f}"
            elif p < 1.0:
                return f"${p:,.5f}"
            elif p < 10.0:
                return f"${p:,.4f}"
            else:
                return f"${p:,.2f}"

        reward_usd = risk_usd * (rr if rr > 0 else 2.0)
        tm = trade_spec.get("time_machine", {})
        sample_size = tm.get("sample_size") or (tm.get("wins", 0) + tm.get("losses", 0))
        wins = tm.get("wins", 0)
        losses = tm.get("losses", 0)
        win_rate = tm.get("win_rate_pct")

        if sample_size and sample_size >= 6 and win_rate and win_rate > 0:
            backtest_line = f"📊 <b>Empirical Backtest:</b> Tested <b>{sample_size} times</b> ({wins}W / {losses}L · <b>{win_rate:.0f}% Win Rate</b> · <b>1:{rr:.1f} R:R</b>)\n"
        else:
            backtest_line = "📊 <b>Market Edge:</b> Multi-Timeframe SMC Confluence Aligned\n"

        score = trade_spec.get("score", 85)
        clean_strat = strategy.replace("_", " ").title()

        is_scale_in = bool(trade_spec.get("is_scale_in", False))
        scale_parent = trade_spec.get("scale_in_parent", {})
        existing_size = float(scale_parent.get("existing_size", 0))
        unrealized_pnl = float(scale_parent.get("unrealized_pnl", 0.0))
        title = "🔥 <b>[SCALE-IN: ADDING TO WINNER]</b>" if is_scale_in else "🎯 <b>[NEW TRADE PROPOSAL]</b>"

        conv_mult = float(trade_spec.get("conviction_multiplier", 1.0))
        boost_info = trade_spec.get("past_win_boost", {})
        boost_reason = boost_info.get("reason")
        boost_tag = f" · 🔥 <b>+{int(round((conv_mult - 1.0) * 100))}% Size Boost</b>" if conv_mult > 1.0 else ""
        boost_line = ""
        if conv_mult > 1.0:
            boost_pct = int(round((conv_mult - 1.0) * 100))
            r_str = f" · <i>{boost_reason}</i>" if boost_reason else ""
            boost_line = f"🚀 <b>PAST WIN LOT BOOST:</b> <b>{conv_mult:.2f}x (+{boost_pct}% contracts)</b>{r_str}\n"

        score_badge = "A+ PRIME CONVICTION" if score >= 90 else ("HIGH CONVICTION EDGE" if score >= 80 else "STANDARD")
        rr_badge = trade_spec.get("risk_reward_badge") or "🟢 MIN RISK · MAX PROFIT"
        rr_desc = trade_spec.get("risk_reward_desc") or "Asymmetric Institutional Alpha"

        sent_info = trade_spec.get("sentiment_report") or {}
        if not sent_info:
            try:
                from multiagent_team.news_sentiment_agent import NewsSentimentAgent
                cached = NewsSentimentAgent().cached_report
                if cached:
                    sent_info = cached.model_dump() if hasattr(cached, "model_dump") else cached.dict()
            except Exception:
                sent_info = {}

        fng_val = sent_info.get("fear_greed_index", 50)
        fng_class = sent_info.get("fear_greed_classification", "Neutral")
        sentiment_regime = sent_info.get("sentiment_regime", "NEUTRAL")
        composite_score = sent_info.get("composite_score", 0.0)

        if composite_score >= 0.15:
            sent_tag = f"🟢 BULLISH BIAS ({composite_score:+.2f})"
        elif composite_score <= -0.15:
            sent_tag = f"🔴 BEARISH BIAS ({composite_score:+.2f})"
        else:
            sent_tag = f"⚪ NEUTRAL BIAS ({composite_score:+.2f})"

        base_sym = symbol.replace("USD", "").replace("USDT", "").replace("-", "").replace("/", "").upper()
        asset_sent = sent_info.get("asset_sentiment_map", {}).get(base_sym, {})
        asset_sentiment_line = ""
        if asset_sent:
            a_bias = asset_sent.get("sentiment", "NEUTRAL")
            a_emoji = "🟢" if a_bias == "BULLISH" else ("🔴" if a_bias == "BEARISH" else "⚪")
            asset_sentiment_line = f" · {a_emoji} {base_sym} Sentiment: {a_bias} ({asset_sent.get('score', 0.0):+.2f})"

        scale_in_block = (
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>ACTIVE TRADE GOING WELL:</b>\n"
            f"• <b>Existing Position:</b> <code>{int(existing_size)} contracts</code> (PnL: <b>+${unrealized_pnl:.2f} USD</b>)\n"
            f"• <b>Adding to Winner:</b> <code>+{contracts} contracts</code> (Second entry opportunity)\n"
            f"• <b>New Combined Size:</b> <code>{int(existing_size + contracts)} contracts</code>\n"
        ) if is_scale_in else ""

        import html
        dd_warnings = (
            trade_spec.get("drawdown_warnings")
            or (trade_spec.get("circuit_breaker") or {}).get("drawdown_warnings")
            or []
        )
        dd_warning_block = ""
        if dd_warnings:
            warn_lines = "\n".join(f"• {html.escape(str(w))}" for w in dd_warnings)
            dd_warning_block = (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>DRAWDOWN LIMIT NOTE:</b>\n"
                f"{warn_lines}\n"
            )

        proposal_text = (
            f"{title}\n"
            f"⭐ <b>QUALITY SCORE:</b> <b><u>{score}/100</u> ({score_badge})</b>{boost_tag}\n"
            f"💎 <b>PROFILE:</b> <b>{rr_badge}</b> <i>({rr_desc})</i>\n"
            f"{boost_line}"
            f"{dd_warning_block}"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{symbol}</code> {emoji_dir}\n"
            f"• <b>Setup:</b> <i>{clean_strat}</i>\n"
            f"{scale_in_block}"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 <b>MARKET SENTIMENT &amp; MACRO PULSE:</b>\n"
            f"• <b>Fear &amp; Greed:</b> <code>{fng_val}/100 ({fng_class})</code>\n"
            f"• <b>Sentiment Polarity:</b> <b>{sent_tag}</b> [{sentiment_regime}]{asset_sentiment_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>Total Risk:</b> <b>${risk_usd:,.2f} USD</b> <i>(Max loss if Stop Loss hits)</i>\n"
            f"💰 <b>Total Reward:</b> <b>${reward_usd:,.2f} USD</b> <i>(Profit if Target hits)</i>\n"
            f"⚖️ <b>Risk to Reward Ratio:</b> <b>1 : {rr:.1f}</b> <i>(Win ${rr:.1f} for every $1 risked)</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Entry:</b> <code>{fmt_p(entry)}</code>\n"
            f"🛑 <b>Stop Loss:</b> <code>{fmt_p(sl)}</code>\n"
            f"🎯 <b>Take Profit:</b> <code>{fmt_p(tp)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 <b>Order Size:</b> <code>{contracts} contracts</code> ({leverage}x Isolated | Margin: ~${margin:,.2f})\n"
            f"{backtest_line}"
            f"🛡️ <b>Protection:</b> Risk Slashed at +0.80R · Green Profit Locked at +1.10R\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Tap below to approve or decline (Expires in {timeout_seconds // 60}m):</i>"
        )
        return proposal_text

    def send_sample_proposal(self, chat_id: Optional[str] = None) -> Optional[int]:
        """Send an interactive demonstration trade proposal card to Telegram."""
        if not self.is_configured:
            logger.error("❌ Telegram is not configured!")
            return None

        trade_id = f"sample_{uuid.uuid4().hex[:6]}"
        sample_spec = {
            "trade_id": trade_id,
            "symbol": "BTCUSD",
            "side": "BUY",
            "entry_price": 75800.0,
            "stop_loss_price": 75250.0,
            "take_profit_price": 77200.0,
            "reward_to_risk_ratio": 2.5,
            "contracts": 1,
            "leverage": 25,
            "required_margin_usd": 30.32,
            "dollar_risk_usd": 2.20,
            "risk_pct": 0.22,
            "estimated_liquidation_price": 72800.0,
            "strategy": "Institutional_SMC_Liquidity_Sweep_Long",
            "thesis": "💧 [BULLISH SSL SWEEP + MSS CONFIRMED] 15m SMC Order Block Alignment",
            "score": 94,
            "conviction_multiplier": 1.25,
            "risk_reward_badge": "🟢 MIN RISK · MAX PROFIT",
            "risk_reward_desc": "Asymmetric Institutional Alpha",
            "confluence": {
                "macd_detail": "15m: BULLISH_CROSS (BULLISH_EXPANSION) | 1H: BULLISH",
                "vwap_detail": "$75,720.00 (ABOVE_VWAP | FAIR_VALUE_CORE | RISING_BULLISH)",
                "liquidity_detail": "BSL: $77,200.00 (+1.85%) | SSL: $75,200.00 (-0.79%) | State: SWEEP_MSS_CONFIRMED | Spread: 0.020% (A+_PRIME_DEPTH)"
            },
            "liquidity_profile": {
                "spread_pct": 0.02,
                "liquidity_grade": "A+_PRIME_DEPTH",
                "liquidity_detail": "BSL: $77,200.00 (+1.85%) | SSL: $75,200.00 (-0.79%) | State: SWEEP_MSS_CONFIRMED | Spread: 0.020%"
            },
            "time_machine": {
                "sample_size": 28,
                "wins": 22,
                "losses": 6,
                "win_rate_pct": 78.6,
                "expected_value_r": 0.48
            },
            "sentiment_report": {
                "fear_greed_index": 25,
                "fear_greed_classification": "Extreme Fear",
                "sentiment_regime": "FEAR",
                "composite_score": -0.22,
                "asset_sentiment_map": {
                    "BTC": {
                        "sentiment": "BULLISH",
                        "score": 0.35
                    }
                }
            }
        }

        card_text = self.format_trade_proposal_card(sample_spec, timeout_seconds=300)
        card_text = card_text.replace(
            "🎯 <b>[NEW TRADE PROPOSAL]</b>",
            "🎯 <b>[SAMPLE DEMONSTRATION TRADE PROPOSAL]</b>"
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Confirm & Execute (Sample)", "callback_data": f"sample_confirm_{trade_id}"},
                    {"text": "❌ Reject Trade (Sample)", "callback_data": f"sample_reject_{trade_id}"}
                ]
            ]
        }
        return self.send_message(card_text, reply_markup=reply_markup, chat_id=chat_id)

    def _process_trade_confirmation_callback(
        self,
        cb_id: str,
        cb_data: str,
        user_info: Dict[str, Any],
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Thread-safe unified callback processor for trade confirmation and rejection buttons.
        Can be invoked from process_incoming_commands or request_trade_confirmation.
        """
        if not cb_data.startswith("confirm_") and not cb_data.startswith("reject_"):
            return False

        action = "confirm" if cb_data.startswith("confirm_") else "reject"
        trade_id = cb_data.replace("confirm_", "").replace("reject_", "").strip()

        info = self._active_trade_confirmations.get(trade_id)
        if not info:
            if trade_id in self._confirmed_trade_ids:
                self.answer_callback(cb_id, "⚠️ This trade has already been confirmed and executed.")
            else:
                self.answer_callback(cb_id, "⌛ This trade proposal has expired or is no longer active.")
            return False

        conf_event = info["event"]
        result_holder = info["result"]
        trade_spec = info["trade_spec"]
        msg_id = info["msg_id"]
        target_chat = info["target_chat"]
        proposal_text = info["proposal_text"]
        param_signature = info["param_signature"]
        client = info["client"]
        symbol = info["symbol"]
        entry = info["entry"]

        def _edit(mid: int, t: str, rm: Optional[Dict[str, Any]] = None) -> bool:
            if target_chat and target_chat != self.chat_id:
                return self.edit_message_text(mid, t, reply_markup=rm, chat_id=target_chat)
            return self.edit_message_text(mid, t, reply_markup=rm)

        import re
        prompt_pattern = r"<i>Tap below to approve or decline.*?</i>"

        # 1. Authenticate sender
        if not self._is_user_authorized(user_info, chat_id=chat_id or target_chat):
            logger.warning(f"SECURITY VETO: Unauthorized callback query from user {user_info} in chat {chat_id}")
            self.answer_callback(cb_id, "⛔ Unauthorized: You are not authorized to approve trades.")
            self._record_approval_audit(trade_id, user_info, "UNAUTHORIZED", "User ID not authorized", trade_spec)
            return False

        # 2. Check Expiry
        if time.time() > info["expiry_timestamp"]:
            self.answer_callback(cb_id, "⏰ Trade proposal has expired.")
            self._record_approval_audit(trade_id, user_info, "EXPIRED", "Confirmation window expired", trade_spec)
            if re.search(prompt_pattern, proposal_text):
                timeout_text = re.sub(prompt_pattern, "⌛ <b>PROPOSAL EXPIRED — NO ORDER PLACED.</b>", proposal_text)
            else:
                timeout_text = proposal_text + "\n\n⌛ <b>PROPOSAL EXPIRED — NO ORDER PLACED.</b>"
            _edit(msg_id, timeout_text, {"inline_keyboard": []})
            result_holder["confirmed"] = False
            conf_event.set()
            return False

        # 3. Check Nonce Replay
        if param_signature in self._processed_nonces or trade_id in self._confirmed_trade_ids:
            self.answer_callback(cb_id, "⚠️ Proposal has already been processed.")
            return False

        if action == "confirm":
            # 4. Mandatory Revalidation with Fresh Live Market Data
            if client:
                try:
                    t_res = client.get_ticker(symbol)
                    if not t_res or not t_res.get("success"):
                        self.answer_callback(cb_id, "❌ Execution rejected: Live market ticker unavailable.")
                        self._record_approval_audit(trade_id, user_info, "REJECTED_STALE_TICKER", "Live ticker refresh failed", trade_spec)
                        if re.search(prompt_pattern, proposal_text):
                            abort_text = re.sub(prompt_pattern, "🛑 <b>EXECUTION ABORTED: LIVE TICKER DATA UNAVAILABLE. CAPITAL PROTECTED.</b>", proposal_text)
                        else:
                            abort_text = proposal_text + "\n\n🛑 <b>EXECUTION ABORTED: LIVE TICKER DATA UNAVAILABLE. CAPITAL PROTECTED.</b>"
                        _edit(msg_id, abort_text, {"inline_keyboard": []})
                        logger.error(f"Trade {trade_id} aborted: Live market data could not be refreshed from Delta Exchange.")
                        result_holder["confirmed"] = False
                        conf_event.set()
                        return False

                    cur_mark = float(t_res.get("result", {}).get("mark_price") or 0.0)
                    if cur_mark <= 0:
                        self.answer_callback(cb_id, "❌ Execution rejected: Invalid mark price from exchange.")
                        self._record_approval_audit(trade_id, user_info, "REJECTED_INVALID_MARK", "Zero mark price", trade_spec)
                        result_holder["confirmed"] = False
                        conf_event.set()
                        return False

                    price_drift_pct = abs(cur_mark - entry) / entry * 100.0 if entry > 0 else 0.0
                    if price_drift_pct > self.max_price_drift_pct:
                        self.answer_callback(cb_id, f"⚠️ Aborted: Price drifted {price_drift_pct:.2f}%!")
                        self._record_approval_audit(trade_id, user_info, "ABORTED_PRICE_DRIFT", f"Price drifted {price_drift_pct:.2f}%", trade_spec)
                        drift_sub = f"🛑 <b>ABORTED: PRICE DRIFTED ({price_drift_pct:.2f}% shift).</b>\n<i>Mark moved to ${cur_mark:.4f} while awaiting confirmation. Capital protected.</i>"
                        if re.search(prompt_pattern, proposal_text):
                            drift_text = re.sub(prompt_pattern, drift_sub, proposal_text)
                        else:
                            drift_text = proposal_text + f"\n\n{drift_sub}"
                        _edit(msg_id, drift_text, {"inline_keyboard": []})
                        logger.warning(f"Trade {trade_id} aborted before execution: Mark price drifted {price_drift_pct:.2f}%")
                        result_holder["confirmed"] = False
                        conf_event.set()
                        return False
                except Exception as drift_err:
                    logger.error(f"Pre-execution price check exception: {drift_err}")
                    self.answer_callback(cb_id, f"❌ Execution aborted: Market feed verification error: {drift_err}")
                    self._record_approval_audit(trade_id, user_info, "REJECTED_FEED_ERROR", str(drift_err), trade_spec)
                    result_holder["confirmed"] = False
                    conf_event.set()
                    return False

            self._confirmed_trade_ids.add(trade_id)
            self._processed_nonces.add(param_signature)
            self._record_approval_audit(trade_id, user_info, "APPROVED", "Confirmed by authorized user", trade_spec)

            self.answer_callback(cb_id, "✅ Confirmed! Executing on Delta Exchange...")
            if re.search(prompt_pattern, proposal_text):
                confirmed_text = re.sub(prompt_pattern, "⚡ <b>CONFIRMED BY AUTHORIZED USER! EXECUTING ON DELTA EXCHANGE...</b>", proposal_text)
            else:
                confirmed_text = proposal_text + "\n\n⚡ <b>CONFIRMED BY AUTHORIZED USER! EXECUTING ON DELTA EXCHANGE...</b>"
            _edit(msg_id, confirmed_text, {"inline_keyboard": []})
            logger.info(f"User {user_info.get('id')} APPROVED trade {trade_id} via Telegram (Nonce: {param_signature})!")
            result_holder["confirmed"] = True
            conf_event.set()
            return True

        elif action == "reject":
            self._processed_nonces.add(param_signature)
            self._record_approval_audit(trade_id, user_info, "REJECTED", "Declined by user", trade_spec)
            self.answer_callback(cb_id, "❌ Trade proposal rejected.")
            if re.search(prompt_pattern, proposal_text):
                rejected_text = re.sub(prompt_pattern, "❌ <b>REJECTED BY USER — CAPITAL PROTECTED.</b>", proposal_text)
            else:
                rejected_text = proposal_text + "\n\n❌ <b>REJECTED BY USER — CAPITAL PROTECTED.</b>"
            _edit(msg_id, rejected_text, {"inline_keyboard": []})
            logger.info(f"User {user_info.get('id')} REJECTED trade {trade_id} via Telegram.")
            result_holder["confirmed"] = False
            conf_event.set()
            return True

        return False

    def request_trade_confirmation(
        self,
        trade_spec: Dict[str, Any],
        timeout_seconds: int = 600,
        client: Optional[Any] = None,
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Send trade analysis with confirmation buttons and BLOCK until the user taps
        [Confirm] or [Reject], or until timeout.
        Returns True ONLY if user explicitly clicked Confirm and pre-execution validation passes!
        """
        if not self.is_configured:
            logger.error("❌ Telegram is not configured! Refusing to trade without user permission.")
            return False

        target_chat = chat_id or getattr(self, "_active_command_chat_id", None) or self.chat_id

        trade_id = trade_spec.get("trade_id") or f"trade_{uuid.uuid4().hex[:8]}"
        trade_spec["trade_id"] = trade_id

        if trade_id in self._confirmed_trade_ids:
            logger.warning(f"Trade {trade_id} already confirmed! Preventing duplicate execution.")
            return False

        proposal_text = self.format_trade_proposal_card(trade_spec, timeout_seconds=timeout_seconds)

        # Generate cryptographic parameter nonce and expiry
        expiry_timestamp = trade_spec.get("approval_expiry") or (time.time() + timeout_seconds)
        param_signature = trade_spec.get("approval_nonce") or hashlib.sha256(
            f"{trade_id}:{trade_spec.get('symbol')}:{trade_spec.get('side')}:{trade_spec.get('entry_price', 0):.4f}:{trade_spec.get('stop_loss_price', 0):.4f}:{trade_spec.get('take_profit_price', 0):.4f}:{trade_spec.get('contracts', 1)}:{trade_spec.get('leverage', 25)}:{trade_spec.get('dollar_risk_usd', 0):.2f}:{int(expiry_timestamp)}".encode()
        ).hexdigest()[:16]
        trade_spec["approval_nonce"] = param_signature
        trade_spec["approval_expiry"] = expiry_timestamp

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Confirm & Execute", "callback_data": f"confirm_{trade_id}"},
                    {"text": "❌ Reject Trade", "callback_data": f"reject_{trade_id}"}
                ]
            ]
        }

        # Send directional candlestick chart if available
        chart_path = trade_spec.get("chart_path")
        if chart_path and os.path.exists(chart_path):
            try:
                self.send_photo(chart_path, chat_id=target_chat)
            except Exception as pe:
                logger.debug(f"Failed to send proposal chart photo: {pe}")

        if target_chat and target_chat != self.chat_id:
            msg_id = self.send_message(proposal_text, reply_markup=reply_markup, chat_id=target_chat)
        else:
            msg_id = self.send_message(proposal_text, reply_markup=reply_markup)
        if not msg_id:
            logger.error("Failed to post proposal message to Telegram!")
            return False

        def _edit(mid: int, t: str, rm: Optional[Dict[str, Any]] = None) -> bool:
            if target_chat and target_chat != self.chat_id:
                return self.edit_message_text(mid, t, reply_markup=rm, chat_id=target_chat)
            return self.edit_message_text(mid, t, reply_markup=rm)

        logger.info(f"Proposal sent to Telegram (msg_id: {msg_id}, Nonce: {param_signature}, chat: {target_chat}). Waiting for user button click (timeout {timeout_seconds}s)...")

        # Register in active confirmations table
        conf_event = threading.Event()
        result_holder = {"confirmed": None}
        self._active_trade_confirmations[trade_id] = {
            "event": conf_event,
            "result": result_holder,
            "trade_spec": trade_spec,
            "msg_id": msg_id,
            "target_chat": target_chat,
            "expiry_timestamp": expiry_timestamp,
            "param_signature": param_signature,
            "client": client,
            "proposal_text": proposal_text,
            "timeout_seconds": timeout_seconds,
            "symbol": trade_spec.get("symbol", "BTCUSD"),
            "entry": float(trade_spec.get("entry_price") or trade_spec.get("entry") or 0.0),
        }
        self._proposal_cards[trade_id] = {
            "msg_id": msg_id,
            "target_chat": target_chat,
            "proposal_text": proposal_text
        }

        try:
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                # 1. Check if event was set by process_incoming_commands callback handler
                if conf_event.is_set():
                    return bool(result_holder.get("confirmed"))

                # 2. Check if a dedicated listener thread is actively polling Telegram
                poller_active = (time.time() - getattr(self, "_poller_last_seen", 0)) < 4.0
                if poller_active:
                    # Listener thread is running. Wait smoothly on Event with ZERO getUpdates conflict!
                    rem = max(0.1, timeout_seconds - (time.time() - start_time))
                    if conf_event.wait(timeout=min(1.0, rem)):
                        return bool(result_holder.get("confirmed"))
                else:
                    # Standalone/test fallback: Poll Telegram updates directly
                    self.process_incoming_commands()
                    if conf_event.wait(timeout=0.5):
                        return bool(result_holder.get("confirmed"))

            # Timeout reached
            self._record_approval_audit(trade_id, None, "TIMEOUT", f"Confirmation timeout reached ({timeout_seconds}s)", trade_spec)
            import re
            prompt_pattern = r"<i>Tap below to approve or decline.*?</i>"
            if re.search(prompt_pattern, proposal_text):
                timeout_text = re.sub(prompt_pattern, f"⌛ <b>PROPOSAL EXPIRED ({timeout_seconds // 60}m) — NO ORDER PLACED.</b>", proposal_text)
            else:
                timeout_text = proposal_text + f"\n\n⌛ <b>PROPOSAL EXPIRED ({timeout_seconds // 60}m) — NO ORDER PLACED.</b>"
            _edit(msg_id, timeout_text, {"inline_keyboard": []})
            logger.info(f"Trade proposal {trade_id} timed out. Order cancelled.")
            return False
        finally:
            self._active_trade_confirmations.pop(trade_id, None)

    def update_proposal_card_status(
        self,
        trade_id: str,
        status: str,
        detail: str = "",
        chat_id: Optional[str] = None
    ) -> bool:
        """
        Update a previously displayed Telegram proposal card to reflect the final execution outcome.
        Status can be: 'EXECUTED', 'FAILED', 'BLOCKED', 'CANCELLED'.
        """
        card_info = self._proposal_cards.get(trade_id)
        if not card_info:
            return False

        msg_id = card_info.get("msg_id")
        target_chat = chat_id or card_info.get("target_chat") or self.chat_id
        base_text = card_info.get("proposal_text", "")

        if not msg_id or not base_text:
            return False

        import re
        prompt_pattern = r"<i>Tap below to approve or decline.*?</i>"
        executing_pattern = r"⚡ <b>CONFIRMED BY AUTHORIZED USER! EXECUTING ON DELTA EXCHANGE...</b>"

        if status == "EXECUTED":
            status_text = f"✅ <b>ORDER EXECUTED ON DELTA EXCHANGE!</b>\n<i>{detail}</i>"
        elif status == "BLOCKED":
            status_text = f"🛑 <b>EXECUTION BLOCKED BY SAFETY GATE:</b>\n<code>{detail}</code>\n<i>Capital protected.</i>"
        elif status in ["FAILED", "ERROR"]:
            status_text = f"🛑 <b>EXECUTION FAILED ON DELTA EXCHANGE:</b>\n<code>{detail}</code>\n<i>Capital protected.</i>"
        else:
            status_text = f"ℹ️ <b>STATUS: {status}</b>\n<i>{detail}</i>"

        new_text = base_text
        if re.search(executing_pattern, new_text):
            new_text = re.sub(executing_pattern, status_text, new_text)
        elif re.search(prompt_pattern, new_text):
            new_text = re.sub(prompt_pattern, status_text, new_text)
        else:
            new_text = new_text + "\n\n" + status_text

        try:
            return self.edit_message_text(msg_id, new_text, reply_markup={"inline_keyboard": []}, chat_id=target_chat)
        except Exception as e:
            logger.warning(f"Failed to update proposal card status for trade {trade_id}: {e}")
            return False

    def _normalize_incoming_command(self, text: str) -> Tuple[str, str]:
        """
        Normalize incoming Telegram message into (cmd, full_text).
        Supports:
        1. Standard slash commands: /trade BTC, /status, /levels, /close BTCUSD, etc.
        2. Natural language commands & common typos:
           - 'propse trade btc', 'propose trade btc', 'trade btc', 'propose btc', 'buy btc', 'sell btc' -> ('/trade', '/trade BTCUSD [side]')
           - 'status', 'ping', 'balance', 'wallet', 'equity', 'cash' -> ('/status', '/status')
           - 'positions', 'position', 'pos', 'portfolio', 'openpositions' -> ('/positions', '/positions')
           - 'orders', 'pending', 'orderbook' -> ('/orders', '/orders')
           - 'close btc', 'close eth', 'closeall', 'panic', 'flatten' -> ('/close', '/close BTCUSD') or ('/closeall', '/closeall')
           - 'radar', 'pretrade', 'levels', 'chart btc', 'news', 'scorecard', 'rules', 'sample', 'pause', 'resume', 'help'
        3. Unrecognized messages -> ('/unknown', raw_text)
        """
        raw = text.strip()
        if raw.startswith("/"):
            parts = raw.split()
            cmd = parts[0].lower().split("@")[0]
            # Normalize legacy/alias commands into clean core commands
            if cmd in ["/scalp", "/findtrade", "/find_trade", "/proposal", "/propose"]:
                cmd = "/trade"
                raw = f"/trade {' '.join(parts[1:])}".strip()
            elif cmd in ["/scan", "/market", "/radar", "/preradar", "/scalpradar", "/pretrade"]:
                cmd = "/levels"
                raw = f"/levels {' '.join(parts[1:])}".strip()
            elif cmd in ["/posture", "/regime", "/marketposture"]:
                cmd = "/status"
                raw = "/status"
            elif cmd in ["/rules", "/discipline", "/operatingrules"]:
                cmd = "/help"
                raw = "/help"
            return cmd, raw

        lower = raw.lower().replace("?", "").replace("!", "").replace(",", " ").strip()
        tokens = lower.split()
        if not tokens:
            return "/unknown", raw

        # Check for asset mention
        asset = None
        for tok in tokens:
            tok_u = tok.upper()
            if tok_u in ["BTC", "BITCOIN", "BTCUSD", "BTCUSDT"]:
                asset = "BTCUSD"
            elif tok_u in ["ETH", "ETHEREUM", "ETHUSD", "ETHUSDT"]:
                asset = "ETHUSD"
            elif tok_u in ["XAU", "GOLD", "PAXG", "XAUUSD"]:
                asset = "XAUUSD"
            elif tok_u in ["SOL", "SOLANA", "SOLUSD", "SOLUSDT"]:
                asset = "SOLUSD"
            elif tok_u in ["XRP", "RIPPLE", "XRPUSD"]:
                asset = "XRPUSD"
            elif tok_u in ["DOGE", "DOGEUSD"]:
                asset = "DOGEUSD"
            elif tok_u in ["ADA", "ADAUSD"]:
                asset = "ADAUSD"

        # Check for side mention
        side = None
        for tok in tokens:
            if tok in ["buy", "long"]:
                side = "buy"
            elif tok in ["sell", "short"]:
                side = "sell"

        # 1. Trade intent: e.g. "propse trade btc", "propose trade btc", "trade btc", "propose btc", "scalp btc"
        trade_keywords = {"trade", "propose", "propse", "propsal", "proposal", "scalp", "findtrade", "find_trade"}
        if any(w in trade_keywords for w in tokens) or (side and asset):
            cmd_str = f"/trade {asset or ''} {side or ''}".strip()
            return "/trade", cmd_str

        # 2. Status / balance
        if any(w in {"status", "ping", "balance", "wallet", "equity", "cash"} for w in tokens):
            return "/status", "/status"

        # 3. Positions
        if any(w in {"positions", "position", "pos", "portfolio", "openpositions"} for w in tokens):
            return "/positions", "/positions"

        # 4. Orders
        if any(w in {"orders", "orderbook", "pending"} for w in tokens):
            return "/orders", "/orders"

        # 5. Close / Closeall
        if any(w in {"closeall", "panic", "flatten", "killall"} for w in tokens):
            return "/closeall", "/closeall"
        if "close" in tokens:
            return "/close", f"/close {asset or ''}".strip()

        # 6. Levels / Breakout / Breakdown / Market / Radar (Normalized to /levels)
        if any(w in {"levels", "breakout", "breakdown", "keylevels", "radar", "scan", "market"} for w in tokens):
            return "/levels", "/levels"

        # 8. Chart / Candlestick / Graph
        if any(w in {"chart", "candlestick", "graph"} for w in tokens):
            return "/chart", f"/chart {asset or 'BTCUSD'}".strip()

        # 9. News / Morning / Sentiment
        if any(w in {"news", "briefing", "morning", "sentiment"} for w in tokens):
            return "/news", "/news"

        # 10. Scorecard / Learning / Performance
        if any(w in {"scorecard", "learning", "performance", "audit"} for w in tokens):
            return "/scorecard", "/scorecard"

        # 11. Rules / Discipline
        if any(w in {"rules", "discipline", "operatingrules"} for w in tokens):
            return "/rules", "/rules"

        # 12. Pause / Stop / Resume
        if any(w in {"pause", "halt", "stop", "freeze"} for w in tokens):
            return "/pause", "/pause"
        if any(w in {"resume", "unpause", "start"} for w in tokens):
            return "/resume", "/resume"

        # 13. Sample
        if any(w in {"sample", "testproposal", "sampletrade"} for w in tokens):
            return "/sample", "/sample"

        # 14. Subscription commands
        if any(w in {"subscribe", "sub", "notify", "alerts"} for w in tokens):
            return "/subscribe", "/subscribe"
        if any(w in {"unsubscribe", "unsub", "mute", "optout"} for w in tokens) or (tokens == ["stop"]):
            return "/unsubscribe", "/unsubscribe"
        if any(w in {"subscribers", "subs", "users"} for w in tokens):
            return "/subscribers", "/subscribers"
        if any(w in {"broadcast_levels", "broadcastlevels"} for w in tokens):
            return "/broadcast_levels", "/broadcast_levels"
        if any(w in {"broadcast_news", "broadcastnews"} for w in tokens):
            return "/broadcast_news", "/broadcast_news"

        # 15. Help
        if any(w in {"help", "commands", "menu", "start", "hi", "hello"} for w in tokens):
            return "/help", "/help"

        # Unrecognized message
        return "/unknown", raw

    def process_incoming_commands(self, orchestrator=None) -> None:
        """
        Poll Telegram for incoming user commands (/status, /scan, /positions, /orders, /help)
        and respond immediately.
        """
        if not self.is_configured:
            return

        self._poller_last_seen = time.time()

        if not self._poll_lock.acquire(blocking=False):
            return

        updates = []
        try:
            if orchestrator:
                self._active_orchestrator = orchestrator

            url = f"{self.base_url}/getUpdates"
            params = {"offset": self.last_update_id, "timeout": 2}
            res = requests.get(url, params=params, timeout=5)
            data = res.json()
            if data.get("ok"):
                updates = data.get("result", [])
                if updates:
                    self.last_update_id = max(self.last_update_id, max(u["update_id"] for u in updates) + 1)
        except Exception as e:
            logger.error(f"Error checking Telegram commands: {e}")
            return
        finally:
            self._poll_lock.release()

        # Execute updates outside _poll_lock so commands/confirmations never deadlock!
        for update in updates:
            cb = update.get("callback_query")
            if cb:
                cb_data = cb.get("data", "")
                cb_id = cb.get("id")
                from_user = cb.get("from", {})
                cb_chat_id = str(cb.get("message", {}).get("chat", {}).get("id", self.chat_id))

                is_admin = self._is_user_authorized(from_user, chat_id=cb_chat_id)

                if cb_data.startswith("confirm_") or cb_data.startswith("reject_"):
                    if not is_admin:
                        self.answer_callback(cb_id, "🔒 Access Restricted: Live trade execution is restricted to the administrator.", show_alert=True)
                        continue
                    self._process_trade_confirmation_callback(
                        cb_id=cb_id,
                        cb_data=cb_data,
                        user_info=from_user,
                        chat_id=cb_chat_id
                    )
                    continue

                if cb_data == "execute_emergency_closeall":
                    if not is_admin:
                        self.answer_callback(cb_id, "⛔ Security Veto: Emergency closeall is restricted to the administrator.", show_alert=True)
                        continue
                    self.answer_callback(cb_id, "🚨 Flattening all positions now...")
                    orch = orchestrator or getattr(self, "_active_orchestrator", None)
                    if orch:
                        from src.emergency_controller import EmergencyController
                        ec = EmergencyController(client=orch.client)
                        res = ec.emergency_flatten_all(authorized=True)
                        self.send_message(
                            f"🛑 <b>[EMERGENCY FLATTEN COMPLETE]</b>\n"
                            f"• Flattened <b>{len(res.get('closed_positions', []))}</b> active positions.\n"
                            f"• Cancelled all open orders. Account is 100% in cash USD.",
                            chat_id=cb_chat_id
                        )
                    continue
                elif cb_data == "cancel_emergency_closeall":
                    if not is_admin:
                        self.answer_callback(cb_id, "⛔ Security Veto: Restricted to administrator.", show_alert=True)
                        continue
                    self.answer_callback(cb_id, "Cancelled.")
                    self.send_message("✅ Emergency close cancelled. Protective trailing stops remain active.", chat_id=cb_chat_id)
                    continue
                elif cb_data.startswith("sample_confirm_"):
                    self.answer_callback(cb_id, "✅ Sample trade proposal approved (Demo Mode).")
                    self.send_message("✅ <b>[SAMPLE PROPOSAL CONFIRMED]</b>\n<i>Demonstration successful. In live trading, this triggers pre-execution safety validation and bracket order submission on Delta Exchange.</i>", chat_id=cb_chat_id)
                    continue
                elif cb_data.startswith("sample_reject_"):
                    self.answer_callback(cb_id, "❌ Sample trade proposal declined (Demo Mode).")
                    self.send_message("❌ <b>[SAMPLE PROPOSAL DECLINED]</b>\n<i>Demonstration successful. Capital remained 100% in cash USD.</i>", chat_id=cb_chat_id)
                    continue
                elif cb_data == "sample_proposal_view":
                    self.answer_callback(cb_id, "Sending demonstration proposal...")
                    self.send_sample_proposal(chat_id=cb_chat_id)
                    continue
                elif cb_data.startswith("propose_trade_") or cb_data.startswith("propose_scalp_"):
                    if not is_admin:
                        self.answer_callback(cb_id, "🔒 Trade proposal generation is restricted to the administrator. Type /levels for analysis.", show_alert=True)
                        continue
                    target_sym = cb_data.replace("propose_trade_", "").replace("propose_scalp_", "").strip()
                    self.answer_callback(cb_id, f"🎯 Evaluating live {target_sym} trade proposal...")
                    orch = orchestrator or getattr(self, "_active_orchestrator", None)
                    if orch and hasattr(orch, "propose_on_demand_trade"):
                        def _trade_worker():
                            try:
                                res = orch.propose_on_demand_trade(symbol=target_sym, chat_id=cb_chat_id)
                                if res and not res.get("notified"):
                                    if res.get("status") == "REJECTED":
                                        self.send_message(
                                            f"🛡️ <b>[TRADE PROPOSAL VETOED BY RISK CONTROLLER]</b>\n"
                                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                            f"• <b>Target Symbol:</b> <code>{target_sym}</code>\n"
                                            f"• <b>Evaluation:</b> 🛑 <b>REJECTED IN BACKGROUND</b>\n"
                                            f"• <b>Veto Reason:</b> <code>{res.get('reason', 'Risk parameters exceeded')}</code>\n"
                                            f"• <b>Protection Code:</b> <code>{res.get('code', 'RISK_VETO')}</code>\n"
                                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                            f"💡 <i>Capital protected. Zero risk incurred.</i>",
                                            chat_id=cb_chat_id
                                        )
                                    elif res.get("status") == "FAILED":
                                        self.send_message(
                                            f"⚠️ <b>Trade Evaluation Failed:</b>\n<code>{res.get('reason') or res.get('error')}</code>",
                                            chat_id=cb_chat_id
                                        )
                            except Exception as we:
                                logger.error(f"Error in trade worker thread: {we}", exc_info=True)
                                self.send_message(f"⚠️ Error evaluating {target_sym}: {we}", chat_id=cb_chat_id)

                        threading.Thread(target=_trade_worker, daemon=True).start()
                    else:
                        self.send_message(f"⚠️ Orchestrator unavailable. Cannot generate trade for {target_sym}.", chat_id=cb_chat_id)
                    continue

            msg = update.get("message")
            if not msg:
                continue

            chat_id = str(msg.get("chat", {}).get("id", ""))
            from_user = msg.get("from", {})

            # Role-Based Access Control: Admin vs Public Guest
            is_authorized = self._is_user_authorized(from_user, chat_id=chat_id)

            # Auto-register subscriber in background
            if hasattr(self, "subscriber_manager") and self.subscriber_manager and chat_id:
                try:
                    self.subscriber_manager.register_subscriber(
                        chat_id,
                        user_info=from_user,
                        role="admin" if is_authorized else "guest"
                    )
                except Exception as se:
                    logger.debug(f"Subscriber auto-registration skipped: {se}")

            text = (msg.get("text") or "").strip()
            if not text:
                continue

            cmd, full_text = self._normalize_incoming_command(text)
            role_label = "ADMIN" if is_authorized else "GUEST"
            logger.info(f"Received Telegram command '{cmd}' (normalized from '{text}') from {role_label} in chat {chat_id}")
            orch = orchestrator or getattr(self, "_active_orchestrator", None)
            self._handle_command(cmd, orch, full_text=full_text, chat_id=chat_id, is_admin=is_authorized)

    def _handle_command(
        self,
        cmd: str,
        orchestrator=None,
        full_text: str = "",
        chat_id: Optional[str] = None,
        is_admin: bool = True
    ) -> None:
        """Route user slash command to response."""
        target_chat = chat_id or self.chat_id
        if not orchestrator:
            orchestrator = getattr(self, "_active_orchestrator", None)

        def reply(text: str, reply_markup=None):
            return self.send_message(text, reply_markup=reply_markup, chat_id=target_chat)

        def reply_photo(photo_path_or_bytes: Any, caption: Optional[str] = None):
            return self.send_photo(photo_path_or_bytes, caption=caption, chat_id=target_chat)

        if not orchestrator:
            reply("⚠️ Orchestrator unavailable. Bot is initializing. Please try again in 5 seconds.")
            return

        client = orchestrator.client

        if cmd in ["/status", "/ping", "/balance", "/wallet", "/equity", "/cash"]:
            if not is_admin:
                reply(
                    "🔒 <b>[ACCOUNT BALANCE RESTRICTED]</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Available cash balances, equity, and wallet metrics are private and restricted to the bot administrator.\n\n"
                    "💡 <i>To explore public market analysis and key levels, use <code>/levels</code> or <code>/chart BTC</code>.</i>"
                )
                return

            try:
                wallet = client.get_wallet_balances()
                avail_usd = 0.0
                if isinstance(wallet, dict) and wallet.get("result"):
                    for a in wallet["result"]:
                        if a.get("asset_symbol") in ["USD", "USDT", "USDC"]:
                            avail_usd += float(a.get("available_balance", "0") or 0.0)
                elif isinstance(wallet, dict) and wallet.get("meta", {}).get("net_equity"):
                    avail_usd = float(wallet["meta"]["net_equity"])

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
                status_lines.append("⚡ <i>Type /positions for active trades, /trade to propose, or /levels for chart.</i>")
                reply("\n".join(status_lines))
            except Exception as e:
                reply(f"⚠️ Error fetching status: {e}")

        elif cmd in ["/scan", "/market"]:
            # Route to breakout levels which gives clear, structured market plans and candlestick chart
            self._handle_command("/levels", orchestrator, full_text="/levels", chat_id=target_chat)

        elif cmd in ["/positions", "/pos", "/portfolio", "/openpositions"]:
            if not is_admin:
                reply(
                    "🔒 <b>[PORTFOLIO POSITIONS RESTRICTED]</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Active open positions, entry prices, leverage, and unrealized PnL are private and restricted to the bot administrator.\n\n"
                    "💡 <i>To view public market levels and breakout setups, use <code>/levels</code>.</i>"
                )
                return

            try:
                pos_res = client.get_positions()
                if not pos_res.get("success"):
                    err = pos_res.get("error", "Failed to query Delta Exchange API")
                    err_code = err.get("code") if isinstance(err, dict) else str(err)
                    if "ip_not_whitelisted" in err_code:
                        client_ip = err.get("context", {}).get("client_ip", "") if isinstance(err, dict) else ""
                        reply(
                            f"🔒 <b>[DELTA EXCHANGE IP RESTRICTION DETECTED]</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Issue:</b> Your Delta API Key has IP Whitelisting enabled.\n"
                            f"• <b>Cloud Server IP:</b> <code>{client_ip}</code>\n"
                            f"• <b>Quick Fix:</b> Log into Delta Exchange (Settings → API Keys), edit your key and <b>leave the Allowed IPs / IP Whitelist field completely blank</b> (or allow all IPs).\n"
                            f"• Once saved, your cloud bot will instantly access positions and execute trades 24/7!"
                        )
                    else:
                        reply(f"⚠️ <b>Could not fetch positions from Delta Exchange:</b>\n<code>{err}</code>")
                    return

                active_pos = [p for p in pos_res.get("result", []) if int(p.get("size", 0)) != 0]
                orders_res = client.get_open_orders()
                open_orders = orders_res.get("result", []) if orders_res.get("success") else []

                if not active_pos:
                    reply("📊 <b>No open positions.</b> Capital is 100% in cash USD.")
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
                    reply("\n".join(lines))
            except Exception as e:
                reply(f"⚠️ Error fetching positions: {e}")

        elif cmd in ["/trade", "/proposal", "/propose", "/scalp", "/findtrade", "/find_trade"]:
            if not is_admin:
                reply(
                    "🔒 <b>[TRADE EXECUTION RESTRICTED]</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "• <b>Live Trade Placement:</b> Restricted to the fund administrator.\n"
                    "• <b>Delta Exchange Orders:</b> Disabled for guest users.\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "💡 <i>You can explore live key breakout/breakdown levels using <code>/levels</code> or view live charts with <code>/chart BTC</code>!</i>"
                )
                return

            parts = full_text.strip().split()
            target_sym = None
            requested_side = None

            if len(parts) > 1:
                arg1 = parts[1].upper()
                arg2 = parts[2].upper() if len(parts) > 2 else ""

                if arg1 in ["BUY", "LONG"]:
                    requested_side = "buy"
                    raw_sym = arg2 if arg2 else None
                elif arg1 in ["SELL", "SHORT"]:
                    requested_side = "sell"
                    raw_sym = arg2 if arg2 else None
                else:
                    raw_sym = arg1
                    if arg2 in ["BUY", "LONG"]:
                        requested_side = "buy"
                    elif arg2 in ["SELL", "SHORT"]:
                        requested_side = "sell"

                if raw_sym:
                    # Normalize raw_sym
                    if raw_sym in ["BTC", "BITCOIN"]:
                        target_sym = "BTCUSD"
                    elif raw_sym in ["ETH", "ETHEREUM"]:
                        target_sym = "ETHUSD"
                    elif raw_sym in ["GOLD", "XAU", "PAXG"]:
                        target_sym = "XAUUSD"
                    elif raw_sym in ["SOL", "SOLANA"]:
                        target_sym = "SOLUSD"
                    elif raw_sym in ["XRP", "RIPPLE"]:
                        target_sym = "XRPUSD"
                    elif raw_sym in ["ALL", "AUTO", "ANY", "SCAN"]:
                        target_sym = None
                    elif raw_sym.endswith("USDT"):
                        target_sym = raw_sym[:-1]
                    elif not raw_sym.endswith("USD"):
                        target_sym = f"{raw_sym}USD"
                    else:
                        target_sym = raw_sym

            self._active_command_chat_id = target_chat

            # 1. Emergency Halt Check
            if hasattr(orchestrator, "emergency_controller"):
                is_halted, halt_reason = orchestrator.emergency_controller.is_halted()
                if is_halted:
                    reply(
                        "🛑 <b>[BOT CURRENTLY PAUSED]</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "• <b>Status:</b> Trading is paused via Emergency Controller.\n"
                        f"• <b>Reason:</b> {halt_reason or 'Manual pause active.'}\n"
                        "• <i>Send <code>/resume</code> to re-enable automated trading.</i>"
                    )
                    return

            dir_txt = f" ({requested_side.upper()})" if requested_side else ""
            if target_sym:
                reply(f"🔍 <i>Evaluating live trade setup for <code>{target_sym}</code>{dir_txt}...</i>")
            else:
                reply(f"🔍 <i>Scanning primary assets (BTC, ETH, XAU, SOL){dir_txt} for best trade setup...</i>")

            # Asynchronously dispatch in dedicated worker thread so the Telegram polling listener never freezes!
            def _async_trade_task():
                try:
                    if hasattr(orchestrator, "propose_on_demand_trade"):
                        res = orchestrator.propose_on_demand_trade(symbol=target_sym, side=requested_side, chat_id=target_chat)
                        status = res.get("status", "")
                        code = res.get("code", "")
                        if res.get("notified"):
                            # Detailed rejection or notification already dispatched directly to Telegram
                            pass
                        elif status == "SUCCESS":
                            reply(
                                f"🚀 <b>TRADE EXECUTED ON DELTA EXCHANGE!</b>\n\n"
                                f"• <b>Order ID:</b> <code>#{res.get('order_id')}</code>\n"
                                f"• <b>Contract:</b> <code>{res.get('symbol', target_sym or 'BTCUSD')}</code>\n"
                                f"• <b>Size:</b> <code>{res.get('contracts')}</code> contracts\n"
                                f"• <b>Status:</b> 🟢 <b>PUNCHED & ACTIVE</b> (SL & TP attached)"
                            )
                        elif code == "USER_REJECTED_OR_EXPIRED" or status == "TIMEOUT":
                            pass
                        elif status == "REJECTED":
                            reply(
                                f"🛡️ <b>[TRADE PROPOSAL VETOED BY RISK CONTROLLER]</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"• <b>Target Symbol:</b> <code>{target_sym or 'Universe'}</code>\n"
                                f"• <b>Evaluation:</b> 🛑 <b>REJECTED IN BACKGROUND</b>\n"
                                f"• <b>Veto Reason:</b> <code>{res.get('reason', 'Safety criteria failed')}</code>\n"
                                f"• <b>Protection Code:</b> <code>{code or 'RISK_VETO'}</code>\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"💡 <i>Capital protected. Proposal withheld. Zero risk incurred.</i>"
                            )
                        elif status == "FAILED":
                            reply(f"⚠️ <b>Trade Generation Failed:</b> <code>{res.get('error', res.get('reason', 'Exchange error'))}</code>")
                        else:
                            reply(f"ℹ️ <b>Trade Search Result:</b> <code>{res.get('reason', res.get('code', 'No setup available this cycle.'))}</code>")
                    else:
                        reply("⚠️ Orchestrator does not support on-demand trade generator.")
                except Exception as te:
                    logger.error(f"Error in on-demand trade worker: {te}", exc_info=True)
                    reply(f"⚠️ Error evaluating trade on {target_sym or 'universe'}: {te}")

            threading.Thread(target=_async_trade_task, daemon=True).start()

        elif cmd in ["/radar", "/preradar", "/scalpradar", "/pretrade"]:
            parts = full_text.strip().split()
            target_sym = "BTCUSD"
            if len(parts) > 1:
                raw_sym = parts[1].upper()
                if raw_sym in ["BTC", "BITCOIN"]: target_sym = "BTCUSD"
                elif raw_sym in ["ETH", "ETHEREUM"]: target_sym = "ETHUSD"
                elif raw_sym in ["GOLD", "XAU", "PAXG"]: target_sym = "XAUUSD"
                elif raw_sym in ["SOL", "SOLANA"]: target_sym = "SOLUSD"
                elif raw_sym in ["XRP", "RIPPLE"]: target_sym = "XRPUSD"
                elif not raw_sym.endswith("USD"): target_sym = f"{raw_sym}USD"
                else: target_sym = raw_sym

            # Emergency Halt Check
            if hasattr(orchestrator, "emergency_controller"):
                is_halted, halt_reason = orchestrator.emergency_controller.is_halted()
                if is_halted:
                    reply(
                        "🛑 <b>[BOT CURRENTLY PAUSED]</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        "• <b>Status:</b> Trading is paused via Emergency Controller.\n"
                        f"• <b>Reason:</b> {halt_reason or 'Manual pause active.'}\n"
                        "• <i>Send <code>/resume</code> to re-enable automated trading.</i>"
                    )
                    return

            # Fetch live mark prices for BTC, ETH, XAU
            btc_mark = 0.0
            eth_mark = 0.0
            xau_mark = 0.0
            try:
                for s_chk in ["BTCUSD", "ETHUSD", "XAUUSD"]:
                    t_obj = client.get_ticker(s_chk)
                    if t_obj and t_obj.get("success"):
                        p = float(t_obj.get("result", {}).get("mark_price", 0.0) or 0.0)
                        if s_chk == "BTCUSD": btc_mark = p
                        elif s_chk == "ETHUSD": eth_mark = p
                        elif s_chk == "XAUUSD": xau_mark = p
            except Exception:
                pass

            # Market Posture
            regime = "NEUTRAL"
            try:
                if hasattr(orchestrator, "exposure_coach"):
                    posture_data = orchestrator.exposure_coach.evaluate_market_posture(orchestrator.client)
                    regime = posture_data.get("posture", "NEUTRAL")
                elif hasattr(orchestrator, "regime_analyst"):
                    ra = orchestrator.regime_analyst.analyze_symbol(target_sym, resolution="15")
                    regime = ra.get("regime", "NEUTRAL")
            except Exception:
                pass

            radar_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🎯 Propose BTC Trade", "callback_data": "propose_trade_BTCUSD"},
                        {"text": "🎯 Propose ETH Trade", "callback_data": "propose_trade_ETHUSD"},
                    ],
                    [
                        {"text": "🎯 Propose XAU Trade", "callback_data": "propose_trade_XAUUSD"},
                        {"text": "📋 View Sample Card", "callback_data": "sample_proposal_view"},
                    ]
                ]
            }

            radar_msg = (
                "🛡️ <b>[PRE-TRADE OPPORTUNITY RADAR]</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Active Focus Asset:</b> <code>{target_sym}</code>\n"
                f"• <b>Market Posture:</b> <code>{regime}</code>\n"
                "• <b>Capital Protection:</b> 100% Isolated Margin | Fixed $2–$4 Risk | 1:2.5 Min R:R\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📊 <b>Live Market Prices:</b>\n"
                f"• <b>BTCUSD:</b> <code>${btc_mark:,.2f}</code>\n"
                f"• <b>ETHUSD:</b> <code>${eth_mark:,.2f}</code>\n"
                f"• <b>XAUUSD:</b> <code>${xau_mark:,.2f}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚡ <i>Tap below to instantly generate a trade proposal card, or type <code>/trade &lt;symbol&gt;</code> directly!</i>"
            )
            reply(radar_msg, reply_markup=radar_markup)

        elif cmd in ["/orders", "/orderbook", "/pending"]:
            if not is_admin:
                reply("🔒 <b>[ORDERS RESTRICTED]</b> Pending order details on Delta Exchange are private and restricted to the administrator.")
                return

            try:
                orders_res = client.get_open_orders()
                if not orders_res.get("success"):
                    err = orders_res.get("error", "Failed to query Delta orders")
                    reply(f"⚠️ <b>Could not fetch orders from Delta Exchange:</b>\n<code>{err}</code>")
                    return

                open_orders = orders_res.get("result", [])
                if not open_orders:
                    reply("📋 <b>No pending orders on orderbook.</b>")
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
                    reply("\n".join(lines))
            except Exception as e:
                reply(f"⚠️ Error fetching orders: {e}")

        elif cmd in ["/pause", "/halt", "/stop", "/freeze"]:
            if not is_admin:
                reply("⛔ <b>[SECURITY VETO]</b> Pausing the bot is restricted to the administrator.")
                return

            try:
                from src.emergency_controller import EmergencyController
                ec = EmergencyController(client=client)
                res = ec.engage_emergency_halt("User requested pause via Telegram")
                reply(
                    f"🛑 <b>[TRADING BOT PAUSED BY USER]</b>\n"
                    f"• <b>Status:</b> All new scan entries BLOCKED.\n"
                    f"• <b>Pending Entries Cancelled:</b> {res.get('cancelled_entry_orders_count', 0)}\n"
                    f"• <b>Protection:</b> Active positions Stop Loss verified.\n"
                    f"• <i>Send <code>/resume</code> to re-enable automated scanning.</i>"
                )
            except Exception as e:
                reply(f"⚠️ Error pausing bot: {e}")

        elif cmd in ["/resume", "/unpause", "/start_scanning"]:
            if not is_admin:
                reply("⛔ <b>[SECURITY VETO]</b> Resuming the bot is restricted to the administrator.")
                return

            try:
                from src.emergency_controller import EmergencyController
                ec = EmergencyController(client=client)
                ec.release_emergency_halt("User via Telegram")
                reply(
                    "🟢 <b>[TRADING BOT RESUMED]</b>\n"
                    "• <b>Status:</b> 24/7 Scanning & Trade Evaluation ACTIVE.\n"
                    "• Capital allocation and risk gates re-engaged."
                )
            except Exception as e:
                reply(f"⚠️ Error resuming bot: {e}")

        elif cmd in ["/closeall", "/panic", "/flatten", "/killall"]:
            if not is_admin:
                reply("⛔ <b>[SECURITY VETO]</b> Emergency flatten is restricted to the administrator.")
                return

            try:
                confirm_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "🚨 YES, FLATTEN ALL NOW", "callback_data": "execute_emergency_closeall"},
                            {"text": "❌ Cancel", "callback_data": "cancel_emergency_closeall"}
                        ]
                    ]
                }
                reply(
                    "⚠️ <b>CRITICAL CONFIRMATION REQUIRED:</b>\n"
                    "Are you sure you want to market close ALL active positions and cancel all orders on Delta Exchange?",
                    reply_markup=confirm_markup
                )
            except Exception as e:
                reply(f"⚠️ Error initiating closeall: {e}")

        elif cmd == "/close":
            if not is_admin:
                reply("⛔ <b>[SECURITY VETO]</b> Closing positions is restricted to the administrator.")
                return

            parts = full_text.split()
            if len(parts) < 2:
                reply("⚠️ Please specify symbol to close, e.g.: <code>/close BTCUSD</code> or use <code>/closeall</code>")
            else:
                sym = parts[1].upper()
                if not sym.endswith("USD") and not sym.endswith("USDT"):
                    sym = f"{sym}USD"
                try:
                    reply(f"🛑 <i>Checking position on {sym}...</i>")
                    res = client.close_position(sym)
                    client.cancel_all_orders(symbol=sym)
                    if res.get("success"):
                        if res.get("message") and "No open position" in res.get("message"):
                            reply(f"ℹ️ <b>[CLOSE REJECTED / NO ACTIVE POSITION]</b>\nNo open position found for <code>{sym}</code> on Delta Exchange to close.\nUse <code>/positions</code> to inspect active positions.")
                        else:
                            reply(f"✅ <b>Position on {sym} closed successfully at market.</b> Open bracket orders cancelled.")
                    else:
                        reply(f"⚠️ <b>Could not close {sym}:</b> <code>{res.get('error', 'Unknown error')}</code>")
                except Exception as e:
                    reply(f"⚠️ Error closing {sym}: {e}")

        elif cmd in ["/scorecard", "/learning", "/performance", "/audit"]:
            if not is_admin:
                reply(
                    "🔒 <b>[PERFORMANCE AUDIT RESTRICTED]</b>\n"
                    "Detailed trading history and cumulative dollar PnL are private and restricted to the administrator.\n\n"
                    "💡 <i>Check <code>/levels</code> or <code>/news</code> for live market insights!</i>"
                )
                return

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
                        lines.append(f"  ↳ 💰 <b>Total Reward:</b> <b>${at['reward_usd']:,.2f} USD</b> <i>(Dynamic Target)</i>")
                        lines.append(f"  ↳ ⚖️ <b>Risk to Reward:</b> <b>1 : {at['rr']:.1f}</b> <i>(Win ${at['rr']:.1f} per $1 risked)</i>")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

                # 2. If recent closed trade exists, display its dynamic trade outcome
                elif latest_trade:
                    l_sym = latest_trade.get("symbol", "TRADE")
                    l_side = latest_trade.get("side", "BUY")
                    l_risk = latest_trade.get("risk_usd", 2.0)
                    l_reward = latest_trade.get("reward_usd", 0.0)
                    l_pnl = latest_trade.get("realized_pnl", 0.0)
                    l_outcome = latest_trade.get("outcome", "CLOSED")
                    l_rr = (abs(l_pnl) / l_risk) if (l_risk > 0 and l_pnl != 0) else (l_reward / l_risk if l_risk > 0 else 2.0)
                    pnl_tag = f"+${l_pnl:,.2f} USD" if l_pnl >= 0 else f"-${abs(l_pnl):,.2f} USD"
                    lines.append(f"🏁 <b>LATEST COMPLETED TRADE ({l_sym} {l_side}):</b>")
                    lines.append(f"• 💵 <b>Total Risk Taken:</b> <b>${l_risk:,.2f} USD</b> <i>(Dynamic Sized)</i>")
                    lines.append(f"• 💰 <b>Total Reward Won:</b> <b>{pnl_tag}</b> (<b>{l_outcome}</b>)")
                    lines.append(f"• ⚖️ <b>Risk to Reward:</b> <b>1 : {l_rr:.1f}</b>")
                    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

                else:
                    lines.append("💵 <b>Total Risk Per Trade:</b> <i>Calculated dynamically per setup ($2.00–$4.00 base, scaled up on A+ setups)</i>")
                    lines.append("💰 <b>Total Reward Target:</b> <i>Calculated dynamically per setup (Targeted 1:2 to 1:3 R:R)</i>")
                    lines.append("⚖️ <b>Risk to Reward Ratio:</b> <b>1 : 2.0 to 1 : 3.0</b> <i>(Asymmetric payout)</i>")
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
                reply("\n".join(lines))
            except Exception as e:
                reply(f"⚠️ Error fetching scorecard: {e}")

        elif cmd in ["/posture", "/regime", "/marketposture"]:
            try:
                from multiagent_team.exposure_coach import ExposureCoachAgent
                coach = ExposureCoachAgent()
                msg = coach.format_telegram_posture()
                reply(msg)
            except Exception as e:
                reply(f"⚠️ Error fetching market posture: {e}")

        elif cmd in ["/rules", "/discipline", "/operatingrules"]:
            try:
                from multiagent_team.performance_coach import PerformanceCoachAgent
                coach = PerformanceCoachAgent()
                msg = coach.format_telegram_rules()
                reply(msg)
            except Exception as e:
                reply(f"⚠️ Error fetching operating rules: {e}")

        elif cmd in ["/sample", "/testproposal", "/sampletrade"]:
            try:
                self.send_sample_proposal(chat_id=target_chat)
            except Exception as e:
                reply(f"⚠️ Error sending sample proposal: {e}")

        elif cmd in ["/news", "/briefing", "/morning", "/sentiment"]:
            try:
                reply("🗞️ <i>Generating today's Daily Crypto Morning Briefing &amp; Sentiment Card...</i>")
                from multiagent_team.news_sentiment_agent import NewsSentimentAgent
                agent = NewsSentimentAgent()
                briefing_card = agent.format_daily_morning_briefing()
                reply(briefing_card)
            except Exception as e:
                reply(f"⚠️ Error generating news briefing: {e}")

        elif cmd in ["/levels", "/breakout", "/breakdown", "/keylevels"]:
            try:
                reply("⚡ <i>Calculating critical breakout &amp; breakdown levels across all assets... Please wait.</i>")
                msg = orchestrator.format_market_levels_telegram()
                reply(msg)

                # Generate and dispatch live candlestick chart with levels overlay for BTCUSD
                try:
                    from src.candlestick_chart import generate_candlestick_chart
                    btc_analysis = orchestrator.regime_analyst.analyze_symbol("BTCUSD", resolution="15")
                    candles = btc_analysis.get("_raw_candles_15m") or btc_analysis.get("_raw_candles_1h")
                    if not candles or len(candles.get("c", [])) < 5:
                        c_res = client.get_candles("BTCUSD", resolution="15")
                        if c_res and isinstance(c_res, dict) and c_res.get("result"):
                            c_list = c_res["result"]
                            if isinstance(c_list, list) and len(c_list) >= 5:
                                candles = {
                                    "o": [float(x.get("open", 0)) for x in c_list],
                                    "h": [float(x.get("high", 0)) for x in c_list],
                                    "l": [float(x.get("low", 0)) for x in c_list],
                                    "c": [float(x.get("close", 0)) for x in c_list],
                                    "v": [float(x.get("volume", 0)) for x in c_list],
                                    "t": [int(x.get("time", 0)) for x in c_list],
                                }
                    if candles and len(candles.get("c", [])) >= 5:
                        kl = btc_analysis.get("key_levels_analysis", {})
                        if not kl or not kl.get("current_price"):
                            cur_p = candles["c"][-1]
                            kl = {
                                "current_price": cur_p,
                                "breakout_level": max(candles["h"][-20:]),
                                "breakdown_level": min(candles["l"][-20:]),
                                "status_label": "MONITORING"
                            }
                        chart_path = generate_candlestick_chart(candles, "BTCUSD", key_levels=kl, timeframe_label="15m")
                        cap = (
                            f"📊 <b>[BTCUSD LIVE 15m CANDLESTICK CHART]</b>\n"
                            f"• <b>Mark:</b> <code>${kl.get('current_price', 0):,.2f}</code>\n"
                            f"• <b>Breakout (LONG / UP):</b> <code>${kl.get('breakout_level', 0):,.2f}</code>\n"
                            f"• <b>Breakdown (SHORT / DOWN):</b> <code>${kl.get('breakdown_level', 0):,.2f}</code>"
                        )
                        reply_photo(chart_path, caption=cap)
                except Exception as c_err:
                    logger.debug(f"Chart attachment in /levels skipped: {c_err}")
            except Exception as e:
                reply(f"⚠️ Error calculating market levels: {e}")

        elif cmd in ["/chart", "/candlestick", "/graph"]:
            parts = full_text.split()
            raw_sym = parts[1].upper() if len(parts) > 1 else "BTCUSD"
            # Normalize user-friendly symbols
            if raw_sym in ["BTC", "BITCOIN"]:
                target_sym = "BTCUSD"
            elif raw_sym in ["ETH", "ETHEREUM"]:
                target_sym = "ETHUSD"
            elif raw_sym in ["GOLD", "XAU", "PAXG"]:
                target_sym = "XAUUSD"
            elif raw_sym in ["SOL", "SOLANA"]:
                target_sym = "SOLUSD"
            elif raw_sym in ["XRP", "RIPPLE"]:
                target_sym = "XRPUSD"
            elif raw_sym.endswith("USDT"):
                target_sym = raw_sym[:-1]
            elif not raw_sym.endswith("USD"):
                target_sym = f"{raw_sym}USD"
            else:
                target_sym = raw_sym

            try:
                reply(f"📊 <i>Generating live 15m candlestick chart for {target_sym}...</i>")
                from src.candlestick_chart import generate_candlestick_chart
                regime_analyst = getattr(orchestrator, "regime_analyst", None)
                if not regime_analyst:
                    from multiagent_team.regime_analyst import RegimeAnalystAgent
                    regime_analyst = RegimeAnalystAgent(client=orchestrator.client)

                analysis = regime_analyst.analyze_symbol(target_sym, resolution="15")
                candles = analysis.get("_raw_candles_15m") or analysis.get("_raw_candles_1h")
                if not candles or len(candles.get("c", [])) < 5:
                    c_res = client.get_candles(target_sym, resolution="15")
                    if c_res and isinstance(c_res, dict) and c_res.get("result"):
                        c_list = c_res["result"]
                        if isinstance(c_list, list) and len(c_list) >= 5:
                            candles = {
                                "o": [float(x.get("open", 0)) for x in c_list],
                                "h": [float(x.get("high", 0)) for x in c_list],
                                "l": [float(x.get("low", 0)) for x in c_list],
                                "c": [float(x.get("close", 0)) for x in c_list],
                                "v": [float(x.get("volume", 0)) for x in c_list],
                                "t": [int(x.get("time", 0)) for x in c_list],
                            }

                if not candles or len(candles.get("c", [])) < 5:
                    reply(f"⚠️ Could not fetch sufficient candlestick history for {target_sym}.")
                else:
                    kl = analysis.get("key_levels_analysis", {})
                    cur_price = kl.get("current_price") or (candles["c"][-1] if candles.get("c") else 0.0)
                    bo_level = kl.get("breakout_level") or (max(candles["h"][-20:]) if candles.get("h") else cur_price)
                    bd_level = kl.get("breakdown_level") or (min(candles["l"][-20:]) if candles.get("l") else cur_price)
                    dist_bo = kl.get("distance_to_breakout_pct") or ((bo_level - cur_price) / cur_price * 100.0 if cur_price > 0 else 0.0)
                    dist_bd = kl.get("distance_to_breakdown_pct") or ((cur_price - bd_level) / cur_price * 100.0 if cur_price > 0 else 0.0)
                    st_label = kl.get("status_label") or "ACTIVE_SCAN"

                    chart_kl = {
                        "current_price": cur_price,
                        "breakout_level": bo_level,
                        "breakdown_level": bd_level,
                        "distance_to_breakout_pct": dist_bo,
                        "distance_to_breakdown_pct": dist_bd,
                        "status_label": st_label,
                        "proximity_status": kl.get("proximity_status", ""),
                        "bullish_breakout_plan": kl.get("bullish_breakout_plan", {}),
                        "bearish_breakdown_plan": kl.get("bearish_breakdown_plan", {})
                    }

                    chart_path = generate_candlestick_chart(candles, target_sym, key_levels=chart_kl, timeframe_label="15m")
                    import html
                    st_label_escaped = html.escape(str(st_label))
                    cap = (
                        f"📊 <b>[{target_sym} LIVE CANDLESTICK CHART · 15m]</b>\n"
                        f"• <b>Mark Price:</b> <code>${cur_price:,.2f}</code>\n"
                        f"• <b>Breakout (LONG / UP):</b> <code>${bo_level:,.2f}</code> (+{dist_bo:.2f}%)\n"
                        f"• <b>Breakdown (SHORT / DOWN):</b> <code>${bd_level:,.2f}</code> (-{dist_bd:.2f}%)\n"
                        f"• <b>Status:</b> <b>{st_label_escaped}</b>"
                    )
                    sent = reply_photo(chart_path, caption=cap)
                    if not sent:
                        reply("⚠️ Chart was generated but could not be sent to Telegram. Check bot permissions.")
            except Exception as ce:
                reply(f"⚠️ Error generating candlestick chart: {ce}")

        elif cmd in ["/subscribe", "/sub", "/notify", "/alerts"]:
            if hasattr(self, "subscriber_manager") and self.subscriber_manager:
                self.subscriber_manager.register_subscriber(target_chat, role="admin" if is_admin else "guest", active=True)
            reply(
                "🔔 <b>[SUBSCRIBED TO DELTA AI MARKET INTELLIGENCE]</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "You are registered for automated broadcasts:\n"
                "• 🌅 <b>Daily Morning Crypto Briefing (10:00 AM IST)</b>\n"
                "• ⚡ <b>Pre-Trade Key Levels &amp; Breakout Radar</b>\n"
                "• 📊 <b>Live 15m Candlestick Breakout Charts</b>\n\n"
                "💡 <i>You can query <code>/levels</code>, <code>/news</code>, or <code>/chart BTC</code> anytime. Send <code>/unsubscribe</code> to pause broadcasts.</i>"
            )

        elif cmd in ["/unsubscribe", "/unsub", "/mute", "/optout"]:
            if hasattr(self, "subscriber_manager") and self.subscriber_manager:
                self.subscriber_manager.unregister_subscriber(target_chat)
            reply(
                "🔕 <b>[NOTIFICATIONS PAUSED]</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "You have unsubscribed from automated market broadcasts.\n"
                "You can still access <code>/levels</code>, <code>/news</code>, and <code>/chart</code> on demand anytime!\n\n"
                "💡 <i>Send <code>/subscribe</code> to turn notifications back on.</i>"
            )

        elif cmd in ["/subscribers", "/subs", "/users"]:
            if not is_admin:
                reply("🔒 <b>[RESTRICTED]</b> Subscriber analytics are restricted to the bot administrator.")
                return
            if not hasattr(self, "subscriber_manager") or not self.subscriber_manager:
                reply("⚠️ Subscriber manager unavailable.")
                return
            counts = self.subscriber_manager.count_summary()
            subs = self.subscriber_manager.load_subscribers()
            lines = [
                "👥 <b>[DELTA AI SUBSCRIBER ANALYTICS]</b>",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"• <b>Total Registered:</b> <b>{counts.get('total_registered', 0)}</b>",
                f"• <b>Active Subscribers:</b> <b>{counts.get('active_total', 0)}</b>",
                f"  ↳ Guests: <b>{counts.get('active_guests', 0)}</b> | Admins: <b>{counts.get('active_admins', 0)}</b>",
                f"• <b>Inactive/Muted:</b> <b>{counts.get('inactive', 0)}</b>",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "📋 <b>Recent Active Subscribers:</b>"
            ]
            for s in list(subs.values())[:10]:
                status_icon = "🟢" if s.get("active", True) else "⚪"
                role_tag = "👑 Admin" if s.get("role") == "admin" else "👤 Guest"
                uname = f"@{s.get('username')}" if s.get("username") else s.get("name", "User")
                lines.append(f"{status_icon} <code>{s.get('chat_id')}</code> ({uname}) · {role_tag}")
            reply("\n".join(lines))

        elif cmd in ["/broadcast_levels", "/broadcastlevels"]:
            if not is_admin:
                reply("🔒 <b>[RESTRICTED]</b> Broadcasting is restricted to the administrator.")
                return
            reply("⚡ <i>Broadcasting Market Key Levels &amp; Breakout Radar to all active subscribers...</i>")
            try:
                if hasattr(orchestrator, "check_and_dispatch_daily_market_levels"):
                    orchestrator.check_and_dispatch_daily_market_levels(force=True)
                    reply("✅ <b>Key Levels broadcast complete!</b> Dispatched to all active subscribers.")
                else:
                    reply("⚠️ Orchestrator does not support daily market levels dispatch.")
            except Exception as be:
                reply(f"⚠️ Error broadcasting levels: {be}")

        elif cmd in ["/broadcast_news", "/broadcastnews"]:
            if not is_admin:
                reply("🔒 <b>[RESTRICTED]</b> Broadcasting is restricted to the administrator.")
                return
            reply("🗞️ <i>Broadcasting Daily Morning Crypto Briefing to all active subscribers...</i>")
            try:
                if hasattr(orchestrator, "check_and_dispatch_daily_morning_briefing"):
                    orchestrator.check_and_dispatch_daily_morning_briefing(force=True)
                    reply("✅ <b>Morning News Briefing broadcast complete!</b> Dispatched to all active subscribers.")
                else:
                    reply("⚠️ Orchestrator does not support morning news dispatch.")
            except Exception as be:
                reply(f"⚠️ Error broadcasting news: {be}")

        elif cmd in ["/help", "/start"]:
            if is_admin:
                help_msg = (
                    "📖 <b>[DELTA BOT COMMAND CENTER · ADMIN]</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Essential controls for 24/7 cloud trading:\n\n"
                    "• <code>/trade [symbol]</code> — Propose live trade setup with 15m chart (e.g. <code>/trade BTC</code>)\n"
                    "• <code>/status</code> — 24/7 cloud health, active position count &amp; cash USD\n"
                    "• <code>/positions</code> — View currently active positions, margin &amp; live PnL\n"
                    "• <code>/levels</code> — Breakout &amp; breakdown key levels with candlestick chart\n"
                    "• <code>/chart [symbol]</code> — Live 15m directional candlestick chart\n"
                    "• <code>/close &lt;symbol&gt;</code> — Market close a specific position (e.g. <code>/close BTCUSD</code>)\n"
                    "• <code>/closeall</code> — Emergency flatten all active positions to cash USD\n"
                    "• <code>/orders</code> — Inspect pending limit &amp; bracket orders on Delta\n"
                    "• <code>/news</code> — Daily Crypto Morning Briefing &amp; sentiment index\n"
                    "• <code>/subscribers</code> — View guest &amp; admin broadcast subscribers\n"
                    "• <code>/broadcast_levels</code> — Force broadcast key levels to all subscribers\n"
                    "• <code>/broadcast_news</code> — Force broadcast morning briefing to all subscribers\n"
                    "• <code>/scorecard</code> — Dynamic self-learning audit, win rate &amp; R:R tracking\n"
                    "• <code>/pause</code> / <code>/resume</code> — Pause or resume automated scanning\n"
                    "• <code>/sample</code> — Test interactive confirmation proposal card\n"
                    "• <code>/help</code> — Show this command manual\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🎯 <b>Primary Assets:</b> BTC, ETH, XAU (Gold), SOL\n"
                    "🛡️ <b>Capital Safety:</b> Zero trades execute without your explicit button confirmation."
                )
            else:
                help_msg = (
                    "🌐 <b>[DELTA AI MARKET INTELLIGENCE · GUEST ACCESS]</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Welcome! You have Guest Access to 24/7 institutional crypto analysis:\n\n"
                    "• <code>/levels</code> — Breakout &amp; breakdown key price levels with pre-trade plans &amp; candlestick chart\n"
                    "• <code>/chart &lt;symbol&gt;</code> — Live 15m candlestick chart with levels overlay (e.g. <code>/chart BTC</code>, <code>/chart ETH</code>, <code>/chart XAU</code>)\n"
                    "• <code>/news</code> — Daily Crypto Morning Briefing, market sentiment &amp; Fear/Greed index\n"
                    "• <code>/subscribe</code> — Receive automated morning briefings &amp; pre-trade radar alerts\n"
                    "• <code>/unsubscribe</code> — Pause automated broadcast alerts\n"
                    "• <code>/sample</code> — View demonstration AI trade proposal card\n"
                    "• <code>/help</code> — Show this market intelligence guide\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🎯 <b>Tracked Assets:</b> Bitcoin (BTC), Ethereum (ETH), Gold (XAU), Solana (SOL)\n"
                    "🔒 <b>Security Note:</b> Live trade execution and private portfolio balances are restricted to the fund manager."
                )
            reply(help_msg)

        elif cmd == "/unknown":
            import html
            if is_admin:
                reply(
                    f"❓ <b>Unrecognized Command / Input:</b> <i>\"{html.escape(full_text)}\"</i>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "I didn't recognize that instruction. Here are quick commands you can use:\n\n"
                    "• <code>/trade BTC</code> (or <i>propose trade btc</i>) — Propose live BTC trade\n"
                    "• <code>/trade</code> — Evaluate best setup across primary assets\n"
                    "• <code>/status</code> — System health &amp; cash balances\n"
                    "• <code>/positions</code> — Active running positions &amp; PnL\n"
                    "• <code>/levels</code> — Breakout/breakdown levels &amp; candlestick chart\n"
                    "• <code>/help</code> — Full command center manual\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "💡 <i>Tip: You can use slash commands like <code>/trade btc</code> or plain English phrases.</i>"
                )
            else:
                reply(
                    f"❓ <b>Unrecognized Command / Input:</b> <i>\"{html.escape(full_text)}\"</i>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Here are the market intelligence commands you can use:\n\n"
                    "• <code>/levels</code> — Breakout/breakdown levels &amp; candlestick chart\n"
                    "• <code>/chart BTC</code> — Live 15m candlestick chart for Bitcoin\n"
                    "• <code>/news</code> — Daily market sentiment &amp; Fear/Greed index\n"
                    "• <code>/help</code> — View guest guide\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🔒 <i>Note: Live trading and account balances are restricted to the bot administrator.</i>"
                )

        else:
            reply(
                f"❓ <b>Unrecognized command:</b> <code>{cmd}</code>\n"
                f"Type <code>/help</code> to see all available bot controls and commands."
            )

