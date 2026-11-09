import unittest
from src.technical_analysis import calculate_breakout_breakdown_levels

class TestBreakoutBreakdownLevels(unittest.TestCase):
    def test_basic_levels_calculation(self):
        mock_analysis = {
            "symbol": "BTCUSD",
            "current_price": 75000.0,
            "atr_14": 500.0,
            "atr_pct": 0.67,
            "liquidity": {
                "bsl_levels": [76000.0, 77500.0],
                "ssl_levels": [74000.0, 73000.0]
            },
            "volume_profile": {
                "poc_price": 75100.0,
                "value_area_high": 75800.0,
                "value_area_low": 74200.0
            },
            "vwap": 74900.0,
            "vwap_analysis": {
                "upper_band_1": 75400.0,
                "lower_band_1": 74400.0,
                "stance": "ABOVE_VWAP",
                "slope": "FLAT"
            },
            "fvg": {},
            "cvd": {"cvd_trend": "RISING_ACCUMULATION", "divergence": "NONE"},
            "order_book_imbalance": {"imbalance_status": "HEAVY_BID_IMBALANCE", "obi_ratio": 0.35},
            "macd": {"bias": "BULLISH", "momentum_phase": "EXPANSION"}
        }

        res = calculate_breakout_breakdown_levels(mock_analysis)
        self.assertNotIn("error", res)
        self.assertEqual(res["symbol"], "BTCUSD")
        self.assertEqual(res["current_price"], 75000.0)

        # Breakout level should be above 75000
        self.assertGreater(res["breakout_level"], 75000.0)
        self.assertGreater(res["distance_to_breakout_pct"], 0.0)

        # Breakdown level should be below 75000
        self.assertLess(res["breakdown_level"], 75000.0)
        self.assertGreater(res["distance_to_breakdown_pct"], 0.0)

        # Plans should have valid TP, SL, R:R >= 2.0
        bo = res["bullish_breakout_plan"]
        self.assertGreater(bo["take_profit_price"], bo["trigger_price"])
        self.assertLess(bo["stop_loss_price"], bo["trigger_price"])
        self.assertGreaterEqual(bo["planned_rr"], 2.0)

        bd = res["bearish_breakdown_plan"]
        self.assertLess(bd["take_profit_price"], bd["trigger_price"])
        self.assertGreater(bd["stop_loss_price"], bd["trigger_price"])
        self.assertGreaterEqual(bd["planned_rr"], 2.0)

    def test_imminent_proximity_detection(self):
        # Current price within 0.2% of breakout level
        mock_analysis = {
            "symbol": "ETHUSD",
            "current_price": 2500.0,
            "atr_14": 20.0,
            "atr_pct": 0.8,
            "liquidity": {
                "bsl_levels": [2505.0],  # 0.2% away
                "ssl_levels": [2450.0]
            },
            "volume_profile": {
                "value_area_high": 2505.0,
                "value_area_low": 2450.0
            },
            "vwap": 2490.0,
            "vwap_analysis": {}
        }

        res = calculate_breakout_breakdown_levels(mock_analysis)
        self.assertTrue(res["is_imminent"])
        self.assertEqual(res["proximity_status"], "TESTING_BREAKOUT")

    def test_invalid_price_handling(self):
        res = calculate_breakout_breakdown_levels({"symbol": "BTCUSD", "current_price": 0.0})
        self.assertIn("error", res)

if __name__ == "__main__":
    unittest.main()
