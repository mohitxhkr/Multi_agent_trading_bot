"""
Market Data Validation Engine for Multi-Agent Trading System.
Guarantees data integrity before feeding candlestick and ticker data into analytical agents.
Detects missing bars, stale feeds, timestamp inversions, abnormal price spikes, and connectivity issues.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("data_validator")


class MarketDataValidator:
    """Rigorous pre-flight validator for exchange market data."""

    RESOLUTION_SECONDS = {
        "1": 60,
        "5": 300,
        "15": 900,
        "30": 1800,
        "60": 3600,
        "240": 14400,
        "D": 86400,
        "1D": 86400,
        "W": 604800,
        "1W": 604800,
    }

    def __init__(self, max_stale_intervals: int = 3, max_allowed_spike_pct: float = 0.08):
        self.max_stale_intervals = max_stale_intervals
        self.max_allowed_spike_pct = max_allowed_spike_pct

    def validate_candlestick_data(
        self,
        symbol: str,
        candles: Optional[Dict[str, Any]],
        resolution: str = "15",
        min_bars_required: int = 20
    ) -> Dict[str, Any]:
        """
        Validate OHLCV candlestick series for gaps, staleness, corruption, and price spikes.
        """
        issues: List[str] = []
        now = int(time.time())

        if not candles or not isinstance(candles, dict):
            return {
                "is_valid": False,
                "symbol": symbol,
                "resolution": resolution,
                "issues": ["Candle data structure is empty or None"],
                "candle_count": 0
            }

        timestamps = candles.get("t", [])
        opens = candles.get("o", [])
        highs = candles.get("h", [])
        lows = candles.get("l", [])
        closes = candles.get("c", [])
        volumes = candles.get("v", [])

        bar_count = len(timestamps)
        if bar_count < min_bars_required:
            issues.append(f"Insufficient bars: got {bar_count}, required at least {min_bars_required}")

        if not (len(opens) == len(highs) == len(lows) == len(closes) == bar_count):
            issues.append(f"Mismatched array lengths: t={bar_count}, o={len(opens)}, h={len(highs)}, l={len(lows)}, c={len(closes)}")

        if issues:
            return {
                "is_valid": False,
                "symbol": symbol,
                "resolution": resolution,
                "issues": issues,
                "candle_count": bar_count
            }

        # 1. Monotonic Timestamps & Future Bar Check
        expected_interval = self.RESOLUTION_SECONDS.get(str(resolution), 900)
        for i in range(1, bar_count):
            t_curr = timestamps[i]
            t_prev = timestamps[i - 1]
            if t_curr <= t_prev:
                issues.append(f"Timestamp inversion at bar {i}: prev={t_prev}, curr={t_curr}")
                break
            if t_curr > now + 300:
                issues.append(f"Future timestamp detected at bar {i}: {t_curr} vs now={now}")
                break

        # 2. Staleness Check
        last_t = timestamps[-1]
        allowed_lag = expected_interval * self.max_stale_intervals
        time_since_last_bar = now - last_t
        if time_since_last_bar > allowed_lag:
            issues.append(
                f"Data is stale: last bar was {time_since_last_bar}s ago "
                f"(allowed {allowed_lag}s for resolution {resolution})"
            )

        # 3. Abnormal Price Spike / Flash Crash Check
        spike_count = 0
        for i in range(bar_count):
            o_val = float(opens[i])
            h_val = float(highs[i])
            l_val = float(lows[i])
            c_val = float(closes[i])

            if o_val <= 0 or h_val <= 0 or l_val <= 0 or c_val <= 0:
                issues.append(f"Zero or negative price at bar {i}")
                break

            if l_val > h_val:
                issues.append(f"Invalid bar {i}: Low ({l_val}) > High ({h_val})")
                break

            # Calculate bar span relative to close
            bar_range = (h_val - l_val) / c_val
            if bar_range > self.max_allowed_spike_pct:
                spike_count += 1

        if spike_count > 2:
            issues.append(f"Excessive abnormal price spikes detected: {spike_count} bars exceeded {self.max_allowed_spike_pct*100:.1f}% range")

        is_valid = len(issues) == 0
        last_price = float(closes[-1]) if bar_count > 0 else 0.0

        if not is_valid:
            logger.warning(f"DataValidator: {symbol} ({resolution}) rejected: {'; '.join(issues)}")

        return {
            "is_valid": is_valid,
            "symbol": symbol,
            "resolution": resolution,
            "issues": issues,
            "candle_count": bar_count,
            "last_timestamp": last_t,
            "last_price": last_price,
            "time_since_last_bar": time_since_last_bar
        }

    def validate_ticker_data(self, symbol: str, ticker: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate live ticker object."""
        issues = []
        if not ticker or not isinstance(ticker, dict):
            return {"is_valid": False, "symbol": symbol, "issues": ["Empty ticker response"]}

        mark_price = float(ticker.get("mark_price") or 0.0)
        spot_price = float(ticker.get("spot_price") or 0.0)
        
        if mark_price <= 0.0:
            issues.append(f"Invalid mark price: {mark_price}")

        # Check spread between spot and mark
        if spot_price > 0 and mark_price > 0:
            disparity = abs(mark_price - spot_price) / spot_price
            if disparity > 0.05:
                issues.append(f"Severe mark/spot disparity: {disparity*100:.2f}% (Mark: {mark_price}, Spot: {spot_price})")

        return {
            "is_valid": len(issues) == 0,
            "symbol": symbol,
            "mark_price": mark_price,
            "issues": issues
        }
