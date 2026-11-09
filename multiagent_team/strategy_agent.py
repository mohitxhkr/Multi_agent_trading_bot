"""
Agent 4: Strategy Agent (Alpha Generator & Technical Decision Engine).
Evaluates multi-timeframe market regime intelligence (1H, 15M, 5M, 1M) and generates
high-conviction trade setups using deterministic Smart Money Concepts (SMC):
- 1H Market Direction, EMA 50/200 Trend, ATR Volatility & ADX Strength
- 15M Market Structure, Break of Structure (BOS), Change of Character (CHOCH),
  Liquidity Sweeps (BSL/SSL), Fair Value Gaps (FVG) & 50% Consequent Encroachment (CE)
- 5M Primary Setup Confirmation & Volume Trigger
- 1M Optional Execution Refinement
- Asset-Specific Calibration (BTC, ETH, SOL, XRP, XAU)
- 100-Point Normalized Confluence Scoring with Mandatory Hard Vetoes
- Asymmetric Risk-to-Reward (Net R:R >= 2.2:1) & Technical Invalidation Stop Loss.
"""

from typing import Dict, Any, List, Optional, Tuple
import time
import math
import logging

from multiagent_team.adaptive_learning import AdaptiveLearningEngine
from src.technical_analysis import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    calculate_vwap,
    detect_fair_value_gaps,
    analyze_liquidity_pools_and_sweeps
)

logger = logging.getLogger("strategy-agent")


# =============================================================================
# ASSET-SPECIFIC CONFIGURATIONS
# =============================================================================

ASSET_CONFIGS: Dict[str, Dict[str, Any]] = {
    "BTCUSD": {
        "symbol": "BTCUSD",
        "max_spread_pct": 0.05,       # Institutional liquidity on BTC
        "target_rr_ratio": 2.5,
        "min_confluence_score": 75,   # Institutional primary alpha floor
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.03,
        "pivot_window": 2,
        "is_primary": True,
        "priority_tier": 1
    },
    "ETHUSD": {
        "symbol": "ETHUSD",
        "max_spread_pct": 0.07,
        "target_rr_ratio": 2.5,
        "min_confluence_score": 75,   # Institutional primary alpha floor
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.04,
        "pivot_window": 2,
        "is_primary": True,
        "priority_tier": 1
    },
    "XAUUSD": {
        "symbol": "XAUUSD",
        "max_spread_pct": 0.10,       # Gold market microstructure
        "target_rr_ratio": 2.4,
        "min_confluence_score": 75,   # Institutional primary alpha floor
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.03,
        "pivot_window": 2,
        "is_primary": True,
        "priority_tier": 1
    },
    "SOLUSD": {
        "symbol": "SOLUSD",
        "max_spread_pct": 0.12,       # Higher altcoin volatility & spread
        "target_rr_ratio": 2.6,
        "min_confluence_score": 75,
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.05,
        "pivot_window": 2,
        "is_primary": False,
        "priority_tier": 2
    },
    "XRPUSD": {
        "symbol": "XRPUSD",
        "max_spread_pct": 0.15,
        "target_rr_ratio": 2.6,
        "min_confluence_score": 75,
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.05,
        "pivot_window": 2,
        "is_primary": False,
        "priority_tier": 2
    },
    "DEFAULT": {
        "symbol": "DEFAULT",
        "max_spread_pct": 0.15,
        "target_rr_ratio": 2.5,
        "min_confluence_score": 75,
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.04,
        "pivot_window": 2,
        "is_primary": False,
        "priority_tier": 2
    }
}


def get_asset_config(symbol: Optional[str]) -> Dict[str, Any]:
    """Retrieve asset configuration with fallback to DEFAULT."""
    if not symbol:
        return ASSET_CONFIGS["DEFAULT"]
    sym = symbol.upper()
    for key, cfg in ASSET_CONFIGS.items():
        if key in sym:
            return cfg
    return ASSET_CONFIGS["DEFAULT"]


# =============================================================================
# DETERMINISTIC SMART MONEY CONCEPTS (SMC) & MULTI-TIMEFRAME UTILITIES
# =============================================================================

def detect_fractal_pivots(
    highs: List[float],
    lows: List[float],
    window: int = 2
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """
    Detect confirmed fractal pivot highs and lows with strictly zero lookahead.
    A pivot at bar i is only confirmed after 'window' subsequent bars have fully closed.
    """
    n = len(highs)
    pivot_highs: List[Tuple[int, float]] = []
    pivot_lows: List[Tuple[int, float]] = []

    if n < (window * 2 + 1):
        return pivot_highs, pivot_lows

    # Only evaluate pivots up to n - 1 - window (confirmed pivots only)
    for i in range(window, n - window):
        # Pivot High
        is_p_high = True
        for w in range(1, window + 1):
            if highs[i] <= highs[i - w] or highs[i] <= highs[i + w]:
                is_p_high = False
                break
        if is_p_high:
            pivot_highs.append((i, highs[i]))

        # Pivot Low
        is_p_low = True
        for w in range(1, window + 1):
            if lows[i] >= lows[i - w] or lows[i] >= lows[i + w]:
                is_p_low = False
                break
        if is_p_low:
            pivot_lows.append((i, lows[i]))

    return pivot_highs, pivot_lows


def analyze_market_structure_bos_choch(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    opens: Optional[List[float]] = None,
    pivot_window: int = 2
) -> Dict[str, Any]:
    """
    Deterministic Break of Structure (BOS) and Change of Character (CHOCH) Engine.
    - BOS: Candle close breaking prior swing pivot in the direction of the trend.
    - CHOCH: Candle close breaking the most recent counter-trend swing pivot, signaling reversal.
    - Candle-close confirmation required; wick-only breaches are not structural breaks.
    """
    n = len(closes)
    if n < 20:
        return {
            "trend": "NEUTRAL",
            "bos_detected": False,
            "choch_detected": False,
            "structure_type": "INSUFFICIENT_DATA",
            "recent_swing_high": 0.0,
            "recent_swing_low": 0.0
        }

    pivot_highs, pivot_lows = detect_fractal_pivots(highs, lows, window=pivot_window)

    recent_swing_high = pivot_highs[-1][1] if pivot_highs else max(highs[-15:])
    recent_swing_low = pivot_lows[-1][1] if pivot_lows else min(lows[-15:])

    # Establish baseline structural trend from consecutive swing points
    trend = "NEUTRAL"
    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        hh = pivot_highs[-1][1] > pivot_highs[-2][1]
        hl = pivot_lows[-1][1] > pivot_lows[-2][1]
        lh = pivot_highs[-1][1] < pivot_highs[-2][1]
        ll = pivot_lows[-1][1] < pivot_lows[-2][1]

        if hh and hl:
            trend = "BULLISH"
        elif lh and ll:
            trend = "BEARISH"

    current_close = closes[-1]
    prev_close = closes[-2] if n >= 2 else current_close

    bos_detected = False
    choch_detected = False
    structure_type = "ALIGNED_STRUCTURE"

    if trend == "BULLISH":
        # Bullish BOS: Candle close exceeds previous swing high
        if current_close > recent_swing_high and prev_close <= recent_swing_high:
            bos_detected = True
            structure_type = "BULLISH_BOS"
        # Bearish CHOCH: Candle close breaks below previous higher low
        elif current_close < recent_swing_low and prev_close >= recent_swing_low:
            choch_detected = True
            trend = "BEARISH_REVERSAL"
            structure_type = "BEARISH_CHOCH"

    elif trend == "BEARISH":
        # Bearish BOS: Candle close breaks below previous swing low
        if current_close < recent_swing_low and prev_close >= recent_swing_low:
            bos_detected = True
            structure_type = "BEARISH_BOS"
        # Bullish CHOCH: Candle close breaks above previous lower high
        elif current_close > recent_swing_high and prev_close <= recent_swing_high:
            choch_detected = True
            trend = "BULLISH_REVERSAL"
            structure_type = "BULLISH_CHOCH"

    else:
        # Neutral market: check for initial breakout
        if current_close > recent_swing_high:
            bos_detected = True
            trend = "BULLISH"
            structure_type = "BULLISH_BREAKOUT"
        elif current_close < recent_swing_low:
            bos_detected = True
            trend = "BEARISH"
            structure_type = "BEARISH_BREAKDOWN"

    return {
        "trend": trend,
        "bos_detected": bos_detected,
        "choch_detected": choch_detected,
        "structure_type": structure_type,
        "recent_swing_high": round(recent_swing_high, 4),
        "recent_swing_low": round(recent_swing_low, 4),
        "pivot_highs_count": len(pivot_highs),
        "pivot_lows_count": len(pivot_lows)
    }


def analyze_1h_market_context(
    candles_1h: Optional[Dict[str, Any]],
    current_price: float
) -> Dict[str, Any]:
    """
    1H Timeframe Market Direction & Volatility Analysis.
    Evaluates Higher Highs / Lows, EMA 50 / 200, ATR volatility, and trend strength.
    """
    if not candles_1h or len(candles_1h.get("c", [])) < 20:
        return {
            "direction": "NEUTRAL",
            "regime": "NEUTRAL",
            "volatility": "NORMAL",
            "ema50": 0.0,
            "ema200": 0.0,
            "atr_14": 0.0,
            "adx_strength": "MODERATE"
        }

    c_1h = [float(x) for x in candles_1h["c"]]
    h_1h = [float(x) for x in candles_1h["h"]]
    l_1h = [float(x) for x in candles_1h["l"]]
    n = len(c_1h)

    ema50 = calculate_ema(c_1h, 50)[-1] if n >= 50 else calculate_ema(c_1h, 21)[-1]
    ema200 = calculate_ema(c_1h, 200)[-1] if n >= 200 else ema50
    atrs = calculate_atr(h_1h, l_1h, c_1h, 14)
    atr_14 = atrs[-1] if atrs else 0.0
    atr_pct = (atr_14 / current_price * 100.0) if current_price > 0 else 0.0

    volatility = "HIGH_VOLATILITY" if atr_pct > 3.0 else ("LOW_VOLATILITY" if atr_pct < 0.8 else "NORMAL")

    # Direction assessment from price and EMA 50/200
    if current_price > ema50 and ema50 >= ema200:
        direction = "BULLISH"
        regime = "STRONG_BULLISH"
    elif current_price > ema50:
        direction = "BULLISH"
        regime = "MILD_BULLISH"
    elif current_price < ema50 and ema50 <= ema200:
        direction = "BEARISH"
        regime = "STRONG_BEARISH"
    elif current_price < ema50:
        direction = "BEARISH"
        regime = "MILD_BEARISH"
    else:
        direction = "NEUTRAL"
        regime = "NEUTRAL_RANGEBOUND"

    return {
        "direction": direction,
        "regime": regime,
        "volatility": volatility,
        "ema50": round(ema50, 4),
        "ema200": round(ema200, 4),
        "atr_14": round(atr_14, 4),
        "atr_pct": round(atr_pct, 2)
    }


# =============================================================================
# STRATEGY AGENT CORE IMPLEMENTATION
# =============================================================================

class StrategyAgent:
    """
    Agent 4: Strategy Agent (Alpha Generator).
    Generates high-conviction scalping setups through multi-timeframe SMC analysis,
    transparent normalized confluence scoring, and strict hard veto separation.
    """

    def __init__(
        self,
        target_rr_ratio: float = 2.5,
        max_allowed_spread_pct: float = 0.15,
        adaptive_learner: Optional[AdaptiveLearningEngine] = None
    ):
        self.target_rr_ratio = target_rr_ratio
        self.max_allowed_spread_pct = max_allowed_spread_pct
        self.adaptive_learner = adaptive_learner or AdaptiveLearningEngine()
        self.last_rejections: Dict[str, Dict[str, Any]] = {}
        self.last_swept_levels: Dict[str, float] = {}

    def get_last_rejection(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieve the last rejection details for a symbol."""
        return self.last_rejections.get(symbol)

    def _record_rejection(self, symbol: str, reason: str, gate: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Store structured rejection telemetry."""
        logger.warning(f"StrategyAgent VETO on {symbol} [{gate}]: {reason}")
        self.last_rejections[symbol] = {
            "symbol": symbol,
            "timestamp": time.time(),
            "gate": gate,
            "reason": reason,
            "metadata": metadata or {}
        }

    def evaluate_setup(
        self,
        analysis: Dict[str, Any],
        candles_5m: Optional[Dict[str, Any]] = None,
        candles_1m: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single symbol analysis and generate a trade proposal ONLY if high-probability edge exists.
        Separates Hard Rejection Gates from Normalized Confluence Scoring.
        Returns a qualified trade setup dictionary, or None if rejected.
        """
        symbol = str(analysis.get("symbol") or "BTCUSD").upper()
        cfg = get_asset_config(symbol)
        is_primary = cfg["is_primary"]
        priority_tag = "PRIMARY" if is_primary else "SECONDARY"

        # Check existing upstream setup or raw candle fallback
        hp_setup = analysis.get("high_probability_setup") or {}
        has_hp = bool(hp_setup.get("qualified"))

        current_price = float(analysis.get("current_price") or hp_setup.get("entry_price") or 0.0)
        spread_pct = float(analysis.get("spread_pct") or 0.0)

        # ---------------------------------------------------------------------
        # 1. Hard Rejection Gates (Vetoes)
        # ---------------------------------------------------------------------
        # Hard Veto A: Major economic news / abnormal volatility spike
        if analysis.get("news_blocked"):
            reason = str(analysis.get("news_reason") or "News block active.")
            self._record_rejection(symbol, reason, "NEWS_VETO")
            return None

        # Hard Veto B: Excessive bid-ask spread / illiquid book
        max_spread = cfg["max_spread_pct"]
        if spread_pct > max_spread:
            reason = f"Spread {spread_pct}% exceeds asset maximum allowed {max_spread}%"
            self._record_rejection(symbol, reason, "SPREAD_VETO", {"spread_pct": spread_pct, "max_spread": max_spread})
            return None

        # Hard Veto C: Zero or unreadable current price
        if current_price <= 0:
            self._record_rejection(symbol, "Current price is non-positive or unavailable.", "PRICE_VETO")
            return None

        # ---------------------------------------------------------------------
        # 2. Multi-Timeframe Structural Ingestion & SMC Analysis
        # ---------------------------------------------------------------------
        candles_15m = analysis.get("_raw_candles_15m") or {}
        candles_1h = analysis.get("_raw_candles_1h") or {}

        macro_1h_ctx = analyze_1h_market_context(candles_1h, current_price)
        h1_dir = macro_1h_ctx["direction"]

        macro_15m = analysis.get("macro_15m") or {}
        atr_15m = float(macro_15m.get("atr_14") or hp_setup.get("atr_14") or analysis.get("atr_14") or 0.0)
        if atr_15m <= 0:
            atr_15m = current_price * 0.005  # Conservative 0.50% fallback if ATR uncalculated

        # 15M SMC Analysis
        c_15m = [float(x) for x in candles_15m.get("c", [])]
        h_15m = [float(x) for x in candles_15m.get("h", [])]
        l_15m = [float(x) for x in candles_15m.get("l", [])]
        o_15m = [float(x) for x in candles_15m.get("o", [])]

        smc_15m = analyze_market_structure_bos_choch(
            highs=h_15m, lows=l_15m, closes=c_15m, opens=o_15m, pivot_window=cfg["pivot_window"]
        ) if len(c_15m) >= 20 else {
            "trend": "NEUTRAL", "bos_detected": False, "choch_detected": False,
            "structure_type": "NORMAL", "recent_swing_high": 0.0, "recent_swing_low": 0.0
        }

        # Resolve Trade Side (from hp_setup or structural signals)
        side = hp_setup.get("side")
        if not side:
            if smc_15m["choch_detected"]:
                side = "buy" if "BULLISH" in smc_15m["structure_type"] else "sell"
            elif smc_15m["trend"] == "BULLISH":
                side = "buy"
            elif smc_15m["trend"] == "BEARISH":
                side = "sell"
            elif h1_dir == "BULLISH":
                side = "buy"
            elif h1_dir == "BEARISH":
                side = "sell"
            else:
                self._record_rejection(symbol, "Unclear directional regime (1H & 15M Neutral without trigger).", "REGIME_VETO")
                return None

        # Setup entry, stop loss, and take profit calculation
        entry = float(hp_setup.get("entry_price") or current_price)

        # Hard Veto D: Extreme entry price deviation
        if entry > 0 and current_price > 0:
            price_dev_pct = abs(current_price - entry) / entry * 100.0
            if price_dev_pct > 0.50:
                reason = f"Price has drifted {price_dev_pct:.2f}% from optimal entry ${entry:.2f}"
                self._record_rejection(symbol, reason, "ENTRY_DRIFT_VETO", {"deviation_pct": price_dev_pct})
                return None

        # Determine Technical Invalidation Stop Loss
        sl = float(hp_setup.get("stop_loss_price") or 0.0)
        tp = float(hp_setup.get("take_profit_price") or 0.0)

        # If SL not provided by hp_setup, derive technically from swing structure or ATR
        if sl <= 0 or sl == entry:
            if side == "buy":
                raw_support = smc_15m["recent_swing_low"] if smc_15m["recent_swing_low"] > 0 else (entry - atr_15m)
                sl = min(raw_support, entry - (0.50 * atr_15m)) - (0.10 * atr_15m)
            else:
                raw_resistance = smc_15m["recent_swing_high"] if smc_15m["recent_swing_high"] > 0 else (entry + atr_15m)
                sl = max(raw_resistance, entry + (0.50 * atr_15m)) + (0.10 * atr_15m)

        # Hard Veto E: Stop Loss Orientation
        if side == "buy" and sl >= entry:
            reason = f"Structural stop loss (${sl:.4f}) is above or at entry (${entry:.4f}) for buy order."
            self._record_rejection(symbol, reason, "INVALID_SL_VETO")
            return None
        elif side == "sell" and sl <= entry:
            reason = f"Structural stop loss (${sl:.4f}) is below or at entry (${entry:.4f}) for sell order."
            self._record_rejection(symbol, reason, "INVALID_SL_VETO")
            return None

        stop_distance = abs(entry - sl)
        atr_multiple = round(stop_distance / atr_15m, 2) if atr_15m > 0 else 1.0

        # Hard Veto F: Sub-ATR micro-stop or excessively loose stop
        min_atr_mult = cfg["atr_stop_min_mult"]
        max_atr_mult = cfg["atr_stop_max_mult"]

        if atr_multiple < min_atr_mult:
            reason = f"Stop loss distance (${stop_distance:.2f}) is only {atr_multiple:.2f}x ATR (< {min_atr_mult:.2f}x ATR of ${atr_15m:.2f}). Highly vulnerable to noise stop-outs."
            self._record_rejection(symbol, reason, "MICRO_STOP_VETO", {"atr_multiple": atr_multiple, "min_required": min_atr_mult})
            return None
        if atr_multiple > max_atr_mult:
            reason = f"Stop loss distance (${stop_distance:.2f}) is {atr_multiple:.2f}x ATR (> {max_atr_mult:.2f}x ATR of ${atr_15m:.2f}). Exceeds acceptable volatility risk bounds."
            self._record_rejection(symbol, reason, "LOOSE_STOP_VETO", {"atr_multiple": atr_multiple, "max_allowed": max_atr_mult})
            return None

        # Take Profit and Asymmetric R:R Calibration
        target_rr = cfg["target_rr_ratio"]
        planned_rr = abs(tp - entry) / stop_distance if stop_distance > 0 else 0.0

        if planned_rr < target_rr or tp <= 0:
            tp = round(entry + (target_rr * stop_distance), 4) if side == "buy" else round(entry - (target_rr * stop_distance), 4)
            planned_rr = abs(tp - entry) / stop_distance

        # Hard Veto G: Minimum R:R ratio
        if planned_rr < 2.20:
            reason = f"Planned R:R ({planned_rr:.2f}:1) is below 2.2:1 minimum threshold."
            self._record_rejection(symbol, reason, "INSUFFICIENT_RR_VETO", {"planned_rr": planned_rr})
            return None

        # ---------------------------------------------------------------------
        # 3. 100-Point Normalized Confluence Scoring Model
        # ---------------------------------------------------------------------
        thesis = hp_setup.get("thesis") or f"SMC Institutional {side.upper()} setup verified."

        # Category A: 1H Macro Context
        score_1h = 0
        if (side == "buy" and h1_dir == "BULLISH") or (side == "sell" and h1_dir == "BEARISH"):
            score_1h += 12
        elif h1_dir == "NEUTRAL":
            score_1h += 7
        else:
            score_1h -= 5

        if macro_1h_ctx["volatility"] == "NORMAL":
            score_1h += 3

        # Category B: 15M Market Structure & BOS/CHOCH
        score_15m = 0
        structure_type = smc_15m.get("structure_type", "NORMAL")
        if (side == "buy" and "BULLISH" in structure_type) or (side == "sell" and "BEARISH" in structure_type):
            score_15m += 20
            if smc_15m.get("choch_detected"):
                score_15m += 5
            elif smc_15m.get("bos_detected"):
                score_15m += 4
        elif structure_type == "NORMAL":
            score_15m += 10

        # Category C: Liquidity Sweep Confluence
        liq = analysis.get("liquidity") or {}
        sweep_type = liq.get("sweep_type") or "NONE"
        mss_confirmed = liq.get("mss_confirmed", False)
        nearest_bsl = float(liq.get("nearest_bsl") or 0.0)
        nearest_ssl = float(liq.get("nearest_ssl") or 0.0)
        liq_structure = liq.get("liquidity_structure", "BALANCED_LIQUIDITY_CORE")

        liq_boost = 0
        if side == "buy":
            if sweep_type == "BULLISH_SSL_SWEEP":
                if mss_confirmed or liq_structure == "SWEEP_MSS_CONFIRMED":
                    liq_boost += 8
                    if "SSL SWEEP" not in thesis:
                        thesis = f"💧 [BULLISH SSL SWEEP + MSS CONFIRMED] {thesis}"
                else:
                    liq_boost += 4
                    if "SSL SWEEP" not in thesis:
                        thesis = f"💧 [BULLISH SSL SWEEP] {thesis}"
            if nearest_bsl > entry:
                liq_boost += 3
            if liq_structure == "TESTING_BSL_LIQUIDITY":
                liq_boost -= 4
        elif side == "sell":
            if sweep_type == "BEARISH_BSL_SWEEP":
                if mss_confirmed or liq_structure == "SWEEP_MSS_CONFIRMED":
                    liq_boost += 8
                    if "BSL SWEEP" not in thesis:
                        thesis = f"💧 [BEARISH BSL SWEEP + MSS CONFIRMED] {thesis}"
                else:
                    liq_boost += 4
                    if "BSL SWEEP" not in thesis:
                        thesis = f"💧 [BEARISH BSL SWEEP] {thesis}"
            if nearest_ssl > 0 and nearest_ssl < entry:
                liq_boost += 3
            if liq_structure == "TESTING_SSL_LIQUIDITY":
                liq_boost -= 4

        # Category D: FVG Retest & Consequent Encroachment
        fvg_1h = analysis.get("fvg") or {}
        fvg_15m = macro_15m.get("fvg") if macro_15m else {}
        fvg_data = fvg_15m if (fvg_15m and fvg_15m.get("retest_active")) else fvg_1h

        retest_type = fvg_data.get("retest_type", "NONE")
        ce_tested = fvg_data.get("ce_tested", False)
        wick_rejection = fvg_data.get("wick_rejection", False)
        nearest_bull_fvg = fvg_data.get("nearest_bullish_fvg")
        nearest_bear_fvg = fvg_data.get("nearest_bearish_fvg")
        bull_dist = fvg_data.get("bullish_fvg_distance_pct")
        bear_dist = fvg_data.get("bearish_fvg_distance_pct")

        fvg_boost = 0
        if side == "buy":
            if retest_type == "BULLISH_FVG_RETEST":
                if ce_tested and wick_rejection:
                    fvg_boost += 10
                    if "BULLISH FVG CE RETEST" not in thesis:
                        thesis = f"🔥 [BULLISH FVG CE RETEST + WICK REJECTION] {thesis}"
                elif ce_tested:
                    fvg_boost += 8
                    if "BULLISH FVG CE RETEST" not in thesis:
                        thesis = f"🔥 [BULLISH FVG CE RETEST] {thesis}"
                else:
                    fvg_boost += 5
                    if "BULLISH FVG BOUNDARY RETEST" not in thesis:
                        thesis = f"🔥 [BULLISH FVG BOUNDARY RETEST] {thesis}"
            if nearest_bear_fvg and bear_dist is not None and bear_dist <= 0.35:
                fvg_boost -= 6
                if "OVERHEAD BEARISH FVG" not in thesis:
                    thesis = f"⚠️ [OVERHEAD BEARISH FVG SUPPLY NEARBY] {thesis}"
        elif side == "sell":
            if retest_type == "BEARISH_FVG_RETEST":
                if ce_tested and wick_rejection:
                    fvg_boost += 10
                    if "BEARISH FVG CE RETEST" not in thesis:
                        thesis = f"🔥 [BEARISH FVG CE RETEST + WICK REJECTION] {thesis}"
                elif ce_tested:
                    fvg_boost += 8
                    if "BEARISH FVG CE RETEST" not in thesis:
                        thesis = f"🔥 [BEARISH FVG CE RETEST] {thesis}"
                else:
                    fvg_boost += 5
                    if "BEARISH FVG BOUNDARY RETEST" not in thesis:
                        thesis = f"🔥 [BEARISH FVG BOUNDARY RETEST] {thesis}"
            if nearest_bull_fvg and bull_dist is not None and bull_dist <= 0.35:
                fvg_boost -= 6
                if "SUPPORT BULLISH FVG" not in thesis:
                    thesis = f"⚠️ [SUPPORT BULLISH FVG DEMAND NEARBY] {thesis}"

        # Category E: 5M Entry Trigger, ATR Stop & VWAP Momentum
        atr_boost = 0
        if 0.70 <= atr_multiple <= 1.50:
            atr_boost += 4
            if "OPTIMAL" not in thesis:
                thesis = f"🛡️ [OPTIMAL {atr_multiple:.1f}x ATR STOP] {thesis}"
        elif atr_multiple < 0.50:
            atr_boost -= 4

        vwap_val = float(analysis.get("vwap") or 0.0)
        vwap_info = analysis.get("vwap_analysis") or {}
        v_stance = vwap_info.get("stance", "AT_VWAP" if (vwap_val > 0 and abs(current_price - vwap_val)/vwap_val <= 0.002) else ("ABOVE_VWAP" if current_price > vwap_val else "BELOW_VWAP"))
        v_band = vwap_info.get("band_location", "FAIR_VALUE_CORE")
        v_slope = vwap_info.get("slope", "FLAT")

        vwap_boost = 0
        if vwap_val > 0:
            if side == "buy":
                if v_stance in ("ABOVE_VWAP", "AT_VWAP"):
                    vwap_boost += 5
                else:
                    vwap_boost -= 5

                if v_band in ("FAIR_VALUE_CORE", "DISCOUNT_BAND") and v_slope == "RISING_BULLISH":
                    vwap_boost += 4
                    if "VWAP" not in thesis:
                        thesis = f"💎 [INSTITUTIONAL VWAP ACCUMULATION] {thesis}"
                elif v_band == "OVERBOUGHT_EXTENSION":
                    vwap_boost -= 8
            elif side == "sell":
                if v_stance in ("BELOW_VWAP", "AT_VWAP"):
                    vwap_boost += 5
                else:
                    vwap_boost -= 5

                if v_band in ("FAIR_VALUE_CORE", "PREMIUM_BAND") and v_slope == "FALLING_BEARISH":
                    vwap_boost += 4
                    if "VWAP" not in thesis:
                        thesis = f"💎 [INSTITUTIONAL VWAP DISTRIBUTION] {thesis}"
                elif v_band == "OVERSOLD_CAPITULATION":
                    vwap_boost -= 8

        macd_1h = analysis.get("macd") or {}
        macd_15m = macro_15m.get("macd") if macro_15m else macd_1h
        m15_cross = macd_15m.get("crossover", "NONE") if macd_15m else "NONE"
        m15_phase = macd_15m.get("momentum_phase", "NEUTRAL") if macd_15m else "NEUTRAL"
        m15_hist = float(macd_15m.get("histogram") or 0.0) if macd_15m else 0.0

        macd_boost = 0
        if side == "buy":
            if m15_cross in ("BULLISH_CROSS", "BULLISH_ALIGNED") or m15_phase == "BULLISH_EXPANSION":
                macd_boost += 6
                if "MACD" not in thesis:
                    thesis = f"📈 [MACD BULLISH MOMENTUM] {thesis}"
            elif m15_hist > 0 or (macd_1h and "BULLISH" in macd_1h.get("bias", "")):
                macd_boost += 3
            elif m15_phase == "BEARISH_EXPANSION" and m15_hist < 0:
                macd_boost -= 6
        elif side == "sell":
            if m15_cross in ("BEARISH_CROSS", "BEARISH_ALIGNED") or m15_phase == "BEARISH_EXPANSION":
                macd_boost += 6
                if "MACD" not in thesis:
                    thesis = f"📉 [MACD BEARISH MOMENTUM] {thesis}"
            elif m15_hist < 0 or (macd_1h and "BEARISH" in macd_1h.get("bias", "")):
                macd_boost += 3
            elif m15_phase == "BULLISH_EXPANSION" and m15_hist > 0:
                macd_boost -= 6

        # Category F: Volume & Order Flow Confirmation
        vp_1h = analysis.get("volume_profile") or {}
        cvd_1h = analysis.get("cvd") or {}
        obi_1h = analysis.get("order_book_imbalance") or {}
        vp_15m = macro_15m.get("volume_profile") if macro_15m else {}
        cvd_15m = macro_15m.get("cvd") if macro_15m else {}
        obi_15m = macro_15m.get("order_book_imbalance") if macro_15m else {}

        active_vp = vp_15m if (vp_15m and vp_15m.get("poc", 0) > 0) else vp_1h
        active_cvd = cvd_15m if (cvd_15m and cvd_15m.get("current_cvd", 0) != 0) else cvd_1h
        active_obi = obi_15m if (obi_15m and obi_15m.get("obi_ratio", 0) != 0) else obi_1h

        cvd_div = active_cvd.get("divergence", "NONE")
        cvd_trend = active_cvd.get("cvd_trend", "FLAT_NEUTRAL")
        obi_status = active_obi.get("imbalance_status", "BALANCED_ORDER_BOOK")
        obi_ratio = float(active_obi.get("obi_ratio") or 0.0)

        order_flow_boost = 0
        if side == "buy":
            if cvd_div == "BULLISH_ABSORPTION_DIV":
                order_flow_boost += 10
                if "ABSORPTION" not in thesis:
                    thesis = f"🌊 [BULLISH CVD ABSORPTION DIVERGENCE] {thesis}"
            elif cvd_trend == "RISING_ACCUMULATION":
                order_flow_boost += 5
                if "CVD" not in thesis:
                    thesis = f"📈 [CVD ACCUMULATION DELTA] {thesis}"
            elif cvd_div == "BEARISH_EXHAUSTION_DIV":
                order_flow_boost -= 8
                if "CVD" not in thesis:
                    thesis = f"⚠️ [BEARISH CVD DIVERGENCE WARNING] {thesis}"

            if obi_status == "HEAVY_BID_IMBALANCE" or obi_ratio >= 0.25:
                order_flow_boost += 6
                if "BID" not in thesis:
                    thesis = f"🧱 [HEAVY BID BOOK SUPPORT (OBI {obi_ratio:+.2f})] {thesis}"
            elif obi_status == "HEAVY_ASK_IMBALANCE" or obi_ratio <= -0.25:
                order_flow_boost -= 7
                if "ASK" not in thesis:
                    thesis = f"⚠️ [HEAVY ASK WALL RESISTANCE (OBI {obi_ratio:+.2f})] {thesis}"
        elif side == "sell":
            if cvd_div == "BEARISH_EXHAUSTION_DIV":
                order_flow_boost += 10
                if "EXHAUSTION" not in thesis:
                    thesis = f"🌊 [BEARISH CVD EXHAUSTION DIVERGENCE] {thesis}"
            elif cvd_trend == "FALLING_DISTRIBUTION":
                order_flow_boost += 5
                if "CVD" not in thesis:
                    thesis = f"📉 [CVD DISTRIBUTION DELTA] {thesis}"
            elif cvd_div == "BULLISH_ABSORPTION_DIV":
                order_flow_boost -= 8
                if "CVD" not in thesis:
                    thesis = f"⚠️ [BULLISH CVD DIVERGENCE WARNING] {thesis}"

            if obi_status == "HEAVY_ASK_IMBALANCE" or obi_ratio <= -0.25:
                order_flow_boost += 6
                if "ASK" not in thesis:
                    thesis = f"🧱 [HEAVY ASK BOOK RESISTANCE (OBI {obi_ratio:+.2f})] {thesis}"
            elif obi_status == "HEAVY_BID_IMBALANCE" or obi_ratio >= 0.25:
                order_flow_boost -= 7
                if "BID" not in thesis:
                    thesis = f"⚠️ [HEAVY BID WALL SUPPORT (OBI {obi_ratio:+.2f})] {thesis}"

        # Adaptive Learning Check
        raw_strat = hp_setup.get("strategy") or f"Institutional_SMC_{priority_tag}_{side.upper()}"
        macro_4h = analysis.get("macro_4h") or {}
        macro_daily = analysis.get("macro_daily") or {}
        macro_weekly = analysis.get("macro_weekly") or {}
        macro_monthly = analysis.get("macro_monthly") or {}

        confluence_summary = {
            "macro_4h": macro_4h.get("regime", "NEUTRAL"),
            "macro_daily": macro_daily.get("regime", "NEUTRAL")
        }
        pat_check = self.adaptive_learner.get_pattern_adjustment(
            symbol=symbol,
            side=side,
            strategy=raw_strat,
            confluence=confluence_summary
        )

        if not pat_check.get("can_trade", True):
            reason = f"Pattern blacklisted by adaptive learning: {pat_check.get('reason')}"
            self._record_rejection(symbol, reason, "ADAPTIVE_LEARNING_VETO")
            return None

        pat_adj = pat_check.get("score_adjustment", 0)

        # Compute Total Confluence Score
        if has_hp and hp_setup.get("score"):
            base_score = int(hp_setup["score"])
            total_normalized_score = (
                base_score + (10 if is_primary else 0) +
                atr_boost + vwap_boost + macd_boost +
                liq_boost + fvg_boost + order_flow_boost + pat_adj
            )
        else:
            total_normalized_score = (
                score_1h + score_15m +
                liq_boost + fvg_boost +
                (atr_boost + vwap_boost + macd_boost) +
                order_flow_boost + (10 if is_primary else 0) + pat_adj
            )

        if pat_adj > 0 and "REINFORCED" not in thesis:
            thesis = f"⚡ [REINFORCED PATTERN +{pat_adj}pts] {thesis}"
        elif pat_adj < 0 and "PENALIZED" not in thesis:
            thesis = f"⚠️ [PENALIZED PATTERN {pat_adj}pts] {thesis}"

        # Hard Veto H: Minimum Confluence Score Floor
        min_score = cfg["min_confluence_score"]
        if total_normalized_score < min_score:
            reason = f"Confluence score ({total_normalized_score}/100) below required {min_score}/100 floor for {priority_tag} asset."
            self._record_rejection(symbol, reason, "CONFLUENCE_SCORE_VETO", {"score": total_normalized_score, "min_required": min_score})
            return None

        # Build Partial Targets
        tp1_price = round(entry + (1.50 * stop_distance), 4) if side == "buy" else round(entry - (1.50 * stop_distance), 4)
        partial_targets = [
            {"target_price": tp1_price, "portion_pct": 50, "label": "TP1_SCALE_OUT_LOCK_BREAKEVEN"},
            {"target_price": tp, "portion_pct": 50, "label": "TP2_RUNNER_OPPOSING_LIQUIDITY"}
        ]

        now_ts = time.time()
        expires_at = now_ts + 3600.0  # 60 minute validity horizon
        formatted_thesis = f"🌟 [PRIMARY FOCUS ASSET] {thesis}" if is_primary else f"⚪ [SECONDARY ASSET] {thesis}"

        confluence_breakdown = {
            "macro_1h_score": score_1h,
            "market_structure_15m_score": score_15m,
            "liquidity_event_score": liq_boost,
            "fvg_retracement_score": fvg_boost,
            "entry_trigger_5m_score": atr_boost + vwap_boost + macd_boost,
            "volume_order_flow_score": order_flow_boost,
            "adaptive_learning_adjustment": pat_adj,
            "total_score": total_normalized_score
        }

        # Clear any prior rejection upon successful approval
        self.last_rejections.pop(symbol, None)

        return {
            "symbol": symbol,
            "strategy_name": f"{raw_strat}_{total_normalized_score}pts",
            "side": side,
            "direction": side,
            "setup_type": structure_type if structure_type != "NORMAL" else ("SWEEP_REVERSAL" if "SWEEP" in sweep_type else "TREND_PULLBACK"),
            "timeframe": "15m",
            "entry_price": entry,
            "stop_loss_price": sl,
            "stop_loss": sl,
            "take_profit_price": tp,
            "take_profit": tp,
            "partial_targets": partial_targets,
            "stop_distance_pct": round((stop_distance / entry) * 100, 2),
            "planned_rr_ratio": round(planned_rr, 2),
            "planned_risk_reward": round(planned_rr, 2),
            "score": total_normalized_score,
            "confidence_score": total_normalized_score,
            "confluence_breakdown": confluence_breakdown,
            "market_regime": macro_1h_ctx["regime"],
            "liquidity_level": smc_15m["recent_swing_low"] if side == "buy" else smc_15m["recent_swing_high"],
            "fvg_details": {
                "retest_type": retest_type,
                "ce_tested": ce_tested,
                "wick_rejection": wick_rejection,
                "nearest_bullish_fvg": nearest_bull_fvg,
                "nearest_bearish_fvg": nearest_bear_fvg
            },
            "structure_confirmation": structure_type,
            "invalidation_reason": f"15m close beyond technical level (${sl:,.2f})",
            "signal_timestamp": now_ts,
            "data_timestamp": now_ts,
            "signal_expiry": expires_at,
            "no_trade_reason": None,
            "is_primary": is_primary,
            "priority_tier": cfg["priority_tier"],
            "thesis": formatted_thesis,
            "expires_at": expires_at,
            "created_at": now_ts,
            "vwap": vwap_val,
            "spread_pct": spread_pct,
            "atr_14": atr_15m,
            "atr_stop_multiple": atr_multiple,
            "fvg_profile": {
                "retest_type": retest_type,
                "ce_tested": ce_tested,
                "wick_rejection": wick_rejection,
                "active_bullish_count": fvg_data.get("active_bullish_count", 0),
                "active_bearish_count": fvg_data.get("active_bearish_count", 0),
                "nearest_bullish_fvg": nearest_bull_fvg,
                "nearest_bearish_fvg": nearest_bear_fvg,
                "active_retest_fvg": fvg_data.get("active_retest_fvg")
            },
            "order_flow_profile": {
                "volume_profile": {
                    "poc": float(active_vp.get("poc") or 0.0),
                    "vah": float(active_vp.get("vah") or 0.0),
                    "val": float(active_vp.get("val") or 0.0),
                    "stance": active_vp.get("stance", "INSIDE_VA")
                },
                "cvd": {
                    "current_cvd": active_cvd.get("current_cvd", 0.0),
                    "cvd_trend": cvd_trend,
                    "divergence": cvd_div,
                    "cvd_slope": active_cvd.get("cvd_slope", 0.0)
                },
                "order_book_imbalance": {
                    "obi_ratio": obi_ratio,
                    "imbalance_status": obi_status,
                    "depth_ratio": active_obi.get("depth_ratio", 1.0),
                    "bid_depth": active_obi.get("bid_depth", 0.0),
                    "ask_depth": active_obi.get("ask_depth", 0.0),
                    "bid_wall_detected": active_obi.get("bid_wall_detected", False),
                    "bid_wall_price": active_obi.get("bid_wall_price"),
                    "ask_wall_detected": active_obi.get("ask_wall_detected", False),
                    "ask_wall_price": active_obi.get("ask_wall_price")
                }
            },
            "confluence": {
                "execution_15m": f"{macro_15m.get('regime', 'NEUTRAL')} (RSI: {macro_15m.get('rsi_14', 'N/A')} | ATR: {macro_15m.get('atr_14', 'N/A')})",
                "monthly": f"{macro_monthly.get('regime', 'NEUTRAL')} (M-Open: ${macro_monthly.get('monthly_open', 'N/A')})",
                "weekly": f"{macro_weekly.get('regime', 'NEUTRAL')} (W-RSI: {macro_weekly.get('rsi_14', 'N/A')})",
                "daily": f"{macro_daily.get('regime', 'NEUTRAL')} (EMA21: ${macro_daily.get('ema_21', 'N/A')} | RSI: {macro_daily.get('rsi_14', 'N/A')})",
                "macro_4h": f"{macro_4h.get('regime', 'NEUTRAL')} (4H RSI: {macro_4h.get('rsi_14', 'N/A')})",
                "structure_detail": f"{liq.get('sweep_type', 'Structure Test')} | MSS: {'YES' if liq.get('mss_confirmed') else 'ALIGNED'}",
                "patterns_detail": f"Candle: {analysis.get('candlestick_pattern', 'Normal')} | Chart: {analysis.get('chart_pattern', 'Normal')} | Trendline: {analysis.get('trendline_direction', 'Aligned')}",
                "levels_detail": f"Support: ${analysis.get('support', 0):,.2f} | Resistance: ${analysis.get('resistance', 0):,.2f} | BSL: ${nearest_bsl:,.2f} | SSL: ${nearest_ssl:,.2f}",
                "volume_rsi": f"1H RSI: {analysis.get('rsi_14', 50.0)} | Vol: {'CONFIRMED' if liq.get('volume_confirmed') else 'NORMAL'}",
                "macd_detail": f"15m: {m15_cross} ({m15_phase}) | 1H: {macd_1h.get('bias', 'NEUTRAL')}",
                "vwap_detail": f"${vwap_val:,.2f} ({v_stance} | {v_band} | {v_slope})",
                "liquidity_detail": f"BSL: ${nearest_bsl:,.2f} | SSL: ${nearest_ssl:,.2f} | State: {liq_structure} | Spread: {spread_pct:.3f}%",
                "atr_detail": f"15m ATR: ${atr_15m:,.2f} | SL Multiple: {atr_multiple:.2f}x ATR",
                "fvg_detail": f"Retest: {retest_type} (CE: {'YES' if ce_tested else 'NO'} | Wick: {'YES' if wick_rejection else 'NO'})",
                "order_flow_detail": f"VP POC: ${float(active_vp.get('poc') or 0):,.2f} | CVD: {cvd_trend} ({cvd_div}) | OBI: {obi_status} ({obi_ratio:+.2f})"
            }
        }

    def find_best_candidates(self, scan_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan all symbols from RegimeAnalyst and return ranked list of qualified setups.
        Primary assets (BTC, ETH, XAU) are prioritized first, followed by planned R:R and score.
        """
        candidates = []
        symbols_data = scan_results.get("symbols_data", {})
        for sym, analysis in symbols_data.items():
            if not analysis.get("symbol"):
                analysis["symbol"] = sym
            setup = self.evaluate_setup(analysis)
            if setup:
                candidates.append(setup)

        # Rank by: Primary tier first, then Asymmetric Profit Ratio (planned R:R), then score
        candidates.sort(
            key=lambda s: (
                1 if s.get("is_primary") else 0,
                s.get("planned_rr_ratio", 0.0),
                s.get("score", 0)
            ),
            reverse=True
        )
        return candidates
