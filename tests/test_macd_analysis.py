"""
Unit tests for MACD indicator engine and multi-agent confluence integration.
"""

import unittest
from src.technical_analysis import analyze_macd, calculate_macd, analyze_vwap, calculate_vwap
from multiagent_team.strategy_agent import StrategyAgent


class TestMACDAnalysis(unittest.TestCase):
    def test_analyze_vwap_structure(self):
        highs = [100.0 + i for i in range(30)]
        lows = [98.0 + i for i in range(30)]
        closes = [99.0 + i for i in range(30)]
        volumes = [1000.0 + (i * 10) for i in range(30)]

        vwap_res = analyze_vwap(highs, lows, closes, volumes)
        self.assertIn("vwap", vwap_res)
        self.assertIn("upper_band_1", vwap_res)
        self.assertIn("lower_band_1", vwap_res)
        self.assertIn("upper_band_2", vwap_res)
        self.assertIn("lower_band_2", vwap_res)
        self.assertIn("stance", vwap_res)
        self.assertIn("band_location", vwap_res)
        self.assertIn("slope", vwap_res)

        self.assertGreater(vwap_res["upper_band_1"], vwap_res["vwap"])
        self.assertLess(vwap_res["lower_band_1"], vwap_res["vwap"])
        self.assertGreater(vwap_res["upper_band_2"], vwap_res["upper_band_1"])
        self.assertLess(vwap_res["lower_band_2"], vwap_res["lower_band_1"])
        self.assertEqual(vwap_res["slope"], "RISING_BULLISH")

    def test_analyze_macd_structure(self):
        # Generate 55 synthetic closing prices with an accelerating upward trend
        closes = [100.0 + (i ** 1.3) for i in range(55)]
        res = analyze_macd(closes)

        self.assertIn("macd", res)
        self.assertIn("signal", res)
        self.assertIn("histogram", res)
        self.assertIn("crossover", res)
        self.assertIn("zero_line", res)
        self.assertIn("momentum_phase", res)
        self.assertIn("bias", res)

        self.assertEqual(res["zero_line"], "ABOVE_ZERO")
        self.assertIn(res["bias"], ["BULLISH", "STRONG_BULLISH"])
        self.assertGreater(res["macd"], 0)

    def test_analyze_macd_bearish_trend(self):
        # Generate 55 synthetic closing prices with an accelerating downward trend
        closes = [500.0 - (i ** 1.3) for i in range(55)]
        res = analyze_macd(closes)

        self.assertEqual(res["zero_line"], "BELOW_ZERO")
        self.assertIn(res["bias"], ["BEARISH", "STRONG_BEARISH"])
        self.assertLess(res["macd"], 0)

    def test_strategy_agent_macd_confluence_scoring(self):
        agent = StrategyAgent()

        # Mock analysis with bullish setup and bullish MACD
        analysis_bullish = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "vwap": 69900.0,
            "spread_pct": 0.02,
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "strategy": "Bullish_Order_Block",
                "score": 88,
                "entry_price": 70000.0,
                "stop_loss_price": 69000.0,
                "take_profit_price": 73000.0,
                "thesis": "15m SMC Order Block Alignment"
            },
            "macro_15m": {
                "regime": "BULLISH",
                "macd": {
                    "crossover": "BULLISH_CROSS",
                    "momentum_phase": "BULLISH_EXPANSION",
                    "histogram": 15.5,
                    "bias": "STRONG_BULLISH"
                }
            },
            "macd": {
                "bias": "BULLISH"
            }
        }

        setup = agent.evaluate_setup(analysis_bullish)
        self.assertIsNotNone(setup)
        self.assertIn("confluence", setup)
        self.assertIn("macd_detail", setup["confluence"])
        self.assertIn("BULLISH_CROSS", setup["confluence"]["macd_detail"])
        self.assertIn("vwap_detail", setup["confluence"])
        self.assertIn("AT_VWAP", setup["confluence"]["vwap_detail"])
        # Score boosted by primary asset (+10), VWAP alignment (+5), and MACD impulse (+6)
        self.assertGreaterEqual(setup["score"], 90)

    def test_liquidity_analysis_and_structure(self):
        from src.technical_analysis import analyze_liquidity_pools_and_sweeps
        # 30 bars series with a swing high at bar 10 (110.0) and swing low at bar 20 (90.0)
        highs = [100.0] * 30
        lows = [95.0] * 30
        closes = [98.0] * 30
        volumes = [1000.0] * 30

        # Form swing high at index 10 (pivot_window=3 requires 3 bars before and after to be lower)
        highs[10] = 110.0
        # Form swing low at index 20
        lows[20] = 90.0
        # Current bar at index 29: price at 100.0
        closes[-1] = 100.0

        liq_res = analyze_liquidity_pools_and_sweeps(highs, lows, closes, volumes, pivot_window=3)
        self.assertIn("nearest_bsl", liq_res)
        self.assertIn("nearest_ssl", liq_res)
        self.assertIn("bsl_distance_pct", liq_res)
        self.assertIn("ssl_distance_pct", liq_res)
        self.assertIn("liquidity_structure", liq_res)
        self.assertEqual(liq_res["nearest_bsl"], 110.0)
        self.assertEqual(liq_res["nearest_ssl"], 90.0)
        self.assertAlmostEqual(liq_res["bsl_distance_pct"], 10.0, places=1)
        self.assertAlmostEqual(liq_res["ssl_distance_pct"], 10.0, places=1)

    def test_strategy_agent_liquidity_confluence(self):
        agent = StrategyAgent()
        analysis_liq = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "vwap": 70000.0,
            "spread_pct": 0.02,
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "strategy": "Liquidity_Sweep_MSS",
                "score": 85,
                "entry_price": 70000.0,
                "stop_loss_price": 69200.0,
                "take_profit_price": 72500.0,
                "thesis": "SSL Sweep and MSS Confirmed"
            },
            "liquidity": {
                "nearest_bsl": 72500.0,
                "nearest_ssl": 69000.0,
                "bsl_distance_pct": 3.57,
                "ssl_distance_pct": 1.43,
                "liquidity_structure": "SWEEP_MSS_CONFIRMED",
                "sweep_type": "BULLISH_SSL_SWEEP",
                "mss_confirmed": True
            }
        }
        setup = agent.evaluate_setup(analysis_liq)
        self.assertIsNotNone(setup)
        self.assertIn("liquidity_detail", setup["confluence"])
        self.assertIn("SWEEP_MSS_CONFIRMED", setup["confluence"]["liquidity_detail"])
        self.assertIn("BSL: $72,500.00", setup["confluence"]["liquidity_detail"])
        # Score boosted by Primary (+10), Bullish SSL Sweep + MSS (+8), BSL target (+3)
        self.assertGreaterEqual(setup["score"], 95)
        self.assertIn("💧 [BULLISH SSL SWEEP + MSS CONFIRMED]", setup["thesis"])

    def test_calculate_atr_calibrated_stops_engine(self):
        from src.technical_analysis import calculate_atr_calibrated_stops

        # 1. Buy setup with structural pivot below entry
        res_buy = calculate_atr_calibrated_stops(
            entry_price=70000.0,
            side="buy",
            structural_pivot=69500.0,
            atr=400.0,
            volatility_state="NORMAL",
            target_rr_ratio=2.5
        )
        self.assertLess(res_buy["stop_loss_price"], 69500.0)  # Must include buffer below pivot
        self.assertGreater(res_buy["take_profit_price"], 70000.0)
        self.assertAlmostEqual(res_buy["planned_rr_ratio"], 2.5, places=1)
        self.assertGreaterEqual(res_buy["atr_stop_multiple"], 0.45)
        self.assertLessEqual(res_buy["atr_stop_multiple"], 2.80)

        # 2. Sell setup with structural pivot above entry in EXPANSION
        res_sell = calculate_atr_calibrated_stops(
            entry_price=70000.0,
            side="sell",
            structural_pivot=70400.0,
            atr=500.0,
            volatility_state="EXPANSION",
            target_rr_ratio=2.5
        )
        self.assertGreater(res_sell["stop_loss_price"], 70400.0)  # Must include buffer above pivot
        self.assertLess(res_sell["take_profit_price"], 70000.0)
        self.assertGreaterEqual(res_sell["stop_distance"], 500.0)

    def test_strategy_agent_atr_validation(self):
        agent = StrategyAgent()

        # Sub-ATR micro-stop setup ($100 stop when 15m ATR is $600 -> 0.17x ATR)
        micro_stop_analysis = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 90,
                "entry_price": 70000.0,
                "stop_loss_price": 69900.0,
                "take_profit_price": 70500.0,
                "atr_14": 600.0
            },
            "macro_15m": {"atr_14": 600.0}
        }
        setup_micro = agent.evaluate_setup(micro_stop_analysis)
        self.assertIsNone(setup_micro)  # MUST be vetoed!

        # Optimal ATR stop ($600 stop when ATR is $600 -> 1.0x ATR)
        optimal_stop_analysis = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 86,
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,  # 600 stop
                "take_profit_price": 71500.0,
                "atr_14": 600.0
            },
            "macro_15m": {"atr_14": 600.0}
        }
        setup_opt = agent.evaluate_setup(optimal_stop_analysis)
        self.assertIsNotNone(setup_opt)
        self.assertIn("atr_detail", setup_opt["confluence"])
        self.assertIn("1.00x ATR", setup_opt["confluence"]["atr_detail"])
        self.assertIn("🛡️ [OPTIMAL 1.0x ATR STOP]", setup_opt["thesis"])


if __name__ == "__main__":
    unittest.main()
