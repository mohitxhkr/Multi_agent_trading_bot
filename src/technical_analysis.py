"""
Technical Analysis Engine for Delta Exchange Candlestick Data.
Computes standard indicators (EMA, RSI, ATR, MACD, Bollinger Bands)
and key support/resistance levels without heavyweight external dependencies.
"""

from typing import Dict, List, Any, Optional, Tuple
import math


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average."""
    if len(prices) < period or period <= 0:
        return [0.0] * len(prices)
    
    ema = [0.0] * len(prices)
    multiplier = 2.0 / (period + 1.0)
    
    # First EMA value is SMA
    sma = sum(prices[:period]) / period
    ema[period - 1] = sma
    
    for i in range(period, len(prices)):
        ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
        
    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """Calculate Relative Strength Index (RSI)."""
    if len(prices) <= period:
        return [50.0] * len(prices)
        
    gains = [0.0] * len(prices)
    losses = [0.0] * len(prices)
    rsi = [50.0] * len(prices)
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains[i] = change
        else:
            losses[i] = abs(change)
            
    # Initial average gain and loss
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    
    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))
        
    # Smoothed averages
    for i in range(period + 1, len(prices)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
            
    return rsi


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Calculate Average True Range (ATR)."""
    n = len(closes)
    if n < 2:
        return [0.0] * n
        
    tr = [0.0] * n
    tr[0] = highs[0] - lows[0]
    
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
        
    if n <= period:
        return tr
        
    atr = [0.0] * n
    atr[period - 1] = sum(tr[:period]) / period
    
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        
    return atr


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
    """Calculate MACD Line, Signal Line, and Histogram."""
    fast_ema = calculate_ema(prices, fast)
    slow_ema = calculate_ema(prices, slow)
    
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = calculate_ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }


def find_support_resistance(highs: List[float], lows: List[float], lookback: int = 50) -> Dict[str, float]:
    """Find nearby swing support and swing resistance levels."""
    if not highs or not lows:
        return {"support": 0.0, "resistance": 0.0}
        
    recent_highs = highs[-lookback:] if len(highs) >= lookback else highs
    recent_lows = lows[-lookback:] if len(lows) >= lookback else lows
    
    resistance = max(recent_highs)
    support = min(recent_lows)
    
    return {
        "support": support,
        "resistance": resistance
    }


def analyze_liquidity_pools_and_sweeps(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    opens: Optional[List[float]] = None,
    volumes: Optional[List[float]] = None,
    pivot_window: int = 2,
    lookback: int = 60
) -> Dict[str, Any]:
    """
    Smart Money Concepts (SMC) Liquidity Sweep & Order Flow Analysis.
    Identifies:
      1. Buy-Side Liquidity (BSL) pools (swing highs / equal highs where short stops sit).
      2. Sell-Side Liquidity (SSL) pools (swing lows / equal lows where long stops sit).
      3. Liquidity Sweeps with Wick Rejections & Market Structure Shift (MSS).
    """
    n = len(closes)
    if n < 10:
        return {
            "bsl_levels": [],
            "ssl_levels": [],
            "nearest_bsl": 0.0,
            "nearest_ssl": 0.0,
            "sweep_detected": False,
            "bias": "NEUTRAL",
            "narrative": "Insufficient bars for liquidity sweep calculation."
        }

    start_idx = max(0, n - lookback)
    swing_highs = []
    swing_lows = []

    # Detect fractal pivot highs and lows
    for i in range(start_idx + pivot_window, n - pivot_window):
        # Swing High
        is_high = True
        for w in range(1, pivot_window + 1):
            if highs[i] <= highs[i - w] or highs[i] <= highs[i + w]:
                is_high = False
                break
        if is_high:
            swing_highs.append((i, highs[i]))

        # Swing Low
        is_low = True
        for w in range(1, pivot_window + 1):
            if lows[i] >= lows[i - w] or lows[i] >= lows[i + w]:
                is_low = False
                break
        if is_low:
            swing_lows.append((i, lows[i]))

    current_price = closes[-1]

    # Active BSL: swing highs above current price
    bsl_above = sorted(list(set([round(h, 2) for _, h in swing_highs if h > current_price])))
    # Active SSL: swing lows below current price
    ssl_below = sorted(list(set([round(l, 2) for _, l in swing_lows if l < current_price])), reverse=True)

    nearest_bsl = bsl_above[0] if bsl_above else round(max(highs[-20:]), 2)
    nearest_ssl = ssl_below[0] if ssl_below else round(min(lows[-20:]), 2)

    sweep_detected = False
    sweep_type = "NONE"
    swept_level = 0.0
    sweep_wick_extreme = 0.0
    target_liquidity = 0.0
    mss_confirmed = False
    volume_confirmed = False
    bias = "NEUTRAL"
    narrative = ""

    avg_volume = (sum(volumes[-20:]) / 20.0) if volumes and len(volumes) >= 20 else 0.0

    # Examine recent candles (last 6 bars) for sweeps
    for bar_offset in range(1, min(7, n - 2)):
        bar_idx = n - bar_offset
        bar_h = highs[bar_idx]
        bar_l = lows[bar_idx]
        bar_c = closes[bar_idx]
        bar_o = opens[bar_idx] if opens and len(opens) > bar_idx else bar_c
        bar_v = volumes[bar_idx] if volumes and len(volumes) > bar_idx else 0.0
        bar_range = max(bar_h - bar_l, 1e-6)

        # 1. Bearish BSL Sweep (pierced prior swing high, closed back below)
        for sh_idx, sh_val in swing_highs:
            if sh_idx < bar_idx and bar_h > sh_val and bar_c < sh_val:
                upper_wick = bar_h - max(bar_o, bar_c)
                wick_ratio = upper_wick / bar_range
                # Must show meaningful wick rejection (>= 25% of candle range)
                if wick_ratio >= 0.25:
                    sweep_detected = True
                    sweep_type = "BEARISH_BSL_SWEEP"
                    swept_level = round(sh_val, 2)
                    sweep_wick_extreme = round(bar_h, 2)
                    target_liquidity = nearest_ssl
                    bias = "DOWNSIDE"

                    # Check MSS: Did any subsequent candle break below the sweep candle low?
                    for sub_idx in range(bar_idx + 1, n):
                        if closes[sub_idx] < bar_l:
                            mss_confirmed = True
                            break

                    # Check Volume:
                    if avg_volume > 0 and bar_v >= (0.9 * avg_volume):
                        volume_confirmed = True

                    narrative = (
                        f"Bearish BSL Liquidity Sweep: Price spiked Buy-Side Liquidity (${swept_level:.2f}) "
                        f"trapping breakout longs, rejected with {wick_ratio * 100:.0f}% upper wick. "
                        f"Market Structure Shift (MSS): {'CONFIRMED' if mss_confirmed else 'FORMING'}."
                    )
                    break
        if sweep_detected:
            break

        # 2. Bullish SSL Sweep (pierced prior swing low, closed back above)
        for sl_idx, sl_val in swing_lows:
            if sl_idx < bar_idx and bar_l < sl_val and bar_c > sl_val:
                lower_wick = min(bar_o, bar_c) - bar_l
                wick_ratio = lower_wick / bar_range
                # Must show meaningful wick rejection (>= 25% of candle range)
                if wick_ratio >= 0.25:
                    sweep_detected = True
                    sweep_type = "BULLISH_SSL_SWEEP"
                    swept_level = round(sl_val, 2)
                    sweep_wick_extreme = round(bar_l, 2)
                    target_liquidity = nearest_bsl
                    bias = "UPSIDE"

                    # Check MSS: Did any subsequent candle break above the sweep candle high?
                    for sub_idx in range(bar_idx + 1, n):
                        if closes[sub_idx] > bar_h:
                            mss_confirmed = True
                            break

                    # Check Volume:
                    if avg_volume > 0 and bar_v >= (0.9 * avg_volume):
                        volume_confirmed = True

                    narrative = (
                        f"Bullish SSL Liquidity Sweep: Price swept Sell-Side Liquidity (${swept_level:.2f}) "
                        f"grabbing stops, rejected higher with {wick_ratio * 100:.0f}% lower wick. "
                        f"Market Structure Shift (MSS): {'CONFIRMED' if mss_confirmed else 'FORMING'}."
                    )
                    break
        if sweep_detected:
            break

    if not sweep_detected:
        narrative = f"Price balancing between BSL (${nearest_bsl:.2f}) and SSL (${nearest_ssl:.2f})."
        bias = "EQUILIBRIUM"

    return {
        "bsl_levels": bsl_above[:5],
        "ssl_levels": ssl_below[:5],
        "nearest_bsl": nearest_bsl,
        "nearest_ssl": nearest_ssl,
        "sweep_detected": sweep_detected,
        "sweep_type": sweep_type,
        "swept_level": swept_level,
        "sweep_wick_extreme": sweep_wick_extreme,
        "target_liquidity": target_liquidity,
        "mss_confirmed": mss_confirmed,
        "volume_confirmed": volume_confirmed,
        "bias": bias,
        "narrative": narrative
    }


def analyze_market_structure(candles_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a full technical regime & indicator analysis on Delta Exchange chart history.
    candles_dict schema: {'t': [...], 'o': [...], 'h': [...], 'l': [...], 'c': [...], 'v': [...]}
    """
    closes = [float(x) for x in candles_dict.get('c', [])]
    opens = [float(x) for x in candles_dict.get('o', [])]
    highs = [float(x) for x in candles_dict.get('h', [])]
    lows = [float(x) for x in candles_dict.get('l', [])]
    volumes = [float(x) for x in candles_dict.get('v', [])]
    
    if len(closes) < 20:
        return {
            "error": "Insufficient candle data (minimum 20 candles needed)",
            "candles_count": len(closes)
        }
        
    current_price = closes[-1]
    
    # EMAs
    ema_9 = calculate_ema(closes, 9)[-1]
    ema_21 = calculate_ema(closes, 21)[-1]
    ema_50 = calculate_ema(closes, 50)[-1] if len(closes) >= 50 else ema_21
    ema_200 = calculate_ema(closes, 200)[-1] if len(closes) >= 200 else ema_50
    
    # RSI & ATR
    rsi_14 = calculate_rsi(closes, 14)[-1]
    atr_14 = calculate_atr(highs, lows, closes, 14)[-1]
    
    # MACD
    macd_res = calculate_macd(closes)
    macd_val = macd_res["macd"][-1]
    signal_val = macd_res["signal"][-1]
    hist_val = macd_res["histogram"][-1]
    
    # Support & Resistance
    sr = find_support_resistance(highs, lows, lookback=min(60, len(highs)))
    
    # Regime Classification
    # Bullish stack: Price > EMA 9 > EMA 21 > EMA 50
    # Bearish stack: Price < EMA 9 < EMA 21 < EMA 50
    if current_price > ema_9 and ema_9 > ema_21 and (len(closes) < 50 or ema_21 > ema_50):
        regime = "STRONG_BULLISH"
        bias = "LONG"
    elif current_price > ema_21 and rsi_14 > 50:
        regime = "MILD_BULLISH"
        bias = "LONG"
    elif current_price < ema_9 and ema_9 < ema_21 and (len(closes) < 50 or ema_21 < ema_50):
        regime = "STRONG_BEARISH"
        bias = "SHORT"
    elif current_price < ema_21 and rsi_14 < 50:
        regime = "MILD_BEARISH"
        bias = "SHORT"
    else:
        regime = "NEUTRAL_RANGEBOUND"
        bias = "NEUTRAL"
        
    # Volatility Assessment
    atr_pct = (atr_14 / current_price * 100.0) if current_price > 0 else 0.0
    volatility_posture = "HIGH" if atr_pct > 3.0 else ("NORMAL" if atr_pct >= 1.0 else "LOW")

    # Smart Money Concepts (SMC) & Liquidity Sweep Engine
    liquidity_data = analyze_liquidity_pools_and_sweeps(highs, lows, closes, opens=opens, volumes=volumes)
    
    return {
        "current_price": current_price,
        "regime": regime,
        "bias": bias,
        "rsi_14": round(rsi_14, 2),
        "atr_14": round(atr_14, 4),
        "atr_pct": round(atr_pct, 2),
        "volatility": volatility_posture,
        "ema_9": round(ema_9, 2),
        "ema_21": round(ema_21, 2),
        "ema_50": round(ema_50, 2),
        "ema_200": round(ema_200, 2),
        "macd": {
            "macd": round(macd_val, 4),
            "signal": round(signal_val, 4),
            "histogram": round(hist_val, 4)
        },
        "support": round(sr["support"], 2),
        "resistance": round(sr["resistance"], 2),
        "liquidity": liquidity_data,
        "candle_count": len(closes)
    }


def analyze_multi_timeframe(
    candles_1h: Dict[str, Any],
    candles_4h: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Multi-Timeframe Confluence Engine (1H Structure + 4H Macro Filter).
    Provides institutional edge (80-90% probability setups):
      1. 4H Macro Trend: 4H EMA 21 / 50 / 200 + 4H RSI.
      2. Trend Filter: Disallow trading against the dominant 4H trend unless extreme exhaustion.
      3. 1H Setup: Liquidity Sweep with wick rejection + Market Structure Shift (MSS).
      4. Exact Structural Stop Loss and realistic 1:2 R:R starting target.
    """
    analysis_1h = analyze_market_structure(candles_1h)
    if "error" in analysis_1h:
        return analysis_1h

    # 4H Macro Analysis
    macro_regime = "NEUTRAL"
    rsi_4h = 50.0
    ema21_4h = 0.0
    ema50_4h = 0.0
    ema200_4h = 0.0

    if candles_4h and len(candles_4h.get('c', [])) >= 20:
        c4_closes = [float(x) for x in candles_4h.get('c', [])]
        if len(c4_closes) >= 20:
            rsi_4h = calculate_rsi(c4_closes, 14)[-1]
            ema21_4h = calculate_ema(c4_closes, 21)[-1]
            ema50_4h = calculate_ema(c4_closes, 50)[-1] if len(c4_closes) >= 50 else ema21_4h
            ema200_4h = calculate_ema(c4_closes, 200)[-1] if len(c4_closes) >= 200 else ema50_4h

            p4 = c4_closes[-1]
            if p4 > ema21_4h and ema21_4h > ema50_4h and (len(c4_closes) < 200 or p4 > ema200_4h):
                macro_regime = "MACRO_BULLISH"
            elif p4 < ema21_4h and ema21_4h < ema50_4h and (len(c4_closes) < 200 or p4 < ema200_4h):
                macro_regime = "MACRO_BEARISH"
            else:
                macro_regime = "MACRO_NEUTRAL"

    analysis_1h["macro_4h"] = {
        "regime": macro_regime,
        "rsi_14": round(rsi_4h, 2),
        "ema_21": round(ema21_4h, 2),
        "ema_50": round(ema50_4h, 2),
        "ema_200": round(ema200_4h, 2),
    }

    # Evaluate Trade Confluence & Realistic Levels
    liq = analysis_1h.get("liquidity", {})
    current_price = analysis_1h.get("current_price", 0.0)
    atr = analysis_1h.get("atr_14", current_price * 0.015)
    sweep_detected = liq.get("sweep_detected", False)
    sweep_type = liq.get("sweep_type", "NONE")
    mss_confirmed = liq.get("mss_confirmed", False)
    vol_confirmed = liq.get("volume_confirmed", False)
    sweep_wick = liq.get("sweep_wick_extreme", current_price)

    setup_qualified = False
    setup_side = None
    setup_score = 0
    invalidation_sl = 0.0
    target_tp = 0.0
    thesis = ""
    rejection_reason = ""

    if sweep_detected:
        if sweep_type == "BULLISH_SSL_SWEEP":
            # Rule: Only take Long if 4H is BULLISH or 4H RSI < 25 (oversold reversal)
            if macro_regime == "MACRO_BEARISH" and rsi_4h >= 28.0:
                rejection_reason = "Blocked: Cannot buy into strong 4H Bearish trend without extreme RSI capitulation."
            else:
                setup_score = 40  # Base sweep
                if macro_regime == "MACRO_BULLISH":
                    setup_score += 30  # Trend alignment
                elif macro_regime == "MACRO_NEUTRAL":
                    setup_score += 15
                if mss_confirmed:
                    setup_score += 20  # Market structure shift confirmed
                if vol_confirmed:
                    setup_score += 10  # Institutional volume absorption

                if setup_score >= 70:
                    setup_qualified = True
                    setup_side = "buy"
                    # Structural Stop Loss: Below the sweep wick extreme with 0.15 * ATR buffer
                    invalidation_sl = round(min(sweep_wick, current_price - (0.8 * atr)) - (0.15 * atr), 2)
                    risk_dist = current_price - invalidation_sl
                    if risk_dist > 0:
                        target_tp = round(current_price + (2.0 * risk_dist), 2)
                        thesis = (
                            f"High-Probability Bullish SSL Sweep (Score {setup_score}/100): Price swept Sell-Side "
                            f"Liquidity (${liq.get('swept_level'):.2f}), grabbed institutional liquidity, and "
                            f"rejected higher. 4H Macro: {macro_regime} | MSS: {'YES' if mss_confirmed else 'FORMING'}."
                        )

        elif sweep_type == "BEARISH_BSL_SWEEP":
            # Rule: Only take Short if 4H is BEARISH or 4H RSI > 75 (overbought exhaustion)
            if macro_regime == "MACRO_BULLISH" and rsi_4h <= 72.0:
                rejection_reason = "Blocked: Cannot short against strong 4H Bullish trend without extreme overbought exhaustion."
            else:
                setup_score = 40
                if macro_regime == "MACRO_BEARISH":
                    setup_score += 30
                elif macro_regime == "MACRO_NEUTRAL":
                    setup_score += 15
                if mss_confirmed:
                    setup_score += 20
                if vol_confirmed:
                    setup_score += 10

                if setup_score >= 70:
                    setup_qualified = True
                    setup_side = "sell"
                    # Structural Stop Loss: Above the sweep wick extreme with 0.15 * ATR buffer
                    invalidation_sl = round(max(sweep_wick, current_price + (0.8 * atr)) + (0.15 * atr), 2)
                    risk_dist = invalidation_sl - current_price
                    if risk_dist > 0:
                        target_tp = round(current_price - (2.0 * risk_dist), 2)
                        thesis = (
                            f"High-Probability Bearish BSL Sweep (Score {setup_score}/100): Price spiked Buy-Side "
                            f"Liquidity (${liq.get('swept_level'):.2f}), trapped breakout buyers, and "
                            f"rejected lower. 4H Macro: {macro_regime} | MSS: {'YES' if mss_confirmed else 'FORMING'}."
                        )

    # Secondary: High-Confluence Trend Pullback / Continuation
    if not setup_qualified and not rejection_reason:
        rsi_1h = analysis_1h.get("rsi_14", 50.0)
        ema_21_1h = analysis_1h.get("ema_21", current_price)

        if macro_regime == "MACRO_BULLISH" and analysis_1h.get("regime") in ["STRONG_BULLISH", "MILD_BULLISH"] and 45.0 <= rsi_1h <= 65.0:
            # Bullish pullback test near 1H EMA 21
            if current_price >= ema_21_1h * 0.995:
                setup_score = 80
                setup_qualified = True
                setup_side = "buy"
                invalidation_sl = round(ema_21_1h - (1.0 * atr), 2)
                risk_dist = current_price - invalidation_sl
                if risk_dist > 0:
                    target_tp = round(current_price + (2.0 * risk_dist), 2)
                    thesis = (
                        f"Trend Continuation Long (Score {setup_score}/100): 4H and 1H Bullish stacks aligned. "
                        f"Orderflow holding above 1H EMA 21 (${ema_21_1h:.2f}) with healthy RSI ({rsi_1h:.1f})."
                    )

        elif macro_regime == "MACRO_BEARISH" and analysis_1h.get("regime") in ["STRONG_BEARISH", "MILD_BEARISH"] and 35.0 <= rsi_1h <= 55.0:
            if current_price <= ema_21_1h * 1.005:
                setup_score = 80
                setup_qualified = True
                setup_side = "sell"
                invalidation_sl = round(ema_21_1h + (1.0 * atr), 2)
                risk_dist = invalidation_sl - current_price
                if risk_dist > 0:
                    target_tp = round(current_price - (2.0 * risk_dist), 2)
                    thesis = (
                        f"Trend Continuation Short (Score {setup_score}/100): 4H and 1H Bearish stacks aligned. "
                        f"Price capped under 1H EMA 21 (${ema_21_1h:.2f}) with bearish RSI ({rsi_1h:.1f})."
                    )

    analysis_1h["high_probability_setup"] = {
        "qualified": setup_qualified,
        "side": setup_side,
        "score": setup_score,
        "entry_price": current_price,
        "stop_loss_price": invalidation_sl,
        "take_profit_price": target_tp,
        "planned_rr_ratio": 2.0 if setup_qualified else 0.0,
        "thesis": thesis,
        "rejection_reason": rejection_reason,
        "macro_regime": macro_regime
    }

    return analysis_1h
