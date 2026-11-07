"""
Trade Memory & Event Store Journaling Engine for Delta Exchange.
Implements dual persistence:
1. Authoritative SQLite Event Store (state/trading_journal.db) tracking full granular lifecycle events:
   SETUP_IDENTIFIED, RISK_EVALUATED, USER_PROMPTED, USER_DECISION_RECEIVED,
   ORDER_PLACED, ORDER_FILLED, PROTECTIVE_ORDER_PLACED, TRAILING_STOP_MODIFIED,
   EXIT_ORDER_FILLED, TRADE_CLOSED, POSTMORTEM_COMPLETED.
2. Backward-compatible JSON summary store (state/trade_journal.json).
"""

from typing import Dict, List, Any, Optional
import json
import os
import time
import sqlite3

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
JOURNAL_FILE = os.path.join(STATE_DIR, "trade_journal.json")
DB_FILE = os.path.join(STATE_DIR, "trading_journal.db")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def get_db_connection() -> sqlite3.Connection:
    ensure_state_dir()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    ensure_state_dir()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                contracts INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                entry_time TEXT NOT NULL,
                status TEXT NOT NULL,
                exit_price REAL,
                exit_time TEXT,
                realized_pnl_usd REAL,
                exit_reason TEXT,
                mfe_r REAL,
                mae_r REAL,
                thesis TEXT,
                strategy TEXT,
                postmortem_notes TEXT,
                raw_data TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_lifecycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(trade_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_trade_id ON trade_lifecycle_events(trade_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
        conn.commit()


# Initialize database schemas on module import
init_db()


def log_trade_event(trade_id: str, event_type: str, details: Optional[Dict[str, Any]] = None):
    """
    Append an immutable lifecycle event to the SQLite event store.
    """
    ensure_state_dir()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    details_json = json.dumps(details or {})
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO trade_lifecycle_events (trade_id, event_type, timestamp, details) VALUES (?, ?, ?, ?)",
                (trade_id, event_type, now_str, details_json)
            )
            conn.commit()
    except Exception as e:
        # Fallback logging if DB is temporarily locked
        pass


def load_journal() -> Dict[str, Any]:
    ensure_state_dir()
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "trades" in data:
                    return data
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
    temp_file = JOURNAL_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(journal, f, indent=2)
    os.replace(temp_file, JOURNAL_FILE)


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
    """Record a newly opened trade into both SQLite and JSON stores."""
    now_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    trade_entry = {
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "contracts": contracts,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "entry_time": now_str,
        "status": "OPEN",
        "thesis": thesis,
        "strategy": strategy,
        "agent_decision": agent_decision,
        "exit_price": None,
        "exit_time": None,
        "realized_pnl_usd": None,
        "postmortem_notes": None
    }

    # 1. Update SQLite
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trades (
                    trade_id, symbol, side, contracts, entry_price, stop_loss, take_profit,
                    entry_time, status, thesis, strategy, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id, symbol, side, contracts, entry_price, stop_loss, take_profit,
                    now_str, "OPEN", thesis, strategy, json.dumps(agent_decision)
                )
            )
            conn.commit()
    except Exception:
        pass

    log_trade_event(trade_id, "ORDER_PLACED", {
        "symbol": symbol,
        "side": side,
        "contracts": contracts,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit
    })

    # 2. Update JSON
    journal = load_journal()
    journal["trades"].append(trade_entry)
    save_journal(journal)
    return trade_entry


def record_trade_exit(
    trade_id: str,
    exit_price: float,
    realized_pnl_usd: float,
    exit_reason: str,
    postmortem_notes: str = "",
    mfe_r: float = 0.0,
    mae_r: float = 0.0
) -> Optional[Dict[str, Any]]:
    """Record a trade closure and update overall performance stats with MFE/MAE tracking."""
    journal = load_journal()
    found = None
    now_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    # 1. Primary match: by exact trade_id
    for t in reversed(journal["trades"]):
        if t.get("trade_id") == trade_id and t.get("status") == "OPEN":
            found = t
            break

    # 2. Secondary fallback match: by symbol if trade_id was passed generically (e.g. trade_BTCUSD)
    if not found:
        sym_clean = trade_id.replace("trade_", "").upper()
        for t in reversed(journal["trades"]):
            if (t.get("symbol") == sym_clean or sym_clean in t.get("symbol", "")) and t.get("status") == "OPEN":
                found = t
                break

    if not found:
        return None

    actual_trade_id = found.get("trade_id", trade_id)
    found["status"] = "CLOSED"
    found["exit_price"] = exit_price
    found["exit_time"] = now_str
    found["realized_pnl_usd"] = round(realized_pnl_usd, 2)
    found["exit_reason"] = exit_reason
    found["postmortem_notes"] = postmortem_notes
    found["mfe_r"] = round(mfe_r, 2)
    found["mae_r"] = round(mae_r, 2)

    # 1. Update SQLite
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE trades SET
                    status = 'CLOSED',
                    exit_price = ?,
                    exit_time = ?,
                    realized_pnl_usd = ?,
                    exit_reason = ?,
                    postmortem_notes = ?,
                    mfe_r = ?,
                    mae_r = ?
                WHERE trade_id = ?
                """,
                (
                    exit_price, now_str, round(realized_pnl_usd, 2),
                    exit_reason, postmortem_notes, round(mfe_r, 2), round(mae_r, 2),
                    actual_trade_id
                )
            )
            conn.commit()
    except Exception:
        pass

    log_trade_event(actual_trade_id, "TRADE_CLOSED", {
        "exit_price": exit_price,
        "realized_pnl_usd": round(realized_pnl_usd, 2),
        "exit_reason": exit_reason,
        "mfe_r": round(mfe_r, 2),
        "mae_r": round(mae_r, 2)
    })

    # Recalculate stats
    closed_trades = [t for t in journal["trades"] if t.get("status") == "CLOSED"]
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
    open_trades = [t for t in journal["trades"] if t.get("status") == "OPEN"]
    recent_closed = [t for t in journal["trades"] if t.get("status") == "CLOSED"][-5:]

    return {
        "stats": journal["stats"],
        "open_trades_count": len(open_trades),
        "open_trades": open_trades,
        "recent_closed_trades": recent_closed
    }
