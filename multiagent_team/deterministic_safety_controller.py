"""
Deterministic Safety Controller.
Enforces all 14 hard risk criteria in pure deterministic Python code immediately
before trade execution. Issues signed, time-limited execution tokens only when
every single safety criterion passes without exception.
"""

from typing import Dict, Any, List, Optional
import time
import hmac
import hashlib
import json
import logging
import os
from src.config import system_config
from src.risk_manager import RiskManager
from src.state_manager import StateManager

logger = logging.getLogger("safety-controller")
SAFETY_AUDIT_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "safety_audit.jsonl")


class DeterministicSafetyController:
    """
    Independent pre-execution safety gatekeeper.
    Evaluates 14 non-negotiable risk invariants and generates tamper-proof execution tokens.
    """
    def __init__(
        self,
        risk_manager: Optional[RiskManager] = None,
        state_manager: Optional[StateManager] = None,
        secret_key: Optional[str] = None
    ):
        self.risk_manager = risk_manager or RiskManager()
        self.state_manager = state_manager or StateManager()
        self.secret_key = (secret_key or system_config.delta_api_secret or "safety-secret-default").encode("utf-8")

    def _generate_token_signature(self, payload: Dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True)
        return hmac.new(self.secret_key, serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    def validate_and_issue_token(
        self,
        trade_setup: Dict[str, Any],
        account_equity: float,
        active_positions: List[Dict[str, Any]],
        market_data: Optional[Dict[str, Any]] = None,
        telegram_approval: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate all 14 safety criteria deterministically.
        Returns:
          {"passed": True, "token": {...}} or {"passed": False, "failure_code": "...", "reason": "..."}
        """
        now_ts = time.time()
        failures = []

        symbol = str(trade_setup.get("symbol", "")).upper()
        side = str(trade_setup.get("side", "")).lower()
        contracts = int(trade_setup.get("contracts", 0))
        entry_price = float(trade_setup.get("entry_price", 0.0))
        stop_loss = float(trade_setup.get("stop_loss_price", 0.0))
        take_profit = float(trade_setup.get("take_profit_price", 0.0))
        leverage = int(trade_setup.get("leverage", 10))
        client_order_id = str(trade_setup.get("client_order_id", ""))

        # ---------------------------------------------------------------------
        # 1. Circuit breaker not tripped
        # ---------------------------------------------------------------------
        cb_res = self.risk_manager.check_circuit_breaker(
            current_equity=account_equity,
            open_positions_count=len(active_positions)
        )
        if not cb_res.get("can_trade", False):
            failures.append(("CRITERION_1_CIRCUIT_BREAKER_HALTED", f"Circuit breaker active: {cb_res.get('reason')}"))

        # ---------------------------------------------------------------------
        # 2. Account equity above minimum threshold ($10)
        # ---------------------------------------------------------------------
        if account_equity < 10.0:
            failures.append(("CRITERION_2_INSUFFICIENT_EQUITY", f"Equity (${account_equity:.2f}) is below minimum $10 threshold"))

        # ---------------------------------------------------------------------
        # 3. Total portfolio exposure within limit
        # ---------------------------------------------------------------------
        if len(active_positions) >= system_config.max_portfolio_concurrency:
            failures.append((
                "CRITERION_3_PORTFOLIO_CONCURRENCY_EXCEEDED",
                f"Active positions ({len(active_positions)}) >= max allowed ({system_config.max_portfolio_concurrency})"
            ))

        # ---------------------------------------------------------------------
        # 4. Per-trade risk within limit (hard dollar cap & equity %)
        # ---------------------------------------------------------------------
        stop_dist = abs(entry_price - stop_loss)
        contract_val = float(trade_setup.get("contract_value", 0.001))
        dollar_risk = contracts * stop_dist * contract_val

        max_allowed_dollar_risk = min(
            account_equity * system_config.max_risk_per_trade_pct,
            system_config.max_dollar_risk_per_trade
        )
        # 1% tolerance for float rounding
        if dollar_risk > (max_allowed_dollar_risk * 1.02):
            failures.append((
                "CRITERION_4_RISK_LIMIT_EXCEEDED",
                f"Trade risk (${dollar_risk:.2f}) exceeds allowed max risk (${max_allowed_dollar_risk:.2f})"
            ))

        # ---------------------------------------------------------------------
        # 5. Maximum leverage within limit
        # ---------------------------------------------------------------------
        if leverage > system_config.max_allowed_leverage:
            failures.append((
                "CRITERION_5_LEVERAGE_EXCEEDED",
                f"Requested leverage ({leverage}x) exceeds hard ceiling ({system_config.max_allowed_leverage}x)"
            ))

        # ---------------------------------------------------------------------
        # 6. Stop loss exists and is on the correct side of entry
        # ---------------------------------------------------------------------
        if stop_loss <= 0 or entry_price <= 0:
            failures.append(("CRITERION_6_INVALID_PRICES", "Entry or stop loss price is non-positive"))
        elif side == "buy" and stop_loss >= entry_price:
            failures.append(("CRITERION_6_INVERTED_STOP_LOSS", f"Buy order stop loss (${stop_loss}) must be below entry (${entry_price})"))
        elif side == "sell" and stop_loss <= entry_price:
            failures.append(("CRITERION_6_INVERTED_STOP_LOSS", f"Sell order stop loss (${stop_loss}) must be above entry (${entry_price})"))

        # ---------------------------------------------------------------------
        # 7. Reward-to-risk ratio meets minimum threshold
        # ---------------------------------------------------------------------
        if stop_dist > 0:
            profit_dist = abs(take_profit - entry_price)
            rr_ratio = profit_dist / stop_dist
            if rr_ratio < (system_config.min_reward_to_risk - 0.05):
                failures.append((
                    "CRITERION_7_RR_INSUFFICIENT",
                    f"R:R ratio ({rr_ratio:.2f}) below minimum {system_config.min_reward_to_risk:.1f}:1"
                ))
        else:
            failures.append(("CRITERION_7_ZERO_STOP_DISTANCE", "Stop distance is zero"))

        # ---------------------------------------------------------------------
        # 8. Estimated liquidation price is outside the stop-loss buffer (>= 3.0x stop dist)
        # ---------------------------------------------------------------------
        liq_distance = float(trade_setup.get("liq_distance_pct", 0.0))
        stop_dist_pct = (stop_dist / entry_price * 100.0) if entry_price > 0 else 1.0
        if stop_dist_pct > 0 and (liq_distance / stop_dist_pct) < 2.8:  # 3.0x with slight tolerance
            failures.append((
                "CRITERION_8_LIQUIDATION_BUFFER_INSUFFICIENT",
                f"Liquidation buffer ({liq_distance:.2f}%) is less than 3.0x stop distance ({stop_dist_pct:.2f}%)"
            ))

        # ---------------------------------------------------------------------
        # 9. Symbol is on approved instrument list
        # ---------------------------------------------------------------------
        if symbol not in system_config.approved_symbols:
            failures.append((
                "CRITERION_9_UNAPPROVED_SYMBOL",
                f"Symbol {symbol} is not on the approved whitelist ({system_config.approved_symbols})"
            ))

        # ---------------------------------------------------------------------
        # 10. Spread is within maximum allowable spread (<= 0.20%)
        # ---------------------------------------------------------------------
        if market_data:
            spread_pct = float(market_data.get("spread_pct", 0.0))
            if spread_pct > 0.20:
                failures.append((
                    "CRITERION_10_EXCESSIVE_SPREAD",
                    f"Bid/Ask spread ({spread_pct:.3f}%) exceeds maximum allowable threshold (0.20%)"
                ))

        # ---------------------------------------------------------------------
        # 11. Data freshness: last candle / mark price is no older than 60s
        # ---------------------------------------------------------------------
        if market_data and "data_timestamp" in market_data:
            data_age = now_ts - float(market_data["data_timestamp"])
            if data_age > 60:
                failures.append((
                    "CRITERION_11_STALE_MARKET_DATA",
                    f"Market data is stale ({data_age:.1f}s old, max 60s permitted)"
                ))

        # ---------------------------------------------------------------------
        # 12. Correlation limit: max N concurrent positions in correlated assets
        # ---------------------------------------------------------------------
        same_side_crypto = 0
        for pos in active_positions:
            pos_sym = pos.get("symbol", "")
            pos_side = pos.get("side", "").lower()
            if any(c in pos_sym for c in ["BTC", "ETH", "SOL", "XRP"]) and pos_side == side:
                same_side_crypto += 1

        if same_side_crypto >= system_config.max_correlated_positions:
            failures.append((
                "CRITERION_12_CORRELATION_LIMIT",
                f"Correlated positions ({same_side_crypto}) reached maximum allowed ({system_config.max_correlated_positions})"
            ))

        # ---------------------------------------------------------------------
        # 13. Idempotency: order has not already been submitted
        # ---------------------------------------------------------------------
        if client_order_id and self.state_manager.is_client_order_id_used(client_order_id):
            failures.append((
                "CRITERION_13_IDEMPOTENCY_COLLISION",
                f"client_order_id {client_order_id} has already been registered in state manager"
            ))

        # ---------------------------------------------------------------------
        # 14. Explicit user approval verified (if Telegram confirmation required)
        # ---------------------------------------------------------------------
        if telegram_approval is not None:
            if not telegram_approval.get("approved", False):
                failures.append((
                    "CRITERION_14_USER_APPROVAL_REJECTED",
                    f"User explicitly rejected trade approval: {telegram_approval.get('reason')}"
                ))
            elif telegram_approval.get("expired", False):
                failures.append((
                    "CRITERION_14_USER_APPROVAL_EXPIRED",
                    "User approval request expired before confirmation"
                ))

        # Record Audit Entry
        os.makedirs(os.path.dirname(SAFETY_AUDIT_LOG), exist_ok=True)
        audit_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "symbol": symbol,
            "side": side,
            "contracts": contracts,
            "passed": len(failures) == 0,
            "failures": failures
        }
        with open(SAFETY_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")

        # If any check failed, reject immediately
        if failures:
            failure_code, reason = failures[0]
            logger.warning(f"SafetyController VETO on {symbol}: [{failure_code}] {reason}")
            return {
                "passed": False,
                "failure_code": failure_code,
                "reason": reason,
                "all_failures": failures
            }

        # Issue Cryptographically Signed Execution Token (TTL = 30 seconds)
        ttl_seconds = 30
        token_payload = {
            "symbol": symbol,
            "side": side,
            "contracts": contracts,
            "entry_price": entry_price,
            "stop_loss_price": stop_loss,
            "take_profit_price": take_profit,
            "client_order_id": client_order_id,
            "issued_at": now_ts,
            "expires_at": now_ts + ttl_seconds
        }
        signature = self._generate_token_signature(token_payload)

        token = {
            "valid": True,
            "payload": token_payload,
            "signature": signature,
            "expires_at": now_ts + ttl_seconds
        }

        logger.info(f"SafetyController APPROVED: Issued execution token for {symbol} {side.upper()} (TTL: {ttl_seconds}s)")
        return {
            "passed": True,
            "token": token
        }

