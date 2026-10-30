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
    pivot_window: int = 2,
    lookback: int = 60
) -> Dict[str, Any]:
    """
    Smart Money Concepts (SMC) Liquidity Sweep & Order Flow Analysis.
    Identifies:
      1. Buy-Side Liquidity (BSL) pools (swing highs / equal highs where short stops sit).
      2. Sell-Side Liquidity (SSL) pools (swing lows / equal lows where long stops sit).
      3. Liquidity Sweeps (Turtle Soup / Stop-Runs):
         - Bearish BSL Sweep: High broke previous swing high, but closed back below -> downside target.
         - Bullish SSL Sweep: Low broke previous swing low, but closed back above -> upside target.
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

    # Check for recent liquidity sweeps across the last 5 bars
    sweep_detected = False
    sweep_type = "NONE"
    swept_level = 0.0
    target_liquidity = 0.0
    bias = "NEUTRAL"
    narrative = ""

    # Examine recent candles for sweeps
    for bar_offset in range(1, min(6, n - 2)):
        bar_idx = n - bar_offset
        bar_h = highs[bar_idx]
        bar_l = lows[bar_idx]
        bar_c = closes[bar_idx]

        # Check Bearish BSL Sweep (pierced prior swing high, closed below)
        for sh_idx, sh_val in swing_highs:
            if sh_idx < bar_idx and bar_h > sh_val and bar_c < sh_val:
                sweep_detected = True
                sweep_type = "BEARISH_BSL_SWEEP"
                swept_level = round(sh_val, 2)
                target_liquidity = nearest_ssl
                bias = "DOWNSIDE"
                narrative = (
                    f"Bearish Liquidity Sweep detected! Price wicked above Buy-Side Liquidity (${swept_level:.2f}) "
                    f"to trigger stop orders, then rejected back lower. Market direction expected DOWNSIDE "
                    f"targeting Sell-Side Liquidity at ${target_liquidity:.2f}."
                )
                break
        if sweep_detected:
            break

        # Check Bullish SSL Sweep (pierced prior swing low, closed above)
        for sl_idx, sl_val in swing_lows:
            if sl_idx < bar_idx and bar_l < sl_val and bar_c > sl_val:
                sweep_detected = True
                sweep_type = "BULLISH_SSL_SWEEP"
                swept_level = round(sl_val, 2)
                target_liquidity = nearest_bsl
                bias = "UPSIDE"
                narrative = (
                    f"Bullish Liquidity Sweep detected! Price swept below Sell-Side Liquidity (${swept_level:.2f}) "
                    f"collecting sell stops, then aggressively rejected higher. Market direction expected UPSIDE "
                    f"targeting Buy-Side Liquidity at ${target_liquidity:.2f}."
                )
                break
        if sweep_detected:
            break

    # If no immediate sweep in last 5 bars, assess position between pools
    if not sweep_detected:
        dist_to_bsl = abs(nearest_bsl - current_price)
        dist_to_ssl = abs(current_price - nearest_ssl)
        if dist_to_ssl < (nearest_bsl - nearest_ssl) * 0.25:
            # Price hanging right at Sell-Side Liquidity
            narrative = (
                f"Market pressing near Sell-Side Liquidity (SSL: ${nearest_ssl:.2f}). "
                f"Watch for SSL sweep & reversal OR clean expansion towards lower support."
            )
            bias = "TESTING_SSL"
        elif dist_to_bsl < (nearest_bsl - nearest_ssl) * 0.25:
            narrative = (
                f"Market probing near Buy-Side Liquidity (BSL: ${nearest_bsl:.2f}). "
                f"Watch for BSL sweep & rejection OR breakout continuation."
            )
            bias = "TESTING_BSL"
        else:
            narrative = (
                f"Price in equilibrium between BSL (${nearest_bsl:.2f}) and SSL (${nearest_ssl:.2f}). "
                f"Awaiting liquidity run."
            )
            bias = "EQUILIBRIUM"

    return {
        "bsl_levels": bsl_above[:5],
        "ssl_levels": ssl_below[:5],
        "nearest_bsl": nearest_bsl,
        "nearest_ssl": nearest_ssl,
        "sweep_detected": sweep_detected,
        "sweep_type": sweep_type,
        "swept_level": swept_level,
        "target_liquidity": target_liquidity,
        "bias": bias,
        "narrative": narrative
    }


def analyze_market_structure(candles_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a full technical regime & indicator analysis on Delta Exchange chart history.
    candles_dict schema: {'t': [...], 'o': [...], 'h': [...], 'l': [...], 'c': [...], 'v': [...]}
    """
    closes = [float(x) for x in candles_dict.get('c', [])]
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
    liquidity_data = analyze_liquidity_pools_and_sweeps(highs, lows, closes)
    
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
