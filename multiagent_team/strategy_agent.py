"""
Agent 3: Alpha & Strategy Generator.
Evaluates technical regime insights from Agent 1 and generates high-conviction trade setups
with explicit Entry, ATR-calibrated Stop Loss, Take Profit targets, VWAP alignment,
order-book spread filters, setup expiration timestamps, and strict hard veto separation.
"""

from typing import Dict, Any, List, Optional
import time
import logging
from multiagent_team.adaptive_learning import AdaptiveLearningEngine

logger = logging.getLogger("strategy-agent")


class StrategyAgent:
    def __init__(self, target_rr_ratio: float = 2.0, max_allowed_spread_pct: float = 0.15):
        self.target_rr_ratio = target_rr_ratio
        self.max_allowed_spread_pct = max_allowed_spread_pct
        self.adaptive_learner = AdaptiveLearningEngine()

    def evaluate_setup(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single symbol analysis and generate a trade proposal ONLY if high-probability edge exists.
        Separates Hard Rejection Gates from Strategy Scoring.
        """
        symbol = analysis.get("symbol")
        hp_setup = analysis.get("high_probability_setup")

        if not hp_setup or not hp_setup.get("qualified"):
            return None

        # -------------------------------------------------------------
        # 1. Hard Rejection Gates (Vetoes)
        # -------------------------------------------------------------
        # Hard Veto A: Major economic news / abnormal volatility spike
        if analysis.get("news_blocked"):
            logger.warning(f"StrategyAgent VETO on {symbol}: {analysis.get('news_reason')}")
            return None

        # Hard Veto B: Excessive bid-ask spread / illiquid book
        spread_pct = float(analysis.get("spread_pct") or 0.0)
        if spread_pct > self.max_allowed_spread_pct:
            logger.warning(f"StrategyAgent VETO on {symbol}: Spread {spread_pct}% exceeds max allowed {self.max_allowed_spread_pct}%")
            return None

        # Hard Veto C: Extreme entry price deviation
        current_price = float(analysis.get("current_price") or 0.0)
        entry = float(hp_setup.get("entry_price") or current_price)
        if entry > 0 and current_price > 0:
            price_deviation_pct = abs(current_price - entry) / entry * 100.0
            if price_deviation_pct > 0.50:
                logger.warning(f"StrategyAgent VETO on {symbol}: Price has drifted {price_deviation_pct:.2f}% from optimal entry ${entry:.2f}")
                return None

        side = hp_setup.get("side")
        sl = float(hp_setup.get("stop_loss_price") or 0.0)
        tp = float(hp_setup.get("take_profit_price") or 0.0)
        score = int(hp_setup.get("score") or 70)
        thesis = hp_setup.get("thesis", "High probability edge verified.")
        macro_4h = analysis.get("macro_4h", {})
        macro_daily = analysis.get("macro_daily", {})
        macro_weekly = analysis.get("macro_weekly", {})
        macro_monthly = analysis.get("macro_monthly", {})
        macro_15m = analysis.get("macro_15m", {})
        liq = analysis.get("liquidity", {})

        # ATR-Adjusted Stop Loss Dynamic Calibration
        atr_15m = float(macro_15m.get("atr_14") or analysis.get("atr_14") or (entry * 0.005))
        min_sl_dist = 0.8 * atr_15m
        max_sl_dist = 1.6 * atr_15m
        raw_sl_dist = abs(entry - sl)
        calibrated_sl_dist = max(min_sl_dist, min(raw_sl_dist, max_sl_dist))

        if side == "buy":
            sl = round(entry - calibrated_sl_dist, 4)
            tp = round(entry + (self.target_rr_ratio * calibrated_sl_dist), 4)
        else:
            sl = round(entry + calibrated_sl_dist, 4)
            tp = round(entry - (self.target_rr_ratio * calibrated_sl_dist), 4)

        stop_distance = abs(entry - sl)
        if stop_distance <= 0 or entry <= 0:
            return None

        # -------------------------------------------------------------
        # 2. Strategy Confluence Scoring
        # -------------------------------------------------------------
        is_primary = any(p in (symbol or "").upper() for p in ["BTC", "ETH", "XAU", "GOLD"])
        priority_tag = "PRIMARY" if is_primary else "SECONDARY"
        adjusted_score = score + (10 if is_primary else 0)

        # VWAP Institutional Level Alignment
        vwap_val = float(analysis.get("vwap") or 0.0)
        if vwap_val > 0:
            if (side == "buy" and current_price >= vwap_val * 0.998) or (side == "sell" and current_price <= vwap_val * 1.002):
                adjusted_score += 5  # Aligned with institutional VWAP
            else:
                adjusted_score -= 5  # Fighting immediate VWAP gravity

        # Adaptive Learning Check
        raw_strat = hp_setup.get("strategy") or f"Institutional_SMC_{priority_tag}_{side.upper()}"
        confluence_summary = {
            "macro_4h": macro_4h.get("regime", "NEUTRAL"),
            "macro_daily": macro_daily.get("regime", "NEUTRAL")
        }
        pat_check = self.adaptive_learner.get_pattern_adjustment(
            symbol=symbol,
            side=side,
            strategy=raw_strat,
            confluence=confluence_summary
        )

        if not pat_check.get("can_trade", True):
            logger.warning(f"StrategyAgent VETO: Pattern blacklisted: {pat_check.get('reason')}")
            return None

        pat_adj = pat_check.get("score_adjustment", 0)
        adjusted_score += pat_adj
        if pat_adj > 0:
            thesis = f"⚡ [REINFORCED PATTERN +{pat_adj}pts] {thesis}"
        elif pat_adj < 0:
            thesis = f"⚠️ [PENALIZED PATTERN {pat_adj}pts] {thesis}"

        # Strict Sniper Quality Floor: 85 / 100 for Primary (BTC, ETH, XAU), 90 / 100 for Secondary
        # Enforces 'Take less trades, but more accurate for maximum profit'
        min_threshold = 85 if is_primary else 90
        if adjusted_score < min_threshold:
            return None

        formatted_thesis = f"🌟 [PRIMARY FOCUS ASSET] {thesis}" if is_primary else f"⚪ [SECONDARY ASSET] {thesis}"
        now_ts = time.time()
        expires_at = now_ts + 3600  # Valid for 60 minutes

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
            "expires_at": expires_at,
            "created_at": now_ts,
            "vwap": vwap_val,
            "spread_pct": spread_pct,
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
