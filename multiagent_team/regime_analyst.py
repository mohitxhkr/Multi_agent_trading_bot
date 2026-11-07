"""
Agent 1: Market Regime & Technical Analyst.
Analyzes 6-timeframe trends, EMA stacks, RSI, ATR, ADX, VWAP, and liquidity mapping
with pre-flight data validation, volatility expansion/contraction, and regime confidence scoring.
"""

from typing import Dict, Any, List, Optional
import logging
import time
from src.delta_client import DeltaExchangeClient
from src.technical_analysis import analyze_multi_timeframe
from multiagent_team.data_validator import MarketDataValidator

logger = logging.getLogger("regime-analyst")


class RegimeAnalystAgent:
    def __init__(self, client: DeltaExchangeClient, data_validator: Optional[MarketDataValidator] = None):
        self.client = client
        self.validator = data_validator or MarketDataValidator()

    def analyze_symbol(self, symbol: str, resolution: str = "60") -> Dict[str, Any]:
        """
        Analyze price action, indicators, and market regime with 6-timeframe confluence:
        15-Minute (Intraday execution/scalp), 1-Hour, 4-Hour, 1-Day, 1-Week, and 1-Month.
        """
        logger.info(f"RegimeAnalyst: Fetching 15m, 1H, 4H, Daily & Weekly structure for {symbol}...")
        now = int(time.time())

        # 15-Minute Candles (Primary Intraday Scalp Execution Trigger)
        candles_15m_res = self.client.get_candles(symbol, resolution="15")
        candles_15m = candles_15m_res.get("result", {}) if candles_15m_res.get("success") else None

        # Pre-flight data validation on 15m trigger series
        if candles_15m:
            val_15 = self.validator.validate_candlestick_data(symbol, candles_15m, resolution="15", min_bars_required=20)
            if not val_15["is_valid"]:
                logger.warning(f"RegimeAnalyst: 15m candles failed validation for {symbol}: {val_15['issues']}")
                # Discard corrupted 15m data so fallback to 1H is used safely
                candles_15m = None

        candles_1h_res = self.client.get_candles(symbol, resolution="60")
        if not candles_1h_res.get("success"):
            return {
                "symbol": symbol,
                "error": candles_1h_res.get("error", "Failed to fetch 1H candlestick data")
            }

        candles_1h = candles_1h_res.get("result", {})
        val_1h = self.validator.validate_candlestick_data(symbol, candles_1h, resolution="60", min_bars_required=20)
        if not val_1h["is_valid"]:
            return {
                "symbol": symbol,
                "error": f"1H Candlestick data validation failed: {'; '.join(val_1h['issues'])}"
            }

        candles_4h_res = self.client.get_candles(symbol, resolution="240")
        candles_4h = candles_4h_res.get("result", {}) if candles_4h_res.get("success") else None

        candles_1d_res = self.client.get_candles(symbol, resolution="D", from_time=now - (86400 * 365), to_time=now)
        candles_1d = candles_1d_res.get("result", {}) if candles_1d_res.get("success") else None

        candles_1w_res = self.client.get_candles(symbol, resolution="W")
        candles_1w = candles_1w_res.get("result", {}) if candles_1w_res.get("success") else None

        analysis = analyze_multi_timeframe(
            candles_1h=candles_1h,
            candles_4h=candles_4h,
            candles_1d=candles_1d,
            candles_1w=candles_1w,
            candles_15m=candles_15m,
            symbol=symbol
        )
        analysis["symbol"] = symbol.upper()
        analysis["resolution"] = resolution
        analysis["_raw_candles_15m"] = candles_15m
        analysis["_raw_candles_1h"] = candles_1h

        # Fetch live ticker for mark price, OI, and funding rate
        ticker_res = self.client.get_ticker(symbol)
        if ticker_res.get("success"):
            tick = ticker_res.get("result")
            if isinstance(tick, dict):
                # Validate ticker
                tick_val = self.validator.validate_ticker_data(symbol, tick)
                if tick_val["is_valid"]:
                    analysis["mark_price"] = float(tick.get("mark_price") or analysis.get("current_price", 0))
                    analysis["open_interest"] = tick.get("oi_contracts")
                    analysis["funding_rate"] = float(tick.get("funding_rate") or 0.0)
                    analysis["bid_price"] = float(tick.get("bid") or 0.0)
                    analysis["ask_price"] = float(tick.get("ask") or 0.0)
                    if analysis["bid_price"] > 0 and analysis["ask_price"] > 0:
                        analysis["spread_pct"] = round((analysis["ask_price"] - analysis["bid_price"]) / analysis["bid_price"] * 100, 3)

        return analysis

    def scan_universe(self, symbols: List[str], resolution: str = "60") -> Dict[str, Any]:
        """
        Analyze a list of symbols and extract multi-timeframe regime intelligence.
        """
        results = {}
        for sym in symbols:
            res = self.analyze_symbol(sym, resolution)
            if "error" not in res:
                results[sym] = res

        # Determine overall crypto market health (BTC regime anchor)
        btc_analysis = results.get("BTCUSD") or results.get("BTCUSDT")
        eth_analysis = results.get("ETHUSD") or results.get("ETHUSDT")
        overall_regime = "NEUTRAL"
        btc_adx = 20.0
        btc_vol_state = "NORMAL"
        btc_confidence = 50

        if btc_analysis:
            overall_regime = btc_analysis.get("macro_4h", {}).get("regime") or btc_analysis.get("regime", "NEUTRAL")
            btc_adx = btc_analysis.get("adx_14", 20.0)
            btc_vol_state = btc_analysis.get("volatility_state", "NORMAL")
            btc_confidence = btc_analysis.get("regime_confidence", 50)

        # 1. Market-Wide Breadth: % of watchlist trading above 20 EMA, MACD, and VWAP
        above_ema_count = 0
        macd_bullish_count = 0
        vwap_above_count = 0
        total_valid = 0
        funding_rates = []
        for s_data in results.values():
            c_price = s_data.get("current_price", 0.0)
            ema20 = s_data.get("ema_20", 0.0)
            if c_price > 0 and ema20 > 0:
                total_valid += 1
                if c_price >= ema20:
                    above_ema_count += 1
            
            # Watchlist MACD Momentum Breadth
            m_info = s_data.get("macd", {})
            if m_info.get("histogram", 0) > 0 or "BULLISH" in m_info.get("bias", ""):
                macd_bullish_count += 1

            # Watchlist Institutional VWAP Breadth
            vwap_p = s_data.get("vwap", 0.0)
            if c_price > 0 and vwap_p > 0 and c_price >= vwap_p:
                vwap_above_count += 1

            if "funding_rate" in s_data:
                funding_rates.append(s_data["funding_rate"])

        breadth_pct = round((above_ema_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0
        macd_breadth_pct = round((macd_bullish_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0
        vwap_breadth_pct = round((vwap_above_count / total_valid * 100.0), 1) if total_valid > 0 else 50.0

        # 2. ETH/BTC Relative Strength
        eth_btc_relative_strength = 1.0
        if eth_analysis and btc_analysis:
            eth_change = eth_analysis.get("price_change_24h_pct", 0.0)
            btc_change = btc_analysis.get("price_change_24h_pct", 0.0)
            eth_btc_relative_strength = round((1.0 + eth_change / 100.0) / max(0.01, 1.0 + btc_change / 100.0), 3)

        # 3. Funding Rate Skew
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
            "eth_btc_relative_strength": eth_btc_relative_strength,
            "avg_funding_rate": avg_funding,
            "funding_rate_skew": funding_skew,
            "analyzed_count": len(results),
            "symbols_data": results
        }
