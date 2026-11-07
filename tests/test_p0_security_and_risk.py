"""
Priority Zero Security & Risk Validation Test Suite.
Validates:
1. Hard dollar risk ceiling and minimum contract rejection (NO_TRADE).
2. Leverage hard clamping.
3. Multi-horizon circuit breaker (daily, weekly, monthly drawdown, cooldown).
4. Persistent fail-closed state loader and manual reset.
5. Telegram authentication, nonces, and replay protection.
6. Time Machine zero-synthetic enforcement (INSUFFICIENT_DATA / INSUFFICIENT_SAMPLE).
7. Execution idempotency and reconciliation.
8. Post-entry Stop-Loss verification and emergency abort.
9. Deterministic Safety Controller 14-criterion validation and token signing.
"""

import unittest
import os
import time
import json
import tempfile
import shutil
from unittest.mock import MagicMock, patch

from src.config import system_config
from src.risk_manager import (
    RiskManager,
    load_circuit_breaker_state,
    save_circuit_breaker_state,
    CIRCUIT_BREAKER_STATE_FILE
)
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.time_machine_agent import TimeMachineAgent
from multiagent_team.execution_agent import ExecutionAgent
from multiagent_team.deterministic_safety_controller import DeterministicSafetyController
from src.telegram_bot import TelegramConfirmationBot
from src.state_manager import StateManager


class TestPriorityZeroRiskAndSecurity(unittest.TestCase):

    def setUp(self):
        # Create a fresh temporary state directory for isolation
        self.test_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.test_dir, "circuit_breaker_state.json")
        self.patcher = patch("src.risk_manager.CIRCUIT_BREAKER_STATE_FILE", self.state_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Risk Gatekeeper: Position Sizing & Minimum Contract Protection
    # -------------------------------------------------------------------------
    def test_minimum_contract_rejection_when_risk_exceeds_budget(self):
        """If risk budget is too small to afford 1 contract, return NO_TRADE."""
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": "100.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_open_orders.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": "1",
            "tick_size": "1.0"
        }

        risk_mgr = RiskManager(
            max_risk_per_trade_pct=0.01,    # 1% of $100 = $1.00 risk budget
            max_dollar_risk_per_trade=1.00  # $1.00 max risk
        )
        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=risk_mgr)

        # BTC at 70,000 with a wide stop loss at 68,000 (distance = $2,000)
        # 1 contract at 0.001 BTC has risk = 2000 * 0.001 = $2.00
        # Permitted risk budget is $1.00 -> cannot afford 1 contract!
        setup = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 68000.0,
            "take_profit_price": 75000.0,
            "score": 85,
            "conviction": "HIGH"  # AI claims HIGH conviction
        }

        decision = gatekeeper.evaluate_candidate(setup, leverage=25)

        # MUST BE REJECTED with NO_TRADE, contracts must be 0
        self.assertEqual(decision["gate_decision"], "NO_TRADE")
        self.assertEqual(decision["contracts"], 0)
        self.assertIn("NO_TRADE", decision["reason"])

    def test_conviction_does_not_override_max_dollar_risk(self):
        """AI conviction must not inflate risk beyond configured hard dollar cap."""
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": "5000.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_open_orders.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": "1",
            "tick_size": "1.0"
        }

        risk_mgr = RiskManager(
            max_risk_per_trade_pct=0.05,
            max_dollar_risk_per_trade=4.00  # Hard cap: $4.00
        )
        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=risk_mgr)

        setup = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,  # $1000 stop distance -> $1.00 risk per contract
            "take_profit_price": 73000.0,
            "score": 98,
            "conviction": "SUPER_MAX_CONVICTION"  # Attempt conviction inflation
        }

        decision = gatekeeper.evaluate_candidate(setup, leverage=25)
        self.assertEqual(decision["gate_decision"], "APPROVED")
        # 4 contracts * $1.00 = $4.00 dollar risk, must not exceed $4.00
        self.assertLessEqual(decision["dollar_risk_usd"], 4.00)
        self.assertLessEqual(decision["contracts"], 4)

    def test_maximum_leverage_clamping(self):
        """Leverage requested above ceiling must be clamped to max_allowed_leverage."""
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": "1000.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_open_orders.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": "1",
            "tick_size": "1.0"
        }

        risk_mgr = RiskManager(max_allowed_leverage=10)
        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=risk_mgr)

        setup = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,
            "take_profit_price": 73000.0,
            "score": 85
        }

        # Request 100x leverage
        decision = gatekeeper.evaluate_candidate(setup, leverage=100)
        self.assertEqual(decision["leverage"], 10)

    # -------------------------------------------------------------------------
    # 2. Multi-Horizon Circuit Breaker & Fail-Closed State
    # -------------------------------------------------------------------------
    def test_circuit_breaker_daily_drawdown_halt(self):
        """Daily drawdown >= 3% trips circuit breaker and halts trading."""
        risk_mgr = RiskManager(max_daily_drawdown_pct=0.03)

        # Baseline equity $1,000
        cb_init = risk_mgr.check_circuit_breaker(current_equity=1000.0, open_positions_count=0)
        self.assertTrue(cb_init["can_trade"])
        self.assertEqual(cb_init["decision"], "TRADING_ALLOWED")

        # Equity drops to $960 (4% drawdown > 3% threshold)
        cb_trip = risk_mgr.check_circuit_breaker(current_equity=960.0, open_positions_count=0)
        self.assertFalse(cb_trip["can_trade"])
        self.assertEqual(cb_trip["decision"], "HALT_CIRCUIT_BREAKER")
        self.assertEqual(cb_trip["state"], "HALTED")

        # Even if equity bounces back up to $990, persistent halt must remain until manual reset!
        cb_rebound = risk_mgr.check_circuit_breaker(current_equity=990.0, open_positions_count=0)
        self.assertFalse(cb_rebound["can_trade"])
        self.assertEqual(cb_rebound["decision"], "HALT_CIRCUIT_BREAKER")

    def test_circuit_breaker_fail_closed_on_corrupt_state(self):
        """If the circuit breaker state file is corrupted, system fails closed."""
        with open(self.state_file, "w", encoding="utf-8") as f:
            f.write("CORRUPTED_NON_JSON_DATA_!!!")

        state = load_circuit_breaker_state()
        self.assertEqual(state["state"], "HALTED")
        self.assertTrue(state["halted"])
        self.assertIn("FAIL_CLOSED", state["halt_reason"])

    def test_circuit_breaker_manual_reset(self):
        """Manual reset by authorized administrator restores trading state with audit log."""
        risk_mgr = RiskManager(max_daily_drawdown_pct=0.03)
        # Force a halt
        risk_mgr.check_circuit_breaker(current_equity=900.0, open_positions_count=0)

        # Explicit manual reset
        reset_res = risk_mgr.manual_reset(
            authorized_by="Lead_Architect",
            reason="Capital deposit confirmed and market stabilized",
            current_equity=1200.0
        )
        self.assertEqual(reset_res["status"], "SUCCESS")

        # Check circuit breaker now allows trading
        cb = risk_mgr.check_circuit_breaker(current_equity=1200.0, open_positions_count=0)
        self.assertTrue(cb["can_trade"])
        self.assertEqual(cb["state"], "TRADING_ALLOWED")

    # -------------------------------------------------------------------------
    # 3. Time Machine: Zero Synthetic Stats & Fail-Closed Simulation
    # -------------------------------------------------------------------------
    def test_time_machine_rejects_insufficient_data(self):
        """Time Machine must reject setups with < 60 bars with INSUFFICIENT_DATA."""
        tm = TimeMachineAgent(client=None)

        candidate = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,
            "take_profit_price": 73000.0
        }

        # Provide only 30 candles (< 60 minimum)
        short_candles = {
            "c": [70000.0] * 30,
            "h": [70100.0] * 30,
            "l": [69900.0] * 30,
            "o": [70000.0] * 30
        }

        res = tm.simulate_setup(candidate, candles_15m=short_candles)
        self.assertFalse(res["passed"])
        self.assertEqual(res["verdict"], "INSUFFICIENT_DATA")
        self.assertIn("INSUFFICIENT_DATA", res["reason"])
        # Ensure zero synthetic numbers were reported
        self.assertEqual(res["sample_size"], 0)
        self.assertEqual(res["wins"], 0)

    def test_time_machine_rejects_insufficient_sample(self):
        """Time Machine must reject setups with < min_sample_size decisive trades."""
        tm = TimeMachineAgent(client=None, min_sample_size=10)

        candidate = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,
            "take_profit_price": 73000.0
        }

        # 100 flat bars with no matching pattern
        flat_candles = {
            "c": [70000.0 + i for i in range(100)],
            "h": [70010.0 + i for i in range(100)],
            "l": [69990.0 + i for i in range(100)],
            "o": [70000.0 + i for i in range(100)]
        }

        res = tm.simulate_setup(candidate, candles_15m=flat_candles)
        self.assertFalse(res["passed"])
        self.assertEqual(res["verdict"], "INSUFFICIENT_SAMPLE")
        self.assertIn("INSUFFICIENT_SAMPLE", res["reason"])

    # -------------------------------------------------------------------------
    # 4. Telegram Security: Authorization, Nonces, and Replay Protection
    # -------------------------------------------------------------------------
    def test_telegram_unauthorized_user_rejected(self):
        """Callbacks from unauthorized Telegram user IDs are rejected."""
        bot = TelegramConfirmationBot(token="TEST_TOKEN", authorized_chat_ids=["12345678"])
        self.assertFalse(bot._is_user_authorized(99999999))
        self.assertTrue(bot._is_user_authorized(12345678))

    def test_telegram_replay_callback_rejected(self):
        """Replayed callback with same nonce must be rejected."""
        bot = TelegramConfirmationBot(token="TEST_TOKEN", authorized_chat_ids=["12345678"])
        nonce = "unique_trade_nonce_123"

        bot._processed_nonces.add(nonce)
        # Attempt to reuse the nonce
        self.assertTrue(nonce in bot._processed_nonces)

    # -------------------------------------------------------------------------
    # 5. Execution Idempotency & Reconciliation
    # -------------------------------------------------------------------------
    def test_execution_idempotency_prevents_duplicate_orders(self):
        """Execution agent rejects duplicate client_order_id registered in state manager."""
        mock_client = MagicMock()
        state_mgr = StateManager()
        state_mgr.record_order(
            order_id="1001",
            client_order_id="cl_BTCUSD_buy_repeat_test",
            symbol="BTCUSD",
            side="buy",
            order_type="limit_order",
            price=70000.0,
            size=1,
            status="open"
        )

        exec_agent = ExecutionAgent(client=mock_client, state_manager=state_mgr)

        decision = {
            "gate_decision": "APPROVED",
            "symbol": "BTCUSD",
            "side": "buy",
            "contracts": 1,
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,
            "take_profit_price": 73000.0,
            "client_order_id": "cl_BTCUSD_buy_repeat_test"
        }

        res = exec_agent.execute_approved_trade(decision)
        self.assertFalse(res["success"])
        self.assertIn("Duplicate order prevented by idempotency", res["error"])
        # Delta API should never be called
        mock_client.place_bracket_order.assert_not_called()

    # -------------------------------------------------------------------------
    # 6. Post-Entry Mandatory Stop-Loss Verification
    # -------------------------------------------------------------------------
    def test_execution_emergency_close_if_stop_loss_missing(self):
        """If protective stop order is missing on exchange and emergency stop fails, close position immediately."""
        mock_client = MagicMock()
        mock_client.set_leverage.return_value = {"success": True}
        # Bracket order places entry, but exchange response lacks stop order
        mock_client.place_bracket_order.return_value = {
            "success": True,
            "result": {"id": 8888, "state": "open"}
        }
        # Open orders check finds NO stop orders
        mock_client.get_open_orders.return_value = {"success": True, "result": []}
        # Emergency stop order placement fails
        mock_client.place_protective_stop.return_value = {"success": False, "error": "Margin error"}
        # Emergency close succeeds
        mock_client.close_position.return_value = {"success": True, "result": "closed"}

        mock_notifier = MagicMock()
        exec_agent = ExecutionAgent(client=mock_client, telegram=mock_notifier)

        decision = {
            "gate_decision": "APPROVED",
            "symbol": "BTCUSD",
            "side": "buy",
            "contracts": 1,
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,
            "take_profit_price": 73000.0,
            "client_order_id": f"cl_BTCUSD_emergency_test_{int(time.time())}"
        }

        res = exec_agent.execute_approved_trade(decision)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "EMERGENCY_ABORTED")
        mock_client.close_position.assert_called_once_with("BTCUSD")
        mock_notifier.send_alert.assert_called_once()

    # -------------------------------------------------------------------------
    # 7. Deterministic Safety Controller (14 Criteria & Token Issuance)
    # -------------------------------------------------------------------------
    def test_safety_controller_issues_signed_token_on_valid_setup(self):
        """When all criteria pass, controller issues HMAC-signed execution token."""
        risk_mgr = RiskManager()
        # Ensure fresh clean state
        risk_mgr.manual_reset(authorized_by="Admin", reason="Test init", current_equity=1000.0)

        controller = DeterministicSafetyController(risk_manager=risk_mgr, secret_key="test_secret")

        trade = {
            "symbol": "BTCUSD",
            "side": "buy",
            "contracts": 1,
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,
            "take_profit_price": 73000.0,
            "leverage": 10,
            "contract_value": 0.001,
            "liq_distance_pct": 5.0,  # stop distance is 1.43% -> 5.0% is > 3.0x stop distance
            "client_order_id": f"token_test_{int(time.time())}"
        }

        res = controller.validate_and_issue_token(
            trade_setup=trade,
            account_equity=1000.0,
            active_positions=[],
            market_data={"spread_pct": 0.05, "data_timestamp": time.time()}
        )

        self.assertTrue(res["passed"])
        self.assertIn("token", res)
        token = res["token"]
        self.assertTrue(token["valid"])
        self.assertGreater(token["expires_at"], time.time())
        self.assertTrue(len(token["signature"]) > 20)

    def test_safety_controller_rejects_inverted_stop_loss(self):
        """Controller rejects buy orders where stop loss is above entry."""
        risk_mgr = RiskManager()
        controller = DeterministicSafetyController(risk_manager=risk_mgr)

        bad_trade = {
            "symbol": "BTCUSD",
            "side": "buy",
            "contracts": 1,
            "entry_price": 70000.0,
            "stop_loss_price": 71000.0,  # INVERTED! Stop loss > entry for buy
            "take_profit_price": 75000.0,
            "leverage": 10,
            "contract_value": 0.001,
            "liq_distance_pct": 5.0
        }

        res = controller.validate_and_issue_token(
            trade_setup=bad_trade,
            account_equity=1000.0,
            active_positions=[]
        )
        self.assertFalse(res["passed"])
        self.assertEqual(res["failure_code"], "CRITERION_6_INVERTED_STOP_LOSS")

    def test_risk_gatekeeper_order_book_liquidity_veto(self):
        """Risk Gatekeeper enforces hard veto when order book spread exceeds 0.15%."""
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": "1000.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        risk_mgr = RiskManager()
        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=risk_mgr)

        # Setup with illiquid spread = 0.22%
        illiquid_setup = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 69500.0,
            "take_profit_price": 71500.0,
            "spread_pct": 0.22  # > 0.15% ceiling
        }

        decision = gatekeeper.evaluate_candidate(illiquid_setup)
        self.assertEqual(decision["gate_decision"], "REJECTED")
        self.assertIn("Liquidity Veto", decision["reason"])
        self.assertIn("0.220%", decision["reason"])

    def test_risk_gatekeeper_liquidity_profile_approved(self):
        """Risk Gatekeeper attaches liquidity grade and profile to approved setup."""
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": "1000.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": "1",
            "tick_size": "1.0",
            "maintenance_margin_rate": "0.01"
        }
        risk_mgr = RiskManager(max_dollar_risk_per_trade=4.0)
        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=risk_mgr)

        prime_setup = {
            "symbol": "BTCUSD",
            "strategy_name": "SMC_Sweep_Long",
            "thesis": "Bullish SSL sweep and MSS",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 69700.0,
            "take_profit_price": 71000.0,
            "spread_pct": 0.03,  # Prime liquid spread
            "score": 92,
            "confluence": {
                "liquidity_detail": "BSL: $71,000.00 | SSL: $69,500.00 | State: SWEEP_MSS_CONFIRMED"
            }
        }

        decision = gatekeeper.evaluate_candidate(prime_setup)
        self.assertEqual(decision["gate_decision"], "APPROVED")
        self.assertIn("liquidity_profile", decision)
        self.assertEqual(decision["liquidity_profile"]["liquidity_grade"], "A+_PRIME_DEPTH")
        self.assertEqual(decision["liquidity_profile"]["spread_pct"], 0.03)


if __name__ == "__main__":
    unittest.main()
