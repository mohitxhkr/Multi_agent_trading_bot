"""
Unit & Integration Test Suite for Upgraded Agent 9 - Portfolio Monitor.
Delta Exchange Multi-Agent Quantitative Trading System.

Validates all 22 mandatory quantitative and capital protection scenarios:
1. Linear contract exposure calculations
2. Inverse contract exposure calculations
3. Unrealized PnL calculations (Long & Short, Linear & Inverse)
4. Realized PnL calculations
5. Multiple open positions aggregation
6. Correlated position concentration warnings
7. Margin utilization calculation & status tiers
8. Mark-to-liquidation distance surveillance
9. Missing stop-loss detection & emergency trigger
10. Incorrect protective order quantity (partial fill deficit)
11. Partial fills and quantity changes
12. Duplicate protective orders detection
13. Exchange / local state mismatch reconciliation (DESYNCHRONIZED)
14. Stale market data detection
15. REST API failure handling (Fail-closed to UNKNOWN)
16. Reconnection and recovery after API failure
17. Daily drawdown threshold breach
18. Weekly drawdown threshold breach
19. Consecutive loss threshold breach
20. Duplicate Telegram alert prevention (cooldown suppression)
21. Concurrent monitoring thread safety
22. Emergency event communication with EmergencyController / Agent 7
"""

import unittest
import time
import threading
from unittest.mock import MagicMock, patch

from multiagent_team.portfolio_monitor import (
    PortfolioMonitorAgent,
    get_contract_spec,
    calculate_position_metrics,
    DEFAULT_PORTFOLIO_CONFIG
)


class TestPortfolioMonitorUpgrade(unittest.TestCase):
    """Test suite validating upgraded Agent 9 Portfolio Monitor."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_state_mgr = MagicMock()
        self.mock_risk_mgr = MagicMock()
        self.mock_safety_ctrl = MagicMock()
        self.mock_emergency_ctrl = MagicMock()
        self.mock_telegram = MagicMock()

        # Configure default mock returns for healthy baseline
        self.mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": 10000.0, "available_balance": 8000.0}],
            "meta": {"net_equity": 10000.0}
        }
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": []
        }
        self.mock_client.get_open_orders.return_value = {
            "success": True,
            "result": []
        }

        self.mock_state_mgr.get_open_positions.return_value = []
        self.mock_risk_mgr.check_circuit_breaker.return_value = {"can_trade": True}
        self.mock_risk_mgr.daily_pnl = 0.0
        self.mock_risk_mgr.weekly_pnl = 0.0
        self.mock_risk_mgr.consecutive_losses = 0
        self.mock_risk_mgr.start_of_day_equity = 10000.0
        self.mock_risk_mgr.start_of_week_equity = 10000.0

        self.agent = PortfolioMonitorAgent(
            client=self.mock_client,
            state_manager=self.mock_state_mgr,
            risk_manager=self.mock_risk_mgr,
            safety_controller=self.mock_safety_ctrl,
            emergency_controller=self.mock_emergency_ctrl,
            telegram=self.mock_telegram
        )

    # -------------------------------------------------------------------------
    # Scenario 1: Linear Contract Exposure
    # -------------------------------------------------------------------------
    def test_linear_contract_exposure(self):
        """Scenario 1: Linear contract notional and base quantity calculations."""
        spec = {"contract_type": "linear", "contract_value": 0.001, "settling_asset": "USDT"}
        pos = {"size": 20, "entry_price": 60000.0, "mark_price": 65000.0, "liquidation_price": 50000.0}
        metrics = calculate_position_metrics(pos, spec)

        # 20 contracts * 0.001 = 0.02 BTC
        self.assertEqual(metrics["base_quantity"], 0.02)
        # 0.02 BTC * $65,000 = $1,300.00 notional
        self.assertEqual(metrics["notional_usd"], 1300.00)
        self.assertEqual(metrics["direction"], "LONG")

    # -------------------------------------------------------------------------
    # Scenario 2: Inverse Contract Exposure
    # -------------------------------------------------------------------------
    def test_inverse_contract_exposure(self):
        """Scenario 2: Inverse contract notional and base quantity calculations."""
        spec = {"contract_type": "inverse", "contract_value": 1.0, "settling_asset": "BTC"}
        pos = {"size": 500, "entry_price": 50000.0, "mark_price": 50000.0, "liquidation_price": 40000.0}
        metrics = calculate_position_metrics(pos, spec)

        # 500 contracts * $1.0 = $500.00 notional
        self.assertEqual(metrics["notional_usd"], 500.00)
        # $500 / $50,000 = 0.01 BTC base quantity
        self.assertEqual(metrics["base_quantity"], 0.01)

    # -------------------------------------------------------------------------
    # Scenario 3: Unrealized PnL Calculations (Long & Short, Linear & Inverse)
    # -------------------------------------------------------------------------
    def test_unrealized_pnl_calculations(self):
        """Scenario 3: Linear & inverse unrealized PnL for Long and Short."""
        # Linear Long: 10 contracts * 0.001 * ($65,000 - $60,000) = +$50.00
        spec_lin = {"contract_type": "linear", "contract_value": 0.001}
        pos_long_lin = {"size": 10, "entry_price": 60000.0, "mark_price": 65000.0}
        m_ll = calculate_position_metrics(pos_long_lin, spec_lin)
        self.assertAlmostEqual(m_ll["unrealized_pnl"], 50.0, places=2)

        # Linear Short: -10 contracts * 0.001 * ($60,000 - $55,000) = +$50.00
        pos_short_lin = {"size": -10, "entry_price": 60000.0, "mark_price": 55000.0}
        m_sl = calculate_position_metrics(pos_short_lin, spec_lin)
        self.assertAlmostEqual(m_sl["unrealized_pnl"], 50.0, places=2)

        # Inverse Long: 10,000 contracts ($10,000 notional) entry $50,000, mark $60,000
        # PnL coin = (1/50,000 - 1/60,000) * 10,000 = (0.00002 - 0.0000166667) * 10,000 = 0.033333 BTC
        # PnL USD = 0.033333 BTC * 60,000 = +$2,000.00
        spec_inv = {"contract_type": "inverse", "contract_value": 1.0}
        pos_long_inv = {"size": 10000, "entry_price": 50000.0, "mark_price": 60000.0}
        m_li = calculate_position_metrics(pos_long_inv, spec_inv)
        self.assertAlmostEqual(m_li["unrealized_pnl"], 2000.0, places=1)

    # -------------------------------------------------------------------------
    # Scenario 4: Realized PnL Extraction
    # -------------------------------------------------------------------------
    def test_realized_pnl_calculations(self):
        """Scenario 4: Realized PnL is properly reported and journaled."""
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [{
                "product_symbol": "BTCUSD",
                "size": 10,
                "entry_price": 60000.0,
                "mark_price": 61000.0,
                "realized_pnl": 75.50
            }]
        }
        res = self.agent.monitor_positions()
        pos = res["open_positions"][0]
        self.assertEqual(pos["realized_pnl"], 75.50)

    # -------------------------------------------------------------------------
    # Scenario 5: Multiple Open Positions Aggregation
    # -------------------------------------------------------------------------
    def test_multiple_open_positions_aggregation(self):
        """Scenario 5: Multiple positions aggregated into total, gross, long, short exposure."""
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [
                {"product_symbol": "BTCUSD", "size": 10, "entry_price": 60000.0, "mark_price": 60000.0}, # $600 long
                {"product_symbol": "ETHUSD", "size": -20, "entry_price": 3000.0, "mark_price": 3000.0}    # $600 short (20 * 0.01 * 3000)
            ]
        }
        # Provide protective stop orders for both so status stays clean
        self.mock_client.get_open_orders.return_value = {
            "success": True,
            "result": [
                {"product_symbol": "BTCUSD", "stop_order_type": "stop_loss_order", "side": "sell", "size": 10},
                {"product_symbol": "ETHUSD", "stop_order_type": "stop_loss_order", "side": "buy", "size": 20}
            ]
        }

        res = self.agent.monitor_positions()
        self.assertEqual(res["active_count"], 2)
        self.assertEqual(res["long_exposure"], 600.0)
        self.assertEqual(res["short_exposure"], 600.0)
        self.assertEqual(res["gross_exposure"], 1200.0)
        self.assertEqual(res["net_directional_exposure"], 0.0)

    # -------------------------------------------------------------------------
    # Scenario 6: Correlated Position Concentration Warnings
    # -------------------------------------------------------------------------
    def test_correlated_position_warnings(self):
        """Scenario 6: Exceeding max correlated positions triggers concentration warning."""
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [
                {"product_symbol": "BTCUSD", "size": 10, "entry_price": 60000.0, "mark_price": 60000.0},
                {"product_symbol": "ETHUSD", "size": 20, "entry_price": 3000.0, "mark_price": 3000.0},
                {"product_symbol": "SOLUSD", "size": 5, "entry_price": 150.0, "mark_price": 150.0}
            ]
        }
        res = self.agent.monitor_positions()
        corr_warnings = res["correlated_exposure"]["warnings"]
        self.assertTrue(any("CORRELATION LIMIT EXCEEDED" in w for w in corr_warnings))
        self.assertTrue(any(ev["event_type"] == "PORTFOLIO_CONCENTRATION" for ev in res["risk_events"]))

    # -------------------------------------------------------------------------
    # Scenario 7: Margin Utilization Calculations & Status Tiers
    # -------------------------------------------------------------------------
    def test_margin_utilization(self):
        """Scenario 7: Margin utilization warning tiers (WARNING >= 70%, HIGH_RISK >= 85%, CRITICAL >= 95%)."""
        # 88% margin utilization -> HIGH_RISK
        self.mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": 10000.0, "available_balance": 1200.0}],
            "meta": {"net_equity": 10000.0}
        }
        res = self.agent.monitor_positions()
        self.assertEqual(res["margin_utilization"], 88.0)
        self.assertEqual(res["margin_status"], "HIGH_RISK")
        self.assertTrue(any(ev["event_type"] == "HIGH_MARGIN_UTILIZATION" for ev in res["risk_events"]))

    # -------------------------------------------------------------------------
    # Scenario 8: Mark-to-Liquidation Distance Warnings
    # -------------------------------------------------------------------------
    def test_liquidation_distance_warnings(self):
        """Scenario 8: True mark-to-liquidation distance calculation triggers WARNING, HIGH_RISK, CRITICAL."""
        # Long position: Mark $60,000, Liq $58,800 -> 2.0% distance (<= 2.5% CRITICAL)
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [{
                "product_symbol": "BTCUSD",
                "size": 10,
                "entry_price": 65000.0,
                "mark_price": 60000.0,
                "liquidation_price": 58800.0
            }]
        }
        res = self.agent.monitor_positions()
        liq_warnings = res["liquidation_warnings"]
        self.assertEqual(len(liq_warnings), 1)
        self.assertEqual(liq_warnings[0]["severity"], "CRITICAL")
        self.assertAlmostEqual(liq_warnings[0]["distance_pct"], 2.0, places=1)
        self.assertEqual(res["overall_status"], "CRITICAL")

    # -------------------------------------------------------------------------
    # Scenario 9: Missing Stop-Loss Detection & Emergency Trigger
    # -------------------------------------------------------------------------
    def test_missing_stop_loss_detection(self):
        """Scenario 9: Open position without stop loss order triggers CRITICAL alert and emergency workflow."""
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [{"product_symbol": "BTCUSD", "size": 10, "entry_price": 60000.0, "mark_price": 60000.0}]
        }
        self.mock_client.get_open_orders.return_value = {"success": True, "result": []}

        res = self.agent.monitor_positions()

        self.assertFalse(res["protective_order_status"]["all_protected"])
        self.assertEqual(len(res["protective_order_status"]["unprotected_positions"]), 1)
        self.assertEqual(res["overall_status"], "CRITICAL")
        # Verify emergency controller was triggered
        self.mock_emergency_ctrl.verify_and_ensure_sl_protection.assert_called_once()

    # -------------------------------------------------------------------------
    # Scenario 10: Incorrect Protective Order Quantity
    # -------------------------------------------------------------------------
    def test_incorrect_protective_order_quantity(self):
        """Scenario 10: Stop loss order quantity smaller than position size flags deficit."""
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [{"product_symbol": "BTCUSD", "size": 10, "entry_price": 60000.0, "mark_price": 60000.0}]
        }
        # Only 6 contracts covered by Stop Loss
        self.mock_client.get_open_orders.return_value = {
            "success": True,
            "result": [{"product_symbol": "BTCUSD", "stop_order_type": "stop_loss_order", "side": "sell", "size": 6}]
        }

        res = self.agent.monitor_positions()
        inq = res["protective_order_status"]["insufficient_quantity_positions"]
        self.assertEqual(len(inq), 1)
        self.assertEqual(inq[0]["coverage_deficit"], 4)
        self.assertEqual(res["overall_status"], "HIGH_RISK")

    # -------------------------------------------------------------------------
    # Scenario 11: Partial Fills and Quantity Changes
    # -------------------------------------------------------------------------
    def test_partial_fills_and_quantity_changes(self):
        """Scenario 11: Updating position size dynamically recalculates notional exposure."""
        # Initial size = 5 contracts ($300)
        pos_init = {"product_symbol": "BTCUSD", "size": 5, "entry_price": 60000.0, "mark_price": 60000.0}
        self.mock_client.get_positions.return_value = {"success": True, "result": [pos_init]}
        res_init = self.agent.monitor_positions()
        self.assertEqual(res_init["total_open_exposure"], 300.0)

        # After partial fill, size increases to 10 contracts ($600)
        pos_filled = {"product_symbol": "BTCUSD", "size": 10, "entry_price": 60000.0, "mark_price": 60000.0}
        self.mock_client.get_positions.return_value = {"success": True, "result": [pos_filled]}
        res_filled = self.agent.monitor_positions()
        self.assertEqual(res_filled["total_open_exposure"], 600.0)

    # -------------------------------------------------------------------------
    # Scenario 12: Duplicate Orders Detection
    # -------------------------------------------------------------------------
    def test_duplicate_orders_detection(self):
        """Scenario 12: Detects multiple duplicate stop-loss orders for the same position."""
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [{"product_symbol": "BTCUSD", "size": 10, "entry_price": 60000.0, "mark_price": 60000.0}]
        }
        self.mock_client.get_open_orders.return_value = {
            "success": True,
            "result": [
                {"id": 101, "product_symbol": "BTCUSD", "stop_order_type": "stop_loss_order", "side": "sell", "size": 10},
                {"id": 102, "product_symbol": "BTCUSD", "stop_order_type": "stop_loss_order", "side": "sell", "size": 10}
            ]
        }
        res = self.agent.monitor_positions()
        dups = res["protective_order_status"]["duplicate_stop_orders"]
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["count"], 2)

    # -------------------------------------------------------------------------
    # Scenario 13: Exchange / Local State Mismatch Reconciliation
    # -------------------------------------------------------------------------
    def test_exchange_local_state_mismatch(self):
        """Scenario 13: Exchange position missing locally marks status as DESYNCHRONIZED."""
        # Exchange has BTC position
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [{"product_symbol": "BTCUSD", "size": 10, "entry_price": 60000.0, "mark_price": 60000.0}]
        }
        self.mock_client.get_open_orders.return_value = {
            "success": True,
            "result": [{"product_symbol": "BTCUSD", "stop_order_type": "stop_loss_order", "side": "sell", "size": 10}]
        }
        # Local state manager has no positions
        self.mock_state_mgr.get_open_positions.return_value = []

        res = self.agent.monitor_positions()
        self.assertEqual(res["exchange_sync_status"], "DESYNCHRONIZED")
        self.assertEqual(res["overall_status"], "DESYNCHRONIZED")
        self.mock_state_mgr.reconcile_positions_with_exchange.assert_called_once()

    # -------------------------------------------------------------------------
    # Scenario 14: Stale Market Data Detection
    # -------------------------------------------------------------------------
    def test_stale_market_data_detection(self):
        """Scenario 14: Age calculation correctly detects poll age."""
        self.agent._last_successful_poll_ts = time.time() - 120.0
        # Trigger fail-closed payload
        fail_closed = self.agent._build_fail_closed_status("UNKNOWN", "Connection timeout", time.time())
        self.assertTrue(fail_closed["stale_data_status"]["is_stale"])
        self.assertGreaterEqual(fail_closed["stale_data_status"]["last_poll_age_seconds"], 120.0)

    # -------------------------------------------------------------------------
    # Scenario 15: REST API Failure Handling
    # -------------------------------------------------------------------------
    def test_rest_api_failure_handling(self):
        """Scenario 15: API network failure fails closed cleanly to UNKNOWN without unhandled exception."""
        self.mock_client.get_wallet_balances.return_value = {"success": False, "error": "503 Gateway Timeout"}
        res = self.agent.monitor_positions()

        self.assertEqual(res["overall_status"], "UNKNOWN")
        self.assertEqual(res["exchange_sync_status"], "UNKNOWN")
        self.assertTrue(any(ev["event_type"] == "API_FAILURE" for ev in res["risk_events"]))

    # -------------------------------------------------------------------------
    # Scenario 16: Reconnection and Recovery
    # -------------------------------------------------------------------------
    def test_reconnection_and_recovery(self):
        """Scenario 16: After API failure, subsequent successful call recovers to HEALTHY."""
        # 1. First poll fails
        self.mock_client.get_wallet_balances.return_value = {"success": False, "error": "503 Gateway Timeout"}
        res_fail = self.agent.monitor_positions()
        self.assertEqual(res_fail["overall_status"], "UNKNOWN")

        # 2. Reconnection succeeds
        self.mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": 10000.0, "available_balance": 8000.0}],
            "meta": {"net_equity": 10000.0}
        }
        res_recovered = self.agent.monitor_positions()
        self.assertEqual(res_recovered["overall_status"], "HEALTHY")

    # -------------------------------------------------------------------------
    # Scenario 17: Daily Drawdown Threshold Breach
    # -------------------------------------------------------------------------
    def test_daily_drawdown_threshold(self):
        """Scenario 17: Daily drawdown >= 3.0% triggers DAILY_DRAWDOWN_LIMIT_BREACH."""
        self.agent.config["max_daily_drawdown_pct"] = 3.0
        self.mock_risk_mgr.daily_pnl = -350.0  # -3.5% on $10,000 equity
        self.mock_risk_mgr.start_of_day_equity = 10000.0

        res = self.agent.monitor_positions()
        self.assertGreaterEqual(res["daily_drawdown"], 3.5)
        self.assertTrue(any(ev["event_type"] == "DAILY_DRAWDOWN_LIMIT_BREACH" for ev in res["risk_events"]))
        self.assertEqual(res["overall_status"], "CRITICAL")

    # -------------------------------------------------------------------------
    # Scenario 18: Weekly Drawdown Threshold Breach
    # -------------------------------------------------------------------------
    def test_weekly_drawdown_threshold(self):
        """Scenario 18: Weekly drawdown >= 5.0% triggers WEEKLY_DRAWDOWN_LIMIT_BREACH."""
        self.mock_risk_mgr.weekly_pnl = -600.0  # -6.0% on $10,000 equity
        self.mock_risk_mgr.start_of_week_equity = 10000.0

        res = self.agent.monitor_positions()
        self.assertGreaterEqual(res["weekly_drawdown"], 6.0)
        self.assertTrue(any(ev["event_type"] == "WEEKLY_DRAWDOWN_LIMIT_BREACH" for ev in res["risk_events"]))
        self.assertEqual(res["overall_status"], "CRITICAL")

    # -------------------------------------------------------------------------
    # Scenario 19: Consecutive Loss Threshold Breach
    # -------------------------------------------------------------------------
    def test_consecutive_loss_threshold(self):
        """Scenario 19: Consecutive losses >= 3 triggers CONSECUTIVE_LOSS_LIMIT_BREACH."""
        self.mock_risk_mgr.consecutive_losses = 3

        res = self.agent.monitor_positions()
        self.assertEqual(res["consecutive_losses"], 3)
        self.assertTrue(any(ev["event_type"] == "CONSECUTIVE_LOSS_LIMIT_BREACH" for ev in res["risk_events"]))

    # -------------------------------------------------------------------------
    # Scenario 20: Duplicate Telegram Alert Prevention
    # -------------------------------------------------------------------------
    def test_duplicate_telegram_alert_prevention(self):
        """Scenario 20: Repeated non-critical alerts within cooldown period are suppressed."""
        # First alert sends
        sent1 = self.agent.dispatch_telegram_alert(
            alert_type="HIGH_MARGIN_UTILIZATION",
            symbol="PORTFOLIO",
            severity="WARNING",
            message="Margin is elevated"
        )
        self.assertTrue(sent1)

        # Immediate second identical alert is suppressed
        sent2 = self.agent.dispatch_telegram_alert(
            alert_type="HIGH_MARGIN_UTILIZATION",
            symbol="PORTFOLIO",
            severity="WARNING",
            message="Margin is elevated"
        )
        self.assertFalse(sent2)

    # -------------------------------------------------------------------------
    # Scenario 21: Concurrent Monitoring Thread Safety
    # -------------------------------------------------------------------------
    def test_concurrent_monitoring_safety(self):
        """Scenario 21: Concurrent monitor_positions calls execute safely without race conditions."""
        errors = []

        def worker():
            try:
                for _ in range(5):
                    self.agent.monitor_positions()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)

    # -------------------------------------------------------------------------
    # Scenario 22: Emergency Event Communication with Agent 7 & EmergencyController
    # -------------------------------------------------------------------------
    def test_emergency_event_communication_with_agent_7(self):
        """Scenario 22: Unprotected position calls emergency controller to ensure SL protection."""
        self.mock_client.get_positions.return_value = {
            "success": True,
            "result": [{"product_symbol": "ETHUSD", "size": 15, "entry_price": 3000.0, "mark_price": 3000.0}]
        }
        self.mock_client.get_open_orders.return_value = {"success": True, "result": []}

        res = self.agent.monitor_positions()

        # Check emergency controller was engaged
        self.mock_emergency_ctrl.verify_and_ensure_sl_protection.assert_called_once()
        self.assertEqual(res["overall_status"], "CRITICAL")


if __name__ == "__main__":
    unittest.main()
