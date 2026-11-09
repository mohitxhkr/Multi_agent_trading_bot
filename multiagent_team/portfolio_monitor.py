"""
Agent 9: Portfolio Monitor & Capital Protection Sentinel.
Delta Exchange Multi-Agent Quantitative Trading System.

Enterprise-grade portfolio-level risk surveillance, real-time position health,
margin utilization, liquidation distance, protective stop-loss verification,
exchange-local state reconciliation, drawdown enforcement, correlation tracking,
and emergency protection integration.
"""

from typing import Dict, Any, List, Optional, Tuple, Set
import logging
import os
import time
import json
import threading
from datetime import datetime, timezone

from src.delta_client import DeltaExchangeClient
from src.config import system_config
from src.state_manager import StateManager
from src.risk_manager import RiskManager
from src.emergency_controller import EmergencyController
from multiagent_team.deterministic_safety_controller import DeterministicSafetyController
from src.journal import (
    record_trade_entry,
    record_trade_exit,
    get_performance_summary
)

logger = logging.getLogger("portfolio-monitor")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def ensure_reports_dir():
    os.makedirs(REPORTS_DIR, exist_ok=True)


# =============================================================================
# DEFAULT CONFIGURATION & THRESHOLDS
# =============================================================================

DEFAULT_PORTFOLIO_CONFIG: Dict[str, Any] = {
    "max_daily_drawdown_pct": float(getattr(system_config, "max_daily_drawdown_pct", 0.03)) * 100.0,   # 3.0%
    "max_weekly_drawdown_pct": float(getattr(system_config, "max_weekly_drawdown_pct", 0.05)) * 100.0, # 5.0%
    "max_consecutive_losses": int(getattr(system_config, "max_consecutive_losses", 3)),
    "max_portfolio_concurrency": int(getattr(system_config, "max_portfolio_concurrency", 2)),
    "max_correlated_positions": int(getattr(system_config, "max_correlated_positions", 2)),
    "max_margin_utilization_pct": 80.0,
    "margin_warning_threshold_pct": 70.0,
    "margin_high_risk_threshold_pct": 85.0,
    "margin_critical_threshold_pct": 95.0,
    "liq_distance_warning_pct": 10.0,
    "liq_distance_high_risk_pct": 5.0,
    "liq_distance_critical_pct": 2.5,
    "max_cluster_concentration_pct": 50.0,
    "alert_cooldown_seconds": 900,  # 15 minutes alert deduplication window
    "data_freshness_max_seconds": 60,
    "max_api_retries": 2
}

# Asset correlation clusters for concentration surveillance
CORRELATION_CLUSTERS: Dict[str, Set[str]] = {
    "CRYPTO_MAJOR_ALT": {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK"},
    "PRECIOUS_METALS": {"XAU", "XAUT", "PAXG", "GOLD"}
}


# =============================================================================
# CONTRACT SPECIFICATION & VALUATION ENGINE
# =============================================================================

KNOWN_CONTRACT_SPECS: Dict[str, Dict[str, Any]] = {
    "BTCUSD": {"contract_type": "linear", "contract_value": 0.001, "settling_asset": "USDT", "quoting_asset": "USD"},
    "BTCUSDT": {"contract_type": "linear", "contract_value": 0.001, "settling_asset": "USDT", "quoting_asset": "USDT"},
    "ETHUSD": {"contract_type": "linear", "contract_value": 0.01, "settling_asset": "USDT", "quoting_asset": "USD"},
    "ETHUSDT": {"contract_type": "linear", "contract_value": 0.01, "settling_asset": "USDT", "quoting_asset": "USDT"},
    "SOLUSD": {"contract_type": "linear", "contract_value": 1.0, "settling_asset": "USDT", "quoting_asset": "USD"},
    "SOLUSDT": {"contract_type": "linear", "contract_value": 1.0, "settling_asset": "USDT", "quoting_asset": "USDT"},
    "XRPUSD": {"contract_type": "linear", "contract_value": 1.0, "settling_asset": "USDT", "quoting_asset": "USD"},
    "XRPUSDT": {"contract_type": "linear", "contract_value": 1.0, "settling_asset": "USDT", "quoting_asset": "USDT"},
    "XAUUSD": {"contract_type": "linear", "contract_value": 0.001, "settling_asset": "USDT", "quoting_asset": "USD"},
    "XAUTUSD": {"contract_type": "linear", "contract_value": 0.001, "settling_asset": "USDT", "quoting_asset": "USDT"},
    "PAXGUSD": {"contract_type": "linear", "contract_value": 0.001, "settling_asset": "USDT", "quoting_asset": "USD"}
}


def get_contract_spec(
    symbol: str,
    client: Optional[DeltaExchangeClient] = None,
    raw_product: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Retrieve contract specification (linear vs inverse, contract multiplier, settling asset).
    Never assumes universal multipliers. Falls back to verified product cache.
    """
    sym = (symbol or "").upper().strip()

    # 1. Product info passed directly with contract_value
    if raw_product and isinstance(raw_product, dict) and ("contract_value" in raw_product or "contract_unit" in raw_product):
        c_type = str(raw_product.get("contract_type", "linear")).lower()
        settling = str(raw_product.get("settling_asset", {}).get("symbol", "USDT") if isinstance(raw_product.get("settling_asset"), dict) else raw_product.get("settling_asset", "USDT")).upper()
        quoting = str(raw_product.get("quoting_asset", {}).get("symbol", "USDT") if isinstance(raw_product.get("quoting_asset"), dict) else raw_product.get("quoting_asset", "USDT")).upper()
        c_val = float(raw_product.get("contract_value") or raw_product.get("contract_unit") or 1.0)
        is_inv = "inverse" in c_type or (settling != "USDT" and settling != "USD")
        return {
            "contract_type": "inverse" if is_inv else "linear",
            "contract_value": c_val,
            "settling_asset": settling,
            "quoting_asset": quoting,
            "tick_size": float(raw_product.get("tick_size") or 0.01)
        }

    # 2. Query Client Product Cache
    if client:
        try:
            p_info = client.get_product_info(sym)
            if p_info:
                return get_contract_spec(sym, None, p_info)
        except Exception:
            pass

    # 3. Known dictionary lookup
    for k, spec in KNOWN_CONTRACT_SPECS.items():
        if k in sym or sym in k:
            return dict(spec)

    # 4. Fallback safe linear specification
    return {
        "contract_type": "linear",
        "contract_value": 1.0,
        "settling_asset": "USDT",
        "quoting_asset": "USDT",
        "tick_size": 0.01
    }


def calculate_position_metrics(
    position: Dict[str, Any],
    contract_spec: Dict[str, Any],
    mark_price_override: Optional[float] = None
) -> Dict[str, Any]:
    """
    Deterministically computes position notional value, unrealized PnL,
    and mark-to-liquidation distance for linear and inverse contracts.
    Never replaces missing mark price with entry price or missing liquidation distance with safe 999.0%.
    """
    raw_size = float(position.get("size", 0))
    direction = "LONG" if raw_size > 0 else ("SHORT" if raw_size < 0 else "FLAT")
    contracts = abs(raw_size)
    entry_price = float(position.get("entry_price", 0.0) or 0.0)

    # Missing data handling: never substitute entry price for mark price
    if mark_price_override is not None and mark_price_override > 0:
        mark_price = float(mark_price_override)
    elif position.get("mark_price") is not None and float(position.get("mark_price")) > 0:
        mark_price = float(position.get("mark_price"))
    else:
        mark_price = None

    raw_liq = position.get("liquidation_price")
    liq_price = float(raw_liq) if (raw_liq is not None and float(raw_liq) > 0) else None
    c_val = float(contract_spec.get("contract_value", 1.0))
    is_inverse = contract_spec.get("contract_type") == "inverse"

    # Notional Exposure & Base Quantity
    if mark_price is not None:
        if not is_inverse:
            # Linear: contracts * contract_value = base coins (e.g. 10 * 0.001 = 0.01 BTC)
            base_quantity = contracts * c_val
            notional_usd = base_quantity * mark_price
        else:
            # Inverse: contracts * contract_value = USD notional (e.g. 100 * $1 = $100)
            notional_usd = contracts * c_val
            base_quantity = (notional_usd / mark_price) if mark_price > 0 else 0.0
    else:
        if is_inverse:
            notional_usd = contracts * c_val
            base_quantity = 0.0
        else:
            base_quantity = contracts * c_val
            notional_usd = 0.0

    # Unrealized PnL Calculation
    unrealized_pnl = 0.0
    if entry_price > 0 and mark_price is not None and mark_price > 0 and contracts > 0:
        if not is_inverse:
            if direction == "LONG":
                unrealized_pnl = (mark_price - entry_price) * contracts * c_val
            elif direction == "SHORT":
                unrealized_pnl = (entry_price - mark_price) * contracts * c_val
        else:
            if direction == "LONG":
                pnl_coin = ((1.0 / entry_price) - (1.0 / mark_price)) * contracts * c_val
            elif direction == "SHORT":
                pnl_coin = ((1.0 / mark_price) - (1.0 / entry_price)) * contracts * c_val
            else:
                pnl_coin = 0.0
            unrealized_pnl = pnl_coin * mark_price

    # Realized PnL from position record if reported
    realized_pnl = float(position.get("realized_pnl", 0.0) or 0.0)

    # True Liquidation Distance: Measured from CURRENT MARK PRICE to LIQUIDATION PRICE!
    # Missing liquidation price returns None; never defaults to safe 999.0%
    if mark_price is not None and mark_price > 0 and liq_price is not None and liq_price > 0:
        if direction == "LONG":
            liq_distance_pct = max(0.0, (mark_price - liq_price) / mark_price * 100.0)
        elif direction == "SHORT":
            liq_distance_pct = max(0.0, (liq_price - mark_price) / mark_price * 100.0)
        else:
            liq_distance_pct = None
    else:
        liq_distance_pct = None

    return {
        "direction": direction,
        "contracts": contracts,
        "base_quantity": round(base_quantity, 6),
        "notional_usd": round(notional_usd, 2),
        "entry_price": round(entry_price, 4),
        "mark_price": round(mark_price, 4) if mark_price is not None else None,
        "liquidation_price": round(liq_price, 4) if liq_price is not None else None,
        "liquidation_distance_pct": round(liq_distance_pct, 2) if liq_distance_pct is not None else None,
        "unrealized_pnl": round(unrealized_pnl, 4),
        "realized_pnl": round(realized_pnl, 4),
        "contract_type": contract_spec.get("contract_type", "linear"),
        "contract_value": c_val
    }


# =============================================================================
# PORTFOLIO MONITOR AGENT
# =============================================================================

class PortfolioMonitorAgent:
    """
    Agent 9: Portfolio Monitor & Capital Protection Sentinel.
    Surveys active positions, margin health, liquidation risks, protective stops,
    and orchestrates emergency containment when safety invariants are breached.
    """

    def __init__(
        self,
        client: DeltaExchangeClient,
        state_manager: Optional[StateManager] = None,
        risk_manager: Optional[RiskManager] = None,
        safety_controller: Optional[DeterministicSafetyController] = None,
        emergency_controller: Optional[EmergencyController] = None,
        telegram: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.client = client
        self.state_manager = state_manager or StateManager()
        self.risk_manager = risk_manager or RiskManager()
        self.safety_controller = safety_controller
        self.emergency_controller = emergency_controller or EmergencyController(client=self.client)
        self.telegram = telegram
        self.config = {**DEFAULT_PORTFOLIO_CONFIG, **(config or {})}

        # Thread safety lock for concurrent evaluations
        self._lock = threading.Lock()

        # Alert deduplication cache: {alert_key: last_sent_timestamp}
        self._alert_history: Dict[str, float] = {}

        # Last confirmed monitoring state
        self._last_state: Dict[str, Any] = {}
        self._last_successful_poll_ts: float = 0.0

    # -------------------------------------------------------------------------
    # Core Position & Portfolio Surveillance (Public API)
    # -------------------------------------------------------------------------
    def monitor_positions(self) -> Dict[str, Any]:
        """
        Continuously polls exchange positions, wallet balances, open orders,
        computes portfolio exposure and margin utilization, audits protective stops,
        and reconciles state with local persistence.
        """
        with self._lock:
            now_ts = time.time()
            risk_events: List[Dict[str, Any]] = []

            # 1. Fetch live exchange wallet balances
            wallet_res = self._fetch_with_retry(self.client.get_wallet_balances)
            if not wallet_res.get("success"):
                err_msg = f"Failed to poll wallet balances: {wallet_res.get('error', 'Network error')}"
                logger.error(f"PortfolioMonitor: {err_msg}")
                return self._build_fail_closed_status("UNKNOWN", err_msg, now_ts)

            # 2. Fetch live exchange open positions
            pos_res = self._fetch_with_retry(self.client.get_positions)
            if not pos_res.get("success"):
                err_msg = f"Failed to poll positions: {pos_res.get('error', 'Network error')}"
                logger.error(f"PortfolioMonitor: {err_msg}")
                return self._build_fail_closed_status("UNKNOWN", err_msg, now_ts)

            # 3. Fetch live exchange open orders (for protective stop audit)
            orders_res = self._fetch_with_retry(self.client.get_open_orders)
            if not orders_res.get("success"):
                err_msg = f"Failed to poll open orders: {orders_res.get('error', 'Network error')}"
                logger.error(f"PortfolioMonitor: {err_msg}")
                return self._build_fail_closed_status("UNKNOWN", err_msg, now_ts)

            self._last_successful_poll_ts = now_ts
            raw_positions = pos_res.get("result", []) or []
            raw_orders = orders_res.get("result", []) or []
            raw_balances = wallet_res.get("result", []) or []
            wallet_meta = wallet_res.get("meta", {}) or {}

            # Parse Account Balances & Equity
            account_equity, available_balance, margin_used = self._parse_wallet_metrics(raw_balances, wallet_meta)

            # Process Active Positions
            active_positions: List[Dict[str, Any]] = []
            total_unrealized_pnl = 0.0
            total_open_exposure = 0.0
            long_exposure = 0.0
            short_exposure = 0.0
            total_initial_risk = 0.0
            remaining_risk = 0.0
            liquidation_warnings: List[Dict[str, Any]] = []

            for p in raw_positions:
                raw_size = float(p.get("size", 0))
                if raw_size == 0:
                    continue

                sym = str(p.get("product_symbol") or p.get("symbol") or "")
                c_spec = get_contract_spec(sym, self.client, p)
                metrics = calculate_position_metrics(p, c_spec)

                pos_unrealized = metrics["unrealized_pnl"]
                pos_notional = metrics["notional_usd"]
                total_unrealized_pnl += pos_unrealized
                total_open_exposure += pos_notional

                if metrics["direction"] == "LONG":
                    long_exposure += pos_notional
                elif metrics["direction"] == "SHORT":
                    short_exposure += pos_notional

                # Liquidation Distance Checks
                liq_dist = metrics["liquidation_distance_pct"]
                if liq_dist is None:
                    if metrics["contracts"] > 0:
                        sev = "WARNING"
                        msg = f"UNKNOWN: {sym} liquidation price is missing from exchange position record!"
                        liquidation_warnings.append({"symbol": sym, "severity": "UNKNOWN", "distance_pct": None, "message": msg})
                        risk_events.append({"event_type": "MISSING_LIQUIDATION_PRICE", "severity": sev, "symbol": sym, "message": msg})
                elif liq_dist <= self.config["liq_distance_critical_pct"]:
                    sev = "CRITICAL"
                    msg = f"CRITICAL: {sym} is only {liq_dist:.2f}% from liquidation (${metrics['liquidation_price']:.2f})!"
                    liquidation_warnings.append({"symbol": sym, "severity": sev, "distance_pct": liq_dist, "message": msg})
                    risk_events.append({"event_type": "LIQUIDATION_RISK", "severity": sev, "symbol": sym, "message": msg})
                    self.dispatch_telegram_alert("LIQUIDATION_RISK", sym, sev, msg, confirmed=True)
                elif liq_dist <= self.config["liq_distance_high_risk_pct"]:
                    sev = "HIGH_RISK"
                    msg = f"HIGH RISK: {sym} liquidation buffer compressed to {liq_dist:.2f}%."
                    liquidation_warnings.append({"symbol": sym, "severity": sev, "distance_pct": liq_dist, "message": msg})
                    risk_events.append({"event_type": "LIQUIDATION_RISK", "severity": sev, "symbol": sym, "message": msg})
                    self.dispatch_telegram_alert("LIQUIDATION_RISK", sym, sev, msg, confirmed=True)
                elif liq_dist <= self.config["liq_distance_warning_pct"]:
                    sev = "WARNING"
                    msg = f"WARNING: {sym} liquidation distance is {liq_dist:.2f}%."
                    liquidation_warnings.append({"symbol": sym, "severity": sev, "distance_pct": liq_dist, "message": msg})
                    self.dispatch_telegram_alert("LIQUIDATION_RISK", sym, sev, msg, confirmed=True)

                # Local Database Cross-reference for Initial Stop Loss and Trade Risk
                local_pos = self._get_local_position_record(sym)
                init_sl = float(local_pos.get("stop_loss", 0.0) if local_pos else p.get("stop_loss", 0.0) or 0.0)
                current_sl = float(p.get("stop_loss", 0.0) or init_sl)
                tp_price = float(local_pos.get("take_profit", 0.0) if local_pos else p.get("take_profit", 0.0) or 0.0)

                # Monetary risk computation
                if init_sl > 0 and metrics["entry_price"] > 0:
                    unit_risk = abs(metrics["entry_price"] - init_sl)
                    pos_risk = unit_risk * metrics["contracts"] * metrics["contract_value"]
                    total_initial_risk += pos_risk

                if current_sl > 0 and metrics["mark_price"] > 0:
                    if metrics["direction"] == "LONG":
                        rem_dist = max(0.0, metrics["mark_price"] - current_sl) if current_sl < metrics["mark_price"] else 0.0
                    else:
                        rem_dist = max(0.0, current_sl - metrics["mark_price"]) if current_sl > metrics["mark_price"] else 0.0
                    remaining_risk += rem_dist * metrics["contracts"] * metrics["contract_value"]

                # Position age calculation
                created_str = p.get("created_at") or (local_pos.get("created_at") if local_pos else None)
                pos_age = self._parse_iso_age(created_str, now_ts)

                active_positions.append({
                    "symbol": sym,
                    "direction": metrics["direction"],
                    "side": metrics["direction"],  # Backward-compatibility alias
                    "size": raw_size,
                    "contracts": metrics["contracts"],
                    "base_quantity": metrics["base_quantity"],
                    "notional_usd": metrics["notional_usd"],
                    "entry_price": metrics["entry_price"],
                    "current_mark_price": metrics["mark_price"],
                    "mark_price": metrics["mark_price"],
                    "liquidation_price": metrics["liquidation_price"],
                    "liquidation_distance_pct": metrics["liquidation_distance_pct"],
                    "unrealized_pnl_usd": metrics["unrealized_pnl"],
                    "unrealized_pnl": metrics["unrealized_pnl"],
                    "realized_pnl": metrics["realized_pnl"],
                    "initial_stop_loss": init_sl,
                    "current_stop_loss": current_sl,
                    "take_profit_levels": [tp_price] if tp_price > 0 else [],
                    "leverage": p.get("leverage", 10),
                    "margin_used": float(p.get("margin", 0.0) or 0.0),
                    "position_age_seconds": round(pos_age, 1),
                    "contract_type": metrics["contract_type"],
                    "is_exchange_confirmed": True,
                    "exchange_position_status": "OPEN"
                })

            # Margin Utilization Assessment
            margin_util_pct = (margin_used / max(1.0, account_equity) * 100.0) if account_equity > 0 else 0.0
            margin_status = "NORMAL"
            if margin_util_pct >= self.config["margin_critical_threshold_pct"]:
                margin_status = "CRITICAL"
                msg = f"CRITICAL: Portfolio margin utilization reached {margin_util_pct:.1f}% (Equity: ${account_equity:.2f})!"
                risk_events.append({"event_type": "HIGH_MARGIN_UTILIZATION", "severity": "CRITICAL", "message": msg})
                self.dispatch_telegram_alert("HIGH_MARGIN_UTILIZATION", "PORTFOLIO", "CRITICAL", msg, confirmed=True)
            elif margin_util_pct >= self.config["margin_high_risk_threshold_pct"]:
                margin_status = "HIGH_RISK"
                msg = f"HIGH RISK: Portfolio margin utilization is elevated at {margin_util_pct:.1f}%."
                risk_events.append({"event_type": "HIGH_MARGIN_UTILIZATION", "severity": "HIGH_RISK", "message": msg})
                self.dispatch_telegram_alert("HIGH_MARGIN_UTILIZATION", "PORTFOLIO", "HIGH_RISK", msg, confirmed=True)
            elif margin_util_pct >= self.config["margin_warning_threshold_pct"]:
                margin_status = "WARNING"
                msg = f"WARNING: Margin utilization at {margin_util_pct:.1f}%."
                self.dispatch_telegram_alert("HIGH_MARGIN_UTILIZATION", "PORTFOLIO", "WARNING", msg, confirmed=True)

            # 4. Critical Protective Stop-Loss Verification
            prot_audit = self.verify_protective_orders(active_positions, raw_orders)
            if prot_audit["unprotected_positions"]:
                for unprot in prot_audit["unprotected_positions"]:
                    u_sym = unprot["symbol"]
                    u_msg = f"CRITICAL SAFETY BREACH: Position on {u_sym} (size {unprot['size']}) has NO active Stop Loss order on exchange!"
                    risk_events.append({"event_type": "MISSING_PROTECTIVE_STOP", "severity": "CRITICAL", "symbol": u_sym, "message": u_msg})
                    self.dispatch_telegram_alert("MISSING_PROTECTIVE_STOP", u_sym, "CRITICAL", u_msg, confirmed=True)
                    # Trigger Emergency Protection Protocol immediately!
                    if self.emergency_controller:
                        logger.critical(f"PortfolioMonitor: Triggering emergency stop placement for {u_sym} via EmergencyController...")
                        self.emergency_controller.verify_and_ensure_sl_protection()

            if prot_audit["insufficient_quantity_positions"]:
                for inq in prot_audit["insufficient_quantity_positions"]:
                    iq_sym = inq["symbol"]
                    iq_msg = f"PROTECTIVE QUANTITY MISMATCH: Position on {iq_sym} is {inq['position_size']} contracts but Stop Loss only covers {inq['stop_size']} contracts!"
                    risk_events.append({"event_type": "INSUFFICIENT_PROTECTIVE_QUANTITY", "severity": "HIGH_RISK", "symbol": iq_sym, "message": iq_msg})
                    self.dispatch_telegram_alert("PARTIAL_FILL_STOP_MISMATCH", iq_sym, "HIGH_RISK", iq_msg, confirmed=True)

            # 5. Exchange vs Local State Reconciliation
            reconcile_report = self.reconcile_state(raw_positions, active_positions)
            exchange_sync_status = "SYNCHRONIZED"
            if reconcile_report["discrepancies"]:
                exchange_sync_status = "DESYNCHRONIZED"
                d_msg = f"DESYNCHRONIZATION DETECTED: {len(reconcile_report['discrepancies'])} mismatch(es) between exchange and local state."
                risk_events.append({"event_type": "DESYNCHRONIZATION", "severity": "WARNING", "message": d_msg, "details": reconcile_report["discrepancies"]})
                self.dispatch_telegram_alert("DESYNCHRONIZATION", "PORTFOLIO", "WARNING", d_msg, confirmed=False)

            # 6. Correlation & Concentration Surveillance
            corr_analysis = self.check_correlation_and_concentration(active_positions, account_equity)
            if corr_analysis["warnings"]:
                for c_warn in corr_analysis["warnings"]:
                    risk_events.append({"event_type": "PORTFOLIO_CONCENTRATION", "severity": "WARNING", "message": c_warn})
                    self.dispatch_telegram_alert("PORTFOLIO_CONCENTRATION", "PORTFOLIO", "WARNING", c_warn, confirmed=True)

            # 7. Drawdown and Circuit Breaker Threshold Surveillance
            drawdown_metrics = self.check_drawdown_and_limits(account_equity, total_unrealized_pnl)
            if drawdown_metrics["events"]:
                for dd_ev in drawdown_metrics["events"]:
                    risk_events.append(dd_ev)
                    self.dispatch_telegram_alert(dd_ev["event_type"], "PORTFOLIO", dd_ev["severity"], dd_ev["message"], confirmed=True)

            # Determine Overall Status
            overall_status = "HEALTHY"
            if any(ev["severity"] == "CRITICAL" for ev in risk_events) or prot_audit["unprotected_positions"]:
                overall_status = "CRITICAL"
            elif any(ev["severity"] == "HIGH_RISK" for ev in risk_events) or margin_status == "HIGH_RISK":
                overall_status = "HIGH_RISK"
            elif exchange_sync_status == "DESYNCHRONIZED":
                overall_status = "DESYNCHRONIZED"
            elif any(ev["severity"] == "WARNING" for ev in risk_events) or margin_status == "WARNING":
                overall_status = "WARNING"

            # Construct Comprehensive Output Contract
            status_payload = {
                "account_equity": round(account_equity, 2),
                "available_balance": round(available_balance, 2),
                "margin_used": round(margin_used, 2),
                "margin_utilization": round(margin_util_pct, 2),
                "margin_status": margin_status,
                "total_open_exposure": round(total_open_exposure, 2),
                "long_exposure": round(long_exposure, 2),
                "short_exposure": round(short_exposure, 2),
                "net_directional_exposure": round(long_exposure - short_exposure, 2),
                "gross_exposure": round(long_exposure + short_exposure, 2),
                "total_open_risk": round(total_initial_risk, 2),
                "remaining_portfolio_risk": round(remaining_risk, 2),
                "daily_pnl": round(drawdown_metrics["daily_pnl"], 2),
                "weekly_pnl": round(drawdown_metrics["weekly_pnl"], 2),
                "daily_drawdown": round(drawdown_metrics["daily_drawdown_pct"], 2),
                "weekly_drawdown": round(drawdown_metrics["weekly_drawdown_pct"], 2),
                "max_observed_drawdown": round(drawdown_metrics["max_observed_drawdown_pct"], 2),
                "consecutive_losses": drawdown_metrics["consecutive_losses"],
                "open_positions": active_positions,
                "correlated_exposure": corr_analysis,
                "liquidation_warnings": liquidation_warnings,
                "protective_order_status": prot_audit,
                "exchange_sync_status": exchange_sync_status,
                "reconciliation_report": reconcile_report,
                "stale_data_status": {
                    "is_stale": False,
                    "last_poll_age_seconds": round(now_ts - self._last_successful_poll_ts, 1)
                },
                "risk_events": risk_events,
                "monitoring_timestamp": now_ts,
                "overall_status": overall_status,

                # Backward compatibility keys for existing Orchestrator:
                "active_count": len(active_positions),
                "total_unrealized_pnl_usd": round(total_unrealized_pnl, 2),
                "positions": active_positions
            }

            self._last_state = status_payload
            return status_payload

    # -------------------------------------------------------------------------
    # Protective Order Verification (Section 6)
    # -------------------------------------------------------------------------
    def verify_protective_orders(
        self,
        positions: List[Dict[str, Any]],
        open_orders: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verifies that every open position is strictly covered by a valid exchange stop-loss.
        Validates symbol, direction, quantity coverage, and price validity.
        """
        audit = {
            "all_protected": True,
            "protected_positions": [],
            "unprotected_positions": [],
            "insufficient_quantity_positions": [],
            "duplicate_stop_orders": []
        }

        # Index stop orders by symbol
        stop_orders_by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for o in open_orders:
            s_type = str(o.get("stop_order_type") or "").lower()
            o_type = str(o.get("order_type") or "").lower()
            is_stop = "stop" in s_type or "stop" in o_type

            if is_stop:
                sym = str(o.get("product_symbol") or o.get("symbol") or "")
                stop_orders_by_sym.setdefault(sym, []).append(o)

        for pos in positions:
            sym = pos["symbol"]
            size = pos["size"]
            direction = pos["direction"]
            matching_stops = stop_orders_by_sym.get(sym, [])

            if not matching_stops:
                audit["all_protected"] = False
                audit["unprotected_positions"].append({
                    "symbol": sym,
                    "size": size,
                    "direction": direction,
                    "reason": "NO_STOP_ORDER_FOUND"
                })
                continue

            # Verify side and quantity
            valid_stop_size = 0
            valid_stops = []
            for so in matching_stops:
                so_side = str(so.get("side", "")).lower()
                so_size = int(so.get("size", 0))
                # Long position requires Sell stop; Short position requires Buy stop
                if (direction == "LONG" and so_side == "sell") or (direction == "SHORT" and so_side == "buy"):
                    valid_stop_size += so_size
                    valid_stops.append(so)

            if len(valid_stops) > 1:
                audit["duplicate_stop_orders"].append({
                    "symbol": sym,
                    "count": len(valid_stops),
                    "order_ids": [o.get("id") for o in valid_stops]
                })

            if valid_stop_size == 0:
                audit["all_protected"] = False
                audit["unprotected_positions"].append({
                    "symbol": sym,
                    "size": size,
                    "direction": direction,
                    "reason": "STOP_ORDERS_HAVE_INCORRECT_SIDE"
                })
            elif valid_stop_size < abs(size):
                audit["all_protected"] = False
                audit["insufficient_quantity_positions"].append({
                    "symbol": sym,
                    "position_size": abs(size),
                    "stop_size": valid_stop_size,
                    "coverage_deficit": abs(size) - valid_stop_size
                })
            else:
                audit["protected_positions"].append({
                    "symbol": sym,
                    "position_size": abs(size),
                    "covered_stop_size": valid_stop_size,
                    "stop_order_ids": [o.get("id") for o in valid_stops]
                })

        return audit

    # -------------------------------------------------------------------------
    # State Reconciliation Engine (Section 7)
    # -------------------------------------------------------------------------
    def reconcile_state(
        self,
        raw_exchange_positions: List[Dict[str, Any]],
        processed_positions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cross-examines live exchange state against SQLite local StateManager database.
        Detects missing, orphaned, or size-divergent positions and applies idempotent synchronization.
        """
        report: Dict[str, Any] = {
            "discrepancies": [],
            "discovered_on_exchange": [],
            "orphans_closed_locally": [],
            "synced_symbols": []
        }

        try:
            local_positions = self.state_manager.get_open_positions()
            local_by_sym = {lp["symbol"]: lp for lp in local_positions}
            exchange_by_sym = {p["symbol"]: p for p in processed_positions}

            # Check Exchange -> Local
            for sym, ep in exchange_by_sym.items():
                if sym not in local_by_sym:
                    report["discrepancies"].append({
                        "type": "EXCHANGE_POSITION_MISSING_LOCALLY",
                        "symbol": sym,
                        "exchange_size": ep["size"],
                        "action": "AUTO_REGISTER_IN_STATE_MANAGER"
                    })
                    report["discovered_on_exchange"].append(sym)
                else:
                    lp = local_by_sym[sym]
                    if abs(int(lp.get("contracts", 0))) != abs(int(ep.get("size", 0))):
                        report["discrepancies"].append({
                            "type": "QUANTITY_MISMATCH",
                            "symbol": sym,
                            "local_contracts": lp.get("contracts"),
                            "exchange_size": ep.get("size")
                        })
                    else:
                        report["synced_symbols"].append(sym)

            # Check Local -> Exchange
            for sym, lp in local_by_sym.items():
                if sym not in exchange_by_sym:
                    report["discrepancies"].append({
                        "type": "LOCAL_POSITION_MISSING_ON_EXCHANGE",
                        "symbol": sym,
                        "local_status": lp.get("status"),
                        "action": "AUTO_CLOSE_ORPHAN_IN_STATE_MANAGER"
                    })
                    report["orphans_closed_locally"].append(sym)

            # Perform Idempotent Sync via StateManager
            self.state_manager.reconcile_positions_with_exchange(raw_exchange_positions)

        except Exception as e:
            logger.error(f"PortfolioMonitor: Error during reconciliation: {e}")
            report["discrepancies"].append({"type": "RECONCILIATION_ERROR", "error": str(e)})

        return report

    # -------------------------------------------------------------------------
    # Correlation & Concentration Surveillance (Section 4)
    # -------------------------------------------------------------------------
    def check_correlation_and_concentration(
        self,
        positions: List[Dict[str, Any]],
        account_equity: float
    ) -> Dict[str, Any]:
        """
        Surveys directional concentration across correlated crypto and commodity clusters.
        """
        cluster_exposure: Dict[str, Dict[str, float]] = {}
        cluster_counts: Dict[str, Dict[str, int]] = {}
        warnings: List[str] = []

        for c_name in CORRELATION_CLUSTERS.keys():
            cluster_exposure[c_name] = {"LONG": 0.0, "SHORT": 0.0}
            cluster_counts[c_name] = {"LONG": 0, "SHORT": 0}

        for p in positions:
            sym = p["symbol"]
            d = p["direction"]
            notional = p["notional_usd"]

            for c_name, members in CORRELATION_CLUSTERS.items():
                if any(m in sym for m in members):
                    if d in ("LONG", "SHORT"):
                        cluster_exposure[c_name][d] += notional
                        cluster_counts[c_name][d] += 1

        # Evaluate concentration limits
        for c_name, counts in cluster_counts.items():
            for d in ("LONG", "SHORT"):
                cnt = counts[d]
                exp = cluster_exposure[c_name][d]
                if cnt > self.config["max_correlated_positions"]:
                    warnings.append(
                        f"CORRELATION LIMIT EXCEEDED: Cluster '{c_name}' has {cnt} concurrent {d} positions (max allowed: {self.config['max_correlated_positions']})."
                    )

                if account_equity > 0:
                    conc_pct = exp / account_equity * 100.0
                    if conc_pct >= self.config["max_cluster_concentration_pct"]:
                        warnings.append(
                            f"CONCENTRATION RISK: Cluster '{c_name}' {d} exposure is {conc_pct:.1f}% of equity (${exp:,.2f} / ${account_equity:,.2f})."
                        )

        return {
            "cluster_exposure": cluster_exposure,
            "cluster_counts": cluster_counts,
            "warnings": warnings
        }

    # -------------------------------------------------------------------------
    # Drawdown & Limit Surveillance (Section 8)
    # -------------------------------------------------------------------------
    def check_drawdown_and_limits(
        self,
        account_equity: float,
        current_unrealized_pnl: float
    ) -> Dict[str, Any]:
        """
        Evaluates daily and weekly drawdown limits, consecutive losses, and circuit breaker posture.
        """
        events: List[Dict[str, Any]] = []
        summary = get_performance_summary()
        stats = summary.get("stats", {})

        # PnL & Drawdowns from RiskManager and Journal
        cb_res = self.risk_manager.check_circuit_breaker(current_equity=account_equity)
        daily_pnl = float(getattr(self.risk_manager, "daily_pnl", 0.0) or 0.0)
        weekly_pnl = float(getattr(self.risk_manager, "weekly_pnl", 0.0) or 0.0)
        consecutive_losses = int(getattr(self.risk_manager, "consecutive_losses", 0) or 0)

        # Baseline equity for drawdown percentage
        start_equity = max(1.0, float(getattr(self.risk_manager, "start_of_day_equity", account_equity)))
        daily_drawdown_pct = max(0.0, -daily_pnl / start_equity * 100.0) if daily_pnl < 0 else 0.0

        week_start_equity = max(1.0, float(getattr(self.risk_manager, "start_of_week_equity", account_equity)))
        weekly_drawdown_pct = max(0.0, -weekly_pnl / week_start_equity * 100.0) if weekly_pnl < 0 else 0.0

        max_observed_dd = max(daily_drawdown_pct, weekly_drawdown_pct)

        # Check Thresholds
        if daily_drawdown_pct >= self.config["max_daily_drawdown_pct"]:
            msg = f"DAILY DRAWDOWN LIMIT BREACHED: {daily_drawdown_pct:.2f}% loss exceeds {self.config['max_daily_drawdown_pct']:.1f}% limit!"
            events.append({"event_type": "DAILY_DRAWDOWN_LIMIT_BREACH", "severity": "CRITICAL", "message": msg})

        if weekly_drawdown_pct >= self.config["max_weekly_drawdown_pct"]:
            msg = f"WEEKLY DRAWDOWN LIMIT BREACHED: {weekly_drawdown_pct:.2f}% loss exceeds {self.config['max_weekly_drawdown_pct']:.1f}% limit!"
            events.append({"event_type": "WEEKLY_DRAWDOWN_LIMIT_BREACH", "severity": "CRITICAL", "message": msg})

        if consecutive_losses >= self.config["max_consecutive_losses"]:
            msg = f"CONSECUTIVE LOSS LIMIT REACHED: {consecutive_losses} consecutive losses (max {self.config['max_consecutive_losses']})."
            events.append({"event_type": "CONSECUTIVE_LOSS_LIMIT_BREACH", "severity": "HIGH_RISK", "message": msg})

        return {
            "daily_pnl": daily_pnl,
            "weekly_pnl": weekly_pnl,
            "daily_drawdown_pct": daily_drawdown_pct,
            "weekly_drawdown_pct": weekly_drawdown_pct,
            "max_observed_drawdown_pct": max_observed_dd,
            "consecutive_losses": consecutive_losses,
            "circuit_breaker_active": not cb_res.get("can_trade", True),
            "events": events
        }

    # -------------------------------------------------------------------------
    # Telegram Alert Deduplication Engine (Section 10)
    # -------------------------------------------------------------------------
    def dispatch_telegram_alert(
        self,
        alert_type: str,
        symbol: str,
        severity: str,
        message: str,
        confirmed: bool = True
    ) -> bool:
        """
        Dispatches structured alert to Telegram with anti-spam cooldown deduplication.
        """
        now = time.time()
        alert_key = f"{alert_type}_{symbol}_{severity}"

        # Deduplication check
        last_sent = self._alert_history.get(alert_key, 0.0)
        cooldown = self.config["alert_cooldown_seconds"]
        if (now - last_sent) < cooldown and severity != "CRITICAL":
            logger.debug(f"PortfolioMonitor: Suppressing duplicate alert '{alert_key}' ({int(now - last_sent)}s < {cooldown}s)")
            return False

        self._alert_history[alert_key] = now

        # Format Telegram text
        icon = "🚨" if severity == "CRITICAL" else ("⚠️" if severity == "HIGH_RISK" else "ℹ️")
        conf_tag = "[EXCHANGE-CONFIRMED]" if confirmed else "[ESTIMATED / LOCAL]"
        timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        text = (
            f"{icon} **PORTFOLIO MONITOR ALERT [{severity}]**\n"
            f"**Type:** `{alert_type}`\n"
            f"**Target:** `{symbol}` | {conf_tag}\n"
            f"**Time:** `{timestamp_str}`\n\n"
            f"{message}"
        )

        logger.info(f"PortfolioMonitor: Dispatched Telegram alert: {alert_key}")

        # Send via configured Telegram instance if available
        if self.telegram:
            try:
                if hasattr(self.telegram, "send_message"):
                    self.telegram.send_message(text)
                elif hasattr(self.telegram, "notify_system_event"):
                    self.telegram.notify_system_event(text)
            except Exception as e:
                logger.error(f"PortfolioMonitor: Failed to send Telegram alert: {e}")

        return True

    # -------------------------------------------------------------------------
    # Order Hygiene: Stale Order Canceller (Preserved & Hardened)
    # -------------------------------------------------------------------------
    def cancel_stale_orders(self, max_age_seconds: int = 5400) -> List[Dict[str, Any]]:
        """
        Scan open orders and automatically cancel unfilled limit entry orders older than max_age_seconds (default 90m).
        Protects against stale fills after market structure has evolved.
        Does NOT cancel active child stop loss or take profit orders.
        """
        cancelled = []
        try:
            orders_res = self.client.get_open_orders()
            if not orders_res.get("success"):
                return cancelled

            open_orders = orders_res.get("result", []) or []
            now = time.time()

            for ord in open_orders:
                # Ignore active child bracket orders (SL/TP)
                s_type = str(ord.get("stop_order_type") or "").lower()
                o_type = str(ord.get("order_type") or "").lower()
                if "stop" in s_type or "stop" in o_type or "take_profit" in s_type:
                    continue

                # Check creation time
                created_str = ord.get("created_at")
                if not created_str:
                    continue

                age = self._parse_iso_age(created_str, now)
                if age > max_age_seconds:
                    oid = ord.get("id")
                    sym = ord.get("product_symbol") or ord.get("symbol")
                    logger.info(f"Cancelling stale unfilled entry order #{oid} on {sym} (age: {age/60:.1f}m)...")
                    c_res = self.client.cancel_order(symbol=sym, order_id=oid)
                    if c_res.get("success"):
                        cancelled.append({
                            "order_id": oid,
                            "symbol": sym,
                            "age_minutes": round(age / 60, 1),
                            "side": ord.get("side", ""),
                            "size": ord.get("size", 0),
                            "limit_price": ord.get("limit_price")
                        })
        except Exception as e:
            logger.error(f"Error checking stale orders: {e}")

        return cancelled

    # -------------------------------------------------------------------------
    # Memory Journaling & Daily Digest (Preserved & Enhanced)
    # -------------------------------------------------------------------------
    def journal_execution(
        self,
        execution_res: Dict[str, Any],
        approved_decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Record a newly executed trade into the persistent journal memory.
        """
        trade_id = execution_res.get("trade_id", f"trade_{int(time.time())}")
        symbol = approved_decision["symbol"]
        side = approved_decision["side"]
        contracts = approved_decision["contracts"]
        entry = approved_decision["entry_price"]
        sl = approved_decision["stop_loss_price"]
        tp = approved_decision["take_profit_price"]
        thesis = approved_decision.get("thesis", "Algorithmic momentum execution")
        strategy = approved_decision.get("strategy", "Delta_MultiAgent_Perpetual")

        journal_entry = record_trade_entry(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            contracts=contracts,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            thesis=thesis,
            strategy=strategy,
            agent_decision=approved_decision
        )

        logger.info(f"PortfolioMonitor: Trade {trade_id} ({symbol}) recorded to journal.")
        return journal_entry

    def generate_daily_digest(self) -> str:
        """
        Produce a clean Markdown performance digest inspired by claude-trading-skills.
        """
        ensure_reports_dir()
        summary = get_performance_summary()
        stats = summary.get("stats", {})
        pos_info = self.monitor_positions()

        today = time.strftime("%Y-%m-%d")
        report_filename = f"daily_digest_{today}.md"
        report_path = os.path.join(REPORTS_DIR, report_filename)

        content = [
            f"# Delta Exchange Daily Trading Digest — {today}",
            "",
            "## 1. Portfolio Health & Active Positions",
            f"- **Overall Status:** `{pos_info.get('overall_status', 'HEALTHY')}`",
            f"- **Account Equity:** `${pos_info.get('account_equity', 0.0):.2f}`",
            f"- **Margin Utilization:** `{pos_info.get('margin_utilization', 0.0):.1f}%` ({pos_info.get('margin_status', 'NORMAL')})",
            f"- **Total Open Exposure:** `${pos_info.get('total_open_exposure', 0.0):.2f}`",
            f"- **Total Unrealized PnL:** `${pos_info.get('total_unrealized_pnl_usd', 0.0):.2f}`",
            "",
            "| Symbol | Side | Contracts | Entry Price | Mark Price | Liq Distance | Unrealized PnL | Leverage | Protected |",
            "|---|---|---|---|---|---|---|---|---|"
        ]

        for p in pos_info.get("positions", []):
            mark_p_str = f"${p['current_mark_price']:.2f}" if p.get('current_mark_price') is not None else "UNKNOWN"
            liq_d_str = f"{p['liquidation_distance_pct']:.1f}%" if p.get('liquidation_distance_pct') is not None else "UNKNOWN"
            content.append(
                f"| {p['symbol']} | {p['side']} | {p['size']} | "
                f"${p['entry_price']:.2f} | {mark_p_str} | "
                f"{liq_d_str} | ${p['unrealized_pnl_usd']:.2f} | "
                f"{p['leverage']}x | {'YES' if pos_info.get('protective_order_status', {}).get('all_protected') else 'CHECK'} |"
            )

        if not pos_info.get("positions"):
            content.append("| No open positions | - | - | - | - | - | - | - | - |")

        content.extend([
            "",
            "## 2. Realized Performance Statistics (All-Time)",
            f"- **Total Closed Trades:** {stats.get('total_trades', 0)}",
            f"- **Winning Trades:** {stats.get('winning_trades', 0)}",
            f"- **Losing Trades:** {stats.get('losing_trades', 0)}",
            f"- **Win Rate:** `{stats.get('win_rate_pct', 0.0)}%`",
            f"- **Total Realized PnL:** `${stats.get('total_realized_pnl_usd', 0.0):.2f}`",
            "",
            "## 3. Pre-Trade Discipline Posture",
            "- All trade decisions passed Circuit Breaker and Pre-Trade Discipline Gates.",
            "- Minimum 2:1 Reward-to-Risk ratio and mandatory bracket stop-losses enforced.",
            ""
        ])

        report_text = "\n".join(content)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

        logger.info(f"PortfolioMonitor: Daily digest generated at {report_path}")
        return report_text

    # -------------------------------------------------------------------------
    # Internal Helpers & Fail-Closed Builder
    # -------------------------------------------------------------------------
    def _fetch_with_retry(self, fetch_fn, *args, **kwargs) -> Dict[str, Any]:
        """Executes an API call with bounded retries and exponential backoff."""
        max_retries = self.config["max_api_retries"]
        for attempt in range(max_retries + 1):
            try:
                res = fetch_fn(*args, **kwargs)
                if isinstance(res, dict) and res.get("success"):
                    return res
                if attempt == max_retries:
                    return res if isinstance(res, dict) else {"success": False, "error": str(res)}
            except Exception as e:
                if attempt == max_retries:
                    return {"success": False, "error": str(e)}
            time.sleep(0.15 * (2 ** attempt))
        return {"success": False, "error": "Max retries exceeded"}

    def _parse_wallet_metrics(
        self,
        balances: List[Dict[str, Any]],
        meta: Dict[str, Any]
    ) -> Tuple[float, float, float]:
        """Extracts account equity, available balance, and margin used."""
        total_usdt = 0.0
        avail_usdt = 0.0

        for b in balances:
            asset = str(b.get("asset_symbol", "")).upper()
            if asset in ("USDT", "USD"):
                bal = float(b.get("balance", 0.0) or 0.0)
                avail = float(b.get("available_balance", bal) if b.get("available_balance") is not None else bal)
                if bal > total_usdt:
                    total_usdt = bal
                    avail_usdt = avail

        # Check meta net equity fallback
        net_eq = float(meta.get("net_equity", 0.0) or 0.0)
        if net_eq > total_usdt:
            total_usdt = net_eq
            avail_usdt = max(avail_usdt, net_eq)

        margin_used = max(0.0, total_usdt - avail_usdt)
        return total_usdt, avail_usdt, margin_used

    def _get_local_position_record(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Queries StateManager SQLite database for open position record."""
        try:
            with self.state_manager._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM positions WHERE symbol=? AND status='OPEN' ORDER BY id DESC LIMIT 1", (symbol,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception:
            pass
        return None

    def _parse_iso_age(self, iso_str: Optional[str], now_ts: float) -> float:
        """Parses ISO timestamp string to age in seconds safely."""
        if not iso_str:
            return 0.0
        try:
            clean = iso_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            return max(0.0, now_ts - dt.timestamp())
        except Exception:
            return 0.0

    def _build_fail_closed_status(self, status: str, error_msg: str, now_ts: float) -> Dict[str, Any]:
        """Constructs safe fail-closed output when exchange connection fails."""
        return {
            "account_equity": self._last_state.get("account_equity", 0.0),
            "available_balance": self._last_state.get("available_balance", 0.0),
            "margin_used": self._last_state.get("margin_used", 0.0),
            "margin_utilization": self._last_state.get("margin_utilization", 0.0),
            "margin_status": "UNKNOWN",
            "total_open_exposure": self._last_state.get("total_open_exposure", 0.0),
            "long_exposure": self._last_state.get("long_exposure", 0.0),
            "short_exposure": self._last_state.get("short_exposure", 0.0),
            "net_directional_exposure": self._last_state.get("net_directional_exposure", 0.0),
            "gross_exposure": self._last_state.get("gross_exposure", 0.0),
            "total_open_risk": self._last_state.get("total_open_risk", 0.0),
            "remaining_portfolio_risk": self._last_state.get("remaining_portfolio_risk", 0.0),
            "daily_pnl": self._last_state.get("daily_pnl", 0.0),
            "weekly_pnl": self._last_state.get("weekly_pnl", 0.0),
            "daily_drawdown": self._last_state.get("daily_drawdown", 0.0),
            "weekly_drawdown": self._last_state.get("weekly_drawdown", 0.0),
            "max_observed_drawdown": self._last_state.get("max_observed_drawdown", 0.0),
            "consecutive_losses": self._last_state.get("consecutive_losses", 0),
            "open_positions": self._last_state.get("open_positions", []),
            "correlated_exposure": {},
            "liquidation_warnings": [],
            "protective_order_status": {"all_protected": False, "reason": "EXCHANGE_FEED_DISCONNECTED"},
            "exchange_sync_status": "UNKNOWN",
            "stale_data_status": {
                "is_stale": True,
                "error": error_msg,
                "last_poll_age_seconds": round(now_ts - self._last_successful_poll_ts, 1) if self._last_successful_poll_ts > 0 else 999.0
            },
            "risk_events": [{"event_type": "API_FAILURE", "severity": "CRITICAL", "message": error_msg}],
            "monitoring_timestamp": now_ts,
            "overall_status": status,

            # Backward compatibility keys:
            "active_count": self._last_state.get("active_count", 0),
            "total_unrealized_pnl_usd": self._last_state.get("total_unrealized_pnl_usd", 0.0),
            "positions": self._last_state.get("positions", [])
        }
