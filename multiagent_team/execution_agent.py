"""
Agent 7: Execution & Orderbook Engine.
Translates approved trade decisions into signed, protective orders on Delta Exchange
with strict idempotency keys, pre-retry order reconciliation, post-entry Stop-Loss
verification, and automated emergency protection protocols.
"""

from typing import Dict, Any, Optional
import logging
import uuid
import time
from src.delta_client import DeltaExchangeClient
from src.state_manager import StateManager
from src.telegram_notifier import TelegramNotifier

logger = logging.getLogger("execution-agent")


class ExecutionAgent:
    def __init__(
        self,
        client: DeltaExchangeClient,
        state_manager: Optional[StateManager] = None,
        telegram: Optional[TelegramNotifier] = None
    ):
        self.client = client
        self.state_manager = state_manager or StateManager()
        self.telegram = telegram or TelegramNotifier()

    def execute_approved_trade(
        self,
        decision: Dict[str, Any],
        order_type: str = "limit_order",
        max_retries: int = 3,
        execution_token: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute an approved trade setup on Delta Exchange with idempotency,
        safe timeout reconciliation, and mandatory verified stop-loss protection.
        """
        # Validate decision gate
        if decision.get("gate_decision") != "APPROVED":
            return {
                "success": False,
                "error": "Execution denied: Trade decision has not been approved by Risk Gatekeeper."
            }

        # Check execution token if provided (Deterministic Safety Controller)
        if execution_token:
            if not execution_token.get("valid") or time.time() > execution_token.get("expires_at", 0):
                return {
                    "success": False,
                    "error": "Execution denied: Safety controller execution token is invalid or expired."
                }

        symbol = decision["symbol"]
        side = decision["side"].lower()
        contracts = int(decision["contracts"])
        entry_price = float(decision["entry_price"])
        stop_loss = float(decision["stop_loss_price"])
        take_profit = float(decision["take_profit_price"])
        leverage = int(decision.get("leverage", 25))

        if contracts <= 0:
            return {
                "success": False,
                "error": "Execution denied: Sized contracts must be >= 1."
            }

        # Idempotency token (unique client_order_id)
        client_order_id = decision.get("client_order_id") or f"cl_{symbol}_{side}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        if self.state_manager.is_client_order_id_used(client_order_id):
            logger.error(f"ExecutionAgent: Idempotency violation! Order {client_order_id} was already submitted.")
            return {
                "success": False,
                "error": f"Duplicate order prevented by idempotency token {client_order_id}"
            }

        # Set Leverage with retry
        logger.info(f"ExecutionAgent: Configuring {leverage}x isolated leverage for {symbol}...")
        for attempt in range(max_retries):
            try:
                lev_res = self.client.set_leverage(symbol, leverage)
                if lev_res.get("success"):
                    break
            except Exception as e:
                logger.warning(f"ExecutionAgent: Leverage set attempt {attempt + 1} error: {e}")
            time.sleep(0.5 * (attempt + 1))

        trade_uid = f"trade_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"ExecutionAgent: Submitting bracket order: {side.upper()} {contracts} contracts {symbol} "
            f"@ ${entry_price:.4f} (SL: ${stop_loss:.4f}, TP: ${take_profit:.4f}, ClientOrderID: {client_order_id})..."
        )

        order_res: Dict[str, Any] = {}
        last_error = ""

        # Pre-retry reconciliation loop: never place duplicate order on ambiguous timeout
        for attempt in range(max_retries):
            # Check if order already exists on exchange before retrying
            if attempt > 0:
                logger.info(f"ExecutionAgent: Reconciling client_order_id {client_order_id} on exchange before retry {attempt + 1}...")
                try:
                    reconcile_res = self.client.get_order_by_client_id(client_order_id, symbol=symbol)
                    if reconcile_res.get("success") and reconcile_res.get("result"):
                        existing_order = reconcile_res["result"]
                        logger.info(f"ExecutionAgent: Order already exists on exchange: ID #{existing_order.get('id')}, status: {existing_order.get('state')}")
                        order_res = {"success": True, "result": existing_order}
                        break
                except Exception as e:
                    logger.warning(f"ExecutionAgent: Reconciliation check failed: {e}")

            try:
                order_res = self.client.place_bracket_order(
                    symbol=symbol,
                    size=contracts,
                    side=side,
                    order_type=order_type,
                    limit_price=entry_price if order_type == "limit_order" else None,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
                    client_order_id=client_order_id
                )
                if order_res.get("success"):
                    break
                else:
                    last_error = str(order_res.get("error"))
                    logger.warning(f"ExecutionAgent: Attempt {attempt + 1}/{max_retries} failed: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"ExecutionAgent network exception on attempt {attempt + 1}: {e}")

            time.sleep(1.0 * (2 ** attempt))

        # Final reconciliation check if all retries timed out/failed
        if not order_res.get("success"):
            try:
                reconcile_res = self.client.get_order_by_client_id(client_order_id, symbol=symbol)
                if reconcile_res.get("success") and reconcile_res.get("result"):
                    order_res = {"success": True, "result": reconcile_res["result"]}
            except Exception:
                pass

        if not order_res.get("success"):
            return {
                "success": False,
                "trade_id": trade_uid,
                "client_order_id": client_order_id,
                "error": f"Failed after {max_retries} attempts: {last_error}",
                "symbol": symbol
            }

        order_data = order_res.get("result", {})
        order_id = str(order_data.get("id", ""))
        order_status = order_data.get("state", "open")

        # Record order in persistent state manager
        self.state_manager.record_order(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=entry_price,
            size=contracts,
            status=order_status
        )

        # ---------------------------------------------------------------------
        # MANDATORY STOP-LOSS VERIFICATION & EMERGENCY PROTOCOL
        # ---------------------------------------------------------------------
        sl_order_id = order_data.get("stop_loss_order_id") or order_data.get("stop_order_id")
        tp_order_id = order_data.get("take_profit_order_id")

        # Verify stop loss order existence and properties on Delta Exchange
        sl_verified = False
        time.sleep(0.5)

        try:
            open_orders_res = self.client.get_open_orders(symbol=symbol)
            if open_orders_res.get("success"):
                expected_sl_side = "sell" if side == "buy" else "buy"
                for o in open_orders_res.get("result", []):
                    o_type = str(o.get("order_type", "")).lower()
                    o_side = str(o.get("side", "")).lower()
                    is_stop = "stop" in o_type or bool(o.get("stop_order_type")) or bool(o.get("stop_price"))
                    
                    if is_stop and o_side == expected_sl_side:
                        # Verify stop price orientation
                        o_stop_px = float(o.get("stop_price") or 0.0)
                        if (side == "buy" and o_stop_px <= entry_price) or (side == "sell" and o_stop_px >= entry_price):
                            sl_order_id = str(o.get("id"))
                            sl_verified = True
                            break
                    elif o_side == expected_sl_side and not is_stop and not tp_order_id:
                        tp_order_id = str(o.get("id"))
        except Exception as e:
            logger.error(f"ExecutionAgent: Error inspecting open orders for SL verification: {e}")

        # If bracket stop loss was not confirmed on the exchange, attempt immediate dedicated stop order
        if not sl_verified:
            logger.warning(
                f"ExecutionAgent: ⚠️ Protective stop NOT confirmed for {symbol} {side} #{order_id}. "
                f"Triggering emergency protective stop placement..."
            )
            try:
                emergency_sl_res = self.client.place_protective_stop(
                    symbol=symbol,
                    size=contracts,
                    side=side,
                    stop_price=stop_loss,
                    client_order_id=f"emerg_sl_{uuid.uuid4().hex[:6]}"
                )
                if emergency_sl_res.get("success"):
                    sl_order_id = str(emergency_sl_res.get("result", {}).get("id"))
                    sl_verified = True
                    logger.info(f"ExecutionAgent: Emergency protective stop confirmed: Order #{sl_order_id}")
                else:
                    logger.critical(f"ExecutionAgent: Failed to place emergency protective stop: {emergency_sl_res}")
            except Exception as e:
                logger.critical(f"ExecutionAgent: Exception placing emergency protective stop: {e}")

        # CRITICAL FAIL-SAFE: If protective coverage is STILL missing, do NOT accept naked position!
        if not sl_verified:
            logger.critical(
                f"ExecutionAgent: 🚨 CRITICAL SAFETY BREACH: Position on {symbol} is UNPROTECTED at exchange. "
                f"Executing emergency market close to protect capital!"
            )
            # Execute emergency position closure
            close_res = self.client.close_position(symbol)
            alert_msg = (
                f"🚨 *CRITICAL EXECUTION ABORT: UNPROTECTED POSITION*\n\n"
                f"Symbol: `{symbol}`\n"
                f"Side: `{side.upper()}`\n"
                f"Order ID: `#{order_id}`\n"
                f"Reason: Exchange stop-loss order failed verification and emergency stop was rejected.\n"
                f"Action Taken: Immediate emergency market close dispatched (`{close_res.get('success')}`)."
            )
            if self.telegram:
                self.telegram.send_alert(alert_msg)

            return {
                "success": False,
                "trade_id": trade_uid,
                "symbol": symbol,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "status": "EMERGENCY_ABORTED",
                "error": "Protective stop-loss order could not be verified on Delta Exchange. Position emergency-closed.",
                "emergency_close_response": close_res
            }

        # Save active position state for instant recovery
        self.state_manager.save_position(
            symbol=symbol,
            side=side,
            contracts=contracts,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_order_id=sl_order_id,
            tp_order_id=tp_order_id,
            metadata={"trade_id": trade_uid, "client_order_id": client_order_id, "sl_verified": True}
        )

        logger.info(f"ExecutionAgent: Order verified & protected! Order ID: #{order_id} | SL Order: #{sl_order_id} | TP Order: #{tp_order_id}")

        return {
            "success": True,
            "trade_id": trade_uid,
            "symbol": symbol,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "status": "PLACED",
            "contracts": contracts,
            "side": side,
            "entry_price": entry_price,
            "stop_loss_price": stop_loss,
            "take_profit_price": take_profit,
            "stop_loss_order_id": sl_order_id,
            "take_profit_order_id": tp_order_id,
            "sl_verified": True,
            "delta_response": order_data
        }
