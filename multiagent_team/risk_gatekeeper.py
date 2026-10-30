"""
Agent 3: Risk & Discipline Gatekeeper (Pre-Trade Discipline Gate).
Inspired by drawdown-circuit-breaker and pre-trade-discipline-gate from claude-trading-skills.
Enforces non-negotiable risk limits, capital allocation, and circuit breakers.
"""

from typing import Dict, Any, Optional
import logging
from src.risk_manager import RiskManager
from src.delta_client import DeltaExchangeClient

logger = logging.getLogger("risk-gatekeeper")


class RiskGatekeeperAgent:
    def __init__(self, client: DeltaExchangeClient, risk_manager: RiskManager):
        self.client = client
        self.risk_manager = risk_manager

    def evaluate_candidate(
        self,
        setup: Dict[str, Any],
        leverage: int = 5,
        risk_pct_override: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Run setup through the mandatory Pre-Trade Discipline Gate.
        """
        symbol = setup.get("symbol")
        entry = setup.get("entry_price", 0.0)
        stop = setup.get("stop_loss_price", 0.0)
        tp = setup.get("take_profit_price", 0.0)

        # 1. Fetch live account balances and open positions
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

        # 2. Check open positions count
        pos_res = self.client.get_positions()
        raw_positions = pos_res.get("result", []) if pos_res.get("success") else []
        active_positions = [p for p in raw_positions if float(p.get("size", 0)) != 0]

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

        # 4. Check if already positioned in this symbol
        for p in active_positions:
            if p.get("product_symbol") == symbol:
                return {
                    "gate_decision": "REJECTED",
                    "reason": f"Active position already exists for symbol {symbol}."
                }

        # 5. Discover product specs for exact contract multiplier
        pinfo = self.client.get_product_info(symbol)
        contract_value = float(pinfo.get("contract_value", "0.001")) if pinfo else 0.001

        # 6. Compute strict position sizing and R:R validation
        sizing = self.risk_manager.calculate_position_size(
            account_equity=total_usdt,
            entry_price=entry,
            stop_loss_price=stop,
            take_profit_price=tp,
            contract_value=contract_value,
            leverage=leverage,
            risk_pct_override=risk_pct_override
        )

        if sizing.get("gate_status") != "APPROVED":
            return {
                "gate_decision": "REJECTED",
                "reason": "; ".join(sizing.get("rejection_reasons", ["Sizing gate criteria not met"])),
                "sizing_details": sizing
            }

        # Passed all gates
        return {
            "gate_decision": "APPROVED",
            "symbol": symbol,
            "side": setup.get("side"),
            "strategy": setup.get("strategy_name"),
            "thesis": setup.get("thesis"),
            "contracts": sizing["contracts"],
            "entry_price": entry,
            "stop_loss_price": stop,
            "take_profit_price": tp,
            "reward_to_risk_ratio": sizing["reward_to_risk_ratio"],
            "dollar_risk_usd": sizing["actual_dollar_risk"],
            "risk_pct": sizing["actual_risk_pct"],
            "required_margin_usd": sizing["required_margin_usd"],
            "leverage": sizing["leverage"],
            "account_equity": total_usdt,
            "available_usdt": available_usdt,
            "circuit_breaker": cb_res
        }
