"""
Trade Memory & Journaling System for Delta Exchange.
Inspired by trader-memory-core and signal-postmortem from claude-trading-skills.
Maintains persistent trade history, execution records, and performance metrics.
"""

from typing import Dict, List, Any, Optional
import json
import os
import time

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
JOURNAL_FILE = os.path.join(STATE_DIR, "trade_journal.json")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def load_journal() -> Dict[str, Any]:
    ensure_state_dir()
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "trades": [],
        "stats": {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "total_realized_pnl_usd": 0.0
        }
    }


def save_journal(journal: Dict[str, Any]):
    ensure_state_dir()
    with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
        json.dump(journal, f, indent=2)


def record_trade_entry(
    trade_id: str,
    symbol: str,
    side: str,
    contracts: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    thesis: str,
    strategy: str,
    agent_decision: Dict[str, Any]
) -> Dict[str, Any]:
    """Record a newly opened trade into the journal."""
    journal = load_journal()
    
    trade_entry = {
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "contracts": contracts,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "entry_time": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "status": "OPEN",
        "thesis": thesis,
        "strategy": strategy,
        "agent_decision": agent_decision,
        "exit_price": None,
        "exit_time": None,
        "realized_pnl_usd": None,
        "postmortem_notes": None
    }
    
    journal["trades"].append(trade_entry)
    save_journal(journal)
    return trade_entry


def record_trade_exit(
    trade_id: str,
    exit_price: float,
    realized_pnl_usd: float,
    exit_reason: str,
    postmortem_notes: str = ""
) -> Optional[Dict[str, Any]]:
    """Record a trade closure and update overall performance stats."""
    journal = load_journal()
    found = None
    
    for t in journal["trades"]:
        if t["trade_id"] == trade_id and t["status"] == "OPEN":
            t["status"] = "CLOSED"
            t["exit_price"] = exit_price
            t["exit_time"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            t["realized_pnl_usd"] = round(realized_pnl_usd, 2)
            t["exit_reason"] = exit_reason
            t["postmortem_notes"] = postmortem_notes
            found = t
            break
            
    if not found:
        return None
        
    # Recalculate stats
    closed_trades = [t for t in journal["trades"] if t["status"] == "CLOSED"]
    winners = [t for t in closed_trades if (t.get("realized_pnl_usd") or 0) > 0]
    losers = [t for t in closed_trades if (t.get("realized_pnl_usd") or 0) <= 0]
    total_pnl = sum(t.get("realized_pnl_usd") or 0 for t in closed_trades)
    
    stats = journal["stats"]
    stats["total_trades"] = len(closed_trades)
    stats["winning_trades"] = len(winners)
    stats["losing_trades"] = len(losers)
    stats["win_rate_pct"] = round((len(winners) / len(closed_trades) * 100.0), 2) if closed_trades else 0.0
    stats["total_realized_pnl_usd"] = round(total_pnl, 2)
    
    save_journal(journal)
    return found


def get_performance_summary() -> Dict[str, Any]:
    """Retrieve full journal statistics and open positions."""
    journal = load_journal()
    open_trades = [t for t in journal["trades"] if t["status"] == "OPEN"]
    recent_closed = [t for t in journal["trades"] if t["status"] == "CLOSED"][-5:]
    
    return {
        "stats": journal["stats"],
        "open_trades_count": len(open_trades),
        "open_trades": open_trades,
        "recent_closed_trades": recent_closed
    }
