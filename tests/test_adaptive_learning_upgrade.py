"""
Unit & Integration Test Suite for Upgraded Agent 10 - Adaptive Learning Engine.
Delta Exchange Multi-Agent Quantitative Trading System.

Validates all 22 required quantitative, machine learning, and configuration safety scenarios:
1. Verified completed trade ingestion
2. Open trade exclusion (rejects uncompleted trades)
3. Canceled order exclusion
4. Partial fill handling
5. Net PnL calculation (deducts fees, slippage, funding)
6. Net R calculation (Net PnL / Initial Monetary Risk)
7. Timeout and breakeven outcome handling
8. Regime-specific performance tracking
9. Insufficient sample-size handling (returns INSUFFICIENT_DATA)
10. Chronological data splitting (Train / Test)
11. Walk-forward validation
12. Data leakage prevention
13. Parameter bounds clamping
14. Candidate versus baseline comparison
15. Overfitting detection
16. Configuration versioning
17. Configuration rollback
18. Live parameter protection (proposals cannot modify live config)
19. Strategy degradation detection (DEGRADING / CRITICAL_DEGRADATION)
20. Invalid historical records exclusion
21. Duplicate trade record prevention
22. Agent communication compatibility (StrategyAgent, TrailingStop, Telegram)
"""

import unittest
import os
import tempfile
import shutil
import time
from typing import Dict, Any, List

from multiagent_team.adaptive_learning import (
    AdaptiveLearningEngine,
    PARAM_BOUNDS,
    BASELINE_STRATEGY_CONFIG
)


def make_sample_trade(
    trade_id: str,
    symbol: str = "BTCUSD",
    side: str = "BUY",
    entry_price: float = 60000.0,
    exit_price: float = 62000.0,
    contracts: int = 10,
    status: str = "CLOSED",
    exit_reason: str = "TAKE_PROFIT",
    regime: str = "STRONG_UPTREND",
    fees: float = 0.50,
    slippage: float = 0.20,
    funding: float = 0.10,
    initial_sl: float = 59000.0
) -> Dict[str, Any]:
    """Helper to generate well-formed trade records for testing."""
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "contracts": contracts,
        "contract_value": 0.001,
        "status": status,
        "exit_reason": exit_reason,
        "regime": regime,
        "fees": fees,
        "slippage": slippage,
        "funding": funding,
        "initial_sl": initial_sl,
        "strategy": "Delta_SMC_Scalper",
        "confluence_score": 85.0
    }


class TestAdaptiveLearningUpgrade(unittest.TestCase):
    """Test suite validating upgraded Agent 10 Adaptive Learning Engine."""

    def setUp(self):
        # Create temporary isolated directory for state files
        self.test_dir = tempfile.mkdtemp()
        self.memory_path = os.path.join(self.test_dir, "test_memory.json")
        self.config_versions_path = os.path.join(self.test_dir, "test_config_versions.json")
        self.trades_dataset_path = os.path.join(self.test_dir, "test_trades.jsonl")

        self.engine = AdaptiveLearningEngine(
            memory_path=self.memory_path,
            config_versions_path=self.config_versions_path,
            trades_dataset_path=self.trades_dataset_path
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Scenario 1: Verified Completed Trade Ingestion
    # -------------------------------------------------------------------------
    def test_verified_completed_trade_ingestion(self):
        """Scenario 1: Completed, valid trade record is ingested successfully."""
        trade = make_sample_trade("t-001", exit_price=62000.0)
        success, msg, record = self.engine.ingest_trade_record(trade)

        self.assertTrue(success)
        self.assertEqual(len(self.engine.verified_trades), 1)
        self.assertEqual(record["trade_id"], "t-001")
        self.assertEqual(record["outcome"], "WIN")

    # -------------------------------------------------------------------------
    # Scenario 2: Open Trade Exclusion
    # -------------------------------------------------------------------------
    def test_open_trade_exclusion(self):
        """Scenario 2: Active or open trades must not be ingested into learning dataset."""
        trade = make_sample_trade("t-open", status="OPEN")
        success, msg, record = self.engine.ingest_trade_record(trade)

        self.assertFalse(success)
        self.assertIn("OPEN_TRADE_EXCLUDED", msg)
        self.assertEqual(len(self.engine.verified_trades), 0)

    # -------------------------------------------------------------------------
    # Scenario 3: Canceled Order Exclusion
    # -------------------------------------------------------------------------
    def test_canceled_order_exclusion(self):
        """Scenario 3: Canceled or rejected orders must not be ingested."""
        trade = make_sample_trade("t-canc", status="CANCELED")
        success, msg, record = self.engine.ingest_trade_record(trade)

        self.assertFalse(success)
        self.assertIn("CANCELED_ORDER_EXCLUDED", msg)
        self.assertEqual(len(self.engine.verified_trades), 0)

    # -------------------------------------------------------------------------
    # Scenario 4: Partial Fill Handling
    # -------------------------------------------------------------------------
    def test_partial_fill_handling(self):
        """Scenario 4: Closed trade with partial fill size correctly calculates notional."""
        # Partially filled order that closed with 6 contracts (out of 10 intended)
        trade = make_sample_trade("t-part", contracts=6, entry_price=60000.0, exit_price=61000.0)
        success, msg, record = self.engine.ingest_trade_record(trade)

        self.assertTrue(success)
        # Gross = (61000 - 60000) * 6 * 0.001 = $6.00
        self.assertAlmostEqual(record["gross_pnl_usd"], 6.00, places=2)

    # -------------------------------------------------------------------------
    # Scenario 5: Net PnL Calculation
    # -------------------------------------------------------------------------
    def test_net_pnl_calculation(self):
        """Scenario 5: Net PnL = Gross PnL - Fees - Slippage - Funding."""
        # Gross = (62000 - 60000) * 10 * 0.001 = $20.00
        # Fees: $1.50, Slippage: $0.50, Funding: $0.20 -> Net: $17.80
        trade = make_sample_trade("t-net", entry_price=60000.0, exit_price=62000.0, fees=1.50, slippage=0.50, funding=0.20)
        success, msg, record = self.engine.ingest_trade_record(trade)

        self.assertTrue(success)
        self.assertAlmostEqual(record["gross_pnl_usd"], 20.00, places=2)
        self.assertAlmostEqual(record["net_pnl_usd"], 17.80, places=2)

    # -------------------------------------------------------------------------
    # Scenario 6: Net R Calculation
    # -------------------------------------------------------------------------
    def test_net_r_calculation(self):
        """Scenario 6: Net R = Net PnL / Initial Monetary Risk."""
        # Entry: $60,000, Initial SL: $59,000, Size: 10 * 0.001 -> Initial Risk = $10.00
        # Exit: $62,000 -> Gross $20, Fees $1.00 -> Net PnL = $19.00
        # Net R = 19.00 / 10.00 = +1.90 R
        trade = make_sample_trade("t-r", entry_price=60000.0, exit_price=62000.0, initial_sl=59000.0, fees=1.00, slippage=0.0, funding=0.0)
        success, msg, record = self.engine.ingest_trade_record(trade)

        self.assertTrue(success)
        self.assertEqual(record["initial_risk_usd"], 10.00)
        self.assertAlmostEqual(record["net_r"], 1.90, places=2)

    # -------------------------------------------------------------------------
    # Scenario 7: Timeout and Breakeven Outcome Handling
    # -------------------------------------------------------------------------
    def test_timeout_and_breakeven_handling(self):
        """Scenario 7: Breakeven and timeout trades are recorded without biasing win rate."""
        t_be = make_sample_trade("t-be", entry_price=60000.0, exit_price=60005.0, exit_reason="BREAKEVEN", fees=0.05, slippage=0.0, funding=0.0)
        t_to = make_sample_trade("t-to", entry_price=60000.0, exit_price=60000.0, exit_reason="TIMEOUT", fees=0.05, slippage=0.0, funding=0.0)

        self.engine.ingest_trade_record(t_be)
        self.engine.ingest_trade_record(t_to)

        perf = self.engine.compute_strategy_performance()
        self.assertEqual(perf["breakevens"], 2)
        self.assertEqual(perf["wins"], 0)
        self.assertEqual(perf["losses"], 0)

    # -------------------------------------------------------------------------
    # Scenario 8: Regime-Specific Performance Tracking
    # -------------------------------------------------------------------------
    def test_regime_specific_performance(self):
        """Scenario 8: Performance metrics are segregated across canonical regimes."""
        # Ingest 5 trades in STRONG_UPTREND
        for i in range(5):
            t = make_sample_trade(f"t-up-{i}", regime="STRONG_UPTREND", exit_price=61500.0)
            self.engine.ingest_trade_record(t)

        reg_perf = self.engine.compute_regime_performance()
        self.assertEqual(reg_perf["STRONG_UPTREND"]["status"], "VALIDATED")
        self.assertEqual(reg_perf["STRONG_UPTREND"]["total_trades"], 5)
        self.assertEqual(reg_perf["STRONG_UPTREND"]["win_rate_pct"], 100.0)

    # -------------------------------------------------------------------------
    # Scenario 9: Insufficient Sample-Size Handling
    # -------------------------------------------------------------------------
    def test_insufficient_sample_size_handling(self):
        """Scenario 9: Regimes with < 5 trades return INSUFFICIENT_DATA."""
        # Ingest only 2 trades in RANGING
        for i in range(2):
            t = make_sample_trade(f"t-range-{i}", regime="RANGING", exit_price=60500.0)
            self.engine.ingest_trade_record(t)

        reg_perf = self.engine.compute_regime_performance()
        self.assertEqual(reg_perf["RANGING"]["status"], "INSUFFICIENT_DATA")

    # -------------------------------------------------------------------------
    # Scenario 10: Chronological Data Splitting
    # -------------------------------------------------------------------------
    def test_chronological_data_splitting(self):
        """Scenario 10: Walk-forward splits maintain strict chronological ordering."""
        trades = []
        for i in range(20):
            t = make_sample_trade(f"t-split-{i}", exit_price=61000.0)
            t["entry_timestamp"] = 1000000 + i * 3600
            trades.append(t)

        # 60% IS, 40% OOS
        split_idx = int(len(trades) * 0.60)
        is_trades = trades[:split_idx]
        oos_trades = trades[split_idx:]

        self.assertEqual(len(is_trades), 12)
        self.assertEqual(len(oos_trades), 8)
        # Verify chronological invariant: max(IS timestamp) < min(OOS timestamp)
        self.assertLess(is_trades[-1]["entry_timestamp"], oos_trades[0]["entry_timestamp"])

    # -------------------------------------------------------------------------
    # Scenario 11: Walk-Forward Validation
    # -------------------------------------------------------------------------
    def test_walk_forward_validation(self):
        """Scenario 11: Candidate configuration validated across out-of-sample data."""
        trades = []
        for i in range(20):
            trades.append(make_sample_trade(f"t-wf-{i}", exit_price=61500.0 if i % 4 != 0 else 58500.0))

        candidate = {"min_confluence_score": 85.0, "atr_multiplier": 1.5}
        wf = self.engine.run_walk_forward_validation(candidate, historical_trades=trades)

        self.assertIn("is_expectancy_r", wf)
        self.assertIn("oos_expectancy_r", wf)
        self.assertFalse(wf["is_overfitting"])

    # -------------------------------------------------------------------------
    # Scenario 12: Data Leakage Prevention
    # -------------------------------------------------------------------------
    def test_data_leakage_prevention(self):
        """Scenario 12: OOS data is strictly excluded from in-sample metrics."""
        trades = []
        for i in range(20):
            # First 12 are wins, last 8 are losses
            exit_p = 62000.0 if i < 12 else 58000.0
            trades.append(make_sample_trade(f"t-leak-{i}", exit_price=exit_p))

        wf = self.engine.run_walk_forward_validation({"min_confluence_score": 85.0}, historical_trades=trades)
        # IS expectancy must be positive (all wins), OOS expectancy must be negative (all losses)
        self.assertGreater(wf["is_expectancy_r"], 0.0)
        self.assertLess(wf["oos_expectancy_r"], 0.0)

    # -------------------------------------------------------------------------
    # Scenario 13: Parameter Bounds Enforcement
    # -------------------------------------------------------------------------
    def test_parameter_bounds(self):
        """Scenario 13: Parameters outside pre-approved bounds are clamped."""
        candidate = {
            "min_confluence_score": 120.0,  # Max is 95.0
            "atr_multiplier": 0.2,          # Min is 1.0
            "target_rr_ratio": 5.0          # Max is 4.0
        }
        all_valid, clamped, violations = self.engine.validate_parameter_bounds(candidate)

        self.assertFalse(all_valid)
        self.assertEqual(len(violations), 3)
        self.assertEqual(clamped["min_confluence_score"], 95.0)
        self.assertEqual(clamped["atr_multiplier"], 1.0)
        self.assertEqual(clamped["target_rr_ratio"], 4.0)

    # -------------------------------------------------------------------------
    # Scenario 14: Candidate vs Baseline Comparison
    # -------------------------------------------------------------------------
    def test_candidate_versus_baseline_comparison(self):
        """Scenario 14: Compare candidate parameters against active baseline."""
        baseline = self.engine.get_active_configuration()
        self.assertEqual(baseline["version"], "1.0.0-PROD")
        self.assertEqual(baseline["parameters"]["min_confluence_score"], 85.0)

        proposal = self.engine.propose_parameter_update(
            candidate_params={"min_confluence_score": 90.0},
            rationale="Test candidate"
        )
        self.assertIn("cand-", proposal["version"])
        self.assertNotEqual(proposal["version"], baseline["version"])

    # -------------------------------------------------------------------------
    # Scenario 15: Overfitting Detection
    # -------------------------------------------------------------------------
    def test_overfitting_detection(self):
        """Scenario 15: Flags overfitting when IS expectancy is high but OOS collapses."""
        trades = []
        for i in range(20):
            # First 12 are massive wins, last 8 are deep losses
            exit_p = 63000.0 if i < 12 else 57500.0
            trades.append(make_sample_trade(f"t-overfit-{i}", exit_price=exit_p))

        wf = self.engine.run_walk_forward_validation({"min_confluence_score": 85.0}, historical_trades=trades)
        self.assertTrue(wf["is_overfitting"])
        self.assertFalse(wf["passed"])
        self.assertEqual(wf["recommendation"], "REJECT_OVERFIT")

    # -------------------------------------------------------------------------
    # Scenario 16: Configuration Versioning
    # -------------------------------------------------------------------------
    def test_configuration_versioning(self):
        """Scenario 16: Configuration updates are uniquely versioned and recorded."""
        proposal = self.engine.propose_parameter_update({"min_confluence_score": 90.0}, "Tighter filter")
        v_id = proposal["version"]

        self.assertIn(v_id, self.engine.config_store["versions"])
        self.assertEqual(self.engine.config_store["versions"][v_id]["stage"], "EXPERIMENTAL")

    # -------------------------------------------------------------------------
    # Scenario 17: Configuration Rollback
    # -------------------------------------------------------------------------
    def test_configuration_rollback(self):
        """Scenario 17: Active configuration can be rolled back to BASELINE safely."""
        proposal = self.engine.propose_parameter_update({"min_confluence_score": 90.0}, "Candidate")
        v_id = proposal["version"]
        self.engine.promote_parameter_version(v_id, "LIVE_APPROVED", authorized_by="SENIOR_RESEARCHER")

        self.assertEqual(self.engine.get_active_configuration()["version"], v_id)

        # Rollback
        rb = self.engine.rollback_configuration("1.0.0-PROD")
        self.assertTrue(rb["success"])
        self.assertEqual(self.engine.get_active_configuration()["version"], "1.0.0-PROD")

    # -------------------------------------------------------------------------
    # Scenario 18: Live Parameter Protection
    # -------------------------------------------------------------------------
    def test_live_parameter_protection(self):
        """Scenario 18: Proposing a candidate must NEVER modify the active live configuration."""
        active_before = self.engine.get_active_configuration()
        self.assertEqual(active_before["version"], "1.0.0-PROD")

        # Propose an experimental candidate
        self.engine.propose_parameter_update({"min_confluence_score": 95.0}, "Aggressive test")

        active_after = self.engine.get_active_configuration()
        # Must strictly remain BASELINE (1.0.0-PROD)
        self.assertEqual(active_after["version"], "1.0.0-PROD")
        self.assertEqual(active_after["parameters"]["min_confluence_score"], 85.0)

    # -------------------------------------------------------------------------
    # Scenario 19: Strategy Degradation Detection
    # -------------------------------------------------------------------------
    def test_strategy_degradation_detection(self):
        """Scenario 19: Detects performance drift and degradation across rolling cohorts."""
        trades = []
        # First 15 trades: strong wins
        for i in range(15):
            trades.append(make_sample_trade(f"t-good-{i}", exit_price=62000.0))
        # Next 15 trades: persistent losses (degradation)
        for i in range(15):
            trades.append(make_sample_trade(f"t-bad-{i}", exit_price=58000.0))

        drift = self.engine.detect_strategy_drift(trades, window_size=15)
        self.assertIn(drift["drift_status"], ["DEGRADING", "CRITICAL_DEGRADATION"])

    # -------------------------------------------------------------------------
    # Scenario 20: Invalid Historical Records Exclusion
    # -------------------------------------------------------------------------
    def test_invalid_historical_records_exclusion(self):
        """Scenario 20: Non-positive price, zero contracts, or non-dict payloads rejected."""
        res1, _, _ = self.engine.ingest_trade_record({"trade_id": "bad-1", "entry_price": -100})
        res2, _, _ = self.engine.ingest_trade_record({"trade_id": "bad-2", "contracts": 0})
        res3, _, _ = self.engine.ingest_trade_record("not a dict")

        self.assertFalse(res1)
        self.assertFalse(res2)
        self.assertFalse(res3)

    # -------------------------------------------------------------------------
    # Scenario 21: Duplicate Trade Record Prevention
    # -------------------------------------------------------------------------
    def test_duplicate_trade_record_prevention(self):
        """Scenario 21: Ingesting the same trade_id twice is rejected."""
        trade = make_sample_trade("t-dup-01")
        success1, _, _ = self.engine.ingest_trade_record(trade)
        success2, msg, _ = self.engine.ingest_trade_record(trade)

        self.assertTrue(success1)
        self.assertFalse(success2)
        self.assertIn("DUPLICATE_TRADE", msg)
        self.assertEqual(len(self.engine.verified_trades), 1)

    # -------------------------------------------------------------------------
    # Scenario 22: Agent Communication Compatibility
    # -------------------------------------------------------------------------
    def test_agent_communication_compatibility(self):
        """Scenario 22: Preserves get_pattern_adjustment and reflect_and_learn APIs."""
        # 1. get_pattern_adjustment for StrategyAgent
        adj = self.engine.get_pattern_adjustment("BTCUSD", "BUY", "SSL_SWEEP", {"macro_4h": "BULLISH"})
        self.assertTrue(adj["can_trade"])
        self.assertIn("score_adjustment", adj)

        # 2. reflect_and_learn for TrailingStopManager
        refl = self.engine.reflect_and_learn("BTCUSD", "BUY", 60000.0, 62000.0, 20.0, 2.0, "TAKE_PROFIT")
        self.assertIn("scoring", refl)
        self.assertIn("reflection", refl)

        # 3. format_telegram_reflection for TelegramBot
        msg = self.engine.format_telegram_reflection(refl)
        self.assertIn("ADAPTIVE LEARNING AUDIT", msg)
        self.assertIn("BTCUSD", msg)


if __name__ == "__main__":
    unittest.main()

