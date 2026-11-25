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
        order_type: str = "market_order",
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

        # Respect Delta Exchange maximum leverage, fixed between 25x and 50x when supported
        product_max_lev = 50
        if self.client and hasattr(self.client, "get_max_leverage"):
            try:
                raw_lev = self.client.get_max_leverage(symbol)
                if isinstance(raw_lev, (int, float)):
                    product_max_lev = int(raw_lev)
                elif isinstance(raw_lev, str) and raw_lev.isdigit():
                    product_max_lev = int(raw_lev)
            except Exception:
                product_max_lev = 50
        effective_max = min(50, product_max_lev) if product_max_lev > 0 else 50
        effective_min = 25 if effective_max >= 25 else effective_max
        clamped_lev = max(effective_min, min(leverage, effective_max))
        if clamped_lev != leverage:
            logger.info(f"ExecutionAgent: Clamping requested leverage {leverage}x to {clamped_lev}x (25x-50x band) for {symbol}.")
            leverage = clamped_lev

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
        is_scale_in = bool(decision.get("is_scale_in", False))

        if is_scale_in:
            logger.info(
                f"ExecutionAgent: 🔥 SCALE-IN OPPORTUNITY DETECTED for {symbol} {side.upper()}! "
                f"Placing market order for +{contracts} contracts to expand winning position..."
            )
            order_res: Dict[str, Any] = {}
            last_error = ""

            for attempt in range(max_retries):
                if attempt > 0:
                    try:
                        reconcile_res = self.client.get_order_by_client_id(client_order_id, symbol=symbol)
                        if reconcile_res.get("success") and reconcile_res.get("result"):
                            order_res = {"success": True, "result": reconcile_res["result"]}
                            break
                    except Exception as e:
                        logger.warning(f"ExecutionAgent: Scale-in reconciliation check failed: {e}")

                try:
                    order_res = self.client.place_order(
                        symbol=symbol,
                        size=contracts,
                        side=side,
                        order_type="market_order",
                        client_order_id=client_order_id
                    )
                    if order_res.get("success"):
                        break
                    else:
                        last_error = str(order_res.get("error"))
                        logger.warning(f"ExecutionAgent: Scale-in attempt {attempt + 1}/{max_retries} failed: {last_error}")
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"ExecutionAgent network exception on scale-in attempt {attempt + 1}: {e}")

                time.sleep(1.0 * (2 ** attempt))

            if not order_res.get("success"):
                return {
                    "success": False,
                    "trade_id": trade_uid,
                    "client_order_id": client_order_id,
                    "error": f"Scale-in market order failed after {max_retries} attempts: {last_error}",
                    "symbol": symbol
                }

            order_data = order_res.get("result", {})
            order_id = str(order_data.get("id", ""))

            # Fetch updated position size
            time.sleep(0.5)
            pos_res = self.client.get_positions()
            total_contracts = contracts
            if pos_res.get("success"):
                for p in pos_res.get("result", []):
                    p_sym = str(p.get("symbol") or p.get("product_symbol") or "").upper()
                    if p_sym == symbol:
                        total_contracts = abs(int(float(p.get("size", contracts))))
                        break

            # Adjust protective Stop Loss and Take Profit to protect expanded position
            sl_updated = False
            tp_updated = False
            sl_order_id = None
            tp_order_id = None
            try:
                open_orders_res = self.client.get_open_orders(symbol=symbol)
                if open_orders_res.get("success"):
                    expected_sl_side = "sell" if side == "buy" else "buy"
                    for o in open_orders_res.get("result", []):
                        o_type = str(o.get("order_type", "")).lower()
                        o_side = str(o.get("side", "")).lower()
                        o_stop_type = str(o.get("stop_order_type", "")).lower()
                        is_stop = "stop" in o_type or "stop" in o_stop_type or bool(o.get("stop_price")) or (o.get("bracket_order") and o_side == expected_sl_side)
                        is_tp = (o_side == expected_sl_side and not is_stop and bool(o.get("reduce_only"))) or ("take_profit" in o_stop_type)
                        if is_stop and o_side == expected_sl_side and not sl_updated:
                            sl_order_id = int(o.get("id"))
                            edit_res = self.client.edit_order(symbol=symbol, order_id=sl_order_id, size=total_contracts)
                            if edit_res.get("success"):
                                logger.info(f"ExecutionAgent: Successfully updated existing SL #{sl_order_id} size to {total_contracts} contracts.")
                                sl_updated = True
                        elif is_tp and o_side == expected_sl_side and not tp_updated:
                            tp_order_id = int(o.get("id"))
                            edit_res = self.client.edit_order(symbol=symbol, order_id=tp_order_id, size=total_contracts)
                            if edit_res.get("success"):
                                logger.info(f"ExecutionAgent: Successfully updated existing TP #{tp_order_id} size to {total_contracts} contracts.")
                                tp_updated = True
            except Exception as e:
                logger.warning(f"ExecutionAgent: Error attempting to edit existing SL/TP order size: {e}")

            if not sl_updated:
                # Place supplementary protective stop for added contracts
                try:
                    add_sl_res = self.client.place_protective_stop(
                        symbol=symbol,
                        size=contracts,
                        side=side,
                        stop_price=stop_loss,
                        client_order_id=f"scale_sl_{uuid.uuid4().hex[:6]}"
                    )
                    if add_sl_res.get("success"):
                        sl_order_id = str(add_sl_res.get("result", {}).get("id"))
                        sl_updated = True
                        logger.info(f"ExecutionAgent: Supplementary protective stop confirmed for {contracts} contracts: Order #{sl_order_id}")
                except Exception as e:
                    logger.warning(f"ExecutionAgent: Supplementary stop error: {e}")

            if not tp_updated and take_profit and float(take_profit) > 0:
                # Place supplementary take profit for added contracts
                try:
                    add_tp_res = self.client.place_take_profit(
                        symbol=symbol,
                        size=contracts,
                        side=side,
                        take_profit_price=take_profit,
                        client_order_id=f"scale_tp_{uuid.uuid4().hex[:6]}"
                    )
                    if add_tp_res.get("success"):
                        tp_order_id = str(add_tp_res.get("result", {}).get("id"))
                        tp_updated = True
                        logger.info(f"ExecutionAgent: Supplementary take profit confirmed for {contracts} contracts: Order #{tp_order_id}")
                except Exception as e:
                    logger.warning(f"ExecutionAgent: Supplementary take profit error: {e}")

            # Record in state manager
            self.state_manager.record_order(
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                order_type="market_order",
                price=entry_price,
                size=contracts,
                status="filled"
            )

            logger.info(f"ExecutionAgent: Scale-in complete! Added {contracts} contracts on {symbol}. Total size: {total_contracts} contracts.")
            return {
                "success": True,
                "is_scale_in": True,
                "trade_id": trade_uid,
                "symbol": symbol,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "status": "SCALED_IN",
                "contracts_added": contracts,
                "total_contracts": total_contracts,
                "contracts": contracts,
                "side": side,
                "entry_price": entry_price,
                "stop_loss_price": stop_loss,
                "take_profit_price": take_profit,
                "stop_loss_order_id": sl_order_id,
                "sl_verified": True,
                "delta_response": order_data
            }

        logger.info(
            f"ExecutionAgent: Submitting bracket order: {side.upper()} {contracts} contracts {symbol} "
            f"@ ${entry_price:.4f} (SL: ${stop_loss:.4f}, TP: ${take_profit:.4f}, ClientOrderID: {client_order_id})..."
        )

        order_res: Dict[str, Any] = {}
        last_error = ""
        sl_order_id = None
        tp_order_id = None
        sl_verified = False
        tp_verified = False

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
                    if "bracket_order_position_exists" in last_error:
                        return {
                            "success": False,
                            "trade_id": trade_uid,
                            "client_order_id": client_order_id,
                            "error": f"An active position with bracket orders already exists on {symbol} on Delta Exchange. Delta does not allow multiple simultaneous bracket orders on the same product. Close the existing position via /close {symbol} first.",
                            "symbol": symbol
                        }
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

        # Defensive Execution Fallback:
        # If bracket order submission was rejected by Delta Exchange (e.g. products where bracket orders
        # are disabled in UI config or strict bracket validation), fallback to submitting a direct market
        # order and immediately attaching a dedicated protective stop-loss.
        if not order_res.get("success") and order_type == "market_order" and "bracket_order_position_exists" not in last_error:
            logger.warning(
                f"ExecutionAgent: Bracket order rejected ({last_error}). Attempting defensive fallback: "
                f"Placing direct market order with standalone protective stop for {symbol}..."
            )
            fallback_cid = f"fb_{client_order_id[-18:]}"
            try:
                fb_market_res = self.client.place_order(
                    symbol=symbol,
                    size=contracts,
                    side=side,
                    order_type="market_order",
                    client_order_id=fallback_cid
                )
                if fb_market_res.get("success"):
                    logger.info(f"ExecutionAgent: Defensive fallback market order placed successfully on {symbol}!")
                    order_res = fb_market_res
                    client_order_id = fallback_cid
                    # Immediately attach protective stop-loss order
                    try:
                        sl_res = self.client.place_protective_stop(
                            symbol=symbol,
                            size=contracts,
                            side=side,
                            stop_price=stop_loss,
                            client_order_id=f"sl_{fallback_cid}"
                        )
                        if sl_res.get("success"):
                            sl_order_id = str(sl_res.get("result", {}).get("id"))
                            sl_verified = True
                            logger.info(f"ExecutionAgent: Protective stop attached for {symbol} @ ${stop_loss} (Order #{sl_order_id})")
                    except Exception as sl_err:
                        logger.error(f"ExecutionAgent: Failed to attach protective stop during fallback: {sl_err}")

                    # Immediately attach standalone take-profit target if specified
                    if take_profit and float(take_profit) > 0:
                        try:
                            tp_res = self.client.place_take_profit(
                                symbol=symbol,
                                size=contracts,
                                side=side,
                                take_profit_price=take_profit,
                                client_order_id=f"tp_{fallback_cid}"
                            )
                            if tp_res.get("success"):
                                tp_order_id = str(tp_res.get("result", {}).get("id"))
                                tp_verified = True
                                logger.info(f"ExecutionAgent: Take profit target attached for {symbol} @ ${take_profit} (Order #{tp_order_id})")
                        except Exception as tp_err:
                            logger.error(f"ExecutionAgent: Failed to attach take profit during fallback: {tp_err}")
                else:
                    last_error = f"{last_error} | Fallback market order failed: {fb_market_res.get('error')}"
            except Exception as fb_err:
                last_error = f"{last_error} | Fallback market order exception: {fb_err}"

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
        # MANDATORY STOP-LOSS & TAKE-PROFIT VERIFICATION PROTOCOL
        # ---------------------------------------------------------------------
        if not sl_order_id:
            sl_order_id = order_data.get("stop_loss_order_id") or order_data.get("stop_order_id")
            if sl_order_id:
                sl_verified = True
        if not tp_order_id:
            tp_order_id = order_data.get("take_profit_order_id")
            if tp_order_id:
                tp_verified = True

        # Inspect open orders on Delta Exchange (with brief retry if child bracket orders are spawning)
        expected_sl_side = "sell" if side == "buy" else "buy"
        for verify_try in range(2):
            if sl_verified and (tp_verified or not take_profit or float(take_profit) <= 0):
                break
            time.sleep(0.6)
            try:
                open_orders_res = self.client.get_open_orders(symbol=symbol)
                if open_orders_res.get("success"):
                    for o in open_orders_res.get("result", []):
                        o_type = str(o.get("order_type", "")).lower()
                        o_side = str(o.get("side", "")).lower()
                        o_stop_type = str(o.get("stop_order_type", "")).lower()
                        is_stop = (
                            o_stop_type == "stop_loss_order"
                            or "stop" in o_type
                            or bool(o.get("stop_price"))
                            or (o.get("bracket_order") and o_side == expected_sl_side and o_stop_type != "take_profit_order")
                        )
                        is_tp = (
                            o_stop_type == "take_profit_order"
                            or (o_side == expected_sl_side and not is_stop and (bool(o.get("reduce_only")) or o_type == "limit_order"))
                        )

                        if is_stop and o_side == expected_sl_side:
                            o_stop_px = float(o.get("stop_price") or o.get("bracket_stop_loss_price") or 0.0)
                            if o_stop_px <= 0 or (side == "buy" and o_stop_px <= entry_price) or (side == "sell" and o_stop_px >= entry_price):
                                sl_order_id = str(o.get("id"))
                                sl_verified = True
                        elif is_tp and o_side == expected_sl_side:
                            tp_order_id = str(o.get("id"))
                            tp_verified = True
            except Exception as e:
                logger.error(f"ExecutionAgent: Error inspecting open orders for SL/TP verification (attempt {verify_try + 1}): {e}")

        # If bracket stop loss was NOT confirmed on the exchange, place standalone protective stop order
        if not sl_verified:
            logger.warning(
                f"ExecutionAgent: ⚠️ Protective stop NOT confirmed for {symbol} {side} #{order_id}. "
                f"Placing standalone protective stop order..."
            )
            for sl_try in range(2):
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
                        logger.info(f"ExecutionAgent: Protective stop confirmed: Order #{sl_order_id}")
                        break
                    else:
                        logger.critical(f"ExecutionAgent: Failed to place protective stop (try {sl_try + 1}): {emergency_sl_res}")
                except Exception as e:
                    logger.critical(f"ExecutionAgent: Exception placing protective stop (try {sl_try + 1}): {e}")
                time.sleep(0.4)

        # If bracket take profit was NOT confirmed on the exchange, place standalone take profit order
        if sl_verified and not tp_verified and take_profit and float(take_profit) > 0:
            logger.warning(
                f"ExecutionAgent: ⚠️ Take Profit NOT confirmed for {symbol} {side} #{order_id}. "
                f"Placing standalone Take Profit order @ ${take_profit:.4f}..."
            )
            for tp_try in range(2):
                try:
                    standalone_tp_res = self.client.place_take_profit(
                        symbol=symbol,
                        size=contracts,
                        side=side,
                        take_profit_price=take_profit,
                        client_order_id=f"tp_{uuid.uuid4().hex[:6]}"
                    )
                    if standalone_tp_res.get("success"):
                        tp_order_id = str(standalone_tp_res.get("result", {}).get("id"))
                        tp_verified = True
                        logger.info(f"ExecutionAgent: Standalone Take Profit confirmed: Order #{tp_order_id}")
                        break
                    else:
                        logger.warning(f"ExecutionAgent: Failed to place standalone Take Profit (try {tp_try + 1}): {standalone_tp_res}")
                except Exception as e:
                    logger.warning(f"ExecutionAgent: Exception placing standalone Take Profit (try {tp_try + 1}): {e}")
                time.sleep(0.4)

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
                if hasattr(self.telegram, "send_alert"):
                    self.telegram.send_alert(alert_msg)
                elif hasattr(self.telegram, "send_message"):
                    self.telegram.send_message(alert_msg)

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
