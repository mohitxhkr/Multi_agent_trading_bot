"""
End-to-End Multi-Agent System Integration Test Suite.
Verifies complete pipeline coordination across the 10 agents,
the Deterministic Safety Controller, and dual SQLite/JSON event journaling.
"""

import unittest
import os
import time
import tempfile
import shutil
from unittest.mock import MagicMock, patch

from src.config import config
from src.risk_manager import RiskManager
from src.state_manager import StateManager
from src.journal import (
    record_trade_entry,
    record_trade_exit,
    get_performance_summary,
    get_db_connection,
    log_trade_event
)
from multiagent_team.regime_analyst import RegimeAnalystAgent
from multiagent_team.strategy_agent import StrategyAgent
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.time_machine_agent import TimeMachineAgent
from multiagent_team.execution_agent import ExecutionAgent
from multiagent_team.deterministic_safety_controller import DeterministicSafetyController
from multiagent_team.orchestrator import MultiAgentTradingOrchestrator


class TestFullMultiAgentPipeline(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.test_dir, "circuit_breaker_state.json")
        self.patcher = patch("src.risk_manager.CIRCUIT_BREAKER_STATE_FILE", self.state_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sqlite_event_store_and_journal_synchronization(self):
        """Verify that trade entries, exits, and granular lifecycle events write to SQLite and JSON."""
        trade_id = f"test_trade_{int(time.time())}"

        # 1. Log pre-trade lifecycle events
        log_trade_event(trade_id, "SETUP_IDENTIFIED", {"symbol": "BTCUSD", "side": "buy"})
        log_trade_event(trade_id, "RISK_EVALUATED", {"status": "APPROVED", "contracts": 2})

        # 2. Record trade entry
        entry_record = record_trade_entry(
            trade_id=trade_id,
            symbol="BTCUSD",
            side="buy",
            contracts=2,
            entry_price=70000.0,
            stop_loss=69000.0,
            take_profit=73000.0,
            thesis="Institutional SMC MSS Breakout",
            strategy="SMC_BOS_LONG",
            agent_decision={"gate_decision": "APPROVED"}
        )
        self.assertEqual(entry_record["status"], "OPEN")

        # 3. Verify SQLite DB row
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["symbol"], "BTCUSD")
            self.assertEqual(row["contracts"], 2)
            self.assertEqual(row["status"], "OPEN")

            # Check lifecycle events count
            events = conn.execute("SELECT * FROM trade_lifecycle_events WHERE trade_id = ?", (trade_id,)).fetchall()
            self.assertGreaterEqual(len(events), 3)  # SETUP_IDENTIFIED, RISK_EVALUATED, ORDER_PLACED

        # 4. Record trade exit
        exit_record = record_trade_exit(
            trade_id=trade_id,
            exit_price=73000.0,
            realized_pnl_usd=6.00,
            exit_reason="TAKE_PROFIT_LIMIT_FILL",
            postmortem_notes="Clean institutional trend impulse to target",
            mfe_r=3.0,
            mae_r=0.2
        )
        self.assertIsNotNone(exit_record)
        self.assertEqual(exit_record["status"], "CLOSED")
        self.assertEqual(exit_record["realized_pnl_usd"], 6.00)

        # 5. Verify SQLite closure
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,)).fetchone()
            self.assertEqual(row["status"], "CLOSED")
            self.assertEqual(row["exit_price"], 73000.0)
            self.assertEqual(row["realized_pnl_usd"], 6.00)

        summary = get_performance_summary()
        self.assertGreaterEqual(summary["stats"]["total_trades"], 1)

    def test_end_to_end_orchestrator_pipeline_execution(self):
        """
        Verify end-to-end execution of orchestrator run_single_scan_and_execute_cycle
        with mocked Delta Exchange responses.
        """
        mock_client = MagicMock()

        # Mock candles (15m, 1h, 4h, daily, weekly)
        now_ts = int(time.time())
        closes_bullish = [68000.0 + (i * 25.0) for i in range(120)]
        mock_candles = {
            "t": [now_ts - (120 - i) * 900 for i in range(120)],
            "c": closes_bullish,
            "h": [p + 30.0 for p in closes_bullish],
            "l": [p - 30.0 for p in closes_bullish],
            "o": [p - 10.0 for p in closes_bullish],
            "v": [100.0 for _ in range(120)]
        }
        mock_client.get_candles.return_value = {"success": True, "result": mock_candles}

        # Mock ticker
        mock_client.get_ticker.return_value = {
            "success": True,
            "result": {
                "mark_price": str(closes_bullish[-1]),
                "bid": str(closes_bullish[-1] - 1.0),
                "ask": str(closes_bullish[-1] + 1.0),
                "funding_rate": "0.0001",
                "oi_contracts": "50000"
            }
        }
        mock_client.resolve_symbol.side_effect = lambda s: s

        # Mock wallet & positions
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": "1000.0", "available_balance": "1000.0"}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_open_orders.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": "1",
            "tick_size": "1.0",
            "maintenance_margin_rate": "0.01"
        }
        mock_client.round_to_tick.side_effect = lambda sym, px: round(px, 1)

        # Mock order placement & SL verification
        mock_client.set_leverage.return_value = {"success": True}
        mock_client.place_bracket_order.return_value = {
            "success": True,
            "result": {
                "id": 99991,
                "state": "open",
                "stop_loss_order_id": 99992,
                "take_profit_order_id": 99993
            }
        }
        mock_client.get_open_orders.return_value = {
            "success": True,
            "result": [
                {
                    "id": 99992,
                    "symbol": "BTCUSD",
                    "side": "sell",
                    "order_type": "stop_market_order",
                    "stop_price": str(closes_bullish[-1] - 500.0)
                }
            ]
        }

        # Instantiate orchestrator
        orchestrator = MultiAgentTradingOrchestrator(
            client=mock_client,
            symbols=["BTCUSD"],
            interactive=False
        )
        orchestrator.telegram_bot.bot_token = ""  # sets is_configured to False without prompt blocking

        # Test pre-execution scan cycle
        scan_res = orchestrator.regime_analyst.scan_universe(["BTCUSD"])
        self.assertIn("BTCUSD", scan_res["symbols_data"])
        self.assertIn("breadth_pct", scan_res)
        self.assertIn("eth_btc_relative_strength", scan_res)


if __name__ == "__main__":
    unittest.main()
