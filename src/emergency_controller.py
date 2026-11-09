"""
Global Kill Switch & Emergency Position Controller for Delta Exchange.
Provides immediate fail-safe controls to block new entries, cancel pending entry orders,
verify protective stop-loss orders on all open positions, and execute orderly shutdowns.
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from src.delta_client import DeltaExchangeClient

logger = logging.getLogger("emergency_controller")


class EmergencyController:
    """Enterprise-grade emergency halt and position protection controller."""

    def __init__(self, client: Optional[DeltaExchangeClient] = None, state_file: Optional[str] = None):
        self.client = client or DeltaExchangeClient()
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        state_dir = os.path.join(base_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        self.state_file = state_file or os.path.join(state_dir, "emergency_state.json")
        self._load_state()

    def _load_state(self):
        self.halted = False
        self.halt_reason = ""
        self.halt_timestamp = 0.0
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.halted = bool(data.get("halted", False))
                    self.halt_reason = data.get("reason", "")
                    self.halt_timestamp = data.get("timestamp", 0.0)
            except Exception as e:
                logger.error(f"Failed to read emergency state file: {e}")

    def _persist_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "halted": self.halted,
                    "reason": self.halt_reason,
                    "timestamp": self.halt_timestamp
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist emergency state: {e}")

    def is_halted(self) -> Tuple[bool, str]:
        """Check if trading is currently blocked by emergency halt."""
        return self.halted, self.halt_reason

    def engage_emergency_halt(self, reason: str) -> Dict[str, Any]:
        """Engage the kill switch. Blocks all new trading and cancels open entry orders."""
        self.halted = True
        self.halt_reason = reason
        self.halt_timestamp = time.time()
        self._persist_state()
        logger.critical(f"🛑 [EMERGENCY KILL SWITCH ENGAGED]: {reason}")

        # Automatically cancel open entry orders so no new positions open
        cancelled_orders = self.cancel_pending_entry_orders()

        # Audit and verify that open positions still have protective stops
        sl_audit = self.verify_and_ensure_sl_protection()

        return {
            "status": "EMERGENCY_HALTED",
            "reason": reason,
            "timestamp": self.halt_timestamp,
            "cancelled_entry_orders_count": len(cancelled_orders),
            "cancelled_orders": cancelled_orders,
            "sl_audit": sl_audit
        }

    def release_emergency_halt(self, operator: str = "trader") -> Dict[str, Any]:
        """Release emergency halt and allow normal trading cycle resume."""
        prev_reason = self.halt_reason
        self.halted = False
        self.halt_reason = ""
        self.halt_timestamp = 0.0
        self._persist_state()

        # Re-synchronize and reset RiskManager circuit breaker
        try:
            from src.risk_manager import RiskManager
            tot_equity = 1000.0
            if hasattr(self, "client") and self.client:
                wallet_res = self.client.get_wallet_balances()
                if wallet_res.get("success"):
                    for b in wallet_res.get("result", []):
                        if b.get("asset_symbol") in ["USD", "USDT"]:
                            tot_equity = float(b.get("balance", 1000.0))
            RiskManager().manual_reset(
                authorized_by=operator,
                reason=f"Emergency halt released by {operator}",
                current_equity=tot_equity
            )
        except Exception as re:
            logger.debug(f"RiskManager reset on release skipped: {re}")

        logger.info(f"🟢 [EMERGENCY KILL SWITCH RELEASED] by {operator}. Previous halt: {prev_reason}")
        return {
            "status": "NORMAL_OPERATION",
            "released_by": operator,
            "previous_reason": prev_reason
        }

    def cancel_pending_entry_orders(self) -> List[Dict[str, Any]]:
        """
        Cancel all pending unfilled limit entry orders across all symbols.
        DOES NOT cancel protective stop-loss or take-profit orders!
        """
        cancelled = []
        try:
            res = self.client.get_open_orders()
            if not res.get("success"):
                logger.error("Failed to query open orders for cancellation.")
                return []

            orders = res.get("result", [])
            for order in orders:
                order_id = str(order.get("id"))
                order_type = str(order.get("order_type", "")).lower()
                is_sl_or_tp = bool(order.get("stop_order_type") or "stop" in order_type)

                # Only cancel entry orders; NEVER touch protective stop loss orders!
                if not is_sl_or_tp:
                    cancel_res = self.client.cancel_order(order.get("product_id"), order_id)
                    if cancel_res.get("success"):
                        cancelled.append({
                            "order_id": order_id,
                            "symbol": order.get("symbol"),
                            "side": order.get("side"),
                            "price": order.get("limit_price")
                        })
                        logger.info(f"Cancelled pending entry order #{order_id} ({order.get('symbol')})")
        except Exception as e:
            logger.error(f"Error cancelling pending entry orders: {e}")

        return cancelled

    def verify_and_ensure_sl_protection(self) -> Dict[str, Any]:
        """
        Inspect all open positions on Delta Exchange.
        If any position exists without an active protective Stop-Loss order,
        flag the vulnerability and attempt to place an emergency protection stop.
        """
        audit = {"checked": 0, "unprotected": [], "protected": [], "emergency_stops_placed": []}
        try:
            pos_res = self.client.get_positions()
            if not pos_res.get("success"):
                return {"error": "Failed to fetch positions from exchange"}

            positions = [p for p in pos_res.get("result", []) if int(p.get("size", 0)) != 0]
            audit["checked"] = len(positions)

            orders_res = self.client.get_open_orders()
            open_orders = orders_res.get("result", []) if orders_res.get("success") else []

            for p in positions:
                sym = p.get("symbol", "")
                size = int(p.get("size", 0))
                entry_p = float(p.get("entry_price") or 0.0)
                product_id = p.get("product_id")

                # Look for matching stop orders for this symbol
                has_sl = any(
                    str(o.get("symbol")) == sym and ("stop" in str(o.get("order_type", "")).lower() or o.get("stop_order_type"))
                    for o in open_orders
                )

                if has_sl:
                    audit["protected"].append(sym)
                else:
                    audit["unprotected"].append(sym)
                    logger.warning(f"⚠️ VULNERABILITY: Position {sym} (size {size}) has NO active Stop Loss order!")
                    
                    # Place an emergency 1.5% protective Stop Loss
                    emergency_sl_price = round(entry_p * 0.985, 2) if size > 0 else round(entry_p * 1.015, 2)
                    sl_side = "sell" if size > 0 else "buy"
                    try:
                        sl_res = self.client.place_order(
                            product_id=product_id,
                            size=abs(size),
                            side=sl_side,
                            order_type="stop_market_order",
                            stop_price=emergency_sl_price
                        )
                        if sl_res.get("success"):
                            audit["emergency_stops_placed"].append({
                                "symbol": sym,
                                "stop_price": emergency_sl_price,
                                "order_id": sl_res.get("result", {}).get("id")
                            })
                            logger.info(f"Placed emergency SL for {sym} at ${emergency_sl_price}")
                    except Exception as sl_err:
                        logger.error(f"Failed to place emergency SL for {sym}: {sl_err}")

        except Exception as e:
            logger.error(f"Error during Stop-Loss protection audit: {e}")
            audit["error"] = str(e)

        return audit

    def emergency_flatten_all(self, authorized: bool = False) -> Dict[str, Any]:
        """
        Close all active positions immediately with market orders.
        Requires explicit authorization parameter to prevent accidental execution.
        """
        if not authorized:
            return {"error": "Emergency flatten requires explicit authorization confirmation."}

        closed = []
        errors = []
        try:
            pos_res = self.client.get_positions()
            if not pos_res.get("success"):
                return {"error": "Failed to fetch positions"}

            positions = [p for p in pos_res.get("result", []) if int(p.get("size", 0)) != 0]
            for p in positions:
                sym = p.get("symbol", "")
                size = int(p.get("size", 0))
                product_id = p.get("product_id")
                close_side = "sell" if size > 0 else "buy"
                
                # Market close
                close_res = self.client.place_order(
                    product_id=product_id,
                    size=abs(size),
                    side=close_side,
                    order_type="market_order"
                )
                if close_res.get("success"):
                    closed.append({"symbol": sym, "size": size, "close_side": close_side})
                else:
                    errors.append({"symbol": sym, "error": close_res.get("error")})

            # Also cancel all remaining orders
            self.cancel_pending_entry_orders()

        except Exception as e:
            errors.append({"general_error": str(e)})

        return {
            "status": "FLATTENED",
            "closed_positions": closed,
            "errors": errors
        }

