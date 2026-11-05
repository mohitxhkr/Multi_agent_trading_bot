"""
Technical Analysis Engine for Delta Exchange Candlestick Data.
Computes standard indicators (EMA, RSI, ATR, MACD, Bollinger Bands)
and key support/resistance levels without heavyweight external dependencies.
"""

from typing import Dict, List, Any, Optional, Tuple
import math
import time
import datetime


def round_price(val: float, ref_price: Optional[float] = None) -> float:
    """Round price with dynamic precision based on asset magnitude."""
    ref = abs(ref_price if ref_price is not None else val)
    if ref < 0.001:
        return round(val, 7)
    elif ref < 0.1:
        return round(val, 6)
    elif ref < 1.0:
        return round(val, 5)
    elif ref < 10.0:
        return round(val, 4)
    elif ref < 100.0:
        return round(val, 3)
    else:
        return round(val, 2)



def aggregate_monthly_candles(daily_candles: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate daily OHLCV candlestick data into true calendar Monthly bars.
    """
    timestamps = daily_candles.get('t', [])
    opens = daily_candles.get('o', [])
    highs = daily_candles.get('h', [])
    lows = daily_candles.get('l', [])
    closes = daily_candles.get('c', [])
    volumes = daily_candles.get('v', [])

    if not timestamps or len(timestamps) < 2:
        return {'t': [], 'o': [], 'h': [], 'l': [], 'c': [], 'v': []}

    months: Dict[str, Dict[str, Any]] = {}
    for i in range(len(timestamps)):
        dt = datetime.datetime.fromtimestamp(timestamps[i], tz=datetime.timezone.utc)
        m_key = dt.strftime('%Y-%m')
        if m_key not in months:
            months[m_key] = {
                't': timestamps[i],
                'o': opens[i],
                'h': highs[i],
                'l': lows[i],
                'c': closes[i],
                'v': volumes[i] if i < len(volumes) else 0.0
            }
        else:
            months[m_key]['h'] = max(months[m_key]['h'], highs[i])
            months[m_key]['l'] = min(months[m_key]['l'], lows[i])
            months[m_key]['c'] = closes[i]
            if i < len(volumes):
                months[m_key]['v'] += volumes[i]

    sorted_months = sorted(months.values(), key=lambda x: x['t'])
    return {
        't': [m['t'] for m in sorted_months],
        'o': [m['o'] for m in sorted_months],
        'h': [m['h'] for m in sorted_months],
        'l': [m['l'] for m in sorted_months],
        'c': [m['c'] for m in sorted_months],
        'v': [m['v'] for m in sorted_months]
    }


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


def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Dict[str, Any]:
    """Calculate Average Directional Index (ADX), +DI, and -DI."""
    n = len(closes)
    if n < period * 2:
        return {"adx": 20.0, "plus_di": 20.0, "minus_di": 20.0, "trend_strength": "RANGING"}

    tr = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    smoothed_tr = sum(tr[1:period + 1])
    smoothed_plus_dm = sum(plus_dm[1:period + 1])
    smoothed_minus_dm = sum(minus_dm[1:period + 1])

    dx_list = []
    adx = 20.0
    plus_di = 20.0
    minus_di = 20.0

    for i in range(period + 1, n):
        smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr[i]
        smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm[i]
        smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm[i]

        if smoothed_tr > 0:
            plus_di = (smoothed_plus_dm / smoothed_tr) * 100.0
            minus_di = (smoothed_minus_dm / smoothed_tr) * 100.0
        else:
            plus_di = 0.0
            minus_di = 0.0

        di_sum = plus_di + minus_di
        dx = (abs(plus_di - minus_di) / di_sum * 100.0) if di_sum > 0 else 0.0
        dx_list.append(dx)

    if dx_list:
        if len(dx_list) >= period:
            adx = sum(dx_list[-period:]) / period
        else:
            adx = sum(dx_list) / len(dx_list)

    trend_strength = "STRONG_TREND" if adx >= 25.0 else ("WEAK_TREND" if adx >= 20.0 else "RANGING")
    return {
        "adx": round(adx, 2),
        "plus_di": round(plus_di, 2),
        "minus_di": round(minus_di, 2),
        "trend_strength": trend_strength
    }


def calculate_vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float]) -> float:
    """Calculate Volume-Weighted Average Price (VWAP) across available series."""
    n = len(closes)
    if n == 0:
        return 0.0
    if not volumes or len(volumes) < n or sum(volumes) <= 0:
        return round(sum(closes) / n, 4)

    cum_pv = 0.0
    cum_vol = 0.0
    for i in range(n):
        typ_price = (highs[i] + lows[i] + closes[i]) / 3.0
        vol = max(0.0, volumes[i])
        cum_pv += typ_price * vol
        cum_vol += vol

    return round(cum_pv / cum_vol, 4) if cum_vol > 0 else round(closes[-1], 4)


def calculate_volatility_state(closes: List[float], atrs: List[float]) -> Dict[str, Any]:
    """Detect volatility expansion and contraction using Bollinger Band Width and ATR trend."""
    if len(closes) < 20 or not atrs:
        return {"state": "NORMAL", "bb_width_pct": 2.0, "atr_expansion_ratio": 1.0}

    window = closes[-20:]
    mean = sum(window) / 20.0
    variance = sum((x - mean) ** 2 for x in window) / 20.0
    std_dev = math.sqrt(variance)
    upper_band = mean + (2.0 * std_dev)
    lower_band = mean - (2.0 * std_dev)
    bb_width_pct = ((upper_band - lower_band) / mean * 100.0) if mean > 0 else 0.0

    current_atr = atrs[-1] if atrs else 0.0
    avg_atr = (sum(atrs[-30:]) / len(atrs[-30:])) if len(atrs) >= 30 else current_atr
    atr_ratio = (current_atr / avg_atr) if avg_atr > 0 else 1.0

    if bb_width_pct < 1.2 or atr_ratio < 0.75:
        state = "CONTRACTION"
    elif bb_width_pct > 3.5 or atr_ratio > 1.5:
        state = "EXPANSION"
    else:
        state = "NORMAL"

    return {
        "state": state,
        "bb_width_pct": round(bb_width_pct, 2),
        "atr_expansion_ratio": round(atr_ratio, 2)
    }


def detect_news_or_abnormal_volatility(current_atr: float, avg_atr: float) -> Tuple[bool, str]:
    """Avoid trading during extreme freak market anomalies (> 4.5x ATR) or high-impact macro news windows."""
    if avg_atr > 0 and (current_atr / avg_atr) > 4.5:
        return True, f"Extreme freak anomaly: 15m ATR is {current_atr/avg_atr:.1f}x historical average (> 4.5x threshold)"

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if now_utc.weekday() < 5:
        hour, minute = now_utc.hour, now_utc.minute
        if hour == 12 and 28 <= minute <= 45:
            return True, "Major economic news release window (US 12:30 UTC economic data release)"
        if hour == 18 and 0 <= minute <= 30:
            return True, "FOMC rate decision / high-impact macro announcement window"

    return False, ""



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
        
    # Volatility Assessment & Expansion/Contraction Detection
    all_atrs = calculate_atr(highs, lows, closes, 14)
    atr_14 = all_atrs[-1] if all_atrs else 0.0
    atr_pct = (atr_14 / current_price * 100.0) if current_price > 0 else 0.0
    vol_state = calculate_volatility_state(closes, all_atrs)
    volatility_posture = "HIGH" if (atr_pct > 3.0 or vol_state["state"] == "EXPANSION") else ("LOW" if vol_state["state"] == "CONTRACTION" else "NORMAL")

    # ADX Trend vs Range Filter
    adx_info = calculate_adx(highs, lows, closes, 14)

    # Volume Profile / VWAP Institutional Anchor
    vwap_val = calculate_vwap(highs, lows, closes, volumes)

    # Regime Confidence Scoring (0 - 100)
    conf_score = 50
    if adx_info["adx"] >= 25.0:
        conf_score += 15  # Solid directional momentum
    elif adx_info["adx"] < 18.0:
        conf_score -= 10  # Chop / rangebound
    if "STRONG" in regime:
        conf_score += 20
    elif "MILD" in regime:
        conf_score += 10
    if (regime.startswith("STRONG_BULLISH") and current_price > vwap_val) or (regime.startswith("STRONG_BEARISH") and current_price < vwap_val):
        conf_score += 15  # VWAP alignment

    conf_score = max(10, min(100, conf_score))

    # Abnormal Volatility / Macro News Window Check
    avg_atr_30 = (sum(all_atrs[-30:]) / len(all_atrs[-30:])) if len(all_atrs) >= 30 else atr_14
    news_blocked, news_reason = detect_news_or_abnormal_volatility(atr_14, avg_atr_30)

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
        "volatility_state": vol_state["state"],
        "adx_14": adx_info["adx"],
        "trend_strength": adx_info["trend_strength"],
        "vwap": vwap_val,
        "regime_confidence": conf_score,
        "news_blocked": news_blocked,
        "news_reason": news_reason,
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
    candles_4h: Optional[Dict[str, Any]] = None,
    candles_1d: Optional[Dict[str, Any]] = None,
    candles_1w: Optional[Dict[str, Any]] = None,
    candles_15m: Optional[Dict[str, Any]] = None,
    symbol: Optional[str] = None
) -> Dict[str, Any]:
    """
    Multi-Timeframe Institutional Confluence Matrix with Intraday Scalp Engine:
      1M (Monthly): Ultra-Macro Bias (Current Price vs Monthly Open, PMH, PML).
      1W (Weekly): High-Timeframe Trend (Weekly EMA 21, RSI, PWH, PWL).
      1D (Daily): Intermediate Swing Anchor (Daily EMA 21, 50, 200, RSI, PDH, PDL).
      4H (4-Hour): Cycle Momentum (4H EMA Stack, RSI).
      1H (1-Hour): Trend Context & Higher-Timeframe Liquidity Pools.
      15m (15-Minute): Ultra-Fast Intraday Scalp Execution Trigger (Liquidity Sweeps, MSS, Tight SL/TP).
    Generates >= 2 confirmed, practically achievable intraday/scalp trades daily on BTC/ETH/XAU.
    """
    analysis_1h = analyze_market_structure(candles_1h)
    if "error" in analysis_1h:
        return analysis_1h

    current_price = analysis_1h.get("current_price", 0.0)

    # -------------------------------------------------------------
    # 0. 15-Minute (15m) Intraday Execution Structure
    # -------------------------------------------------------------
    analysis_15m = None
    atr_15m = analysis_1h.get("atr_14", current_price * 0.005) * 0.5  # fallback estimate
    liq_15m = {}
    regime_15m = "NEUTRAL"
    rsi_15m = 50.0
    ema21_15m = current_price

    if candles_15m and len(candles_15m.get('c', [])) >= 20:
        analysis_15m = analyze_market_structure(candles_15m)
        if "error" not in analysis_15m:
            current_price = analysis_15m.get("current_price", current_price)
            atr_15m = analysis_15m.get("atr_14", atr_15m)
            liq_15m = analysis_15m.get("liquidity", {})
            regime_15m = analysis_15m.get("regime", "NEUTRAL")
            rsi_15m = analysis_15m.get("rsi_14", 50.0)
            ema21_15m = analysis_15m.get("ema_21", current_price)

    analysis_1h["current_price"] = current_price
    analysis_1h["macro_15m"] = {
        "regime": regime_15m,
        "rsi_14": round(rsi_15m, 2),
        "ema_21": round(ema21_15m, 2),
        "atr_14": round(atr_15m, 4),
        "liquidity": liq_15m
    }

    # -------------------------------------------------------------
    # 1. 4-Hour (4H) Cycle Momentum
    # -------------------------------------------------------------
    macro_4h_regime = "NEUTRAL"
    rsi_4h = 50.0
    ema21_4h = current_price
    ema50_4h = current_price
    ema200_4h = current_price

    if candles_4h and len(candles_4h.get('c', [])) >= 20:
        c4_closes = [float(x) for x in candles_4h.get('c', [])]
        rsi_4h = calculate_rsi(c4_closes, 14)[-1]
        ema21_4h = calculate_ema(c4_closes, 21)[-1]
        ema50_4h = calculate_ema(c4_closes, 50)[-1] if len(c4_closes) >= 50 else ema21_4h
        ema200_4h = calculate_ema(c4_closes, 200)[-1] if len(c4_closes) >= 200 else ema50_4h

        p4 = c4_closes[-1]
        if p4 > ema21_4h and ema21_4h > ema50_4h and (len(c4_closes) < 200 or p4 > ema200_4h):
            macro_4h_regime = "MACRO_BULLISH"
        elif p4 < ema21_4h and ema21_4h < ema50_4h and (len(c4_closes) < 200 or p4 < ema200_4h):
            macro_4h_regime = "MACRO_BEARISH"
        else:
            macro_4h_regime = "MACRO_NEUTRAL"

    analysis_1h["macro_4h"] = {
        "regime": macro_4h_regime,
        "rsi_14": round(rsi_4h, 2),
        "ema_21": round(ema21_4h, 2),
        "ema_50": round(ema50_4h, 2),
        "ema_200": round(ema200_4h, 2),
    }

    # -------------------------------------------------------------
    # 2. 1-Day (Daily) Intermediate Swing Anchor
    # -------------------------------------------------------------
    daily_regime = "DAILY_NEUTRAL"
    rsi_1d = 50.0
    ema21_1d = current_price
    ema50_1d = current_price
    ema200_1d = current_price
    pdh = 0.0
    pdl = 0.0

    if candles_1d and len(candles_1d.get('c', [])) >= 20:
        c1d_closes = [float(x) for x in candles_1d.get('c', [])]
        c1d_highs = [float(x) for x in candles_1d.get('h', [])]
        c1d_lows = [float(x) for x in candles_1d.get('l', [])]
        rsi_1d = calculate_rsi(c1d_closes, 14)[-1]
        ema21_1d = calculate_ema(c1d_closes, 21)[-1]
        ema50_1d = calculate_ema(c1d_closes, 50)[-1] if len(c1d_closes) >= 50 else ema21_1d
        ema200_1d = calculate_ema(c1d_closes, 200)[-1] if len(c1d_closes) >= 200 else ema50_1d

        if len(c1d_highs) >= 2:
            pdh = round(c1d_highs[-2], 2)
            pdl = round(c1d_lows[-2], 2)

        p1d = c1d_closes[-1]
        if p1d > ema21_1d and ema21_1d > ema50_1d and (len(c1d_closes) < 200 or p1d > ema200_1d):
            daily_regime = "DAILY_BULLISH"
        elif p1d < ema21_1d and ema21_1d < ema50_1d and (len(c1d_closes) < 200 or p1d < ema200_1d):
            daily_regime = "DAILY_BEARISH"
        else:
            daily_regime = "DAILY_NEUTRAL"

    analysis_1h["macro_daily"] = {
        "regime": daily_regime,
        "rsi_14": round(rsi_1d, 2),
        "ema_21": round(ema21_1d, 2),
        "ema_50": round(ema50_1d, 2),
        "ema_200": round(ema200_1d, 2),
        "pdh": pdh,
        "pdl": pdl
    }

    # -------------------------------------------------------------
    # 3. 1-Week (Weekly) High-Timeframe Trend
    # -------------------------------------------------------------
    weekly_regime = "WEEKLY_NEUTRAL"
    rsi_1w = 50.0
    ema21_1w = current_price
    pwh = 0.0
    pwl = 0.0

    if candles_1w and len(candles_1w.get('c', [])) >= 10:
        cw_closes = [float(x) for x in candles_1w.get('c', [])]
        cw_highs = [float(x) for x in candles_1w.get('h', [])]
        cw_lows = [float(x) for x in candles_1w.get('l', [])]
        rsi_1w = calculate_rsi(cw_closes, 14)[-1] if len(cw_closes) >= 15 else 50.0
        ema21_1w = calculate_ema(cw_closes, 21)[-1] if len(cw_closes) >= 21 else cw_closes[-1]

        if len(cw_highs) >= 2:
            pwh = round(cw_highs[-2], 2)
            pwl = round(cw_lows[-2], 2)

        pw = cw_closes[-1]
        if pw > ema21_1w and rsi_1w >= 48.0:
            weekly_regime = "WEEKLY_BULLISH"
        elif pw < ema21_1w and rsi_1w <= 52.0:
            weekly_regime = "WEEKLY_BEARISH"
        else:
            weekly_regime = "WEEKLY_NEUTRAL"

    analysis_1h["macro_weekly"] = {
        "regime": weekly_regime,
        "rsi_14": round(rsi_1w, 2),
        "ema_21": round(ema21_1w, 2),
        "pwh": pwh,
        "pwl": pwl
    }

    # -------------------------------------------------------------
    # 4. 1-Month (Monthly) Ultra-Macro Trend
    # -------------------------------------------------------------
    monthly_regime = "MONTHLY_NEUTRAL"
    monthly_open = current_price
    pmh = 0.0
    pml = 0.0

    if candles_1d and len(candles_1d.get('t', [])) >= 30:
        m_bars = aggregate_monthly_candles(candles_1d)
        m_opens = m_bars.get('o', [])
        m_highs = m_bars.get('h', [])
        m_lows = m_bars.get('l', [])
        m_closes = m_bars.get('c', [])

        if m_opens:
            monthly_open = round(m_opens[-1], 2)
            if len(m_highs) >= 2:
                pmh = round(m_highs[-2], 2)
                pml = round(m_lows[-2], 2)
            if m_closes[-1] >= monthly_open:
                monthly_regime = "MONTHLY_BULLISH"
            else:
                monthly_regime = "MONTHLY_BEARISH"

    analysis_1h["macro_monthly"] = {
        "regime": monthly_regime,
        "monthly_open": monthly_open,
        "pmh": pmh,
        "pml": pml
    }

    # -------------------------------------------------------------
    # 5. Multi-Timeframe Confluence Scoring & Intraday Scalp Engine
    # -------------------------------------------------------------
    liq_1h = analysis_1h.get("liquidity", {})
    atr = analysis_1h.get("atr_14", current_price * 0.015)
    
    # Prioritize 15m liquidity structure for intraday scalps, fallback to 1H
    sweep_15 = liq_15m.get("sweep_detected", False)
    sweep_1h = liq_1h.get("sweep_detected", False)
    
    active_liq = liq_15m if sweep_15 else (liq_1h if sweep_1h else {})
    sweep_detected = bool(active_liq.get("sweep_detected", False))
    sweep_type = active_liq.get("sweep_type", "NONE")
    mss_confirmed = active_liq.get("mss_confirmed", False)
    vol_confirmed = active_liq.get("volume_confirmed", False)
    sweep_wick = active_liq.get("sweep_wick_extreme", current_price)
    st_tf = "15m" if sweep_15 else ("1H" if sweep_1h else "None")

    is_primary = any(p in (symbol or "").upper() for p in ["BTC", "ETH", "XAU", "GOLD"])
    min_sl_dist = current_price * (0.0018 if is_primary else 0.0028)  # 0.18% - 0.28% minimum tight risk
    max_sl_dist = current_price * (0.0038 if is_primary else 0.0055)  # 0.38% - 0.55% strict scalp ceiling

    # High-Liquidity Institutional Killzones:
    # London Open: 07:00 - 10:00 UTC | New York Open: 12:00 - 17:00 UTC
    import datetime
    utc_now = datetime.datetime.utcnow()
    utc_hour = utc_now.hour
    is_killzone = (7 <= utc_hour <= 10) or (12 <= utc_hour <= 17)
    session_label = "London Open Killzone" if (7 <= utc_hour <= 10) else ("New York Open Killzone" if (12 <= utc_hour <= 17) else "Inter-Session")

    # Calculate Volume Surge & Relative Volume Expansion
    c15_v = [float(x) for x in candles_15m.get('v', [])] if candles_15m else []
    vol_ratio_15m = 1.0
    if len(c15_v) >= 15:
        avg_v15 = sum(c15_v[-21:-1]) / len(c15_v[-21:-1]) if len(c15_v[-21:-1]) > 0 and sum(c15_v[-21:-1]) > 0 else 1.0
        vol_ratio_15m = round(c15_v[-1] / avg_v15, 2)

    c1h_v = [float(x) for x in candles_1h.get('v', [])] if candles_1h else []
    vol_ratio_1h = 1.0
    if len(c1h_v) >= 15:
        avg_v1h = sum(c1h_v[-21:-1]) / len(c1h_v[-21:-1]) if len(c1h_v[-21:-1]) > 0 and sum(c1h_v[-21:-1]) > 0 else 1.0
        vol_ratio_1h = round(c1h_v[-1] / avg_v1h, 2)

    max_vol_ratio = max(vol_ratio_15m, vol_ratio_1h)

    setup_qualified = False
    setup_side = None
    setup_score = 0
    invalidation_sl = 0.0
    target_tp = 0.0
    calc_entry = current_price
    thesis = ""
    rejection_reason = ""
    long_rejection_reason = ""
    short_rejection_reason = ""
    strategy_label = ""

    # Priority 0: High-Volume Momentum Impulse Scalp (Pro Fast Scalp)
    # Catches explosive volume momentum in volatile markets without waiting for slow retests
    if not setup_qualified and max_vol_ratio >= 1.25:
        regime_1h = analysis_1h.get("regime", "NEUTRAL")
        vwap_val = float(analysis_1h.get("vwap") or current_price)

        # Bullish Momentum Impulse Scalp
        if (
            current_price >= ema21_15m * 0.998
            and (vwap_val == 0 or current_price >= vwap_val * 0.998)
            and macro_4h_regime != "MACRO_BEARISH"
            and 42.0 <= rsi_15m <= 80.0
            and ("BEARISH" not in regime_1h or macro_4h_regime == "MACRO_BULLISH")
        ):
            c15_c = [float(x) for x in candles_15m.get('c', [])] if candles_15m else []
            c15_o = [float(x) for x in candles_15m.get('o', [])] if candles_15m else []
            is_bull_bar = (c15_c[-1] >= c15_o[-1]) if (c15_c and c15_o) else True

            if is_bull_bar:
                setup_score = 65
                if max_vol_ratio >= 1.7:
                    setup_score += 15
                elif max_vol_ratio >= 1.4:
                    setup_score += 10
                else:
                    setup_score += 5

                if macro_4h_regime == "MACRO_BULLISH":
                    setup_score += 15
                elif macro_4h_regime == "MACRO_NEUTRAL":
                    setup_score += 5

                if "BULLISH" in regime_1h:
                    setup_score += 10
                if is_primary:
                    setup_score += 10
                if is_killzone:
                    setup_score += 5

                qual_threshold = 85 if is_primary else 90
                if setup_score >= qual_threshold:
                    calc_entry = current_price
                    sl_dist = max(min_sl_dist, min(0.95 * atr_15m, max_sl_dist))
                    invalidation_sl = round_price(calc_entry - sl_dist, calc_entry)
                    target_tp = round_price(calc_entry + (2.25 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "buy"
                    setup_score = min(98, setup_score)
                    strategy_label = "High_Volume_Momentum_Impulse_Scalp_Long"
                    thesis = (
                        f"⚡ High-Volume Momentum Impulse Scalp Long (Score {setup_score}/100 · {session_label}): "
                        f"Volume surge {max_vol_ratio:.2f}x avg with bullish candle expansion. "
                        f"Above EMA21 (${ema21_15m:.2f}) & VWAP. Fast pro scalp targeting 2.25R ({sl_dist / calc_entry * 100:.2f}% tight SL)."
                    )

        # Bearish Momentum Impulse Scalp
        elif (
            current_price <= ema21_15m * 1.002
            and (vwap_val == 0 or current_price <= vwap_val * 1.002)
            and macro_4h_regime != "MACRO_BULLISH"
            and 16.0 <= rsi_15m <= 55.0
            and ("BULLISH" not in regime_1h or macro_4h_regime == "MACRO_BEARISH")
        ):
            c15_c = [float(x) for x in candles_15m.get('c', [])] if candles_15m else []
            c15_o = [float(x) for x in candles_15m.get('o', [])] if candles_15m else []
            is_bear_bar = (c15_c[-1] <= c15_o[-1]) if (c15_c and c15_o) else True

            if is_bear_bar:
                setup_score = 65
                if max_vol_ratio >= 1.7:
                    setup_score += 15
                elif max_vol_ratio >= 1.4:
                    setup_score += 10
                else:
                    setup_score += 5

                if macro_4h_regime == "MACRO_BEARISH":
                    setup_score += 15
                elif macro_4h_regime == "MACRO_NEUTRAL":
                    setup_score += 5

                if "BEARISH" in regime_1h:
                    setup_score += 10
                if is_primary:
                    setup_score += 10
                if is_killzone:
                    setup_score += 5

                qual_threshold = 85 if is_primary else 90
                if setup_score >= qual_threshold:
                    calc_entry = current_price
                    sl_dist = max(min_sl_dist, min(0.95 * atr_15m, max_sl_dist))
                    invalidation_sl = round_price(calc_entry + sl_dist, calc_entry)
                    target_tp = round_price(calc_entry - (2.25 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "sell"
                    setup_score = min(98, setup_score)
                    strategy_label = "High_Volume_Momentum_Impulse_Scalp_Short"
                    thesis = (
                        f"⚡ High-Volume Momentum Impulse Scalp Short (Score {setup_score}/100 · {session_label}): "
                        f"Volume surge {max_vol_ratio:.2f}x avg with bearish candle expansion. "
                        f"Below EMA21 (${ema21_15m:.2f}) & VWAP. Fast pro scalp targeting 2.25R ({sl_dist / calc_entry * 100:.2f}% tight SL)."
                    )

    # Priority A: Intraday Liquidity Sweep Scalp (15m / 1H)
    # Institutional Rules:
    # 1. Macro Trend Alignment: NEVER trade against dominant 1H & 4H momentum.
    # 2. Market Structure Shift (MSS): MANDATORY confirmation (no entering on unconfirmed wicks).
    # 3. Optimal Trade Entry (OTE): Retest limit entry to maximize R:R (>= 2.4:1).
    # 4. Strict Confluence: High precision setup targeting 80-90% win rate.
    if sweep_detected:
        if sweep_type == "BULLISH_SSL_SWEEP":
            # STRICT VETO 1: Cannot go long if 1H or 4H is strongly bearish
            if macro_4h_regime == "MACRO_BEARISH" or (daily_regime == "DAILY_BEARISH" and weekly_regime == "WEEKLY_BEARISH" and rsi_1d >= 32.0):
                long_rejection_reason = "Blocked: Counter-trend conflict (Higher Timeframe 4H/Daily Bearish)."
            elif not mss_confirmed:
                long_rejection_reason = "Blocked: Market Structure Shift (MSS) not yet confirmed on lower timeframe."
            else:
                setup_score = 40  # Base confirmed sweep
                setup_score += 25  # MSS confirmed (mandatory)
                if vol_confirmed:
                    setup_score += 10  # Volume absorption confirmed
                if macro_4h_regime == "MACRO_BULLISH":
                    setup_score += 15  # 4H aligned
                elif macro_4h_regime == "MACRO_NEUTRAL":
                    setup_score += 5
                if daily_regime == "DAILY_BULLISH" or rsi_1d < 38.0:
                    setup_score += 10  # Daily aligned or oversold bounce
                if is_primary:
                    setup_score += 10  # Priority asset boost
                if is_killzone:
                    setup_score += 5   # Peak liquidity session boost

                qual_threshold = 85 if is_primary else 90
                if setup_score >= qual_threshold:
                    # Optimal Trade Entry (OTE): If candle expanded > 1 ATR, wait for 0.382 pullback limit
                    displacement = current_price - sweep_wick
                    if displacement > (1.0 * atr_15m):
                        calc_entry = round_price(current_price - (0.382 * displacement), current_price)
                    else:
                        calc_entry = current_price

                    raw_sl = min(sweep_wick, calc_entry - (0.5 * atr_15m)) - (0.08 * atr_15m)
                    raw_risk = calc_entry - raw_sl
                    sl_dist = max(min_sl_dist, min(raw_risk, max_sl_dist))
                    invalidation_sl = round_price(calc_entry - sl_dist, calc_entry)
                    target_tp = round_price(calc_entry + (2.4 * sl_dist), calc_entry)
                    
                    setup_qualified = True
                    setup_side = "buy"
                    strategy_label = f"Institutional_SSL_Sweep_{st_tf}"
                    thesis = (
                        f"High-Precision {st_tf} Bullish SSL Sweep (Score {setup_score}/100 · {session_label}): Confirmed liquidity absorption "
                        f"at ${active_liq.get('swept_level', 0):.4f} with verified MSS & HTF alignment. "
                        f"OTE Limit Entry: ${calc_entry:.4f}, Tight SL: {sl_dist / calc_entry * 100:.2f}%, Planned R:R: 2.4:1."
                    )

        elif sweep_type == "BEARISH_BSL_SWEEP":
            # STRICT VETO 1: Cannot short if 1H or 4H is strongly bullish
            if macro_4h_regime == "MACRO_BULLISH" or (daily_regime == "DAILY_BULLISH" and weekly_regime == "WEEKLY_BULLISH" and rsi_1d <= 68.0):
                short_rejection_reason = "Blocked: Counter-trend conflict (Higher Timeframe 4H/Daily Bullish expansion)."
            elif not mss_confirmed:
                short_rejection_reason = "Blocked: Market Structure Shift (MSS) not yet confirmed on lower timeframe."
            else:
                setup_score = 40  # Base confirmed sweep
                setup_score += 25  # MSS confirmed (mandatory)
                if vol_confirmed:
                    setup_score += 10  # Volume absorption confirmed
                if macro_4h_regime == "MACRO_BEARISH":
                    setup_score += 15  # 4H aligned
                elif macro_4h_regime == "MACRO_NEUTRAL":
                    setup_score += 5
                if daily_regime == "DAILY_BEARISH" or rsi_1d > 62.0:
                    setup_score += 10  # Daily aligned or overbought rejection
                if is_primary:
                    setup_score += 10  # Priority asset boost
                if is_killzone:
                    setup_score += 5   # Peak liquidity session boost

                qual_threshold = 85 if is_primary else 90
                if setup_score >= qual_threshold:
                    # Optimal Trade Entry (OTE): If candle expanded > 1 ATR, wait for 0.382 pullback limit
                    displacement = sweep_wick - current_price
                    if displacement > (1.0 * atr_15m):
                        calc_entry = round_price(current_price + (0.382 * displacement), current_price)
                    else:
                        calc_entry = current_price

                    raw_sl = max(sweep_wick, calc_entry + (0.5 * atr_15m)) + (0.08 * atr_15m)
                    raw_risk = raw_sl - calc_entry
                    sl_dist = max(min_sl_dist, min(raw_risk, max_sl_dist))
                    invalidation_sl = round_price(calc_entry + sl_dist, calc_entry)
                    target_tp = round_price(calc_entry - (2.4 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "sell"
                    strategy_label = f"Institutional_BSL_Sweep_{st_tf}"
                    thesis = (
                        f"High-Precision {st_tf} Bearish BSL Sweep (Score {setup_score}/100 · {session_label}): Confirmed liquidity absorption "
                        f"at ${active_liq.get('swept_level', 0):.4f} with verified MSS & HTF alignment. "
                        f"OTE Limit Entry: ${calc_entry:.4f}, Tight SL: {sl_dist / calc_entry * 100:.2f}%, Planned R:R: 2.4:1."
                    )

    # Priority B: 15m High-Momentum Trend Pullback / EMA Re-test Scalp
    if not setup_qualified:
        regime_1h = analysis_1h.get("regime", "NEUTRAL")
        vwap_val = float(analysis_1h.get("vwap") or current_price)
        
        # Bullish Pullback: 1H & 4H Bullish, 15m testing EMA dynamic support
        if (
            "BULLISH" in regime_1h
            and macro_4h_regime != "MACRO_BEARISH"
            and current_price >= ema21_15m * 0.995
            and 40.0 <= rsi_15m <= 75.0
        ):
            pb_score = 65 + (10 if is_primary else 0)
            if vwap_val > 0 and current_price >= vwap_val:
                pb_score += 10
            if is_killzone:
                pb_score += 5

            qual_threshold = 85 if is_primary else 90
            if pb_score >= qual_threshold:
                setup_score = pb_score
                sl_dist = max(min_sl_dist, min(1.1 * atr_15m, max_sl_dist))
                invalidation_sl = round_price(current_price - sl_dist, current_price)
                target_tp = round_price(current_price + (2.25 * sl_dist), current_price)
                
                setup_qualified = True
                setup_side = "buy"
                strategy_label = "Intraday_EMA_Pullback_Scalp_Long"
                thesis = (
                    f"Intraday 15m EMA Trend Bounce (Score {setup_score}/100): 1H {regime_1h}, holding 15m EMA21 support (${ema21_15m:.2f}). "
                    f"Tight Scalp SL: {sl_dist / current_price * 100:.2f}%, Planned R:R: 2.25:1."
                )

        # Bearish Pullback: 1H & 4H Bearish, 15m capped by EMA dynamic resistance
        elif (
            "BEARISH" in regime_1h
            and macro_4h_regime != "MACRO_BULLISH"
            and current_price <= ema21_15m * 1.005
            and 18.0 <= rsi_15m <= 58.0
        ):
            pb_score = 65 + (10 if is_primary else 0)
            if vwap_val > 0 and current_price <= vwap_val:
                pb_score += 10
            if is_killzone:
                pb_score += 5

            qual_threshold = 85 if is_primary else 90
            if pb_score >= qual_threshold:
                setup_score = pb_score
                sl_dist = max(min_sl_dist, min(1.1 * atr_15m, max_sl_dist))
                invalidation_sl = round_price(current_price + sl_dist, current_price)
                target_tp = round_price(current_price - (2.25 * sl_dist), current_price)

                setup_qualified = True
                setup_side = "sell"
                strategy_label = "Intraday_EMA_Pullback_Scalp_Short"
                thesis = (
                    f"Intraday 15m EMA Trend Rejection (Score {setup_score}/100): 1H {regime_1h}, capped under 15m EMA21 (${ema21_15m:.2f}). "
                    f"Tight Scalp SL: {sl_dist / current_price * 100:.2f}%, Planned R:R: 2.25:1."
                )

    # Priority C: Institutional Bearish Breakdown Short (Trend continuation during sell-offs / market dumps)
    if not setup_qualified:
        regime_1h = analysis_1h.get("regime", "NEUTRAL")
        vwap_val = float(analysis_1h.get("vwap") or current_price)

        is_bearish_regime = ("BEARISH" in regime_1h) or (macro_4h_regime in ["MACRO_BEARISH", "MACRO_NEUTRAL"] and "BEARISH" in regime_1h)
        is_below_ema = current_price <= ema21_15m * 1.003
        has_bearish_momentum = 16.0 <= rsi_15m <= 50.0

        if is_bearish_regime and is_below_ema and has_bearish_momentum:
            bd_score = 50
            if macro_4h_regime == "MACRO_BEARISH":
                bd_score += 20
            elif macro_4h_regime == "MACRO_NEUTRAL":
                bd_score += 10

            if "BEARISH" in regime_1h:
                bd_score += 15

            if vwap_val > 0 and current_price <= vwap_val:
                bd_score += 10

            if is_primary:
                bd_score += 10

            if is_killzone:
                bd_score += 5

            qual_threshold = 85 if is_primary else 90
            if bd_score >= qual_threshold:
                calc_entry = current_price
                raw_sl = max(ema21_15m, calc_entry + (0.9 * atr_15m))
                raw_risk = raw_sl - calc_entry
                sl_dist = max(min_sl_dist, min(raw_risk, max_sl_dist))
                invalidation_sl = round_price(calc_entry + sl_dist, calc_entry)
                target_tp = round_price(calc_entry - (2.2 * sl_dist), calc_entry)

                setup_qualified = True
                setup_side = "sell"
                setup_score = min(98, bd_score)
                strategy_label = "Institutional_Bearish_Breakdown_Short"
                thesis = (
                    f"Institutional Bearish Breakdown Short (Score {setup_score}/100 · {session_label}): "
                    f"Unified 4H {macro_4h_regime} & 1H {regime_1h} momentum continuation. "
                    f"Trading below EMA21 (${ema21_15m:.2f}) with RSI {rsi_15m:.1f}. "
                    f"Tight SL: {sl_dist / calc_entry * 100:.2f}%, Planned R:R: 2.2:1."
                )

    if not setup_qualified:
        rejection_reason = short_rejection_reason or long_rejection_reason or "No high-probability trend or mean-reversion edge qualified (min score 85)."

    real_rr = round(abs(target_tp - calc_entry) / abs(calc_entry - invalidation_sl), 2) if (setup_qualified and abs(calc_entry - invalidation_sl) > 0) else 0.0

    analysis_1h["high_probability_setup"] = {
        "qualified": setup_qualified,
        "side": setup_side,
        "strategy": strategy_label,
        "score": setup_score,
        "entry_price": calc_entry,
        "stop_loss_price": invalidation_sl,
        "take_profit_price": target_tp,
        "planned_rr_ratio": real_rr,
        "thesis": thesis,
        "rejection_reason": rejection_reason,
        "macro_regime": macro_4h_regime
    }

    return analysis_1h
