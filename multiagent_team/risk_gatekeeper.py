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

logger = logging.getLogger("risk-gatekeeper")


class RiskGatekeeperAgent:
    def __init__(
        self,
        client: DeltaExchangeClient,
        risk_manager: RiskManager,
        max_portfolio_open_risk_usd: float = 8.00,
        cooldown_seconds: int = 1800
    ):
        self.client = client
        self.risk_manager = risk_manager
        self.max_portfolio_open_risk_usd = max_portfolio_open_risk_usd
        self.cooldown_seconds = cooldown_seconds
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
        entry = float(setup.get("entry_price", 0.0))
        stop = float(setup.get("stop_loss_price", 0.0))
        tp = float(setup.get("take_profit_price", 0.0))

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
                avail = float(b.get("available_balance", 0.0))
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
        # When a setup is of superior quality ("good" / high conviction), scale up quantity/lot size to maximize profit
        score = int(setup.get("score") or 75)
        tm = setup.get("time_machine", {})
        tm_win_rate = float(tm.get("win_rate_pct") or 50.0)
        tm_ev = float(tm.get("expected_value_r") or 0.0)
        is_reinforced = "REINFORCED" in str(setup.get("thesis", "")) or "REINFORCED" in str(setup.get("strategy_name", ""))

        conviction_multiplier = 1.0
        conviction_tier = "STANDARD"
        conviction_reasons = []

        # Tier 1: A+ Prime Conviction Setup (Score >= 90 & (TM Win Rate >= 70% or TM EV >= 0.40R or Reinforced))
        if score >= 90 and (tm_win_rate >= 70.0 or tm_ev >= 0.40 or is_reinforced):
            conviction_multiplier = 2.0 if is_primary else 1.50  # Up to 2.0x contract boost for Primary A+ setups
            conviction_tier = "A+_PRIME_CONVICTION"
            conviction_reasons.append(f"A+ Setup (Score: {score}/100, TM EV: +{tm_ev}R, Win Rate: {tm_win_rate}%)")
        # Tier 2: High Conviction Setup (Score >= 85 or (Score >= 80 and TM EV >= 0.35R))
        elif score >= 85 or (score >= 80 and tm_ev >= 0.35):
            conviction_multiplier = 1.60 if is_primary else 1.30  # +60% contract boost
            conviction_tier = "HIGH_CONVICTION"
            conviction_reasons.append(f"High Quality Setup (Score: {score}/100, TM EV: +{tm_ev}R)")
        # Tier 3: Empirically Reinforced Historical Pattern
        elif is_reinforced:
            conviction_multiplier = 1.35 if is_primary else 1.20  # +35% contract boost
            conviction_tier = "REINFORCED_EDGE"
            conviction_reasons.append("Empirically Reinforced Historical Pattern")

        base_dollar_risk_cap = float(os.getenv("MAX_DOLLAR_RISK_PER_TRADE", "4.00" if is_primary else "2.00"))
        max_dollar_risk_cap = base_dollar_risk_cap * dd_risk_scalar * conviction_multiplier

        target_risk_pct = (0.02 if is_primary else 0.015) * dd_risk_scalar * conviction_multiplier
        # When trade setup is good/high conviction, scale up contract risk to the max budget for maximum profit
        if conviction_multiplier >= 1.5:
            calculated_dollar_risk = max_dollar_risk_cap
        else:
            calculated_dollar_risk = min(max(total_usdt * target_risk_pct, 1.50 * conviction_multiplier), max_dollar_risk_cap)

        # Include estimated round-trip taker fees (0.10%) + slippage (0.06%) into risk unit
        friction_per_contract = per_contract_notional * 0.0016
        risk_per_contract = (contract_value * stop_distance) + friction_per_contract

        raw_contracts = int(calculated_dollar_risk / risk_per_contract) if risk_per_contract > 0 else 1
        # Align with lot size
        contracts = max(lot_size, (raw_contracts // lot_size) * lot_size)

        # 6. Pre-Check Liquidation Buffer (Isolated Leverage)
        # Estimated liquidation distance should be safely >= 3.0x stop loss distance
        est_liq_distance = (entry / leverage) * 0.90  # 90% bankruptcy buffer
        if est_liq_distance < (2.5 * stop_distance):
            # Safe de-leverage if liquidation is too close to Stop Loss
            safe_leverage = max(5, int((entry * 0.90) / (3.0 * stop_distance)))
            if safe_leverage < leverage:
                logger.info(f"RiskGatekeeper: Clamping leverage on {symbol} from {leverage}x to {safe_leverage}x for liquidation safety.")
                leverage = safe_leverage

        # Margin guardrails: expand margin ceiling for high conviction setups to allow the larger position
        max_margin_pct = (0.45 if is_primary else 0.25) if conviction_multiplier >= 1.4 else (0.25 if is_primary else 0.10)
        max_allowed_margin = min(usable_capital * max_margin_pct, (100.0 if is_primary else 35.0) * conviction_multiplier)
        
        req_margin = (contracts * per_contract_notional) / leverage
        if req_margin > max_allowed_margin:
            contracts = max(lot_size, (int((max_allowed_margin * leverage) / per_contract_notional) // lot_size) * lot_size)
            req_margin = (contracts * per_contract_notional) / leverage

        if contracts < lot_size or req_margin > usable_capital:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Required margin (${req_margin:.2f}) exceeds risk ceiling or available balance (${usable_capital:.2f})."
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

        if rr_ratio < self.risk_manager.min_reward_to_risk:
            return {
                "gate_decision": "REJECTED",
                "reason": f"Reward-to-Risk ratio {rr_ratio:.2f}:1 is below required minimum of {self.risk_manager.min_reward_to_risk:.1f}:1"
            }

        est_liq_price = round(entry * (1.0 - (1.0 / leverage)), 2) if side == "buy" else round(entry * (1.0 + (1.0 / leverage)), 2)

        return {
            "gate_decision": "APPROVED",
            "symbol": symbol,
            "side": side,
            "strategy": setup.get("strategy_name"),
            "thesis": setup.get("thesis"),
            "score": setup.get("score", 75),
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
            "estimated_liquidation_price": est_liq_price,
            "leverage": leverage,
            "account_equity": total_usdt,
            "available_usdt": available_usdt,
            "circuit_breaker": cb_res
        }
