"""
Trailing Stop Loss & Profit Preservation Engine for Delta Exchange.
Monitors open positions and dynamically trails stop-loss orders in lockstep with
R-multiples (1:1 -> Breakeven, 1:2 -> Lock +1R & target 1:3, 1:3 -> Lock +2R & target 1:5).
"""

from typing import Dict, Any, List, Optional
import os
import sys
import json
import time
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.delta_client import DeltaExchangeClient
from src.telegram_notifier import TelegramNotifier
from src.technical_analysis import round_price

logger = logging.getLogger("trailing-stop-manager")


class TrailingStopManager:
    def __init__(
        self,
        client: Optional[DeltaExchangeClient] = None,
        telegram: Optional[TelegramNotifier] = None,
        state_file: str = "state/trailing_stop_state.json",
    ):
        self.client = client or DeltaExchangeClient()
        self.telegram = telegram or TelegramNotifier()
        self.state_file = state_file
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load trailing stop state: {e}")
        return {}

    def _save_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trailing stop state: {e}")

    def register_initial_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        initial_sl: float,
        initial_tp: float,
        contracts: int,
        sl_order_id: Optional[int] = None,
        tp_order_id: Optional[int] = None,
    ) -> None:
        """Register newly entered trade parameters for exact R-multiple trailing calculations."""
        risk = abs(entry_price - initial_sl)
        self.state[symbol] = {
            "symbol": symbol,
            "side": side.lower(),
            "entry_price": float(entry_price),
            "initial_sl": float(initial_sl),
            "current_sl": float(initial_sl),
            "initial_tp": float(initial_tp),
            "current_tp": float(initial_tp),
            "risk_per_unit": float(risk),
            "contracts": int(contracts),
            "highest_r_reached": 0.0,
            "stage": 0,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "created_at": time.time(),
        }
        self._save_state()
        logger.info(f"Registered trade for trailing stop: {symbol} | Entry: {entry_price} | SL: {initial_sl} | Risk: {risk:.2f}")

    def check_and_update_trailing_stops(self) -> List[Dict[str, Any]]:
        """
        Inspect all open positions on Delta Exchange and trail Stop Losses if milestones reached.
        """
        positions_res = self.client.get_positions()
        if not positions_res.get("success"):
            return []

        active_positions = [p for p in positions_res.get("result", []) if int(p.get("size", 0)) != 0]
        if not active_positions:
            return []

        # Fetch open orders to match bracket SL/TP orders
        open_orders_res = self.client.get_open_orders()
        open_orders = open_orders_res.get("result", []) if open_orders_res.get("success") else []

        updates_made = []

        for pos in active_positions:
            symbol = pos.get("product_symbol", "")
            pid = pos.get("product_id")
            size = int(pos.get("size", 0))
            side = "buy" if size > 0 else "sell"
            entry_price = float(pos.get("entry_price", 0.0))
            mark_price = float(pos.get("mark_price", 0.0))

            if not symbol or entry_price <= 0 or mark_price <= 0:
                continue

            # Find matching SL order
            sl_order = None
            tp_order = None
            for ord in open_orders:
                if ord.get("product_id") == pid:
                    s_type = ord.get("stop_order_type", "")
                    if s_type == "stop_loss_order":
                        sl_order = ord
                    elif s_type == "take_profit_order":
                        tp_order = ord

            # Retrieve or initialize state
            pos_state = self.state.get(symbol)
            if not pos_state:
                # Attempt to retrieve original trade from trade_journal.json
                journal_sl = None
                journal_tp = None
                journal_path = "state/trade_journal.json"
                if os.path.exists(journal_path):
                    try:
                        with open(journal_path, "r", encoding="utf-8") as jf:
                            jdata = json.load(jf)
                            for t in reversed(jdata.get("trades", [])):
                                if t.get("symbol") == symbol and t.get("status") == "OPEN":
                                    journal_sl = float(t.get("stop_loss", 0.0))
                                    journal_tp = float(t.get("take_profit", 0.0))
                                    break
                    except Exception as e:
                        logger.warning(f"Error checking journal for {symbol}: {e}")

                if journal_sl and journal_sl > 0:
                    current_sl_val = float(sl_order["stop_price"]) if sl_order and sl_order.get("stop_price") else journal_sl
                    risk = abs(entry_price - journal_sl)
                    initial_sl_val = journal_sl
                    initial_tp_val = journal_tp or (float(tp_order["stop_price"]) if tp_order and tp_order.get("stop_price") else 0.0)
                elif sl_order and sl_order.get("stop_price"):
                    current_sl_val = float(sl_order["stop_price"])
                    risk = abs(entry_price - current_sl_val)
                    if risk < (entry_price * 0.005):
                        risk = entry_price * 0.015  # Fallback 1.5% if already moved to breakeven
                    initial_sl_val = current_sl_val
                    initial_tp_val = float(tp_order["stop_price"]) if tp_order and tp_order.get("stop_price") else 0.0
                else:
                    risk = entry_price * 0.015
                    current_sl_val = entry_price - risk if side == "buy" else entry_price + risk
                    initial_sl_val = current_sl_val
                    initial_tp_val = float(tp_order["stop_price"]) if tp_order and tp_order.get("stop_price") else 0.0

                pos_state = {
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "initial_sl": initial_sl_val,
                    "current_sl": current_sl_val,
                    "initial_tp": initial_tp_val,
                    "current_tp": initial_tp_val,
                    "risk_per_unit": risk,
                    "contracts": abs(size),
                    "highest_r_reached": 0.0,
                    "stage": 0,
                    "sl_order_id": sl_order.get("id") if sl_order else None,
                    "tp_order_id": tp_order.get("id") if tp_order else None,
                    "created_at": time.time(),
                }
                self.state[symbol] = pos_state

            # Update order IDs if missing
            if sl_order and not pos_state.get("sl_order_id"):
                pos_state["sl_order_id"] = sl_order.get("id")
            if tp_order and not pos_state.get("tp_order_id"):
                pos_state["tp_order_id"] = tp_order.get("id")

            risk_per_unit = pos_state.get("risk_per_unit", entry_price * 0.015)
            if risk_per_unit <= 0:
                risk_per_unit = entry_price * 0.015

            # Calculate current R-multiple
            if side == "buy":
                gain = mark_price - entry_price
            else:
                gain = entry_price - mark_price

            current_r = gain / risk_per_unit
            if current_r > pos_state.get("highest_r_reached", 0.0):
                pos_state["highest_r_reached"] = round(current_r, 2)

            current_sl = pos_state.get("current_sl", pos_state["initial_sl"])
            current_stage = pos_state.get("stage", 0)
            sl_order_id = pos_state.get("sl_order_id")
            tp_order_id = pos_state.get("tp_order_id")

            new_sl = None
            new_tp = None
            stage_narrative = ""
            new_stage = current_stage

            # ---------------------------------------------------------
            # Milestone 1: At >= +1.0R -> Move SL to Breakeven (+0.05% fee buffer)
            # ---------------------------------------------------------
            if current_r >= 1.0 and current_stage < 1:
                buffer = risk_per_unit * 0.05
                if side == "buy":
                    candidate_sl = round_price(entry_price + buffer, entry_price)
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                else:
                    candidate_sl = round_price(entry_price - buffer, entry_price)
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl

                if new_sl:
                    new_stage = 1
                    stage_narrative = (
                        f"🛡️ <b>[BREAKEVEN ACTIVATED — ZERO RISK]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss moved from ${current_sl:,.2f} to <b>${new_sl:,.2f}</b> (Breakeven + fee buffer)\n"
                        f"• Downside risk is completely eliminated! Trade is now a free roll."
                    )

            # ---------------------------------------------------------
            # Milestone 2: At >= +2.0R -> Lock +1.0R profit & trail TP towards 1:3
            # ---------------------------------------------------------
            if current_r >= 2.0 and current_stage < 2:
                if side == "buy":
                    candidate_sl = round_price(entry_price + (1.0 * risk_per_unit), entry_price)
                    candidate_tp = round_price(entry_price + (3.0 * risk_per_unit), entry_price)
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                        new_tp = candidate_tp
                else:
                    candidate_sl = round_price(entry_price - (1.0 * risk_per_unit), entry_price)
                    candidate_tp = round_price(entry_price - (3.0 * risk_per_unit), entry_price)
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl
                        new_tp = candidate_tp

                if new_sl:
                    new_stage = 2
                    stage_narrative = (
                        f"💰 <b>[TRAILING STOP UPDATE — +1.0R PROFIT LOCKED]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss moved to <b>${new_sl:,.2f}</b> (Locking +1.0R pure profit)\n"
                        f"• Take Profit extended to <b>${new_tp:,.2f}</b> (Targeting 1:3 R:R runner expansion)!"
                    )

            # ---------------------------------------------------------
            # Milestone 3: At >= +3.0R -> Lock +2.0R profit & trail TP towards 1:5
            # ---------------------------------------------------------
            if current_r >= 3.0 and current_stage < 3:
                if side == "buy":
                    candidate_sl = round_price(entry_price + (2.0 * risk_per_unit), entry_price)
                    candidate_tp = round_price(entry_price + (5.0 * risk_per_unit), entry_price)
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                        new_tp = candidate_tp
                else:
                    candidate_sl = round_price(entry_price - (2.0 * risk_per_unit), entry_price)
                    candidate_tp = round_price(entry_price - (5.0 * risk_per_unit), entry_price)
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl
                        new_tp = candidate_tp

                if new_sl:
                    new_stage = 3
                    stage_narrative = (
                        f"🚀 <b>[TRAILING STOP UPDATE — +2.0R PROFIT LOCKED]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss moved to <b>${new_sl:,.2f}</b> (Locking +2.0R profit)\n"
                        f"• Take Profit extended to <b>${new_tp:,.2f}</b> (Targeting 1:5 R:R runner expansion)!"
                    )

            # ---------------------------------------------------------
            # Milestone 4: At >= +5.0R -> Lock +4.0R profit
            # ---------------------------------------------------------
            if current_r >= 5.0 and current_stage < 4:
                if side == "buy":
                    candidate_sl = round(entry_price + (4.0 * risk_per_unit), 2)
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                else:
                    candidate_sl = round(entry_price - (4.0 * risk_per_unit), 2)
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl

                if new_sl:
                    new_stage = 4
                    stage_narrative = (
                        f"🏆 <b>[MEGA RUNNER — +4.0R PROFIT LOCKED]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss locked at <b>${new_sl:,.2f}</b> (+4.0R in the bank)!"
                    )

            # Apply order modification on Delta Exchange if SL updated
            if new_sl and sl_order_id:
                logger.info(f"Modifying SL order {sl_order_id} on Delta Exchange to ${new_sl}...")
                edit_res = self.client.edit_order(
                    order_id=int(sl_order_id),
                    product_id=int(pid),
                    stop_price=new_sl,
                    limit_price=new_sl,
                )
                if edit_res.get("success"):
                    pos_state["current_sl"] = new_sl
                    pos_state["stage"] = new_stage
                    logger.info(f"✅ SL updated successfully to ${new_sl} for {symbol}")

                    # Update TP if extended
                    if new_tp and tp_order_id:
                        tp_edit_res = self.client.edit_order(
                            order_id=int(tp_order_id),
                            product_id=int(pid),
                            stop_price=new_tp,
                            limit_price=new_tp,
                        )
                        if tp_edit_res.get("success"):
                            pos_state["current_tp"] = new_tp

                    # Notify Telegram
                    if stage_narrative:
                        self.telegram.send_message(stage_narrative)

                    updates_made.append({
                        "symbol": symbol,
                        "new_sl": new_sl,
                        "new_tp": new_tp,
                        "stage": new_stage,
                        "r_multiple": current_r,
                    })
                else:
                    logger.warning(f"Failed to edit SL order on Delta: {edit_res.get('error')}")

        self._save_state()
        return updates_made
