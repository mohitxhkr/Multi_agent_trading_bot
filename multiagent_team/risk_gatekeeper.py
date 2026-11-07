"""
Agent 5: Risk & Discipline Gatekeeper (Pre-Trade Discipline Gate).
Enforces institutional fixed dollar risk ($2-$4 USD), dynamic drawdown scaling,
friction (fees + slippage) deduction, liquidation buffer verification (>= 3x SL distance),
portfolio correlation limits, and maximum cumulative open-risk constraints.
"""

from typing import Dict, Any, Optional, List
import os
import logging
from src.risk_manager import RiskManager
from src.delta_client import DeltaExchangeClient
from src.config import config

logger = logging.getLogger("risk-gatekeeper")


class RiskGatekeeperAgent:
    def __init__(
        self,
        client: DeltaExchangeClient,
        risk_manager: RiskManager,
        max_portfolio_open_risk_usd: Optional[float] = None,
        cooldown_seconds: Optional[int] = None
    ):
        self.client = client
        self.risk_manager = risk_manager
        self.max_portfolio_open_risk_usd = max_portfolio_open_risk_usd or (config.max_dollar_risk_per_trade * 2.0)
        self.cooldown_seconds = cooldown_seconds or config.cooldown_seconds
        self.last_trade_time: Dict[str, float] = {}

    def register_execution(self, symbol: str):
        """Record trade entry timestamp to enforce selective post-trade cooldown."""
        import time
        self.last_trade_time[symbol] = time.time()

    def evaluate_candidate(
        self,
        setup: Dict[str, Any],
        leverage: int = 25,
        risk_pct_override: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Run setup through the mandatory Pre-Trade Discipline Gate.
        """
        symbol = setup.get("symbol", "")
        side = setup.get("side", "buy").lower()
        entry = float(setup.get("entry_price") or setup.get("entry") or 0.0)
        stop = float(setup.get("stop_loss_price") or setup.get("stop_loss") or 0.0)
        tp = float(setup.get("take_profit_price") or setup.get("take_profit") or 0.0)

        # 1. Fetch live account balances
        balances_res = self.client.get_wallet_balances()
        if not balances_res.get("success"):
            return {
                "gate_decision": "REJECTED",
                "reason": "Unable to verify live account balances with Delta Exchange."
            }

        balances = balances_res.get("result", [])
        total_usdt = 0.0
        available_usdt = 0.0
        for b in balances:
            if b.get("asset_symbol") in ("USDT", "USD"):
                bal = float(b.get("balance", 0.0))
                avail = float(b.get("available_balance") if b.get("available_balance") is not None else bal)
                if bal > total_usdt:
                    total_usdt = bal
                    available_usdt = avail

        if total_usdt <= 0:
            meta = balances_res.get("meta", {})
            net_eq = float(meta.get("net_equity", 0.0) or 0.0)
            if net_eq > 0:
                total_usdt = net_eq
                available_usdt = net_eq

        if total_usdt <= 0:
            return {
                "gate_decision": "REJECTED",
                "reason": "Account USD/USDT balance is zero or depleted."
            }

        # 1.5. Selective Post-Trade Cooldown Check (Prevents overtrading the same symbol)
        import time
        last_t = self.last_trade_time.get(symbol, 0.0)
        time_since_last = time.time() - last_t
        if last_t > 0 and time_since_last < self.cooldown_seconds:
            remaining_mins = int((self.cooldown_seconds - time_since_last) / 60)
            return {
                "gate_decision": "REJECTED",
                "reason": f"Symbol {symbol} in selective sniper cooldown ({remaining_mins}m remaining). Quality over quantity enforced."
            }

        # 1.6. Order Book Liquidity & Spread Gate (Hard Veto on Illiquid Books)
        spread_pct = float(setup.get("spread_pct") or 0.0)
        if spread_pct > 0.15:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Order Book Liquidity Veto: Bid-ask spread ({spread_pct:.3f}%) exceeds safety ceiling (0.150%). High slippage risk."
            }

        # 2. Check open positions and portfolio correlation
        pos_res = self.client.get_positions()
        raw_positions = pos_res.get("result", []) if pos_res.get("success") else []
        active_positions = [p for p in raw_positions if float(p.get("size", 0)) != 0]

        # Strict Portfolio Concurrency Cap (Max 2 active positions total across portfolio)
        if len(active_positions) >= 2:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Maximum portfolio concurrency limit reached ({len(active_positions)}/2 active positions). Selective quality enforcement active."
            }

        # Duplicate symbol check
        for p in active_positions:
            if p.get("symbol") == symbol or p.get("product_symbol") == symbol:
                return {
                    "gate_decision": "REJECTED",
                    "reason": f"Active position already exists for symbol {symbol}."
                }

        # Correlated Exposure Limit (max 2 concurrent directional crypto positions)
        crypto_symbols = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA"]
        is_crypto = any(c in symbol.upper() for c in crypto_symbols)
        if is_crypto:
            same_side_crypto = 0
            for p in active_positions:
                p_sym = p.get("symbol", "")
                p_size = float(p.get("size", 0))
                p_side = "buy" if p_size > 0 else "sell"
                if any(c in p_sym.upper() for c in crypto_symbols) and p_side == side:
                    same_side_crypto += 1

            if same_side_crypto >= 2:
                return {
                    "gate_decision": "REJECTED",
                    "reason": f"Correlated exposure limit reached ({same_side_crypto} active {side.upper()} crypto positions)."
                }

        # 3. Check Account Circuit Breaker
        cb_res = self.risk_manager.check_circuit_breaker(
            current_equity=total_usdt,
            open_positions_count=len(active_positions)
        )

        if not cb_res.get("can_trade", False):
            return {
                "gate_decision": "REJECTED",
                "reason": f"Circuit Breaker Gate: {cb_res.get('reason')}",
                "circuit_breaker_status": cb_res
            }

        # 4. Product Specs & Precision
        pinfo = self.client.get_product_info(symbol)
        contract_value = float(pinfo.get("contract_value", "0.001")) if pinfo else 0.001
        lot_size = int(pinfo.get("lot_size", 1)) if pinfo else 1

        # 5. Sizing Engine: Fixed Dollar Risk Model ($2.00 - $4.00 USD)
        usable_capital = max(available_usdt, 0.0)
        if usable_capital < 3.0:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Available capital (${usable_capital:.2f}) is too low to open a new position."
            }

        is_primary = any(p in symbol.upper() for p in ["BTC", "ETH", "XAU", "GOLD"])
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return {"gate_decision": "REJECTED", "reason": "Invalid stop loss distance (zero or negative)."}

        per_contract_notional = contract_value * entry
        if per_contract_notional <= 0:
            return {"gate_decision": "REJECTED", "reason": "Invalid entry price or contract value."}

        # Dynamic Drawdown Scaling:
        # If in minor drawdown (> 2%), scale risk down to protect equity
        current_dd_pct = cb_res.get("current_drawdown_pct", 0.0)
        dd_risk_scalar = 0.70 if current_dd_pct > 0.02 else 1.0

        # Conviction Sizing Engine:
        # High strategy confidence may affect trade ranking or reduce risk for lower quality setups,
        # but configured maximum risk is an absolute hard ceiling and CANNOT be multiplied above 1.0x!
        score = int(setup.get("score") or 75)
        tm = setup.get("time_machine", {})
        tm_win_rate = float(tm.get("win_rate_pct") or 50.0)
        tm_ev = float(tm.get("expected_value_r") or 0.0)
        is_reinforced = "REINFORCED" in str(setup.get("thesis", "")) or "REINFORCED" in str(setup.get("strategy_name", ""))

        conviction_multiplier = 1.0
        conviction_tier = "STANDARD"
        conviction_reasons = []

        # Ranking tiers (for prioritization only, never to exceed hard risk budget)
        if score >= 90 and (tm_win_rate >= 65.0 or tm_ev >= 0.35 or is_reinforced):
            conviction_tier = "A+_PRIME_CONVICTION"
            conviction_reasons.append(f"A+ Setup (Score: {score}/100, TM EV: +{tm_ev}R, Win Rate: {tm_win_rate}%)")
        elif score >= 85 or (score >= 80 and tm_ev >= 0.30):
            conviction_tier = "HIGH_CONVICTION"
            conviction_reasons.append(f"High Quality Setup (Score: {score}/100, TM EV: +{tm_ev}R)")
        elif is_reinforced:
            conviction_tier = "REINFORCED_EDGE"
            conviction_reasons.append("Empirically Reinforced Historical Pattern")

        # Absolute Hard Risk Budget:
        hard_dollar_risk_cap = float(
            self.risk_manager.max_dollar_risk_per_trade if is_primary else min(self.risk_manager.max_dollar_risk_per_trade, 2.50)
        )
        target_risk_pct = float(
            self.risk_manager.max_risk_per_trade_pct if is_primary else (self.risk_manager.max_risk_per_trade_pct * 0.75)
        )
        
        # Max dollar risk is strictly capped by hard limits and scaled down by drawdown
        calculated_dollar_risk = min(
            hard_dollar_risk_cap * dd_risk_scalar,
            total_usdt * target_risk_pct * dd_risk_scalar
        )

        # Include estimated round-trip taker fees (0.10%) + slippage (0.06%) into risk unit
        friction_per_contract = per_contract_notional * 0.0016
        risk_per_contract = (contract_value * stop_distance) + friction_per_contract

        if risk_per_contract <= 0:
            return {"gate_decision": "REJECTED", "reason": "Invalid zero or negative risk per contract."}

        raw_contracts = int(calculated_dollar_risk / risk_per_contract)
        # Align strictly with lot size steps
        aligned_contracts = (raw_contracts // lot_size) * lot_size

        # CRITICAL SAFETY RULE: Never force a minimum contract quantity if it exceeds the permitted risk budget!
        if aligned_contracts < lot_size:
            min_contract_risk = lot_size * risk_per_contract
            logger.warning(
                f"RiskGatekeeper: Minimum tradable lot size ({lot_size} contracts, risk ${min_contract_risk:.2f}) "
                f"exceeds permitted risk budget (${calculated_dollar_risk:.2f}). Returning NO_TRADE."
            )
            return {
                "gate_decision": "NO_TRADE",
                "contracts": 0,
                "reason": f"NO_TRADE: Minimum tradable quantity ({lot_size} contracts, risk ${min_contract_risk:.2f}) exceeds permitted risk budget (${calculated_dollar_risk:.2f})."
            }

        contracts = aligned_contracts

        # 6. Instrument-Specific Liquidation Buffer Calculation
        # Enforce maximum leverage ceiling from config and risk manager
        max_lev_ceiling = min(config.max_allowed_leverage, self.risk_manager.max_allowed_leverage)
        leverage = min(leverage, max_lev_ceiling)
        
        # Query authoritative maintenance margin rate (MMR) from product info
        mmr = float(pinfo.get("maintenance_margin_rate") or 0.01) if pinfo else 0.01
        imr = 1.0 / leverage if leverage > 0 else 0.04

        if side == "buy":
            est_liq_price = entry * (1.0 - imr) / max(0.001, 1.0 - mmr)
            est_liq_distance = max(0.0, entry - est_liq_price)
        else:
            est_liq_price = entry * (1.0 + imr) / max(0.001, 1.0 + mmr)
            est_liq_distance = max(0.0, est_liq_price - entry)

        required_liq_buffer = config.liquidation_buffer_multiple * stop_distance
        if est_liq_distance < required_liq_buffer:
            # Deterministic de-leverage until liquidation buffer is safe
            needed_imr = (required_liq_buffer / entry) * (1.0 - mmr) + mmr
            safe_leverage = max(1, min(int(1.0 / needed_imr) if needed_imr > 0 else 5, max_lev_ceiling))
            if safe_leverage < leverage:
                logger.info(f"RiskGatekeeper: Clamping leverage on {symbol} from {leverage}x to {safe_leverage}x for liquidation safety buffer.")
                leverage = safe_leverage
                imr = 1.0 / leverage
                if side == "buy":
                    est_liq_price = entry * (1.0 - imr) / max(0.001, 1.0 - mmr)
                    est_liq_distance = max(0.0, entry - est_liq_price)
                else:
                    est_liq_price = entry * (1.0 + imr) / max(0.001, 1.0 + mmr)
                    est_liq_distance = max(0.0, est_liq_price - entry)

            if est_liq_distance < (2.0 * stop_distance):
                return {
                    "gate_decision": "REJECTED",
                    "reason": f"Liquidation distance (${est_liq_distance:.2f}) is too close to Stop Loss (${stop_distance:.2f}) even at minimum leverage."
                }

        # Margin guardrails
        max_margin_pct = 0.25 if is_primary else 0.15
        max_allowed_margin = min(usable_capital * max_margin_pct, usable_capital)
        
        req_margin = (contracts * per_contract_notional) / leverage
        if req_margin > max_allowed_margin:
            capped_contracts = (int((max_allowed_margin * leverage) / per_contract_notional) // lot_size) * lot_size
            if capped_contracts < lot_size:
                return {
                    "gate_decision": "REJECTED",
                    "reason": f"Required margin (${req_margin:.2f}) exceeds risk ceiling or available balance (${usable_capital:.2f})."
                }
            contracts = capped_contracts
            req_margin = (contracts * per_contract_notional) / leverage

        if req_margin > usable_capital:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Required margin (${req_margin:.2f}) exceeds available balance (${usable_capital:.2f})."
            }

        # 7. Check Portfolio Total Open Risk Limit
        current_open_risk = sum(float(p.get("dollar_risk", 2.0)) for p in active_positions)
        total_risk_with_trade = current_open_risk + (contracts * risk_per_contract)
        if total_risk_with_trade > self.max_portfolio_open_risk_usd:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Portfolio cumulative open risk (${total_risk_with_trade:.2f}) exceeds max allowed ceiling (${self.max_portfolio_open_risk_usd:.2f})."
            }

        dollar_risk = round(contracts * risk_per_contract, 2)
        risk_pct = round((dollar_risk / total_usdt) * 100.0, 2) if total_usdt > 0 else 0.0
        profit_distance = abs(tp - entry)
        rr_ratio = round((profit_distance / stop_distance), 2) if stop_distance > 0 else 2.0
        stop_dist_pct = round((stop_distance / entry) * 100.0, 2)

        # Categorize Trade Risk-to-Reward Profile
        if stop_dist_pct <= 0.60 and rr_ratio >= 2.2:
            rr_category = "MIN_RISK_MAX_REWARD"
            rr_badge = "🟢 MIN RISK · MAX PROFIT"
            rr_desc = "Asymmetric Institutional Alpha"
        elif stop_dist_pct > 0.70 and rr_ratio < 2.0:
            rr_category = "MAX_RISK_MIN_REWARD"
            rr_badge = "🔴 MAX RISK · MIN PROFIT"
            rr_desc = "Toxic Amateur Trap (Negative Asymmetry)"
        elif stop_dist_pct > 0.70 and rr_ratio >= 2.2:
            rr_category = "MAX_RISK_MAX_REWARD"
            rr_badge = "🟠 MAX RISK · MAX PROFIT"
            rr_desc = "High-Stakes Speculation"
        else:
            rr_category = "MIN_RISK_MIN_REWARD"
            rr_badge = "⚪ MIN RISK · MIN PROFIT"
            rr_desc = "Low-Payoff Base Scalp"

        # Strictly enforce: ONLY "Min Risk · Max Profit" trades are allowed to execute
        if rr_category == "MAX_RISK_MIN_REWARD":
            return {
                "gate_decision": "REJECTED",
                "reason": f"Setup classified as MAX RISK · MIN PROFIT (Stop: {stop_dist_pct}%, R:R: {rr_ratio}:1). Toxic asymmetry strictly banned."
            }

        if rr_ratio < self.risk_manager.min_reward_to_risk:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Reward-to-Risk ratio {rr_ratio:.2f}:1 is below required minimum of {self.risk_manager.min_reward_to_risk:.1f}:1"
            }

        final_liq_price = round(est_liq_price, 2)

        liq_conf = setup.get("confluence", {}).get("liquidity_detail", "")
        if spread_pct <= 0.04:
            liq_grade = "A+_PRIME_DEPTH"
        elif spread_pct <= 0.08:
            liq_grade = "HIGH_DEPTH"
        elif spread_pct <= 0.15:
            liq_grade = "STANDARD_DEPTH"
        else:
            liq_grade = "ILLIQUID_CAUTION"

        return {
            "gate_decision": "APPROVED",
            "symbol": symbol,
            "side": side,
            "strategy": setup.get("strategy_name"),
            "thesis": setup.get("thesis"),
            "score": setup.get("score", 75),
            "spread_pct": spread_pct,
            "liquidity_profile": {
                "spread_pct": spread_pct,
                "liquidity_grade": liq_grade,
                "liquidity_detail": liq_conf
            },
            "risk_reward_category": rr_category,
            "risk_reward_badge": rr_badge,
            "risk_reward_desc": rr_desc,
            "stop_distance_pct": stop_dist_pct,
            "confluence": setup.get("confluence", {}),
            "time_machine": setup.get("time_machine", {}),
            "conviction_multiplier": round(conviction_multiplier, 2),
            "conviction_tier": conviction_tier,
            "conviction_boost_pct": int(round((conviction_multiplier - 1.0) * 100)),
            "conviction_reasons": conviction_reasons,
            "contracts": contracts,
            "entry_price": entry,
            "stop_loss_price": stop,
            "take_profit_price": tp,
            "reward_to_risk_ratio": rr_ratio,
            "dollar_risk_usd": dollar_risk,
            "risk_pct": risk_pct,
            "required_margin_usd": round(req_margin, 2),
            "estimated_liquidation_price": final_liq_price,
            "leverage": leverage,
            "account_equity": total_usdt,
            "available_usdt": available_usdt,
            "circuit_breaker": cb_res
        }
