"""
Agent 2: Exposure Coach & Market Posture Engine.
Synthesizes market-wide breadth, BTC dominance, altcoin relative strength,
aggregate funding rates, open portfolio exposure, and consecutive trade outcomes
to dictate portfolio risk budgets, volatility postures, and recovery modes.
"""

from typing import Dict, Any, List, Optional
import os
import json
import time
import logging

logger = logging.getLogger("exposure-coach")

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
POSTURE_STATE_FILE = os.path.join(STATE_DIR, "market_posture_state.json")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


class ExposureCoachAgent:
    """
    Evaluates global market conditions to dictate portfolio risk budget:
    1. AGGRESSIVE_EXPANSION (Health >= 75): 100% risk budget, up to 3 positions.
    2. MODERATE_SELECTIVE (Health 50-74): 75% risk budget, Tier-1 focus only (BTC/ETH/XAU).
    3. DEFENSIVE_CAUTION (Health 32-49): 50% risk budget, max 1 position, tighter invalidation.
    4. RECOVERY_POSTURE: Triggered after 2 consecutive losses. Slashes risk to 40-50% and limits to 1 position.
    5. CASH_PRIORITY (Health < 32): 0% risk budget. ALL new entries blocked. Cash preserved.
    """
    def __init__(self):
        self.state_file = POSTURE_STATE_FILE

    def _check_consecutive_losses(self) -> int:
        """Check the number of trailing consecutive losses from trade journal."""
        journal_file = os.path.join(STATE_DIR, "trade_journal.json")
        if not os.path.exists(journal_file):
            return 0
        try:
            with open(journal_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                trades = data.get("trades", [])
                losses = 0
                for t in reversed(trades):
                    outcome = t.get("outcome", "").upper()
                    if outcome in ["LOSS", "STOP_LOSS", "FAILED"]:
                        losses += 1
                    elif outcome in ["WIN", "TAKE_PROFIT", "SUCCESS"]:
                        break
                return losses
        except Exception:
            return 0

    def evaluate_market_posture(
        self,
        scan_results: Dict[str, Any],
        wallet_equity: float = 100.0,
        active_positions_count: int = 0,
        open_margin_utilization_pct: float = 0.0
    ) -> Dict[str, Any]:
        """
        Synthesize cross-asset indicators into a deterministic Market Health score (0-100)
        and establish the Exposure Posture.
        """
        symbols_data = scan_results.get("symbols_data", {})
        total_symbols = len(symbols_data)
        
        if total_symbols == 0:
            return {
                "health_score": 50,
                "posture": "MODERATE_SELECTIVE",
                "cash_priority": False,
                "exposure_ceiling_pct": 25.0,
                "max_allowed_positions": 2,
                "risk_multiplier": 0.85,
                "rationale": "Insufficient universe data; adopting neutral moderate posture."
            }

        # 1. Market Breadth: % of assets trading above their 15m/1H 21 EMA
        above_ema_count = 0
        funding_rates = []
        macro_bull_count = 0
        macro_bear_count = 0
        alt_strengths = []

        btc_data = symbols_data.get("BTCUSD", {})
        btc_price = btc_data.get("current_price", 1.0)
        btc_vol_state = btc_data.get("volatility_state", "NORMAL")

        for sym, d in symbols_data.items():
            price = d.get("current_price", 0.0)
            m15 = d.get("macro_15m", {})
            ema21 = m15.get("ema_21", price)
            if price >= ema21 and ema21 > 0:
                above_ema_count += 1

            h4 = d.get("macro_4h", {}).get("regime", "")
            if "BULLISH" in h4:
                macro_bull_count += 1
            elif "BEARISH" in h4:
                macro_bear_count += 1

            fr = d.get("funding_rate")
            if fr is not None:
                try:
                    funding_rates.append(float(fr))
                except (ValueError, TypeError):
                    pass

            # Altcoin Relative Strength against BTC
            if sym != "BTCUSD" and btc_price > 0:
                d_pct = d.get("macro_daily", {}).get("rsi_14", 50.0)
                btc_rsi = btc_data.get("macro_daily", {}).get("rsi_14", 50.0)
                alt_strengths.append(d_pct - btc_rsi)

        breadth_pct = (above_ema_count / total_symbols) * 100.0
        bearish_breadth_pct = ((total_symbols - above_ema_count) / total_symbols) * 100.0
        avg_alt_rs = (sum(alt_strengths) / len(alt_strengths)) if alt_strengths else 0.0
        
        # 2. BTC Anchor Health (35 pts max) & Directional Trend Detection
        btc_h4 = btc_data.get("macro_4h", {}).get("regime", "MACRO_NEUTRAL")
        is_macro_bearish = "BEARISH" in btc_h4 or (macro_bear_count >= macro_bull_count and macro_bear_count >= total_symbols * 0.5)

        # Detect Unified Bearish Trend Expansion (Sell-off / Dump regime)
        is_bearish_expansion = is_macro_bearish and bearish_breadth_pct >= 60.0

        if is_bearish_expansion:
            direction_bias = "SHORTS_ONLY"
            # In a macro sell-off, bearish alignment gives full directional conviction
            btc_trend_score = 35
            breadth_score = (bearish_breadth_pct / 100.0) * 45.0
        else:
            direction_bias = "LONGS_ONLY" if ("BULLISH" in btc_h4 and breadth_pct >= 60.0) else "BOTH"
            btc_trend_score = 35 if "BULLISH" in btc_h4 else (10 if "BEARISH" in btc_h4 else 20)
            breadth_score = (breadth_pct / 100.0) * 45.0

        # 4. Funding Rate Sentiment Alignment (20 pts max)
        avg_funding = (sum(funding_rates) / len(funding_rates)) if funding_rates else 0.0001
        extreme_crowding = False
        crowding_note = ""

        if avg_funding > 0.04:
            funding_score = 5
            extreme_crowding = True
            crowding_note = f"Extreme long crowding (avg funding {avg_funding*100:.3f}%). High squeeze risk."
        elif avg_funding < -0.04:
            funding_score = 8
            extreme_crowding = True
            crowding_note = f"Extreme short crowding (avg funding {avg_funding*100:.3f}%). Aggressive short cascade risk."
        elif -0.015 <= avg_funding <= 0.015:
            funding_score = 20
        else:
            funding_score = 14

        # 5. Open Exposure Penalty (if portfolio already heavily loaded)
        exposure_penalty = 0
        if active_positions_count >= 2:
            exposure_penalty += 8
        if open_margin_utilization_pct > 35.0:
            exposure_penalty += 12

        health_score = int(round(btc_trend_score + breadth_score + funding_score - exposure_penalty))
        health_score = max(0, min(100, health_score))

        # Check for Recovery Posture
        consecutive_losses = self._check_consecutive_losses()
        in_recovery_mode = consecutive_losses >= 2

        # Classify Market Posture
        if in_recovery_mode:
            posture = "RECOVERY_POSTURE"
            cash_priority = False
            direction_bias = "BOTH"
            exposure_ceiling_pct = 15.0
            max_positions = 1
            risk_mult = 0.50
            rationale = (
                f"RECOVERY POSTURE ENGAGED after {consecutive_losses} consecutive stop losses. "
                f"Risk slashed to 50% ($2.00 max risk) and concurrency clamped to 1 position until win confirmed."
            )
        elif is_bearish_expansion and health_score >= 50:
            posture = "BEARISH_TREND_EXPANSION"
            cash_priority = False
            direction_bias = "SHORTS_ONLY"
            exposure_ceiling_pct = 35.0
            max_positions = 2
            risk_mult = 0.90
            rationale = (
                f"Unified Bearish Trend Expansion ({bearish_breadth_pct:.0f}% assets < EMA21, BTC 4H Bearish). "
                f"High-conviction SHORT setups authorized. Counter-trend longs strictly vetoed."
            )
        elif health_score >= 75:
            posture = "AGGRESSIVE_EXPANSION"
            cash_priority = False
            direction_bias = "LONGS_ONLY" if breadth_pct >= 65.0 else "BOTH"
            exposure_ceiling_pct = 30.0
            max_positions = 2
            risk_mult = 1.0
            rationale = f"Strong multi-asset breadth ({breadth_pct:.0f}% > EMA21) & aligned BTC macro momentum. Full risk authorized."
        elif health_score >= 50:
            posture = "MODERATE_SELECTIVE"
            cash_priority = False
            direction_bias = "BOTH"
            exposure_ceiling_pct = 25.0
            max_positions = 2
            risk_mult = 0.85
            rationale = f"Selective market structure ({breadth_pct:.0f}% breadth). Tier-1 core focus (BTC/ETH/XAU) with standard risk."
        elif health_score >= 32:
            posture = "DEFENSIVE_CAUTION"
            cash_priority = False
            direction_bias = "BOTH"
            exposure_ceiling_pct = 15.0
            max_positions = 1
            risk_mult = 0.65
            rationale = f"Deteriorating market participation ({breadth_pct:.0f}% breadth). Capital defense engaged; max 1 position with tighter stops."
        else:
            posture = "CASH_PRIORITY"
            cash_priority = True
            direction_bias = "NEUTRAL"
            exposure_ceiling_pct = 0.0
            max_positions = 0
            risk_mult = 0.0
            rationale = f"Market structure broken / severe chop ({breadth_pct:.0f}% breadth, Health: {health_score}/100). ZERO new trades authorized. 100% Cash Priority."

        # Volatility Posture Adjustment - Enable Pro Momentum Scalp Execution
        if btc_vol_state == "EXPANSION" and not cash_priority:
            risk_mult = max(0.90, risk_mult)
            rationale += " [High Volatility Expansion: Pro Momentum Scalp Mode active with tight ATR stops]."

        if extreme_crowding and crowding_note:
            rationale += f" [{crowding_note}]"

        posture_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "health_score": health_score,
            "posture": posture,
            "cash_priority": cash_priority,
            "direction_bias": direction_bias,
            "breadth_pct": round(breadth_pct, 1),
            "bearish_breadth_pct": round(bearish_breadth_pct, 1),
            "btc_macro_regime": btc_h4,
            "btc_volatility_state": btc_vol_state,
            "avg_funding_rate": round(avg_funding, 6),
            "alt_relative_strength": round(avg_alt_rs, 2),
            "exposure_ceiling_pct": exposure_ceiling_pct,
            "max_allowed_positions": max_positions,
            "risk_multiplier": risk_mult,
            "active_positions_count": active_positions_count,
            "consecutive_losses": consecutive_losses,
            "extreme_crowding": extreme_crowding,
            "rationale": rationale
        }

        self._save_posture(posture_data)
        return posture_data

    def _save_posture(self, data: Dict[str, Any]):
        ensure_state_dir()
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving posture state: {e}")

    def load_cached_posture(self) -> Optional[Dict[str, Any]]:
        ensure_state_dir()
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def format_telegram_posture(self, posture_data: Optional[Dict[str, Any]] = None) -> str:
        """Format Market Posture digest for Telegram command /posture."""
        if not posture_data:
            posture_data = self.load_cached_posture() or {}

        health = posture_data.get("health_score", 50)
        posture = posture_data.get("posture", "MODERATE_SELECTIVE")
        breadth = posture_data.get("breadth_pct", 50.0)
        btc_flow = posture_data.get("btc_macro_regime", "MACRO_NEUTRAL").replace("MACRO_", "")
        ceiling = posture_data.get("exposure_ceiling_pct", 25.0)
        max_pos = posture_data.get("max_allowed_positions", 2)
        cash_pri = posture_data.get("cash_priority", False)
        losses = posture_data.get("consecutive_losses", 0)
        rationale = posture_data.get("rationale", "Normal trading posture active.")

        status_badge = (
            "🔴 CASH PRIORITY" if cash_pri
            else ("🩹 RECOVERY POSTURE" if posture == "RECOVERY_POSTURE"
                  else ("🟢 AGGRESSIVE EXPANSION" if posture == "AGGRESSIVE_EXPANSION"
                        else ("🟡 MODERATE SELECTIVE" if posture == "MODERATE_SELECTIVE"
                              else "🟠 DEFENSIVE CAUTION")))
        )

        lines = [
            "🧭 <b>[MARKET POSTURE & EXPOSURE COACH]</b>",
            "<i>Agent 2: Cross-Asset Breadth & Regime Health Assessment</i>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Market Posture:</b> <b>{status_badge}</b>",
            f"• <b>Market Health Score:</b> <b>{health}/100</b>",
            f"• <b>Participation Breadth:</b> <b>{breadth:.1f}%</b> (> 21 EMA)",
            f"• <b>BTC Macro Flow:</b> <code>{btc_flow}</code>",
            f"• <b>Net Exposure Ceiling:</b> <b>{ceiling:.0f}% of Wallet</b>",
            f"• <b>Max Concurrency:</b> <b>{max_pos} Active Position(s)</b>",
            f"• <b>Consecutive Loss Count:</b> <b>{losses}</b>",
            f"• <b>Cash Priority State:</b> <b>{'ACTIVE (New Entries Blocked)' if cash_pri else 'INACTIVE (Risk Permitted)'}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📝 <b>Coach Guidance:</b>",
            f"<i>{rationale}</i>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "⚡ <i>Evaluated before every trading cycle to protect capital during market regime shifts.</i>"
        ]
        return "\n".join(lines)
