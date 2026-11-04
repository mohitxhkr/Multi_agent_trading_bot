"""
Agent 7: Trade Performance Coach & Next-Session Operating Rules Engine.
Directly inspired by trade-performance-coach, signal-postmortem, and weekly-performance-digest
from claude-trading-skills.
Analyzes closed trades, risk adherence, and pattern cohorts to generate binding
Next-Session Operating Rules for the Strategy and Risk agents.
"""

from typing import Dict, Any, List, Optional
import os
import json
import time
import logging

logger = logging.getLogger("performance-coach")

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
RULES_FILE = os.path.join(STATE_DIR, "active_operating_rules.json")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


class PerformanceCoachAgent:
    def __init__(self, rules_path: Optional[str] = None):
        self.rules_path = rules_path or RULES_FILE
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
        return {
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
        Review all closed trades from journal & pattern memory, diagnose systemic trends,
        and generate dynamic next-session operating rules.
        """
        from src.journal import load_journal
        journal = load_journal()
        closed_trades = [t for t in journal.get("trades", []) if t.get("status") == "CLOSED"]
        
        total = len(closed_trades)
        if total == 0:
            return self.rules

        winners = [t for t in closed_trades if float(t.get("realized_pnl_usd") or 0.0) > 0.0]
        losers = [t for t in closed_trades if float(t.get("realized_pnl_usd") or 0.0) < -0.05]
        be_trades = [t for t in closed_trades if abs(float(t.get("realized_pnl_usd") or 0.0)) <= 0.05]

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

        # Synthesize Dynamic Rules based on live data
        dynamic_rules = []

        # Base Non-Negotiables
        dynamic_rules.append({
            "id": "RULE_1_MACRO_FLOW",
            "title": "Strict Macro Order Flow Alignment",
            "rule": "Mandatory 1H/4H trend alignment: LONGS only in bull trend, SHORTS only in bear trend.",
            "status": "ACTIVE",
            "enforcement": "MANDATORY"
        })
        dynamic_rules.append({
            "id": "RULE_2_FIXED_RISK",
            "title": "Fixed Dollar Risk Cap ($2.00 - $4.00 Max)",
            "rule": "Every trade strictly bounded by fixed dollar loss. Max loss = $2.00 - $4.00.",
            "status": "ACTIVE",
            "enforcement": "MANDATORY"
        })

        # Data-driven adaptations
        alt_data = asset_stats.get("ALT", {"wins": 0, "losses": 0, "pnl": 0.0})
        if alt_data["losses"] > alt_data["wins"] or alt_data["pnl"] < -10.0:
            dynamic_rules.append({
                "id": "RULE_3_ALTCOIN_RESTRICTION",
                "title": "Altcoin Exposure Restriction",
                "rule": f"Secondary alts have underperformed (PnL: ${alt_data['pnl']:.2f}). Sizing strictly capped at 1 contract / max $2.00 risk. Prioritize BTC & ETH.",
                "status": "ACTIVE",
                "enforcement": "MANDATORY"
            })

        btc_data = asset_stats.get("BTC", {"wins": 0, "losses": 0, "pnl": 0.0})
        if btc_data["wins"] >= 2 and btc_data["pnl"] > 0:
            dynamic_rules.append({
                "id": "RULE_4_BTC_CORE_EDGE",
                "title": "BTC Edge Prioritization",
                "rule": f"BTC perpetuals showing strong performance ({btc_data['wins']}W / {btc_data['losses']}L). Grant +10 priority score on BTC 15m liquidity sweeps.",
                "status": "ACTIVE",
                "enforcement": "RECOMMENDED"
            })

        dynamic_rules.append({
            "id": "RULE_5_TIME_MACHINE_VERIFICATION",
            "title": "Mandatory Time Machine Probability Check",
            "rule": "Every prospective trade must demonstrate >= 68% historical win rate and positive EV before approval.",
            "status": "ACTIVE",
            "enforcement": "MANDATORY"
        })

        self.rules["rules"] = dynamic_rules
        self.rules["stats_summary"] = {
            "total_trades": total,
            "win_rate_pct": round(win_rate, 1),
            "total_pnl_usd": round(total_pnl, 2),
            "asset_breakdown": asset_stats
        }

        self._save_rules()
        return self.rules

    def format_telegram_rules(self) -> str:
        """Format operating rules for Telegram command /rules."""
        self.audit_and_update_rules()
        rules_list = self.rules.get("rules", [])
        stats = self.rules.get("stats_summary", {})

        lines = [
            "📋 <b>[ACTIVE NEXT-SESSION OPERATING RULES]</b>",
            "<i>Synthesized by Agent 7: Performance Coach from closed trade audit</i>",
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
        lines.append("⚡ <i>These operating rules are actively enforced across Strategy & Risk agents.</i>")
        return "\n".join(lines)

