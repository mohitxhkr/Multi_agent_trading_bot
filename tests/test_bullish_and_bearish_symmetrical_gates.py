import unittest
import numpy as np
from src.technical_analysis import analyze_multi_timeframe
from multiagent_team.time_machine_agent import TimeMachineAgent
from multiagent_team.strategy_agent import StrategyAgent

class TestBullishAndBearishSymmetricalGates(unittest.TestCase):
    def setUp(self):
        self.tm = TimeMachineAgent()
        self.strategy_agent = StrategyAgent()

    def _generate_synthetic_candles(self, trend="bullish", n_bars=200, base_price=65000.0):
        # Realistic oscillating trend generator with authentic RSI range
        c = [base_price]
        for i in range(n_bars):
            drift = 10.0 if trend == "bullish" else -10.0
            wave = 30.0 * np.sin(i / 3.0) + (i % 3 - 1) * 20.0
            c.append(c[-1] + drift + wave)
        c = c[1:]
        o = [c[i - 1] if i > 0 else c[0] for i in range(n_bars)]
        h = [max(o[i], c[i]) + 40.0 for i in range(n_bars)]
        l = [min(o[i], c[i]) - 40.0 for i in range(n_bars)]
        v = [100.0] * n_bars
        t = [1700000000 + i * 900 for i in range(n_bars)]
        return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}

    def test_bullish_breakout_long_generated_and_verified(self):
        """Verify that in a bullish market, Institutional_Bullish_Breakout_Long is generated with valid geometry."""
        c15 = self._generate_synthetic_candles(trend="bullish", n_bars=200, base_price=65000.0)
        c1h = self._generate_synthetic_candles(trend="bullish", n_bars=200, base_price=65000.0)
        c4h = self._generate_synthetic_candles(trend="bullish", n_bars=100, base_price=65000.0)
        c1d = self._generate_synthetic_candles(trend="bullish", n_bars=50, base_price=65000.0)
        
        analysis = analyze_multi_timeframe(
            candles_1h=c1h,
            candles_4h=c4h,
            candles_1d=c1d,
            candles_1w=None,
            candles_15m=c15,
            symbol="BTCUSD"
        )
        
        hp = analysis.get("high_probability_setup", {})
        self.assertTrue(hp.get("qualified"), f"Setup not qualified: {hp}")
        self.assertEqual(hp.get("side"), "buy")
        self.assertEqual(hp.get("strategy"), "Institutional_Bullish_Breakout_Long")
        
        entry = hp.get("entry_price")
        sl = hp.get("stop_loss_price")
        tp = hp.get("take_profit_price")
        
        self.assertGreater(entry, sl, "Long SL must be below entry")
        self.assertGreater(tp, entry, "Long TP must be above entry")
        sl_pct = (entry - sl) / entry
        self.assertGreaterEqual(sl_pct, 0.0080, "Long SL must respect minimum 0.80% structural buffer")

    def test_bearish_breakdown_short_generated_and_verified(self):
        """Verify that in a bearish market, Institutional_Bearish_Breakdown_Short is generated with valid geometry."""
        c15 = self._generate_synthetic_candles(trend="bearish", n_bars=200, base_price=75000.0)
        c1h = self._generate_synthetic_candles(trend="bearish", n_bars=200, base_price=75000.0)
        c4h = self._generate_synthetic_candles(trend="bearish", n_bars=100, base_price=75000.0)
        c1d = self._generate_synthetic_candles(trend="bearish", n_bars=50, base_price=75000.0)
        
        analysis = analyze_multi_timeframe(
            candles_1h=c1h,
            candles_4h=c4h,
            candles_1d=c1d,
            candles_1w=None,
            candles_15m=c15,
            symbol="BTCUSD"
        )
        
        hp = analysis.get("high_probability_setup", {})
        self.assertTrue(hp.get("qualified"), f"Setup not qualified: {hp}")
        self.assertEqual(hp.get("side"), "sell")
        self.assertEqual(hp.get("strategy"), "Institutional_Bearish_Breakdown_Short")
        
        entry = hp.get("entry_price")
        sl = hp.get("stop_loss_price")
        tp = hp.get("take_profit_price")
        
        self.assertGreater(sl, entry, "Short SL must be above entry")
        self.assertGreater(entry, tp, "Short TP must be below entry")
        sl_pct = (sl - entry) / entry
        self.assertGreaterEqual(sl_pct, 0.0080, "Short SL must respect minimum 0.80% structural buffer")

if __name__ == "__main__":
    unittest.main()
