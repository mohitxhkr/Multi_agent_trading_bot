"""
Agent 6: Adaptive Learning, Pattern Diagnosis & Self-Reflection Engine.
Performs an automated post-mortem audit after every completed trade to:
1. Analyze P&L, R-multiple captured, and execution discipline.
2. Self-score each trade (0-100) and assign an institutional letter grade (A+ to F).
3. Diagnose exact root causes of wins vs losses (pattern feature attribution).
4. Maintain persistent pattern memory: reinforce winning patterns and avoid/blacklist failing patterns.
5. Provide score adjustments and veto directives to StrategyAgent & RiskGatekeeper.
"""

from typing import Dict, Any, List, Optional
import os
import json
import time
import logging

logger = logging.getLogger("adaptive-learning")

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
MEMORY_FILE = os.path.join(STATE_DIR, "pattern_learning_memory.json")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


class AdaptiveLearningEngine:
    def __init__(self, memory_path: Optional[str] = None):
        self.memory_path = memory_path or MEMORY_FILE
        self.memory = self._load_memory()

    def _load_memory(self) -> Dict[str, Any]:
        ensure_state_dir()
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading adaptive pattern memory: {e}")
        
        # Default fresh memory structure
        return {
            "version": "2.0.0",
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "scorecard": {
                "total_completed_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "breakeven_trades": 0,
                "win_rate_pct": 0.0,
                "cumulative_pnl_usd": 0.0,
                "average_trade_score": 0.0,
                "profit_factor": 0.0
            },
            "patterns": {},
            "recent_reflections": []
        }

    def _save_memory(self):
        ensure_state_dir()
        self.memory["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        try:
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving adaptive pattern memory: {e}")

    def _derive_pattern_key(self, symbol: str, side: str, strategy: str, confluence: Dict[str, Any]) -> str:
        """Derive a normalized pattern signature key from trade attributes."""
        sym = (symbol or "UNKNOWN").upper()
        # Clean symbol prefix (e.g. BTCUSD -> BTC)
        asset_base = "BTC" if "BTC" in sym else ("ETH" if "ETH" in sym else ("XAU" if "XAU" in sym else sym))
        
        dir_tag = (side or "BUY").upper()
        strat = (strategy or "").upper()
        
        if "SSL" in strat or "SELL_SIDE" in strat:
            pattern_type = "SSL_SWEEP"
        elif "BSL" in strat or "BUY_SIDE" in strat:
            pattern_type = "BSL_SWEEP"
        elif "PULLBACK" in strat or "EMA" in strat:
            pattern_type = "EMA_PULLBACK"
        else:
            pattern_type = "STRUCTURE_BREAKOUT"

        h4 = confluence.get("macro_4h", "ALIGNED").upper()
        trend_context = "TREND_ALIGNED" if ("BULL" in h4 and dir_tag == "BUY") or ("BEAR" in h4 and dir_tag == "SELL") else "COUNTER_OR_NEUTRAL"

        return f"{asset_base}_{pattern_type}_{dir_tag}_{trend_context}"

    def score_trade(
        self,
        symbol: str,
        side: str,
        realized_pnl: float,
        r_multiple: float,
        exit_reason: str,
        trade_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate and score completed trade from 0 to 100 points based on:
        1. Execution Discipline (0-30 pts)
        2. Trend & Confluence Quality (0-40 pts)
        3. Edge Realization & Asymmetric Payout (0-30 pts)
        """
        is_win = realized_pnl > 0.01
        is_be = abs(realized_pnl) <= 0.05 or exit_reason == "BREAKEVEN"
        is_loss = realized_pnl < -0.05

        # 1. Execution Discipline (30 pts max)
        discipline_score = 30
        dollar_risk = trade_spec.get("dollar_risk_usd", 4.0)
        # Penalize if realized loss exceeded predetermined max risk by > 20%
        if is_loss and abs(realized_pnl) > (dollar_risk * 1.25):
            discipline_score = 15
        elif not is_win and not is_be:
            discipline_score = 25  # Took disciplined stop loss cleanly

        # 2. Confluence & Trend Alignment (40 pts max)
        confluence_score = 40
        confluence = trade_spec.get("confluence", {})
        h4 = str(confluence.get("macro_4h", "")).upper()
        # Check if trade was with the macro trend
        if side.upper() == "BUY" and "BEAR" in h4:
            confluence_score = 15  # Counter-trend penalty
        elif side.upper() == "SELL" and "BULL" in h4:
            confluence_score = 15  # Counter-trend penalty

        # 3. Edge Realization (30 pts max)
        edge_score = 0
        if r_multiple >= 2.0 or exit_reason == "TAKE_PROFIT":
            edge_score = 30  # Full TP target hit
        elif r_multiple >= 1.20:
            edge_score = 25  # Trailing stop locked major profit
        elif r_multiple >= 0.35 or is_win:
            edge_score = 20  # Micro-profit captured
        elif is_be:
            edge_score = 18  # Capital preserved at breakeven
        else:
            edge_score = 5   # Stopped out

        total_score = min(100, max(10, discipline_score + confluence_score + edge_score))

        # Letter Grade
        if total_score >= 90:
            grade = "A+ (Flawless Institutional Execution)"
        elif total_score >= 80:
            grade = "A (High-Edge Profitable Capture)"
        elif total_score >= 70:
            grade = "B (Disciplined Controlled Execution)"
        elif total_score >= 60:
            grade = "C (Marginal Outcome / Breakeven)"
        else:
            grade = "F (Sub-Par Confluence / Counter-Trend Flaw)"

        return {
            "total_score": total_score,
            "grade": grade,
            "discipline_score": discipline_score,
            "confluence_score": confluence_score,
            "edge_score": edge_score
        }

    def diagnose_root_cause(
        self,
        symbol: str,
        side: str,
        is_win: bool,
        is_be: bool,
        r_multiple: float,
        trade_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Diagnose the exact mechanical and market reasons why the trade succeeded or failed.
        """
        confluence = trade_spec.get("confluence", {})
        h4 = str(confluence.get("macro_4h", "")).upper()
        strategy = trade_spec.get("strategy", "")
        
        is_trend_aligned = (side.upper() == "BUY" and "BULL" in h4) or (side.upper() == "SELL" and "BEAR" in h4)
        
        success_reasons = []
        failure_reasons = []
        actionable_lesson = ""

        if is_win:
            if is_trend_aligned:
                success_reasons.append("Higher-timeframe trend momentum (1H & 4H) accelerated price expansion.")
            if "SWEEP" in strategy.upper():
                success_reasons.append("Clean liquidity sweep trapped retail breakout traders, fueling swift reversal.")
            if r_multiple >= 1.5:
                success_reasons.append("Displacement candle closed with Market Structure Shift (MSS) body confirmation.")
            if trade_spec.get("time_machine", {}).get("passed"):
                success_reasons.append(f"Time Machine pre-trade simulation verified {trade_spec.get('time_machine', {}).get('win_rate_pct')}% historical win probability.")

            actionable_lesson = f"REPEAT PATTERN: Setup demonstrated clear institutional edge. Maintain full sizing and priority boost for this setup signature."

        elif is_be:
            success_reasons.append("Breakeven Shield ratcheted at +0.50R, eliminating downside risk completely.")
            failure_reasons.append("Momentum stalled prior to 2.0R target; liquidity absorption caused mean-reversion pullback.")
            actionable_lesson = "ZERO-RISK OUTCOME: Trailing stop successfully protected capital. No sizing penalty applied."

        else:
            # Trade was a loss
            if not is_trend_aligned:
                failure_reasons.append(f"Counter-trend vulnerability: Trade entered {side.upper()} while 4H macro orderflow was opposing ({h4}).")
            else:
                failure_reasons.append("Liquidity sweep level was violated; aggressive market orders absorbed the rejection wick.")
            
            failure_reasons.append("Immediate market structure continuation forced stop loss execution.")
            actionable_lesson = f"AVOID / PENALIZE PATTERN: Apply score reduction (-15 pts) to prevent re-entering this specific regime trap until market confirms clearer MSS."

        return {
            "success_factors": success_reasons,
            "failure_factors": failure_reasons,
            "actionable_lesson": actionable_lesson
        }

    def reflect_and_learn(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        realized_pnl: float,
        r_multiple: float,
        exit_reason: str,
        trade_spec: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute full post-trade reflection, update persistent pattern memory, and adapt algorithm weights.
        """
        spec = trade_spec or {}
        confluence = spec.get("confluence", {})
        strategy = spec.get("strategy", "Intraday_Scalp")
        
        is_win = realized_pnl > 0.01
        is_be = abs(realized_pnl) <= 0.05 or exit_reason == "BREAKEVEN"
        is_loss = realized_pnl < -0.05

        # 1. Score the trade
        scoring = self.score_trade(symbol, side, realized_pnl, r_multiple, exit_reason, spec)

        # 2. Diagnose root cause
        diagnosis = self.diagnose_root_cause(symbol, side, is_win, is_be, r_multiple, spec)

        # 3. Update Pattern Memory
        pattern_key = self._derive_pattern_key(symbol, side, strategy, confluence)
        pat_data = self.memory["patterns"].get(pattern_key, {
            "pattern_key": pattern_key,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "breakevens": 0,
            "win_rate_pct": 0.0,
            "cumulative_pnl": 0.0,
            "avg_r_multiple": 0.0,
            "score_adjustment": 0,
            "status": "EVALUATING",
            "consecutive_losses": 0,
            "last_action": "Initial observation"
        })

        pat_data["total_trades"] += 1
        pat_data["cumulative_pnl"] = round(pat_data["cumulative_pnl"] + realized_pnl, 2)

        if is_win:
            pat_data["wins"] += 1
            pat_data["consecutive_losses"] = 0
        elif is_be:
            pat_data["breakevens"] += 1
        else:
            pat_data["losses"] += 1
            pat_data["consecutive_losses"] += 1

        resolved = pat_data["wins"] + pat_data["losses"]
        win_rate = round((pat_data["wins"] / resolved * 100.0), 1) if resolved > 0 else 50.0
        pat_data["win_rate_pct"] = win_rate

        # Adaptive Algorithm Feedback Rules:
        # If pattern has >= 70% win rate -> REINFORCE (+5 to +10 bonus points)
        # If pattern has >= 2 consecutive losses or win rate < 45% -> PENALIZE / BLACKLIST
        if resolved >= 2 and win_rate >= 70.0:
            pat_data["status"] = "REINFORCED"
            pat_data["score_adjustment"] = +8
            pat_data["last_action"] = "Reinforced: Added +8 confluence boost for future candidate setups."
        elif pat_data["consecutive_losses"] >= 2 or (resolved >= 3 and win_rate < 40.0):
            pat_data["status"] = "VETOED_BLACKLISTED"
            pat_data["score_adjustment"] = -30
            pat_data["last_action"] = "Blacklisted: Pattern banned due to repeated failure in live market conditions."
        elif resolved >= 2 and win_rate < 55.0:
            pat_data["status"] = "PENALIZED"
            pat_data["score_adjustment"] = -15
            pat_data["last_action"] = "Penalized: -15 point deduction applied to require higher confluence."
        else:
            pat_data["status"] = "NEUTRAL"
            pat_data["score_adjustment"] = 0
            pat_data["last_action"] = "Monitoring pattern development."

        self.memory["patterns"][pattern_key] = pat_data

        # 4. Update Global Scorecard
        sc = self.memory["scorecard"]
        sc["total_completed_trades"] += 1
        if is_win:
            sc["winning_trades"] += 1
        elif is_be:
            sc["breakeven_trades"] += 1
        else:
            sc["losing_trades"] += 1

        sc["cumulative_pnl_usd"] = round(sc["cumulative_pnl_usd"] + realized_pnl, 2)
        total_res = sc["winning_trades"] + sc["losing_trades"]
        sc["win_rate_pct"] = round((sc["winning_trades"] / total_res * 100.0), 1) if total_res > 0 else 0.0
        
        # Running average trade score
        current_avg = sc.get("average_trade_score", 75.0)
        n = sc["total_completed_trades"]
        sc["average_trade_score"] = round(((current_avg * (n - 1)) + scoring["total_score"]) / n, 1)

        reflection_summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "symbol": symbol,
            "side": side.upper(),
            "realized_pnl": realized_pnl,
            "r_multiple": r_multiple,
            "exit_reason": exit_reason,
            "score": scoring["total_score"],
            "grade": scoring["grade"],
            "pattern_key": pattern_key,
            "pattern_status": pat_data["status"],
            "score_adjustment": pat_data["score_adjustment"],
            "actionable_lesson": diagnosis["actionable_lesson"]
        }

        # Keep last 10 reflections
        self.memory["recent_reflections"].append(reflection_summary)
        if len(self.memory["recent_reflections"]) > 10:
            self.memory["recent_reflections"] = self.memory["recent_reflections"][-10:]

        self._save_memory()

        return {
            "scoring": scoring,
            "diagnosis": diagnosis,
            "pattern_data": pat_data,
            "scorecard": sc,
            "reflection": reflection_summary
        }

    def get_pattern_adjustment(self, symbol: str, side: str, strategy: str, confluence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Consulted by StrategyAgent & Orchestrator during setup evaluation.
        Returns bonus/penalty points or strict veto directive.
        """
        pattern_key = self._derive_pattern_key(symbol, side, strategy, confluence)
        pat = self.memory["patterns"].get(pattern_key)
        
        if not pat:
            return {
                "pattern_key": pattern_key,
                "status": "NEW_PATTERN",
                "score_adjustment": 0,
                "can_trade": True,
                "reason": "No prior negative or positive bias recorded."
            }

        status = pat.get("status", "NEUTRAL")
        adj = pat.get("score_adjustment", 0)

        if status == "VETOED_BLACKLISTED":
            return {
                "pattern_key": pattern_key,
                "status": status,
                "score_adjustment": adj,
                "can_trade": False,
                "reason": f"Pattern Blacklist: '{pattern_key}' has {pat.get('win_rate_pct')}% live win rate ({pat.get('losses')} losses). Banned to avoid repeating failed trade."
            }
        elif status == "REINFORCED":
            return {
                "pattern_key": pattern_key,
                "status": status,
                "score_adjustment": adj,
                "can_trade": True,
                "reason": f"Pattern Reinforcement: '{pattern_key}' has proven {pat.get('win_rate_pct')}% live win rate (+{adj} pts priority boost)."
            }
        elif status == "PENALIZED":
            return {
                "pattern_key": pattern_key,
                "status": status,
                "score_adjustment": adj,
                "can_trade": True,
                "reason": f"Pattern Caution: '{pattern_key}' has sub-par past performance ({adj} pts penalty applied)."
            }

        return {
            "pattern_key": pattern_key,
            "status": "NEUTRAL",
            "score_adjustment": 0,
            "can_trade": True,
            "reason": "Neutral track record."
        }

    def format_telegram_reflection(self, reflection_data: Dict[str, Any]) -> str:
        """Format an institutional reflection message for Telegram."""
        refl = reflection_data["reflection"]
        scoring = reflection_data["scoring"]
        diag = reflection_data["diagnosis"]
        pat = reflection_data["pattern_data"]
        sc = reflection_data["scorecard"]

        sym = refl["symbol"]
        side = refl["side"]
        emoji_dir = "🟢 LONG" if side == "BUY" else "🔴 SHORT"
        pnl = refl["realized_pnl"]
        r = refl["r_multiple"]
        pnl_str = f"+${pnl:.2f} USD (+{r:.2f}R)" if pnl > 0 else (f"-${abs(pnl):.2f} USD ({r:.2f}R)" if pnl < 0 else "$0.00 USD (Breakeven)")
        outcome_tag = "🏆 WIN" if pnl > 0 else ("🛡️ BREAKEVEN" if pnl == 0 else "❌ LOSS")

        status_emoji = "🟢 REINFORCED (Repeat Pattern)" if pat["status"] == "REINFORCED" else ("🔴 BLACKLISTED (Avoid Pattern)" if pat["status"] == "VETOED_BLACKLISTED" else "🟡 EVALUATING")

        lines = [
            f"🧠 <b>[ALGORITHM POST-TRADE REFLECTION &amp; SELF-AUDIT]</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"• <b>Asset:</b> <code>{sym}</code> | <b>Side:</b> {emoji_dir}",
            f"• <b>Outcome:</b> <b>{outcome_tag}</b> (<code>{pnl_str}</code>)",
            f"• <b>Self-Scorecard:</b> <b>{scoring['total_score']}/100</b> — <i>{scoring['grade']}</i>",
            f"  ↳ Discipline: {scoring['discipline_score']}/30 | Confluence: {scoring['confluence_score']}/40 | Edge: {scoring['edge_score']}/30",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "🔍 <b>ROOT CAUSE DIAGNOSIS:</b>"
        ]

        if diag["success_factors"]:
            lines.append("<b>Why It Succeeded:</b>")
            for sf in diag["success_factors"]:
                lines.append(f"  ✅ <i>{sf}</i>")

        if diag["failure_factors"]:
            lines.append("<b>Why It Failed / Drawdown Drivers:</b>")
            for ff in diag["failure_factors"]:
                lines.append(f"  ⚠️ <i>{ff}</i>")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"⚙️ <b>ALGORITHM ADAPTATION:</b>")
        lines.append(f"• <b>Pattern Signature:</b> <code>{pat['pattern_key']}</code>")
        lines.append(f"• <b>Pattern Status:</b> {status_emoji}")
        lines.append(f"• <b>Score Adjustment:</b> <b>{'+' if pat['score_adjustment'] >= 0 else ''}{pat['score_adjustment']} pts</b>")
        lines.append(f"• <b>Rule:</b> <i>{diag['actionable_lesson']}</i>")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📈 <b>UPDATED BOT SCORECARD:</b>")
        lines.append(f"• Total Completed Trades: <b>{sc['total_completed_trades']}</b>")
        lines.append(f"• Performance: <b>{sc['winning_trades']} Wins</b> | <b>{sc['losing_trades']} Losses</b> | <b>{sc['breakeven_trades']} BE</b>")
        lines.append(f"• Realized Win Rate: <b>{sc['win_rate_pct']}%</b>")
        lines.append(f"• Cumulative Realized PnL: <b>{'+' if sc['cumulative_pnl_usd'] >= 0 else ''}${sc['cumulative_pnl_usd']:.2f} USD</b>")
        lines.append(f"• Average Trade Score: <b>{sc['average_trade_score']}/100</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚡ <i>Self-learning loop complete. Weights persisted to memory.</i>")

        return "\n".join(lines)
