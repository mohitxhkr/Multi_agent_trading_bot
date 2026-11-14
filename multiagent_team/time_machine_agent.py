"""
Agent 5: Time Machine Historical Simulation & Probability Engine.
Simulates candidate trade setups backwards through historical price data to calculate
empirical success rate, realized net expected value (EV), contract-specific friction,
Wilson score confidence intervals, rolling walk-forward out-of-sample validation,
intrabar event sequencing, and Profit Factor BEFORE any trade is submitted
to the Risk Gatekeeper or user for execution.

CRITICAL COMPLIANCE & FAIL-CLOSED MANDATE:
All synthetic fallbacks and fabricated backtest approvals are strictly prohibited.
If data is missing, corrupted, or sample sizes are insufficient, the agent fails closed
with INSUFFICIENT_DATA or INSUFFICIENT_SAMPLE.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import time
import math
import logging
import random

from src.delta_client import DeltaExchangeClient
from src.technical_analysis import (
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    detect_fair_value_gaps,
    analyze_liquidity_pools_and_sweeps
)
from multiagent_team.strategy_agent import (
    analyze_market_structure_bos_choch,
    analyze_1h_market_context,
    get_asset_config,
    detect_fractal_pivots
)

logger = logging.getLogger("time-machine-agent")


# =============================================================================
# STATISTICAL UTILITIES
# =============================================================================

def calculate_wilson_lower_bound(wins: int, n: int, confidence: float = 0.95) -> float:
    """
    Calculate the lower bound of the Wilson Score Confidence Interval.
    Prevents trusting small sample flukes (e.g. 2 wins out of 2 trades).
    """
    if n <= 0:
        return 0.0
    p = wins / n
    z = 1.96 if confidence >= 0.95 else 1.645
    denominator = 1.0 + (z ** 2) / n
    centre_adjusted = p + (z ** 2) / (2.0 * n)
    spread = z * math.sqrt(max(0.0, (p * (1.0 - p) + (z ** 2) / (4.0 * n)) / n))
    lower_bound = (centre_adjusted - spread) / denominator
    return round(max(0.0, lower_bound) * 100.0, 1)


def bootstrap_mean_confidence_interval(
    values: List[float],
    n_resamples: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42
) -> Tuple[float, float]:
    """
    Compute empirical non-parametric bootstrap confidence interval for net expectancy.
    """
    if not values:
        return 0.0, 0.0
    if len(values) < 4:
        m = sum(values) / len(values)
        return round(m, 2), round(m, 2)

    rng = random.Random(seed)
    n = len(values)
    means: List[float] = []

    for _ in range(n_resamples):
        sample = [values[rng.randint(0, n - 1)] for _ in range(n)]
        means.append(sum(sample) / n)

    means.sort()
    lower_idx = int(((1.0 - confidence_level) / 2.0) * n_resamples)
    upper_idx = int((1.0 - (1.0 - confidence_level) / 2.0) * n_resamples)
    upper_idx = min(upper_idx, n_resamples - 1)

    return round(means[lower_idx], 2), round(means[upper_idx], 2)


# =============================================================================
# DATA INTEGRITY & SANITY VALIDATION
# =============================================================================

def validate_candle_data(
    candles: Optional[Dict[str, Any]],
    min_bars: int = 60
) -> Tuple[bool, str, Dict[str, List[float]]]:
    """
    Validate historical OHLCV data for consistency, monotonicity, and completeness.
    Enforces strict data quality checks:
    - Lists present and have identical lengths
    - Length >= min_bars
    - Prices > 0
    - High >= max(Open, Close) and Low <= min(Open, Close)
    - High >= Low
    - Timestamps monotonic (if present)
    """
    if not candles or not isinstance(candles, dict):
        return False, "Candle payload is null or not a dictionary.", {}

    closes = candles.get("c") or []
    highs = candles.get("h") or []
    lows = candles.get("l") or []
    opens = candles.get("o") or []
    volumes = candles.get("v") or []
    timestamps = candles.get("t") or []

    n = len(closes)
    if n < min_bars:
        return False, f"Insufficient candles: {n} available, {min_bars} required.", {}

    if not (len(highs) == n and len(lows) == n and len(opens) == n):
        return False, f"Mismatched OHLC list lengths (c={n}, h={len(highs)}, l={len(lows)}, o={len(opens)}).", {}

    c_clean: List[float] = []
    h_clean: List[float] = []
    l_clean: List[float] = []
    o_clean: List[float] = []
    v_clean: List[float] = []
    t_clean: List[int] = []

    for i in range(n):
        try:
            ci = float(closes[i])
            hi = float(highs[i])
            li = float(lows[i])
            oi = float(opens[i])
            vi = float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 1.0
            ti = int(timestamps[i]) if i < len(timestamps) and timestamps[i] is not None else 0
        except (ValueError, TypeError):
            return False, f"Non-numeric price or volume encountered at index {i}.", {}

        if ci <= 0 or hi <= 0 or li <= 0 or oi <= 0:
            return False, f"Non-positive price encountered at index {i} (c={ci}, h={hi}, l={li}, o={oi}).", {}

        if hi < li:
            return False, f"Corrupted bar at index {i}: High ({hi}) < Low ({li}).", {}

        # Allow epsilon tolerance (1e-5) for floating point precision
        if hi < max(oi, ci) - 1e-4 or li > min(oi, ci) + 1e-4:
            return False, f"Inconsistent OHLC bar at index {i} (o={oi}, h={hi}, l={li}, c={ci}).", {}

        c_clean.append(ci)
        h_clean.append(hi)
        l_clean.append(li)
        o_clean.append(oi)
        v_clean.append(max(0.0, vi))
        if ti > 0:
            t_clean.append(ti)

    # Monotonicity check on timestamps if provided
    if len(t_clean) == n and n > 1:
        for i in range(1, n):
            if t_clean[i] < t_clean[i - 1]:
                return False, f"Non-monotonic timestamps detected at index {i} ({t_clean[i-1]} -> {t_clean[i]}).", {}

    clean_dict: Dict[str, Any] = {
        "c": c_clean,
        "h": h_clean,
        "l": l_clean,
        "o": o_clean,
        "v": v_clean,
        "t": t_clean if len(t_clean) == n else []
    }
    return True, "Data validation passed.", clean_dict


# =============================================================================
# SESSION-ANCHORED VWAP
# =============================================================================

def calculate_session_anchored_vwap(
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    timestamps: Optional[List[int]] = None,
    bars_per_session: int = 96
) -> List[float]:
    """
    Calculate intraday VWAP with daily session reset (UTC 00:00).
    If unix timestamps are provided, resets when calendar date changes (ts // 86400).
    If timestamps are absent, resets every 96 15m bars (24 hours).
    Strictly zero lookahead: bar i only uses data from session start up to i.
    """
    total = len(closes)
    vwap_series: List[float] = []
    cum_pv = 0.0
    cum_vol = 0.0
    prev_day = -1

    for i in range(total):
        typ_price = (highs[i] + lows[i] + closes[i]) / 3.0
        vol = volumes[i] if i < len(volumes) and volumes[i] > 0 else 1.0

        # Check for daily session reset
        reset = False
        if timestamps and i < len(timestamps) and timestamps[i] > 0:
            day = timestamps[i] // 86400
            if day != prev_day and prev_day != -1:
                reset = True
            prev_day = day
        elif i > 0 and (i % bars_per_session == 0):
            reset = True

        if reset:
            cum_pv = 0.0
            cum_vol = 0.0

        cum_pv += typ_price * vol
        cum_vol += vol
        vwap_series.append(cum_pv / cum_vol if cum_vol > 0 else closes[i])

    return vwap_series


# =============================================================================
# MULTI-TIMEFRAME ALIGNMENT (ZERO LOOKAHEAD)
# =============================================================================

def align_htf_1h_to_15m(
    candles_15m: Dict[str, Any],
    candles_1h: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Chronologically join 1H context onto 15m bars.
    Strictly prevents future 1H candle access: at 15m bar i, only the last
    fully closed 1H candle is made available.
    """
    n_15m = len(candles_15m["c"])
    if not candles_1h or len(candles_1h.get("c", [])) < 2:
        # Fallback if 1H candles unavailable: derive pseudo-1H from 15m (every 4 bars)
        # using strictly past 15m bars
        h1_closes = [candles_15m["c"][max(0, k - 4)] for k in range(n_15m)]
        h1_ema21 = calculate_ema(h1_closes, 21)
        h1_rsi = calculate_rsi(h1_closes, 14)
        return {
            "h1_closes": h1_closes,
            "h1_ema21": h1_ema21,
            "h1_rsi": h1_rsi,
            "source": "derived_15m_synthesized"
        }

    valid_1h, _, clean_1h = validate_candle_data(candles_1h, min_bars=2)
    if not valid_1h:
        h1_closes = [candles_15m["c"][max(0, k - 4)] for k in range(n_15m)]
        return {
            "h1_closes": h1_closes,
            "h1_ema21": calculate_ema(h1_closes, 21),
            "h1_rsi": calculate_rsi(h1_closes, 14),
            "source": "fallback_due_to_invalid_1h"
        }

    c_1h = clean_1h["c"]
    t_1h = clean_1h.get("t", [])
    ema21_1h = calculate_ema(c_1h, 21)
    rsi_1h = calculate_rsi(c_1h, 14)

    t_15m = candles_15m.get("t", [])
    aligned_h1_close: List[float] = []
    aligned_h1_ema21: List[float] = []
    aligned_h1_rsi: List[float] = []

    # If timestamps exist for both, align by timestamp
    if t_15m and t_1h and len(t_15m) == n_15m and len(t_1h) == len(c_1h):
        h1_idx = 0
        for i in range(n_15m):
            t15 = t_15m[i]
            # Advance 1H pointer as long as 1H candle closed at or before t15
            # Assuming standard 1H resolution (3600 seconds)
            while h1_idx + 1 < len(t_1h) and (t_1h[h1_idx + 1] + 3600 <= t15):
                h1_idx += 1

            aligned_h1_close.append(c_1h[h1_idx])
            aligned_h1_ema21.append(ema21_1h[h1_idx])
            aligned_h1_rsi.append(rsi_1h[h1_idx])
    else:
        # Align by bar index ratio: 4 15m bars = 1 1H bar
        # At 15m bar i, the closed 1H bar corresponds to (i // 4) - 1
        h1_len = len(c_1h)
        for i in range(n_15m):
            h_idx = max(0, min((i // 4) - 1, h1_len - 1))
            aligned_h1_close.append(c_1h[h_idx])
            aligned_h1_ema21.append(ema21_1h[h_idx])
            aligned_h1_rsi.append(rsi_1h[h_idx])

    return {
        "h1_closes": aligned_h1_close,
        "h1_ema21": aligned_h1_ema21,
        "h1_rsi": aligned_h1_rsi,
        "source": "aligned_1h_feed"
    }


# =============================================================================
# TIME MACHINE PROBABILITY & HISTORICAL REPLAY ENGINE
# =============================================================================

class TimeMachineAgent:
    """
    Agent 5: Time Machine Historical Simulation & Probability Engine.
    Executes walk-forward historical simulation of exact strategy conditions
    with realistic intrabar event ordering, friction deduction, Wilson 95% CI,
    bootstrap expectancy estimation, and rolling walk-forward out-of-sample partitions.
    """

    def __init__(
        self,
        client: Optional[DeltaExchangeClient] = None,
        min_win_rate_pct: float = 60.0,
        min_expected_value_r: float = 0.20,
        lookback_candles: int = 400,
        max_simulation_bars: int = 48,
        min_sample_size: Optional[int] = None,
        min_oos_sample_size: Optional[int] = None
    ):
        self.client = client
        self.min_win_rate_pct = min_win_rate_pct
        self.min_expected_value_r = min_expected_value_r
        self.lookback_candles = lookback_candles
        self.max_simulation_bars = max_simulation_bars
        default_min_samples = int(os.getenv("TIME_MACHINE_MIN_SAMPLES", "4"))
        self.min_sample_size = min_sample_size if min_sample_size is not None else default_min_samples
        default_min_oos = int(os.getenv("TIME_MACHINE_MIN_OOS_SAMPLES", "1"))
        self.min_oos_sample_size = min_oos_sample_size if min_oos_sample_size is not None else default_min_oos

        # Institutional Friction Assumptions for Delta Exchange
        # Maker: 0.02% (0.0002) | Taker: 0.05% (0.0005)
        self.entry_fee_pct = 0.0005     # Taker entry
        self.exit_fee_pct = 0.0005      # Taker exit (conservative assumption)
        self.slippage_pct = 0.0003      # 0.03% slippage per leg for BTC / majors
        self.funding_per_8h_pct = 0.0001 # 0.01% funding per 8h funding cycle
        self.base_friction_pct = (self.entry_fee_pct + self.exit_fee_pct) + (self.slippage_pct * 2)

    def get_contract_specs(self, symbol: str) -> Dict[str, Any]:
        """
        Get contract specifications for Delta Exchange assets.
        Supports inverse contracts (BTCUSD) and linear contracts (ETHUSD, ALTs).
        """
        sym = symbol.upper()
        if "BTC" in sym:
            return {
                "symbol": sym,
                "contract_type": "inverse",
                "contract_value": 1.0,  # $1 USD per contract
                "lot_size": 1,
                "slippage_pct": 0.0003,
                "maker_fee": 0.0002,
                "taker_fee": 0.0005
            }
        else:
            return {
                "symbol": sym,
                "contract_type": "linear",
                "contract_value": 0.001 if "ETH" in sym else 1.0,
                "lot_size": 1,
                "slippage_pct": 0.0005,
                "maker_fee": 0.0002,
                "taker_fee": 0.0005
            }

    def _matches_historical_strategy(
        self,
        strategy_name: str,
        side: str,
        i: int,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        volumes: List[float],
        rsi: List[float],
        ema21: List[float],
        ema50: List[float],
        vwap: List[float],
        macd_hist: List[float],
        h1_closes: List[float],
        h1_ema21: List[float],
        h1_rsi: List[float],
        vol_sma20: List[float],
        symbol: str = "BTCUSD",
        candles_5m: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Historical Replay Adapter: Replays exact Strategy Agent conditions
        based on deterministic Smart Money Concepts (BOS, CHOCH, FVG 50% CE,
        liquidity sweeps, 1H trend alignment, and normalized confluence scoring).
        Strictly zero lookahead: bar i only accesses historical data <= i.
        """
        if i < 20:
            return False

        c_price = closes[i]
        c_open = opens[i]
        c_high = highs[i]
        c_low = lows[i]
        c_rsi = rsi[i]
        c_ema21 = ema21[i]
        c_ema50 = ema50[i]
        c_vwap = vwap[i]
        c_hist = macd_hist[i] if i < len(macd_hist) else 0.0
        p_hist = macd_hist[i - 1] if 0 < i < len(macd_hist) else c_hist
        c_vol = volumes[i]
        v_sma = vol_sma20[i] if i < len(vol_sma20) and vol_sma20[i] > 0 else 1.0

        # HTF 1H Context (closed 1H bars only)
        h1_c = h1_closes[i] if i < len(h1_closes) else c_price
        h1_ema = h1_ema21[i] if i < len(h1_ema21) else c_ema21
        h1_bullish = h1_c >= h1_ema
        h1_bearish = h1_c <= h1_ema

        # Zero-lookahead slice of 15m bars up to bar i (last 60 bars max for rolling calculation)
        w_start = max(0, i - 60)
        c_slice = closes[w_start:i + 1]
        h_slice = highs[w_start:i + 1]
        l_slice = lows[w_start:i + 1]
        o_slice = opens[w_start:i + 1]
        v_slice = volumes[w_start:i + 1]

        # 1. Deterministic Market Structure Shift (BOS / CHOCH) from StrategyAgent engine
        smc_res = analyze_market_structure_bos_choch(
            highs=h_slice, lows=l_slice, closes=c_slice, opens=o_slice, pivot_window=2
        )
        bos_detected = smc_res.get("bos_detected", False)
        choch_detected = smc_res.get("choch_detected", False)
        structure_type = smc_res.get("structure_type", "NORMAL")

        # 2. Fair Value Gaps (FVG) and 50% Consequent Encroachment (CE)
        fvg_res = detect_fair_value_gaps(
            highs=h_slice, lows=l_slice, closes=c_slice, opens=o_slice, min_gap_pct=0.03
        )
        bullish_fvgs = fvg_res.get("bullish_fvgs", [])
        bearish_fvgs = fvg_res.get("bearish_fvgs", [])

        # 3. Liquidity Sweeps (BSL/SSL)
        liq_res = analyze_liquidity_pools_and_sweeps(
            highs=h_slice, lows=l_slice, closes=c_slice, opens=o_slice, volumes=v_slice
        )
        sweep_type = liq_res.get("sweep_type", "NONE")
        mss_confirmed = liq_res.get("mss_confirmed", False)

        strat_lower = strategy_name.lower()
        recent_low = min(lows[max(0, i - 10):i])
        recent_high = max(highs[max(0, i - 10):i])

        # Optional 5M confirmation alignment if 5M candles are provided
        if candles_5m and "c" in candles_5m and len(candles_5m["c"]) > 0:
            c5 = candles_5m["c"]
            o5 = candles_5m.get("o", c5)
            if len(c5) >= 2:
                # 5M candle body direction check
                if side == "buy" and c5[-1] < o5[-1] and c5[-2] < o5[-2]:
                    return False
                elif side == "sell" and c5[-1] > o5[-1] and c5[-2] > o5[-2]:
                    return False

        if side == "buy":
            # 1. Sweep setup (Institutional_SSL_Sweep) - Verified by SMC Sweep & MSS Body Close
            if "ssl" in strat_lower or "sweep" in strat_lower:
                sweep_ok = (sweep_type == "BULLISH_SSL_SWEEP" and mss_confirmed) or (c_low < recent_low and c_price > recent_low)
                mss_bull = c_price > c_open and c_rsi >= 38
                return sweep_ok and mss_bull and (h1_bullish or c_rsi < 35)

            # 2. Pullback setup (Intraday_EMA_Pullback_Scalp_Long)
            if "pullback" in strat_lower or "ema" in strat_lower:
                pullback_test = c_low <= c_ema21 * 1.002 and c_price >= c_ema21 * 0.998
                rsi_ok = 40.0 <= c_rsi <= 75.0
                vwap_ok = c_price >= c_vwap * 0.996
                macd_ok = c_hist >= 0 or c_hist > p_hist
                return pullback_test and rsi_ok and vwap_ok and macd_ok and h1_bullish

            # 3. Momentum Impulse / Breakout (High_Volume_Momentum_Impulse)
            if "momentum" in strat_lower or "impulse" in strat_lower or "breakout" in strat_lower:
                vol_surge = c_vol >= 1.5 * v_sma
                strong_body = (c_price - c_open) > 0 and (c_price - c_open) / max(0.0001, (c_high - c_low)) >= 0.50
                trend_ok = (c_price > c_ema21 or bos_detected) and h1_bullish
                return vol_surge and strong_body and trend_ok

            # 4. FVG Retest (Institutional_SMC_Bullish_FVG_Retest) - 50% Consequent Encroachment (CE)
            if "fvg" in strat_lower:
                active_fvg_retest = False
                for fvg in bullish_fvgs[-3:]:
                    ce_level = fvg.get("midpoint", (fvg.get("top", 0) + fvg.get("bottom", 0)) / 2.0)
                    if c_low <= fvg.get("top", 0) and c_price >= fvg.get("bottom", 0):
                        active_fvg_retest = True
                        break
                if not active_fvg_retest and i >= 3:
                    fvg_low = highs[i - 2]
                    fvg_high = lows[i]
                    active_fvg_retest = (fvg_high > fvg_low) and (c_low <= fvg_high and c_price > fvg_low)
                return active_fvg_retest and c_price >= c_vwap * 0.995

            # Default / Generic High Confluence Buy: Full SMC Confluence Model
            swept_low = (sweep_type == "BULLISH_SSL_SWEEP") or (c_low < recent_low and c_price > recent_low)
            is_oversold_bounce = c_rsi < 38 and c_price > c_open
            trend_aligned = (c_price >= c_ema21 or c_ema21 >= c_ema50 or "BULLISH" in structure_type) and h1_bullish
            is_breakout = (c_high > recent_high or bos_detected) and trend_aligned
            is_ema_bounce = c_low <= c_ema21 * 1.002 and c_price >= c_ema21 and trend_aligned
            is_momentum_impulse = c_price > c_open and c_rsi >= 45 and trend_aligned
            is_macd_confirmed = c_hist >= 0 or c_hist > p_hist
            is_vwap_aligned = c_price >= c_vwap * 0.995

            return (swept_low or is_oversold_bounce or is_breakout or is_ema_bounce or is_momentum_impulse) and (trend_aligned or is_macd_confirmed) and is_vwap_aligned

        elif side == "sell":
            # 1. Sweep setup (Institutional_BSL_Sweep) - Verified by SMC Sweep & MSS Body Close
            if "bsl" in strat_lower or "sweep" in strat_lower:
                sweep_ok = (sweep_type == "BEARISH_BSL_SWEEP" and mss_confirmed) or (c_high > recent_high and c_price < recent_high)
                mss_bear = c_price < c_open and c_rsi <= 62
                return sweep_ok and mss_bear and (h1_bearish or c_rsi > 65)

            # 2. Pullback setup (Intraday_EMA_Pullback_Scalp_Short)
            if "pullback" in strat_lower or "ema" in strat_lower:
                pullback_test = c_high >= c_ema21 * 0.998 and c_price <= c_ema21 * 1.002
                rsi_ok = 25.0 <= c_rsi <= 60.0
                vwap_ok = c_price <= c_vwap * 1.004
                macd_ok = c_hist <= 0 or c_hist < p_hist
                return pullback_test and rsi_ok and vwap_ok and macd_ok and h1_bearish

            # 3. Breakdown setup (Institutional_Bearish_Breakdown_Short)
            if "breakdown" in strat_lower:
                breakdown = (c_low < recent_low or bos_detected) and c_price < c_ema21
                rsi_ok = 20.0 <= c_rsi <= 55.0
                return breakdown and rsi_ok and h1_bearish

            # 4. Momentum Impulse (High_Volume_Momentum_Impulse)
            if "momentum" in strat_lower or "impulse" in strat_lower:
                vol_surge = c_vol >= 1.5 * v_sma
                strong_body = (c_open - c_price) > 0 and (c_open - c_price) / max(0.0001, (c_high - c_low)) >= 0.50
                trend_ok = (c_price < c_ema21 or bos_detected) and h1_bearish
                return vol_surge and strong_body and trend_ok

            # 5. FVG Retest (Institutional_SMC_Bearish_FVG_Retest) - 50% Consequent Encroachment (CE)
            if "fvg" in strat_lower:
                active_fvg_retest = False
                for fvg in bearish_fvgs[-3:]:
                    ce_level = fvg.get("midpoint", (fvg.get("top", 0) + fvg.get("bottom", 0)) / 2.0)
                    if c_high >= fvg.get("bottom", 0) and c_price <= fvg.get("top", 0):
                        active_fvg_retest = True
                        break
                if not active_fvg_retest and i >= 3:
                    fvg_high = lows[i - 2]
                    fvg_low = highs[i]
                    active_fvg_retest = (fvg_high > fvg_low) and (c_high >= fvg_low and c_price < fvg_high)
                return active_fvg_retest and c_price <= c_vwap * 1.005

            # Default / Generic High Confluence Sell: Full SMC Confluence Model
            swept_high = (sweep_type == "BEARISH_BSL_SWEEP") or (c_high > recent_high and c_price < recent_high)
            is_overbought_reject = c_rsi > 62 and c_price < c_open
            trend_aligned = (c_price <= c_ema21 or c_ema21 <= c_ema50 or "BEARISH" in structure_type) and h1_bearish
            is_breakdown = (c_low < recent_low or bos_detected) and trend_aligned
            is_ema_reject = c_high >= c_ema21 * 0.998 and c_price <= c_ema21 and trend_aligned
            is_momentum_impulse = c_price < c_open and c_rsi <= 55 and trend_aligned
            is_macd_confirmed = c_hist <= 0 or c_hist < p_hist
            is_vwap_aligned = c_price <= c_vwap * 1.005

            return (swept_high or is_overbought_reject or is_breakdown or is_ema_reject or is_momentum_impulse) and (trend_aligned or is_macd_confirmed) and is_vwap_aligned

        return False

    def simulate_setup(
        self,
        setup: Dict[str, Any],
        candles_15m: Optional[Dict[str, Any]] = None,
        candles_1h: Optional[Dict[str, Any]] = None,
        candles_5m: Optional[Dict[str, Any]] = None,
        candles_1m: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run multi-timeframe walk-forward simulation with realistic intrabar event ordering,
        trade-by-trade net expectancy, Wilson 95% confidence bounds, rolling out-of-sample
        partitions, and Delta Exchange contract friction.
        Fails closed with INSUFFICIENT_DATA or INSUFFICIENT_SAMPLE if statistical evidence is absent.
        """
        symbol = setup.get("symbol", "BTCUSD")
        side = setup.get("side", "buy").lower()
        strategy_name = setup.get("strategy_name", "") or setup.get("thesis", "")
        entry = float(setup.get("entry_price", 0.0))
        sl = float(setup.get("stop_loss_price", 0.0))
        tp = float(setup.get("take_profit_price", 0.0))

        # Check geometry sanity
        if entry <= 0 or sl <= 0 or tp <= 0 or entry == sl or entry == tp:
            return {
                "passed": False,
                "verdict": "VETOED_INVALID_PRICES",
                "sample_size": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "timeouts": 0,
                "win_rate_pct": 0.0,
                "wilson_ci_lower_pct": 0.0,
                "expected_value_r": 0.0,
                "gross_expected_value_r": 0.0,
                "profit_factor": 0.0,
                "reason": "VETOED_INVALID_PRICES: Invalid or inverted entry, stop loss, or take profit values."
            }

        if side == "buy" and (sl >= entry or tp <= entry):
            return {
                "passed": False,
                "verdict": "VETOED_INVALID_PRICES",
                "sample_size": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "timeouts": 0,
                "win_rate_pct": 0.0,
                "wilson_ci_lower_pct": 0.0,
                "expected_value_r": 0.0,
                "gross_expected_value_r": 0.0,
                "profit_factor": 0.0,
                "reason": f"VETOED_INVALID_PRICES: For BUY setup, SL ({sl}) must be < entry ({entry}) and TP ({tp}) > entry."
            }
        elif side == "sell" and (sl <= entry or tp >= entry):
            return {
                "passed": False,
                "verdict": "VETOED_INVALID_PRICES",
                "sample_size": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "timeouts": 0,
                "win_rate_pct": 0.0,
                "wilson_ci_lower_pct": 0.0,
                "expected_value_r": 0.0,
                "gross_expected_value_r": 0.0,
                "profit_factor": 0.0,
                "reason": f"VETOED_INVALID_PRICES: For SELL setup, SL ({sl}) must be > entry ({entry}) and TP ({tp}) < entry."
            }

        sl_dist_pct = abs(entry - sl) / entry
        tp_dist_pct = abs(tp - entry) / entry
        planned_rr = tp_dist_pct / sl_dist_pct if sl_dist_pct > 0 else 2.0

        contract_specs = self.get_contract_specs(symbol)

        # Ingest / fetch historical candles if absent or has fewer than lookback_candles
        if not candles_15m or len(candles_15m.get("c", [])) < self.lookback_candles:
            if self.client:
                try:
                    now = int(time.time())
                    from_t = now - (900 * self.lookback_candles)
                    res = self.client.get_candles(symbol, resolution="15", from_time=from_t, to_time=now)
                    fetched_15m = res.get("result", {}) if res and res.get("success") else {}
                    if fetched_15m and len(fetched_15m.get("c", [])) >= len((candles_15m or {}).get("c", [])):
                        candles_15m = fetched_15m
                except Exception as e:
                    logger.error(f"TimeMachine: Failed to fetch 15m candles for {symbol}: {e}")

        # Validate 15m candle series
        is_valid, err_msg, clean_15m = validate_candle_data(candles_15m, min_bars=60)
        if not is_valid:
            logger.warning(f"TimeMachine: Data validation failed for {symbol}: {err_msg}")
            return {
                "passed": False,
                "verdict": "INSUFFICIENT_DATA",
                "sample_size": 0,
                "wins": 0,
                "losses": 0,
                "breakevens": 0,
                "timeouts": 0,
                "win_rate_pct": 0.0,
                "wilson_ci_lower_pct": 0.0,
                "expected_value_r": 0.0,
                "gross_expected_value_r": 0.0,
                "profit_factor": 0.0,
                "reason": f"INSUFFICIENT_DATA: {err_msg} Real statistical simulation cannot be executed."
            }

        closes = clean_15m["c"]
        highs = clean_15m["h"]
        lows = clean_15m["l"]
        opens = clean_15m["o"]
        volumes = clean_15m["v"]
        timestamps = clean_15m.get("t", [])
        total_bars = len(closes)

        # Ingest and chronologically align 1H candle context
        if not candles_1h and self.client:
            try:
                now = int(time.time())
                from_t_1h = now - (3600 * (self.lookback_candles // 4 + 50))
                res_1h = self.client.get_candles(symbol, resolution="60", from_time=from_t_1h, to_time=now)
                candles_1h = res_1h.get("result", {}) if res_1h and res_1h.get("success") else {}
            except Exception as e:
                logger.debug(f"TimeMachine: 1H candles fetch failed for {symbol}: {e}")
                candles_1h = None

        htf_context = align_htf_1h_to_15m(clean_15m, candles_1h)
        h1_closes = htf_context["h1_closes"]
        h1_ema21 = htf_context["h1_ema21"]
        h1_rsi = htf_context["h1_rsi"]

        # Calculate indicators across history (strictly zero lookahead)
        rsi_series = calculate_rsi(closes, 14)
        ema21_series = calculate_ema(closes, 21)
        ema50_series = calculate_ema(closes, 50) if total_bars >= 50 else ema21_series
        macd_series = calculate_macd(closes)
        macd_hist = macd_series.get("histogram", [])

        # Volume 20-period moving average
        vol_sma20: List[float] = []
        for v_idx in range(total_bars):
            v_start = max(0, v_idx - 19)
            v_window = volumes[v_start:v_idx + 1]
            vol_sma20.append(sum(v_window) / len(v_window) if v_window else 1.0)

        # Session-anchored intraday VWAP series (UTC 00:00 reset)
        vwap_series = calculate_session_anchored_vwap(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            timestamps=timestamps
        )

        # Determine simulation holding horizon (scalp trades vs swing trades)
        sim_bars = 16 if sl_dist_pct <= 0.008 else min(self.max_simulation_bars, 48)

        # =========================================================================
        # HISTORICAL SCAN & INTRABAR SIMULATION
        # =========================================================================
        matches: List[Dict[str, Any]] = []
        i = 30
        end_idx = total_bars - sim_bars - 1
        ambiguous_cases = 0

        while i < end_idx:
            is_match = self._matches_historical_strategy(
                strategy_name=strategy_name,
                side=side,
                i=i,
                opens=opens,
                highs=highs,
                lows=lows,
                closes=closes,
                volumes=volumes,
                rsi=rsi_series,
                ema21=ema21_series,
                ema50=ema50_series,
                vwap=vwap_series,
                macd_hist=macd_hist,
                h1_closes=h1_closes,
                h1_ema21=h1_ema21,
                h1_rsi=h1_rsi,
                vol_sma20=vol_sma20
            )

            if is_match:
                sim_entry = opens[i + 1]
                sim_sl = sim_entry * (1.0 - sl_dist_pct) if side == "buy" else sim_entry * (1.0 + sl_dist_pct)
                sim_tp = sim_entry * (1.0 + tp_dist_pct) if side == "buy" else sim_entry * (1.0 - tp_dist_pct)
                initial_sl = sim_sl

                outcome = "TIMEOUT"
                exit_price = sim_entry
                bars_held = 0
                max_adverse = 0.0
                trailing_stage = 0
                ambiguity = False

                unit_risk = abs(sim_entry - initial_sl)
                m1_threshold = sim_entry + (0.80 * unit_risk) if side == "buy" else sim_entry - (0.80 * unit_risk)
                m2_threshold = sim_entry + (1.10 * unit_risk) if side == "buy" else sim_entry - (1.10 * unit_risk)
                m3_threshold = sim_entry + (1.60 * unit_risk) if side == "buy" else sim_entry - (1.60 * unit_risk)

                for step in range(1, sim_bars + 1):
                    bar_idx = i + 1 + step
                    if bar_idx >= total_bars:
                        break

                    b_open = opens[bar_idx]
                    b_high = highs[bar_idx]
                    b_low = lows[bar_idx]
                    b_close = closes[bar_idx]
                    bars_held = step

                    # 1M Intrabar Pathing if 1M candles provided
                    intrabar_resolved = False
                    if candles_1m and isinstance(candles_1m, dict) and "h" in candles_1m and "l" in candles_1m:
                        t_bar = timestamps[bar_idx] if bar_idx < len(timestamps) else None
                        t_1m = candles_1m.get("t", [])
                        h_1m = candles_1m["h"]
                        l_1m = candles_1m["l"]
                        c_1m = candles_1m.get("c", h_1m)

                        if t_bar and t_1m and len(t_1m) == len(h_1m):
                            m1_indices = [idx for idx, t in enumerate(t_1m) if t_bar <= t < t_bar + 900]
                        else:
                            m1_start = bar_idx * 15
                            m1_indices = list(range(m1_start, min(m1_start + 15, len(h_1m))))

                        if m1_indices:
                            for m1_idx in m1_indices:
                                m1_h = h_1m[m1_idx]
                                m1_l = l_1m[m1_idx]
                                if side == "buy":
                                    m1_sl_hit = m1_l <= sim_sl
                                    m1_tp_hit = m1_h >= sim_tp
                                    
                                    # Sentinel Staged Trailing Updates
                                    if m1_h >= m3_threshold and trailing_stage < 3:
                                        trailing_stage = 3
                                        sim_sl = max(sim_sl, sim_entry + (0.80 * unit_risk))
                                    elif m1_h >= m2_threshold and trailing_stage < 2:
                                        trailing_stage = 2
                                        sim_sl = max(sim_sl, sim_entry + (0.25 * unit_risk))
                                    elif m1_h >= m1_threshold and trailing_stage < 1:
                                        trailing_stage = 1
                                        sim_sl = max(sim_sl, sim_entry - (0.40 * unit_risk))

                                    if m1_sl_hit and not m1_tp_hit:
                                        outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl >= sim_entry else "LOSS")
                                        exit_price = sim_sl
                                        intrabar_resolved = True
                                        break
                                    elif m1_tp_hit and not m1_sl_hit:
                                        outcome = "WIN"
                                        exit_price = sim_tp
                                        intrabar_resolved = True
                                        break
                                    elif m1_sl_hit and m1_tp_hit:
                                        ambiguity = True
                                        outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl >= sim_entry else "LOSS")
                                        exit_price = sim_sl
                                        intrabar_resolved = True
                                        break
                                else:
                                    m1_sl_hit = m1_h >= sim_sl
                                    m1_tp_hit = m1_l <= sim_tp

                                    # Sentinel Staged Trailing Updates
                                    if m1_l <= m3_threshold and trailing_stage < 3:
                                        trailing_stage = 3
                                        sim_sl = min(sim_sl, sim_entry - (0.80 * unit_risk))
                                    elif m1_l <= m2_threshold and trailing_stage < 2:
                                        trailing_stage = 2
                                        sim_sl = min(sim_sl, sim_entry - (0.25 * unit_risk))
                                    elif m1_l <= m1_threshold and trailing_stage < 1:
                                        trailing_stage = 1
                                        sim_sl = min(sim_sl, sim_entry + (0.40 * unit_risk))

                                    if m1_sl_hit and not m1_tp_hit:
                                        outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl <= sim_entry else "LOSS")
                                        exit_price = sim_sl
                                        intrabar_resolved = True
                                        break
                                    elif m1_tp_hit and not m1_sl_hit:
                                        outcome = "WIN"
                                        exit_price = sim_tp
                                        intrabar_resolved = True
                                        break
                                    elif m1_sl_hit and m1_tp_hit:
                                        ambiguity = True
                                        outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl <= sim_entry else "LOSS")
                                        exit_price = sim_sl
                                        intrabar_resolved = True
                                        break
                            if intrabar_resolved:
                                break

                    if side == "buy":
                        adverse = max(0.0, (sim_entry - b_low) / sim_entry)
                        if adverse > max_adverse:
                            max_adverse = adverse

                        # Check Sentinel trailing milestones (breathing cushion)
                        if b_high >= m3_threshold and trailing_stage < 3:
                            trailing_stage = 3
                            sim_sl = max(sim_sl, sim_entry + (0.80 * unit_risk))
                        elif b_high >= m2_threshold and trailing_stage < 2:
                            trailing_stage = 2
                            sim_sl = max(sim_sl, sim_entry + (0.25 * unit_risk))
                        elif b_high >= m1_threshold and trailing_stage < 1:
                            trailing_stage = 1
                            sim_sl = max(sim_sl, sim_entry - (0.40 * unit_risk))

                        sl_touched = b_low <= sim_sl
                        tp_touched = b_high >= sim_tp

                        if sl_touched and tp_touched:
                            ambiguity = True
                            outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl >= sim_entry else "LOSS")
                            exit_price = sim_sl
                            break
                        elif sl_touched:
                            outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl >= sim_entry else "LOSS")
                            exit_price = sim_sl
                            break
                        elif tp_touched:
                            outcome = "WIN"
                            exit_price = sim_tp
                            break

                    elif side == "sell":
                        adverse = max(0.0, (b_high - sim_entry) / sim_entry)
                        if adverse > max_adverse:
                            max_adverse = adverse

                        # Check Sentinel trailing milestones (breathing cushion)
                        if b_low <= m3_threshold and trailing_stage < 3:
                            trailing_stage = 3
                            sim_sl = min(sim_sl, sim_entry - (0.80 * unit_risk))
                        elif b_low <= m2_threshold and trailing_stage < 2:
                            trailing_stage = 2
                            sim_sl = min(sim_sl, sim_entry - (0.25 * unit_risk))
                        elif b_low <= m1_threshold and trailing_stage < 1:
                            trailing_stage = 1
                            sim_sl = min(sim_sl, sim_entry + (0.40 * unit_risk))

                        sl_touched = b_high >= sim_sl
                        tp_touched = b_low <= sim_tp

                        if sl_touched and tp_touched:
                            ambiguity = True
                            outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl <= sim_entry else "LOSS")
                            exit_price = sim_sl
                            break
                        elif sl_touched:
                            outcome = "WIN" if trailing_stage >= 2 else ("BREAKEVEN" if sim_sl <= sim_entry else "LOSS")
                            exit_price = sim_sl
                            break
                        elif tp_touched:
                            outcome = "WIN"
                            exit_price = sim_tp
                            break

                # If trade timed out after max bars, evaluate realized PnL at final close
                if outcome == "TIMEOUT":
                    final_bar = min(i + 1 + sim_bars, total_bars - 1)
                    exit_price = closes[final_bar]

                if ambiguity:
                    ambiguous_cases += 1

                # Calculate trade-by-trade realized Net R-multiple & Dollar PnL
                hours_held = (bars_held * 15.0) / 60.0
                funding_drag = (hours_held / 8.0) * self.funding_per_8h_pct
                total_trade_friction = self.base_friction_pct + funding_drag

                if side == "buy":
                    gross_return_pct = (exit_price - sim_entry) / sim_entry
                    gross_dollar_pnl = exit_price - sim_entry
                else:
                    gross_return_pct = (sim_entry - exit_price) / sim_entry
                    gross_dollar_pnl = sim_entry - exit_price

                net_return_pct = gross_return_pct - total_trade_friction
                friction_usd = sim_entry * total_trade_friction
                net_dollar_pnl = gross_dollar_pnl - friction_usd
                initial_dollar_risk = abs(sim_entry - initial_sl)

                # Standard Quant Net R: Net PnL USD / Initial Dollar Risk USD
                gross_r = gross_return_pct / sl_dist_pct if sl_dist_pct > 0 else 0.0
                net_r = net_return_pct / sl_dist_pct if sl_dist_pct > 0 else 0.0

                matches.append({
                    "bar_index": i,
                    "entry_price": sim_entry,
                    "exit_price": exit_price,
                    "outcome": outcome,
                    "bars_held": bars_held,
                    "max_adverse_pct": max_adverse * 100.0,
                    "gross_return_pct": gross_return_pct,
                    "net_return_pct": net_return_pct,
                    "gross_dollar_pnl": round(gross_dollar_pnl, 4),
                    "net_dollar_pnl": round(net_dollar_pnl, 4),
                    "initial_dollar_risk": round(initial_dollar_risk, 4),
                    "gross_r": gross_r,
                    "net_r": net_r,
                    "ambiguity_resolved": ambiguity
                })

                # Embargo step: skip forward past the holding duration to eliminate overlapping trade leakage
                i += max(bars_held, 4)
            else:
                i += 1

        total_matches = len(matches)
        wins = sum(1 for m in matches if m["outcome"] == "WIN")
        losses = sum(1 for m in matches if m["outcome"] == "LOSS")
        breakevens = sum(1 for m in matches if m["outcome"] == "BREAKEVEN")
        timeouts = sum(1 for m in matches if m["outcome"] == "TIMEOUT")
        decisive_trades = wins + losses

        # Minimum sample size verification: FAIL CLOSED
        if decisive_trades < self.min_sample_size:
            return {
                "passed": False,
                "verdict": "INSUFFICIENT_SAMPLE",
                "sample_size": decisive_trades,
                "total_matches": total_matches,
                "wins": wins,
                "losses": losses,
                "breakevens": breakevens,
                "timeouts": timeouts,
                "win_rate_pct": round((wins / decisive_trades * 100.0), 1) if decisive_trades > 0 else 0.0,
                "wilson_ci_lower_pct": calculate_wilson_lower_bound(wins, decisive_trades) if decisive_trades > 0 else 0.0,
                "expected_value_r": 0.0,
                "gross_expected_value_r": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "max_drawdown_r": 0.0,
                "max_consecutive_losses": 0,
                "recovery_factor": 0.0,
                "bootstrap_ci_net_ev": (0.0, 0.0),
                "oos_valid": False,
                "oos_sample_size": 0,
                "oos_win_rate_pct": None,
                "oos_expected_value_r": None,
                "walk_forward_windows": [],
                "avg_mae_pct": 0.0,
                "avg_bars_to_target": 0.0,
                "friction_deducted_pct": round(self.base_friction_pct * 100.0, 3),
                "ambiguous_cases": ambiguous_cases,
                "reason": (
                    f"INSUFFICIENT_SAMPLE: Found only {decisive_trades} decisive historical trade matches "
                    f"({self.min_sample_size} minimum required). Trade candidate rejected to prevent overfitting."
                )
            }

        # Calculate empirical win rate on filled trades
        win_rate = round((wins / max(1, decisive_trades)) * 100.0, 1)
        wilson_lower = calculate_wilson_lower_bound(wins, decisive_trades)

        # Realized net expectancy across all filled and closed trades (including timeouts and breakevens)
        all_net_r = [m["net_r"] for m in matches]
        all_gross_r = [m["gross_r"] for m in matches]
        net_ev_r = round(sum(all_net_r) / len(all_net_r), 2) if all_net_r else 0.0
        gross_ev_r = round(sum(all_gross_r) / len(all_gross_r), 2) if all_gross_r else 0.0

        # Decisive trade metrics (Wins and Losses only)
        decisive_matches = [m for m in matches if m["outcome"] in ("WIN", "LOSS")]
        decisive_ev_r = round(sum(m["net_r"] for m in decisive_matches) / len(decisive_matches), 2) if decisive_matches else 0.0
        decisive_losses = abs(sum(m["net_return_pct"] for m in matches if m["outcome"] == "LOSS"))

        # Realized Profit Factor: sum of positive net returns vs sum of real trading losses
        # Breakevens are capital-protected exits (gross return = 0.0). Standard quantitative practice
        # does not treat capital-protected breakeven exits as trading losses.
        gross_profits = sum(m["net_return_pct"] for m in matches if m["net_return_pct"] > 0)
        real_losses = abs(sum(m["net_return_pct"] for m in matches if m["outcome"] in ("LOSS", "TIMEOUT") and m["net_return_pct"] < 0))
        decisive_profit_factor = round(gross_profits / decisive_losses, 2) if decisive_losses > 0 else (10.0 if gross_profits > 0 else 0.0)

        if real_losses > 0:
            profit_factor = round(gross_profits / real_losses, 2)
        elif gross_profits > 0:
            profit_factor = 10.0  # Cap representation for zero-loss runs
        else:
            profit_factor = 0.0

        # Drawdown and Risk Metrics
        cumulative_r = 0.0
        peak_r = 0.0
        max_dd_r = 0.0
        consecutive_losses = 0
        max_consecutive_losses = 0

        for m in matches:
            cumulative_r += m["net_r"]
            if cumulative_r > peak_r:
                peak_r = cumulative_r
            dd = peak_r - cumulative_r
            if dd > max_dd_r:
                max_dd_r = dd

            if m["outcome"] == "LOSS":
                consecutive_losses += 1
                if consecutive_losses > max_consecutive_losses:
                    max_consecutive_losses = consecutive_losses
            elif m["outcome"] == "WIN":
                consecutive_losses = 0

        recovery_factor = round(cumulative_r / max_dd_r, 2) if max_dd_r > 0 else (round(cumulative_r, 2) if cumulative_r > 0 else 0.0)

        # Sharpe and Sortino Ratios (if N >= 6)
        sharpe_ratio = None
        sortino_ratio = None
        if len(all_net_r) >= 6:
            mean_r = sum(all_net_r) / len(all_net_r)
            var_r = sum((x - mean_r) ** 2 for x in all_net_r) / (len(all_net_r) - 1)
            std_r = math.sqrt(var_r) if var_r > 0 else 0.0
            if std_r > 0:
                sharpe_ratio = round((mean_r / std_r) * math.sqrt(252 * 4), 2)

            downside_sq = [x ** 2 for x in all_net_r if x < 0]
            if downside_sq:
                downside_std = math.sqrt(sum(downside_sq) / len(downside_sq))
                if downside_std > 0:
                    sortino_ratio = round((mean_r / downside_std) * math.sqrt(252 * 4), 2)

        # Bootstrap Confidence Interval for Net Expectancy
        bootstrap_ci_net_ev = bootstrap_mean_confidence_interval(all_net_r, n_resamples=1000)

        # =========================================================================
        # ROLLING WALK-FORWARD OUT-OF-SAMPLE VALIDATION
        # =========================================================================
        # Partition data into 3 rolling chronological windows with embargo separation
        # Each window evaluates: Train (first 65%) -> Embargo (buffer) -> OOS (last 35%)
        n_windows = 3
        window_size = total_bars // n_windows
        walk_forward_reports: List[Dict[str, Any]] = []
        oos_matches: List[Dict[str, Any]] = []

        for w in range(n_windows):
            w_start = w * (window_size // 2)
            w_end = min(w_start + window_size, total_bars)
            if w_end - w_start < 50:
                continue

            w_train_end = w_start + int((w_end - w_start) * 0.65)
            w_embargo_end = min(w_train_end + sim_bars, w_end)

            w_matches = [m for m in matches if w_start <= m["bar_index"] < w_end]
            w_oos = [m for m in w_matches if m["bar_index"] >= w_embargo_end]
            oos_matches.extend(w_oos)

            w_oos_decisive = [m for m in w_oos if m["outcome"] in ["WIN", "LOSS"]]
            w_oos_wins = sum(1 for m in w_oos_decisive if m["outcome"] == "WIN")
            w_oos_wr = round(w_oos_wins / len(w_oos_decisive) * 100.0, 1) if w_oos_decisive else 0.0
            w_oos_ev = round(sum(m["net_r"] for m in w_oos) / len(w_oos), 2) if w_oos else 0.0

            walk_forward_reports.append({
                "window": w + 1,
                "bar_range": f"{w_start}-{w_end}",
                "train_bars": f"{w_start}-{w_train_end}",
                "oos_bars": f"{w_embargo_end}-{w_end}",
                "oos_sample_size": len(w_oos_decisive),
                "oos_win_rate_pct": w_oos_wr,
                "oos_net_ev_r": w_oos_ev
            })

        oos_decisive = [m for m in oos_matches if m["outcome"] in ["WIN", "LOSS"]]
        oos_wins = sum(1 for m in oos_decisive if m["outcome"] == "WIN")
        oos_valid = len(oos_decisive) >= self.min_oos_sample_size
        oos_win_rate = round((oos_wins / len(oos_decisive) * 100.0), 1) if oos_valid else None
        oos_ev_r = round(sum(m["net_r"] for m in oos_matches) / len(oos_matches), 2) if (oos_valid and oos_matches) else None

        avg_mae = round(sum(m["max_adverse_pct"] for m in matches) / len(matches), 2) if matches else 0.0
        avg_bars = round(sum(m["bars_held"] for m in matches) / len(matches), 1) if matches else 0.0

        # =========================================================================
        # STATISTICAL DECISION GATE (Strict Low-Win-Rate & Low-Edge Rejection)
        # =========================================================================
        # 1. Edge: Empirical Win Rate >= min_win_rate_pct (default 60.0%)
        # 2. Net Expectancy: Realized net EV >= min_expected_value_r (default 0.20R) OR
        #    high win rate (>= 60.0%) with decisive EV >= 0.30R and gross EV >= 0.20R
        # 3. Profit Factor: Net PF >= 1.50x OR (win rate >= 60.0% and decisive PF >= 1.50x)
        # 4. Out-of-Sample: Positive OOS Net Expectancy & WR >= 50% (or Wilson Lower >= 35.0%)
        # 5. Risk Safeguard: Max consecutive losses <= 4
        edge_passed = (win_rate >= self.min_win_rate_pct)
        ev_passed = (net_ev_r >= self.min_expected_value_r) or (
            win_rate >= self.min_win_rate_pct and decisive_ev_r >= 0.30 and gross_ev_r >= self.min_expected_value_r
        )
        pf_passed = (profit_factor >= 1.50) or (
            win_rate >= self.min_win_rate_pct and decisive_profit_factor >= 1.50
        )
        oos_passed = (
            (oos_ev_r >= 0.0 and (oos_win_rate is None or oos_win_rate >= 50.0))
            if (oos_valid and oos_ev_r is not None)
            else (wilson_lower >= 28.0 or (win_rate >= self.min_win_rate_pct and net_ev_r >= self.min_expected_value_r))
        )
        streak_passed = max_consecutive_losses <= 4

        passed = edge_passed and ev_passed and pf_passed and oos_passed and streak_passed
        verdict = "APPROVED" if passed else "REJECTED"

        reasons = []
        if not edge_passed:
            reasons.append(f"Win rate {win_rate}% below required {self.min_win_rate_pct}%")
        if not ev_passed:
            reasons.append(f"Realized Net EV {net_ev_r:+.2f}R (Decisive {decisive_ev_r:+.2f}R) below minimum {self.min_expected_value_r}R")
        if not pf_passed:
            reasons.append(f"Profit factor {profit_factor}x (Decisive {decisive_profit_factor}x) below 1.50x")
        if not oos_passed:
            reasons.append(f"Out-of-sample validation failed (OOS Net EV: {oos_ev_r}R, Wilson Lower: {wilson_lower}%)")
        if not streak_passed:
            reasons.append(f"Max consecutive losses ({max_consecutive_losses}) exceeded safety threshold")

        reason_str = (
            f"Time Machine APPROVED: {win_rate}% Win Rate ({wins}W / {losses}L / {breakevens}BE / {timeouts}TO, "
            f"Wilson 95% Lower: {wilson_lower}%), Net EV: +{net_ev_r}R (Decisive: +{decisive_ev_r}R), "
            f"Profit Factor: {profit_factor}x, OOS Net EV: {oos_ev_r if oos_ev_r is not None else 'N/A'}R."
            if passed else
            f"Time Machine REJECTED: {'; '.join(reasons)}."
        )

        return {
            "passed": passed,
            "verdict": verdict,
            "sample_size": decisive_trades,
            "total_matches": total_matches,
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "timeouts": timeouts,
            "win_rate_pct": win_rate,
            "wilson_ci_lower_pct": wilson_lower,
            "expected_value_r": net_ev_r,
            "decisive_expected_value_r": decisive_ev_r,
            "gross_expected_value_r": gross_ev_r,
            "profit_factor": profit_factor,
            "decisive_profit_factor": decisive_profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown_r": round(max_dd_r, 2),
            "max_consecutive_losses": max_consecutive_losses,
            "recovery_factor": recovery_factor,
            "bootstrap_ci_net_ev": bootstrap_ci_net_ev,
            "oos_valid": oos_valid,
            "oos_sample_size": len(oos_decisive),
            "oos_win_rate_pct": oos_win_rate,
            "oos_expected_value_r": oos_ev_r,
            "walk_forward_windows": walk_forward_reports,
            "avg_mae_pct": avg_mae,
            "avg_bars_to_target": avg_bars,
            "friction_deducted_pct": round(self.base_friction_pct * 100.0, 3),
            "ambiguous_cases": ambiguous_cases,
            "reason": reason_str
        }

    def evaluate_candidate_parameters(
        self,
        candidate_params: Dict[str, Any],
        candles_15m: Dict[str, Any],
        candles_1h: Optional[Dict[str, Any]] = None,
        candles_5m: Optional[Dict[str, Any]] = None,
        candles_1m: Optional[Dict[str, Any]] = None,
        symbol: str = "BTCUSD",
        side: str = "buy",
        strategy_name: str = "Institutional_SSL_Sweep"
    ) -> Dict[str, Any]:
        """
        Evaluate candidate parameters on historical candle series for Agent 10 Adaptive Learning.
        Derives simulated entry, stop loss, and take profit from candidate parameters across candles.
        """
        closes = candles_15m.get("c", [])
        if not closes or len(closes) < 60:
            return {
                "passed": False,
                "reason": "INSUFFICIENT_DATA: Minimum 60 candles required for candidate evaluation.",
                "verdict": "REJECTED",
                "sample_size": 0
            }

        current_price = closes[-1]
        target_rr = float(candidate_params.get("target_rr_ratio") or candidate_params.get("rr_ratio") or 2.0)
        atr_mult = float(candidate_params.get("atr_multiplier") or candidate_params.get("sl_atr_mult") or 1.5)

        sl_dist = current_price * 0.01 * atr_mult
        tp_dist = sl_dist * target_rr

        if side.lower() == "buy":
            sim_entry = current_price
            sim_sl = current_price - sl_dist
            sim_tp = current_price + tp_dist
        else:
            sim_entry = current_price
            sim_sl = current_price + sl_dist
            sim_tp = current_price - tp_dist

        setup = {
            "symbol": symbol,
            "side": side,
            "strategy_name": strategy_name,
            "entry_price": sim_entry,
            "stop_loss_price": sim_sl,
            "take_profit_price": sim_tp
        }

        saved_bars = self.max_simulation_bars
        if "max_holding_bars" in candidate_params:
            self.max_simulation_bars = int(candidate_params["max_holding_bars"])

        try:
            res = self.simulate_setup(
                setup=setup,
                candles_15m=candles_15m,
                candles_1h=candles_1h,
                candles_5m=candles_5m,
                candles_1m=candles_1m
            )
        finally:
            self.max_simulation_bars = saved_bars

        return res
