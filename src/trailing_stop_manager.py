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
        is_high_volatility: bool = False,
        trade_id: Optional[str] = None,
    ) -> None:
        """Register newly entered trade parameters for exact R-multiple trailing calculations."""
        risk = abs(entry_price - initial_sl)
        self.state[symbol] = {
            "symbol": symbol,
            "trade_id": trade_id or f"trade_{symbol}",
            "side": side.lower(),
            "entry_price": float(entry_price),
            "initial_sl": float(initial_sl),
            "current_sl": float(initial_sl),
            "initial_tp": float(initial_tp),
            "current_tp": float(initial_tp),
            "risk_per_unit": float(risk),
            "contracts": int(contracts),
            "highest_r_reached": 0.0,
            "lowest_r_reached": 0.0,
            "stage": 0,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "is_high_volatility": is_high_volatility,
            "created_at": time.time(),
        }
        self._save_state()
        vol_note = " [HIGH VOLATILITY BUFFER ENGAGED]" if is_high_volatility else ""
        logger.info(f"Registered trade for trailing stop: {symbol} | Entry: {entry_price} | SL: {initial_sl} | Risk: {risk:.2f}{vol_note}")

    def _is_market_highly_volatile(self, pos_state: Dict[str, Any]) -> bool:
        """
        Check if the market or position is in high volatility mode,
        either from initial trade registration or live market posture state.
        """
        if pos_state.get("is_high_volatility"):
            return True
        try:
            from multiagent_team.exposure_coach import POSTURE_STATE_FILE
            if os.path.exists(POSTURE_STATE_FILE):
                with open(POSTURE_STATE_FILE, "r", encoding="utf-8") as f:
                    posture_data = json.load(f)
                    if posture_data.get("btc_volatility_state") == "EXPANSION":
                        return True
                    if "VOLATILITY_EXPANSION" in posture_data.get("posture", ""):
                        return True
        except Exception:
            pass
        return False

    def get_wallet_metrics(self) -> Dict[str, Any]:
        """Fetch fresh wallet metrics from Delta Exchange."""
        try:
            wallet = self.client.get_wallet_balances()
            meta = wallet.get("meta", {}) if isinstance(wallet, dict) else {}
            net_equity = float(meta.get("net_equity", 0.0) or 0.0)
            avail_usd = 0.0
            avail_inr = 0.0
            total_usd = 0.0
            total_inr = 0.0

            if isinstance(wallet, dict) and wallet.get("result"):
                for a in wallet["result"]:
                    if a.get("asset_symbol") == "USD":
                        avail_usd = float(a.get("available_balance", "0") or 0.0)
                        avail_inr = float(a.get("available_balance_inr", "0") or 0.0)
                        total_usd = float(a.get("balance", "0") or 0.0)
                        total_inr = float(a.get("balance_inr", "0") or 0.0)
                        break

            if net_equity <= 0:
                net_equity = total_usd

            return {
                "net_equity_usd": round(net_equity, 2),
                "available_usd": round(avail_usd, 2),
                "available_inr": round(avail_inr, 2),
                "total_usd": round(total_usd, 2),
                "total_inr": round(total_inr, 2)
            }
        except Exception as e:
            logger.error(f"Error fetching wallet metrics: {e}")
            return {
                "net_equity_usd": 0.0,
                "available_usd": 0.0,
                "available_inr": 0.0,
                "total_usd": 0.0,
                "total_inr": 0.0
            }

    def check_and_update_trailing_stops(self) -> List[Dict[str, Any]]:
        """
        Inspect all open positions on Delta Exchange and trail Stop Losses if milestones reached.
        Detects order fills, Take Profit hits, and Stop Loss exits automatically.
        """
        positions_res = self.client.get_positions()
        if not positions_res.get("success"):
            return []

        active_positions = [p for p in positions_res.get("result", []) if int(p.get("size", 0)) != 0]
        active_symbols = {p.get("product_symbol") for p in active_positions}

        # -----------------------------------------------------------------
        # STEP 1: DETECT CLOSED POSITIONS (Target Hit / Stop Loss Hit)
        # -----------------------------------------------------------------
        closed_symbols = [s for s in list(self.state.keys()) if s not in active_symbols]
        for sym in closed_symbols:
            pos_state = self.state.pop(sym, None)
            if not pos_state:
                continue

            # Query recent fills on Delta Exchange to confirm exit price & time
            exit_price = None
            try:
                fills_res = self.client.get_fills(symbol=sym, page_size=5)
                for f in fills_res.get("result", []):
                    f_side = f.get("side", "").lower()
                    if (pos_state["side"] == "buy" and f_side == "sell") or (pos_state["side"] == "sell" and f_side == "buy"):
                        exit_price = float(f.get("price") or 0.0)
                        break
            except Exception as e:
                logger.error(f"Error fetching exit fills for {sym}: {e}")

            if not exit_price or exit_price <= 0:
                exit_price = pos_state.get("current_sl") or pos_state.get("entry_price")

            # Calculate realized PnL
            entry_p = pos_state["entry_price"]
            side = pos_state["side"]
            contracts = pos_state.get("contracts", 1)

            pinfo = self.client.get_product_info(sym)
            contract_value = float(pinfo.get("contract_value", "1.0")) if pinfo else 1.0

            if side == "buy":
                pnl = (exit_price - entry_p) * contracts * contract_value
                is_tp = exit_price >= (pos_state["current_tp"] * 0.998)
            else:
                pnl = (entry_p - exit_price) * contracts * contract_value
                is_tp = exit_price <= (pos_state["current_tp"] * 1.002)

            # Calculate return pct on margin used
            leverage = 25 if "BTC" not in sym else 50
            margin_used = (contracts * contract_value * entry_p) / leverage
            return_pct = (pnl / margin_used * 100.0) if margin_used > 0 else 0.0

            # Calculate R-multiple achieved
            risk_unit = pos_state.get("risk_per_unit", entry_p * 0.01)
            gain_per_unit = (exit_price - entry_p) if side == "buy" else (entry_p - exit_price)
            r_achieved = round(gain_per_unit / risk_unit, 2) if risk_unit > 0 else 0.0

            mfe_r = pos_state.get("highest_r_reached", max(r_achieved, 0.0))
            mae_r = pos_state.get("lowest_r_reached", min(r_achieved, 0.0))

            # Distinguish profitable trailing stop exits vs pure breakeven exits:
            # Once price locked profit (r >= 0.20 or PnL >= $0.20), celebrate as green trailing exit!
            is_profit_trailing = not is_tp and (r_achieved >= 0.20 or pnl >= 0.20)
            is_be = not is_tp and not is_profit_trailing and (pos_state.get("stage", 0) >= 1) and (abs(pnl) < 0.20)
            is_sl = not is_tp and not is_profit_trailing and not is_be

            # Record in persistent trade journal with MFE/MAE
            from src.journal import record_trade_exit, get_performance_summary
            exit_reason = "TAKE_PROFIT" if is_tp else ("PROFIT_TRAILING" if is_profit_trailing else ("BREAKEVEN" if is_be else "STOP_LOSS"))
            trade_id = pos_state.get("trade_id") or f"trade_{sym}"
            record_trade_exit(
                trade_id=trade_id,
                exit_price=exit_price,
                realized_pnl_usd=pnl,
                exit_reason=exit_reason,
                postmortem_notes=f"Exited at stage {pos_state.get('stage', 0)} ({r_achieved:+.2f}R | Return: {return_pct:+.1f}% | MFE: +{mfe_r}R | MAE: {mae_r}R)",
                mfe_r=mfe_r,
                mae_r=mae_r
            )

            # Get fresh wallet metrics & updated stats
            wallet_metrics = self.get_wallet_metrics()
            stats = get_performance_summary().get("stats", {})

            # Dispatch rich Telegram notification!
            if is_tp:
                self.telegram.notify_take_profit_hit(
                    symbol=sym,
                    side=side,
                    entry_price=entry_p,
                    exit_price=exit_price,
                    contracts=contracts,
                    realized_pnl=pnl,
                    return_pct=return_pct,
                    r_multiple=max(r_achieved, 2.0),
                    wallet=wallet_metrics,
                    stats=stats
                )
            elif is_profit_trailing:
                self.telegram.notify_profit_trailing_exit(
                    symbol=sym,
                    side=side,
                    entry_price=entry_p,
                    exit_price=exit_price,
                    contracts=contracts,
                    realized_pnl=pnl,
                    return_pct=return_pct,
                    r_multiple=r_achieved,
                    wallet=wallet_metrics,
                    stats=stats
                )
            elif is_be:
                self.telegram.notify_breakeven_exit(
                    symbol=sym,
                    side=side,
                    entry_price=entry_p,
                    exit_price=exit_price,
                    contracts=contracts,
                    realized_pnl=pnl,
                    wallet=wallet_metrics,
                    stats=stats
                )
            else:
                stage_label = "Initial Protective Stop Loss" if pos_state.get("stage", 0) == 0 else f"Trailing Stop (Stage {pos_state.get('stage')})"
                self.telegram.notify_stop_loss_hit(
                    symbol=sym,
                    side=side,
                    entry_price=entry_p,
                    exit_price=exit_price,
                    contracts=contracts,
                    realized_pnl=pnl,
                    return_pct=return_pct,
                    exit_stage=stage_label,
                    wallet=wallet_metrics,
                    stats=stats
                )

            logger.info(f"Position closed for {sym}: {exit_reason} @ ${exit_price} (PnL: ${pnl:.2f})")

            # ---------------------------------------------------------
            # Agent 6: Adaptive Learning, Pattern Diagnosis & Self-Audit
            # ---------------------------------------------------------
            try:
                from multiagent_team.adaptive_learning import AdaptiveLearningEngine
                learner = AdaptiveLearningEngine()
                reflection_res = learner.reflect_and_learn(
                    symbol=sym,
                    side=side,
                    entry_price=entry_p,
                    exit_price=exit_price,
                    realized_pnl=pnl,
                    r_multiple=r_achieved,
                    exit_reason=exit_reason,
                    trade_spec=pos_state
                )
                reflection_msg = learner.format_telegram_reflection(reflection_res)
                self.telegram.send_message(reflection_msg)
                logger.info(f"✅ Dispatched automated post-trade reflection for {sym} to Telegram.")
            except Exception as e:
                logger.error(f"Error during adaptive learning reflection: {e}")

            # Clean up any leftover open bracket orders for this symbol so nothing is orphaned
            try:
                self.client.cancel_all_orders(symbol=sym)
                logger.info(f"Cleaned up any orphaned bracket orders for {sym}")
            except Exception as e:
                logger.warning(f"Error cancelling leftover orders for {sym}: {e}")

            self._save_state()

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

            # Find matching SL and TP orders by product symbol or product ID
            sl_order = None
            tp_order = None
            for ord in open_orders:
                ord_pid = ord.get("product_id")
                ord_sym = ord.get("product_symbol")
                matches_prod = (ord_sym and ord_sym == symbol) or (ord_pid and pid and int(ord_pid) == int(pid))
                if matches_prod:
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
                    "lowest_r_reached": 0.0,
                    "stage": 0,
                    "sl_order_id": sl_order.get("id") if sl_order else None,
                    "tp_order_id": tp_order.get("id") if tp_order else None,
                    "created_at": time.time(),
                }
                self.state[symbol] = pos_state

            # Always synchronize with the active open bracket child order IDs on Delta Exchange
            if sl_order:
                pos_state["sl_order_id"] = sl_order.get("id")
            elif size != 0:
                # Emergency protective Stop Loss placement if protection missing
                logger.warning(f"⚠️ TrailingStopManager: Position {symbol} has NO Stop Loss order! Placing emergency stop...")
                emer_sl = round(entry_price * 0.985, 2) if side == "buy" else round(entry_price * 1.015, 2)
                sl_side = "sell" if side == "buy" else "buy"
                try:
                    placed_sl = self.client.place_protective_stop(
                        symbol=symbol,
                        size=abs(size),
                        side=side,
                        stop_price=emer_sl
                    )
                    if placed_sl.get("success"):
                        emer_id = placed_sl.get("result", {}).get("id")
                        pos_state["sl_order_id"] = emer_id
                        pos_state["current_sl"] = emer_sl
                        self.telegram.send_message(
                            f"🛡️ <b>[EMERGENCY SL PLACED]</b> Active position <b>{symbol}</b> was missing Stop Loss.\n"
                            f"• Placed emergency stop market order at <code>${emer_sl:,.2f}</code>."
                        )
                except Exception as e_sl:
                    logger.error(f"Failed to place emergency SL for {symbol}: {e_sl}")

            if tp_order:
                pos_state["tp_order_id"] = tp_order.get("id")

            # Sync partial fills or size adjustments
            if pos_state.get("contracts") != abs(size):
                pos_state["contracts"] = abs(size)

            # Notify Telegram when order transitions to FILLED on orderbook
            if not pos_state.get("fill_notified"):
                wallet_metrics = self.get_wallet_metrics()
                leverage = 25 if "BTC" not in symbol else 50
                self.telegram.notify_order_filled(
                    symbol=symbol,
                    side=side,
                    fill_price=entry_price,
                    contracts=abs(size),
                    leverage=leverage,
                    sl=pos_state.get("current_sl", 0.0),
                    tp=pos_state.get("current_tp", 0.0),
                    wallet=wallet_metrics
                )
                pos_state["fill_notified"] = True
                self._save_state()

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
            if "lowest_r_reached" not in pos_state:
                pos_state["lowest_r_reached"] = 0.0
            if current_r < pos_state.get("lowest_r_reached", 0.0):
                pos_state["lowest_r_reached"] = round(current_r, 2)

            current_sl = pos_state.get("current_sl", pos_state["initial_sl"])
            current_stage = pos_state.get("stage", 0)
            sl_order_id = pos_state.get("sl_order_id")
            tp_order_id = pos_state.get("tp_order_id")

            new_sl = None
            new_tp = None
            stage_narrative = ""
            new_stage = current_stage

            is_volatile = self._is_market_highly_volatile(pos_state)
            vol_badge = " 🌪️ [VOLATILITY BUFFER ACTIVE]" if is_volatile else ""

            # Volatility-adjusted milestone triggers:
            # Prevents premature breakeven traps by giving trades room to breathe during natural retests
            m1_trigger = 0.90 if is_volatile else 0.80
            m2_trigger = 1.20 if is_volatile else 1.10
            m3_trigger = 1.60 if is_volatile else 1.50
            m4_trigger = 1.90 if is_volatile else 1.80

            # ---------------------------------------------------------
            # Stage 1: Risk-Slashing Cushion (60% Downside Slashed, Breakeven Retest Protected)
            # ---------------------------------------------------------
            if current_r >= m1_trigger and current_stage < 1:
                # Do NOT snap SL directly to entry! Cut initial risk by 60% (move SL to -0.40R).
                # This leaves a huge 1.20R-1.30R breathing cushion so entry retests NEVER trigger stops!
                slash_ratio = 0.40
                if side == "buy":
                    candidate_sl = self.client.round_to_tick(symbol, entry_price - (slash_ratio * risk_per_unit))
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                else:
                    candidate_sl = self.client.round_to_tick(symbol, entry_price + (slash_ratio * risk_per_unit))
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl

                if new_sl:
                    new_stage = 1
                    stage_narrative = (
                        f"🛡️ <b>[RISK SLASHED BY 60% — BREATHING CUSHION ACTIVE{vol_badge}]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss moved to <b>${new_sl:,.2f}</b> (Risk cut from -1.0R to -0.40R)\n"
                        f"• Retest cushion: 1.20R+ space so natural breakout retests do not wick out the trade!"
                    )

            # ---------------------------------------------------------
            # Stage 2: Guaranteed Green Profit Lock (+0.30R Pure Green Banked)
            # ---------------------------------------------------------
            elif current_r >= m2_trigger and current_stage < 2:
                # Downside eliminated 100%! Locks in positive cash so the trade CANNOT exit at $0 breakeven.
                lock_ratio = 0.25 if is_volatile else 0.30
                if side == "buy":
                    candidate_sl = self.client.round_to_tick(symbol, entry_price + (lock_ratio * risk_per_unit))
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                else:
                    candidate_sl = self.client.round_to_tick(symbol, entry_price - (lock_ratio * risk_per_unit))
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl

                if new_sl:
                    new_stage = 2
                    stage_narrative = (
                        f"🔒 <b>[GUARANTEED GREEN PROFIT LOCKED — +{lock_ratio:.2f}R BANKED{vol_badge}]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss secured at <b>${new_sl:,.2f}</b> (Guaranteed green profit)\n"
                        f"• Breakeven trap avoided! Exits from here are guaranteed winners."
                    )

            # ---------------------------------------------------------
            # Stage 3: Core Profit Expansion (+0.85R Locked · >= 5-10%+ Margin Profit)
            # ---------------------------------------------------------
            elif current_r >= m3_trigger and current_stage < 3:
                # Locks in +0.85R pure profit (delivers 8-15%+ return on allocated margin)
                lock_ratio = 0.75 if is_volatile else 0.85
                if side == "buy":
                    candidate_sl = self.client.round_to_tick(symbol, entry_price + (lock_ratio * risk_per_unit))
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                else:
                    candidate_sl = self.client.round_to_tick(symbol, entry_price - (lock_ratio * risk_per_unit))
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl

                if new_sl:
                    new_stage = 3
                    stage_narrative = (
                        f"💰 <b>[CORE PROFIT SECURED — +{lock_ratio:.2f}R LOCKED{vol_badge}]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss moved to <b>${new_sl:,.2f}</b> (Banked ~10%+ margin return)\n"
                        f"• High quality gain banked, running towards final scalp target!"
                    )

            # ---------------------------------------------------------
            # Stage 4: Pre-Target Lock (+1.40R Locked)
            # ---------------------------------------------------------
            elif current_r >= m4_trigger and current_stage < 4:
                lock_ratio = 1.30 if is_volatile else 1.40
                if side == "buy":
                    candidate_sl = self.client.round_to_tick(symbol, entry_price + (lock_ratio * risk_per_unit))
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                else:
                    candidate_sl = self.client.round_to_tick(symbol, entry_price - (lock_ratio * risk_per_unit))
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl

                if new_sl:
                    new_stage = 4
                    stage_narrative = (
                        f"🎯 <b>[PRE-TARGET SECURED — +{lock_ratio:.2f}R IN BANK{vol_badge}]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Stop Loss locked at <b>${new_sl:,.2f}</b> (+{lock_ratio:.2f}R guaranteed)\n"
                        f"• Final Take Profit target in sight!"
                    )

            # ---------------------------------------------------------
            # Stage 5: Target Hit & Outsized Runner Trailing (Max Profit)
            # ---------------------------------------------------------
            elif current_r >= 2.00:
                # Dynamic runner trailing: trail at 0.55R behind mark price and extend TP
                runner_cushion = (0.65 * risk_per_unit) if is_volatile else (0.50 * risk_per_unit)
                if side == "buy":
                    candidate_sl = self.client.round_to_tick(symbol, mark_price - runner_cushion)
                    candidate_tp = self.client.round_to_tick(symbol, mark_price + (1.5 * risk_per_unit))
                    if candidate_sl > current_sl:
                        new_sl = candidate_sl
                        new_tp = candidate_tp
                else:
                    candidate_sl = self.client.round_to_tick(symbol, mark_price + runner_cushion)
                    candidate_tp = self.client.round_to_tick(symbol, mark_price - (1.5 * risk_per_unit))
                    if candidate_sl < current_sl:
                        new_sl = candidate_sl
                        new_tp = candidate_tp

                if new_sl:
                    new_stage = 5
                    stage_narrative = (
                        f"🏆 <b>[OUTSIZED RUNNER TRAILING — MAX PROFIT MODE{vol_badge}]</b>\n"
                        f"• Asset: <b>{symbol}</b> ({side.upper()})\n"
                        f"• Profit: <b>+{current_r:.2f}R</b> (Mark: ${mark_price:,.2f})\n"
                        f"• Trailing Stop updated to <b>${new_sl:,.2f}</b>\n"
                        f"• Take Profit extended to <b>${new_tp:,.2f}</b> to capture maximum trend expansion!"
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
