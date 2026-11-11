"""
Unit tests for Telegram Two-Way Communication & Rejection Notifications.
Ensures no commands or proposed trades are silently suppressed in the background.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.telegram_bot import TelegramConfirmationBot
from src.telegram_subscriber_manager import TelegramSubscriberManager
from multiagent_team.orchestrator import MultiAgentTradingOrchestrator


class TestTelegramTwoWayRejections(unittest.TestCase):
    def setUp(self):
        self._sub_tmp = tempfile.TemporaryDirectory()
        self.bot = TelegramConfirmationBot(
            bot_token="TEST_BOT_TOKEN",
            chat_id="123456789",
            authorized_users=[123456789]
        )
        self.bot.subscriber_manager = TelegramSubscriberManager(
            subscribers_file=os.path.join(self._sub_tmp.name, "subs.json")
        )

    def tearDown(self):
        self._sub_tmp.cleanup()

    def test_normalize_natural_language_and_typos(self):
        """Verify natural language trade commands and typos are normalized to /trade."""
        # Common typos and phrases
        cmd, full = self.bot._normalize_incoming_command("propse trade btc")
        self.assertEqual(cmd, "/trade")
        self.assertEqual(full, "/trade BTCUSD")

        cmd, full = self.bot._normalize_incoming_command("propose trade btc buy")
        self.assertEqual(cmd, "/trade")
        self.assertEqual(full, "/trade BTCUSD buy")

        cmd, full = self.bot._normalize_incoming_command("trade eth short")
        self.assertEqual(cmd, "/trade")
        self.assertEqual(full, "/trade ETHUSD sell")

        cmd, full = self.bot._normalize_incoming_command("propose scalp gold")
        self.assertEqual(cmd, "/trade")
        self.assertEqual(full, "/trade XAUUSD")

        cmd, full = self.bot._normalize_incoming_command("find trade")
        self.assertEqual(cmd, "/trade")
        self.assertEqual(full, "/trade")

        # Standard slash command preserved
        cmd, full = self.bot._normalize_incoming_command("/trade BTCUSD")
        self.assertEqual(cmd, "/trade")
        self.assertEqual(full, "/trade BTCUSD")

        # Other plain controls
        cmd, full = self.bot._normalize_incoming_command("status")
        self.assertEqual(cmd, "/status")

        cmd, full = self.bot._normalize_incoming_command("positions")
        self.assertEqual(cmd, "/positions")

        cmd, full = self.bot._normalize_incoming_command("close btc")
        self.assertEqual(cmd, "/close")
        self.assertEqual(full, "/close BTCUSD")

        cmd, full = self.bot._normalize_incoming_command("closeall")
        self.assertEqual(cmd, "/closeall")

        # Unrecognized message routes to /unknown
        cmd, full = self.bot._normalize_incoming_command("random unrecognized text 12345")
        self.assertEqual(cmd, "/unknown")
        self.assertEqual(full, "random unrecognized text 12345")

    def test_unknown_command_feedback(self):
        """Verify unrecognized input receives clear help options rather than being ignored."""
        sent_messages = []
        self.bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))
        mock_orch = MagicMock()

        self.bot._handle_command("/unknown", mock_orch, full_text="random gibberish", chat_id="123456789")

        self.assertTrue(len(sent_messages) > 0)
        self.assertIn("Unrecognized Command / Input", sent_messages[0])
        self.assertIn("propose trade btc", sent_messages[0])
        self.assertIn("/trade", sent_messages[0])

    def test_close_command_when_no_position_exists(self):
        """Verify /close informs user when no active position exists instead of falsely reporting closure."""
        sent_messages = []
        self.bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))

        mock_orch = MagicMock()
        mock_orch.client.close_position.return_value = {
            "success": True,
            "message": "No open position found for BTCUSD"
        }

        self.bot._handle_command("/close", mock_orch, full_text="/close BTCUSD", chat_id="123456789")

        self.assertTrue(len(sent_messages) >= 2)
        final_msg = sent_messages[-1]
        self.assertIn("CLOSE REJECTED / NO ACTIVE POSITION", final_msg)
        self.assertIn("BTCUSD", final_msg)

    def test_orchestrator_propose_trade_rejection_dispatches_telegram_card(self):
        """Verify propose_on_demand_trade sends an explicit rejection card when a trade is vetoed."""
        sent_messages = []
        mock_bot = MagicMock()
        mock_bot.is_configured = True
        mock_bot.chat_id = "123456789"
        mock_bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))

        mock_client = MagicMock()
        # Mock active losing position on BTCUSD
        mock_client.get_positions.return_value = {
            "success": True,
            "result": [
                {
                    "symbol": "BTCUSD",
                    "product_symbol": "BTCUSD",
                    "size": "10",
                    "unrealized_pnl": "-1.50"
                }
            ]
        }

        orch = MultiAgentTradingOrchestrator(interactive=False, client=mock_client)
        orch.telegram_bot = mock_bot

        # Request trade on BTCUSD while losing position exists
        res = orch.propose_on_demand_trade(symbol="BTCUSD", chat_id="123456789")

        self.assertEqual(res.get("status"), "REJECTED")
        self.assertEqual(res.get("code"), "POSITION_ALREADY_EXISTS")
        self.assertTrue(res.get("notified"))

        # Check that an explicit rejection notification was dispatched to Telegram
        self.assertTrue(len(sent_messages) > 0)
        rejection_text = sent_messages[0]
        self.assertIn("TRADE PROPOSAL VETOED BY RISK CONTROLLER", rejection_text)
        self.assertIn("BTCUSD", rejection_text)
        self.assertIn("POSITION_ALREADY_EXISTS", rejection_text)
        self.assertIn("Capital protected", rejection_text)

    def test_propose_trade_emergency_halt_rejection_notification(self):
        """Verify propose_on_demand_trade notifies Telegram when bot is halted."""
        sent_messages = []
        mock_bot = MagicMock()
        mock_bot.is_configured = True
        mock_bot.chat_id = "123456789"
        mock_bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))

        mock_client = MagicMock()

        orch = MultiAgentTradingOrchestrator(interactive=False, client=mock_client)
        orch.telegram_bot = mock_bot
        orch.emergency_controller.is_halted = MagicMock(return_value=(True, "High daily loss limit breached"))

        res = orch.propose_on_demand_trade(symbol="BTCUSD", chat_id="123456789")

        self.assertEqual(res.get("status"), "SKIPPED")
        self.assertEqual(res.get("code"), "EMERGENCY_HALT_ACTIVE")
        self.assertTrue(res.get("notified"))

        self.assertTrue(len(sent_messages) > 0)
        self.assertIn("TRADE PROPOSAL VETOED BY RISK CONTROLLER", sent_messages[0])
        self.assertIn("EMERGENCY_HALT_ACTIVE", sent_messages[0])

    def test_guest_can_access_public_market_intelligence(self):
        """Verify guest user can access /levels, /news, /help, /chart without restriction."""
        sent_messages = []
        self.bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))
        mock_orch = MagicMock()
        mock_orch.format_market_levels_telegram.return_value = "⚡ BTC Breakout Levels Analysis"

        # 1. /levels
        self.bot._handle_command("/levels", mock_orch, full_text="/levels", chat_id="999999", is_admin=False)
        self.assertTrue(any("Breakout Levels" in m for m in sent_messages))

        # 2. /help for guest
        sent_messages.clear()
        self.bot._handle_command("/help", mock_orch, full_text="/help", chat_id="999999", is_admin=False)
        self.assertTrue(any("GUEST ACCESS" in m for m in sent_messages))
        self.assertTrue(any("Security Note" in m for m in sent_messages))

    def test_guest_blocked_from_private_balances_and_trading(self):
        """Verify guest user is blocked from viewing balances, running positions, or placing trades."""
        sent_messages = []
        self.bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))
        mock_orch = MagicMock()

        # 1. /status & /balance blocked
        self.bot._handle_command("/status", mock_orch, full_text="/status", chat_id="999999", is_admin=False)
        self.assertIn("ACCOUNT BALANCE RESTRICTED", sent_messages[-1])

        # 2. /positions blocked
        self.bot._handle_command("/positions", mock_orch, full_text="/positions", chat_id="999999", is_admin=False)
        self.assertIn("PORTFOLIO POSITIONS RESTRICTED", sent_messages[-1])

        # 3. /trade blocked
        self.bot._handle_command("/trade", mock_orch, full_text="/trade BTC", chat_id="999999", is_admin=False)
        self.assertIn("TRADE EXECUTION RESTRICTED", sent_messages[-1])

        # 4. /close & /closeall blocked
        self.bot._handle_command("/close", mock_orch, full_text="/close BTCUSD", chat_id="999999", is_admin=False)
        self.assertIn("SECURITY VETO", sent_messages[-1])

        self.bot._handle_command("/closeall", mock_orch, full_text="/closeall", chat_id="999999", is_admin=False)
        self.assertIn("SECURITY VETO", sent_messages[-1])

    def test_guest_subscribe_and_unsubscribe(self):
        """Verify guest user can subscribe and unsubscribe to automated notifications."""
        sent_messages = []
        self.bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))
        mock_orch = MagicMock()

        # 1. /subscribe
        self.bot._handle_command("/subscribe", mock_orch, full_text="/subscribe", chat_id="888888", is_admin=False)
        self.assertIn("SUBSCRIBED TO DELTA AI MARKET INTELLIGENCE", sent_messages[-1])
        self.assertIn("Daily Morning Crypto Briefing", sent_messages[-1])

        # 2. /unsubscribe
        self.bot._handle_command("/unsubscribe", mock_orch, full_text="/unsubscribe", chat_id="888888", is_admin=False)
        self.assertIn("NOTIFICATIONS PAUSED", sent_messages[-1])

    def test_admin_subscriber_controls_and_broadcasting(self):
        """Verify admin can view subscriber stats and broadcast, while guest is restricted."""
        sent_messages = []
        self.bot.send_message = MagicMock(side_effect=lambda text, **kwargs: sent_messages.append(text))
        mock_orch = MagicMock()

        # Guest blocked from /subscribers
        self.bot._handle_command("/subscribers", mock_orch, full_text="/subscribers", chat_id="999999", is_admin=False)
        self.assertIn("RESTRICTED", sent_messages[-1])

        # Guest blocked from /broadcast_levels
        self.bot._handle_command("/broadcast_levels", mock_orch, full_text="/broadcast_levels", chat_id="999999", is_admin=False)
        self.assertIn("RESTRICTED", sent_messages[-1])

        # Admin can view /subscribers
        sent_messages.clear()
        self.bot._handle_command("/subscribers", mock_orch, full_text="/subscribers", chat_id="123456789", is_admin=True)
        self.assertTrue(any("DELTA AI SUBSCRIBER ANALYTICS" in m for m in sent_messages))

        # Admin can broadcast levels
        sent_messages.clear()
        self.bot._handle_command("/broadcast_levels", mock_orch, full_text="/broadcast_levels", chat_id="123456789", is_admin=True)
        self.assertTrue(any("broadcast complete" in m for m in sent_messages))


if __name__ == "__main__":
    unittest.main()
