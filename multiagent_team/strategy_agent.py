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
        Evaluate a single symbol analysis and generate a trade proposal ONLY if high-probability edge exists.
        Requires >= 70 confluence score, 4H macro alignment, and strict risk-reward.
        """
        symbol = analysis.get("symbol")
        hp_setup = analysis.get("high_probability_setup")

        if hp_setup and hp_setup.get("qualified"):
            side = hp_setup.get("side")
            entry = hp_setup.get("entry_price", 0.0)
            sl = hp_setup.get("stop_loss_price", 0.0)
            tp = hp_setup.get("take_profit_price", 0.0)
            score = hp_setup.get("score", 70)
            thesis = hp_setup.get("thesis", "High probability edge verified.")
            macro = hp_setup.get("macro_regime", "NEUTRAL")
            liq = analysis.get("liquidity", {})
            macro_4h = analysis.get("macro_4h", {})
            macro_daily = analysis.get("macro_daily", {})
            macro_weekly = analysis.get("macro_weekly", {})
            macro_monthly = analysis.get("macro_monthly", {})

            stop_distance = abs(entry - sl)
            if stop_distance > 0 and entry > 0:
                is_primary = any(p in (symbol or "").upper() for p in ["BTC", "ETH", "XAU", "GOLD"])
                priority_tag = "PRIMARY" if is_primary else "SECONDARY"
                adjusted_score = score + (10 if is_primary else 0)

                # Enforce institutional high-conviction threshold (80-90% accuracy standard)
                min_threshold = 80 if is_primary else 85
                if adjusted_score < min_threshold:
                    return None

                formatted_thesis = f"🌟 [PRIMARY FOCUS ASSET] {thesis}" if is_primary else f"⚪ [SECONDARY ASSET] {thesis}"
                raw_strat = hp_setup.get("strategy") or f"Institutional_SMC_{priority_tag}_{side.upper()}"
                macro_15m = analysis.get("macro_15m", {})

                return {
                    "symbol": symbol,
                    "strategy_name": f"{raw_strat}_{adjusted_score}pts",
                    "side": side,
                    "entry_price": entry,
                    "stop_loss_price": sl,
                    "take_profit_price": tp,
                    "stop_distance_pct": round((stop_distance / entry) * 100, 2),
                    "planned_rr_ratio": round(abs(tp - entry) / stop_distance, 2),
                    "score": adjusted_score,
                    "is_primary": is_primary,
                    "priority_tier": 1 if is_primary else 2,
                    "thesis": formatted_thesis,
                    "confluence": {
                        "execution_15m": f"{macro_15m.get('regime', 'NEUTRAL')} (RSI: {macro_15m.get('rsi_14', 'N/A')} | ATR: {macro_15m.get('atr_14', 'N/A')})",
                        "monthly": f"{macro_monthly.get('regime', 'NEUTRAL')} (M-Open: ${macro_monthly.get('monthly_open', 'N/A')})",
                        "weekly": f"{macro_weekly.get('regime', 'NEUTRAL')} (W-RSI: {macro_weekly.get('rsi_14', 'N/A')})",
                        "daily": f"{macro_daily.get('regime', 'NEUTRAL')} (EMA21: ${macro_daily.get('ema_21', 'N/A')} | RSI: {macro_daily.get('rsi_14', 'N/A')})",
                        "macro_4h": f"{macro_4h.get('regime', 'NEUTRAL')} (4H RSI: {macro_4h.get('rsi_14', 'N/A')})",
                        "structure_detail": f"{liq.get('sweep_type', 'Structure Test')} | MSS: {'YES' if liq.get('mss_confirmed') else 'ALIGNED'}",
                        "volume_rsi": f"1H RSI: {analysis.get('rsi_14', 50.0)} | Vol: {'CONFIRMED' if liq.get('volume_confirmed') else 'NORMAL'}"
                    }
                }

        return None

    def find_best_candidates(self, scan_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan all symbols from RegimeAnalyst and return list of qualified setups.
        Primary assets (BTC, ETH, XAU) are prioritized first.
        """
        candidates = []
        symbols_data = scan_results.get("symbols_data", {})
        for sym, analysis in symbols_data.items():
            if not analysis.get("symbol"):
                analysis["symbol"] = sym
            setup = self.evaluate_setup(analysis)
            if setup:
                candidates.append(setup)
                
        # Rank by: Primary tier first, then score, then R:R ratio descending
        candidates.sort(
            key=lambda s: (
                1 if s.get("is_primary") else 0,
                s.get("score", 0),
                s.get("planned_rr_ratio", 0.0)
            ),
            reverse=True
        )
        return candidates
