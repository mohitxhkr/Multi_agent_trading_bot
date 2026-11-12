import unittest
from unittest.mock import MagicMock, patch
import time

from src.delta_client import DeltaExchangeClient
from src.config import system_config
from src.risk_manager import RiskManager
from multiagent_team.deterministic_safety_controller import DeterministicSafetyController
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.execution_agent import ExecutionAgent
from src.telegram_bot import TelegramConfirmationBot


class TestPaxgAndExecutionReliability(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=DeltaExchangeClient)

    def test_delta_client_max_leverage_and_clamping(self):
        client = DeltaExchangeClient.__new__(DeltaExchangeClient)
        client._products_cache = {
            "PAXGUSD": {
                "id": 169532,
                "symbol": "PAXGUSD",
                "initial_margin": "5",
                "default_leverage": "20.0",
                "ui_config": {"leverage_slider_values": [1, 2, 3, 5, 10, 20]}
            },
            "BTCUSD": {
                "id": 1,
                "symbol": "BTCUSD",
                "initial_margin": "1",
                "default_leverage": "50.0",
                "ui_config": {"leverage_slider_values": [1, 5, 10, 25, 50, 100]}
            }
        }
        client._product_id_map = {"PAXGUSD": 169532, "BTCUSD": 1}
        client._cache_timestamp = time.time()
        client._request = MagicMock(return_value={"success": True})

        # Test get_max_leverage
        paxg_max = client.get_max_leverage("PAXGUSD")
        self.assertEqual(paxg_max, 20)

        btc_max = client.get_max_leverage("BTCUSD")
        self.assertEqual(btc_max, 100)

        # Test set_leverage clamping on PAXGUSD
        client.set_leverage("PAXGUSD", 50)
        client._request.assert_called_with(
            "POST",
            "/v2/products/169532/orders/leverage",
            payload={"leverage": "20"},
            authenticated=True
        )

    def test_delta_client_resolve_symbol_gold_variants(self):
        client = DeltaExchangeClient.__new__(DeltaExchangeClient)
        client._products_cache = {
            "PAXGUSD": {"id": 169532, "symbol": "PAXGUSD"},
            "BTCUSD": {"id": 1, "symbol": "BTCUSD"}
        }
        client._product_id_map = {"PAXGUSD": 169532, "BTCUSD": 1}
        client._cache_timestamp = time.time()
        client.load_products = MagicMock()

        self.assertEqual(client.resolve_symbol("PAXG"), "PAXGUSD")
        self.assertEqual(client.resolve_symbol("PAXGUSD"), "PAXGUSD")

    def test_safety_controller_criterion_9_gold_whitelist(self):
        controller = DeterministicSafetyController()
        candidate = {
            "symbol": "PAXGUSD",
            "side": "buy",
            "entry_price": 3870.0,
            "stop_loss_price": 3840.0,
            "take_profit_price": 3950.0,
            "contracts": 1,
            "leverage": 20,
            "dollar_risk_usd": 3.0,
            "required_margin_usd": 19.35,
            "estimated_liquidation_price": 3680.0
        }

        # Even if default_symbols only has XAUUSD
        with patch.object(system_config, "default_symbols", ["BTCUSD", "ETHUSD", "XAUUSD", "SOLUSD"]):
            res = controller.validate_and_issue_token(
                trade_setup=candidate,
                account_equity=100.0,
                active_positions=[],
                telegram_approval={"approved": True, "expired": False}
            )
            # PAXGUSD must be recognized as valid Gold symbol and NOT fail Criterion 9
            self.assertTrue(res.get("passed"), f"Failed with: {res.get('failure_code')}: {res.get('reason')}")

    def test_risk_gatekeeper_clamps_leverage_to_product_max(self):
        mock_client = MagicMock()
        mock_client.get_max_leverage.return_value = 20
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USD", "balance": "100.0", "available_balance": "100.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "initial_margin": "5",
            "maintenance_margin_rate": "0.02"
        }
        mock_client.resolve_symbol.return_value = "PAXGUSD"

        rm = RiskManager()
        rm.get_account_balance = MagicMock(return_value={"total_usdt": 100.0, "available_usdt": 100.0})
        rm.check_circuit_breaker = MagicMock(return_value={"can_trade": True, "reason": "OK"})
        rm.evaluate_trade_risk = MagicMock(return_value={"status": "APPROVED", "drawdown_warnings": []})

        gatekeeper = RiskGatekeeperAgent(risk_manager=rm, client=mock_client)

        setup = {
            "symbol": "PAXGUSD",
            "side": "buy",
            "entry_price": 3870.0,
            "stop_loss_price": 3840.0,
            "take_profit_price": 3960.0,
            "confluence_score": 85,
            "is_primary": True
        }

        # Request 50x leverage
        decision = gatekeeper.evaluate_candidate(setup, leverage=50)
        self.assertEqual(decision["gate_decision"], "APPROVED")
        # Leverage must be clamped to 20x (PAXGUSD product max)
        self.assertLessEqual(decision["leverage"], 20)

    def test_execution_agent_defensive_bracket_fallback(self):
        mock_client = MagicMock()
        mock_client.get_max_leverage.return_value = 20
        mock_client.set_leverage.return_value = {"success": True}
        mock_client.get_order_by_client_id.return_value = {"success": False}
        # Simulate bracket order failing (e.g. show_bracket_orders: false)
        mock_client.place_bracket_order.return_value = {
            "success": False,
            "error": "bracket_orders_not_supported_for_product"
        }
        # Defensive fallback market order succeeds
        mock_client.place_order.return_value = {
            "success": True,
            "result": {"id": "123456", "state": "filled"}
        }
        mock_client.place_protective_stop.return_value = {
            "success": True,
            "result": {"id": "78910"}
        }
        mock_client.get_open_orders.return_value = {"success": True, "result": []}

        exec_agent = ExecutionAgent(client=mock_client)
        decision = {
            "gate_decision": "APPROVED",
            "symbol": "PAXGUSD",
            "side": "buy",
            "contracts": 1,
            "entry_price": 3870.0,
            "stop_loss_price": 3840.0,
            "take_profit_price": 3960.0,
            "leverage": 25
        }

        token = {"valid": True, "expires_at": time.time() + 30}
        res = exec_agent.execute_approved_trade(decision, execution_token=token)

        self.assertTrue(res.get("success"))
        # Verify set_leverage called with clamped 20x
        mock_client.set_leverage.assert_called_with("PAXGUSD", 20)
        # Verify fallback market order was called
        mock_client.place_order.assert_called()
        # Verify protective stop was placed
        mock_client.place_protective_stop.assert_called()

    def test_telegram_bot_update_proposal_card_status(self):
        bot = TelegramConfirmationBot.__new__(TelegramConfirmationBot)
        bot.bot_token = "mock_token"
        bot.chat_id = "12345"
        bot._proposal_cards = {
            "trade_abc": {
                "msg_id": 999,
                "target_chat": "12345",
                "proposal_text": "<b>PROPOSAL: BUY PAXGUSD</b>\n<i>Tap below to approve or decline</i>"
            }
        }
        bot.edit_message_text = MagicMock(return_value=True)

        # 1. Test EXECUTED
        res = bot.update_proposal_card_status("trade_abc", "EXECUTED", "Order #55555 placed")
        self.assertTrue(res)
        called_args = bot.edit_message_text.call_args[0]
        self.assertIn("ORDER EXECUTED ON DELTA EXCHANGE", called_args[1])
        self.assertIn("Order #55555 placed", called_args[1])

        # 2. Test FAILED
        bot._proposal_cards["trade_abc"]["proposal_text"] = "<b>PROPOSAL: BUY PAXGUSD</b>\n⚡ <b>CONFIRMED BY AUTHORIZED USER! EXECUTING ON DELTA EXCHANGE...</b>"
        res_fail = bot.update_proposal_card_status("trade_abc", "FAILED", "max_leverage_exceeded")
        self.assertTrue(res_fail)
        called_args_fail = bot.edit_message_text.call_args[0]
        self.assertIn("EXECUTION FAILED ON DELTA EXCHANGE", called_args_fail[1])
        self.assertIn("max_leverage_exceeded", called_args_fail[1])

        # 3. Test BLOCKED
        res_blocked = bot.update_proposal_card_status("trade_abc", "BLOCKED", "CRITERION_9_UNAPPROVED_SYMBOL")
        self.assertTrue(res_blocked)
        called_args_blocked = bot.edit_message_text.call_args[0]
        self.assertIn("EXECUTION BLOCKED BY SAFETY GATE", called_args_blocked[1])

    def test_proposal_card_shows_backtest_data_for_all_samples(self):
        bot = TelegramConfirmationBot.__new__(TelegramConfirmationBot)
        
        # Test case 1: 4 samples (previously suppressed because sample_size < 6)
        spec_4_samples = {
            "symbol": "PAXGUSD",
            "side": "BUY",
            "entry_price": 3870.0,
            "stop_loss_price": 3840.0,
            "take_profit_price": 3950.0,
            "reward_to_risk_ratio": 2.7,
            "contracts": 1,
            "leverage": 20,
            "required_margin_usd": 19.35,
            "dollar_risk_usd": 3.0,
            "strategy": "Institutional_SSL_Sweep",
            "score": 88,
            "time_machine": {
                "sample_size": 4,
                "wins": 3,
                "losses": 1,
                "win_rate_pct": 75.0,
                "expected_value_r": 1.25,
                "profit_factor": 2.5
            }
        }
        card_text = bot.format_trade_proposal_card(spec_4_samples)
        self.assertIn("Empirical Backtest", card_text)
        self.assertIn("75% Win Rate", card_text)
        self.assertIn("3W / 1L across <b>4 matches</b>", card_text)
        self.assertIn("Net EV: <b>+1.25R</b>", card_text)
        self.assertIn("PF: <b>2.5x</b>", card_text)
        self.assertNotIn("Market Edge: Multi-Timeframe SMC Confluence Aligned", card_text)

        # Test case 2: top-level win_rate_pct without nested dict
        spec_top_level = {
            "symbol": "BTCUSD",
            "side": "BUY",
            "entry_price": 75000.0,
            "stop_loss_price": 74500.0,
            "take_profit_price": 76500.0,
            "win_rate_pct": 68.0,
            "reward_to_risk_ratio": 3.0,
            "contracts": 1,
            "leverage": 50,
            "dollar_risk_usd": 2.0,
            "strategy": "FVG_Sweep"
        }
        card_text_top = bot.format_trade_proposal_card(spec_top_level)
        self.assertIn("Empirical Backtest", card_text_top)
        self.assertIn("68% Win Rate", card_text_top)

    def test_time_machine_breakeven_friction_does_not_artificially_veto_high_win_rate_trades(self):
        from multiagent_team.time_machine_agent import TimeMachineAgent
        tm = TimeMachineAgent(client=None)

        # 3 Wins, 1 Loss, 8 Breakevens (75% WR on decisive trades)
        matches = [
            {"outcome": "WIN", "gross_return_pct": 0.02, "net_return_pct": 0.0184, "gross_r": 2.0, "net_r": 1.84, "max_adverse_pct": 0.1, "bars_held": 5, "bar_index": 50},
            {"outcome": "WIN", "gross_return_pct": 0.02, "net_return_pct": 0.0184, "gross_r": 2.0, "net_r": 1.84, "max_adverse_pct": 0.1, "bars_held": 5, "bar_index": 70},
            {"outcome": "WIN", "gross_return_pct": 0.02, "net_return_pct": 0.0184, "gross_r": 2.0, "net_r": 1.84, "max_adverse_pct": 0.1, "bars_held": 5, "bar_index": 90},
            {"outcome": "LOSS", "gross_return_pct": -0.01, "net_return_pct": -0.0116, "gross_r": -1.0, "net_r": -1.16, "max_adverse_pct": 1.0, "bars_held": 4, "bar_index": 110},
        ]
        # 8 Breakevens (gross return 0.0, net return -0.0016 after friction)
        for idx in range(8):
            matches.append({
                "outcome": "BREAKEVEN", "gross_return_pct": 0.0, "net_return_pct": -0.0016, "gross_r": 0.0, "net_r": -0.16, "max_adverse_pct": 0.3, "bars_held": 3, "bar_index": 130 + idx * 10
            })

        # Calculate decisive metrics
        decisive_matches = [m for m in matches if m["outcome"] in ("WIN", "LOSS")]
        decisive_ev_r = round(sum(m["net_r"] for m in decisive_matches) / len(decisive_matches), 2)
        decisive_losses = abs(sum(m["net_return_pct"] for m in matches if m["outcome"] == "LOSS"))
        gross_profits = sum(m["net_return_pct"] for m in matches if m["net_return_pct"] > 0)
        decisive_pf = round(gross_profits / decisive_losses, 2)
        
        real_losses = abs(sum(m["net_return_pct"] for m in matches if m["outcome"] in ("LOSS", "TIMEOUT") and m["net_return_pct"] < 0))
        pf = round(gross_profits / real_losses, 2)

        self.assertEqual(len(decisive_matches), 4)
        self.assertAlmostEqual(decisive_pf, 4.76, delta=0.1)
        self.assertAlmostEqual(pf, 4.76, delta=0.1)
        self.assertGreater(decisive_ev_r, 1.0)


if __name__ == "__main__":
    unittest.main()
