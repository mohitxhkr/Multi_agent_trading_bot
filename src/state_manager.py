"""
Central State Management System for Delta Exchange Multi-Agent Trading System.
Maintains persistent SQLite records for positions, active orders, agent execution status,
market posture, operating rule versions, and trade logs with instant recovery on restart.
"""

import os
import json
import time
import sqlite3
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("state_manager")


class StateManager:
    """Thread-safe SQLite persistent state manager with JSON fallbacks."""

    def __init__(self, db_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        state_dir = os.path.join(base_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(state_dir, "trading_system.db")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create necessary tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Active and historical positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    side TEXT NOT NULL,
                    contracts INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    mark_price REAL DEFAULT 0.0,
                    stop_loss REAL,
                    take_profit REAL,
                    sl_order_id TEXT,
                    tp_order_id TEXT,
                    unrealized_pnl REAL DEFAULT 0.0,
                    realized_pnl REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'OPEN',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT
                )
            """)

            # Tracked orders with client idempotency key
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    client_order_id TEXT UNIQUE,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    size INTEGER NOT NULL,
                    filled_size INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    error_message TEXT
                )
            """)

            # Agent execution states
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    cycle_id TEXT,
                    status TEXT NOT NULL,
                    duration_ms REAL,
                    summary TEXT,
                    timestamp REAL NOT NULL
                )
            """)

            # Market posture snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_posture_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    posture TEXT NOT NULL,
                    health_score INTEGER NOT NULL,
                    breadth_pct REAL NOT NULL,
                    cash_priority INTEGER DEFAULT 0,
                    details_json TEXT
                )
            """)

            # Versioned Operating Rules
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operating_rules (
                    version TEXT PRIMARY KEY,
                    rules_json TEXT NOT NULL,
                    is_active INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    notes TEXT
                )
            """)

            # Trade executions and audits
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_audits (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    contracts INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    pnl_usd REAL DEFAULT 0.0,
                    pnl_r REAL DEFAULT 0.0,
                    outcome TEXT DEFAULT 'OPEN',
                    strategy_name TEXT,
                    confluence_score INTEGER,
                    time_machine_passed INTEGER,
                    created_at REAL NOT NULL,
                    closed_at REAL,
                    postmortem_json TEXT
                )
            """)
            conn.commit()

    # -------------------------------------------------------------
    # Position State Management
    # -------------------------------------------------------------
    def save_position(
        self,
        symbol: str,
        side: str,
        contracts: int,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        sl_order_id: Optional[str] = None,
        tp_order_id: Optional[str] = None,
        unrealized_pnl: float = 0.0,
        status: str = "OPEN",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Upsert a position record."""
        now = time.time()
        meta_str = json.dumps(metadata or {})
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO positions (
                        symbol, side, contracts, entry_price, stop_loss, take_profit,
                        sl_order_id, tp_order_id, unrealized_pnl, status, created_at, updated_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        contracts=excluded.contracts,
                        stop_loss=COALESCE(excluded.stop_loss, positions.stop_loss),
                        take_profit=COALESCE(excluded.take_profit, positions.take_profit),
                        sl_order_id=COALESCE(excluded.sl_order_id, positions.sl_order_id),
                        tp_order_id=COALESCE(excluded.tp_order_id, positions.tp_order_id),
                        unrealized_pnl=excluded.unrealized_pnl,
                        status=excluded.status,
                        updated_at=excluded.updated_at,
                        metadata=excluded.metadata
                """, (symbol, side, contracts, entry_price, stop_loss, take_profit,
                      sl_order_id, tp_order_id, unrealized_pnl, status, now, now, meta_str))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save position {symbol}: {e}")
            return False

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Retrieve all currently active positions."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM positions WHERE status='OPEN' AND contracts > 0")
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to query open positions: {e}")
            return []

    def close_position(self, symbol: str, realized_pnl: float = 0.0) -> bool:
        """Mark a position as closed."""
        now = time.time()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE positions
                    SET status='CLOSED', contracts=0, realized_pnl=?, updated_at=?
                    WHERE symbol=?
                """, (realized_pnl, now, symbol))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            return False

    # -------------------------------------------------------------
    # Order Tracking & Idempotency
    # -------------------------------------------------------------
    def record_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        price: float,
        size: int,
        client_order_id: Optional[str] = None,
        status: str = "open"
    ) -> bool:
        now = time.time()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO orders (
                        order_id, client_order_id, symbol, side, order_type, price, size, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(order_id) DO UPDATE SET
                        status=excluded.status,
                        updated_at=excluded.updated_at
                """, (order_id, client_order_id, symbol, side, order_type, price, size, status, now, now))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to record order {order_id}: {e}")
            return False

    def is_client_order_id_used(self, client_order_id: str) -> bool:
        """Check if an idempotency client order ID has already been recorded."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM orders WHERE client_order_id=?", (client_order_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking client_order_id {client_order_id}: {e}")
            return False

    # -------------------------------------------------------------
    # Agent Observability & Auditing
    # -------------------------------------------------------------
    def record_agent_run(
        self,
        agent_name: str,
        status: str,
        duration_ms: float = 0.0,
        summary: str = "",
        cycle_id: Optional[str] = None
    ):
        now = time.time()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO agent_runs (agent_name, cycle_id, status, duration_ms, summary, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (agent_name, cycle_id, status, duration_ms, summary, now))
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to record agent run {agent_name}: {e}")

    # -------------------------------------------------------------
    # Market Posture Snapshots
    # -------------------------------------------------------------
    def save_market_posture(
        self,
        posture: str,
        health_score: int,
        breadth_pct: float,
        cash_priority: bool = False,
        details: Optional[Dict[str, Any]] = None
    ):
        now = time.time()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO market_posture_history (timestamp, posture, health_score, breadth_pct, cash_priority, details_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (now, posture, health_score, breadth_pct, 1 if cash_priority else 0, json.dumps(details or {})))
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to record market posture: {e}")

    def get_latest_market_posture(self) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM market_posture_history ORDER BY timestamp DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    res = dict(row)
                    if res.get("details_json"):
                        res["details"] = json.loads(res["details_json"])
                    return res
        except Exception as e:
            logger.error(f"Error loading market posture: {e}")
        return None

    # -------------------------------------------------------------
    # Operating Rules Versioning
    # -------------------------------------------------------------
    def save_operating_rules_version(self, version: str, rules: Dict[str, Any], notes: str = "", activate: bool = True) -> bool:
        now = time.time()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if activate:
                    cursor.execute("UPDATE operating_rules SET is_active=0")
                cursor.execute("""
                    INSERT INTO operating_rules (version, rules_json, is_active, created_at, notes)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(version) DO UPDATE SET
                        rules_json=excluded.rules_json,
                        is_active=excluded.is_active,
                        notes=excluded.notes
                """, (version, json.dumps(rules), 1 if activate else 0, now, notes))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save operating rules version {version}: {e}")
            return False

    def get_active_operating_rules(self) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM operating_rules WHERE is_active=1 LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return json.loads(row["rules_json"])
        except Exception as e:
            logger.error(f"Failed to get active operating rules: {e}")
        return None

    def rollback_operating_rules(self) -> Optional[str]:
        """Roll back to the previous version of operating rules."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version FROM operating_rules ORDER BY created_at DESC LIMIT 2")
                rows = cursor.fetchall()
                if len(rows) >= 2:
                    prior_version = rows[1]["version"]
                    cursor.execute("UPDATE operating_rules SET is_active=0")
                    cursor.execute("UPDATE operating_rules SET is_active=1 WHERE version=?", (prior_version,))
                    conn.commit()
                    logger.info(f"Successfully rolled back operating rules to {prior_version}")
                    return prior_version
        except Exception as e:
            logger.error(f"Failed to rollback operating rules: {e}")
        return None

    # -------------------------------------------------------------
    # State Reconciliation with Delta Exchange
    # -------------------------------------------------------------
    def reconcile_positions_with_exchange(self, exchange_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Reconcile local open position records against actual live positions from Delta Exchange.
        If an exchange position exists that is not in state, it registers it.
        If a position was closed on exchange, it marks local position closed.
        """
        active_exchange_syms = set()
        reconciled = {"synced": [], "orphans_closed": [], "discovered": []}

        for p in exchange_positions:
            size = int(p.get("size", 0))
            if size == 0:
                continue
            sym = p.get("symbol", "")
            active_exchange_syms.add(sym)
            entry_p = float(p.get("entry_price") or 0.0)
            side = "buy" if size > 0 else "sell"
            unrealized = float(p.get("unrealized_pnl") or 0.0)
            
            # Check local record
            local = None
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM positions WHERE symbol=? AND status='OPEN'", (sym,))
                    local = cursor.fetchone()
            except Exception:
                pass

            if not local:
                self.save_position(
                    symbol=sym,
                    side=side,
                    contracts=abs(size),
                    entry_price=entry_p,
                    unrealized_pnl=unrealized,
                    metadata={"source": "exchange_reconciliation"}
                )
                reconciled["discovered"].append(sym)
            else:
                self.save_position(
                    symbol=sym,
                    side=side,
                    contracts=abs(size),
                    entry_price=entry_p,
                    unrealized_pnl=unrealized,
                    status="OPEN"
                )
                reconciled["synced"].append(sym)

        # Find local open positions no longer on exchange
        local_open = self.get_open_positions()
        for lp in local_open:
            if lp["symbol"] not in active_exchange_syms:
                self.close_position(lp["symbol"], realized_pnl=0.0)
                reconciled["orphans_closed"].append(lp["symbol"])

        return reconciled

