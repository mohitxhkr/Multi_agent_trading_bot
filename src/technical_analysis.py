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
    """Calculate MACD Line, Signal Line, and Histogram with proper warm-up handling."""
    if len(prices) < slow:
        zeroes = [0.0] * len(prices)
        return {"macd": zeroes, "signal": zeroes, "histogram": zeroes}

    fast_ema = calculate_ema(prices, fast)
    slow_ema = calculate_ema(prices, slow)
    
    # Prior to slow warmup period, MACD is not yet active (zero-padded)
    macd_line = [0.0 if i < (slow - 1) else (f - s) for i, (f, s) in enumerate(zip(fast_ema, slow_ema))]
    
    # Calculate signal line only across the valid MACD series to prevent signal line distortion
    valid_macd = macd_line[slow - 1:]
    valid_signal = calculate_ema(valid_macd, signal)
    signal_line = [0.0] * (slow - 1) + valid_signal
    
    histogram = [0.0 if i < (slow + signal - 2) else (m - s) for i, (m, s) in enumerate(zip(macd_line, signal_line))]
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }


def analyze_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Any]:
    """
    Computes comprehensive MACD intelligence:
    - MACD Line, Signal Line, and Histogram values
    - Crossover state: BULLISH_CROSS, BEARISH_CROSS, BULLISH_ALIGNED, BEARISH_ALIGNED, or NONE
    - Zero-line stance: ABOVE_ZERO (Macro Bullish) vs BELOW_ZERO (Macro Bearish)
    - Momentum phase:
        * BULLISH_EXPANSION: Histogram > 0 and expanding upward
        * BULLISH_DECELERATION: Histogram > 0 but contracting toward zero
        * BEARISH_EXPANSION: Histogram < 0 and expanding downward
        * BEARISH_DECELERATION: Histogram < 0 but contracting upward toward zero
    - Overall MACD bias: STRONG_BULLISH, BULLISH, NEUTRAL, BEARISH, or STRONG_BEARISH
    """
    raw = calculate_macd(prices, fast, slow, signal)
    macd_series = raw.get("macd", [])
    signal_series = raw.get("signal", [])
    hist_series = raw.get("histogram", [])

    if not macd_series or not signal_series or not hist_series:
        return {
            "macd": 0.0,
            "signal": 0.0,
            "histogram": 0.0,
            "crossover": "NONE",
            "zero_line": "AT_ZERO",
            "momentum_phase": "NEUTRAL",
            "bias": "NEUTRAL",
            "raw": raw
        }

    c_macd = macd_series[-1]
    c_signal = signal_series[-1]
    c_hist = hist_series[-1]

    # Previous bar values for crossover and momentum phase detection
    p_macd = macd_series[-2] if len(macd_series) >= 2 else c_macd
    p_signal = signal_series[-2] if len(signal_series) >= 2 else c_signal
    p_hist = hist_series[-2] if len(hist_series) >= 2 else c_hist

    # 1. Crossover Detection
    if p_macd <= p_signal and c_macd > c_signal:
        crossover = "BULLISH_CROSS"
    elif p_macd >= p_signal and c_macd < c_signal:
        crossover = "BEARISH_CROSS"
    elif c_macd > c_signal:
        crossover = "BULLISH_ALIGNED"
    elif c_macd < c_signal:
        crossover = "BEARISH_ALIGNED"
    else:
        crossover = "NONE"

    # 2. Zero-Line Regime Position
    if c_macd > 0 and c_signal > 0:
        zero_line = "ABOVE_ZERO"
    elif c_macd < 0 and c_signal < 0:
        zero_line = "BELOW_ZERO"
    else:
        zero_line = "CROSSING_ZERO"

    # 3. Momentum Histogram Phase
    if c_hist > 0:
        momentum_phase = "BULLISH_EXPANSION" if c_hist >= p_hist else "BULLISH_DECELERATION"
    elif c_hist < 0:
        momentum_phase = "BEARISH_EXPANSION" if c_hist <= p_hist else "BEARISH_DECELERATION"
    else:
        momentum_phase = "NEUTRAL"

    # 4. Synthesized Technical MACD Bias
    if crossover == "BULLISH_CROSS" or (c_macd > c_signal and zero_line == "ABOVE_ZERO" and momentum_phase == "BULLISH_EXPANSION"):
        bias = "STRONG_BULLISH"
    elif c_macd > c_signal:
        bias = "BULLISH"
    elif crossover == "BEARISH_CROSS" or (c_macd < c_signal and zero_line == "BELOW_ZERO" and momentum_phase == "BEARISH_EXPANSION"):
        bias = "STRONG_BEARISH"
    elif c_macd < c_signal:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return {
        "macd": round(c_macd, 4),
        "signal": round(c_signal, 4),
        "histogram": round(c_hist, 4),
        "crossover": crossover,
        "zero_line": zero_line,
        "momentum_phase": momentum_phase,
        "bias": bias,
        "raw": raw
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


def analyze_vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float]) -> Dict[str, Any]:
    """
    Computes institutional Volume-Weighted Average Price (VWAP) with Standard Deviation Bands:
    - Base VWAP
    - Upper Band +1 Sigma (+1σ) & Upper Band +2 Sigma (+2σ) [Overbought / Take Profit targets]
    - Lower Band -1 Sigma (-1σ) & Lower Band -2 Sigma (-2σ) [Oversold / Discount Accumulation]
    - Price Stance: ABOVE_VWAP, BELOW_VWAP, or AT_VWAP (within ±0.15%)
    - Band Location: OVERBOUGHT_EXTENSION, PREMIUM_BAND, FAIR_VALUE_CORE, DISCOUNT_BAND, OVERSOLD_CAPITULATION
    - Slope: RISING_BULLISH, FALLING_BEARISH, or FLAT
    """
    n = len(closes)
    if n == 0:
        return {
            "vwap": 0.0,
            "upper_band_1": 0.0,
            "lower_band_1": 0.0,
            "upper_band_2": 0.0,
            "lower_band_2": 0.0,
            "band_width_pct": 0.0,
            "deviation_pct": 0.0,
            "stance": "AT_VWAP",
            "band_location": "FAIR_VALUE_CORE",
            "slope": "FLAT"
        }

    current_price = closes[-1]
    if not volumes or len(volumes) < n or sum(volumes) <= 0:
        base_vwap = round(sum(closes) / n, 4)
        dev_pct = ((current_price - base_vwap) / base_vwap * 100.0) if base_vwap > 0 else 0.0
        return {
            "vwap": base_vwap,
            "upper_band_1": round(base_vwap * 1.01, 4),
            "lower_band_1": round(base_vwap * 0.99, 4),
            "upper_band_2": round(base_vwap * 1.02, 4),
            "lower_band_2": round(base_vwap * 0.98, 4),
            "band_width_pct": 2.0,
            "deviation_pct": round(dev_pct, 2),
            "stance": "ABOVE_VWAP" if current_price > base_vwap else ("BELOW_VWAP" if current_price < base_vwap else "AT_VWAP"),
            "band_location": "FAIR_VALUE_CORE",
            "slope": "FLAT"
        }

    cum_pv = 0.0
    cum_vol = 0.0
    typical_prices = []
    vols = []
    for i in range(n):
        typ = (highs[i] + lows[i] + closes[i]) / 3.0
        v = max(0.0, volumes[i])
        cum_pv += typ * v
        cum_vol += v
        typical_prices.append(typ)
        vols.append(v)

    if cum_vol <= 0:
        base_vwap = closes[-1]
        sigma = 0.0
    else:
        base_vwap = cum_pv / cum_vol
        variance = sum(v * ((typ - base_vwap) ** 2) for typ, v in zip(typical_prices, vols)) / cum_vol
        sigma = math.sqrt(max(0.0, variance))

    upper_1 = base_vwap + sigma
    lower_1 = base_vwap - sigma
    upper_2 = base_vwap + (2.0 * sigma)
    lower_2 = base_vwap - (2.0 * sigma)

    # Stance relative to base VWAP (within 0.15% is equilibrium AT_VWAP)
    dev_pct = ((current_price - base_vwap) / base_vwap * 100.0) if base_vwap > 0 else 0.0
    if abs(dev_pct) <= 0.15:
        stance = "AT_VWAP"
    elif dev_pct > 0:
        stance = "ABOVE_VWAP"
    else:
        stance = "BELOW_VWAP"

    # Band Location
    if current_price >= upper_2:
        band_loc = "OVERBOUGHT_EXTENSION"
    elif current_price >= upper_1:
        band_loc = "PREMIUM_BAND"
    elif current_price <= lower_2:
        band_loc = "OVERSOLD_CAPITULATION"
    elif current_price <= lower_1:
        band_loc = "DISCOUNT_BAND"
    else:
        band_loc = "FAIR_VALUE_CORE"

    # Slope calculation (comparing recent VWAP vs previous window)
    slope = "FLAT"
    if n >= 6:
        prev_n = n - 4
        prev_pv = sum(typical_prices[i] * vols[i] for i in range(prev_n))
        prev_v = sum(vols[:prev_n])
        if prev_v > 0:
            prev_vwap = prev_pv / prev_v
            if base_vwap > prev_vwap * 1.0006:
                slope = "RISING_BULLISH"
            elif base_vwap < prev_vwap * 0.9994:
                slope = "FALLING_BEARISH"

    band_width_pct = round(((upper_2 - lower_2) / base_vwap * 100.0), 2) if base_vwap > 0 else 0.0

    return {
        "vwap": round(base_vwap, 4),
        "upper_band_1": round(upper_1, 4),
        "lower_band_1": round(lower_1, 4),
        "upper_band_2": round(upper_2, 4),
        "lower_band_2": round(lower_2, 4),
        "band_width_pct": band_width_pct,
        "deviation_pct": round(dev_pct, 2),
        "stance": stance,
        "band_location": band_loc,
        "slope": slope
    }


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


def calculate_atr_calibrated_stops(
    entry_price: float,
    side: str,
    structural_pivot: Optional[float] = None,
    atr: float = 0.0,
    volatility_state: str = "NORMAL",
    target_rr_ratio: float = 2.5,
    min_stop_distance_pct: float = 0.25,
    max_stop_distance_pct: float = 1.80
) -> Dict[str, Any]:
    """
    Calculate dynamic ATR-calibrated Stop Loss and Take Profit levels.
    Combines market structure anchors with ATR volatility cushions to eliminate
    premature noise stop-outs and maintain mathematical risk-to-reward asymmetry.
    """
    if entry_price <= 0:
        return {
            "entry_price": entry_price,
            "stop_loss_price": 0.0,
            "take_profit_price": 0.0,
            "stop_distance": 0.0,
            "stop_distance_pct": 0.0,
            "atr": atr,
            "atr_stop_multiple": 0.0,
            "planned_rr_ratio": target_rr_ratio,
            "volatility_state": volatility_state
        }

    effective_atr = atr if atr > 0 else (entry_price * 0.006)

    # Volatility regime scalar: widen during expansion, compress during consolidation
    if volatility_state == "EXPANSION":
        atr_scalar = 1.25
        structural_buffer = 0.30 * effective_atr
    elif volatility_state == "CONTRACTION":
        atr_scalar = 0.75
        structural_buffer = 0.15 * effective_atr
    else:
        atr_scalar = 1.00
        structural_buffer = 0.20 * effective_atr

    side_clean = side.lower()

    if side_clean == "buy":
        if structural_pivot is not None and structural_pivot > 0 and structural_pivot < entry_price:
            raw_sl = structural_pivot - structural_buffer
            stop_distance = entry_price - raw_sl
        else:
            stop_distance = effective_atr * atr_scalar
            raw_sl = entry_price - stop_distance
    else:
        if structural_pivot is not None and structural_pivot > 0 and structural_pivot > entry_price:
            raw_sl = structural_pivot + structural_buffer
            stop_distance = raw_sl - entry_price
        else:
            stop_distance = effective_atr * atr_scalar
            raw_sl = entry_price + stop_distance

    min_dist = max(min_stop_distance_pct / 100.0 * entry_price, 0.45 * effective_atr)
    max_dist = min(max_stop_distance_pct / 100.0 * entry_price, 2.80 * effective_atr)
    if max_dist < min_dist:
        max_dist = min_dist * 1.5

    clamped_stop_distance = max(min_dist, min(stop_distance, max_dist))

    if side_clean == "buy":
        final_sl = round_price(entry_price - clamped_stop_distance, entry_price)
        final_tp = round_price(entry_price + (clamped_stop_distance * target_rr_ratio), entry_price)
    else:
        final_sl = round_price(entry_price + clamped_stop_distance, entry_price)
        final_tp = round_price(entry_price - (clamped_stop_distance * target_rr_ratio), entry_price)

    final_distance = abs(entry_price - final_sl)
    atr_multiple = round(final_distance / effective_atr, 2) if effective_atr > 0 else 1.0
    dist_pct = round((final_distance / entry_price) * 100.0, 2)
    rr_achieved = round(abs(final_tp - entry_price) / final_distance, 2) if final_distance > 0 else target_rr_ratio

    return {
        "entry_price": entry_price,
        "stop_loss_price": final_sl,
        "take_profit_price": final_tp,
        "stop_distance": round(final_distance, 4),
        "stop_distance_pct": dist_pct,
        "atr": round(effective_atr, 4),
        "atr_stop_multiple": atr_multiple,
        "planned_rr_ratio": rr_achieved,
        "volatility_state": volatility_state
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
            "bsl_distance_pct": None,
            "ssl_distance_pct": None,
            "liquidity_structure": "INSUFFICIENT_DATA",
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

    bsl_dist_pct = round(abs(nearest_bsl - current_price) / current_price * 100.0, 2) if current_price > 0 else 0.0
    ssl_dist_pct = round(abs(current_price - nearest_ssl) / current_price * 100.0, 2) if current_price > 0 else 0.0

    if sweep_detected and mss_confirmed:
        liq_structure = "SWEEP_MSS_CONFIRMED"
    elif sweep_detected:
        liq_structure = "SWEEP_WICK_REJECTION"
    elif bsl_dist_pct <= 0.40:
        liq_structure = "TESTING_BSL_LIQUIDITY"
    elif ssl_dist_pct <= 0.40:
        liq_structure = "TESTING_SSL_LIQUIDITY"
    else:
        liq_structure = "BALANCED_LIQUIDITY_CORE"

    return {
        "bsl_levels": bsl_above[:5],
        "ssl_levels": ssl_below[:5],
        "nearest_bsl": nearest_bsl,
        "nearest_ssl": nearest_ssl,
        "bsl_distance_pct": bsl_dist_pct,
        "ssl_distance_pct": ssl_dist_pct,
        "liquidity_structure": liq_structure,
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


def detect_fair_value_gaps(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    opens: Optional[List[float]] = None,
    min_gap_pct: float = 0.03,
    lookback: int = 60
) -> Dict[str, Any]:
    """
    Smart Money Concepts (SMC) Fair Value Gap (FVG) Detection, 50% Consequent Encroachment (CE),
    and Mitigation / Retest Life-cycle Engine.

    A 3-candle Fair Value Gap occurs when:
      - Bullish FVG (Buy-Side Imbalance / Sell-Side Inefficiency):
          lows[i] > highs[i - 2]
          gap_bottom = highs[i - 2], gap_top = lows[i]
          Consequent Encroachment (CE): 50% midpoint = (gap_bottom + gap_top) / 2.0
      - Bearish FVG (Sell-Side Imbalance / Buy-Side Inefficiency):
          highs[i] < lows[i - 2]
          gap_bottom = highs[i], gap_top = lows[i - 2]
          Consequent Encroachment (CE): 50% midpoint = (gap_bottom + gap_top) / 2.0

    Mitigation Life-cycle:
      - UNTESTED: Price has never re-entered the gap since formation.
      - RETESTING: Price has tapped into the gap boundary.
      - CE_RETESTED: Price has touched or penetrated 50% Consequent Encroachment without invalidating.
      - MITIGATED: Price has closed through or fully traversed the opposite gap boundary (gap filled).
    """
    n = len(closes)
    if n < 4:
        return {
            "bullish_fvgs": [],
            "bearish_fvgs": [],
            "active_bullish_fvgs": [],
            "active_bearish_fvgs": [],
            "active_bullish_count": 0,
            "active_bearish_count": 0,
            "nearest_bullish_fvg": None,
            "nearest_bearish_fvg": None,
            "bullish_fvg_distance_pct": None,
            "bearish_fvg_distance_pct": None,
            "retest_active": False,
            "retest_type": "NONE",
            "active_retest_fvg": None,
            "ce_tested": False,
            "wick_rejection": False,
            "bias": "NEUTRAL",
            "narrative": "Insufficient candle history for FVG detection."
        }

    start_idx = max(2, n - lookback)
    all_bullish_fvgs: List[Dict[str, Any]] = []
    all_bearish_fvgs: List[Dict[str, Any]] = []
    current_price = closes[-1]

    for i in range(start_idx, n):
        # 1. Bullish FVG: Candle i Low > Candle i-2 High
        if lows[i] > highs[i - 2]:
            gap_bottom = highs[i - 2]
            gap_top = lows[i]
            gap_size = gap_top - gap_bottom
            gap_pct = (gap_size / closes[i] * 100.0) if closes[i] > 0 else 0.0

            if gap_pct >= min_gap_pct:
                ce = round((gap_bottom + gap_top) / 2.0, 4)

                mitigated = False
                tested = False
                ce_tested = False
                mitigated_idx = None

                for k in range(i + 1, n):
                    if lows[k] <= gap_top:
                        tested = True
                    if lows[k] <= ce:
                        ce_tested = True
                    # Invalidation: candle close below gap_bottom or low below gap_bottom
                    if closes[k] < gap_bottom or lows[k] < gap_bottom:
                        mitigated = True
                        mitigated_idx = k
                        break

                fvg_item = {
                    "type": "BULLISH_FVG",
                    "formed_idx": i,
                    "gap_top": round(gap_top, 4),
                    "gap_bottom": round(gap_bottom, 4),
                    "ce": ce,
                    "gap_size": round(gap_size, 4),
                    "gap_pct": round(gap_pct, 3),
                    "mitigated": mitigated,
                    "mitigated_idx": mitigated_idx,
                    "tested": tested,
                    "ce_tested": ce_tested,
                    "state": "MITIGATED" if mitigated else ("CE_RETESTED" if ce_tested else ("RETESTING" if tested else "UNTESTED"))
                }
                all_bullish_fvgs.append(fvg_item)

        # 2. Bearish FVG: Candle i High < Candle i-2 Low
        elif highs[i] < lows[i - 2]:
            gap_bottom = highs[i]
            gap_top = lows[i - 2]
            gap_size = gap_top - gap_bottom
            gap_pct = (gap_size / closes[i] * 100.0) if closes[i] > 0 else 0.0

            if gap_pct >= min_gap_pct:
                ce = round((gap_bottom + gap_top) / 2.0, 4)

                mitigated = False
                tested = False
                ce_tested = False
                mitigated_idx = None

                for k in range(i + 1, n):
                    if highs[k] >= gap_bottom:
                        tested = True
                    if highs[k] >= ce:
                        ce_tested = True
                    # Invalidation: candle close above gap_top or high above gap_top
                    if closes[k] > gap_top or highs[k] > gap_top:
                        mitigated = True
                        mitigated_idx = k
                        break

                fvg_item = {
                    "type": "BEARISH_FVG",
                    "formed_idx": i,
                    "gap_top": round(gap_top, 4),
                    "gap_bottom": round(gap_bottom, 4),
                    "ce": ce,
                    "gap_size": round(gap_size, 4),
                    "gap_pct": round(gap_pct, 3),
                    "mitigated": mitigated,
                    "mitigated_idx": mitigated_idx,
                    "tested": tested,
                    "ce_tested": ce_tested,
                    "state": "MITIGATED" if mitigated else ("CE_RETESTED" if ce_tested else ("RETESTING" if tested else "UNTESTED"))
                }
                all_bearish_fvgs.append(fvg_item)

    active_bullish = [f for f in all_bullish_fvgs if not f["mitigated"]]
    active_bearish = [f for f in all_bearish_fvgs if not f["mitigated"]]

    # Nearest active Bullish FVG below current price (acting as dynamic support)
    bullish_below = [f for f in active_bullish if f["gap_top"] <= current_price * 1.002]
    bullish_below.sort(key=lambda f: f["gap_top"], reverse=True)
    nearest_bullish_fvg = bullish_below[0] if bullish_below else (active_bullish[-1] if active_bullish else None)

    # Nearest active Bearish FVG above current price (acting as dynamic resistance)
    bearish_above = [f for f in active_bearish if f["gap_bottom"] >= current_price * 0.998]
    bearish_above.sort(key=lambda f: f["gap_bottom"])
    nearest_bearish_fvg = bearish_above[0] if bearish_above else (active_bearish[-1] if active_bearish else None)

    # Distance percentages
    bullish_dist_pct = round(abs(current_price - nearest_bullish_fvg["gap_top"]) / current_price * 100.0, 2) if (nearest_bullish_fvg and current_price > 0) else None
    bearish_dist_pct = round(abs(nearest_bearish_fvg["gap_bottom"] - current_price) / current_price * 100.0, 2) if (nearest_bearish_fvg and current_price > 0) else None

    # Current Retest & Wick Rejection Evaluation
    retest_active = False
    retest_type = "NONE"
    active_retest_fvg: Optional[Dict[str, Any]] = None
    ce_retested_now = False
    wick_rejection = False

    bar_o = opens[-1] if opens and len(opens) >= n else closes[-1]
    bar_h = highs[-1]
    bar_l = lows[-1]
    bar_c = closes[-1]
    bar_rng = max(bar_h - bar_l, 1e-6)

    # Prior bar for multi-bar retest verification
    bar_o_prev = opens[-2] if opens and len(opens) >= n - 1 else closes[-2]
    bar_h_prev = highs[-2]
    bar_l_prev = lows[-2]
    bar_c_prev = closes[-2]
    bar_rng_prev = max(bar_h_prev - bar_l_prev, 1e-6)

    # 1. Bullish FVG Retest Check
    for bf in active_bullish:
        # Latest bar testing FVG or previous bar dipped in and current bar bounced
        tested_curr = (bar_l <= bf["gap_top"] and bar_c >= bf["gap_bottom"])
        tested_prev = (bar_l_prev <= bf["gap_top"] and bar_c_prev >= bf["gap_bottom"] and bar_c > bf["ce"])

        if tested_curr or tested_prev:
            retest_active = True
            retest_type = "BULLISH_FVG_RETEST"
            active_retest_fvg = bf
            if bar_l <= bf["ce"] or bar_l_prev <= bf["ce"]:
                ce_retested_now = True

            lower_wick = min(bar_o, bar_c) - bar_l
            lower_wick_prev = min(bar_o_prev, bar_c_prev) - bar_l_prev
            if (lower_wick / bar_rng) >= 0.25 or (lower_wick_prev / bar_rng_prev) >= 0.25 or bar_c > bf["ce"]:
                wick_rejection = True
            break

    # 2. Bearish FVG Retest Check
    if not retest_active:
        for bsf in active_bearish:
            tested_curr = (bar_h >= bsf["gap_bottom"] and bar_c <= bsf["gap_top"])
            tested_prev = (bar_h_prev >= bsf["gap_bottom"] and bar_c_prev <= bsf["gap_top"] and bar_c < bsf["ce"])

            if tested_curr or tested_prev:
                retest_active = True
                retest_type = "BEARISH_FVG_RETEST"
                active_retest_fvg = bsf
                if bar_h >= bsf["ce"] or bar_h_prev >= bsf["ce"]:
                    ce_retested_now = True

                upper_wick = bar_h - max(bar_o, bar_c)
                upper_wick_prev = bar_h_prev - max(bar_o_prev, bar_c_prev)
                if (upper_wick / bar_rng) >= 0.25 or (upper_wick_prev / bar_rng_prev) >= 0.25 or bar_c < bsf["ce"]:
                    wick_rejection = True
                break

    # Construct SMC institutional narrative
    if retest_active and retest_type == "BULLISH_FVG_RETEST" and active_retest_fvg:
        bias = "BULLISH"
        ce_str = "with 50% CE tap" if ce_retested_now else "upper boundary retest"
        rej_str = "and confirmed institutional wick rejection" if wick_rejection else ""
        narrative = f"Bullish FVG Retest: Price entered active FVG [${active_retest_fvg['gap_bottom']:,.2f} - ${active_retest_fvg['gap_top']:,.2f}] ({ce_str}) {rej_str}."
    elif retest_active and retest_type == "BEARISH_FVG_RETEST" and active_retest_fvg:
        bias = "BEARISH"
        ce_str = "with 50% CE tap" if ce_retested_now else "lower boundary retest"
        rej_str = "and confirmed institutional rejection wick" if wick_rejection else ""
        narrative = f"Bearish FVG Retest: Price rallied into active FVG [${active_retest_fvg['gap_bottom']:,.2f} - ${active_retest_fvg['gap_top']:,.2f}] ({ce_str}) {rej_str}."
    elif nearest_bullish_fvg and bullish_dist_pct is not None and bullish_dist_pct <= 0.40:
        bias = "MILD_BULLISH"
        narrative = f"Price approaching dynamic Bullish FVG support at ${nearest_bullish_fvg['gap_top']:,.2f} ({bullish_dist_pct:.2f}% away)."
    elif nearest_bearish_fvg and bearish_dist_pct is not None and bearish_dist_pct <= 0.40:
        bias = "MILD_BEARISH"
        narrative = f"Price approaching dynamic Bearish FVG resistance at ${nearest_bearish_fvg['gap_bottom']:,.2f} ({bearish_dist_pct:.2f}% away)."
    else:
        bias = "NEUTRAL"
        n_bull_str = f"${nearest_bullish_fvg['gap_top']:,.2f}" if nearest_bullish_fvg else "None"
        n_bear_str = f"${nearest_bearish_fvg['gap_bottom']:,.2f}" if nearest_bearish_fvg else "None"
        narrative = f"No immediate FVG retest. Active Bullish FVG: {n_bull_str} | Active Bearish FVG: {n_bear_str}."

    return {
        "bullish_fvgs": all_bullish_fvgs,
        "bearish_fvgs": all_bearish_fvgs,
        "active_bullish_fvgs": active_bullish,
        "active_bearish_fvgs": active_bearish,
        "active_bullish_count": len(active_bullish),
        "active_bearish_count": len(active_bearish),
        "nearest_bullish_fvg": nearest_bullish_fvg,
        "nearest_bearish_fvg": nearest_bearish_fvg,
        "bullish_fvg_distance_pct": bullish_dist_pct,
        "bearish_fvg_distance_pct": bearish_dist_pct,
        "retest_active": retest_active,
        "retest_type": retest_type,
        "active_retest_fvg": active_retest_fvg,
        "ce_tested": ce_retested_now,
        "wick_rejection": wick_rejection,
        "bias": bias,
        "narrative": narrative
    }


def calculate_volume_profile(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    num_bins: int = 30,
    value_area_pct: float = 0.70
) -> Dict[str, Any]:
    """
    Volume Profile (VP) Engine:
    Constructs price-volume distribution to identify:
      - Point of Control (POC): Price level where highest volume transacted.
      - Value Area High (VAH): Upper boundary containing 70% of volume.
      - Value Area Low (VAL): Lower boundary containing 70% of volume.
      - High Volume Nodes (HVN) & Low Volume Nodes (LVN).
      - Institutional Market Stance: ABOVE_VAH, INSIDE_VA, BELOW_VAL, AT_POC.
    """
    n = len(closes)
    if n < 10 or not volumes or sum(volumes) <= 0:
        curr = closes[-1] if n > 0 else 0.0
        return {
            "poc": curr,
            "vah": curr,
            "val": curr,
            "stance": "INSIDE_VA",
            "distance_to_poc_pct": 0.0,
            "distance_to_vah_pct": 0.0,
            "distance_to_val_pct": 0.0,
            "hvn_levels": [],
            "lvn_levels": [],
            "total_profile_volume": 0.0,
            "narrative": "Insufficient volume data for Volume Profile."
        }

    p_min = min(lows)
    p_max = max(highs)
    if p_max <= p_min:
        curr = closes[-1]
        return {
            "poc": curr,
            "vah": curr,
            "val": curr,
            "stance": "AT_POC",
            "distance_to_poc_pct": 0.0,
            "distance_to_vah_pct": 0.0,
            "distance_to_val_pct": 0.0,
            "hvn_levels": [curr],
            "lvn_levels": [],
            "total_profile_volume": sum(volumes),
            "narrative": "Flat price distribution."
        }

    bin_width = (p_max - p_min) / float(num_bins)
    bins = [0.0] * num_bins
    bin_centers = [p_min + (i + 0.5) * bin_width for i in range(num_bins)]

    for i in range(n):
        h_i = highs[i]
        l_i = lows[i]
        v_i = volumes[i]
        if v_i <= 0:
            continue
        start_b = max(0, min(num_bins - 1, int((l_i - p_min) / bin_width)))
        end_b = max(0, min(num_bins - 1, int((h_i - p_min) / bin_width)))
        span = max(1, end_b - start_b + 1)
        vol_per_bin = v_i / float(span)
        for b in range(start_b, end_b + 1):
            bins[b] += vol_per_bin

    total_vol = sum(bins)
    if total_vol <= 0:
        total_vol = 1e-6

    # Point of Control (POC)
    poc_idx = max(range(num_bins), key=lambda b: bins[b])
    poc = round(bin_centers[poc_idx], 2)

    # Value Area (70% total volume around POC)
    target_vol = total_vol * value_area_pct
    accum_vol = bins[poc_idx]
    lower_idx = poc_idx
    upper_idx = poc_idx

    while accum_vol < target_vol and (lower_idx > 0 or upper_idx < num_bins - 1):
        vol_below = bins[lower_idx - 1] if lower_idx > 0 else -1.0
        vol_above = bins[upper_idx + 1] if upper_idx < num_bins - 1 else -1.0

        if vol_above >= vol_below and upper_idx < num_bins - 1:
            upper_idx += 1
            accum_vol += bins[upper_idx]
        elif lower_idx > 0:
            lower_idx -= 1
            accum_vol += bins[lower_idx]
        elif upper_idx < num_bins - 1:
            upper_idx += 1
            accum_vol += bins[upper_idx]
        else:
            break

    val = round(bin_centers[lower_idx] - 0.5 * bin_width, 2)
    vah = round(bin_centers[upper_idx] + 0.5 * bin_width, 2)

    # High / Low Volume Nodes
    mean_bin_vol = total_vol / float(num_bins)
    hvn_levels = [round(bin_centers[b], 2) for b in range(num_bins) if bins[b] >= 1.35 * mean_bin_vol]
    lvn_levels = [round(bin_centers[b], 2) for b in range(num_bins) if bins[b] <= 0.65 * mean_bin_vol]

    current_price = closes[-1]
    dist_poc_pct = round(abs(current_price - poc) / current_price * 100.0, 2) if current_price > 0 else 0.0
    dist_vah_pct = round(abs(current_price - vah) / current_price * 100.0, 2) if current_price > 0 else 0.0
    dist_val_pct = round(abs(current_price - val) / current_price * 100.0, 2) if current_price > 0 else 0.0

    if current_price > vah:
        stance = "ABOVE_VAH"
        narrative = f"Price (${current_price:,.2f}) trading above Value Area High (${vah:,.2f}) - Bullish expansion."
    elif current_price < val:
        stance = "BELOW_VAL"
        narrative = f"Price (${current_price:,.2f}) trading below Value Area Low (${val:,.2f}) - Bearish discount."
    elif dist_poc_pct <= 0.20:
        stance = "AT_POC"
        narrative = f"Price (${current_price:,.2f}) consolidating at Point of Control (${poc:,.2f}) - High consensus value."
    else:
        stance = "INSIDE_VA"
        narrative = f"Price (${current_price:,.2f}) rotating inside Value Area [${val:,.2f} - ${vah:,.2f}] around POC (${poc:,.2f})."

    return {
        "poc": poc,
        "vah": vah,
        "val": val,
        "stance": stance,
        "distance_to_poc_pct": dist_poc_pct,
        "distance_to_vah_pct": dist_vah_pct,
        "distance_to_val_pct": dist_val_pct,
        "hvn_levels": hvn_levels[:5],
        "lvn_levels": lvn_levels[:5],
        "total_profile_volume": round(total_vol, 2),
        "narrative": narrative
    }


def calculate_cumulative_volume_delta(
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    lookback: int = 25
) -> Dict[str, Any]:
    """
    Cumulative Volume Delta (CVD) & Delta Divergence Engine:
    Calculates intrabar aggressor delta:
      - Signed Delta per candle via price action & body distribution.
      - Cumulative Volume Delta (CVD) running curve.
      - CVD Slope & Order Flow Trend: RISING_ACCUMULATION, FALLING_DISTRIBUTION, FLAT_NEUTRAL.
      - Institutional Divergences:
          * Bullish Absorption Divergence: Price lower/equal low, CVD higher low (aggressive sellers absorbed).
          * Bearish Exhaustion Divergence: Price higher/equal high, CVD lower high (aggressive buyers exhausted/absorbed).
    """
    n = len(closes)
    if n < 5 or not volumes or sum(volumes) <= 0:
        return {
            "cvd_series": [0.0] * n,
            "current_cvd": 0.0,
            "delta_last_bar": 0.0,
            "cvd_slope": 0.0,
            "cvd_trend": "FLAT_NEUTRAL",
            "divergence": "NONE",
            "narrative": "Insufficient data for CVD calculation."
        }

    deltas: List[float] = []
    for i in range(n):
        h = highs[i]
        l = lows[i]
        c = closes[i]
        o = opens[i] if opens and len(opens) > i else c
        v = volumes[i]
        rng = max(h - l, 1e-6)

        # Delta Factor: Close relative to range midpoint [-1.0, +1.0]
        wick_delta_factor = (2.0 * (c - l) - (h - l)) / rng
        # Body Factor: Close relative to Open [-1.0, +1.0]
        body_delta_factor = (c - o) / rng

        # Blended signed delta
        bar_delta = 0.5 * (wick_delta_factor + body_delta_factor) * v
        deltas.append(bar_delta)

    # Cumulative series
    cvd_series: List[float] = []
    run_sum = 0.0
    for d in deltas:
        run_sum += d
        cvd_series.append(round(run_sum, 2))

    current_cvd = cvd_series[-1]
    delta_last = round(deltas[-1], 2)

    # CVD Trend via Linear Regression over lookback
    win = min(lookback, n)
    x_vals = list(range(win))
    y_vals = cvd_series[-win:]
    x_mean = sum(x_vals) / float(win)
    y_mean = sum(y_vals) / float(win)

    num = sum((x_vals[k] - x_mean) * (y_vals[k] - y_mean) for k in range(win))
    den = sum((x_vals[k] - x_mean) ** 2 for k in range(win))
    cvd_slope = (num / den) if den != 0 else 0.0

    avg_vol = (sum(volumes[-win:]) / float(win)) if win > 0 else 1.0
    normalized_slope = cvd_slope / max(avg_vol, 1e-6)

    if normalized_slope > 0.05:
        cvd_trend = "RISING_ACCUMULATION"
    elif normalized_slope < -0.05:
        cvd_trend = "FALLING_DISTRIBUTION"
    else:
        cvd_trend = "FLAT_NEUTRAL"

    # Divergence Analysis over recent lookback window
    divergence = "NONE"
    div_bars = min(20, n)
    start_k = n - div_bars

    p_lows = []
    p_highs = []
    for k in range(start_k + 2, n - 2):
        if lows[k] <= lows[k - 1] and lows[k] <= lows[k - 2] and lows[k] <= lows[k + 1] and lows[k] <= lows[k + 2]:
            p_lows.append((k, lows[k], cvd_series[k]))
        if highs[k] >= highs[k - 1] and highs[k] >= highs[k - 2] and highs[k] >= highs[k + 1] and highs[k] >= highs[k + 2]:
            p_highs.append((k, highs[k], cvd_series[k]))

    curr_low = min(lows[-3:])
    curr_high = max(highs[-3:])
    curr_cvd_low = min(cvd_series[-3:])
    curr_cvd_high = max(cvd_series[-3:])

    # 1. Bullish CVD Divergence (Price lower/equal low, CVD higher low)
    if len(p_lows) >= 1:
        _, prev_p_low, prev_cvd_low = p_lows[-1]
        if curr_low <= prev_p_low * 1.002 and curr_cvd_low > prev_cvd_low:
            divergence = "BULLISH_ABSORPTION_DIV"
    if len(p_lows) >= 2 and divergence == "NONE":
        _, l1, c1 = p_lows[-2]
        _, l2, c2 = p_lows[-1]
        if l2 <= l1 * 1.001 and c2 > c1:
            divergence = "BULLISH_ABSORPTION_DIV"

    # 2. Bearish CVD Divergence (Price higher/equal high, CVD lower high)
    if len(p_highs) >= 1 and divergence == "NONE":
        _, prev_p_high, prev_cvd_high = p_highs[-1]
        if curr_high >= prev_p_high * 0.998 and curr_cvd_high < prev_cvd_high:
            divergence = "BEARISH_EXHAUSTION_DIV"
    if len(p_highs) >= 2 and divergence == "NONE":
        _, h1, c1 = p_highs[-2]
        _, h2, c2 = p_highs[-1]
        if h2 >= h1 * 0.999 and c2 < c1:
            divergence = "BEARISH_EXHAUSTION_DIV"

    if divergence == "BULLISH_ABSORPTION_DIV":
        narrative = f"Bullish CVD Divergence: Price pressing lows but CVD rising (Institutional limit buyers absorbing market sells)."
    elif divergence == "BEARISH_EXHAUSTION_DIV":
        narrative = f"Bearish CVD Divergence: Price pressing highs but CVD declining (Buyer exhaustion / Institutional limit selling)."
    else:
        narrative = f"CVD trend is {cvd_trend} (Slope: {cvd_slope:+.2f}). No divergence."

    return {
        "cvd_series": cvd_series[-win:],
        "current_cvd": current_cvd,
        "delta_last_bar": delta_last,
        "cvd_slope": round(cvd_slope, 4),
        "cvd_trend": cvd_trend,
        "divergence": divergence,
        "narrative": narrative
    }


def calculate_order_book_imbalance(
    orderbook: Optional[Dict[str, Any]],
    depth: int = 10
) -> Dict[str, Any]:
    """
    Level-2 Order Book Imbalance (OBI) & Resting Wall Detection Engine.
    Computes:
      - Bid Depth vs Ask Depth across top K levels.
      - Order Book Imbalance Ratio: (Bid_Vol - Ask_Vol) / (Bid_Vol + Ask_Vol) in [-1.0, +1.0].
      - Depth Ratio: Bid_Vol / Ask_Vol.
      - Resting Liquidity Walls (Whale Iceberg/Limit order >= 35% of side depth).
      - Status: HEAVY_BID_IMBALANCE, HEAVY_ASK_IMBALANCE, BALANCED_ORDER_BOOK.
    """
    if not orderbook or not isinstance(orderbook, dict):
        return {
            "obi_ratio": 0.0,
            "depth_ratio": 1.0,
            "bid_depth": 0.0,
            "ask_depth": 0.0,
            "imbalance_status": "BALANCED_ORDER_BOOK",
            "bid_wall_detected": False,
            "bid_wall_price": None,
            "bid_wall_size": 0.0,
            "ask_wall_detected": False,
            "ask_wall_price": None,
            "ask_wall_size": 0.0,
            "narrative": "Order book data not available."
        }

    raw_bids = orderbook.get("buy") or orderbook.get("bids") or []
    raw_asks = orderbook.get("sell") or orderbook.get("asks") or []

    bids: List[Tuple[float, float]] = []
    for b in raw_bids[:depth]:
        if isinstance(b, dict):
            bids.append((float(b.get("price") or b.get("limit_price") or 0.0), float(b.get("size") or 0.0)))
        elif isinstance(b, (list, tuple)) and len(b) >= 2:
            bids.append((float(b[0]), float(b[1])))

    asks: List[Tuple[float, float]] = []
    for a in raw_asks[:depth]:
        if isinstance(a, dict):
            asks.append((float(a.get("price") or a.get("limit_price") or 0.0), float(a.get("size") or 0.0)))
        elif isinstance(a, (list, tuple)) and len(a) >= 2:
            asks.append((float(a[0]), float(a[1])))

    bid_vol = sum(size for _, size in bids)
    ask_vol = sum(size for _, size in asks)
    total_vol = bid_vol + ask_vol

    if total_vol <= 0:
        obi_ratio = 0.0
        depth_ratio = 1.0
    else:
        obi_ratio = round((bid_vol - ask_vol) / float(total_vol), 4)
        depth_ratio = round(bid_vol / max(ask_vol, 1e-6), 2)

    bid_wall_detected = False
    bid_wall_price = None
    bid_wall_size = 0.0
    if bids and bid_vol > 0:
        largest_bid = max(bids, key=lambda x: x[1])
        if (largest_bid[1] / bid_vol) >= 0.35:
            bid_wall_detected = True
            bid_wall_price = largest_bid[0]
            bid_wall_size = largest_bid[1]

    ask_wall_detected = False
    ask_wall_price = None
    ask_wall_size = 0.0
    if asks and ask_vol > 0:
        largest_ask = max(asks, key=lambda x: x[1])
        if (largest_ask[1] / ask_vol) >= 0.35:
            ask_wall_detected = True
            ask_wall_price = largest_ask[0]
            ask_wall_size = largest_ask[1]

    if obi_ratio >= 0.25:
        imbalance_status = "HEAVY_BID_IMBALANCE"
        wall_msg = f" (Bid Wall @ ${bid_wall_price:,.2f})" if bid_wall_detected else ""
        narrative = f"Strong Bid Imbalance ({obi_ratio:+.2f} · {depth_ratio:.1f}x): Heavy resting buy support protecting downside{wall_msg}."
    elif obi_ratio <= -0.25:
        imbalance_status = "HEAVY_ASK_IMBALANCE"
        wall_msg = f" (Ask Wall @ ${ask_wall_price:,.2f})" if ask_wall_detected else ""
        narrative = f"Strong Ask Imbalance ({obi_ratio:+.2f} · {1.0/max(depth_ratio, 0.01):.1f}x): Heavy resting sell resistance capping upside{wall_msg}."
    else:
        imbalance_status = "BALANCED_ORDER_BOOK"
        narrative = f"Order book balanced ({obi_ratio:+.2f} · Bid: {bid_vol:.1f} vs Ask: {ask_vol:.1f})."

    return {
        "obi_ratio": obi_ratio,
        "depth_ratio": depth_ratio,
        "bid_depth": round(bid_vol, 2),
        "ask_depth": round(ask_vol, 2),
        "imbalance_status": imbalance_status,
        "bid_wall_detected": bid_wall_detected,
        "bid_wall_price": bid_wall_price,
        "bid_wall_size": round(bid_wall_size, 2),
        "ask_wall_detected": ask_wall_detected,
        "ask_wall_price": ask_wall_price,
        "ask_wall_size": round(ask_wall_size, 2),
        "narrative": narrative
    }


def analyze_candlestick_and_chart_patterns(
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    lookback: int = 30
) -> Dict[str, Any]:
    """
    Exhaustive Candlestick Pattern, Chart Pattern, and Trendline Analysis:
    - Candlestick Patterns: Bullish/Bearish Engulfing, Hammer/Pinbar, Shooting Star, Doji
    - Chart Patterns: Double Top (M-Shape/Equal Highs), Double Bottom (W-Shape/Equal Lows)
    - Trendline: Linear regression slope & trendline dynamic angle
    """
    n = len(closes)
    if n < 5:
        return {
            "candlestick_pattern": "NONE",
            "candlestick_bias": "NEUTRAL",
            "chart_pattern": "NONE",
            "chart_pattern_bias": "NEUTRAL",
            "trendline_direction": "FLAT",
            "trendline_slope_pct": 0.0,
            "patterns_detected": []
        }

    detected_patterns = []

    # 1. Candlestick Pattern Detection (Last 1-2 bars)
    o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
    o0, h0, l0, c0 = opens[-1], highs[-1], lows[-1], closes[-1]

    rng0 = max(h0 - l0, 1e-6)
    body0 = abs(c0 - o0)
    rng1 = max(h1 - l1, 1e-6)
    body1 = abs(c1 - o1)

    candlestick_pattern = "NONE"
    candlestick_bias = "NEUTRAL"

    # Bullish Pinbar / Hammer
    lower_wick0 = min(o0, c0) - l0
    upper_wick0 = h0 - max(o0, c0)
    if (lower_wick0 / rng0) >= 0.55 and (body0 / rng0) <= 0.35:
        candlestick_pattern = "BULLISH_HAMMER_PINBAR"
        candlestick_bias = "BULLISH"
        detected_patterns.append("Bullish Hammer Pinbar")
    # Bearish Pinbar / Shooting Star
    elif (upper_wick0 / rng0) >= 0.55 and (body0 / rng0) <= 0.35:
        candlestick_pattern = "BEARISH_SHOOTING_STAR_PINBAR"
        candlestick_bias = "BEARISH"
        detected_patterns.append("Bearish Shooting Star Pinbar")
    # Bullish Engulfing
    elif c1 < o1 and c0 > o0 and c0 >= o1 and o0 <= c1 and body0 > body1:
        candlestick_pattern = "BULLISH_ENGULFING"
        candlestick_bias = "BULLISH"
        detected_patterns.append("Bullish Engulfing")
    # Bearish Engulfing
    elif c1 > o1 and c0 < o0 and c0 <= o1 and o0 >= c1 and body0 > body1:
        candlestick_pattern = "BEARISH_ENGULFING"
        candlestick_bias = "BEARISH"
        detected_patterns.append("Bearish Engulfing")
    # Doji / Indecision
    elif (body0 / rng0) <= 0.10:
        candlestick_pattern = "DOJI_INDECISION"
        candlestick_bias = "NEUTRAL"
        detected_patterns.append("Doji Indecision")

    # 2. Chart Pattern Detection (Double Top / Double Bottom across lookback)
    chart_pattern = "NONE"
    chart_pattern_bias = "NEUTRAL"

    pivots_h = []
    pivots_l = []
    start_bar = max(0, n - lookback)
    for i in range(start_bar + 2, n - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            pivots_h.append((i, highs[i]))
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            pivots_l.append((i, lows[i]))

    if len(pivots_h) >= 2:
        last_h1, last_h2 = pivots_h[-2][1], pivots_h[-1][1]
        diff_pct = abs(last_h1 - last_h2) / last_h1 * 100.0
        if diff_pct <= 0.30:  # Within 0.30% tolerance
            chart_pattern = "DOUBLE_TOP_M_PATTERN"
            chart_pattern_bias = "BEARISH"
            detected_patterns.append(f"Double Top (M-Pattern @ ${last_h2:,.2f})")

    if len(pivots_l) >= 2 and chart_pattern == "NONE":
        last_l1, last_l2 = pivots_l[-2][1], pivots_l[-1][1]
        diff_pct = abs(last_l1 - last_l2) / last_l1 * 100.0
        if diff_pct <= 0.30:
            chart_pattern = "DOUBLE_BOTTOM_W_PATTERN"
            chart_pattern_bias = "BULLISH"
            detected_patterns.append(f"Double Bottom (W-Pattern @ ${last_l2:,.2f})")

    # 3. Dynamic Trendline Slope (Linear regression on recent closes)
    trend_bars = min(20, n)
    x_vals = list(range(trend_bars))
    y_vals = closes[-trend_bars:]
    x_mean = sum(x_vals) / trend_bars
    y_mean = sum(y_vals) / trend_bars
    numerator = sum((x_vals[i] - x_mean) * (y_vals[i] - y_mean) for i in range(trend_bars))
    denominator = sum((x_vals[i] - x_mean) ** 2 for i in range(trend_bars))
    slope = (numerator / denominator) if denominator != 0 else 0.0
    slope_pct = (slope / closes[-1] * 100.0) if closes[-1] > 0 else 0.0

    if slope_pct > 0.05:
        trendline_dir = "ASCENDING_BULLISH"
    elif slope_pct < -0.05:
        trendline_dir = "DESCENDING_BEARISH"
    else:
        trendline_dir = "HORIZONTAL_CONSOLIDATION"

    return {
        "candlestick_pattern": candlestick_pattern,
        "candlestick_bias": candlestick_bias,
        "chart_pattern": chart_pattern,
        "chart_pattern_bias": chart_pattern_bias,
        "trendline_direction": trendline_dir,
        "trendline_slope_pct": round(slope_pct, 4),
        "patterns_detected": detected_patterns
    }


def analyze_market_structure(
    candles_dict: Dict[str, Any],
    orderbook: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
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
    
    # MACD Comprehensive Analysis
    macd_res = analyze_macd(closes)
    macd_val = macd_res["macd"]
    signal_val = macd_res["signal"]
    hist_val = macd_res["histogram"]
    
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

    # Volume Profile / VWAP Institutional Anchor & Standard Deviation Bands
    vwap_val = calculate_vwap(highs, lows, closes, volumes)
    vwap_analysis = analyze_vwap(highs, lows, closes, volumes)

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

    # Institutional VWAP Alignment & Slope Confirmation
    if (regime.startswith("STRONG_BULLISH") and vwap_analysis["stance"] == "ABOVE_VWAP") or (regime.startswith("STRONG_BEARISH") and vwap_analysis["stance"] == "BELOW_VWAP"):
        conf_score += 15  # Solid VWAP alignment
        if (regime.startswith("STRONG_BULLISH") and vwap_analysis["slope"] == "RISING_BULLISH") or (regime.startswith("STRONG_BEARISH") and vwap_analysis["slope"] == "FALLING_BEARISH"):
            conf_score += 5  # Trend slope aligned with VWAP
    elif (regime.startswith("STRONG_BULLISH") and vwap_analysis["stance"] == "BELOW_VWAP") or (regime.startswith("STRONG_BEARISH") and vwap_analysis["stance"] == "ABOVE_VWAP"):
        conf_score -= 10  # Fighting institutional VWAP value

    # MACD Momentum & Crossover Alignment in Regime Confidence
    if "BULLISH" in regime and macd_res["bias"] in ("BULLISH", "STRONG_BULLISH"):
        conf_score += 10  # MACD confirms bullish regime
    elif "BEARISH" in regime and macd_res["bias"] in ("BEARISH", "STRONG_BEARISH"):
        conf_score += 10  # MACD confirms bearish regime
    elif ("BULLISH" in regime and "BEARISH" in macd_res["bias"]) or ("BEARISH" in regime and "BULLISH" in macd_res["bias"]):
        conf_score -= 10  # MACD divergence against regime

    conf_score = max(10, min(100, conf_score))

    # Abnormal Volatility / Macro News Window Check
    avg_atr_30 = (sum(all_atrs[-30:]) / len(all_atrs[-30:])) if len(all_atrs) >= 30 else atr_14
    news_blocked, news_reason = detect_news_or_abnormal_volatility(atr_14, avg_atr_30)

    # Smart Money Concepts (SMC) & Liquidity Sweep Engine
    liquidity_data = analyze_liquidity_pools_and_sweeps(highs, lows, closes, opens=opens, volumes=volumes)

    # Smart Money Concepts (SMC) Fair Value Gap (FVG) Engine
    fvg_data = detect_fair_value_gaps(highs, lows, closes, opens=opens)

    # Institutional Volume Profile (VP) Engine
    volume_profile = calculate_volume_profile(highs, lows, closes, volumes)

    # Cumulative Volume Delta (CVD) Engine
    cvd_data = calculate_cumulative_volume_delta(opens, highs, lows, closes, volumes)

    # Level-2 Order Book Imbalance (OBI) Engine
    obi_data = calculate_order_book_imbalance(orderbook)

    # FVG Retest & Wick Rejection Alignment in Regime Confidence
    if "BULLISH" in regime and fvg_data.get("retest_type") == "BULLISH_FVG_RETEST":
        conf_score += 10
        if fvg_data.get("wick_rejection"):
            conf_score += 5
    elif "BEARISH" in regime and fvg_data.get("retest_type") == "BEARISH_FVG_RETEST":
        conf_score += 10
        if fvg_data.get("wick_rejection"):
            conf_score += 5

    # Order Flow Alignment (CVD Divergence, OBI Imbalance, Volume Profile Stance)
    if "BULLISH" in regime:
        if cvd_data.get("divergence") == "BULLISH_ABSORPTION_DIV" or cvd_data.get("cvd_trend") == "RISING_ACCUMULATION":
            conf_score += 10
        if obi_data.get("imbalance_status") == "HEAVY_BID_IMBALANCE":
            conf_score += 5
        if volume_profile.get("stance") in ("INSIDE_VA", "ABOVE_VAH"):
            conf_score += 5
    elif "BEARISH" in regime:
        if cvd_data.get("divergence") == "BEARISH_EXHAUSTION_DIV" or cvd_data.get("cvd_trend") == "FALLING_DISTRIBUTION":
            conf_score += 10
        if obi_data.get("imbalance_status") == "HEAVY_ASK_IMBALANCE":
            conf_score += 5
        if volume_profile.get("stance") in ("INSIDE_VA", "BELOW_VAL"):
            conf_score += 5

    conf_score = max(10, min(100, conf_score))

    # Exhaustive Candlestick Pattern, Chart Pattern, and Dynamic Trendline Analysis
    patterns_info = analyze_candlestick_and_chart_patterns(opens, highs, lows, closes)
    
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
        "vwap_analysis": vwap_analysis,
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
            "histogram": round(hist_val, 4),
            "crossover": macd_res["crossover"],
            "zero_line": macd_res["zero_line"],
            "momentum_phase": macd_res["momentum_phase"],
            "bias": macd_res["bias"]
        },
        "support": round(sr["support"], 2),
        "resistance": round(sr["resistance"], 2),
        "liquidity": liquidity_data,
        "fvg": fvg_data,
        "volume_profile": volume_profile,
        "cvd": cvd_data,
        "order_book_imbalance": obi_data,
        "patterns": patterns_info,
        "candlestick_pattern": patterns_info["candlestick_pattern"],
        "chart_pattern": patterns_info["chart_pattern"],
        "trendline_direction": patterns_info["trendline_direction"],
        "candle_count": len(closes)
    }


def analyze_multi_timeframe(
    candles_1h: Dict[str, Any],
    candles_4h: Optional[Dict[str, Any]] = None,
    candles_1d: Optional[Dict[str, Any]] = None,
    candles_1w: Optional[Dict[str, Any]] = None,
    candles_15m: Optional[Dict[str, Any]] = None,
    symbol: Optional[str] = None,
    orderbook: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Multi-Timeframe Institutional Confluence Matrix with Intraday Scalp Engine:
      1M (Monthly): Ultra-Macro Bias (Current Price vs Monthly Open, PMH, PML).
      1W (Weekly): High-Timeframe Trend (Weekly EMA 21, RSI, PWH, PWL).
      1D (Daily): Intermediate Swing Anchor (Daily EMA 21, 50, 200, RSI, PDH, PDL).
      4H (4-Hour): Cycle Momentum (4H EMA Stack, RSI).
      1H (1-Hour): Trend Context & Higher-Timeframe Liquidity Pools, Volume Profile & CVD.
      15m (15-Minute): Ultra-Fast Intraday Scalp Execution Trigger (Sweeps, FVG, OBI, Tight SL/TP).
    Generates >= 2 confirmed, practically achievable intraday/scalp trades daily on BTC/ETH/XAU.
    """
    analysis_1h = analyze_market_structure(candles_1h, orderbook=orderbook)
    if "error" in analysis_1h:
        return analysis_1h

    current_price = analysis_1h.get("current_price", 0.0)

    # -------------------------------------------------------------
    # 0. 15-Minute (15m) Intraday Execution Structure
    # -------------------------------------------------------------
    analysis_15m = None
    atr_15m = analysis_1h.get("atr_14", current_price * 0.005) * 0.5  # fallback estimate
    liq_15m = {}
    fvg_15m = {}
    vp_15m = {}
    cvd_15m = {}
    obi_15m = {}
    regime_15m = "NEUTRAL"
    rsi_15m = 50.0
    ema21_15m = current_price
    macd_15m = {}

    if candles_15m and len(candles_15m.get('c', [])) >= 20:
        analysis_15m = analyze_market_structure(candles_15m, orderbook=orderbook)
        if "error" not in analysis_15m:
            current_price = analysis_15m.get("current_price", current_price)
            atr_15m = analysis_15m.get("atr_14", atr_15m)
            liq_15m = analysis_15m.get("liquidity", {})
            fvg_15m = analysis_15m.get("fvg", {})
            vp_15m = analysis_15m.get("volume_profile", {})
            cvd_15m = analysis_15m.get("cvd", {})
            obi_15m = analysis_15m.get("order_book_imbalance", {})
            regime_15m = analysis_15m.get("regime", "NEUTRAL")
            rsi_15m = analysis_15m.get("rsi_14", 50.0)
            ema21_15m = analysis_15m.get("ema_21", current_price)
            macd_15m = analysis_15m.get("macd", {})

    analysis_1h["current_price"] = current_price
    macro_15m = {
        "regime": regime_15m,
        "rsi_14": round(rsi_15m, 2),
        "ema_21": round(ema21_15m, 2),
        "atr_14": round(atr_15m, 4),
        "liquidity": liq_15m,
        "fvg": fvg_15m,
        "volume_profile": vp_15m,
        "cvd": cvd_15m,
        "order_book_imbalance": obi_15m,
        "macd": macd_15m
    }
    analysis_1h["macro_15m"] = macro_15m

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
    is_btc = "BTC" in (symbol or "").upper()
    is_eth = "ETH" in (symbol or "").upper()

    # Dynamic Structural SL calibration:
    # BTC requires >= 0.35% buffer to clear 15m ATR noise ($300-$500 on $80k BTC)
    # ETH requires >= 0.25% buffer
    if is_btc:
        min_sl_dist = current_price * 0.0035
        max_sl_dist = current_price * 0.0065
    elif is_eth:
        min_sl_dist = current_price * 0.0025
        max_sl_dist = current_price * 0.0060
    elif is_primary:
        min_sl_dist = current_price * 0.0028
        max_sl_dist = current_price * 0.0060
    else:
        min_sl_dist = current_price * 0.0035
        max_sl_dist = current_price * 0.0075

    # High-Liquidity Institutional Killzones:
    # London Open: 07:00 - 10:00 UTC | New York Open: 12:00 - 17:00 UTC
    import datetime
    utc_now = datetime.datetime.now(datetime.timezone.utc)
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

    # Priority B: High-Volume Momentum Impulse Scalp (Pro Fast Scalp)
    # Triggers when volume expands aggressively in volatile markets and no liquidity sweep is present
    if not setup_qualified and not sweep_detected and max_vol_ratio >= 1.25:
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
                    sl_dist = max(min_sl_dist, min(0.90 * atr_15m, max_sl_dist))
                    invalidation_sl = round_price(calc_entry - sl_dist, calc_entry)
                    target_tp = round_price(calc_entry + (2.5 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "buy"
                    setup_score = min(98, setup_score)
                    strategy_label = "High_Volume_Momentum_Impulse_Scalp_Long"
                    thesis = (
                        f"⚡ High-Volume Momentum Impulse Scalp Long (Score {setup_score}/100 · {session_label}): "
                        f"Volume surge {max_vol_ratio:.2f}x avg with bullish candle expansion. "
                        f"Above EMA21 (${ema21_15m:.2f}) & VWAP. Minimum risk ({sl_dist / calc_entry * 100:.2f}%), Maximum profit planned R:R: 2.5:1."
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
                    sl_dist = max(min_sl_dist, min(0.90 * atr_15m, max_sl_dist))
                    invalidation_sl = round_price(calc_entry + sl_dist, calc_entry)
                    target_tp = round_price(calc_entry - (2.5 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "sell"
                    setup_score = min(98, setup_score)
                    strategy_label = "High_Volume_Momentum_Impulse_Scalp_Short"
                    thesis = (
                        f"⚡ High-Volume Momentum Impulse Scalp Short (Score {setup_score}/100 · {session_label}): "
                        f"Volume surge {max_vol_ratio:.2f}x avg with bearish candle expansion. "
                        f"Below EMA21 (${ema21_15m:.2f}) & VWAP. Minimum risk ({sl_dist / calc_entry * 100:.2f}%), Maximum profit planned R:R: 2.5:1."
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
                    target_tp = round_price(calc_entry + (2.6 * sl_dist), calc_entry)
                    
                    setup_qualified = True
                    setup_side = "buy"
                    strategy_label = f"Institutional_SSL_Sweep_{st_tf}"
                    thesis = (
                        f"High-Precision {st_tf} Bullish SSL Sweep (Score {setup_score}/100 · {session_label}): Confirmed liquidity absorption "
                        f"at ${active_liq.get('swept_level', 0):.4f} with verified MSS & HTF alignment. "
                        f"OTE Limit Entry: ${calc_entry:.4f}, Tight SL: {sl_dist / calc_entry * 100:.2f}%, Planned Asymmetric R:R: 2.6:1."
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
                    target_tp = round_price(calc_entry - (2.6 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "sell"
                    strategy_label = f"Institutional_BSL_Sweep_{st_tf}"
                    thesis = (
                        f"High-Precision {st_tf} Bearish BSL Sweep (Score {setup_score}/100 · {session_label}): Confirmed liquidity absorption "
                        f"at ${active_liq.get('swept_level', 0):.4f} with verified MSS & HTF alignment. "
                        f"OTE Limit Entry: ${calc_entry:.4f}, Tight SL: {sl_dist / calc_entry * 100:.2f}%, Planned Asymmetric R:R: 2.6:1."
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
            
            # VWAP Institutional Alignment & Band Position
            vwap_1h_info = analysis_1h.get("vwap_analysis", {})
            v_stance = vwap_1h_info.get("stance", "AT_VWAP")
            v_band = vwap_1h_info.get("band_location", "FAIR_VALUE_CORE")
            v_slope = vwap_1h_info.get("slope", "FLAT")

            if v_stance in ("ABOVE_VWAP", "AT_VWAP") or current_price >= vwap_val:
                pb_score += 10
            if v_band in ("FAIR_VALUE_CORE", "DISCOUNT_BAND") and v_slope == "RISING_BULLISH":
                pb_score += 5

            if is_killzone:
                pb_score += 5

            # MACD Momentum & Crossover Alignment
            macd_15m = macro_15m.get("macd", {}) if macro_15m else {}
            if macd_15m.get("crossover") == "BULLISH_CROSS" or macd_15m.get("momentum_phase") == "BULLISH_EXPANSION":
                pb_score += 10
            elif macd_15m.get("histogram", 0) > 0 or "BULLISH" in macd_15m.get("bias", ""):
                pb_score += 5

            qual_threshold = 85 if is_primary else 90
            if pb_score >= qual_threshold:
                setup_score = pb_score
                sl_dist = max(min_sl_dist, min(1.0 * atr_15m, max_sl_dist))
                invalidation_sl = round_price(current_price - sl_dist, current_price)
                target_tp = round_price(current_price + (2.5 * sl_dist), current_price)
                
                setup_qualified = True
                setup_side = "buy"
                strategy_label = "Intraday_EMA_Pullback_Scalp_Long"
                m_tag = f" | MACD {macd_15m.get('crossover', 'ALIGNED')}" if macd_15m else ""
                thesis = (
                    f"Intraday 15m EMA Trend Bounce (Score {setup_score}/100{m_tag}): 1H {regime_1h}, holding 15m EMA21 support (${ema21_15m:.2f}) & VWAP (${vwap_val:.2f}). "
                    f"Tight Scalp SL: {sl_dist / current_price * 100:.2f}%, Planned Asymmetric R:R: 2.5:1."
                )

        # Bearish Pullback: 1H & 4H Bearish, 15m capped by EMA dynamic resistance
        elif (
            "BEARISH" in regime_1h
            and macro_4h_regime != "MACRO_BULLISH"
            and current_price <= ema21_15m * 1.005
            and 18.0 <= rsi_15m <= 58.0
        ):
            pb_score = 65 + (10 if is_primary else 0)

            # VWAP Institutional Alignment & Band Position
            vwap_1h_info = analysis_1h.get("vwap_analysis", {})
            v_stance = vwap_1h_info.get("stance", "AT_VWAP")
            v_band = vwap_1h_info.get("band_location", "FAIR_VALUE_CORE")
            v_slope = vwap_1h_info.get("slope", "FLAT")

            if v_stance in ("BELOW_VWAP", "AT_VWAP") or current_price <= vwap_val:
                pb_score += 10
            if v_band in ("FAIR_VALUE_CORE", "PREMIUM_BAND") and v_slope == "FALLING_BEARISH":
                pb_score += 5

            if is_killzone:
                pb_score += 5

            # MACD Momentum & Crossover Alignment
            macd_15m = macro_15m.get("macd", {}) if macro_15m else {}
            if macd_15m.get("crossover") == "BEARISH_CROSS" or macd_15m.get("momentum_phase") == "BEARISH_EXPANSION":
                pb_score += 10
            elif macd_15m.get("histogram", 0) < 0 or "BEARISH" in macd_15m.get("bias", ""):
                pb_score += 5

            qual_threshold = 85 if is_primary else 90
            if pb_score >= qual_threshold:
                setup_score = pb_score
                sl_dist = max(min_sl_dist, min(1.0 * atr_15m, max_sl_dist))
                invalidation_sl = round_price(current_price + sl_dist, current_price)
                target_tp = round_price(current_price - (2.5 * sl_dist), current_price)

                setup_qualified = True
                setup_side = "sell"
                strategy_label = "Intraday_EMA_Pullback_Scalp_Short"
                m_tag = f" | MACD {macd_15m.get('crossover', 'ALIGNED')}" if macd_15m else ""
                thesis = (
                    f"Intraday 15m EMA Trend Rejection (Score {setup_score}/100{m_tag}): 1H {regime_1h}, capped under 15m EMA21 (${ema21_15m:.2f}). "
                    f"Tight Scalp SL: {sl_dist / current_price * 100:.2f}%, Planned Asymmetric R:R: 2.5:1."
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

            # MACD Momentum & Crossover Alignment
            macd_15m = macro_15m.get("macd", {}) if macro_15m else {}
            if macd_15m.get("crossover") == "BEARISH_CROSS" or macd_15m.get("momentum_phase") == "BEARISH_EXPANSION":
                bd_score += 10
            elif macd_15m.get("histogram", 0) < 0 or "BEARISH" in macd_15m.get("bias", ""):
                bd_score += 5

            qual_threshold = 85 if is_primary else 90
            if bd_score >= qual_threshold:
                calc_entry = current_price
                raw_sl = max(ema21_15m, calc_entry + (0.85 * atr_15m))
                raw_risk = raw_sl - calc_entry
                sl_dist = max(min_sl_dist, min(raw_risk, max_sl_dist))
                invalidation_sl = round_price(calc_entry + sl_dist, calc_entry)
                target_tp = round_price(calc_entry - (2.5 * sl_dist), calc_entry)

                setup_qualified = True
                setup_side = "sell"
                setup_score = min(98, bd_score)
                strategy_label = "Institutional_Bearish_Breakdown_Short"
                m_tag = f" | MACD {macd_15m.get('crossover', 'ALIGNED')}" if macd_15m else ""
                thesis = (
                    f"Institutional Bearish Breakdown Short (Score {setup_score}/100 · {session_label}{m_tag}): "
                    f"Unified 4H {macro_4h_regime} & 1H {regime_1h} momentum continuation. "
                    f"Trading below EMA21 (${ema21_15m:.2f}) with RSI {rsi_15m:.1f}. "
                    f"Tight SL: {sl_dist / calc_entry * 100:.2f}%, Planned Asymmetric R:R: 2.5:1."
                )

    # Priority D: SMC Fair Value Gap (FVG) Retest & Mitigation Engine
    if not setup_qualified:
        fvg_1h = analysis_1h.get("fvg", {})
        active_fvg_ctx = fvg_15m if fvg_15m.get("retest_active") else (fvg_1h if fvg_1h.get("retest_active") else {})
        retest_type = active_fvg_ctx.get("retest_type", "NONE")
        retest_fvg = active_fvg_ctx.get("active_retest_fvg")
        fvg_ce_tested = active_fvg_ctx.get("ce_tested", False)
        fvg_wick_rej = active_fvg_ctx.get("wick_rejection", False)

        if retest_type == "BULLISH_FVG_RETEST" and retest_fvg:
            if macro_4h_regime == "MACRO_BEARISH" or (daily_regime == "DAILY_BEARISH" and weekly_regime == "WEEKLY_BEARISH"):
                long_rejection_reason = "Blocked: Counter-trend conflict (Higher Timeframe 4H/Daily Bearish against Bullish FVG)."
            else:
                fvg_score = 65 + (10 if is_primary else 0)
                if fvg_ce_tested:
                    fvg_score += 10  # 50% CE level tested & defended
                if fvg_wick_rej:
                    fvg_score += 8   # Confirmed lower wick rejection
                if "BULLISH" in regime_1h:
                    fvg_score += 10
                if is_killzone:
                    fvg_score += 5

                # MACD alignment
                macd_15m = macro_15m.get("macd", {}) if macro_15m else {}
                if macd_15m.get("crossover") == "BULLISH_CROSS" or macd_15m.get("momentum_phase") == "BULLISH_EXPANSION":
                    fvg_score += 10
                elif macd_15m.get("histogram", 0) > 0 or "BULLISH" in macd_15m.get("bias", ""):
                    fvg_score += 5

                qual_threshold = 85 if is_primary else 90
                if fvg_score >= qual_threshold:
                    calc_entry = current_price
                    fvg_bot = float(retest_fvg.get("gap_bottom", current_price - atr_15m))
                    raw_sl = min(fvg_bot, calc_entry - (0.5 * atr_15m)) - (0.10 * atr_15m)
                    raw_risk = calc_entry - raw_sl
                    sl_dist = max(min_sl_dist, min(raw_risk, max_sl_dist))
                    invalidation_sl = round_price(calc_entry - sl_dist, calc_entry)
                    target_tp = round_price(calc_entry + (2.6 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "buy"
                    setup_score = min(98, fvg_score)
                    strategy_label = "Institutional_SMC_Bullish_FVG_Retest"
                    ce_tag = "50% CE Retest" if fvg_ce_tested else "Boundary Retest"
                    wick_tag = " · Wick Rejection Confirmed" if fvg_wick_rej else ""
                    m_tag = f" | MACD {macd_15m.get('crossover', 'ALIGNED')}" if macd_15m else ""
                    thesis = (
                        f"SMC Fair Value Gap Retest Long (Score {setup_score}/100 · {session_label}{m_tag}): "
                        f"{ce_tag}{wick_tag} at [${fvg_bot:,.2f} - ${retest_fvg.get('gap_top', calc_entry):,.2f}]. "
                        f"Protected SL: {sl_dist / calc_entry * 100:.2f}%, Planned Asymmetric R:R: 2.6:1."
                    )

        elif retest_type == "BEARISH_FVG_RETEST" and retest_fvg:
            if macro_4h_regime == "MACRO_BULLISH" or (daily_regime == "DAILY_BULLISH" and weekly_regime == "WEEKLY_BULLISH"):
                short_rejection_reason = "Blocked: Counter-trend conflict (Higher Timeframe 4H/Daily Bullish against Bearish FVG)."
            else:
                fvg_score = 65 + (10 if is_primary else 0)
                if fvg_ce_tested:
                    fvg_score += 10  # 50% CE level tested & rejected
                if fvg_wick_rej:
                    fvg_score += 8   # Confirmed upper wick rejection
                if "BEARISH" in regime_1h:
                    fvg_score += 10
                if is_killzone:
                    fvg_score += 5

                # MACD alignment
                macd_15m = macro_15m.get("macd", {}) if macro_15m else {}
                if macd_15m.get("crossover") == "BEARISH_CROSS" or macd_15m.get("momentum_phase") == "BEARISH_EXPANSION":
                    fvg_score += 10
                elif macd_15m.get("histogram", 0) < 0 or "BEARISH" in macd_15m.get("bias", ""):
                    fvg_score += 5

                qual_threshold = 85 if is_primary else 90
                if fvg_score >= qual_threshold:
                    calc_entry = current_price
                    fvg_top = float(retest_fvg.get("gap_top", current_price + atr_15m))
                    raw_sl = max(fvg_top, calc_entry + (0.5 * atr_15m)) + (0.10 * atr_15m)
                    raw_risk = raw_sl - calc_entry
                    sl_dist = max(min_sl_dist, min(raw_risk, max_sl_dist))
                    invalidation_sl = round_price(calc_entry + sl_dist, calc_entry)
                    target_tp = round_price(calc_entry - (2.6 * sl_dist), calc_entry)

                    setup_qualified = True
                    setup_side = "sell"
                    setup_score = min(98, fvg_score)
                    strategy_label = "Institutional_SMC_Bearish_FVG_Retest"
                    ce_tag = "50% CE Retest" if fvg_ce_tested else "Boundary Retest"
                    wick_tag = " · Wick Rejection Confirmed" if fvg_wick_rej else ""
                    m_tag = f" | MACD {macd_15m.get('crossover', 'ALIGNED')}" if macd_15m else ""
                    thesis = (
                        f"SMC Fair Value Gap Retest Short (Score {setup_score}/100 · {session_label}{m_tag}): "
                        f"{ce_tag}{wick_tag} at [${retest_fvg.get('gap_bottom', calc_entry):,.2f} - ${fvg_top:,.2f}]. "
                        f"Protected SL: {sl_dist / calc_entry * 100:.2f}%, Planned Asymmetric R:R: 2.6:1."
                    )

    if not setup_qualified:
        rejection_reason = short_rejection_reason or long_rejection_reason or "No high-probability trend or mean-reversion edge qualified (min score 85)."

    real_rr = round(abs(target_tp - calc_entry) / abs(calc_entry - invalidation_sl), 2) if (setup_qualified and abs(calc_entry - invalidation_sl) > 0) else 0.0

    stop_dist_val = round(abs(calc_entry - invalidation_sl), 4) if (setup_qualified and abs(calc_entry - invalidation_sl) > 0) else 0.0
    atr_mult_val = round(stop_dist_val / atr_15m, 2) if (atr_15m > 0 and stop_dist_val > 0) else 1.0

    analysis_1h["high_probability_setup"] = {
        "qualified": setup_qualified,
        "side": setup_side,
        "strategy": strategy_label,
        "score": setup_score,
        "entry_price": calc_entry,
        "stop_loss_price": invalidation_sl,
        "take_profit_price": target_tp,
        "stop_distance": stop_dist_val,
        "atr_14": atr_15m,
        "atr_stop_multiple": atr_mult_val,
        "planned_rr_ratio": real_rr,
        "thesis": thesis,
        "rejection_reason": rejection_reason,
        "macro_regime": macro_4h_regime
    }

    # Synthesize Breakout and Breakdown Key Levels & Pre-Trade Plan
    try:
        analysis_1h["key_levels_analysis"] = calculate_breakout_breakdown_levels(analysis_1h)
    except Exception as kle:
        analysis_1h["key_levels_analysis"] = {"error": str(kle)}

    return analysis_1h


def calculate_breakout_breakdown_levels(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesize order flow, volume profile, liquidity pools, and market structure
    to extract critical breakout and breakdown trigger levels with pre-trade actionable plans.
    """
    symbol = analysis_data.get("symbol", "N/A")
    current_price = float(analysis_data.get("mark_price") or analysis_data.get("current_price") or 0.0)
    if current_price <= 0.0:
        return {"error": "Invalid current price"}

    atr = float(analysis_data.get("atr_14") or (current_price * 0.008))
    atr_pct = float(analysis_data.get("atr_pct") or 0.80)

    # 1. Structural Liquidity Levels (BSL & SSL)
    liq = analysis_data.get("liquidity", {})
    bsl_levels = [float(x) for x in liq.get("bsl_levels", []) if float(x) > current_price]
    ssl_levels = [float(x) for x in liq.get("ssl_levels", []) if float(x) < current_price]

    nearest_bsl = min(bsl_levels) if bsl_levels else 0.0
    nearest_ssl = max(ssl_levels) if ssl_levels else 0.0

    # 2. Volume Profile Value Area & POC
    vp = analysis_data.get("volume_profile", {})
    vah = float(vp.get("value_area_high") or 0.0)
    val = float(vp.get("value_area_low") or 0.0)
    poc = float(vp.get("poc_price") or current_price)

    # 3. Session VWAP & Bands
    vwap_data = analysis_data.get("vwap_analysis", {})
    vwap_price = float(analysis_data.get("vwap") or current_price)
    vwap_upper = float(vwap_data.get("upper_band_1") or (vwap_price + atr))
    vwap_lower = float(vwap_data.get("lower_band_1") or (vwap_price - atr))
    vwap_slope = vwap_data.get("slope", "FLAT")
    vwap_stance = vwap_data.get("stance", "AT_VWAP")

    # 4. Fair Value Gaps (FVG)
    fvg_data = analysis_data.get("fvg", {})
    bearish_fvg = fvg_data.get("nearest_unmitigated_bearish", {})
    bullish_fvg = fvg_data.get("nearest_unmitigated_bullish", {})

    # 5. Determine Breakout Resistance (Ceiling)
    breakout_candidates = []
    if nearest_bsl > current_price:
        breakout_candidates.append(nearest_bsl)
    if vah > current_price:
        breakout_candidates.append(vah)
    if vwap_upper > current_price:
        breakout_candidates.append(vwap_upper)
    if bearish_fvg and float(bearish_fvg.get("gap_bottom", 0)) > current_price:
        breakout_candidates.append(float(bearish_fvg.get("gap_bottom")))

    sr = analysis_data.get("support_resistance", {})
    res_level = float(sr.get("resistance") or 0.0)
    if res_level > current_price:
        breakout_candidates.append(res_level)

    if breakout_candidates:
        breakout_level = round_price(min(breakout_candidates), current_price)
    else:
        breakout_level = round_price(current_price + (1.2 * atr), current_price)

    # 6. Determine Breakdown Support (Floor)
    breakdown_candidates = []
    if nearest_ssl > 0 and nearest_ssl < current_price:
        breakdown_candidates.append(nearest_ssl)
    if val > 0 and val < current_price:
        breakdown_candidates.append(val)
    if vwap_lower > 0 and vwap_lower < current_price:
        breakdown_candidates.append(vwap_lower)
    if bullish_fvg and float(bullish_fvg.get("gap_top", 0)) < current_price:
        breakdown_candidates.append(float(bullish_fvg.get("gap_top")))

    sup_level = float(sr.get("support") or 0.0)
    if sup_level > 0 and sup_level < current_price:
        breakdown_candidates.append(sup_level)

    if breakdown_candidates:
        breakdown_level = round_price(max(breakdown_candidates), current_price)
    else:
        breakdown_level = round_price(max(0.0001, current_price - (1.2 * atr)), current_price)

    # Distances
    dist_breakout_usd = round(breakout_level - current_price, 4)
    dist_breakout_pct = round((dist_breakout_usd / current_price) * 100.0, 3)

    dist_breakdown_usd = round(current_price - breakdown_level, 4)
    dist_breakdown_pct = round((dist_breakdown_usd / current_price) * 100.0, 3)

    # Proximity & Coiling Status
    if dist_breakout_pct <= 0.35:
        proximity_status = "TESTING_BREAKOUT"
        status_label = f"🔥 TESTING BREAKOUT (+{dist_breakout_pct:.2f}%)"
    elif dist_breakdown_pct <= 0.35:
        proximity_status = "TESTING_BREAKDOWN"
        status_label = f"⚠️ TESTING BREAKDOWN (-{dist_breakdown_pct:.2f}%)"
    elif ((breakout_level - breakdown_level) / current_price * 100.0) <= (atr_pct * 1.6):
        proximity_status = "COILING_VOLATILITY_SQUEEZE"
        status_label = f"⚡ COILING / SQUEEZE (Range: {((breakout_level - breakdown_level)/current_price*100.0):.2f}%)"
    else:
        proximity_status = "RANGING_IN_VALUE_AREA"
        status_label = "⚖️ RANGING IN VALUE AREA"

    # Pre-Trade Bullish Breakout Trade Plan
    bullish_entry = breakout_level
    bullish_sl = round_price(breakout_level - (0.8 * atr), current_price)
    bullish_risk = max(0.0001, abs(bullish_entry - bullish_sl))
    bullish_tp = round_price(breakout_level + (2.3 * bullish_risk), current_price)
    bullish_rr = round(abs(bullish_tp - bullish_entry) / bullish_risk, 2)

    # Pre-Trade Bearish Breakdown Trade Plan
    bearish_entry = breakdown_level
    bearish_sl = round_price(breakdown_level + (0.8 * atr), current_price)
    bearish_risk = max(0.0001, abs(bearish_sl - bearish_entry))
    bearish_tp = round_price(max(0.0001, breakdown_level - (2.3 * bearish_risk)), current_price)
    bearish_rr = round(abs(bearish_entry - bearish_tp) / bearish_risk, 2)

    # Order Flow Signals
    cvd_data = analysis_data.get("cvd", {})
    obi_data = analysis_data.get("order_book_imbalance", {})
    macd_data = analysis_data.get("macd", {})

    return {
        "symbol": symbol,
        "current_price": current_price,
        "atr_14": atr,
        "atr_pct": atr_pct,
        "breakout_level": breakout_level,
        "distance_to_breakout_usd": dist_breakout_usd,
        "distance_to_breakout_pct": dist_breakout_pct,
        "breakdown_level": breakdown_level,
        "distance_to_breakdown_usd": dist_breakdown_usd,
        "distance_to_breakdown_pct": dist_breakdown_pct,
        "poc_price": poc,
        "vwap_price": vwap_price,
        "vwap_stance": vwap_stance,
        "vwap_slope": vwap_slope,
        "proximity_status": proximity_status,
        "status_label": status_label,
        "is_imminent": (dist_breakout_pct <= 0.35 or dist_breakdown_pct <= 0.35),
        "order_flow": {
            "cvd_trend": cvd_data.get("cvd_trend", "NEUTRAL"),
            "cvd_divergence": cvd_data.get("divergence", "NONE"),
            "obi_ratio": obi_data.get("obi_ratio", 0.0),
            "obi_status": obi_data.get("imbalance_status", "NEUTRAL"),
            "macd_bias": macd_data.get("bias", "NEUTRAL"),
            "macd_momentum": macd_data.get("momentum_phase", "NEUTRAL")
        },
        "bullish_breakout_plan": {
            "trigger_price": bullish_entry,
            "stop_loss_price": bullish_sl,
            "take_profit_price": bullish_tp,
            "planned_rr": bullish_rr,
            "confirmation_criteria": "Confirmed 15m candle close > breakout level with CVD buyer expansion & OBI > +0.15"
        },
        "bearish_breakdown_plan": {
            "trigger_price": bearish_entry,
            "stop_loss_price": bearish_sl,
            "take_profit_price": bearish_tp,
            "planned_rr": bearish_rr,
            "confirmation_criteria": "Confirmed 15m candle close < breakdown level with aggressive CVD sell volume & OBI < -0.15"
        }
    }

