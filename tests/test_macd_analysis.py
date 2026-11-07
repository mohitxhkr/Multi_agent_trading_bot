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


if __name__ == "__main__":
    unittest.main()
