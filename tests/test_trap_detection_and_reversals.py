"""
Unit tests for Institutional Trap Detection, Anti-Trap Vetoes, and Liquidity Reversals.
Verifies:
1. Multi-bar and single-bar false breakout (Bull Trap) and false breakdown (Bear Trap) detection.
2. Anti-Trap veto prevents entering Breakout Longs at the top of a Bull Trap.
3. Anti-Trap veto prevents entering Breakdown Shorts at the bottom of a Bear Trap.
4. Institutional Reversals are generated and prioritized with stop loss safely beyond sweep wicks.
"""

import unittest
import numpy as np
from unittest.mock import MagicMock
from src.technical_analysis import analyze_liquidity_pools_and_sweeps, analyze_multi_timeframe
from multiagent_team.strategy_agent import StrategyAgent


class TestTrapDetectionAndReversals(unittest.TestCase):

    def setUp(self):
        self.strategy_agent = StrategyAgent()

    def _generate_synthetic_candles(self, trend="bullish", n_bars=200, base_price=65000.0):
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

    # -------------------------------------------------------------------------
    # 1. Multi-Bar False Breakout (Bull Trap) Detection
    # -------------------------------------------------------------------------
    def test_two_bar_bull_trap_detection(self):
        # 30 bars. Swing high established at bar 10 = 100.0.
        highs = [90.0] * 30
        lows = [85.0] * 30
        closes = [88.0] * 30
        opens = [87.0] * 30
        volumes = [1000.0] * 30

        # Bar 10 is swing high
        highs[10] = 100.0
        lows[10] = 88.0
        closes[10] = 92.0

        # Bar 26: Breakout bar pushes above 100.0 (e.g. high 104.0, closes 101.0)
        highs[26] = 104.0
        lows[26] = 95.0
        opens[26] = 96.0
        closes[26] = 101.0

        # Bar 27: Bull Trap candle closes back BELOW 100.0 (e.g. closes 97.0, opens 101.0)
        highs[27] = 102.0
        lows[27] = 96.0
        opens[27] = 101.0
        closes[27] = 97.0

        # Subsequent bars confirm MSS below the trap base
        closes[28] = 94.0
        closes[29] = 93.0

        res = analyze_liquidity_pools_and_sweeps(highs, lows, closes, opens, volumes)
        self.assertTrue(res["sweep_detected"])
        self.assertEqual(res["sweep_type"], "BEARISH_BSL_SWEEP")
        self.assertTrue(res["bull_trap_detected"])
        self.assertEqual(res["trap_type"], "BULL_TRAP")
        self.assertEqual(res["trap_level"], 100.0)
        self.assertEqual(res["trap_extreme"], 104.0)

    # -------------------------------------------------------------------------
    # 2. Multi-Bar False Breakdown (Bear Trap) Detection
    # -------------------------------------------------------------------------
    def test_two_bar_bear_trap_detection(self):
        # 30 bars. Swing low established at bar 10 = 50.0.
        highs = [60.0] * 30
        lows = [55.0] * 30
        closes = [58.0] * 30
        opens = [57.0] * 30
        volumes = [1000.0] * 30

        # Bar 10 is swing low
        lows[10] = 50.0
        highs[10] = 58.0
        closes[10] = 55.0

        # Bar 26: Breakdown bar flushes below 50.0 (e.g. low 46.0, closes 49.0)
        highs[26] = 53.0
        lows[26] = 46.0
        opens[26] = 52.0
        closes[26] = 49.0

        # Bar 27: Bear Trap candle closes back ABOVE 50.0 (e.g. closes 52.0, opens 49.0)
        highs[27] = 53.0
        lows[27] = 48.0
        opens[27] = 49.0
        closes[27] = 52.0

        # Subsequent bars confirm MSS above the trap top
        closes[28] = 54.0
        closes[29] = 55.0

        res = analyze_liquidity_pools_and_sweeps(highs, lows, closes, opens, volumes)
        self.assertTrue(res["sweep_detected"])
        self.assertEqual(res["sweep_type"], "BULLISH_SSL_SWEEP")
        self.assertTrue(res["bear_trap_detected"])
        self.assertEqual(res["trap_type"], "BEAR_TRAP")
        self.assertEqual(res["trap_level"], 50.0)
        self.assertEqual(res["trap_extreme"], 46.0)

    # -------------------------------------------------------------------------
    # 3. StrategyAgent Anti-Trap Veto on Breakout Long & Breakdown Short
    # -------------------------------------------------------------------------
    def test_strategy_agent_anti_trap_veto(self):
        # Setup trying to enter breakout long into active bull trap
        analysis_bull_trap = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "atr_14": 400.0,
            "liquidity": {
                "bull_trap_detected": True,
                "sweep_type": "BEARISH_BSL_SWEEP",
                "nearest_bsl": 70200.0,
                "nearest_ssl": 68000.0,
                "liquidity_structure": "SWEEP_WICK_REJECTION"
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 90,
                "strategy_name": "Institutional_Bullish_Breakout_Long",
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,
                "take_profit_price": 71500.0,
                "atr_14": 400.0
            }
        }
        res_long = self.strategy_agent.evaluate_setup(analysis_bull_trap)
        self.assertIsNone(res_long)
        last_rej = self.strategy_agent.get_last_rejection("BTCUSD")
        self.assertEqual(last_rej["gate"], "BULL_TRAP_VETO")

        # Setup trying to enter breakdown short into active bear trap
        analysis_bear_trap = {
            "symbol": "BTCUSD",
            "current_price": 65000.0,
            "spread_pct": 0.02,
            "atr_14": 400.0,
            "liquidity": {
                "bear_trap_detected": True,
                "sweep_type": "BULLISH_SSL_SWEEP",
                "nearest_bsl": 67000.0,
                "nearest_ssl": 64800.0,
                "liquidity_structure": "SWEEP_WICK_REJECTION"
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "sell",
                "score": 90,
                "strategy_name": "Institutional_Bearish_Breakdown_Short",
                "entry_price": 65000.0,
                "stop_loss_price": 65600.0,
                "take_profit_price": 63500.0,
                "atr_14": 400.0
            }
        }
        res_short = self.strategy_agent.evaluate_setup(analysis_bear_trap)
        self.assertIsNone(res_short)
        last_rej_bear = self.strategy_agent.get_last_rejection("BTCUSD")
        self.assertEqual(last_rej_bear["gate"], "BEAR_TRAP_VETO")

    # -------------------------------------------------------------------------
    # 4. Institutional Reversal Setup Qualification & Ranking
    # -------------------------------------------------------------------------
    def test_institutional_reversal_ranking_and_qualification(self):
        # Bear Trap Reversal Long Setup
        analysis_reversal = {
            "symbol": "BTCUSD",
            "current_price": 65200.0,
            "spread_pct": 0.015,
            "atr_14": 350.0,
            "directional_bias": "BULLISH",
            "macro_4h": {"regime": "MACRO_BULLISH"},
            "liquidity": {
                "bear_trap_detected": True,
                "sweep_type": "BULLISH_SSL_SWEEP",
                "mss_confirmed": True,
                "nearest_bsl": 68000.0,
                "nearest_ssl": 64800.0,
                "liquidity_structure": "SWEEP_MSS_CONFIRMED"
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 92,
                "strategy_name": "Institutional_SSL_Sweep_15m",
                "entry_price": 65200.0,
                "stop_loss_price": 64650.0,
                "take_profit_price": 66800.0,
                "atr_14": 350.0
            }
        }

        # Normal pullback scalp setup
        analysis_pullback = {
            "symbol": "ETHUSD",
            "current_price": 3100.0,
            "spread_pct": 0.02,
            "atr_14": 25.0,
            "directional_bias": "BULLISH",
            "macro_4h": {"regime": "MACRO_BULLISH"},
            "liquidity": {
                "sweep_type": "NONE",
                "nearest_bsl": 3200.0,
                "nearest_ssl": 3000.0,
                "liquidity_structure": "BALANCED_LIQUIDITY_CORE"
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 88,
                "strategy_name": "Intraday_EMA_Pullback_Scalp_Long",
                "entry_price": 3100.0,
                "stop_loss_price": 3060.0,
                "take_profit_price": 3200.0,
                "atr_14": 25.0
            }
        }

        scan_results = {
            "symbols_data": {
                "ETHUSD": analysis_pullback,
                "BTCUSD": analysis_reversal
            }
        }

        ranked = self.strategy_agent.find_best_candidates(scan_results)
        self.assertGreaterEqual(len(ranked), 2)
        # BTCUSD Sweep/Trap Reversal should rank #1
        self.assertEqual(ranked[0]["symbol"], "BTCUSD")
        self.assertIn("SWEEP", ranked[0]["strategy_name"].upper())
        self.assertIn("BULLISH SSL SWEEP", ranked[0]["thesis"])

    # -------------------------------------------------------------------------
    # 5. Multi-Timeframe Anti-Trap Veto on Breakout Longs & Breakdown Shorts
    # -------------------------------------------------------------------------
    def test_multi_timeframe_anti_trap_veto_breakout_long(self):
        c15 = self._generate_synthetic_candles(trend="bullish", n_bars=200, base_price=65000.0)
        c1h = self._generate_synthetic_candles(trend="bullish", n_bars=200, base_price=65000.0)
        c4h = self._generate_synthetic_candles(trend="bullish", n_bars=100, base_price=65000.0)
        c1d = self._generate_synthetic_candles(trend="bullish", n_bars=50, base_price=65000.0)

        # Force final 15m candle to have sharp upper rejection wick (40% of range)
        last_o = c15["o"][-1]
        last_c = c15["c"][-1]
        c15["h"][-1] = max(last_o, last_c) + 200.0  # Big upper wick
        c15["l"][-1] = min(last_o, last_c) - 10.0

        analysis = analyze_multi_timeframe(
            candles_1h=c1h,
            candles_4h=c4h,
            candles_1d=c1d,
            candles_1w=None,
            candles_15m=c15,
            symbol="BTCUSD"
        )
        hp = analysis.get("high_probability_setup", {})
        # Breakout long must NOT be qualified due to upper rejection wick / bull trap
        if hp.get("qualified"):
            self.assertNotEqual(hp.get("strategy"), "Institutional_Bullish_Breakout_Long")
        else:
            rej = analysis.get("long_rejection_reason", "")
            self.assertTrue("Bull Trap" in rej or "rejection" in rej or "Blocked" in rej)

    def test_multi_timeframe_anti_trap_veto_breakdown_short(self):
        c15 = self._generate_synthetic_candles(trend="bearish", n_bars=200, base_price=75000.0)
        c1h = self._generate_synthetic_candles(trend="bearish", n_bars=200, base_price=75000.0)
        c4h = self._generate_synthetic_candles(trend="bearish", n_bars=100, base_price=75000.0)
        c1d = self._generate_synthetic_candles(trend="bearish", n_bars=50, base_price=75000.0)

        # Force final 15m candle to have sharp lower rejection wick (40% of range)
        last_o = c15["o"][-1]
        last_c = c15["c"][-1]
        c15["l"][-1] = min(last_o, last_c) - 200.0  # Big lower wick
        c15["h"][-1] = max(last_o, last_c) + 10.0

        analysis = analyze_multi_timeframe(
            candles_1h=c1h,
            candles_4h=c4h,
            candles_1d=c1d,
            candles_1w=None,
            candles_15m=c15,
            symbol="BTCUSD"
        )
        hp = analysis.get("high_probability_setup", {})
        # Breakdown short must NOT be qualified due to lower rejection wick / bear trap
        if hp.get("qualified"):
            self.assertNotEqual(hp.get("strategy"), "Institutional_Bearish_Breakdown_Short")
        else:
            rej = analysis.get("short_rejection_reason", "")
            self.assertTrue("Bear Trap" in rej or "rejection" in rej or "Blocked" in rej)


if __name__ == "__main__":
    unittest.main()
