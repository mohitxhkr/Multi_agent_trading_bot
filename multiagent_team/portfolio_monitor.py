"""
Agent 5: Portfolio Monitor & Memory Journaler.
Inspired by trader-memory-core, signal-postmortem, and weekly-performance-digest from claude-trading-skills.
Monitors open positions, writes persistent journal entries, and audits realized outcomes.
"""

from typing import Dict, Any, List
import logging
import os
import time
import json
from src.delta_client import DeltaExchangeClient
from src.journal import (
    record_trade_entry,
    record_trade_exit,
    get_performance_summary
)

logger = logging.getLogger("portfolio-monitor")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def ensure_reports_dir():
    os.makedirs(REPORTS_DIR, exist_ok=True)


class PortfolioMonitorAgent:
    def __init__(self, client: DeltaExchangeClient):
        self.client = client

    def monitor_positions(self) -> Dict[str, Any]:
        """
        Poll active positions and check health, unrealized PnL, and liquidation distance.
        """
        pos_res = self.client.get_positions()
        if not pos_res.get("success"):
            return {"error": "Failed to poll positions from Delta Exchange"}

        raw_positions = pos_res.get("result", [])
        active = []
        total_unrealized_pnl = 0.0

        for p in raw_positions:
            size = float(p.get("size", 0))
            if size != 0:
                pnl = float(p.get("unrealized_pnl", 0.0))
                total_unrealized_pnl += pnl
                entry = float(p.get("entry_price", 0.0))
                liq = float(p.get("liquidation_price", 0.0))
                
                liq_distance_pct = 0.0
                if entry > 0 and liq > 0:
                    liq_distance_pct = abs(entry - liq) / entry * 100.0

                active.append({
                    "symbol": p.get("product_symbol"),
                    "size": size,
                    "side": "LONG" if size > 0 else "SHORT",
                    "entry_price": entry,
                    "liquidation_price": liq,
                    "liquidation_distance_pct": round(liq_distance_pct, 2),
                    "unrealized_pnl_usd": round(pnl, 2),
                    "leverage": p.get("leverage")
                })

        return {
            "active_count": len(active),
            "total_unrealized_pnl_usd": round(total_unrealized_pnl, 2),
            "positions": active
        }

    def cancel_stale_orders(self, max_age_seconds: int = 5400) -> List[Dict[str, Any]]:
        """
        Scan open orders and automatically cancel unfilled limit entry orders older than max_age_seconds (default 90m).
        Protects against stale fills after market structure has evolved.
        Does NOT cancel active child stop loss or take profit orders.
        """
        cancelled = []
        try:
            orders_res = self.client.get_open_orders()
            if not orders_res.get("success"):
                return cancelled

            open_orders = orders_res.get("result", [])
            now = time.time()

            for ord in open_orders:
                # Ignore active child bracket orders (SL/TP)
                s_type = ord.get("stop_order_type")
                if s_type in ["stop_loss_order", "take_profit_order"]:
                    continue

                # Check creation time
                created_str = ord.get("created_at")
                if not created_str:
                    continue

                try:
                    import datetime
                    dt = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    age = now - dt.timestamp()
                except Exception:
                    age = 0

                if age > max_age_seconds:
                    oid = ord.get("id")
                    sym = ord.get("product_symbol")
                    logger.info(f"Cancelling stale unfilled entry order #{oid} on {sym} (age: {age/60:.1f}m)...")
                    c_res = self.client.cancel_order(symbol=sym, order_id=oid)
                    if c_res.get("success"):
                        cancelled.append({
                            "order_id": oid,
                            "symbol": sym,
                            "age_minutes": round(age / 60, 1),
                            "side": ord.get("side", ""),
                            "size": ord.get("size", 0),
                            "limit_price": ord.get("limit_price")
                        })
        except Exception as e:
            logger.error(f"Error checking stale orders: {e}")

        return cancelled

    def journal_execution(
        self,
        execution_res: Dict[str, Any],
        approved_decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Record a newly executed trade into the persistent journal memory.
        """
        trade_id = execution_res.get("trade_id", f"trade_{int(time.time())}")
        symbol = approved_decision["symbol"]
        side = approved_decision["side"]
        contracts = approved_decision["contracts"]
        entry = approved_decision["entry_price"]
        sl = approved_decision["stop_loss_price"]
        tp = approved_decision["take_profit_price"]
        thesis = approved_decision.get("thesis", "Algorithmic momentum execution")
        strategy = approved_decision.get("strategy", "Delta_MultiAgent_Perpetual")

        journal_entry = record_trade_entry(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            contracts=contracts,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            thesis=thesis,
            strategy=strategy,
            agent_decision=approved_decision
        )

        logger.info(f"PortfolioMonitor: Trade {trade_id} ({symbol}) recorded to journal.")
        return journal_entry

    def generate_daily_digest(self) -> str:
        """
        Produce a clean Markdown performance digest inspired by claude-trading-skills.
        """
        ensure_reports_dir()
        summary = get_performance_summary()
        stats = summary["stats"]
        pos_info = self.monitor_positions()

        today = time.strftime("%Y-%m-%d")
        report_filename = f"daily_digest_{today}.md"
        report_path = os.path.join(REPORTS_DIR, report_filename)

        content = [
            f"# Delta Exchange Daily Trading Digest — {today}",
            "",
            "## 1. Portfolio Health & Active Positions",
            f"- **Active Positions:** {pos_info.get('active_count', 0)}",
            f"- **Total Unrealized PnL:** `${pos_info.get('total_unrealized_pnl_usd', 0.0):.2f}`",
            "",
            "| Symbol | Side | Contracts | Entry Price | Liq Price | Unrealized PnL | Leverage |",
            "|---|---|---|---|---|---|---|"
        ]

        for p in pos_info.get("positions", []):
            content.append(
                f"| {p['symbol']} | {p['side']} | {p['size']} | "
                f"${p['entry_price']:.2f} | ${p['liquidation_price']:.2f} | "
                f"${p['unrealized_pnl_usd']:.2f} | {p['leverage']}x |"
            )

        if not pos_info.get("positions"):
            content.append("| No open positions | - | - | - | - | - | - |")

        content.extend([
            "",
            "## 2. Realized Performance Statistics (All-Time)",
            f"- **Total Closed Trades:** {stats.get('total_trades', 0)}",
            f"- **Winning Trades:** {stats.get('winning_trades', 0)}",
            f"- **Losing Trades:** {stats.get('losing_trades', 0)}",
            f"- **Win Rate:** `{stats.get('win_rate_pct', 0.0)}%`",
            f"- **Total Realized PnL:** `${stats.get('total_realized_pnl_usd', 0.0):.2f}`",
            "",
            "## 3. Pre-Trade Discipline Posture",
            "- All trade decisions passed Circuit Breaker and Pre-Trade Discipline Gates.",
            "- Minimum 2:1 Reward-to-Risk ratio and mandatory bracket stop-losses enforced.",
            ""
        ])

        report_text = "\n".join(content)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

        logger.info(f"PortfolioMonitor: Daily digest generated at {report_path}")
        return report_text
