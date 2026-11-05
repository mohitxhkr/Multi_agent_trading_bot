"""
Risk Management & Circuit Breaker Engine for Delta Exchange Trading.
Inspired by drawdown-circuit-breaker, position-sizer, and pre-trade-discipline-gate
from claude-trading-skills.
"""

from typing import Dict, Any, Optional
import json
import os
import time

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
CIRCUIT_BREAKER_STATE_FILE = os.path.join(STATE_DIR, "circuit_breaker_state.json")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def load_circuit_breaker_state() -> Dict[str, Any]:
    ensure_state_dir()
    if os.path.exists(CIRCUIT_BREAKER_STATE_FILE):
        try:
            with open(CIRCUIT_BREAKER_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "date": time.strftime("%Y-%m-%d"),
        "starting_equity": 0.0,
        "peak_equity": 0.0,
        "halted": False,
        "halt_reason": ""
    }


def save_circuit_breaker_state(state: Dict[str, Any]):
    ensure_state_dir()
    with open(CIRCUIT_BREAKER_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


class RiskManager:
    def __init__(
        self,
        max_risk_per_trade_pct: float = 0.01,       # 1% per trade
        max_concurrent_positions: int = 3,          # max 3 simultaneous positions
        max_daily_drawdown_pct: float = 0.05,       # 5% max daily drawdown
        max_allowed_leverage: int = 10,             # 10x max leverage ceiling
        min_reward_to_risk: float = 2.2             # 2.2:1 strict minimum R:R for asymmetric profit vs risk
    ):
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_concurrent_positions = max_concurrent_positions
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.max_allowed_leverage = max_allowed_leverage
        self.min_reward_to_risk = min_reward_to_risk

    def check_circuit_breaker(
        self,
        current_equity: float,
        open_positions_count: int = 0
    ) -> Dict[str, Any]:
        """
        Evaluate account drawdown and decide if new trades are permitted.
        Status values:
          - TRADING_ALLOWED
          - CAUTION_EXPOSURE_HIGH
          - HALT_CIRCUIT_BREAKER
        """
        today = time.strftime("%Y-%m-%d")
        state = load_circuit_breaker_state()

        # Reset daily starting equity if new day
        if state.get("date") != today or state.get("starting_equity", 0.0) <= 0.0:
            state["date"] = today
            state["starting_equity"] = current_equity
            state["peak_equity"] = max(current_equity, state.get("peak_equity", current_equity))
            state["halted"] = False
            state["halt_reason"] = ""

        # Update peak equity
        if current_equity > state.get("peak_equity", 0.0):
            state["peak_equity"] = current_equity

        starting_equity = state["starting_equity"]
        peak_equity = state["peak_equity"]

        daily_drawdown_pct = 0.0
        if starting_equity > 0:
            daily_drawdown_pct = (starting_equity - current_equity) / starting_equity

        peak_drawdown_pct = 0.0
        if peak_equity > 0:
            peak_drawdown_pct = (peak_equity - current_equity) / peak_equity

        # Evaluate rules
        if daily_drawdown_pct >= self.max_daily_drawdown_pct:
            state["halted"] = True
            state["halt_reason"] = (
                f"Daily drawdown of {daily_drawdown_pct * 100:.2f}% breached maximum allowed "
                f"threshold of {self.max_daily_drawdown_pct * 100:.1f}%."
            )
            save_circuit_breaker_state(state)
            return {
                "decision": "HALT_CIRCUIT_BREAKER",
                "can_trade": False,
                "reason": state["halt_reason"],
                "daily_drawdown_pct": round(daily_drawdown_pct * 100, 2),
                "peak_drawdown_pct": round(peak_drawdown_pct * 100, 2),
                "current_equity": current_equity,
                "open_positions": open_positions_count
            }

        if open_positions_count >= self.max_concurrent_positions:
            return {
                "decision": "MAX_CONCURRENT_POSITIONS_REACHED",
                "can_trade": False,
                "reason": f"Active positions count ({open_positions_count}) has reached the maximum allowed limit ({self.max_concurrent_positions}).",
                "daily_drawdown_pct": round(daily_drawdown_pct * 100, 2),
                "peak_drawdown_pct": round(peak_drawdown_pct * 100, 2),
                "current_equity": current_equity,
                "open_positions": open_positions_count
            }

        # Consecutive Loss Cooling-Off Gate (Anti-Churn / Anti-Tilt Safeguard)
        try:
            from src.journal import load_journal
            j = load_journal()
            closed_trades = [t for t in j.get("trades", []) if t.get("status") == "CLOSED"]
            if len(closed_trades) >= 2:
                last_two = closed_trades[-2:]
                both_losses = all((float(t.get("realized_pnl_usd") or 0.0) < -0.05) for t in last_two)
                if both_losses:
                    last_exit_str = last_two[-1].get("exit_time", "")
                    if last_exit_str:
                        import datetime
                        t_clean = last_exit_str.replace(" UTC", "")
                        exit_dt = datetime.datetime.strptime(t_clean, "%Y-%m-%d %H:%M:%S")
                        now_dt = datetime.datetime.utcnow()
                        diff_sec = (now_dt - exit_dt).total_seconds()
                        cooling_period_sec = 7200  # 2 hours cooling-off
                        if 0 <= diff_sec < cooling_period_sec:
                            remaining_min = int((cooling_period_sec - diff_sec) / 60)
                            return {
                                "decision": "HALT_COOLING_OFF",
                                "can_trade": False,
                                "reason": f"Cooling-Off Circuit Breaker: 2 consecutive losses hit recently. Paused for {remaining_min} more minutes to protect capital during abnormal volatility shock.",
                                "daily_drawdown_pct": round(daily_drawdown_pct * 100, 2),
                                "peak_drawdown_pct": round(peak_drawdown_pct * 100, 2),
                                "current_equity": current_equity,
                                "open_positions": open_positions_count
                            }
        except Exception:
            pass

        save_circuit_breaker_state(state)
        return {
            "decision": "TRADING_ALLOWED",
            "can_trade": True,
            "reason": "Account health verified within risk tolerances.",
            "daily_drawdown_pct": round(daily_drawdown_pct * 100, 2),
            "peak_drawdown_pct": round(peak_drawdown_pct * 100, 2),
            "current_equity": current_equity,
            "open_positions": open_positions_count,
            "max_concurrent_positions": self.max_concurrent_positions
        }

    def calculate_position_size(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        contract_value: float = 0.001,      # Delta contract multiplier (e.g. 0.001 BTC per contract)
        leverage: int = 5,
        risk_pct_override: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate disciplined contract sizing strictly based on maximum risk tolerance.
        """
        if entry_price <= 0 or stop_loss_price <= 0:
            return {"error": "Entry and Stop Loss prices must be greater than zero"}

        risk_pct = risk_pct_override if risk_pct_override is not None else self.max_risk_per_trade_pct
        max_dollar_risk = account_equity * risk_pct

        is_long = entry_price > stop_loss_price
        stop_distance = abs(entry_price - stop_loss_price)
        stop_distance_pct = (stop_distance / entry_price) * 100.0

        if stop_distance <= 0:
            return {"error": "Stop loss price cannot equal entry price"}

        # Calculate Reward to Risk
        profit_distance = abs(take_profit_price - entry_price)
        reward_to_risk = profit_distance / stop_distance if stop_distance > 0 else 0.0

        # Sizing formula:
        # Risk per 1 contract = stop_distance * contract_value
        # Contracts = max_dollar_risk / (stop_distance * contract_value)
        risk_per_contract = stop_distance * contract_value
        if risk_per_contract <= 0:
            return {"error": "Invalid risk per contract calculated"}

        contracts_exact = max_dollar_risk / risk_per_contract
        contracts_int = int(contracts_exact)  # Delta requires integer contract quantities

        if contracts_int < 1:
            contracts_int = 1  # Minimum 1 contract

        # Notional and Margin
        notional_value = contracts_int * contract_value * entry_price
        actual_dollar_risk = contracts_int * risk_per_contract
        actual_risk_pct = (actual_dollar_risk / account_equity) * 100.0 if account_equity > 0 else 0.0

        clamped_leverage = min(leverage, self.max_allowed_leverage)
        required_margin = notional_value / clamped_leverage if clamped_leverage > 0 else notional_value

        # Discipline gate validation
        rr_passed = reward_to_risk >= self.min_reward_to_risk
        margin_passed = required_margin <= (account_equity * 0.95)  # Leave 5% buffer

        gate_status = "APPROVED" if (rr_passed and margin_passed) else "REJECTED"
        rejection_reasons = []
        if not rr_passed:
            rejection_reasons.append(
                f"Reward-to-Risk ratio {reward_to_risk:.2f}:1 is below required minimum of {self.min_reward_to_risk:.1f}:1"
            )
        if not margin_passed:
            rejection_reasons.append(
                f"Required margin (${required_margin:.2f}) exceeds available equity (${account_equity:.2f})"
            )

        return {
            "gate_status": gate_status,
            "contracts": contracts_int,
            "side": "buy" if is_long else "sell",
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "stop_distance_pct": round(stop_distance_pct, 2),
            "reward_to_risk_ratio": round(reward_to_risk, 2),
            "max_dollar_risk": round(max_dollar_risk, 2),
            "actual_dollar_risk": round(actual_dollar_risk, 2),
            "actual_risk_pct": round(actual_risk_pct, 2),
            "notional_value_usd": round(notional_value, 2),
            "required_margin_usd": round(required_margin, 2),
            "leverage": clamped_leverage,
            "contract_value": contract_value,
            "rejection_reasons": rejection_reasons
        }
