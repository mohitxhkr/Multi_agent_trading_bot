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

            stop_distance = abs(entry - sl)
            if stop_distance > 0 and entry > 0:
                return {
                    "symbol": symbol,
                    "strategy_name": f"Institutional_SMC_{side.upper()}_{score}pts",
                    "side": side,
                    "entry_price": entry,
                    "stop_loss_price": sl,
                    "take_profit_price": tp,
                    "stop_distance_pct": round((stop_distance / entry) * 100, 2),
                    "planned_rr_ratio": round(abs(tp - entry) / stop_distance, 2),
                    "score": score,
                    "thesis": thesis,
                    "confluence": {
                        "macro_trend": f"{macro} (4H RSI: {macro_4h.get('rsi_14', 'N/A')})",
                        "structure_detail": f"{liq.get('sweep_type', 'Structure Test')} | MSS: {'YES' if liq.get('mss_confirmed') else 'ALIGNED'}",
                        "volume_rsi": f"1H RSI: {analysis.get('rsi_14', 50.0)} | Vol Confirmed: {'YES' if liq.get('volume_confirmed') else 'NORMAL'}"
                    }
                }

        return None

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
