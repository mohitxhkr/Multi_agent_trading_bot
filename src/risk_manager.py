"""
Risk Management & Persistent Circuit Breaker Engine for Delta Exchange Trading.
Implements multi-horizon drawdown protection (daily, weekly, monthly), consecutive loss cooldowns,
fail-closed state management, and strict deterministic position sizing.
"""

from typing import Dict, Any, Optional
import json
import os
import time
import datetime
from src.config import system_config

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
CIRCUIT_BREAKER_STATE_FILE = os.path.join(STATE_DIR, "circuit_breaker_state.json")
AUDIT_LOG_FILE = os.path.join(STATE_DIR, "circuit_breaker_audit.jsonl")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def _get_current_timestamps():
    now = datetime.datetime.utcnow()
    day_str = now.strftime("%Y-%m-%d")
    # ISO calendar week: YYYY-Www
    week_str = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
    month_str = now.strftime("%Y-%m")
    iso_now = now.isoformat() + "Z"
    return day_str, week_str, month_str, iso_now


def load_circuit_breaker_state() -> Dict[str, Any]:
    """
    Load circuit breaker state with strict fail-closed guarantees.
    If the state file exists but is corrupted, or if an unhandled I/O error occurs,
    fails closed by returning a HALTED state to protect live capital.
    """
    ensure_state_dir()
    day_str, week_str, month_str, iso_now = _get_current_timestamps()

    if os.path.exists(CIRCUIT_BREAKER_STATE_FILE):
        try:
            with open(CIRCUIT_BREAKER_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                if not isinstance(state, dict):
                    raise ValueError("Circuit breaker state file contains invalid JSON structure (non-dict)")
                return state
        except Exception as e:
            # FAIL-CLOSED: if corrupted or unreadable, halt trading immediately
            return {
                "state": "HALTED",
                "halted": True,
                "halt_reason": f"FAIL_CLOSED: State file read error ({str(e)}). Manual inspection required.",
                "halt_timestamp": iso_now,
                "day": day_str,
                "week": week_str,
                "month": month_str,
                "daily_starting_equity": 0.0,
                "weekly_starting_equity": 0.0,
                "monthly_starting_equity": 0.0,
                "peak_equity": 0.0,
                "consecutive_losses": 0,
                "cooldown_until": 0.0
            }

    # Brand new clean state file
    return {
        "state": "TRADING_ALLOWED",
        "halted": False,
        "halt_reason": "",
        "halt_timestamp": None,
        "day": day_str,
        "week": week_str,
        "month": month_str,
        "daily_starting_equity": 0.0,
        "weekly_starting_equity": 0.0,
        "monthly_starting_equity": 0.0,
        "peak_equity": 0.0,
        "consecutive_losses": 0,
        "cooldown_until": 0.0
    }


def save_circuit_breaker_state(state: Dict[str, Any]):
    """Safely persist state using atomic write semantics."""
    ensure_state_dir()
    temp_file = CIRCUIT_BREAKER_STATE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(temp_file, CIRCUIT_BREAKER_STATE_FILE)


class RiskManager:
    def __init__(
        self,
        max_risk_per_trade_pct: Optional[float] = None,
        max_dollar_risk_per_trade: Optional[float] = None,
        max_concurrent_positions: Optional[int] = None,
        max_daily_drawdown_pct: Optional[float] = None,
        max_weekly_drawdown_pct: Optional[float] = None,
        max_monthly_drawdown_pct: Optional[float] = None,
        max_consecutive_losses: Optional[int] = None,
        cooldown_seconds: Optional[int] = None,
        max_allowed_leverage: Optional[int] = None,
        min_reward_to_risk: Optional[float] = None
    ):
        self.max_risk_per_trade_pct = max_risk_per_trade_pct if max_risk_per_trade_pct is not None else system_config.max_risk_per_trade_pct
        self.max_dollar_risk_per_trade = max_dollar_risk_per_trade if max_dollar_risk_per_trade is not None else system_config.max_dollar_risk_per_trade
        self.max_concurrent_positions = max_concurrent_positions if max_concurrent_positions is not None else system_config.max_portfolio_concurrency
        self.max_daily_drawdown_pct = max_daily_drawdown_pct if max_daily_drawdown_pct is not None else system_config.max_daily_drawdown_pct
        self.max_weekly_drawdown_pct = max_weekly_drawdown_pct if max_weekly_drawdown_pct is not None else system_config.max_weekly_drawdown_pct
        self.max_monthly_drawdown_pct = max_monthly_drawdown_pct if max_monthly_drawdown_pct is not None else system_config.max_monthly_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses if max_consecutive_losses is not None else system_config.max_consecutive_losses
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else system_config.cooldown_seconds
        self.max_allowed_leverage = max_allowed_leverage if max_allowed_leverage is not None else system_config.max_allowed_leverage
        self.min_reward_to_risk = min_reward_to_risk if min_reward_to_risk is not None else system_config.min_reward_to_risk

        self._last_checked_equity: float = 0.0
        self._daily_pnl: float = 0.0
        self._weekly_pnl: float = 0.0
        self._consecutive_losses: int = 0

    @property
    def daily_pnl(self) -> float:
        """Daily PnL based on starting equity vs current checked equity."""
        state = load_circuit_breaker_state()
        daily_start = float(state.get("daily_starting_equity", 0.0) or 0.0)
        cur = self._last_checked_equity if self._last_checked_equity > 0 else daily_start
        return round(float(cur - daily_start), 2) if daily_start > 0 else 0.0

    @property
    def weekly_pnl(self) -> float:
        """Weekly PnL based on starting equity vs current checked equity."""
        state = load_circuit_breaker_state()
        weekly_start = float(state.get("weekly_starting_equity", 0.0) or 0.0)
        cur = self._last_checked_equity if self._last_checked_equity > 0 else weekly_start
        return round(float(cur - weekly_start), 2) if weekly_start > 0 else 0.0

    @property
    def consecutive_losses(self) -> int:
        state = load_circuit_breaker_state()
        return int(state.get("consecutive_losses", 0))

    @property
    def start_of_day_equity(self) -> float:
        state = load_circuit_breaker_state()
        return float(state.get("daily_starting_equity", 0.0) or 0.0)

    @property
    def start_of_week_equity(self) -> float:
        state = load_circuit_breaker_state()
        return float(state.get("weekly_starting_equity", 0.0) or 0.0)

    def manual_reset(self, authorized_by: str, reason: str, current_equity: float) -> Dict[str, Any]:
        """
        Explicit administrative reset of circuit breaker halt/emergency state.
        Never resets automatically on day roll or process restart.
        """
        day_str, week_str, month_str, iso_now = _get_current_timestamps()
        state = {
            "state": "TRADING_ALLOWED",
            "halted": False,
            "halt_reason": "",
            "halt_timestamp": None,
            "day": day_str,
            "week": week_str,
            "month": month_str,
            "daily_starting_equity": current_equity,
            "weekly_starting_equity": current_equity,
            "monthly_starting_equity": current_equity,
            "peak_equity": current_equity,
            "consecutive_losses": 0,
            "cooldown_until": 0.0,
            "last_reset_by": authorized_by,
            "last_reset_reason": reason,
            "last_reset_timestamp": iso_now
        }
        save_circuit_breaker_state(state)

        # Log audit entry
        ensure_state_dir()
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "action": "MANUAL_CIRCUIT_BREAKER_RESET",
                "authorized_by": authorized_by,
                "reason": reason,
                "equity": current_equity,
                "timestamp": iso_now
            }) + "\n")

        return {"status": "SUCCESS", "message": f"Circuit breaker reset by {authorized_by}.", "state": state}

    def record_trade_outcome(self, realized_pnl_usd: float):
        """Update consecutive loss counter and cooldown timestamp."""
        state = load_circuit_breaker_state()
        now_ts = time.time()
        _, _, _, iso_now = _get_current_timestamps()

        if realized_pnl_usd < -0.01:
            losses = state.get("consecutive_losses", 0) + 1
            state["consecutive_losses"] = losses
            if losses >= self.max_consecutive_losses:
                state["cooldown_until"] = now_ts + self.cooldown_seconds
                if state.get("state") not in ["HALTED", "EMERGENCY"]:
                    state["state"] = "COOLDOWN"
                    state["halt_reason"] = f"Cooldown triggered: {losses} consecutive losses. Cooldown for {self.cooldown_seconds // 60}m."
                    state["halt_timestamp"] = iso_now
        else:
            state["consecutive_losses"] = 0
            if state.get("state") == "COOLDOWN" and now_ts >= state.get("cooldown_until", 0.0):
                state["state"] = "TRADING_ALLOWED"
                state["halt_reason"] = ""

        save_circuit_breaker_state(state)

    def check_circuit_breaker(
        self,
        current_equity: float,
        open_positions_count: int = 0
    ) -> Dict[str, Any]:
        """
        Evaluate multi-horizon drawdown and system state with strict persistence.
        States:
          - TRADING_ALLOWED
          - COOLDOWN
          - HALTED
          - EMERGENCY
        """
        day_str, week_str, month_str, iso_now = _get_current_timestamps()
        state = load_circuit_breaker_state()
        now_ts = time.time()

        # Check existing persistent halt or emergency
        current_system_state = state.get("state", "TRADING_ALLOWED")
        is_halted = state.get("halted", False) or current_system_state in ["HALTED", "EMERGENCY"]

        # If already halted or emergency, DO NOT auto-resume even if day or week changed!
        if is_halted:
            return {
                "decision": "HALT_CIRCUIT_BREAKER",
                "state": current_system_state if current_system_state in ["HALTED", "EMERGENCY"] else "HALTED",
                "can_trade": False,
                "reason": state.get("halt_reason", "Persistent circuit breaker halt active. Manual reset required."),
                "halt_timestamp": state.get("halt_timestamp"),
                "current_equity": current_equity,
                "open_positions": open_positions_count
            }

        # Handle chronological baseline resets (ONLY if NOT halted)
        if state.get("day") != day_str or state.get("daily_starting_equity", 0.0) <= 0.0:
            state["day"] = day_str
            state["daily_starting_equity"] = current_equity

        if state.get("week") != week_str or state.get("weekly_starting_equity", 0.0) <= 0.0:
            state["week"] = week_str
            state["weekly_starting_equity"] = current_equity

        if state.get("month") != month_str or state.get("monthly_starting_equity", 0.0) <= 0.0:
            state["month"] = month_str
            state["monthly_starting_equity"] = current_equity

        # Track historical equity peak
        if current_equity > state.get("peak_equity", 0.0):
            state["peak_equity"] = current_equity

        daily_start = state.get("daily_starting_equity", current_equity)
        weekly_start = state.get("weekly_starting_equity", current_equity)
        monthly_start = state.get("monthly_starting_equity", current_equity)
        peak_equity = state.get("peak_equity", current_equity)

        self._last_checked_equity = float(current_equity)
        self._daily_pnl = round(float(current_equity - daily_start), 2)
        self._weekly_pnl = round(float(current_equity - weekly_start), 2)
        self._consecutive_losses = int(state.get("consecutive_losses", 0))

        # Calculate drawdowns
        daily_dd_pct = (daily_start - current_equity) / daily_start if daily_start > 0 else 0.0
        weekly_dd_pct = (weekly_start - current_equity) / weekly_start if weekly_start > 0 else 0.0
        monthly_dd_pct = (monthly_start - current_equity) / monthly_start if monthly_start > 0 else 0.0
        peak_dd_pct = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0.0

        # 1. Monthly Emergency Drawdown Breach (Hardest stop)
        if monthly_dd_pct >= self.max_monthly_drawdown_pct:
            state["state"] = "EMERGENCY"
            state["halted"] = True
            state["halt_reason"] = (
                f"EMERGENCY: Monthly drawdown {monthly_dd_pct * 100:.2f}% breached maximum allowed "
                f"limit of {self.max_monthly_drawdown_pct * 100:.1f}%."
            )
            state["halt_timestamp"] = iso_now
            save_circuit_breaker_state(state)
            return {
                "decision": "HALT_CIRCUIT_BREAKER",
                "state": "EMERGENCY",
                "can_trade": False,
                "reason": state["halt_reason"],
                "daily_drawdown_pct": round(daily_dd_pct * 100, 2),
                "weekly_drawdown_pct": round(weekly_dd_pct * 100, 2),
                "monthly_drawdown_pct": round(monthly_dd_pct * 100, 2),
                "peak_drawdown_pct": round(peak_dd_pct * 100, 2),
                "current_equity": current_equity
            }

        # 2. Weekly Drawdown Breach
        if weekly_dd_pct >= self.max_weekly_drawdown_pct:
            state["state"] = "HALTED"
            state["halted"] = True
            state["halt_reason"] = (
                f"HALTED: Weekly drawdown {weekly_dd_pct * 100:.2f}% breached maximum allowed "
                f"limit of {self.max_weekly_drawdown_pct * 100:.1f}%."
            )
            state["halt_timestamp"] = iso_now
            save_circuit_breaker_state(state)
            return {
                "decision": "HALT_CIRCUIT_BREAKER",
                "state": "HALTED",
                "can_trade": False,
                "reason": state["halt_reason"],
                "daily_drawdown_pct": round(daily_dd_pct * 100, 2),
                "weekly_drawdown_pct": round(weekly_dd_pct * 100, 2),
                "monthly_drawdown_pct": round(monthly_dd_pct * 100, 2),
                "peak_drawdown_pct": round(peak_dd_pct * 100, 2),
                "current_equity": current_equity
            }

        # 3. Daily Drawdown Breach
        if daily_dd_pct >= self.max_daily_drawdown_pct:
            state["state"] = "HALTED"
            state["halted"] = True
            state["halt_reason"] = (
                f"HALTED: Daily drawdown {daily_dd_pct * 100:.2f}% breached maximum allowed "
                f"limit of {self.max_daily_drawdown_pct * 100:.1f}%."
            )
            state["halt_timestamp"] = iso_now
            save_circuit_breaker_state(state)
            return {
                "decision": "HALT_CIRCUIT_BREAKER",
                "state": "HALTED",
                "can_trade": False,
                "reason": state["halt_reason"],
                "daily_drawdown_pct": round(daily_dd_pct * 100, 2),
                "weekly_drawdown_pct": round(weekly_dd_pct * 100, 2),
                "monthly_drawdown_pct": round(monthly_dd_pct * 100, 2),
                "peak_drawdown_pct": round(peak_dd_pct * 100, 2),
                "current_equity": current_equity
            }

        # 4. Cooldown Period Check
        cooldown_until = state.get("cooldown_until", 0.0)
        if now_ts < cooldown_until:
            rem_sec = int(cooldown_until - now_ts)
            state["state"] = "COOLDOWN"
            save_circuit_breaker_state(state)
            return {
                "decision": "COOLDOWN",
                "state": "COOLDOWN",
                "can_trade": False,
                "reason": f"Active cooldown period: {rem_sec}s remaining after loss threshold.",
                "cooldown_remaining_seconds": rem_sec,
                "daily_drawdown_pct": round(daily_dd_pct * 100, 2),
                "weekly_drawdown_pct": round(weekly_dd_pct * 100, 2),
                "monthly_drawdown_pct": round(monthly_dd_pct * 100, 2),
                "peak_drawdown_pct": round(peak_dd_pct * 100, 2),
                "current_equity": current_equity
            }
        elif state.get("state") == "COOLDOWN":
            state["state"] = "TRADING_ALLOWED"
            state["halt_reason"] = ""

        # 5. Portfolio Concurrency Limit
        if open_positions_count >= self.max_concurrent_positions:
            save_circuit_breaker_state(state)
            return {
                "decision": "MAX_CONCURRENT_POSITIONS_REACHED",
                "state": state.get("state", "TRADING_ALLOWED"),
                "can_trade": False,
                "reason": f"Active positions count ({open_positions_count}) has reached maximum limit ({self.max_concurrent_positions}).",
                "daily_drawdown_pct": round(daily_dd_pct * 100, 2),
                "weekly_drawdown_pct": round(weekly_dd_pct * 100, 2),
                "monthly_drawdown_pct": round(monthly_dd_pct * 100, 2),
                "peak_drawdown_pct": round(peak_dd_pct * 100, 2),
                "current_equity": current_equity,
                "open_positions": open_positions_count
            }

        state["state"] = "TRADING_ALLOWED"
        save_circuit_breaker_state(state)
        return {
            "decision": "TRADING_ALLOWED",
            "state": "TRADING_ALLOWED",
            "can_trade": True,
            "reason": "Account health verified within risk tolerances across all horizons.",
            "daily_drawdown_pct": round(daily_dd_pct * 100, 2),
            "weekly_drawdown_pct": round(weekly_dd_pct * 100, 2),
            "monthly_drawdown_pct": round(monthly_dd_pct * 100, 2),
            "peak_drawdown_pct": round(peak_dd_pct * 100, 2),
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
        contract_value: float = 0.001,
        leverage: int = 5,
        risk_pct_override: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate disciplined contract sizing strictly based on maximum risk tolerance.
        NEVER forces 1 contract if risk budget allows 0 contracts.
        """
        if entry_price <= 0 or stop_loss_price <= 0:
            return {"gate_status": "REJECTED", "error": "Entry and Stop Loss prices must be greater than zero", "contracts": 0}

        risk_pct = risk_pct_override if risk_pct_override is not None else self.max_risk_per_trade_pct
        planned_risk_usd = account_equity * risk_pct
        max_dollar_risk = min(planned_risk_usd, self.max_dollar_risk_per_trade)

        is_long = entry_price > stop_loss_price
        stop_distance = abs(entry_price - stop_loss_price)
        stop_distance_pct = (stop_distance / entry_price) * 100.0

        if stop_distance <= 0:
            return {"gate_status": "REJECTED", "error": "Stop loss price cannot equal entry price", "contracts": 0}

        # Calculate Reward to Risk
        profit_distance = abs(take_profit_price - entry_price)
        reward_to_risk = profit_distance / stop_distance if stop_distance > 0 else 0.0

        # Risk per 1 contract = stop_distance * contract_value
        risk_per_contract = stop_distance * contract_value
        if risk_per_contract <= 0:
            return {"gate_status": "REJECTED", "error": "Invalid risk per contract calculated", "contracts": 0}

        contracts_exact = max_dollar_risk / risk_per_contract
        contracts_int = int(contracts_exact)

        # STRICT RULE: Never force 1 contract if contracts_int < 1!
        if contracts_int < 1:
            return {
                "gate_status": "REJECTED",
                "contracts": 0,
                "reason": (
                    f"NO_TRADE: Permitted risk budget (${max_dollar_risk:.2f}) cannot afford 1 minimum "
                    f"contract (requires ${risk_per_contract:.2f} risk at {stop_distance_pct:.2f}% stop distance)."
                ),
                "rejection_reasons": [
                    f"Risk budget (${max_dollar_risk:.2f}) is lower than minimum single-contract risk (${risk_per_contract:.2f})."
                ],
                "side": "buy" if is_long else "sell",
                "entry_price": entry_price,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "max_dollar_risk": round(max_dollar_risk, 2),
                "actual_dollar_risk": 0.0,
                "reward_to_risk_ratio": round(reward_to_risk, 2)
            }

        # Notional and Margin
        notional_value = contracts_int * contract_value * entry_price
        actual_dollar_risk = contracts_int * risk_per_contract
        actual_risk_pct = (actual_dollar_risk / account_equity) * 100.0 if account_equity > 0 else 0.0

        clamped_leverage = min(leverage, self.max_allowed_leverage)
        required_margin = notional_value / clamped_leverage if clamped_leverage > 0 else notional_value

        # Discipline gate validation
        rr_passed = reward_to_risk >= self.min_reward_to_risk
        margin_passed = required_margin <= (account_equity * 0.95)

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
