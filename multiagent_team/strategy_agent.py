"""
Agent 2: Alpha & Strategy Generator.
Evaluates technical regime insights from Agent 1 and generates concrete trade setups
with explicit Entry, Stop Loss, and Take Profit targets.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("strategy-agent")


class StrategyAgent:
    def __init__(self, target_rr_ratio: float = 2.0):
        self.target_rr_ratio = target_rr_ratio

    def evaluate_setup(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single symbol analysis and generate a trade proposal if edge exists.
        """
        symbol = analysis.get("symbol")
        current_price = analysis.get("current_price", 0.0)
        regime = analysis.get("regime", "NEUTRAL")
        rsi = analysis.get("rsi_14", 50.0)
        atr = analysis.get("atr_14", current_price * 0.015)
        ema_21 = analysis.get("ema_21", current_price)
        support = analysis.get("support", current_price * 0.95)
        resistance = analysis.get("resistance", current_price * 1.05)

        if current_price <= 0 or atr <= 0:
            return None

        setup = None
        liq = analysis.get("liquidity", {})

        # -------------------------------------------------------------
        # Strategy 0: Liquidity Sweep & Smart Money Orderflow (Top Priority)
        # -------------------------------------------------------------
        if liq.get("sweep_detected"):
            sweep_type = liq.get("sweep_type")
            swept_lvl = liq.get("swept_level", current_price)
            target_lvl = liq.get("target_liquidity", current_price)

            if sweep_type == "BEARISH_BSL_SWEEP":
                # Price swept Buy-Side Liquidity (BSL) and wicked down -> SHORT targeting SSL
                entry = current_price
                stop_loss = round(max(swept_lvl * 1.002, entry + (1.2 * atr)), 2)
                stop_distance = stop_loss - entry
                if stop_distance > 0:
                    tp_target = target_lvl if target_lvl < entry else (entry - (stop_distance * self.target_rr_ratio))
                    take_profit = round(min(tp_target, entry - (stop_distance * self.target_rr_ratio)), 2)
                    setup = {
                        "symbol": symbol,
                        "strategy_name": "BSL_Sweep_Downside_Expansion",
                        "side": "sell",
                        "entry_price": entry,
                        "stop_loss_price": stop_loss,
                        "take_profit_price": take_profit,
                        "stop_distance_pct": round((stop_distance / entry) * 100, 2),
                        "planned_rr_ratio": round((entry - take_profit) / stop_distance, 2),
                        "thesis": (
                            f"Smart Money Liquidity Sweep: Price swept Buy-Side Liquidity (${swept_lvl:.2f}) "
                            f"trapping breakout buyers, then closed below. Market orderflow accelerating DOWNSIDE "
                            f"targeting Sell-Side Liquidity at ${take_profit:.2f}."
                        )
                    }

            elif sweep_type == "BULLISH_SSL_SWEEP":
                # Price swept Sell-Side Liquidity (SSL) and wicked up -> LONG targeting BSL
                entry = current_price
                stop_loss = round(min(swept_lvl * 0.998, entry - (1.2 * atr)), 2)
                stop_distance = entry - stop_loss
                if stop_distance > 0:
                    tp_target = target_lvl if target_lvl > entry else (entry + (stop_distance * self.target_rr_ratio))
                    take_profit = round(max(tp_target, entry + (stop_distance * self.target_rr_ratio)), 2)
                    setup = {
                        "symbol": symbol,
                        "strategy_name": "SSL_Sweep_Upside_Expansion",
                        "side": "buy",
                        "entry_price": entry,
                        "stop_loss_price": stop_loss,
                        "take_profit_price": take_profit,
                        "stop_distance_pct": round((stop_distance / entry) * 100, 2),
                        "planned_rr_ratio": round((take_profit - entry) / stop_distance, 2),
                        "thesis": (
                            f"Smart Money Liquidity Sweep: Price swept Sell-Side Liquidity (${swept_lvl:.2f}) "
                            f"triggering sell stops, then aggressively rejected higher. Market orderflow accelerating "
                            f"UPSIDE targeting Buy-Side Liquidity at ${take_profit:.2f}."
                        )
                    }

        if setup:
            return setup

        # -------------------------------------------------------------
        # Strategy A: Trend Following / Momentum Continuation
        # -------------------------------------------------------------
        if regime == "STRONG_BULLISH" and 50.0 <= rsi <= 72.0:
            # Long Setup
            entry = current_price
            # Stop loss placed below EMA 21 or 1.5 * ATR, whichever is tighter but realistic
            stop_loss = round(max(ema_21 * 0.995, entry - (1.5 * atr)), 2)
            stop_distance = entry - stop_loss

            if stop_distance > 0:
                # Target at least target_rr_ratio * stop_distance
                take_profit = round(entry + (stop_distance * self.target_rr_ratio), 2)
                setup = {
                    "symbol": symbol,
                    "strategy_name": "Trend_Continuation_Long",
                    "side": "buy",
                    "entry_price": entry,
                    "stop_loss_price": stop_loss,
                    "take_profit_price": take_profit,
                    "stop_distance_pct": round((stop_distance / entry) * 100, 2),
                    "planned_rr_ratio": round((take_profit - entry) / stop_distance, 2),
                    "thesis": (
                        f"Strong bullish EMA stack and positive RSI ({rsi:.1f}). "
                        f"Targeting momentum expansion with stop below dynamic EMA support."
                    )
                }

        elif regime == "STRONG_BEARISH" and 28.0 <= rsi <= 50.0:
            # Short Setup
            entry = current_price
            stop_loss = round(min(ema_21 * 1.005, entry + (1.5 * atr)), 2)
            stop_distance = stop_loss - entry

            if stop_distance > 0:
                take_profit = round(entry - (stop_distance * self.target_rr_ratio), 2)
                setup = {
                    "symbol": symbol,
                    "strategy_name": "Trend_Continuation_Short",
                    "side": "sell",
                    "entry_price": entry,
                    "stop_loss_price": stop_loss,
                    "take_profit_price": take_profit,
                    "stop_distance_pct": round((stop_distance / entry) * 100, 2),
                    "planned_rr_ratio": round((entry - take_profit) / stop_distance, 2),
                    "thesis": (
                        f"Strong bearish EMA stack and weak RSI ({rsi:.1f}). "
                        f"Targeting breakdown continuation with stop above EMA resistance."
                    )
                }

        # -------------------------------------------------------------
        # Strategy B: Mean Reversion / Key Support Bounce
        # -------------------------------------------------------------
        elif rsi < 32.0 and current_price <= (support * 1.015):
            entry = current_price
            stop_loss = round(support * 0.985, 2)
            stop_distance = entry - stop_loss

            if stop_distance > 0:
                take_profit = round(entry + (stop_distance * self.target_rr_ratio), 2)
                setup = {
                    "symbol": symbol,
                    "strategy_name": "Oversold_Support_Bounce_Long",
                    "side": "buy",
                    "entry_price": entry,
                    "stop_loss_price": stop_loss,
                    "take_profit_price": take_profit,
                    "stop_distance_pct": round((stop_distance / entry) * 100, 2),
                    "planned_rr_ratio": round((take_profit - entry) / stop_distance, 2),
                    "thesis": (
                        f"Deeply oversold RSI ({rsi:.1f}) testing structural support (${support:.2f}). "
                        f"Anticipating mean reversion bounce."
                    )
                }

        return setup

    def find_best_candidates(self, scan_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan all symbols from RegimeAnalyst and return list of qualified setups.
        """
        candidates = []
        symbols_data = scan_results.get("symbols_data", {})
        for sym, analysis in symbols_data.items():
            if not analysis.get("symbol"):
                analysis["symbol"] = sym
            setup = self.evaluate_setup(analysis)
            if setup:
                candidates.append(setup)
                
        # Rank by R:R ratio descending
        candidates.sort(key=lambda s: s.get("planned_rr_ratio", 0.0), reverse=True)
        return candidates
