"""
Agent 10: Trade Performance Coach & Dynamic Operating Rules Engine.
Analyzes cohort performance by asset, session, strategy, and market regime,
monitors planned vs actual execution variance, tracks efficacy of Agent 9's bonuses,
and maintains version-controlled operating rules with automated rollback safeguards.
"""

from typing import Dict, Any, List, Optional
import os
import json
import time
import logging
from src.state_manager import StateManager

logger = logging.getLogger("performance-coach")

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
RULES_FILE = os.path.join(STATE_DIR, "active_operating_rules.json")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


class PerformanceCoachAgent:
    def __init__(self, rules_path: Optional[str] = None, state_manager: Optional[StateManager] = None):
        self.rules_path = rules_path or RULES_FILE
        self.state_manager = state_manager or StateManager()
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        ensure_state_dir()
        if os.path.exists(self.rules_path):
            try:
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading operating rules: {e}")

        # Default institutional operating rules
        default_rules = {
            "version": "1.0.0",
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "rules": [
                {
                    "id": "RULE_1_CORE_ASSET_FOCUS",
                    "title": "Primary Asset Priority (BTC, ETH, XAU)",
                    "rule": "Prioritize high-liquidity primary assets (BTC, ETH, XAU) over secondary altcoins.",
                    "status": "ACTIVE",
                    "enforcement": "MANDATORY"
                },
                {
                    "id": "RULE_2_MACRO_TREND_ALIGNMENT",
                    "title": "Strict Higher-Timeframe Trend Alignment",
                    "rule": "Never short into confirmed 1H & 4H bull expansion; never buy into confirmed bear trend.",
                    "status": "ACTIVE",
                    "enforcement": "MANDATORY"
                },
                {
                    "id": "RULE_3_MANDATORY_MSS_CONFIRMATION",
                    "title": "Market Structure Shift (MSS) Candle Close",
                    "rule": "Never enter on an unconfirmed wick. Wait for candle close breaking structure.",
                    "status": "ACTIVE",
                    "enforcement": "MANDATORY"
                },
                {
                    "id": "RULE_4_FIXED_DOLLAR_RISK",
                    "title": "Fixed Dollar Risk Ceiling ($2.00 - $4.00 Max Risk)",
                    "rule": "Size strictly by dollar risk. Max loss capped at $2-$4 (max 2% equity). Altcoins capped at $2 max.",
                    "status": "ACTIVE",
                    "enforcement": "MANDATORY"
                },
                {
                    "id": "RULE_5_BREAKEVEN_SHIELD",
                    "title": "Scalper Breakeven Shield at +0.50R",
                    "rule": "Ratchet stop loss to Entry + fee buffer when price reaches +0.50R to guarantee zero downside.",
                    "status": "ACTIVE",
                    "enforcement": "MANDATORY"
                }
            ],
            "stats_summary": {}
        }
        self.state_manager.save_operating_rules_version("1.0.0", default_rules, "Initial institutional defaults")
        return default_rules

    def _save_rules(self):
        ensure_state_dir()
        self.rules["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        try:
            with open(self.rules_path, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving operating rules: {e}")

    def audit_and_update_rules(self) -> Dict[str, Any]:
        """
        Review all closed trades, diagnose systemic trends, and version-control
        Next-Session Operating Rules.
        """
        from src.journal import load_journal
        journal = load_journal()
        closed_trades = [t for t in journal.get("trades", []) if t.get("status") == "CLOSED"]
        total = len(closed_trades)
        if total == 0:
            return self.rules

        winners = [t for t in closed_trades if float(t.get("realized_pnl_usd") or 0.0) > 0.0]
        losers = [t for t in closed_trades if float(t.get("realized_pnl_usd") or 0.0) < -0.05]
        win_rate = (len(winners) / total * 100.0) if total > 0 else 0.0
        total_pnl = sum(float(t.get("realized_pnl_usd") or 0.0) for t in closed_trades)

        # Asset breakdown
        asset_stats = {}
        for t in closed_trades:
            sym = t.get("symbol", "UNKNOWN")
            base = "BTC" if "BTC" in sym else ("ETH" if "ETH" in sym else ("XAU" if "XAU" in sym else "ALT"))
            if base not in asset_stats:
                asset_stats[base] = {"wins": 0, "losses": 0, "pnl": 0.0}
            
            pnl = float(t.get("realized_pnl_usd") or 0.0)
            asset_stats[base]["pnl"] += pnl
            if pnl > 0:
                asset_stats[base]["wins"] += 1
            elif pnl < -0.05:
                asset_stats[base]["losses"] += 1

        # Check for degradation to trigger rollback
        recent_5 = closed_trades[-5:] if len(closed_trades) >= 5 else []
        recent_5_wins = sum(1 for t in recent_5 if float(t.get("realized_pnl_usd") or 0.0) > 0.0)
        if len(recent_5) == 5 and recent_5_wins <= 1:
            logger.warning("PerformanceCoach: Degradation detected (< 20% win rate over last 5 trades). Checking rollback...")
            rb_ver = self.state_manager.rollback_operating_rules()
            if rb_ver:
                cached = self.state_manager.get_active_operating_rules()
                if cached:
                    self.rules = cached
                    self._save_rules()
                    return self.rules

        # Synthesize Rules
        dynamic_rules = [
            {
                "id": "RULE_1_MACRO_FLOW",
                "title": "Strict Macro Order Flow Alignment",
                "rule": "Mandatory 1H/4H trend alignment: LONGS only in bull trend, SHORTS only in bear trend.",
                "status": "ACTIVE",
                "enforcement": "MANDATORY"
            },
            {
                "id": "RULE_2_FIXED_RISK",
                "title": "Fixed Dollar Risk Cap ($2.00 - $4.00 Max)",
                "rule": "Every trade strictly bounded by fixed dollar loss ($2-$4 max).",
                "status": "ACTIVE",
                "enforcement": "MANDATORY"
            }
        ]

        alt_data = asset_stats.get("ALT", {"wins": 0, "losses": 0, "pnl": 0.0})
        if alt_data["losses"] > alt_data["wins"] or alt_data["pnl"] < -10.0:
            dynamic_rules.append({
                "id": "RULE_3_ALTCOIN_RESTRICTION",
                "title": "Altcoin Exposure Restriction",
                "rule": f"Secondary alts underperforming (PnL: ${alt_data['pnl']:.2f}). Sizing strictly capped at 1 contract / max $2.00 risk.",
                "status": "ACTIVE",
                "enforcement": "MANDATORY"
            })

        btc_data = asset_stats.get("BTC", {"wins": 0, "losses": 0, "pnl": 0.0})
        if btc_data["wins"] >= 2 and btc_data["pnl"] > 0:
            dynamic_rules.append({
                "id": "RULE_4_BTC_CORE_EDGE",
                "title": "BTC Edge Prioritization",
                "rule": f"BTC perpetuals showing positive edge ({btc_data['wins']}W / {btc_data['losses']}L). Grant +10 priority score on BTC 15m liquidity sweeps.",
                "status": "ACTIVE",
                "enforcement": "RECOMMENDED"
            })

        dynamic_rules.append({
            "id": "RULE_5_TIME_MACHINE_VERIFICATION",
            "title": "Mandatory Time Machine Probability Check",
            "rule": "Every prospective trade must demonstrate >= 65% historical win rate and positive EV before approval.",
            "status": "ACTIVE",
            "enforcement": "MANDATORY"
        })

        # Version bump
        curr_ver = self.rules.get("version", "1.0.0")
        try:
            parts = curr_ver.split(".")
            new_patch = int(parts[2]) + 1
            new_ver = f"{parts[0]}.{parts[1]}.{new_patch}"
        except Exception:
            new_ver = "1.0.1"

        self.rules["version"] = new_ver
        self.rules["rules"] = dynamic_rules
        self.rules["stats_summary"] = {
            "total_trades": total,
            "win_rate_pct": round(win_rate, 1),
            "total_pnl_usd": round(total_pnl, 2),
            "asset_breakdown": asset_stats
        }

        self._save_rules()
        self.state_manager.save_operating_rules_version(new_ver, self.rules, f"Performance coach update based on {total} trades")
        return self.rules

    def format_telegram_rules(self) -> str:
        """Format operating rules for Telegram command /rules."""
        self.audit_and_update_rules()
        rules_list = self.rules.get("rules", [])
        stats = self.rules.get("stats_summary", {})
        ver = self.rules.get("version", "1.0.0")

        lines = [
            f"📋 <b>[OPERATING RULES — VERSION {ver}]</b>",
            "<i>Synthesized by Agent 10: Performance Coach from closed trade audit</i>",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]

        if stats:
            lines.append(f"• <b>Audited Trades:</b> <b>{stats.get('total_trades', 0)}</b> | <b>Win Rate:</b> <b>{stats.get('win_rate_pct', 0)}%</b> | <b>PnL:</b> <b>${stats.get('total_pnl_usd', 0):.2f}</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        for i, r in enumerate(rules_list, 1):
            enf = "🔴 MANDATORY" if r.get("enforcement") == "MANDATORY" else "🟢 RECOMMENDED"
            lines.append(f"<b>{i}. {r.get('title')}</b> [{enf}]")
            lines.append(f"   ↳ <i>{r.get('rule')}</i>")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚡ <i>Version-controlled with automated rollback if rolling win rate degrades.</i>")
        return "\n".join(lines)
