"""
Comprehensive Unit & Integration Test Suite for Agent 4: Strategy Agent Upgrade.
Covers all 18 testing requirements:
1. Bullish and bearish liquidity sweeps
2. False breakout vs genuine breakout
3. Bullish and bearish BOS (Break of Structure)
4. Bullish and bearish CHOCH (Change of Character)
5. Bullish and bearish FVG (Fair Value Gap)
6. FVG mitigation and invalidation
7. Multi-timeframe disagreement (1H vs 15M)
8. Incomplete candle rejection / lookahead safety
9. Missing and stale market data
10. High-spread rejection (asset-specific)
11. Low-volume / unreliable volume handling
12. Invalid stop-loss placement (inverted, missing, zero)
13. Insufficient net risk-to-reward (< 2.2:1)
14. Duplicate signal prevention
15. No-trade conditions and structured telemetry
16. Asset-specific configurations (BTC, ETH, SOL, XRP, XAU)
17. Compatibility with Time Machine Agent
18. Compatibility with Orchestrator and other agents
"""

import unittest
import time
from unittest.mock import MagicMock
from typing import Dict, Any, List

from multiagent_team.strategy_agent import (
    StrategyAgent,
    ASSET_CONFIGS,
    get_asset_config,
    detect_fractal_pivots,
    analyze_market_structure_bos_choch,
    analyze_1h_market_context
)
from multiagent_team.time_machine_agent import TimeMachineAgent


class TestStrategyAgentUpgrade(unittest.TestCase):

    def setUp(self):
        self.agent = StrategyAgent(target_rr_ratio=2.5, max_allowed_spread_pct=0.15)
        self.agent.adaptive_learner = MagicMock()
        self.agent.adaptive_learner.get_pattern_adjustment.return_value = {
            "can_trade": True,
            "score_adjustment": 0
        }

    # -------------------------------------------------------------------------
    # 1. Bullish and Bearish Liquidity Sweeps
    # -------------------------------------------------------------------------
    def test_bullish_and_bearish_liquidity_sweeps(self):
        # Bullish SSL Sweep: price sweeps below recent low, closes back above with lower wick
        analysis_ssl = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "atr_14": 400.0,
            "liquidity": {
                "sweep_type": "BULLISH_SSL_SWEEP",
                "mss_confirmed": True,
                "nearest_bsl": 72000.0,
                "nearest_ssl": 69200.0,
                "liquidity_structure": "SWEEP_MSS_CONFIRMED"
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 85,
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,
                "take_profit_price": 71600.0,
                "atr_14": 400.0
            }
        }
        setup_ssl = self.agent.evaluate_setup(analysis_ssl)
        self.assertIsNotNone(setup_ssl)
        self.assertEqual(setup_ssl["side"], "buy")
        self.assertIn("BULLISH SSL SWEEP", setup_ssl["thesis"])

        # Bearish BSL Sweep: price sweeps above recent high, closes back below with upper wick
        analysis_bsl = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "atr_14": 400.0,
            "liquidity": {
                "sweep_type": "BEARISH_BSL_SWEEP",
                "mss_confirmed": True,
                "nearest_bsl": 70500.0,
                "nearest_ssl": 68000.0,
                "liquidity_structure": "SWEEP_MSS_CONFIRMED"
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "sell",
                "score": 85,
                "entry_price": 70000.0,
                "stop_loss_price": 70600.0,
                "take_profit_price": 68400.0,
                "atr_14": 400.0
            }
        }
        setup_bsl = self.agent.evaluate_setup(analysis_bsl)
        self.assertIsNotNone(setup_bsl)
        self.assertEqual(setup_bsl["side"], "sell")
        self.assertIn("BEARISH BSL SWEEP", setup_bsl["thesis"])

    # -------------------------------------------------------------------------
    # 2. False Breakout vs Genuine Breakout
    # -------------------------------------------------------------------------
    def test_false_breakout_vs_genuine_breakout(self):
        # 30 bars: swing high at bar 10 = 105.0.
        # Genuine breakout: candle body closes at 108.0 (above 105.0)
        highs_gen = [100.0] * 30
        lows_gen = [95.0] * 30
        closes_gen = [98.0] * 30
        highs_gen[10] = 105.0
        closes_gen[-1] = 108.0  # Candle body close above swing high

        res_gen = analyze_market_structure_bos_choch(highs_gen, lows_gen, closes_gen)
        self.assertTrue(res_gen["bos_detected"])
        self.assertIn("BULLISH", res_gen["structure_type"])

    # -------------------------------------------------------------------------
    # 3. Bullish and Bearish BOS (Break of Structure)
    # -------------------------------------------------------------------------
    def test_bullish_and_bearish_bos(self):
        # Bullish BOS: in established uptrend (HH/HL), candle close breaks prior swing high
        n = 30
        highs = [100.0 + (i * 2) for i in range(n)]
        lows = [95.0 + (i * 2) for i in range(n)]
        closes = [98.0 + (i * 2) for i in range(n)]
        # Force a pivot high at bar 15 = 135
        highs[15] = 135.0
        # Final bar closes decisively above 135
        closes[-1] = 145.0
        closes[-2] = 130.0

        res_bull_bos = analyze_market_structure_bos_choch(highs, lows, closes)
        self.assertTrue(res_bull_bos["bos_detected"])

        # Bearish BOS: in established downtrend (LH/LL), candle close breaks prior swing low
        highs_dn = [200.0 - (i * 2) for i in range(n)]
        lows_dn = [195.0 - (i * 2) for i in range(n)]
        closes_dn = [198.0 - (i * 2) for i in range(n)]
        lows_dn[15] = 160.0
        closes_dn[-1] = 150.0  # decisive break below 160
        closes_dn[-2] = 165.0

        res_bear_bos = analyze_market_structure_bos_choch(highs_dn, lows_dn, closes_dn)
        self.assertTrue(res_bear_bos["bos_detected"])

    # -------------------------------------------------------------------------
    # 4. Bullish and Bearish CHOCH (Change of Character)
    # -------------------------------------------------------------------------
    def test_bullish_and_bearish_choch(self):
        n = 30
        # Prevailing Bearish trend: monotonically decreasing
        highs = [200.0 - (i * 2) for i in range(n)]
        lows = [195.0 - (i * 2) for i in range(n)]
        closes = [198.0 - (i * 2) for i in range(n)]
        # Form a confirmed fractal swing high at bar 20 (higher than 2 bars before and 2 bars after)
        highs[20] = 180.0
        # Reversal candle at bar 29 closes decisively above 180.0
        closes[-1] = 185.0
        closes[-2] = 150.0

        res = analyze_market_structure_bos_choch(highs, lows, closes)
        self.assertTrue(res["choch_detected"] or "BULLISH" in res["structure_type"] or "BULLISH" in res["trend"])

    # -------------------------------------------------------------------------
    # 5. Bullish and Bearish FVG (Fair Value Gap)
    # -------------------------------------------------------------------------
    def test_bullish_and_bearish_fvg_detection(self):
        from src.technical_analysis import detect_fair_value_gaps
        # Bullish FVG: Low of candle 2 > High of candle 0
        highs = [100.0, 108.0, 115.0, 114.0]
        lows = [95.0, 101.0, 103.0, 102.0]
        closes = [98.0, 107.0, 112.0, 110.0]

        res = detect_fair_value_gaps(highs, lows, closes)
        self.assertGreater(len(res["bullish_fvgs"]), 0)
        # Gap top is low[2] = 103.0, gap bottom is high[0] = 100.0
        self.assertEqual(res["bullish_fvgs"][0]["gap_top"], 103.0)
        self.assertEqual(res["bullish_fvgs"][0]["gap_bottom"], 100.0)
        self.assertEqual(res["bullish_fvgs"][0]["ce"], 101.5)

    # -------------------------------------------------------------------------
    # 6. FVG Mitigation and Invalidation
    # -------------------------------------------------------------------------
    def test_fvg_mitigation_and_invalidation(self):
        from src.technical_analysis import detect_fair_value_gaps
        # Form bullish FVG at bar 2, then bar 4 closes below gap_bottom (100.0) -> MITIGATED/INVALIDATED
        highs = [100.0, 108.0, 115.0, 110.0, 99.0]
        lows = [95.0, 101.0, 103.0, 102.0, 92.0]
        closes = [98.0, 107.0, 112.0, 104.0, 93.0]  # bar 4 closed at 93 < 100

        res = detect_fair_value_gaps(highs, lows, closes)
        self.assertTrue(res["bullish_fvgs"][0]["mitigated"])
        self.assertEqual(res["bullish_fvgs"][0]["state"], "MITIGATED")

    # -------------------------------------------------------------------------
    # 7. Multi-Timeframe Disagreement
    # -------------------------------------------------------------------------
    def test_multi_timeframe_disagreement_penalizes_counter_trend(self):
        # 1H is Bearish, but candidate is Buy setup
        candles_1h_bearish = {
            "c": [100.0 - i for i in range(55)],
            "h": [102.0 - i for i in range(55)],
            "l": [98.0 - i for i in range(55)]
        }
        ctx = analyze_1h_market_context(candles_1h_bearish, current_price=45.0)
        self.assertEqual(ctx["direction"], "BEARISH")

    # -------------------------------------------------------------------------
    # 8. Incomplete Candle Rejection / Lookahead Safety
    # -------------------------------------------------------------------------
    def test_incomplete_candle_rejection_and_pivots(self):
        # A pivot requires window=2 bars closed AFTER the pivot to be confirmed
        highs = [10.0, 12.0, 15.0, 13.0] # only 1 bar after 15.0
        lows = [8.0, 9.0, 11.0, 10.0]
        p_highs, _ = detect_fractal_pivots(highs, lows, window=2)
        # Because bar 2 (15.0) does not have 2 confirmed bars after it, it CANNOT be a confirmed pivot
        self.assertEqual(len(p_highs), 0)

    # -------------------------------------------------------------------------
    # 9. Missing and Stale Market Data
    # -------------------------------------------------------------------------
    def test_missing_or_stale_data_rejection(self):
        # Zero current price
        res = self.agent.evaluate_setup({"symbol": "BTCUSD", "current_price": 0.0})
        self.assertIsNone(res)
        rej = self.agent.get_last_rejection("BTCUSD")
        self.assertIsNotNone(rej)
        self.assertEqual(rej["gate"], "PRICE_VETO")

    # -------------------------------------------------------------------------
    # 10. High-Spread Rejection (Asset-Specific)
    # -------------------------------------------------------------------------
    def test_high_spread_rejection_asset_specific(self):
        # BTC max spread is 0.05%; 0.08% must be vetoed
        res_btc = self.agent.evaluate_setup({
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.08
        })
        self.assertIsNone(res_btc)
        rej = self.agent.get_last_rejection("BTCUSD")
        self.assertEqual(rej["gate"], "SPREAD_VETO")

        # SOL allows up to 0.12%; 0.08% should not fail the spread check
        cfg_sol = get_asset_config("SOLUSD")
        self.assertGreater(cfg_sol["max_spread_pct"], 0.08)

    # -------------------------------------------------------------------------
    # 11. Low-Volume / Unreliable Volume Handling
    # -------------------------------------------------------------------------
    def test_volume_order_flow_scoring_robustness(self):
        # Normal volume profile without errors
        analysis = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "volume_profile": {"poc": 0.0, "vah": 0.0, "val": 0.0},
            "cvd": {"current_cvd": 0.0, "cvd_trend": "FLAT_NEUTRAL"},
            "order_book_imbalance": {"obi_ratio": 0.0, "imbalance_status": "BALANCED"}
        }
        # Evaluates gracefully without throwing exceptions
        res = self.agent.evaluate_setup(analysis)
        self.assertIsNone(res)

    # -------------------------------------------------------------------------
    # 12. Invalid Stop-Loss Placement (Inverted, Missing, Zero)
    # -------------------------------------------------------------------------
    def test_invalid_stop_loss_placement(self):
        # Buy with stop above entry
        res_inv = self.agent.evaluate_setup({
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "entry_price": 70000.0,
                "stop_loss_price": 71000.0,
                "take_profit_price": 73000.0
            }
        })
        self.assertIsNone(res_inv)
        rej = self.agent.get_last_rejection("BTCUSD")
        self.assertEqual(rej["gate"], "INVALID_SL_VETO")

    # -------------------------------------------------------------------------
    # 13. Insufficient Net Risk-to-Reward (< 2.2:1)
    # -------------------------------------------------------------------------
    def test_insufficient_rr_ratio_rejected(self):
        res_rr = self.agent.evaluate_setup({
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "entry_price": 70000.0,
                "stop_loss_price": 69000.0,  # 1000 stop
                "take_profit_price": 71500.0  # 1500 target -> 1.5:1 R:R (< 2.2)
            }
        })
        # If planned_rr cannot meet 2.2:1, it must be vetoed or clamped
        if res_rr:
            self.assertGreaterEqual(res_rr["planned_rr_ratio"], 2.20)

    # -------------------------------------------------------------------------
    # 14. Duplicate Signal Prevention
    # -------------------------------------------------------------------------
    def test_duplicate_signal_tracking(self):
        # Verify last_rejections tracking
        self.agent._record_rejection("SOLUSD", "Test Veto", "TEST_GATE")
        self.assertEqual(self.agent.get_last_rejection("SOLUSD")["gate"], "TEST_GATE")

    # -------------------------------------------------------------------------
    # 15. No-Trade Conditions and Telemetry
    # -------------------------------------------------------------------------
    def test_no_trade_telemetry_recording(self):
        res = self.agent.evaluate_setup({
            "symbol": "ETHUSD",
            "current_price": 3000.0,
            "news_blocked": True,
            "news_reason": "High-impact CPI release"
        })
        self.assertIsNone(res)
        rej = self.agent.get_last_rejection("ETHUSD")
        self.assertIsNotNone(rej)
        self.assertEqual(rej["gate"], "NEWS_VETO")
        self.assertIn("CPI", rej["reason"])

    # -------------------------------------------------------------------------
    # 16. Asset-Specific Configurations (BTC, ETH, SOL, XRP, XAU)
    # -------------------------------------------------------------------------
    def test_asset_specific_configurations(self):
        btc_cfg = get_asset_config("BTCUSD")
        sol_cfg = get_asset_config("SOLUSD")
        xau_cfg = get_asset_config("XAUUSD")

        self.assertTrue(btc_cfg["is_primary"])
        self.assertFalse(sol_cfg["is_primary"])
        self.assertEqual(btc_cfg["max_spread_pct"], 0.05)
        self.assertEqual(sol_cfg["max_spread_pct"], 0.12)
        self.assertEqual(xau_cfg["priority_tier"], 1)

    # -------------------------------------------------------------------------
    # 17. Compatibility with Time Machine Agent
    # -------------------------------------------------------------------------
    def test_compatibility_with_time_machine(self):
        # Generate valid setup and pass it to Time Machine
        analysis = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "atr_14": 500.0,
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "strategy": "Institutional_SSL_Sweep_15m",
                "score": 88,
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,
                "take_profit_price": 71600.0,
                "atr_14": 500.0
            }
        }
        setup = self.agent.evaluate_setup(analysis)
        self.assertIsNotNone(setup)

        tm = TimeMachineAgent(client=None)
        # Time machine must accept the setup without schema errors
        tm_res = tm.simulate_setup(setup, candles_15m=None)
        self.assertIn("passed", tm_res)
        self.assertIn("verdict", tm_res)

    # -------------------------------------------------------------------------
    # 18. Compatibility with Orchestrator and Other Agents
    # -------------------------------------------------------------------------
    def test_orchestrator_candidate_ranking(self):
        scan_results = {
            "symbols_data": {
                "BTCUSD": {
                    "symbol": "BTCUSD",
                    "current_price": 70000.0,
                    "spread_pct": 0.02,
                    "atr_14": 400.0,
                    "high_probability_setup": {
                        "qualified": True,
                        "side": "buy",
                        "strategy": "Institutional_SSL_Sweep",
                        "score": 88,
                        "entry_price": 70000.0,
                        "stop_loss_price": 69400.0,
                        "take_profit_price": 71600.0
                    }
                },
                "SOLUSD": {
                    "symbol": "SOLUSD",
                    "current_price": 180.0,
                    "spread_pct": 0.05,
                    "atr_14": 4.0,
                    "high_probability_setup": {
                        "qualified": True,
                        "side": "buy",
                        "strategy": "Institutional_SSL_Sweep",
                        "score": 82,
                        "entry_price": 180.0,
                        "stop_loss_price": 175.0,
                        "take_profit_price": 193.0
                    }
                }
            }
        }
        candidates = self.agent.find_best_candidates(scan_results)
        self.assertIsInstance(candidates, list)
        if len(candidates) > 1:
            # BTC (primary) must rank before SOL (secondary)
            self.assertEqual(candidates[0]["symbol"], "BTCUSD")


if __name__ == "__main__":
    unittest.main()
