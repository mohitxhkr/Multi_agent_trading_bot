"""
Comprehensive Unit Tests for Historical Win Lot Size Boost and Scale-In (Add to Winner) Logic
"""
import time
import unittest
from unittest.mock import MagicMock, patch

from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.deterministic_safety_controller import DeterministicSafetyController
from multiagent_team.execution_agent import ExecutionAgent
from src.trailing_stop_manager import TrailingStopManager
from src.telegram_bot import TelegramConfirmationBot
from src.risk_manager import RiskManager
from src.state_manager import StateManager


class TestLotBoostAndScaleIn(unittest.TestCase):

    def setUp(self):
        self.risk_mgr = RiskManager(
            max_risk_per_trade_pct=0.01,
            max_dollar_risk_per_trade=4.00
        )

    def test_past_win_streak_boosts_lot_size(self):
        """When symbol or portfolio has a past win streak, conviction multiplier boosts contracts within risk cap."""
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": "1000.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": "1",
            "tick_size": "0.1",
            "maintenance_margin_rate": "0.01"
        }

        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=self.risk_mgr)

        setup = {
            "symbol": "ETHUSD",
            "side": "buy",
            "entry_price": 3000.0,
            "stop_loss_price": 2950.0,  # $50 stop dist -> $0.05 per contract
            "take_profit_price": 3150.0,
            "spread_pct": 0.02,
            "time_machine": {
                "win_rate_pct": 70.0,
                "expected_value_r": 0.45
            }
        }

        # Mock journal with 2-win streak
        mock_journal = {
            "trades": [
                {"symbol": "ETHUSD", "status": "CLOSED", "realized_pnl_usd": 2.50},
                {"symbol": "ETHUSD", "status": "CLOSED", "realized_pnl_usd": 1.80}
            ]
        }

        with patch("src.journal.load_journal", return_value=mock_journal):
            decision = gatekeeper.evaluate_candidate(setup, leverage=25)

        self.assertEqual(decision["gate_decision"], "APPROVED")
        self.assertGreaterEqual(decision["conviction_multiplier"], 1.30)
        self.assertIn("past_win_boost", decision)
        self.assertTrue(decision["past_win_boost"]["applied"])
        self.assertIn("Winning Streak", decision["past_win_boost"]["reason"])
        self.assertLessEqual(decision["dollar_risk_usd"], 4.00)

    def test_safety_controller_approves_scale_in_on_profitable_trade(self):
        """Deterministic Safety Controller approves adding quantity to a winning (profitable) trade."""
        controller = DeterministicSafetyController(risk_manager=self.risk_mgr)

        # Active profitable position on ETHUSD
        active_positions = [
            {
                "symbol": "ETHUSD",
                "size": "10",
                "entry_price": 3000.0,
                "mark_price": 3080.0,
                "unrealized_pnl": 0.80
            }
        ]

        # Second opportunity for enter in same asset
        setup = {
            "symbol": "ETHUSD",
            "side": "buy",
            "contracts": 5,
            "entry_price": 3080.0,
            "stop_loss_price": 3040.0,
            "take_profit_price": 3200.0,
            "leverage": 25,
            "contract_value": 0.001,
            "liq_distance_pct": 5.0
        }

        res = controller.validate_and_issue_token(
            trade_setup=setup,
            account_equity=1000.0,
            active_positions=active_positions
        )

        self.assertTrue(res["passed"], f"Safety check failed: {res.get('reason')}")
        self.assertTrue(setup.get("is_scale_in"))
        self.assertEqual(setup.get("scale_in_parent", {}).get("existing_size"), 10)
        self.assertGreater(setup.get("scale_in_parent", {}).get("unrealized_pnl"), 0)

    def test_safety_controller_rejects_scale_in_on_losing_trade(self):
        """Deterministic Safety Controller strictly forbids adding to a losing position (no averaging down)."""
        controller = DeterministicSafetyController(risk_manager=self.risk_mgr)

        # Active losing position on ETHUSD
        active_positions = [
            {
                "symbol": "ETHUSD",
                "size": "10",
                "entry_price": 3000.0,
                "mark_price": 2950.0,
                "unrealized_pnl": -0.50
            }
        ]

        setup = {
            "symbol": "ETHUSD",
            "side": "buy",
            "contracts": 5,
            "entry_price": 2950.0,
            "stop_loss_price": 2900.0,
            "take_profit_price": 3100.0,
            "leverage": 25,
            "contract_value": 0.001,
            "liq_distance_pct": 5.0
        }

        res = controller.validate_and_issue_token(
            trade_setup=setup,
            account_equity=1000.0,
            active_positions=active_positions
        )

        self.assertFalse(res["passed"])
        self.assertEqual(res["failure_code"], "CRITERION_3_POSITION_ALREADY_EXISTS")
        self.assertIn("losing trade is strictly prohibited", res["reason"])

    def test_safety_controller_rejects_opposite_direction_trade(self):
        """Deterministic Safety Controller rejects opposite direction trade on active asset."""
        controller = DeterministicSafetyController(risk_manager=self.risk_mgr)

        # Active LONG position
        active_positions = [
            {
                "symbol": "ETHUSD",
                "size": "10",
                "entry_price": 3000.0,
                "mark_price": 3080.0,
                "unrealized_pnl": 0.80
            }
        ]

        # Attempting SHORT setup on same symbol
        setup = {
            "symbol": "ETHUSD",
            "side": "sell",
            "contracts": 5,
            "entry_price": 3080.0,
            "stop_loss_price": 3120.0,
            "take_profit_price": 2950.0,
            "leverage": 25,
            "contract_value": 0.001,
            "liq_distance_pct": 5.0
        }

        res = controller.validate_and_issue_token(
            trade_setup=setup,
            account_equity=1000.0,
            active_positions=active_positions
        )

        self.assertFalse(res["passed"])
        self.assertEqual(res["failure_code"], "CRITERION_3_OPPOSITE_POSITION_EXISTS")

    def test_execution_agent_scale_in_order(self):
        """ExecutionAgent places a standard market order for scale-in and edits SL order size."""
        mock_client = MagicMock()
        mock_client.set_leverage.return_value = {"success": True}
        mock_client.place_order.return_value = {
            "success": True,
            "result": {"id": 12345, "state": "filled"}
        }
        mock_client.get_positions.return_value = {
            "success": True,
            "result": [{"symbol": "ETHUSD", "size": "15"}]
        }
        mock_client.get_open_orders.return_value = {
            "success": True,
            "result": [{"id": 99901, "side": "sell", "order_type": "stop_order", "stop_price": 2950.0}]
        }
        mock_client.edit_order.return_value = {"success": True}

        state_mgr = StateManager()
        agent = ExecutionAgent(client=mock_client, state_manager=state_mgr)

        scale_in_decision = {
            "gate_decision": "APPROVED",
            "symbol": "ETHUSD",
            "side": "buy",
            "contracts": 5,
            "entry_price": 3080.0,
            "stop_loss_price": 2950.0,
            "take_profit_price": 3200.0,
            "leverage": 25,
            "is_scale_in": True
        }

        res = agent.execute_approved_trade(scale_in_decision)
        self.assertTrue(res["success"], f"Execution failed: {res}")
        self.assertTrue(res.get("is_scale_in"))
        self.assertEqual(res.get("contracts_added"), 5)
        self.assertEqual(res.get("total_contracts"), 15)

        # Verify place_order was called (NOT place_bracket_order)
        mock_client.place_order.assert_called_once()
        mock_client.place_bracket_order.assert_not_called()
        # Verify edit_order was called to increase SL size
        mock_client.edit_order.assert_called_once_with(symbol="ETHUSD", order_id=99901, size=15)

    def test_trailing_stop_manager_scale_in(self):
        """TrailingStopManager updates contract count and calculates weighted average entry price."""
        mock_client = MagicMock()
        tsm = TrailingStopManager(client=mock_client)

        # Initial trade of 10 contracts @ $3000
        tsm.register_initial_trade(
            symbol="ETHUSD",
            side="buy",
            entry_price=3000.0,
            initial_sl=2950.0,
            initial_tp=3150.0,
            contracts=10
        )

        self.assertEqual(tsm.state["ETHUSD"]["contracts"], 10)
        self.assertEqual(tsm.state["ETHUSD"]["entry_price"], 3000.0)

        # Scale in: add 5 contracts @ $3060
        # Expected new avg entry: (10*3000 + 5*3060) / 15 = 45300 / 15 = 3020.0
        scale_res = tsm.scale_in_trade(
            symbol="ETHUSD",
            additional_contracts=5,
            scale_in_price=3060.0,
            new_sl_order_id=99902
        )

        self.assertTrue(scale_res["success"])
        self.assertEqual(scale_res["total_contracts"], 15)
        self.assertEqual(scale_res["avg_entry"], 3020.0)
        self.assertEqual(tsm.state["ETHUSD"]["contracts"], 15)
        self.assertEqual(tsm.state["ETHUSD"]["entry_price"], 3020.0)
        self.assertEqual(tsm.state["ETHUSD"]["sl_order_id"], 99902)

    def test_telegram_proposal_card_scale_in_and_boost_formatting(self):
        """Telegram proposal card displays SCALE-IN banner, combined size, and past win boost."""
        bot = TelegramConfirmationBot(token="123:ABC", chat_id="456")

        spec = {
            "symbol": "ETHUSD",
            "side": "BUY",
            "entry_price": 3080.0,
            "stop_loss_price": 2950.0,
            "take_profit_price": 3250.0,
            "contracts": 5,
            "leverage": 25,
            "is_scale_in": True,
            "scale_in_parent": {
                "existing_size": 10,
                "unrealized_pnl": 1.45
            },
            "conviction_multiplier": 1.30,
            "past_win_boost": {
                "applied": True,
                "reason": "2-Trade Winning Streak in Past Trades (1.30x Boost)"
            }
        }

        card = bot.format_trade_proposal_card(spec)

        self.assertIn("[SCALE-IN: ADDING TO WINNER]", card)
        self.assertIn("ACTIVE TRADE GOING WELL", card)
        self.assertIn("<b>Existing Position:</b> <code>10 contracts</code>", card)
        self.assertIn("<b>Adding to Winner:</b> <code>+5 contracts</code>", card)
        self.assertIn("<b>New Combined Size:</b> <code>15 contracts</code>", card)
        self.assertIn("PAST WIN LOT BOOST:", card)
        self.assertIn("1.30x (+30% contracts)", card)


if __name__ == "__main__":
    unittest.main()
