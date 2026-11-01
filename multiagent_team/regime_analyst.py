"""
Agent 1: Market Regime & Technical Analyst.
Analyzes multi-timeframe trends, EMA stacks, RSI, ATR, and support/resistance
to determine market posture and directional bias.
"""

from typing import Dict, Any, List
import logging
from src.delta_client import DeltaExchangeClient
from src.technical_analysis import analyze_multi_timeframe

logger = logging.getLogger("regime-analyst")


class RegimeAnalystAgent:
    def __init__(self, client: DeltaExchangeClient):
        self.client = client

    def analyze_symbol(self, symbol: str, resolution: str = "60") -> Dict[str, Any]:
        """
        Analyze price action, indicators, and market regime with multi-timeframe 1H + 4H confluence.
        """
        logger.info(f"RegimeAnalyst: Fetching 1H & 4H structure for {symbol}...")
        candles_1h_res = self.client.get_candles(symbol, resolution="60")
        if not candles_1h_res.get("success"):
            return {
                "symbol": symbol,
                "error": candles_1h_res.get("error", "Failed to fetch 1H candlestick data")
            }

        candles_4h_res = self.client.get_candles(symbol, resolution="240")
        candles_4h = candles_4h_res.get("result", {}) if candles_4h_res.get("success") else None

        candles_1h = candles_1h_res.get("result", {})
        analysis = analyze_multi_timeframe(candles_1h, candles_4h)
        analysis["symbol"] = symbol.upper()
        analysis["resolution"] = resolution

        # Fetch live ticker for open interest and mark price
        ticker_res = self.client.get_ticker(symbol)
        if ticker_res.get("success"):
            tick = ticker_res.get("result")
            if isinstance(tick, dict):
                analysis["mark_price"] = float(tick.get("mark_price") or analysis.get("current_price", 0))
                analysis["open_interest"] = tick.get("oi_contracts")
                analysis["funding_rate"] = tick.get("funding_rate")

        return analysis

    def scan_universe(self, symbols: List[str], resolution: str = "60") -> Dict[str, Any]:
        """
        Analyze a list of symbols and rank them by regime clarity and momentum.
        """
        results = {}
        for sym in symbols:
            res = self.analyze_symbol(sym, resolution)
            if "error" not in res:
                results[sym] = res

        # Determine overall crypto market health (BTC regime anchor)
        btc_analysis = results.get("BTCUSD") or results.get("BTCUSDT")
        overall_regime = "NEUTRAL"
        if btc_analysis:
            overall_regime = btc_analysis.get("macro_4h", {}).get("regime") or btc_analysis.get("regime", "NEUTRAL")

        return {
            "overall_market_regime": overall_regime,
            "analyzed_count": len(results),
            "symbols_data": results
        }
