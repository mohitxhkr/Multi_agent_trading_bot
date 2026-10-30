"""
Agent 4: Execution & Order Manager.
Translates approved trade decisions from Agent 3 into signed, protective orders
on Delta Exchange (leveraged bracket entry, stop loss, take profit).
"""

from typing import Dict, Any
import logging
import uuid
from src.delta_client import DeltaExchangeClient

logger = logging.getLogger("execution-agent")


class ExecutionAgent:
    def __init__(self, client: DeltaExchangeClient):
        self.client = client

    def execute_approved_trade(self, decision: Dict[str, Any], order_type: str = "limit_order") -> Dict[str, Any]:
        """
        Execute an approved trade setup on Delta Exchange.
        """
        if decision.get("gate_decision") != "APPROVED":
            return {
                "success": False,
                "error": "Execution denied: Trade decision has not been approved by Risk Gatekeeper."
            }

        symbol = decision["symbol"]
        side = decision["side"]
        contracts = decision["contracts"]
        entry_price = decision["entry_price"]
        stop_loss = decision["stop_loss_price"]
        take_profit = decision["take_profit_price"]
        leverage = decision.get("leverage", 5)

        logger.info(f"ExecutionAgent: Setting leverage to {leverage}x for {symbol}...")
        lev_res = self.client.set_leverage(symbol, leverage)
        if not lev_res.get("success"):
            logger.warning(f"Leverage set returned warning: {lev_res.get('error')}")

        logger.info(
            f"ExecutionAgent: Submitting bracket order: {side.upper()} {contracts} contracts {symbol} "
            f"@ {entry_price} (SL: {stop_loss}, TP: {take_profit})..."
        )

        # Submit bracket order (entry + stop loss + take profit)
        order_res = self.client.place_bracket_order(
            symbol=symbol,
            size=contracts,
            side=side,
            order_type=order_type,
            limit_price=entry_price if order_type == "limit_order" else None,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit
        )

        trade_uid = f"trade_{uuid.uuid4().hex[:8]}"

        if order_res.get("success"):
            order_data = order_res.get("result", {})
            return {
                "success": True,
                "trade_id": trade_uid,
                "symbol": symbol,
                "order_id": order_data.get("id"),
                "status": "PLACED",
                "contracts": contracts,
                "side": side,
                "entry_price": entry_price,
                "stop_loss_price": stop_loss,
                "take_profit_price": take_profit,
                "delta_response": order_data
            }
        else:
            return {
                "success": False,
                "trade_id": trade_uid,
                "error": order_res.get("error", "Order placement failed on Delta Exchange"),
                "symbol": symbol
            }
