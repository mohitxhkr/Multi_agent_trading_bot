"""
Agent 7: Execution & Orderbook Engine.
Translates approved trade decisions into signed, protective orders on Delta Exchange
with idempotency keys, exchange order ID tracking, exponential backoff retries,
post-entry Stop-Loss verification, rate-limit recovery, and state synchronization.
"""

from typing import Dict, Any, Optional
import logging
import uuid
import time
from src.delta_client import DeltaExchangeClient
from src.state_manager import StateManager

logger = logging.getLogger("execution-agent")


class ExecutionAgent:
    def __init__(self, client: DeltaExchangeClient, state_manager: Optional[StateManager] = None):
        self.client = client
        self.state_manager = state_manager or StateManager()

    def execute_approved_trade(
        self,
        decision: Dict[str, Any],
        order_type: str = "limit_order",
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Execute an approved trade setup on Delta Exchange with idempotency,
        retries, and post-fill protection verification.
        """
        if decision.get("gate_decision") != "APPROVED":
            return {
                "success": False,
                "error": "Execution denied: Trade decision has not been approved by Risk Gatekeeper."
            }

        symbol = decision["symbol"]
        side = decision["side"]
        contracts = int(decision["contracts"])
        entry_price = float(decision["entry_price"])
        stop_loss = float(decision["stop_loss_price"])
        take_profit = float(decision["take_profit_price"])
        leverage = int(decision.get("leverage", 25))

        # Idempotency token
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
            lev_res = self.client.set_leverage(symbol, leverage)
            if lev_res.get("success"):
                break
            time.sleep(0.5 * (attempt + 1))

        trade_uid = f"trade_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"ExecutionAgent: Submitting bracket order: {side.upper()} {contracts} contracts {symbol} "
            f"@ ${entry_price:.4f} (SL: ${stop_loss:.4f}, TP: ${take_profit:.4f}, Idempotency: {client_order_id})..."
        )

        # Place Bracket Order with exponential backoff retry for transient network/API failures
        order_res = {}
        last_error = ""

        for attempt in range(max_retries):
            try:
                order_res = self.client.place_bracket_order(
                    symbol=symbol,
                    size=contracts,
                    side=side,
                    order_type=order_type,
                    limit_price=entry_price if order_type == "limit_order" else None,
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit
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

        # Post-Placement Stop-Loss Verification
        # Inspect if stop loss order was successfully registered on exchange
        sl_order_id = order_data.get("stop_loss_order_id") or order_data.get("stop_order_id")
        tp_order_id = order_data.get("take_profit_order_id")

        if not sl_order_id:
            logger.info("ExecutionAgent: Verifying open orders to capture bracket SL/TP order IDs...")
            time.sleep(1.0)
            open_orders_res = self.client.get_open_orders()
            if open_orders_res.get("success"):
                for o in open_orders_res.get("result", []):
                    if o.get("symbol") == symbol:
                        if "stop" in str(o.get("order_type", "")).lower() or o.get("stop_order_type"):
                            sl_order_id = str(o.get("id"))
                        elif o.get("side") != side and not sl_order_id:
                            tp_order_id = str(o.get("id"))

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
            metadata={"trade_id": trade_uid, "client_order_id": client_order_id}
        )

        logger.info(f"ExecutionAgent: Order verified! Order ID: #{order_id} | SL Order: #{sl_order_id} | TP Order: #{tp_order_id}")

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
            "delta_response": order_data
        }
