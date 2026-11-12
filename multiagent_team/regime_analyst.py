"""
Agent 1: Market Regime & Technical Analyst.
Analyzes 1H macro regime, 15M market structure, 5M entry momentum, and order flow context
with deterministic 9-regime classification, anti-whipsaw hysteresis, asset-specific calibration,
pre-flight data validation, and explainable confidence scoring.

Supported Regimes:
1. STRONG_UPTREND
2. WEAK_UPTREND
3. STRONG_DOWNTREND
4. WEAK_DOWNTREND
5. RANGING
6. HIGH_VOLATILITY
7. LOW_VOLATILITY
8. TRANSITIONAL
9. UNKNOWN
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import time

from src.delta_client import DeltaExchangeClient
from src.technical_analysis import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    calculate_adx,
    calculate_vwap,
    evaluate_htf_trend,
    analyze_multi_timeframe
)
from multiagent_team.data_validator import MarketDataValidator

logger = logging.getLogger("regime-analyst")


# =============================================================================
# ASSET-SPECIFIC REGIME CONFIGURATIONS
# =============================================================================

ASSET_REGIME_CONFIGS: Dict[str, Dict[str, Any]] = {
    "BTCUSD": {
        "symbol": "BTCUSD",
        "adx_trend_threshold": 22.0,
        "adx_strong_trend_threshold": 30.0,
        "volatility_high_atr_pct": 2.5,   # % of spot price
        "volatility_low_atr_pct": 0.8,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "ETHUSD": {
        "symbol": "ETHUSD",
        "adx_trend_threshold": 22.0,
        "adx_strong_trend_threshold": 32.0,
        "volatility_high_atr_pct": 3.0,
        "volatility_low_atr_pct": 1.0,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "XAUUSD": {
        "symbol": "XAUUSD",
        "adx_trend_threshold": 20.0,
        "adx_strong_trend_threshold": 28.0,
        "volatility_high_atr_pct": 1.8,   # Gold percentage ATR is lower
        "volatility_low_atr_pct": 0.6,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "PAXGUSD": {
        "symbol": "PAXGUSD",
        "adx_trend_threshold": 20.0,
        "adx_strong_trend_threshold": 28.0,
        "volatility_high_atr_pct": 1.8,
        "volatility_low_atr_pct": 0.6,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "XAUTUSD": {
        "symbol": "XAUTUSD",
        "adx_trend_threshold": 20.0,
        "adx_strong_trend_threshold": 28.0,
        "volatility_high_atr_pct": 1.8,
        "volatility_low_atr_pct": 0.6,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "SOLUSD": {
        "symbol": "SOLUSD",
        "adx_trend_threshold": 25.0,      # High-volatility altcoin
        "adx_strong_trend_threshold": 35.0,
        "volatility_high_atr_pct": 4.5,
        "volatility_low_atr_pct": 1.5,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": False
    },
    "XRPUSD": {
        "symbol": "XRPUSD",
        "adx_trend_threshold": 24.0,
        "adx_strong_trend_threshold": 34.0,
        "volatility_high_atr_pct": 4.0,
        "volatility_low_atr_pct": 1.2,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": False
    },
    "DEFAULT": {
        "symbol": "DEFAULT",
        "adx_trend_threshold": 22.0,
        "adx_strong_trend_threshold": 30.0,
        "volatility_high_atr_pct": 3.0,
        "volatility_low_atr_pct": 1.0,
        "ema_fast": 50,
        "ema_slow": 200,
        "hysteresis_bars": 2,
        "is_primary": False
    }
}


def get_asset_regime_config(symbol: Optional[str]) -> Dict[str, Any]:
    """Retrieve asset regime configuration with fallback to DEFAULT."""
    if not symbol:
        return ASSET_REGIME_CONFIGS["DEFAULT"]
    sym = symbol.upper()
    for key, cfg in ASSET_REGIME_CONFIGS.items():
        if key in sym:
            return cfg
    return ASSET_REGIME_CONFIGS["DEFAULT"]


# =============================================================================
# DETERMINISTIC REGIME CLASSIFICATION ENGINE
# =============================================================================

def classify_market_regime(
    candles_1h: Optional[Dict[str, Any]],
    candles_15m: Optional[Dict[str, Any]] = None,
    candles_5m: Optional[Dict[str, Any]] = None,
    symbol: str = "BTCUSD",
    regime_history: Optional[List[str]] = None,
    candles_4h: Optional[Dict[str, Any]] = None,
    candles_1d: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Deterministic 9-Regime Market Classification & Multi-Timeframe Engine.
    Evaluates:
      1D & 4H: Higher-timeframe macro anchor (EMA 21/50/200, ADX, swing structure)
      1H: Intermediate trend (EMA 50/200), ADX strength, ATR volatility state
      15M: Structural confirmation, local trend, range conditions
      5M: Short-term momentum (cannot independently reverse 1H/4H/1D bias)
      Regime Transitions: Trend weakening, Range breakout, HTF macro conflict, Volatility changes
      Anti-whipsaw hysteresis tracking.
    """
    cfg = get_asset_regime_config(symbol)
    now_ts = time.time()

    # Pre-flight data validation
    if not candles_1h or not isinstance(candles_1h, dict):
        return {
            "symbol": symbol,
            "regime": "UNKNOWN",
            "directional_bias": "NEUTRAL",
            "trend_strength": "NONE",
            "volatility_state": "NORMAL",
            "confidence_score": 0,
            "timeframe_analysis": {},
            "regime_transition": {
                "transition_detected": False,
                "transition_type": "NONE",
                "prior_regime": "UNKNOWN",
                "hysteresis_confirmed": False
            },
            "supporting_evidence": [],
            "conflicting_evidence": ["1H candle feed is missing or invalid."],
            "data_timestamp": now_ts,
            "is_provisional": False,
            "reason": "UNKNOWN: 1H candlestick data is missing or empty.",
            "status": "INVALID"
        }

    c_1h = [float(x) for x in candles_1h.get("c", [])]
    h_1h = [float(x) for x in candles_1h.get("h", [])]
    l_1h = [float(x) for x in candles_1h.get("l", [])]
    o_1h = [float(x) for x in candles_1h.get("o", [])]
    n_1h = len(c_1h)

    if n_1h < 20:
        return {
            "symbol": symbol,
            "regime": "UNKNOWN",
            "directional_bias": "NEUTRAL",
            "trend_strength": "NONE",
            "volatility_state": "NORMAL",
            "confidence_score": 0,
            "timeframe_analysis": {},
            "regime_transition": {
                "transition_detected": False,
                "transition_type": "NONE",
                "prior_regime": "UNKNOWN",
                "hysteresis_confirmed": False
            },
            "supporting_evidence": [],
            "conflicting_evidence": [f"Insufficient 1H candles: got {n_1h}, minimum 20 required."],
            "data_timestamp": now_ts,
            "is_provisional": False,
            "reason": f"UNKNOWN: Insufficient 1H candle history ({n_1h} bars).",
            "status": "INVALID"
        }

    current_price = c_1h[-1]
    if current_price <= 0:
        return {
            "symbol": symbol,
            "regime": "UNKNOWN",
            "directional_bias": "NEUTRAL",
            "trend_strength": "NONE",
            "volatility_state": "NORMAL",
            "confidence_score": 0,
            "timeframe_analysis": {},
            "regime_transition": {"transition_detected": False, "transition_type": "NONE", "prior_regime": "UNKNOWN", "hysteresis_confirmed": False},
            "supporting_evidence": [],
            "conflicting_evidence": ["Current price is zero or negative."],
            "data_timestamp": now_ts,
            "is_provisional": False,
            "reason": "UNKNOWN: Price is non-positive.",
            "status": "INVALID"
        }

    # -------------------------------------------------------------------------
    # 1. 1H Macro Timeframe Analysis
    # -------------------------------------------------------------------------
    ema50 = calculate_ema(c_1h, 50)[-1] if n_1h >= 50 else calculate_ema(c_1h, 21)[-1]
    ema200 = calculate_ema(c_1h, 200)[-1] if n_1h >= 200 else ema50

    adx_info = calculate_adx(h_1h, l_1h, c_1h, 14)
    adx_val = float(adx_info.get("adx", 20.0))
    plus_di = float(adx_info.get("plus_di", 20.0))
    minus_di = float(adx_info.get("minus_di", 20.0))

    atrs_1h = calculate_atr(h_1h, l_1h, c_1h, 14)
    atr_1h = atrs_1h[-1] if atrs_1h else current_price * 0.015
    atr_pct = (atr_1h / current_price * 100.0) if current_price > 0 else 1.5

    # ATR 20-period baseline for expansion/contraction detection
    recent_atrs = atrs_1h[-20:] if len(atrs_1h) >= 20 else atrs_1h
    avg_atr_baseline = sum(recent_atrs) / len(recent_atrs) if recent_atrs else atr_1h
    atr_expansion_ratio = atr_1h / max(1e-6, avg_atr_baseline)

    # Volatility State Classification
    high_atr_threshold = cfg["volatility_high_atr_pct"]
    low_atr_threshold = cfg["volatility_low_atr_pct"]

    if atr_pct >= high_atr_threshold or atr_expansion_ratio >= 1.60:
        volatility_state = "HIGH_VOLATILITY"
    elif atr_pct <= low_atr_threshold or atr_expansion_ratio <= 0.75:
        volatility_state = "LOW_VOLATILITY"
    else:
        volatility_state = "NORMAL"

    # 1H Swing Structure Check
    recent_high_1h = max(h_1h[-15:])
    recent_low_1h = min(l_1h[-15:])
    h1_range_pct = (recent_high_1h - recent_low_1h) / current_price * 100.0

    # 1H Directional Stance
    if current_price > ema50 and ema50 >= ema200:
        h1_direction = "BULLISH"
        h1_strength = "STRONG" if adx_val >= cfg["adx_strong_trend_threshold"] else "MODERATE"
    elif current_price > ema50:
        h1_direction = "BULLISH"
        h1_strength = "WEAK"
    elif current_price < ema50 and ema50 <= ema200:
        h1_direction = "BEARISH"
        h1_strength = "STRONG" if adx_val >= cfg["adx_strong_trend_threshold"] else "MODERATE"
    elif current_price < ema50:
        h1_direction = "BEARISH"
        h1_strength = "WEAK"
    else:
        h1_direction = "NEUTRAL"
        h1_strength = "NONE"

    # -------------------------------------------------------------------------
    # 2. 15M Local Market Structure Analysis
    # -------------------------------------------------------------------------
    h15_trend = "NEUTRAL"
    h15_structure = "NORMAL"
    h15_rsi = 50.0

    if candles_15m and len(candles_15m.get("c", [])) >= 20:
        c_15m = [float(x) for x in candles_15m["c"]]
        h_15m = [float(x) for x in candles_15m["h"]]
        l_15m = [float(x) for x in candles_15m["l"]]
        ema21_15m = calculate_ema(c_15m, 21)[-1]
        rsis_15m = calculate_rsi(c_15m, 14)
        h15_rsi = rsis_15m[-1] if rsis_15m else 50.0

        hh = max(h_15m[-10:]) > max(h_15m[-20:-10])
        hl = min(l_15m[-10:]) > min(l_15m[-20:-10])
        lh = max(h_15m[-10:]) < max(h_15m[-20:-10])
        ll = min(l_15m[-10:]) < min(l_15m[-20:-10])

        if hh and hl and c_15m[-1] >= ema21_15m:
            h15_trend = "BULLISH"
            h15_structure = "HIGHER_HIGHS_AND_LOWS"
        elif lh and ll and c_15m[-1] <= ema21_15m:
            h15_trend = "BEARISH"
            h15_structure = "LOWER_HIGHS_AND_LOWS"
        else:
            h15_trend = "NEUTRAL"
            h15_structure = "CONSOLIDATION"

    # -------------------------------------------------------------------------
    # 3. 5M Short-Term Momentum & Entry Environment Analysis
    # -------------------------------------------------------------------------
    m5_momentum = "NEUTRAL"
    m5_rsi = 50.0

    if candles_5m and len(candles_5m.get("c", [])) >= 10:
        c_5m = [float(x) for x in candles_5m["c"]]
        rsis_5m = calculate_rsi(c_5m, 14)
        m5_rsi = rsis_5m[-1] if rsis_5m else 50.0
        ema9_5m = calculate_ema(c_5m, 9)[-1]
        ema21_5m = calculate_ema(c_5m, 21)[-1]

        if c_5m[-1] > ema9_5m and ema9_5m >= ema21_5m and m5_rsi >= 50.0:
            m5_momentum = "BULLISH_ALIGNED"
        elif c_5m[-1] < ema9_5m and ema9_5m <= ema21_5m and m5_rsi <= 50.0:
            m5_momentum = "BEARISH_ALIGNED"
        else:
            m5_momentum = "PULLBACK_OR_CHOP"

    # -------------------------------------------------------------------------
    # 3.5 Higher Timeframe Macro Context (4H & 1D)
    # -------------------------------------------------------------------------
    htf_4h = evaluate_htf_trend(candles_4h, prefix="MACRO", default_price=current_price)
    htf_1d = evaluate_htf_trend(candles_1d, prefix="DAILY", default_price=current_price)
    h4_direction = htf_4h["direction"] if htf_4h["available"] else "UNKNOWN"
    d1_direction = htf_1d["direction"] if htf_1d["available"] else "UNKNOWN"

    # -------------------------------------------------------------------------
    # 4. Canonical 9-Regime State Machine Classification
    # -------------------------------------------------------------------------
    adx_trend_th = cfg["adx_trend_threshold"]
    adx_strong_th = cfg["adx_strong_trend_threshold"]

    # Initial Raw Regime Evaluation
    raw_regime = "RANGING"
    raw_bias = "NEUTRAL"

    # Check Volatility Extrema First
    if volatility_state == "HIGH_VOLATILITY" and (atr_expansion_ratio >= 1.80 or atr_pct >= (high_atr_threshold * 1.25)):
        raw_regime = "HIGH_VOLATILITY"
        raw_bias = h1_direction if h1_strength == "STRONG" else "NEUTRAL"
    elif volatility_state == "LOW_VOLATILITY" and adx_val < adx_trend_th:
        raw_regime = "LOW_VOLATILITY"
        raw_bias = "NEUTRAL"
    elif h1_direction == "BULLISH":
        if adx_val >= adx_strong_th and plus_di > minus_di:
            raw_regime = "STRONG_UPTREND"
            raw_bias = "BULLISH"
        elif adx_val >= adx_trend_th and plus_di >= minus_di:
            raw_regime = "WEAK_UPTREND"
            raw_bias = "BULLISH"
        else:
            raw_regime = "RANGING"
            raw_bias = "NEUTRAL"
    elif h1_direction == "BEARISH":
        if adx_val >= adx_strong_th and minus_di > plus_di:
            raw_regime = "STRONG_DOWNTREND"
            raw_bias = "BEARISH"
        elif adx_val >= adx_trend_th and minus_di >= plus_di:
            raw_regime = "WEAK_DOWNTREND"
            raw_bias = "BEARISH"
        else:
            raw_regime = "RANGING"
            raw_bias = "NEUTRAL"
    else:
        raw_regime = "RANGING"
        raw_bias = "NEUTRAL"

    # -------------------------------------------------------------------------
    # 5. Regime Transition & Anti-Whipsaw Hysteresis Engine
    # -------------------------------------------------------------------------
    transition_detected = False
    transition_type = "NONE"
    is_provisional = False
    prior_regime = regime_history[-1] if (regime_history and len(regime_history) > 0) else raw_regime
    hysteresis_confirmed = True

    # Transition Detection Logic
    if "TREND" in prior_regime and raw_regime == "RANGING":
        transition_detected = True
        transition_type = "TREND_TO_RANGE"
    elif prior_regime == "RANGING" and "TREND" in raw_regime:
        transition_detected = True
        transition_type = "RANGE_BREAKOUT"
    elif "STRONG" in prior_regime and "WEAK" in raw_regime:
        transition_detected = True
        transition_type = "TREND_WEAKENING"
    elif volatility_state == "HIGH_VOLATILITY" and prior_regime != "HIGH_VOLATILITY":
        transition_detected = True
        transition_type = "VOLATILITY_EXPANSION"
    elif volatility_state == "LOW_VOLATILITY" and prior_regime != "LOW_VOLATILITY":
        transition_detected = True
        transition_type = "VOLATILITY_COMPRESSION"

    # Apply Hysteresis: prevent rapid 1-bar flipping between Strong Trend and Range
    final_regime = raw_regime
    final_bias = raw_bias

    if regime_history and len(regime_history) >= 1:
        recent_regimes = regime_history[-cfg["hysteresis_bars"]:]
        # If trying to flip from established strong trend to range or compression based on only 1 bar
        if any("STRONG" in r for r in recent_regimes) and raw_regime in ("RANGING", "TRANSITIONAL", "LOW_VOLATILITY"):
            # If not yet confirmed for hysteresis_bars, classify as TRANSITIONAL
            if not all(r in ("RANGING", "TRANSITIONAL", "LOW_VOLATILITY") for r in recent_regimes):
                final_regime = "TRANSITIONAL"
                final_bias = "NEUTRAL"
                is_provisional = True
                hysteresis_confirmed = False

    # Multi-Timeframe Invariant Check: 5M cannot independently reverse 1H bias!
    if h1_direction == "BULLISH" and m5_momentum == "BEARISH_ALIGNED":
        # 5M counter-move is classified as an intraday pullback, NOT a macro trend change
        if "UPTREND" in final_regime:
            final_regime = "WEAK_UPTREND"
            final_bias = "BULLISH"

    elif h1_direction == "BEARISH" and m5_momentum == "BULLISH_ALIGNED":
        if "DOWNTREND" in final_regime:
            final_regime = "WEAK_DOWNTREND"
            final_bias = "BEARISH"

    # Higher-Timeframe (4H + 1D) Macro Alignment Anchor
    htf_conflict_demoted = False
    if htf_4h["available"] or htf_1d["available"]:
        if final_bias == "BULLISH":
            if h4_direction == "BEARISH" and d1_direction == "BEARISH":
                final_regime = "TRANSITIONAL"
                final_bias = "NEUTRAL"
                is_provisional = True
                transition_detected = True
                transition_type = "HTF_MACRO_CONFLICT"
                htf_conflict_demoted = True
            elif (h4_direction == "BEARISH" or d1_direction == "BEARISH") and h4_direction != "BULLISH" and d1_direction != "BULLISH":
                if final_regime == "STRONG_UPTREND":
                    final_regime = "WEAK_UPTREND"
        elif final_bias == "BEARISH":
            if h4_direction == "BULLISH" and d1_direction == "BULLISH":
                final_regime = "TRANSITIONAL"
                final_bias = "NEUTRAL"
                is_provisional = True
                transition_detected = True
                transition_type = "HTF_MACRO_CONFLICT"
                htf_conflict_demoted = True
            elif (h4_direction == "BULLISH" or d1_direction == "BULLISH") and h4_direction != "BEARISH" and d1_direction != "BEARISH":
                if final_regime == "STRONG_DOWNTREND":
                    final_regime = "WEAK_DOWNTREND"

    # -------------------------------------------------------------------------
    # 6. Explainable Confidence Calibration Model
    # -------------------------------------------------------------------------
    # Base = 20 pts
    # +30 pts: MTF Agreement (1H, 15M, and 5M aligned)
    # +25 pts: Trend Strength (ADX >= strong threshold)
    # +15 pts: Structural Confirmation (HH/HL or LH/LL)
    # +10 pts: Normal Volatility & Fresh Data
    # Deductions: -25 pts for conflicting timeframes, -15 pts for provisional/transitional
    conf_score = 20
    supporting = []
    conflicting = []

    # Evidence & Score Compilation
    if final_bias == "BULLISH":
        supporting.append(f"1H Price (${current_price:,.2f}) above EMA50 (${ema50:,.2f}) and EMA200 (${ema200:,.2f})")
    elif final_bias == "BEARISH":
        supporting.append(f"1H Price (${current_price:,.2f}) below EMA50 (${ema50:,.2f}) and EMA200 (${ema200:,.2f})")
    else:
        supporting.append(f"1H Price oscillating around EMA50 (${ema50:,.2f}) in range-bound structure")

    if adx_val >= adx_strong_th:
        conf_score += 25
        supporting.append(f"ADX(14) is {adx_val:.1f} (Strong Trend) with +DI={plus_di:.1f}, -DI={minus_di:.1f}")
    elif adx_val >= adx_trend_th:
        conf_score += 15
        supporting.append(f"ADX(14) is {adx_val:.1f} (Moderate Trend)")
    else:
        conf_score += 5
        supporting.append(f"ADX(14) is {adx_val:.1f} (Ranging / Trendless)")

    # MTF Alignment Check
    mtf_aligned = False
    if final_bias == "BULLISH":
        if h15_trend == "BULLISH":
            conf_score += 20
            supporting.append("15M structural trend confirms Higher Highs & Higher Lows")
        elif h15_trend == "BEARISH":
            conf_score -= 20
            conflicting.append("15M structure is BEARISH, conflicting with 1H bullish bias")

        if m5_momentum == "BULLISH_ALIGNED":
            conf_score += 10
            mtf_aligned = True
            supporting.append("5M short-term momentum confirms bullish alignment")
        elif m5_momentum == "BEARISH_ALIGNED":
            conf_score -= 15
            conflicting.append("5M momentum counter-trend (short-term pullback active)")

    elif final_bias == "BEARISH":
        if h15_trend == "BEARISH":
            conf_score += 20
            supporting.append("15M structural trend confirms Lower Highs & Lower Lows")
        elif h15_trend == "BULLISH":
            conf_score -= 20
            conflicting.append("15M structure is BULLISH, conflicting with 1H bearish bias")

        if m5_momentum == "BEARISH_ALIGNED":
            conf_score += 10
            mtf_aligned = True
            supporting.append("5M short-term momentum confirms bearish alignment")
        elif m5_momentum == "BULLISH_ALIGNED":
            conf_score -= 15
            conflicting.append("5M momentum counter-trend (short-term bounce active)")

    if volatility_state == "NORMAL":
        conf_score += 10
        supporting.append(f"ATR percentage ({atr_pct:.2f}%) within normal volatility bounds")
    elif volatility_state == "HIGH_VOLATILITY":
        conf_score -= 10
        conflicting.append(f"High volatility expansion detected (ATR {atr_pct:.2f}%)")
    elif volatility_state == "LOW_VOLATILITY":
        supporting.append(f"Volatility compression active (ATR {atr_pct:.2f}%)")

    # Higher-Timeframe (4H & 1D) Confidence & Evidence Integration
    if htf_conflict_demoted:
        conf_score -= 20
        conflicting.append(
            f"1H {h1_direction} move opposes both 4H ({h4_direction}) and 1D ({d1_direction}) macro trends — demoted to TRANSITIONAL"
        )
    else:
        for tf_label, htf_meta in (("4H", htf_4h), ("1D", htf_1d)):
            if not htf_meta["available"]:
                continue
            tf_dir = htf_meta["direction"]
            if final_bias in ("BULLISH", "BEARISH"):
                if tf_dir == final_bias:
                    conf_score += 10
                    supporting.append(
                        f"{tf_label} confirms {tf_dir} ({htf_meta['structure']}, ADX {htf_meta['adx']:.1f})"
                    )
                elif tf_dir in ("BULLISH", "BEARISH"):
                    conf_score -= 15
                    conflicting.append(
                        f"{tf_label} is {tf_dir} (ADX {htf_meta['adx']:.1f}), opposing {final_bias} regime"
                    )
                else:
                    conf_score -= 5
                    conflicting.append(
                        f"{tf_label} is NEUTRAL (ADX {htf_meta['adx']:.1f}), lacking higher-timeframe confirmation"
                    )
            else:
                supporting.append(
                    f"{tf_label} context: {tf_dir} ({htf_meta['structure']}, ADX {htf_meta['adx']:.1f})"
                )

    if is_provisional:
        conf_score -= 15
        conflicting.append("Regime in provisional state pending multi-bar confirmation")

    calibrated_conf = max(10, min(100, conf_score))

    # Construct Narrative Reason
    htf_summary = ""
    if htf_4h["available"] or htf_1d["available"]:
        parts = []
        if htf_4h["available"]:
            parts.append(f"4H {h4_direction}")
        if htf_1d["available"]:
            parts.append(f"1D {d1_direction}")
        htf_summary = f", {' / '.join(parts)}"

    reason = (
        f"{final_regime} confirmed on {symbol}: 1H {h1_direction} bias (ADX {adx_val:.1f}, Vol {volatility_state}){htf_summary} "
        f"with 15M {h15_trend} structure ({h15_structure}). Confidence: {calibrated_conf}/100."
    )

    return {
        "symbol": symbol,
        "regime": final_regime,
        "directional_bias": final_bias,
        "trend_strength": h1_strength,
        "volatility_state": volatility_state,
        "confidence_score": calibrated_conf,
        "timeframe_analysis": {
            "1d": {
                "available": htf_1d["available"],
                "direction": d1_direction,
                "regime": htf_1d["regime"],
                "adx": htf_1d["adx"],
                "plus_di": htf_1d["plus_di"],
                "minus_di": htf_1d["minus_di"],
                "rsi_14": htf_1d["rsi_14"],
                "ema_21": htf_1d["ema_21"],
                "ema_50": htf_1d["ema_50"],
                "ema_200": htf_1d["ema_200"],
                "structure": htf_1d["structure"]
            },
            "4h": {
                "available": htf_4h["available"],
                "direction": h4_direction,
                "regime": htf_4h["regime"],
                "adx": htf_4h["adx"],
                "plus_di": htf_4h["plus_di"],
                "minus_di": htf_4h["minus_di"],
                "rsi_14": htf_4h["rsi_14"],
                "ema_21": htf_4h["ema_21"],
                "ema_50": htf_4h["ema_50"],
                "ema_200": htf_4h["ema_200"],
                "structure": htf_4h["structure"]
            },
            "1h": {
                "direction": h1_direction,
                "adx": adx_val,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "volatility": volatility_state,
                "ema50": round(ema50, 4),
                "ema200": round(ema200, 4),
                "atr_14": round(atr_1h, 4),
                "atr_pct": round(atr_pct, 2)
            },
            "15m": {
                "trend": h15_trend,
                "structure": h15_structure,
                "rsi_14": round(h15_rsi, 2)
            },
            "5m": {
                "momentum": m5_momentum,
                "rsi_14": round(m5_rsi, 2)
            }
        },
        "regime_transition": {
            "transition_detected": transition_detected,
            "transition_type": transition_type,
            "prior_regime": prior_regime,
            "hysteresis_confirmed": hysteresis_confirmed
        },
        "supporting_evidence": supporting,
        "conflicting_evidence": conflicting,
        "data_timestamp": now_ts,
        "is_provisional": is_provisional,
        "reason": reason,
        "status": "CONFIRMED" if not is_provisional else "PROVISIONAL"
    }


# =============================================================================
# REGIME ANALYST AGENT CLASS
# =============================================================================

class RegimeAnalystAgent:
    """
    Agent 1: Market Regime & Technical Analyst.
    Multi-timeframe market structure and regime intelligence engine.
    """

    def __init__(
        self,
        client: Optional[DeltaExchangeClient] = None,
        data_validator: Optional[MarketDataValidator] = None
    ):
        self.client = client
        self.validator = data_validator or MarketDataValidator()
        self.regime_histories: Dict[str, List[str]] = {}

    def classify_regime(
        self,
        candles_1h: Optional[Dict[str, Any]],
        candles_15m: Optional[Dict[str, Any]] = None,
        candles_5m: Optional[Dict[str, Any]] = None,
        symbol: str = "BTCUSD",
        candles_4h: Optional[Dict[str, Any]] = None,
        candles_1d: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Public deterministic classification method.
        Directly testable with historical fixtures or mocked data.
        """
        history = self.regime_histories.get(symbol, [])
        result = classify_market_regime(
            candles_1h=candles_1h,
            candles_15m=candles_15m,
            candles_5m=candles_5m,
            symbol=symbol,
            regime_history=history,
            candles_4h=candles_4h,
            candles_1d=candles_1d
        )
        # Update rolling regime history
        if result.get("regime") and result["regime"] != "UNKNOWN":
            history.append(result["regime"])
            if len(history) > 10:
                history.pop(0)
            self.regime_histories[symbol] = history

        return result

    def analyze_symbol(
        self,
        symbol: str,
        resolution: str = "60",
        candles_5m: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze price action, indicators, and market regime with multi-timeframe confluence:
        1H, 15M, 5M (if available), 4H, Daily, and Weekly.
        """
        logger.info(f"RegimeAnalyst: Fetching 15m, 1H, 4H, Daily & Weekly structure for {symbol}...")
        now = int(time.time())

        # If no exchange client provided, fail closed with UNKNOWN
        if not self.client:
            return {
                "symbol": symbol,
                "regime": "UNKNOWN",
                "directional_bias": "NEUTRAL",
                "trend_strength": "NONE",
                "volatility_state": "NORMAL",
                "confidence_score": 0,
                "error": "No exchange client available",
                "status": "INVALID"
            }

        # 1. 15-Minute Candles (Structural Timeframe - 400 bars for statistical stability)
        candles_15m_res = self.client.get_candles(symbol, resolution="15", from_time=now - (900 * 400), to_time=now)
        candles_15m = candles_15m_res.get("result", {}) if candles_15m_res.get("success") else None

        if candles_15m:
            val_15 = self.validator.validate_candlestick_data(symbol, candles_15m, resolution="15", min_bars_required=20)
            if not val_15["is_valid"]:
                logger.warning(f"RegimeAnalyst: 15m candles failed validation for {symbol}: {val_15['issues']}")
                candles_15m = None

        # 2. 1-Hour Candles (Macro Direction & Volatility Timeframe - 200 bars)
        candles_1h_res = self.client.get_candles(symbol, resolution="60", from_time=now - (3600 * 200), to_time=now)
        if not candles_1h_res.get("success"):
            err_msg = str(candles_1h_res.get("error", "Failed to fetch 1H candlestick data"))
            return {
                "symbol": symbol,
                "regime": "UNKNOWN",
                "directional_bias": "NEUTRAL",
                "trend_strength": "NONE",
                "volatility_state": "NORMAL",
                "confidence_score": 0,
                "error": err_msg,
                "status": "INVALID"
            }

        candles_1h = candles_1h_res.get("result", {})
        val_1h = self.validator.validate_candlestick_data(symbol, candles_1h, resolution="60", min_bars_required=20)
        if not val_1h["is_valid"]:
            return {
                "symbol": symbol,
                "regime": "UNKNOWN",
                "directional_bias": "NEUTRAL",
                "trend_strength": "NONE",
                "volatility_state": "NORMAL",
                "confidence_score": 0,
                "error": f"1H Candlestick data validation failed: {'; '.join(val_1h['issues'])}",
                "status": "INVALID"
            }

        # 3. 5-Minute Candles (Primary Scalp Momentum Timeframe)
        if not candles_5m:
            try:
                candles_5m_res = self.client.get_candles(symbol, resolution="5")
                candles_5m = candles_5m_res.get("result", {}) if (candles_5m_res and candles_5m_res.get("success")) else None
                if candles_5m:
                    val_5 = self.validator.validate_candlestick_data(symbol, candles_5m, resolution="5", min_bars_required=15)
                    if not val_5["is_valid"]:
                        candles_5m = None
            except Exception as e:
                logger.debug(f"RegimeAnalyst: 5m fetch optional fallback: {e}")
                candles_5m = None

        # 4. Higher Timeframes (4H, Daily, Weekly)
        candles_4h_res = self.client.get_candles(symbol, resolution="240", from_time=now - (14400 * 240), to_time=now)
        candles_4h = candles_4h_res.get("result", {}) if candles_4h_res.get("success") else None

        candles_1d_res = self.client.get_candles(symbol, resolution="D", from_time=now - (86400 * 365), to_time=now)
        candles_1d = candles_1d_res.get("result", {}) if candles_1d_res.get("success") else None

        candles_1w_res = self.client.get_candles(symbol, resolution="W")
        candles_1w = candles_1w_res.get("result", {}) if candles_1w_res.get("success") else None

        # Level-2 Order Book
        orderbook_res = self.client.get_orderbook(symbol)
        orderbook_data = orderbook_res.get("result") if (orderbook_res and orderbook_res.get("success")) else None

        # Technical Analysis Base
        analysis = analyze_multi_timeframe(
            candles_1h=candles_1h,
            candles_4h=candles_4h,
            candles_1d=candles_1d,
            candles_1w=candles_1w,
            candles_15m=candles_15m,
            symbol=symbol,
            orderbook=orderbook_data
        )
        analysis["symbol"] = symbol.upper()
        analysis["resolution"] = resolution
        analysis["_raw_candles_15m"] = candles_15m
        analysis["_raw_candles_1h"] = candles_1h
        analysis["_raw_candles_5m"] = candles_5m

        # Live Ticker Ingestion
        ticker_res = self.client.get_ticker(symbol)
        if ticker_res.get("success"):
            tick = ticker_res.get("result")
            if isinstance(tick, dict):
                tick_val = self.validator.validate_ticker_data(symbol, tick)
                if tick_val["is_valid"]:
                    analysis["mark_price"] = float(tick.get("mark_price") or analysis.get("current_price", 0))
                    analysis["open_interest"] = tick.get("oi_contracts")
                    analysis["funding_rate"] = float(tick.get("funding_rate") or 0.0)
                    analysis["bid_price"] = float(tick.get("bid") or 0.0)
                    analysis["ask_price"] = float(tick.get("ask") or 0.0)
                    if analysis["bid_price"] > 0 and analysis["ask_price"] > 0:
                        analysis["spread_pct"] = round((analysis["ask_price"] - analysis["bid_price"]) / analysis["bid_price"] * 100, 3)

        # Execute Deterministic 9-Regime Classification
        regime_meta = self.classify_regime(
            candles_1h=candles_1h,
            candles_15m=candles_15m,
            candles_5m=candles_5m,
            symbol=symbol,
            candles_4h=candles_4h,
            candles_1d=candles_1d
        )

        # Merge new canonical fields into analysis dictionary
        analysis["regime"] = regime_meta["regime"]
        analysis["directional_bias"] = regime_meta["directional_bias"]
        analysis["trend_strength"] = regime_meta["trend_strength"]
        analysis["volatility_state"] = regime_meta["volatility_state"]
        analysis["confidence_score"] = regime_meta["confidence_score"]
        analysis["regime_confidence"] = regime_meta["confidence_score"]
        analysis["timeframe_analysis"] = regime_meta["timeframe_analysis"]
        analysis["regime_transition"] = regime_meta["regime_transition"]
        analysis["supporting_evidence"] = regime_meta["supporting_evidence"]
        analysis["conflicting_evidence"] = regime_meta["conflicting_evidence"]
        analysis["data_timestamp"] = regime_meta["data_timestamp"]
        analysis["is_provisional"] = regime_meta["is_provisional"]
        analysis["reason"] = regime_meta["reason"]
        analysis["status"] = regime_meta["status"]

        return analysis

    def scan_universe(self, symbols: List[str], resolution: str = "60") -> Dict[str, Any]:
        """
        Analyze watchlist and compute aggregate market breadth, volatility temperature, and BTC anchor.
        """
        results = {}
        for sym in symbols:
            res = self.analyze_symbol(sym, resolution)
            if "error" not in res:
                results[sym] = res

        # BTC anchor
        btc_analysis = results.get("BTCUSD") or results.get("BTCUSDT")
        eth_analysis = results.get("ETHUSD") or results.get("ETHUSDT")

        overall_regime = "NEUTRAL"
        btc_adx = 20.0
        btc_vol_state = "NORMAL"
        btc_confidence = 50

        if btc_analysis:
            overall_regime = btc_analysis.get("regime") or btc_analysis.get("macro_4h", {}).get("regime", "NEUTRAL")
            btc_adx = btc_analysis.get("timeframe_analysis", {}).get("1h", {}).get("adx", 20.0)
            btc_vol_state = btc_analysis.get("volatility_state", "NORMAL")
            btc_confidence = btc_analysis.get("confidence_score", 50)

        # Market-wide breadth
        above_ema_count = 0
        macd_bullish_count = 0
        vwap_above_count = 0
        cvd_bullish_count = 0
        obi_bullish_count = 0
        total_valid = 0
        funding_rates = []
        spreads = []
        atr_pcts = []

        for s_data in results.values():
            c_price = s_data.get("current_price", 0.0)
            ema20 = s_data.get("ema_20", 0.0)
            if c_price > 0 and ema20 > 0:
                total_valid += 1
                if c_price >= ema20:
                    above_ema_count += 1

            m_info = s_data.get("macd", {})
            if m_info.get("histogram", 0) > 0 or "BULLISH" in m_info.get("bias", ""):
                macd_bullish_count += 1

            vwap_p = s_data.get("vwap", 0.0)
            if c_price > 0 and vwap_p > 0 and c_price >= vwap_p:
                vwap_above_count += 1

            cvd_info = s_data.get("cvd", {})
            if cvd_info.get("cvd_trend") == "RISING_ACCUMULATION" or cvd_info.get("current_cvd", 0) > 0:
                cvd_bullish_count += 1

            obi_info = s_data.get("order_book_imbalance", {})
            if obi_info.get("obi_ratio", 0) > 0.05 or obi_info.get("imbalance_status") == "HEAVY_BID_IMBALANCE":
                obi_bullish_count += 1

            if "funding_rate" in s_data:
                funding_rates.append(s_data["funding_rate"])

            sp = s_data.get("spread_pct")
            if sp is not None and sp > 0:
                spreads.append(sp)

            ap = s_data.get("atr_pct")
            if ap is not None and ap > 0:
                atr_pcts.append(ap)

        breadth_pct = round((above_ema_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0
        macd_breadth_pct = round((macd_bullish_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0
        vwap_breadth_pct = round((vwap_above_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0
        cvd_breadth_pct = round((cvd_bullish_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0
        obi_breadth_pct = round((obi_bullish_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0
        avg_spread = round(sum(spreads) / len(spreads), 3) if spreads else 0.04
        market_liquidity_state = "PRIME_LIQUIDITY" if avg_spread <= 0.05 else ("NORMAL_LIQUIDITY" if avg_spread <= 0.12 else "ILLIQUID_CAUTION")

        avg_atr_pct = round(sum(atr_pcts) / len(atr_pcts), 2) if atr_pcts else 1.50
        if avg_atr_pct < 1.0:
            vol_temperature = "CALM_COMPRESSION"
        elif avg_atr_pct <= 2.5:
            vol_temperature = "NORMAL_VOLATILITY"
        elif avg_atr_pct <= 4.0:
            vol_temperature = "HIGH_VOLATILITY_EXPANSION"
        else:
            vol_temperature = "EXTREME_VOLATILITY"

        eth_btc_relative_strength = 1.0
        if eth_analysis and btc_analysis:
            eth_change = eth_analysis.get("price_change_24h_pct", 0.0)
            btc_change = btc_analysis.get("price_change_24h_pct", 0.0)
            eth_btc_relative_strength = round((1.0 + eth_change / 100.0) / max(0.01, 1.0 + btc_change / 100.0), 3)

        avg_funding = round(sum(funding_rates) / len(funding_rates), 6) if funding_rates else 0.0
        funding_skew = "NEUTRAL"
        if avg_funding > 0.0003:
            funding_skew = "CROWDED_LONGS"
        elif avg_funding < -0.0001:
            funding_skew = "CROWDED_SHORTS"

        btc_macd = btc_analysis.get("macd", {}) if btc_analysis else {}
        btc_vwap = btc_analysis.get("vwap_analysis", {}) if btc_analysis else {}

        return {
            "overall_market_regime": overall_regime,
            "btc_adx": btc_adx,
            "btc_volatility_state": btc_vol_state,
            "btc_macd": btc_macd,
            "btc_vwap": btc_vwap,
            "regime_confidence_score": btc_confidence,
            "breadth_pct": breadth_pct,
            "macd_breadth_pct": macd_breadth_pct,
            "vwap_breadth_pct": vwap_breadth_pct,
            "cvd_breadth_pct": cvd_breadth_pct,
            "obi_breadth_pct": obi_breadth_pct,
            "avg_spread_pct": avg_spread,
            "market_liquidity_state": market_liquidity_state,
            "avg_watchlist_atr_pct": avg_atr_pct,
            "market_volatility_temperature": vol_temperature,
            "eth_btc_relative_strength": eth_btc_relative_strength,
            "avg_funding_rate": avg_funding,
            "funding_rate_skew": funding_skew,
            "analyzed_count": len(results),
            "symbols_data": results
        }
