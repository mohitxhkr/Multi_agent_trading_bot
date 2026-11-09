"""
Unit tests for Telegram Single-Poller Synchronization and Fast-Path /trade Execution.
Verifies:
1. Single-poller synchronization prevents concurrent getUpdates calls and HTTP 409 conflicts.
2. Callback query in process_incoming_commands immediately wakes up request_trade_confirmation.
3. MultiAgentTradingOrchestrator initializes _active_orchestrator on telegram_bot.
4. Fast-path propose_on_demand_trade generates directional candlestick chart.
5. Asynchronous /trade command routing never blocks the Telegram polling listener.
"""

import unittest
from unittest.mock import MagicMock, patch
import time
import threading
import os

from src.telegram_bot import TelegramConfirmationBot
from multiagent_team.orchestrator import MultiAgentTradingOrchestrator


class TestTelegramSinglePollerAndTrade(unittest.TestCase):
    def setUp(self):
        self.bot = TelegramConfirmationBot(
            bot_token="TEST_BOT_TOKEN",
            chat_id="123456789"
        )
        self.bot.send_message = MagicMock(return_value=999)
        self.bot.edit_message_text = MagicMock(return_value=True)
        self.bot.send_photo = MagicMock(return_value=888)
        self.bot.answer_callback = MagicMock(return_value=True)

    def test_single_poller_skips_inner_getupdates_when_listener_active(self):
        """When a listener thread is actively polling, request_trade_confirmation does NOT call getUpdates."""
        self.bot._poller_last_seen = time.time()  # Active poller

        trade_spec = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 75000.0,
            "stop_loss_price": 74500.0,
            "take_profit_price": 76500.0,
            "contracts": 1,
            "leverage": 25,
            "dollar_risk_usd": 2.50
        }

        with patch("requests.get") as mock_get:
            # Run request_trade_confirmation with short timeout in thread
            result = [None]
            def run():
                result[0] = self.bot.request_trade_confirmation(trade_spec, timeout_seconds=1)

            t = threading.Thread(target=run)
            t.start()
            t.join()

            # mock_get should NEVER have been called for getUpdates because poller was active!
            get_updates_calls = [c for c in mock_get.call_args_list if "getUpdates" in str(c)]
            self.assertEqual(len(get_updates_calls), 0)
            self.assertFalse(result[0])

    def test_callback_unblocks_request_trade_confirmation(self):
        """User tapping Confirm button in process_incoming_commands unblocks waiting request_trade_confirmation."""
        self.bot._poller_last_seen = time.time()
        mock_client = MagicMock()
        mock_client.get_ticker.return_value = {"success": True, "result": {"mark_price": 75000.0}}

        trade_spec = {
            "trade_id": "test_trade_123",
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 75000.0,
            "stop_loss_price": 74500.0,
            "take_profit_price": 76500.0,
            "contracts": 1,
            "leverage": 25,
            "dollar_risk_usd": 2.50
        }

        result = [None]
        def run_confirm():
            result[0] = self.bot.request_trade_confirmation(
                trade_spec,
                timeout_seconds=5,
                client=mock_client
            )

        t = threading.Thread(target=run_confirm)
        t.start()
        time.sleep(0.1)

        # Active confirmation registered
        self.assertIn("test_trade_123", self.bot._active_trade_confirmations)

        # Simulate incoming callback query via process_incoming_commands
        callback_update = {
            "update_id": 100,
            "callback_query": {
                "id": "cb_001",
                "from": {"id": 123456789, "username": "trader"},
                "message": {"chat": {"id": 123456789}, "message_id": 999},
                "data": "confirm_test_trade_123"
            }
        }

        with patch("requests.get") as mock_get:
            mock_res = MagicMock()
            mock_res.json.return_value = {"ok": True, "result": [callback_update]}
            mock_get.return_value = mock_res

            self.bot.process_incoming_commands()

        t.join(timeout=2.0)
        self.assertTrue(result[0], "request_trade_confirmation should return True on confirm callback")
        self.assertIn("test_trade_123", self.bot._confirmed_trade_ids)

    def test_orchestrator_initializes_active_orchestrator_on_telegram_bot(self):
        """MultiAgentTradingOrchestrator sets _active_orchestrator on telegram_bot in __init__."""
        mock_client = MagicMock()
        mock_client.get_positions.return_value = {"success": True, "result": []}
        orch = MultiAgentTradingOrchestrator(client=mock_client, interactive=False)
        self.assertIsNotNone(orch.telegram_bot._active_orchestrator)
        self.assertEqual(orch.telegram_bot._active_orchestrator, orch)

    def test_propose_on_demand_trade_generates_chart_and_passes_safety(self):
        """Fast-path on-demand trade generates directional candlestick chart and passes safety gate."""
        mock_client = MagicMock()
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USD", "balance": 1000.0}]
        }
        mock_client.get_ticker.return_value = {
            "success": True,
            "result": {"mark_price": 75000.0, "symbol": "BTCUSD"}
        }
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": "1",
            "tick_size": "0.1",
            "maintenance_margin_rate": "0.01"
        }
        # Provide sample 15m candles
        now_ts = int(time.time())
        candles = []
        for i in range(20):
            candles.append({
                "open": 74800.0 + i * 10,
                "high": 75100.0 + i * 10,
                "low": 74700.0 + i * 10,
                "close": 75000.0 + i * 10,
                "volume": 100.0,
                "time": now_ts - (20 - i) * 900
            })
        mock_client.get_candles.return_value = {"success": True, "result": candles}

        orch = MultiAgentTradingOrchestrator(client=mock_client, interactive=False)
        # Mock request_trade_confirmation so it does not block
        orch.telegram_bot.request_trade_confirmation = MagicMock(return_value=False)

        res = orch.propose_on_demand_trade(symbol="BTCUSD")
        # request_trade_confirmation was called with trade_spec containing chart_path
        self.assertTrue(orch.telegram_bot.request_trade_confirmation.called)
        trade_spec = orch.telegram_bot.request_trade_confirmation.call_args[1]["trade_spec"]
        self.assertIn("chart_path", trade_spec)
        chart_p = trade_spec["chart_path"]
        self.assertTrue(os.path.exists(chart_p), f"Candlestick chart file should exist at {chart_p}")
        self.assertEqual(trade_spec["symbol"], "BTCUSD")
        self.assertLessEqual(trade_spec.get("dollar_risk_usd", 0.0), 4.0)

    def test_handle_command_trade_is_non_blocking_and_dispatches_async(self):
        """Sending /trade command immediately replies and runs task asynchronously."""
        mock_orch = MagicMock()
        mock_orch.emergency_controller.is_halted.return_value = (False, "")
        mock_orch.propose_on_demand_trade.return_value = {"status": "SUCCESS", "order_id": 99999, "contracts": 1}

        replies = []
        self.bot.send_message = lambda text, *args, **kwargs: replies.append(text)

        t_start = time.time()
        self.bot._handle_command("/trade", orchestrator=mock_orch, full_text="/trade BTC", chat_id="123456789")
        elapsed = time.time() - t_start

        # Should return in <0.05 seconds because worker is async
        self.assertLess(elapsed, 0.1)
        self.assertTrue(any("Evaluating live trade setup" in r for r in replies))


if __name__ == "__main__":
    unittest.main()
