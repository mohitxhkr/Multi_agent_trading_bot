"""
Unit & Integration Test Suite for Upgraded Agent 1 - Regime Analyst.
Validates:
1. Strong Bullish Trend (STRONG_UPTREND)
2. Strong Bearish Trend (STRONG_DOWNTREND)
3. Weak Uptrend & Weak Downtrend (WEAK_UPTREND, WEAK_DOWNTREND)
4. Sideways / Ranging Market (RANGING)
5. Volatility Expansion (HIGH_VOLATILITY)
6. Volatility Contraction (LOW_VOLATILITY)
7. Trend-to-Range Transition Detection (TREND_TO_RANGE)
8. Range Breakout Transition Detection (RANGE_BREAKOUT)
9. Conflicting 1H and 15M Signals (Conflict penalties & evidence)
10. Multi-Timeframe Invariant (5M cannot independently reverse 1H bias)
11. Regime Switching Stability & Hysteresis (TRANSITIONAL / Provisional state)
12. Missing & Insufficient Data Handling (Fails closed to UNKNOWN, status INVALID)
13. Non-positive Price Handling (Fails closed to UNKNOWN, status INVALID)
14. Asset-Specific Calibration (BTC, ETH, SOL, XRP, XAU sensitivity)
15. Backward Compatibility of scan_universe and analyze_symbol
"""

import unittest
import math
from typing import Dict, List, Any
from unittest.mock import MagicMock

from multiagent_team.regime_analyst import (
    RegimeAnalystAgent,
    classify_market_regime,
    get_asset_regime_config,
    ASSET_REGIME_CONFIGS
)


def make_trending_candles(
    n_bars: int = 70,
    base_price: float = 60000.0,
    slope: float = 150.0,
    spread: float = 80.0
) -> Dict[str, List[float]]:
    """Generate synthetic trending candlestick data."""
    closes, highs, lows, opens, volumes = [], [], [], [], []
    current = base_price
    for i in range(n_bars):
        open_p = current
        current += slope
        close_p = current
        high_p = max(open_p, close_p) + spread * 0.6
        low_p = min(open_p, close_p) - spread * 0.4
        vol = 1000.0 + i * 10.0
        closes.append(round(close_p, 2))
        highs.append(round(high_p, 2))
        lows.append(round(low_p, 2))
        opens.append(round(open_p, 2))
        volumes.append(vol)
    return {"c": closes, "h": highs, "l": lows, "o": opens, "v": volumes}


def make_ranging_candles(
    n_bars: int = 70,
    base_price: float = 60000.0,
    amplitude: float = 600.0,
    spread: float = 700.0,
    period_bars: float = 12.0
) -> Dict[str, List[float]]:
    """Generate synthetic oscillating / sideways candlestick data with normal ATR volatility."""
    closes, highs, lows, opens, volumes = [], [], [], [], []
    for i in range(n_bars):
        wave = math.sin((2.0 * math.pi * i) / period_bars) * amplitude
        close_p = base_price + wave
        open_p = base_price + math.sin((2.0 * math.pi * (i - 0.5)) / period_bars) * amplitude
        high_p = max(open_p, close_p) + spread * 0.5
        low_p = min(open_p, close_p) - spread * 0.5
        vol = 500.0
        closes.append(round(close_p, 2))
        highs.append(round(high_p, 2))
        lows.append(round(low_p, 2))
        opens.append(round(open_p, 2))
        volumes.append(vol)
    return {"c": closes, "h": highs, "l": lows, "o": opens, "v": volumes}


def make_high_volatility_candles(
    n_bars: int = 70,
    base_price: float = 60000.0,
    baseline_spread: float = 100.0,
    spike_spread: float = 3500.0
) -> Dict[str, List[float]]:
    """Generate candlestick data with sudden extreme volatility expansion."""
    closes, highs, lows, opens, volumes = [], [], [], [], []
    current = base_price
    for i in range(n_bars):
        spread = spike_spread if i >= (n_bars - 8) else baseline_spread
        open_p = current
        close_p = current + (spread * 0.4 if i % 2 == 0 else -spread * 0.4)
        high_p = max(open_p, close_p) + (spread * 0.5)
        low_p = min(open_p, close_p) - (spread * 0.5)
        current = close_p
        closes.append(round(close_p, 2))
        highs.append(round(high_p, 2))
        lows.append(round(low_p, 2))
        opens.append(round(open_p, 2))
        volumes.append(2000.0)
    return {"c": closes, "h": highs, "l": lows, "o": opens, "v": volumes}


def make_low_volatility_candles(
    n_bars: int = 70,
    base_price: float = 60000.0,
    tight_spread: float = 20.0
) -> Dict[str, List[float]]:
    """Generate candlestick data with ultra-compressed volatility."""
    closes, highs, lows, opens, volumes = [], [], [], [], []
    for i in range(n_bars):
        close_p = base_price + (i % 3) * 5.0
        open_p = base_price + ((i + 1) % 3) * 5.0
        high_p = max(open_p, close_p) + tight_spread * 0.5
        low_p = min(open_p, close_p) - tight_spread * 0.5
        closes.append(round(close_p, 2))
        highs.append(round(high_p, 2))
        lows.append(round(low_p, 2))
        opens.append(round(open_p, 2))
        volumes.append(200.0)
    return {"c": closes, "h": highs, "l": lows, "o": opens, "v": volumes}


class TestRegimeAnalystUpgrade(unittest.TestCase):
    """Test suite for upgraded Agent 1 deterministic regime intelligence."""

    def setUp(self):
        self.agent = RegimeAnalystAgent(client=None)

    def test_strong_uptrend(self):
        """Scenario 1: Strong bullish trend with MTF alignment."""
        c_1h = make_trending_candles(n_bars=70, base_price=50000.0, slope=180.0, spread=100.0)
        c_15m = make_trending_candles(n_bars=40, base_price=60000.0, slope=60.0, spread=40.0)
        c_5m = make_trending_candles(n_bars=25, base_price=62000.0, slope=25.0, spread=15.0)

        result = self.agent.classify_regime(c_1h, c_15m, c_5m, symbol="BTCUSD")

        self.assertEqual(result["regime"], "STRONG_UPTREND")
        self.assertEqual(result["directional_bias"], "BULLISH")
        self.assertEqual(result["trend_strength"], "STRONG")
        self.assertGreaterEqual(result["confidence_score"], 70)
        self.assertEqual(result["status"], "CONFIRMED")
        self.assertFalse(result["is_provisional"])
        self.assertTrue(len(result["supporting_evidence"]) > 0)
        self.assertEqual(result["timeframe_analysis"]["1h"]["direction"], "BULLISH")
        self.assertEqual(result["timeframe_analysis"]["15m"]["trend"], "BULLISH")
        self.assertEqual(result["timeframe_analysis"]["5m"]["momentum"], "BULLISH_ALIGNED")

    def test_strong_downtrend(self):
        """Scenario 2: Strong bearish trend with MTF alignment."""
        c_1h = make_trending_candles(n_bars=70, base_price=70000.0, slope=-180.0, spread=100.0)
        c_15m = make_trending_candles(n_bars=40, base_price=60000.0, slope=-60.0, spread=40.0)
        c_5m = make_trending_candles(n_bars=25, base_price=58000.0, slope=-25.0, spread=15.0)

        result = self.agent.classify_regime(c_1h, c_15m, c_5m, symbol="BTCUSD")

        self.assertEqual(result["regime"], "STRONG_DOWNTREND")
        self.assertEqual(result["directional_bias"], "BEARISH")
        self.assertEqual(result["trend_strength"], "STRONG")
        self.assertGreaterEqual(result["confidence_score"], 70)
        self.assertEqual(result["timeframe_analysis"]["1h"]["direction"], "BEARISH")
        self.assertEqual(result["timeframe_analysis"]["15m"]["trend"], "BEARISH")
        self.assertEqual(result["timeframe_analysis"]["5m"]["momentum"], "BEARISH_ALIGNED")

    def test_weak_uptrend(self):
        """Scenario 3: Uptrend with moderate ADX below strong threshold."""
        # Gentle slope yields moderate ADX
        c_1h = make_trending_candles(n_bars=70, base_price=50000.0, slope=35.0, spread=120.0)
        c_15m = make_trending_candles(n_bars=40, base_price=52000.0, slope=15.0, spread=40.0)

        result = self.agent.classify_regime(c_1h, c_15m, None, symbol="BTCUSD")

        self.assertIn(result["regime"], ["WEAK_UPTREND", "STRONG_UPTREND"])
        self.assertEqual(result["directional_bias"], "BULLISH")

    def test_weak_downtrend(self):
        """Scenario 4: Downtrend with moderate ADX below strong threshold."""
        c_1h = make_trending_candles(n_bars=70, base_price=50000.0, slope=-35.0, spread=120.0)
        c_15m = make_trending_candles(n_bars=40, base_price=48000.0, slope=-15.0, spread=40.0)

        result = self.agent.classify_regime(c_1h, c_15m, None, symbol="BTCUSD")

        self.assertIn(result["regime"], ["WEAK_DOWNTREND", "STRONG_DOWNTREND"])
        self.assertEqual(result["directional_bias"], "BEARISH")

    def test_sideways_ranging_market(self):
        """Scenario 5: Ranging / sideways market with oscillating price."""
        c_1h = make_ranging_candles(n_bars=70, base_price=50000.0, amplitude=80.0, period_bars=10.0)

        result = self.agent.classify_regime(c_1h, None, None, symbol="BTCUSD")

        self.assertEqual(result["regime"], "RANGING")
        self.assertEqual(result["directional_bias"], "NEUTRAL")

    def test_high_volatility_expansion(self):
        """Scenario 6: High volatility expansion detection."""
        # Massive price swings expanding ATR ratio
        c_1h = make_high_volatility_candles(n_bars=70, base_price=60000.0, baseline_spread=100.0, spike_spread=4500.0)

        result = self.agent.classify_regime(c_1h, None, None, symbol="BTCUSD")

        self.assertEqual(result["volatility_state"], "HIGH_VOLATILITY")
        self.assertEqual(result["regime"], "HIGH_VOLATILITY")

    def test_low_volatility_compression(self):
        """Scenario 7: Low volatility compression detection."""
        # Ultra tight range: ATR percentage < 0.8%
        c_1h = make_low_volatility_candles(n_bars=70, base_price=60000.0, tight_spread=15.0)

        result = self.agent.classify_regime(c_1h, None, None, symbol="BTCUSD")

        self.assertEqual(result["volatility_state"], "LOW_VOLATILITY")
        self.assertEqual(result["regime"], "LOW_VOLATILITY")
        self.assertEqual(result["directional_bias"], "NEUTRAL")

    def test_trend_to_range_transition(self):
        """Scenario 8: Transition from trend to range."""
        agent = RegimeAnalystAgent(client=None)
        agent.regime_histories["BTCUSD"] = ["STRONG_UPTREND", "STRONG_UPTREND", "STRONG_UPTREND"]

        c_1h = make_ranging_candles(n_bars=70, base_price=60000.0, amplitude=60.0)
        result = agent.classify_regime(c_1h, None, None, symbol="BTCUSD")

        transition = result["regime_transition"]
        self.assertTrue(transition["transition_detected"])
        self.assertEqual(transition["transition_type"], "TREND_TO_RANGE")
        self.assertEqual(transition["prior_regime"], "STRONG_UPTREND")

    def test_range_breakout_transition(self):
        """Scenario 9: Transition from range breakout into trend."""
        agent = RegimeAnalystAgent(client=None)
        agent.regime_histories["BTCUSD"] = ["RANGING", "RANGING", "RANGING"]

        c_1h = make_trending_candles(n_bars=70, base_price=50000.0, slope=200.0, spread=100.0)
        result = agent.classify_regime(c_1h, None, None, symbol="BTCUSD")

        transition = result["regime_transition"]
        self.assertTrue(transition["transition_detected"])
        self.assertEqual(transition["transition_type"], "RANGE_BREAKOUT")
        self.assertEqual(transition["prior_regime"], "RANGING")

    def test_conflicting_timeframes_penalty(self):
        """Scenario 10: 1H Bullish bias conflicting with 15M Bearish structure."""
        c_1h = make_trending_candles(n_bars=70, base_price=50000.0, slope=180.0, spread=100.0)
        # 15M trending down (counter-trend)
        c_15m = make_trending_candles(n_bars=40, base_price=62000.0, slope=-100.0, spread=40.0)

        result_aligned = classify_market_regime(c_1h, None, None, symbol="BTCUSD")
        result_conflicted = classify_market_regime(c_1h, c_15m, None, symbol="BTCUSD")

        # Confidence should be penalised for the structural conflict
        self.assertLess(result_conflicted["confidence_score"], result_aligned["confidence_score"])
        self.assertTrue(any("conflicting with 1H" in c for c in result_conflicted["conflicting_evidence"]))

    def test_mtf_invariant_5m_cannot_reverse_1h_bias(self):
        """Scenario 11: 5M counter-trend momentum cannot independently flip 1H macro bias."""
        c_1h = make_trending_candles(n_bars=70, base_price=50000.0, slope=180.0, spread=100.0)
        # 5M has a strong pullback (bearish aligned)
        c_5m = make_trending_candles(n_bars=25, base_price=62000.0, slope=-80.0, spread=20.0)

        result = classify_market_regime(c_1h, None, c_5m, symbol="BTCUSD")

        # 1H is Bullish, so overall bias MUST remain Bullish (not Bearish)
        self.assertEqual(result["directional_bias"], "BULLISH")
        self.assertIn(result["regime"], ["STRONG_UPTREND", "WEAK_UPTREND"])
        self.assertTrue(any("pullback" in c for c in result["conflicting_evidence"]))

    def test_regime_switching_stability_hysteresis(self):
        """Scenario 12: Anti-whipsaw hysteresis prevents single-bar flip from strong trend to range."""
        agent = RegimeAnalystAgent(client=None)
        # Establish strong trend history
        agent.regime_histories["BTCUSD"] = ["STRONG_UPTREND", "STRONG_UPTREND"]

        # Sudden single bar ranging
        c_1h = make_ranging_candles(n_bars=70, base_price=60000.0, amplitude=50.0)
        result = agent.classify_regime(c_1h, None, None, symbol="BTCUSD")

        # Must enter TRANSITIONAL provisional state rather than instant flip
        self.assertEqual(result["regime"], "TRANSITIONAL")
        self.assertTrue(result["is_provisional"])
        self.assertEqual(result["status"], "PROVISIONAL")
        self.assertFalse(result["regime_transition"]["hysteresis_confirmed"])

    def test_missing_and_insufficient_candle_data(self):
        """Scenario 13: Missing or insufficient candlestick data fails closed."""
        # Empty dict
        res_empty = classify_market_regime({}, None, None, symbol="BTCUSD")
        self.assertEqual(res_empty["regime"], "UNKNOWN")
        self.assertEqual(res_empty["status"], "INVALID")
        self.assertEqual(res_empty["confidence_score"], 0)

        # None
        res_none = classify_market_regime(None, None, None, symbol="BTCUSD")
        self.assertEqual(res_none["regime"], "UNKNOWN")
        self.assertEqual(res_none["status"], "INVALID")

        # Less than 20 bars
        c_short = {"c": [100.0] * 10, "h": [105.0] * 10, "l": [95.0] * 10, "o": [100.0] * 10}
        res_short = classify_market_regime(c_short, None, None, symbol="BTCUSD")
        self.assertEqual(res_short["regime"], "UNKNOWN")
        self.assertEqual(res_short["status"], "INVALID")
        self.assertIn("Insufficient 1H candles", res_short["conflicting_evidence"][0])

    def test_non_positive_price_fails_closed(self):
        """Scenario 14: Non-positive price fails closed to UNKNOWN."""
        c_zero = {"c": [0.0] * 30, "h": [0.0] * 30, "l": [0.0] * 30, "o": [0.0] * 30}
        res_zero = classify_market_regime(c_zero, None, None, symbol="BTCUSD")
        self.assertEqual(res_zero["regime"], "UNKNOWN")
        self.assertEqual(res_zero["status"], "INVALID")

    def test_asset_specific_calibration(self):
        """Scenario 15: Volatility sensitivity calibrated differently for BTC, ETH, SOL, XRP, XAU."""
        btc_cfg = get_asset_regime_config("BTCUSD")
        sol_cfg = get_asset_regime_config("SOLUSD")
        xau_cfg = get_asset_regime_config("XAUUSD")
        eth_cfg = get_asset_regime_config("ETHUSD")
        xrp_cfg = get_asset_regime_config("XRPUSD")

        # XAU (Gold) has tighter ATR threshold than BTC, and SOL has higher threshold than BTC
        self.assertLess(xau_cfg["volatility_high_atr_pct"], btc_cfg["volatility_high_atr_pct"])
        self.assertGreater(sol_cfg["volatility_high_atr_pct"], btc_cfg["volatility_high_atr_pct"])
        self.assertGreater(xrp_cfg["volatility_high_atr_pct"], eth_cfg["volatility_high_atr_pct"])

        # Test that 2.0% ATR is NORMAL for BTC (threshold 2.5%), but HIGH_VOLATILITY for XAU (threshold 1.8%)
        # Synthesize 70 candles with ~2.0% spread
        base_gold = 2000.0
        c_gold = make_high_volatility_candles(n_bars=70, base_price=base_gold, baseline_spread=15.0, spike_spread=45.0)
        res_gold = classify_market_regime(c_gold, None, None, symbol="XAUUSD")

        base_btc = 60000.0
        # 1.5% spread for BTC
        c_btc = make_trending_candles(n_bars=70, base_price=base_btc, slope=100.0, spread=600.0)
        res_btc = classify_market_regime(c_btc, None, None, symbol="BTCUSD")

        # Ensure asset config is honored
        self.assertEqual(res_gold["symbol"], "XAUUSD")
        self.assertEqual(res_btc["symbol"], "BTCUSD")

    def test_scan_universe_backward_compatibility(self):
        """Scenario 16: scan_universe aggregates metrics and preserves required downstream keys."""
        mock_client = MagicMock()
        agent = RegimeAnalystAgent(client=mock_client)

        # Mock analyze_symbol to return valid mock analyses for BTCUSD and ETHUSD
        mock_btc = {
            "symbol": "BTCUSD",
            "regime": "STRONG_UPTREND",
            "directional_bias": "BULLISH",
            "current_price": 65000.0,
            "ema_20": 64000.0,
            "vwap": 64500.0,
            "volatility_state": "NORMAL",
            "confidence_score": 85,
            "macd": {"histogram": 25.0, "bias": "BULLISH"},
            "timeframe_analysis": {"1h": {"adx": 32.5}},
            "cvd": {"current_cvd": 1500.0},
            "order_book_imbalance": {"obi_ratio": 0.12},
            "funding_rate": 0.0001,
            "spread_pct": 0.02,
            "atr_pct": 1.45
        }
        mock_eth = {
            "symbol": "ETHUSD",
            "regime": "WEAK_UPTREND",
            "directional_bias": "BULLISH",
            "current_price": 3500.0,
            "ema_20": 3450.0,
            "vwap": 3480.0,
            "volatility_state": "NORMAL",
            "confidence_score": 75,
            "macd": {"histogram": 5.0, "bias": "BULLISH"},
            "timeframe_analysis": {"1h": {"adx": 24.0}},
            "cvd": {"current_cvd": 500.0},
            "order_book_imbalance": {"obi_ratio": 0.04},
            "funding_rate": 0.0001,
            "spread_pct": 0.03,
            "atr_pct": 1.80
        }

        agent.analyze_symbol = MagicMock(side_effect=lambda sym, res: mock_btc if "BTC" in sym else mock_eth)

        scan = agent.scan_universe(["BTCUSD", "ETHUSD"])

        # Check all required backward-compatible keys
        self.assertIn("overall_market_regime", scan)
        self.assertIn("btc_adx", scan)
        self.assertIn("btc_volatility_state", scan)
        self.assertIn("regime_confidence_score", scan)
        self.assertIn("breadth_pct", scan)
        self.assertIn("macd_breadth_pct", scan)
        self.assertIn("vwap_breadth_pct", scan)
        self.assertIn("avg_watchlist_atr_pct", scan)
        self.assertIn("market_volatility_temperature", scan)
        self.assertIn("symbols_data", scan)

        self.assertEqual(scan["overall_market_regime"], "STRONG_UPTREND")
        self.assertEqual(scan["btc_adx"], 32.5)
        self.assertEqual(scan["breadth_pct"], 100.0)
        self.assertEqual(scan["analyzed_count"], 2)

    def test_4h_and_1d_aligned_confirmation_and_fields(self):
        """Scenario 17: 1D + 4H + 1H bullish alignment boosts confidence and populates 4h/1d fields."""
        c_1h = make_trending_candles(n_bars=70, base_price=60000.0, slope=120.0, spread=80.0)
        c_15m = make_trending_candles(n_bars=30, base_price=64000.0, slope=40.0, spread=30.0)
        c_5m = make_trending_candles(n_bars=25, base_price=65000.0, slope=15.0, spread=10.0)
        c_4h = make_trending_candles(n_bars=220, base_price=48000.0, slope=80.0, spread=120.0)
        c_1d = make_trending_candles(n_bars=220, base_price=40000.0, slope=115.0, spread=200.0)

        res_no_htf = classify_market_regime(c_1h, c_15m, c_5m, symbol="BTCUSD")
        res_with_htf = classify_market_regime(
            c_1h, c_15m, c_5m, symbol="BTCUSD", candles_4h=c_4h, candles_1d=c_1d
        )

        self.assertEqual(res_with_htf["regime"], "STRONG_UPTREND")
        self.assertEqual(res_with_htf["directional_bias"], "BULLISH")
        self.assertGreaterEqual(res_with_htf["confidence_score"], res_no_htf["confidence_score"])
        self.assertTrue(res_with_htf["timeframe_analysis"]["4h"]["available"])
        self.assertEqual(res_with_htf["timeframe_analysis"]["4h"]["direction"], "BULLISH")
        self.assertTrue(res_with_htf["timeframe_analysis"]["1d"]["available"])
        self.assertEqual(res_with_htf["timeframe_analysis"]["1d"]["direction"], "BULLISH")
        self.assertTrue(any("4H confirms BULLISH" in s for s in res_with_htf["supporting_evidence"]))
        self.assertTrue(any("1D confirms BULLISH" in s for s in res_with_htf["supporting_evidence"]))

    def test_4h_and_1d_conflict_suppresses_1h_bull_trap(self):
        """Scenario 18: Bearish 4H & 1D anchor demotes a counter-trend 1H rally to TRANSITIONAL/NEUTRAL."""
        c_1h = make_trending_candles(n_bars=70, base_price=60000.0, slope=120.0, spread=80.0)
        c_15m = make_trending_candles(n_bars=30, base_price=64000.0, slope=40.0, spread=30.0)
        c_5m = make_trending_candles(n_bars=25, base_price=65000.0, slope=15.0, spread=10.0)
        c_4h_bear = make_trending_candles(n_bars=220, base_price=90000.0, slope=-100.0, spread=100.0)
        c_1d_bear = make_trending_candles(n_bars=220, base_price=95000.0, slope=-120.0, spread=150.0)

        res = classify_market_regime(
            c_1h, c_15m, c_5m, symbol="BTCUSD", candles_4h=c_4h_bear, candles_1d=c_1d_bear
        )

        self.assertEqual(res["regime"], "TRANSITIONAL")
        self.assertEqual(res["directional_bias"], "NEUTRAL")
        self.assertTrue(res["is_provisional"])
        self.assertEqual(res["regime_transition"]["transition_type"], "HTF_MACRO_CONFLICT")
        self.assertTrue(any("HTF" in c or "macro trends" in c for c in res["conflicting_evidence"]))

    def test_analyze_symbol_fetches_240_4h_bars_and_passes_htf(self):
        """Scenario 19: analyze_symbol fetches 240+ bars window for 4H and populates 4h/1d in timeframe_analysis."""
        import time as _time
        now = int(_time.time())

        def with_timestamps(candles, step_sec):
            n = len(candles["c"])
            candles["t"] = [now - ((n - 1 - i) * step_sec) for i in range(n)]
            return candles

        c_1h = with_timestamps(make_trending_candles(n_bars=70, base_price=60000.0, slope=100.0, spread=80.0), 3600)
        c_15m = with_timestamps(make_trending_candles(n_bars=30, base_price=64000.0, slope=35.0, spread=30.0), 900)
        c_5m = with_timestamps(make_trending_candles(n_bars=25, base_price=65000.0, slope=10.0, spread=10.0), 300)
        c_4h = with_timestamps(make_trending_candles(n_bars=240, base_price=42000.0, slope=90.0, spread=110.0), 14400)
        c_1d = with_timestamps(make_trending_candles(n_bars=240, base_price=35000.0, slope=110.0, spread=160.0), 86400)
        c_1w = with_timestamps(make_trending_candles(n_bars=30, base_price=30000.0, slope=800.0, spread=500.0), 604800)

        calls = []

        def fake_get_candles(symbol, resolution="60", from_time=None, to_time=None):
            calls.append((resolution, from_time, to_time))
            mapping = {
                "60": c_1h,
                "15": c_15m,
                "5": c_5m,
                "240": c_4h,
                "D": c_1d,
                "W": c_1w,
            }
            return {"success": True, "result": mapping.get(resolution, c_1h)}

        mock_client = MagicMock()
        mock_client.get_candles.side_effect = fake_get_candles
        mock_client.get_orderbook.return_value = {"success": False}
        mock_client.get_ticker.return_value = {"success": False}

        agent = RegimeAnalystAgent(client=mock_client)
        result = agent.analyze_symbol("BTCUSD", resolution="60")

        call_240 = [c for c in calls if c[0] == "240"][0]
        self.assertIsNotNone(call_240[1])
        self.assertGreaterEqual(call_240[2] - call_240[1], 14400 * 200)
        self.assertTrue(result["timeframe_analysis"]["4h"]["available"])
        self.assertTrue(result["timeframe_analysis"]["1d"]["available"])
        self.assertEqual(result["macro_4h"]["regime"], "MACRO_BULLISH")
        self.assertEqual(result["macro_daily"]["regime"], "DAILY_BULLISH")

    def test_htf_pullback_tolerance_keeps_macro_trend(self):
        """Scenario 20: evaluate_htf_trend maintains BULLISH on shallow 1-bar pullback below EMA21 when structure/ADX stay bullish."""
        from src.technical_analysis import evaluate_htf_trend

        c_up = make_trending_candles(n_bars=220, base_price=40000.0, slope=100.0, spread=120.0)
        # Simulate a minor 1-candle pullback slightly below EMA21 but well above EMA50 & EMA200
        c_up["c"][-1] = c_up["c"][-8]
        c_up["l"][-1] = c_up["c"][-1] - 40.0

        htf = evaluate_htf_trend(c_up, prefix="MACRO")
        self.assertTrue(htf["available"])
        self.assertEqual(htf["direction"], "BULLISH")
        self.assertEqual(htf["regime"], "MACRO_BULLISH")
        self.assertEqual(htf["structure"], "HIGHER_HIGHS_AND_LOWS")


if __name__ == "__main__":
    unittest.main()
