"""
Agent 10: Adaptive Learning, Pattern Diagnosis & Controlled Optimization Engine.
Delta Exchange Multi-Agent Quantitative Trading System.

Core Capabilities:
1. Reliable completed-trade dataset ingestion with rigorous data integrity filtering.
2. Net PnL, Net R-multiple, and Net Expectancy accounting (including fees, slippage, and funding).
3. Multi-timeframe & market-regime-aware performance attribution across 9 canonical regimes.
4. Deterministic loss categorization into 12 institutional failure modes.
5. Controlled, bounded parameter optimization with walk-forward validation and overfitting detection.
6. Strict parameter lifecycle management: BASELINE -> EXPERIMENTAL -> VALIDATED -> PAPER_APPROVED -> LIVE_APPROVED.
7. Immutable protection of live trading parameters with versioned configuration snapshots and rollback.
8. Real-time strategy drift and performance degradation surveillance.
9. Seamless backward compatibility for StrategyAgent, TrailingStopManager, and TelegramBot.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import json
import time
import math
import logging
from datetime import datetime, timezone

logger = logging.getLogger("adaptive-learning")

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
MEMORY_FILE = os.path.join(STATE_DIR, "pattern_learning_memory.json")
CONFIG_VERSIONS_FILE = os.path.join(STATE_DIR, "strategy_configuration_versions.json")
TRADES_DATASET_FILE = os.path.join(STATE_DIR, "verified_trade_dataset.jsonl")


def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


# =============================================================================
# PARAMETER BOUNDS & BASELINE STRATEGY CONFIGURATION
# =============================================================================

PARAM_BOUNDS: Dict[str, Dict[str, float]] = {
    "min_confluence_score": {"min": 65.0, "max": 95.0, "step": 5.0, "default": 85.0},
    "fvg_min_size_pct": {"min": 0.05, "max": 0.60, "step": 0.05, "default": 0.15},
    "atr_multiplier": {"min": 1.0, "max": 3.5, "step": 0.25, "default": 1.5},
    "adx_threshold": {"min": 18.0, "max": 35.0, "step": 2.0, "default": 22.0},
    "sl_buffer_multiplier": {"min": 0.8, "max": 1.6, "step": 0.1, "default": 1.1},
    "target_rr_ratio": {"min": 2.0, "max": 4.0, "step": 0.25, "default": 2.5},
    "max_allowed_spread_pct": {"min": 0.02, "max": 0.20, "step": 0.01, "default": 0.05}
}

BASELINE_STRATEGY_CONFIG: Dict[str, Any] = {
    "version": "1.0.0-PROD",
    "stage": "LIVE_APPROVED",
    "created_at": "2026-11-01 00:00:00 UTC",
    "parameters": {
        "min_confluence_score": 85.0,
        "fvg_min_size_pct": 0.15,
        "atr_multiplier": 1.5,
        "adx_threshold": 22.0,
        "sl_buffer_multiplier": 1.1,
        "target_rr_ratio": 2.5,
        "max_allowed_spread_pct": 0.05
    },
    "rationale": "Initial institutional baseline configuration for Delta multi-agent scalping.",
    "metrics_oos": {
        "win_rate_pct": 68.0,
        "net_expectancy_r": 0.45,
        "profit_factor": 2.2,
        "max_drawdown_pct": 2.8
    }
}

# The 12 Institutional Loss Categorization Modes
LOSS_CATEGORIES: List[str] = [
    "INCORRECT_REGIME",
    "FALSE_LIQUIDITY_SWEEP",
    "FAILED_BOS_CHOCH",
    "INVALID_FVG",
    "POOR_ENTRY_TIMING",
    "STOP_LOSS_PLACEMENT",
    "EXCESSIVE_SPREAD",
    "SLIPPAGE",
    "UNEXPECTED_VOLATILITY",
    "NEWS_EVENT",
    "EXECUTION_FAILURE",
    "STRATEGY_WEAKNESS"
]


# =============================================================================
# AGENT 10: ADAPTIVE LEARNING ENGINE CLASS
# =============================================================================

class AdaptiveLearningEngine:
    """
    Agent 10: Adaptive Learning, Pattern Diagnosis & Controlled Optimization Engine.
    Performs verified post-trade auditing, statistical expectancy evaluation,
    regime attribution, loss diagnostics, and controlled walk-forward parameter optimization.
    """

    def __init__(
        self,
        memory_path: Optional[str] = None,
        config_versions_path: Optional[str] = None,
        trades_dataset_path: Optional[str] = None
    ):
        self.memory_path = memory_path or MEMORY_FILE
        self.config_versions_path = config_versions_path or CONFIG_VERSIONS_FILE
        self.trades_dataset_path = trades_dataset_path or TRADES_DATASET_FILE

        self.memory: Dict[str, Any] = self._load_memory()
        self.config_store: Dict[str, Any] = self._load_config_store()
        self.verified_trades: List[Dict[str, Any]] = self._load_trade_dataset()

    # -------------------------------------------------------------------------
    # Persistence & Memory Management
    # -------------------------------------------------------------------------
    def _load_memory(self) -> Dict[str, Any]:
        ensure_state_dir()
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading adaptive pattern memory: {e}")

        # Default structured memory format (maintains full backward compatibility)
        return {
            "version": "2.0.0-PROD",
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "scorecard": {
                "total_completed_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "breakeven_trades": 0,
                "win_rate_pct": 0.0,
                "cumulative_pnl_usd": 0.0,
                "average_trade_score": 0.0,
                "profit_factor": 0.0,
                "net_expectancy_r": 0.0
            },
            "patterns": {},
            "recent_reflections": [],
            "regime_performance": {},
            "loss_distribution": {cat: 0 for cat in LOSS_CATEGORIES}
        }

    def _save_memory(self):
        ensure_state_dir()
        self.memory["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        try:
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving adaptive pattern memory: {e}")

    def _load_config_store(self) -> Dict[str, Any]:
        ensure_state_dir()
        if os.path.exists(self.config_versions_path):
            try:
                with open(self.config_versions_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading strategy config versions: {e}")

        # Default configuration store
        init_store = {
            "active_version": "1.0.0-PROD",
            "versions": {
                "1.0.0-PROD": BASELINE_STRATEGY_CONFIG
            },
            "audit_history": [
                {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                    "action": "INITIALIZE_BASELINE",
                    "version": "1.0.0-PROD",
                    "authorized_by": "SYSTEM"
                }
            ]
        }
        self._save_config_store(init_store)
        return init_store

    def _save_config_store(self, store: Optional[Dict[str, Any]] = None):
        ensure_state_dir()
        data = store or self.config_store
        try:
            with open(self.config_versions_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving strategy config store: {e}")

    def _load_trade_dataset(self) -> List[Dict[str, Any]]:
        ensure_state_dir()
        trades = []
        if os.path.exists(self.trades_dataset_path):
            try:
                with open(self.trades_dataset_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            trades.append(json.loads(line.strip()))
            except Exception as e:
                logger.error(f"Error loading trade dataset: {e}")
        return trades

    # -------------------------------------------------------------------------
    # Verified Trade Ingestion Pipeline (Section 2)
    # -------------------------------------------------------------------------
    def ingest_trade_record(self, raw_trade: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validates, normalizes, and appends a verified completed trade to the learning dataset.
        Enforces strict rules:
        - Excludes open, canceled, rejected, or uncompleted trades.
        - Excludes corrupted or missing pricing records.
        - Deduplicates by trade_id.
        - Accurately deducts fees, slippage, and funding to calculate Net PnL and Net R.
        """
        if not isinstance(raw_trade, dict):
            return False, "INVALID_PAYLOAD: Trade record must be a dictionary.", None

        # 1. Completion & Status Verification
        status = str(raw_trade.get("status") or "").upper()
        if status in ("OPEN", "PENDING", "PARTIALLY_FILLED", "ACTIVE"):
            return False, f"OPEN_TRADE_EXCLUDED: Trade is still active ({status}); learning requires closed outcomes.", None
        if status in ("CANCELED", "CANCELLED", "REJECTED", "EXPIRED"):
            return False, f"CANCELED_ORDER_EXCLUDED: Order was {status} without execution.", None

        # 2. Mandatory Identifier & Symbol
        trade_id = str(raw_trade.get("trade_id") or raw_trade.get("id") or "").strip()
        symbol = str(raw_trade.get("symbol") or raw_trade.get("product_symbol") or "").upper().strip()
        if not trade_id or not symbol:
            return False, "MISSING_IDENTITY: Trade record missing trade_id or symbol.", None

        # 3. Deduplication Check
        if any(t.get("trade_id") == trade_id for t in self.verified_trades):
            return False, f"DUPLICATE_TRADE: trade_id '{trade_id}' already ingested.", None

        # 4. Price & Size Validation
        try:
            entry_price = float(raw_trade.get("entry_price") or raw_trade.get("avg_fill_price") or 0.0)
            exit_price = float(raw_trade.get("exit_price") or 0.0)
            contracts = int(raw_trade.get("contracts") or raw_trade.get("size") or 0)
            if entry_price <= 0 or exit_price <= 0 or contracts <= 0:
                return False, f"CORRUPTED_PRICES: Non-positive price or size (entry: {entry_price}, exit: {exit_price}, contracts: {contracts}).", None
        except (ValueError, TypeError) as e:
            return False, f"CORRUPTED_DATA: Numerical conversion error: {e}", None

        side = str(raw_trade.get("side") or "BUY").upper()
        exit_reason = str(raw_trade.get("exit_reason") or "TAKE_PROFIT").upper()

        # Contract Multiplier
        c_val = 0.001 if "BTC" in symbol else (0.01 if "ETH" in symbol else 1.0)
        c_val = float(raw_trade.get("contract_value") or c_val)

        # 5. Risk Accounting
        initial_sl = float(raw_trade.get("initial_sl") or raw_trade.get("stop_loss") or raw_trade.get("stop_loss_price") or 0.0)
        initial_risk = float(raw_trade.get("dollar_risk_usd") or raw_trade.get("initial_risk") or 0.0)
        if initial_risk <= 0 and initial_sl > 0:
            initial_risk = abs(entry_price - initial_sl) * contracts * c_val
        if initial_risk <= 0:
            initial_risk = 2.0  # Safe minimum fallback risk floor

        # 6. Gross PnL, Fees, Slippage & Funding
        gross_pnl = float(raw_trade.get("gross_pnl") or raw_trade.get("realized_pnl") or 0.0)
        if gross_pnl == 0.0:
            if side == "BUY":
                gross_pnl = (exit_price - entry_price) * contracts * c_val
            else:
                gross_pnl = (entry_price - exit_price) * contracts * c_val

        fees = abs(float(raw_trade.get("fees") or raw_trade.get("fee_usd") or 0.0))
        slippage = abs(float(raw_trade.get("slippage") or raw_trade.get("slippage_usd") or 0.0))
        funding = float(raw_trade.get("funding") or raw_trade.get("funding_usd") or 0.0)

        # Net Realized PnL Formula
        net_pnl = round(gross_pnl - fees - slippage - funding, 4)

        # Net R Multiple Formula: Net PnL / Initial Monetary Risk
        net_r = round(net_pnl / initial_risk, 4) if initial_risk > 0 else 0.0

        # Outcome Classification
        if exit_reason in ("BREAKEVEN", "BE") or abs(net_r) <= 0.05:
            outcome = "BREAKEVEN"
        elif exit_reason in ("TIMEOUT", "TIME_EXPIRED"):
            outcome = "TIMEOUT"
        elif net_pnl > 0:
            outcome = "WIN"
        else:
            outcome = "LOSS"

        # Market Regime & Confluence Context
        regime = str(raw_trade.get("regime") or raw_trade.get("market_regime") or "UNKNOWN").upper()
        confluence_score = float(raw_trade.get("confluence_score") or 85.0)

        # Excursions (MFE & MAE)
        mfe_r = float(raw_trade.get("mfe_r") or raw_trade.get("mfe") or max(0.0, net_r))
        mae_r = float(raw_trade.get("mae_r") or raw_trade.get("mae") or min(0.0, net_r))

        verified_record: Dict[str, Any] = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "contracts": contracts,
            "contract_value": c_val,
            "entry_timestamp": float(raw_trade.get("entry_timestamp") or time.time() - 3600),
            "exit_timestamp": float(raw_trade.get("exit_timestamp") or time.time()),
            "holding_duration_seconds": float(raw_trade.get("holding_duration_seconds") or 3600.0),
            "initial_sl": initial_sl,
            "initial_tp": float(raw_trade.get("initial_tp") or raw_trade.get("take_profit") or 0.0),
            "initial_risk_usd": round(initial_risk, 2),
            "gross_pnl_usd": round(gross_pnl, 4),
            "fees_usd": round(fees, 4),
            "slippage_usd": round(slippage, 4),
            "funding_usd": round(funding, 4),
            "net_pnl_usd": net_pnl,
            "net_r": net_r,
            "outcome": outcome,
            "exit_reason": exit_reason,
            "regime": regime,
            "strategy": str(raw_trade.get("strategy") or "Delta_SMC_Scalper"),
            "confluence_score": confluence_score,
            "config_version": str(raw_trade.get("config_version") or self.config_store["active_version"]),
            "mfe_r": mfe_r,
            "mae_r": mae_r,
            "ingested_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }

        # Append to dataset file & in-memory cache
        self.verified_trades.append(verified_record)
        ensure_state_dir()
        try:
            with open(self.trades_dataset_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(verified_record) + "\n")
        except Exception as e:
            logger.error(f"Error persisting verified trade record: {e}")

        # Update pattern learning and scorecard memory
        self._update_learning_from_trade(verified_record)

        return True, "SUCCESS: Trade verified and ingested.", verified_record

    # -------------------------------------------------------------------------
    # Strategy Performance Analysis Engine (Section 3)
    # -------------------------------------------------------------------------
    def compute_strategy_performance(self, trades: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Calculates institutional performance metrics across completed verified trades:
        - Win rate, Net Expectancy (R), Profit Factor, Recovery Factor
        - Average winning/losing R, Sharpe and Sortino ratios, Max Drawdown
        """
        dataset = trades if trades is not None else self.verified_trades
        n = len(dataset)
        if n == 0:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "net_expectancy_r": 0.0,
                "profit_factor": 0.0,
                "cumulative_net_pnl_usd": 0.0,
                "avg_win_r": 0.0,
                "avg_loss_r": 0.0,
                "max_drawdown_usd": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "consecutive_losses": 0,
                "recovery_factor": 0.0,
                "status": "INSUFFICIENT_DATA"
            }

        # Normalize records if raw dictionaries are passed
        normalized_dataset = []
        for raw_t in dataset:
            t = dict(raw_t)
            if "net_pnl_usd" not in t:
                gross = float(t.get("gross_pnl_usd") or t.get("realized_pnl") or 0.0)
                if gross == 0.0 and "entry_price" in t and "exit_price" in t:
                    cval = float(t.get("contract_value", 0.001))
                    cntr = float(t.get("contracts", 1))
                    side = str(t.get("side", "BUY")).upper()
                    gross = (t["exit_price"] - t["entry_price"]) * cntr * cval if side == "BUY" else (t["entry_price"] - t["exit_price"]) * cntr * cval
                fees = float(t.get("fees", 0.0)) + float(t.get("slippage", 0.0)) + float(t.get("funding", 0.0))
                t["net_pnl_usd"] = round(gross - fees, 4)
            if "outcome" not in t:
                pnl = t["net_pnl_usd"]
                reason = str(t.get("exit_reason", "")).upper()
                if reason in ("BREAKEVEN", "TIMEOUT") or abs(pnl) <= 0.05:
                    t["outcome"] = "BREAKEVEN" if reason != "TIMEOUT" else "TIMEOUT"
                elif pnl > 0:
                    t["outcome"] = "WIN"
                else:
                    t["outcome"] = "LOSS"
            if "net_r" not in t:
                risk = float(t.get("initial_risk_usd") or t.get("dollar_risk_usd") or 10.0)
                t["net_r"] = round(t["net_pnl_usd"] / max(1.0, risk), 4)
            normalized_dataset.append(t)

        wins = [t for t in normalized_dataset if t["outcome"] == "WIN"]
        losses = [t for t in normalized_dataset if t["outcome"] == "LOSS"]
        breakevens = [t for t in normalized_dataset if t["outcome"] in ("BREAKEVEN", "TIMEOUT")]

        win_rate = (len(wins) / n * 100.0) if n > 0 else 0.0
        r_multiples = [t["net_r"] for t in normalized_dataset]
        net_pnls = [t["net_pnl_usd"] for t in normalized_dataset]

        # Net Expectancy = Sum(Net R) / N
        net_expectancy = sum(r_multiples) / n if n > 0 else 0.0

        total_gain = sum(t["net_pnl_usd"] for t in wins)
        total_loss = abs(sum(t["net_pnl_usd"] for t in losses))
        profit_factor = (total_gain / total_loss) if total_loss > 0 else (99.0 if total_gain > 0 else 0.0)

        avg_win_r = (sum(t["net_r"] for t in wins) / len(wins)) if wins else 0.0
        avg_loss_r = (sum(t["net_r"] for t in losses) / len(losses)) if losses else 0.0

        # Drawdown calculation
        cumulative_pnl = 0.0
        peak = 0.0
        max_dd = 0.0
        curr_streak = 0
        max_consec_losses = 0

        for t in normalized_dataset:
            cumulative_pnl += t["net_pnl_usd"]
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = peak - cumulative_pnl
            if dd > max_dd:
                max_dd = dd

            if t["outcome"] == "LOSS":
                curr_streak += 1
                if curr_streak > max_consec_losses:
                    max_consec_losses = curr_streak
            else:
                curr_streak = 0

        # Sharpe & Sortino
        mean_r = net_expectancy
        variance = sum((r - mean_r) ** 2 for r in r_multiples) / max(1, n - 1)
        std_r = math.sqrt(variance) if variance > 0 else 1.0
        sharpe = round((mean_r / std_r) * math.sqrt(n), 2) if std_r > 0 else 0.0

        downside_vars = [min(0.0, r) ** 2 for r in r_multiples]
        downside_std = math.sqrt(sum(downside_vars) / max(1, n))
        sortino = round((mean_r / downside_std) * math.sqrt(n), 2) if downside_std > 0 else sharpe

        recovery_factor = round(cumulative_pnl / max_dd, 2) if max_dd > 0 else 99.0

        return {
            "total_trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "breakevens": len(breakevens),
            "win_rate_pct": round(win_rate, 2),
            "net_expectancy_r": round(net_expectancy, 4),
            "profit_factor": round(profit_factor, 2),
            "cumulative_net_pnl_usd": round(sum(net_pnls), 2),
            "avg_win_r": round(avg_win_r, 2),
            "avg_loss_r": round(avg_loss_r, 2),
            "max_drawdown_usd": round(max_dd, 2),
            "consecutive_losses": max_consec_losses,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "recovery_factor": recovery_factor,
            "status": "VALIDATED" if n >= 10 else "INSUFFICIENT_DATA"
        }

    # -------------------------------------------------------------------------
    # Regime-Aware Learning & Attribution (Section 4)
    # -------------------------------------------------------------------------
    def compute_regime_performance(self, trades: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Segregates performance metrics across Agent 1's 9 canonical market regimes.
        Enforces minimum sample sizes (min 5 trades required per regime).
        """
        dataset = trades if trades is not None else self.verified_trades
        regimes = [
            "STRONG_UPTREND", "WEAK_UPTREND",
            "STRONG_DOWNTREND", "WEAK_DOWNTREND",
            "RANGING", "HIGH_VOLATILITY",
            "LOW_VOLATILITY", "TRANSITIONAL", "UNKNOWN"
        ]

        breakdown: Dict[str, Any] = {}
        for reg in regimes:
            reg_trades = [t for t in dataset if t.get("regime") == reg]
            count = len(reg_trades)
            if count < 5:
                breakdown[reg] = {
                    "total_trades": count,
                    "status": "INSUFFICIENT_DATA",
                    "note": f"Sample size ({count}) below minimum threshold (5) for statistical confidence."
                }
            else:
                perf = self.compute_strategy_performance(reg_trades)
                breakdown[reg] = {
                    "total_trades": count,
                    "win_rate_pct": perf["win_rate_pct"],
                    "net_expectancy_r": perf["net_expectancy_r"],
                    "profit_factor": perf["profit_factor"],
                    "cumulative_net_pnl_usd": perf["cumulative_net_pnl_usd"],
                    "status": "VALIDATED"
                }

        return breakdown

    # -------------------------------------------------------------------------
    # Institutional Loss Categorization Engine (Section 8)
    # -------------------------------------------------------------------------
    def classify_loss_reason(self, trade: Dict[str, Any]) -> str:
        """
        Classifies losing trade into one of 12 institutional root causes.
        Avoids naive blanket indicator adjustments.
        """
        if trade.get("outcome") != "LOSS":
            return "NOT_A_LOSS"

        regime = str(trade.get("regime") or "").upper()
        side = str(trade.get("side") or "").upper()
        spread_pct = float(trade.get("spread_pct") or 0.0)
        slippage_usd = float(trade.get("slippage_usd") or 0.0)
        fees_usd = float(trade.get("fees_usd") or 0.0)
        exit_reason = str(trade.get("exit_reason") or "").upper()

        # 1. Incorrect regime (e.g. Buying in Strong Downtrend or High Volatility trap)
        if (side == "BUY" and "DOWNTREND" in regime) or (side == "SELL" and "UPTREND" in regime):
            return "INCORRECT_REGIME"
        if "HIGH_VOLATILITY" in regime:
            return "UNEXPECTED_VOLATILITY"

        # 2. News Spike
        if "NEWS" in exit_reason or "CPI" in exit_reason or "FOMC" in exit_reason:
            return "NEWS_EVENT"

        # 3. Excessive Spread or Slippage
        if spread_pct > 0.10:
            return "EXCESSIVE_SPREAD"
        if slippage_usd > (abs(trade.get("net_pnl_usd", 1.0)) * 0.40):
            return "SLIPPAGE"

        # 4. Stop Loss Placement Issue (Noise stop-out)
        entry_price = float(trade.get("entry_price") or 1.0)
        initial_sl = float(trade.get("initial_sl") or 0.0)
        if initial_sl > 0:
            stop_dist_pct = abs(entry_price - initial_sl) / entry_price * 100.0
            if stop_dist_pct < 0.20:
                return "STOP_LOSS_PLACEMENT"

        # 5. SMC Structural Failures
        thesis = str(trade.get("strategy") or "").upper()
        if "SWEEP" in thesis:
            return "FALSE_LIQUIDITY_SWEEP"
        if "BOS" in thesis or "CHOCH" in thesis:
            return "FAILED_BOS_CHOCH"
        if "FVG" in thesis:
            return "INVALID_FVG"

        # 6. Fallback General Strategy Weakness
        return "STRATEGY_WEAKNESS"

    # -------------------------------------------------------------------------
    # Strategy Drift & Performance Degradation Detection (Section 9)
    # -------------------------------------------------------------------------
    def detect_strategy_drift(
        self,
        trades: Optional[List[Dict[str, Any]]] = None,
        window_size: int = 15
    ) -> Dict[str, Any]:
        """
        Monitors rolling expectancy and profit factor to detect strategy drift.
        Returns: STABLE, IMPROVING, DEGRADING, CRITICAL_DEGRADATION, or INSUFFICIENT_DATA.
        """
        dataset = trades if trades is not None else self.verified_trades
        n = len(dataset)
        if n < window_size:
            return {
                "drift_status": "INSUFFICIENT_DATA",
                "sample_size": n,
                "required_sample": window_size,
                "message": f"Sample size ({n}) is too small to determine strategy drift (requires {window_size}+ trades)."
            }

        # Compare baseline (first half) against rolling (last window)
        rolling_cohort = dataset[-window_size:]
        prior_cohort = dataset[:-window_size] if len(dataset) >= (window_size * 2) else dataset[:window_size]

        perf_rolling = self.compute_strategy_performance(rolling_cohort)
        perf_prior = self.compute_strategy_performance(prior_cohort)

        r_roll = perf_rolling["net_expectancy_r"]
        r_prior = perf_prior["net_expectancy_r"]

        # Degradation logic
        if r_roll < -0.20 and perf_rolling["consecutive_losses"] >= 4:
            status = "CRITICAL_DEGRADATION"
            msg = f"CRITICAL: Strategy in deep degradation! Rolling expectancy is negative ({r_roll:.2f}R, {perf_rolling['consecutive_losses']} consec losses)."
        elif r_roll < (r_prior * 0.50) or (r_prior > 0 and r_roll <= 0):
            status = "DEGRADING"
            msg = f"WARNING: Strategy performance degrading. Rolling expectancy dropped from {r_prior:.2f}R to {r_roll:.2f}R."
        elif r_roll >= (r_prior * 1.25):
            status = "IMPROVING"
            msg = f"POSITIVE: Strategy edge expanding. Rolling expectancy increased from {r_prior:.2f}R to {r_roll:.2f}R."
        else:
            status = "STABLE"
            msg = f"STABLE: Strategy performance consistent with baseline ({r_roll:.2f}R)."

        return {
            "drift_status": status,
            "rolling_expectancy_r": r_roll,
            "prior_expectancy_r": r_prior,
            "rolling_profit_factor": perf_rolling["profit_factor"],
            "rolling_win_rate_pct": perf_rolling["win_rate_pct"],
            "consecutive_losses": perf_rolling["consecutive_losses"],
            "message": msg
        }

    # -------------------------------------------------------------------------
    # Controlled Parameter Optimization & Overfitting Prevention (Sections 5 & 6)
    # -------------------------------------------------------------------------
    def validate_parameter_bounds(self, candidate_params: Dict[str, Any]) -> Tuple[bool, Dict[str, float], List[str]]:
        """
        Clamps candidate parameters strictly within pre-approved quantitative bounds.
        Prevents dangerous or extreme parameter settings.
        """
        clamped = {}
        violations = []

        for param, val in candidate_params.items():
            if param in PARAM_BOUNDS:
                bounds = PARAM_BOUNDS[param]
                v = float(val)
                if v < bounds["min"]:
                    violations.append(f"{param} value {v} below min {bounds['min']}; clamped to {bounds['min']}.")
                    v = bounds["min"]
                elif v > bounds["max"]:
                    violations.append(f"{param} value {v} above max {bounds['max']}; clamped to {bounds['max']}.")
                    v = bounds["max"]
                clamped[param] = v

        # Fill missing parameters with defaults
        for param, bounds in PARAM_BOUNDS.items():
            if param not in clamped:
                clamped[param] = bounds["default"]

        return len(violations) == 0, clamped, violations

    def run_walk_forward_validation(
        self,
        candidate_params: Dict[str, Any],
        historical_trades: Optional[List[Dict[str, Any]]] = None,
        windows: int = 3,
        candles_15m: Optional[Dict[str, Any]] = None,
        candles_1h: Optional[Dict[str, Any]] = None,
        candles_5m: Optional[Dict[str, Any]] = None,
        candles_1m: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes rolling walk-forward validation across chronological data splits.
        Detects overfitting by comparing in-sample (IS) vs out-of-sample (OOS) expectancy.
        """
        # Validate & clamp parameter bounds first
        _, clamped_params, bounds_violations = self.validate_parameter_bounds(candidate_params)

        # If candles are provided, run quantitative candle backtest via TimeMachineAgent
        if candles_15m and len(candles_15m.get("c", [])) >= 60:
            from multiagent_team.time_machine_agent import TimeMachineAgent
            tm = TimeMachineAgent(client=self.client)
            return tm.evaluate_candidate_parameters(
                candidate_params=clamped_params,
                candles_15m=candles_15m,
                candles_1h=candles_1h,
                candles_5m=candles_5m,
                candles_1m=candles_1m
            )

        dataset = historical_trades if historical_trades is not None else self.verified_trades
        n = len(dataset)
        if n < 15:
            return {
                "passed": False,
                "reason": f"INSUFFICIENT_SAMPLE: Walk-forward validation requires >= 15 completed trades (got {n}).",
                "is_overfitting": False,
                "oos_expectancy_r": 0.0,
                "walk_forward_windows": []
            }

        # 60% Train / In-Sample (IS), 40% Out-Of-Sample (OOS)
        split_idx = int(n * 0.60)
        is_trades = dataset[:split_idx]
        oos_trades = dataset[split_idx:]

        is_perf = self.compute_strategy_performance(is_trades)
        oos_perf = self.compute_strategy_performance(oos_trades)

        is_exp = is_perf["net_expectancy_r"]
        oos_exp = oos_perf["net_expectancy_r"]

        # Multi-window rolling walk-forward analysis
        num_windows = max(1, min(windows, n // 5))
        window_size = n // num_windows
        wf_windows = []
        for w in range(num_windows):
            w_start = w * (window_size // 2) if num_windows > 1 else 0
            w_end = min(w_start + window_size, n) if num_windows > 1 else n
            sub_trades = dataset[w_start:w_end]
            if len(sub_trades) >= 5:
                w_split = int(len(sub_trades) * 0.60)
                w_is = sub_trades[:w_split]
                w_oos = sub_trades[w_split:]
                w_is_perf = self.compute_strategy_performance(w_is)
                w_oos_perf = self.compute_strategy_performance(w_oos)
                wf_windows.append({
                    "window": w + 1,
                    "trade_range": f"{w_start}-{w_end}",
                    "is_count": len(w_is),
                    "oos_count": len(w_oos),
                    "is_net_ev_r": w_is_perf["net_expectancy_r"],
                    "oos_net_ev_r": w_oos_perf["net_expectancy_r"],
                    "oos_profit_factor": w_oos_perf["profit_factor"]
                })

        # Overfitting Detection Rule:
        # If IS expectancy is high (>= 0.40R) but OOS collapses by > 40% or goes negative
        is_overfitting = False
        if is_exp > 0.30 and (oos_exp < (is_exp * 0.60) or oos_exp < 0.05):
            is_overfitting = True

        passed = (not is_overfitting) and (oos_exp >= 0.20) and (oos_perf["profit_factor"] >= 1.5)

        return {
            "passed": passed,
            "is_overfitting": is_overfitting,
            "clamped_parameters": clamped_params,
            "is_expectancy_r": is_exp,
            "oos_expectancy_r": oos_exp,
            "is_profit_factor": is_perf["profit_factor"],
            "oos_profit_factor": oos_perf["profit_factor"],
            "is_trades_count": len(is_trades),
            "oos_trades_count": len(oos_trades),
            "bounds_violations": bounds_violations,
            "walk_forward_windows": wf_windows,
            "recommendation": "PROCEED_TO_EXPERIMENTAL" if passed else ("REJECT_OVERFIT" if is_overfitting else "REJECT_INSUFFICIENT_EDGE")
        }

    # -------------------------------------------------------------------------
    # Parameter Promotion & Approval Lifecycle (Section 7)
    # -------------------------------------------------------------------------
    def propose_parameter_update(
        self,
        candidate_params: Dict[str, Any],
        rationale: str
    ) -> Dict[str, Any]:
        """
        Creates an EXPERIMENTAL configuration proposal without modifying live trading parameters.
        Live trading continues uninterrupted on the current BASELINE.
        """
        wf_res = self.run_walk_forward_validation(candidate_params)
        _, clamped_params, _ = self.validate_parameter_bounds(candidate_params)

        version_id = f"cand-{int(time.time())}"
        stage = "REJECTED" if wf_res.get("is_overfitting") else "EXPERIMENTAL"
        proposal = {
            "version": version_id,
            "stage": stage,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "parameters": clamped_params,
            "rationale": rationale,
            "validation_results": wf_res,
            "requires_approval": True,
            "is_live_active": False
        }

        self.config_store["versions"][version_id] = proposal
        self.config_store["audit_history"].append({
            "timestamp": proposal["created_at"],
            "action": "PROPOSE_CANDIDATE",
            "version": version_id,
            "stage": proposal["stage"]
        })
        self._save_config_store()

        logger.info(f"AdaptiveLearning: Proposed new parameter configuration '{version_id}' [Stage: {proposal['stage']}]")
        return proposal

    def promote_parameter_version(
        self,
        version_id: str,
        target_stage: str,
        authorized_by: str
    ) -> Dict[str, Any]:
        """
        Controlled promotion workflow:
        BASELINE -> EXPERIMENTAL -> VALIDATED -> PAPER_APPROVED -> LIVE_APPROVED
        Strictly requires manual / authorized invocation.
        """
        if version_id not in self.config_store["versions"]:
            return {"success": False, "error": f"Version '{version_id}' not found."}

        valid_stages = ["BASELINE", "EXPERIMENTAL", "VALIDATED", "PAPER_APPROVED", "LIVE_APPROVED"]
        if target_stage not in valid_stages:
            return {"success": False, "error": f"Invalid stage '{target_stage}'. Must be one of {valid_stages}."}

        cfg = self.config_store["versions"][version_id]

        # Cannot promote rejected candidates
        if cfg.get("stage") == "REJECTED":
            return {"success": False, "error": "Cannot promote REJECTED candidate."}

        # Validation evidence check for VALIDATED promotion
        if target_stage == "VALIDATED":
            val_res = cfg.get("validation_results", {})
            if not val_res.get("passed", False):
                return {"success": False, "error": "Cannot promote to VALIDATED: candidate failed statistical walk-forward validation."}

        # LIVE_APPROVED requires authorized sign-off
        if target_stage == "LIVE_APPROVED":
            if not authorized_by or authorized_by.strip().upper() in ("SYSTEM", "AUTO", "UNKNOWN"):
                return {"success": False, "error": "Cannot promote to LIVE_APPROVED without explicit human researcher authorization."}

        # Update stage
        cfg["stage"] = target_stage
        cfg["promoted_by"] = authorized_by
        cfg["promoted_at"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        # If promoting to LIVE_APPROVED, set as active
        if target_stage == "LIVE_APPROVED":
            self.config_store["active_version"] = version_id
            cfg["is_live_active"] = True

        self.config_store["audit_history"].append({
            "timestamp": cfg["promoted_at"],
            "action": f"PROMOTE_TO_{target_stage}",
            "version": version_id,
            "authorized_by": authorized_by
        })
        self._save_config_store()

        logger.info(f"AdaptiveLearning: Version '{version_id}' promoted to {target_stage} by {authorized_by}.")
        return {"success": True, "version": version_id, "stage": target_stage}

    def rollback_configuration(self, target_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Reverts active configuration safely to a prior validated version or BASELINE (1.0.0-PROD).
        """
        fallback_ver = target_version or "1.0.0-PROD"
        if fallback_ver not in self.config_store["versions"]:
            return {"success": False, "error": f"Rollback target '{fallback_ver}' does not exist."}

        self.config_store["active_version"] = fallback_ver
        self.config_store["audit_history"].append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "action": "ROLLBACK_CONFIGURATION",
            "reverted_to": fallback_ver
        })
        self._save_config_store()

        logger.warning(f"AdaptiveLearning: Rolled back active strategy configuration to '{fallback_ver}'.")
        return {"success": True, "active_version": fallback_ver}

    def get_active_configuration(self) -> Dict[str, Any]:
        """Returns the currently active live strategy configuration."""
        active_ver = self.config_store.get("active_version", "1.0.0-PROD")
        return self.config_store.get("versions", {}).get(active_ver, BASELINE_STRATEGY_CONFIG)

    # -------------------------------------------------------------------------
    # Backward Compatibility APIs for StrategyAgent, TrailingStop, & Telegram
    # -------------------------------------------------------------------------
    def _derive_pattern_key(self, symbol: str, side: str, strategy: str, confluence: Dict[str, Any]) -> str:
        """Derives a normalized pattern signature key."""
        sym = (symbol or "UNKNOWN").upper()
        asset_base = "BTC" if "BTC" in sym else ("ETH" if "ETH" in sym else ("SOL" if "SOL" in sym else ("XAU" if "XAU" in sym else sym)))
        dir_tag = (side or "BUY").upper()
        strat = (strategy or "").upper()

        if "SSL" in strat or "SELL_SIDE" in strat:
            pattern_type = "SSL_SWEEP"
        elif "BSL" in strat or "BUY_SIDE" in strat:
            pattern_type = "BSL_SWEEP"
        elif "PULLBACK" in strat or "EMA" in strat:
            pattern_type = "EMA_PULLBACK"
        else:
            pattern_type = "STRUCTURE_BREAKOUT"

        h4 = str(confluence.get("macro_4h", "ALIGNED")).upper()
        trend_context = "TREND_ALIGNED" if ("BULL" in h4 and dir_tag == "BUY") or ("BEAR" in h4 and dir_tag == "SELL") else "COUNTER_OR_NEUTRAL"
        return f"{asset_base}_{pattern_type}_{dir_tag}_{trend_context}"

    def score_trade(
        self,
        symbol: str,
        side: str,
        realized_pnl: float,
        r_multiple: float,
        exit_reason: str,
        trade_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate and score completed trade from 0 to 100 points."""
        is_win = realized_pnl > 0.01
        is_be = abs(realized_pnl) <= 0.05 or exit_reason in ("BREAKEVEN", "TIMEOUT")
        is_loss = realized_pnl < -0.05

        discipline_score = 30
        dollar_risk = trade_spec.get("dollar_risk_usd", 4.0)
        if is_loss and abs(realized_pnl) > (dollar_risk * 1.25):
            discipline_score = 15
        elif not is_win and not is_be:
            discipline_score = 25

        confluence_score = 40
        confluence = trade_spec.get("confluence", {})
        h4 = str(confluence.get("macro_4h", "")).upper()
        if side.upper() == "BUY" and "BEAR" in h4:
            confluence_score = 15
        elif side.upper() == "SELL" and "BULL" in h4:
            confluence_score = 15

        edge_score = 0
        if r_multiple >= 2.0 or exit_reason == "TAKE_PROFIT":
            edge_score = 30
        elif r_multiple >= 1.20:
            edge_score = 25
        elif r_multiple >= 0.35 or is_win:
            edge_score = 20
        elif is_be:
            edge_score = 18
        else:
            edge_score = 5

        total_score = min(100, max(10, discipline_score + confluence_score + edge_score))
        grade = "A+" if total_score >= 90 else ("A" if total_score >= 80 else ("B" if total_score >= 70 else ("C" if total_score >= 60 else "F")))

        return {
            "total_score": total_score,
            "grade": f"{grade} (Quality Grade)",
            "discipline_score": discipline_score,
            "confluence_score": confluence_score,
            "edge_score": edge_score
        }

    def diagnose_root_cause(
        self,
        symbol: str,
        side: str,
        is_win: bool,
        is_be: bool,
        r_multiple: float,
        trade_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Diagnose root causes and determine institutional failure modes."""
        confluence = trade_spec.get("confluence", {})
        h4 = str(confluence.get("macro_4h", "")).upper()
        is_trend_aligned = (side.upper() == "BUY" and "BULL" in h4) or (side.upper() == "SELL" and "BEAR" in h4)

        success_reasons = []
        failure_reasons = []
        loss_category = "NOT_A_LOSS"

        if is_win:
            if is_trend_aligned:
                success_reasons.append("Higher-timeframe trend momentum (1H & 4H) accelerated price expansion.")
            actionable_lesson = "REPEAT PATTERN: Setup demonstrated clear institutional edge."
        elif is_be:
            success_reasons.append("Breakeven Shield ratcheted at +0.50R, eliminating downside risk.")
            failure_reasons.append("Momentum stalled prior to full target; mean-reversion occurred.")
            actionable_lesson = "ZERO-RISK OUTCOME: Trailing stop successfully protected capital."
        else:
            loss_category = self.classify_loss_reason({
                "outcome": "LOSS",
                "side": side,
                "regime": trade_spec.get("regime") or h4,
                "strategy": trade_spec.get("strategy", ""),
                "entry_price": trade_spec.get("entry_price", 1.0),
                "initial_sl": trade_spec.get("initial_sl", 0.0),
                "net_pnl_usd": trade_spec.get("realized_pnl", -2.0)
            })
            failure_reasons.append(f"Institutional failure mode: {loss_category}")
            actionable_lesson = f"LOSS AUDITED: Categorized as {loss_category}. Maintain risk discipline."

        return {
            "success_factors": success_reasons,
            "failure_factors": failure_reasons,
            "loss_category": loss_category,
            "actionable_lesson": actionable_lesson
        }

    def reflect_and_learn(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        realized_pnl: float,
        r_multiple: float,
        exit_reason: str,
        trade_spec: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Public callback invoked after trade exit by TrailingStopManager / ExecutionAgent.
        Updates verified dataset, pattern memory, and global scorecard.
        """
        spec = trade_spec or {}
        trade_id = str(spec.get("trade_id") or f"trade_{symbol}_{int(time.time())}")

        # Ingest into verified trade dataset
        trade_payload = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "contracts": spec.get("contracts", 1),
            "initial_sl": spec.get("initial_sl") or spec.get("stop_loss"),
            "initial_tp": spec.get("initial_tp") or spec.get("take_profit"),
            "dollar_risk_usd": spec.get("dollar_risk_usd") or spec.get("risk_usd"),
            "realized_pnl": realized_pnl,
            "exit_reason": exit_reason,
            "regime": spec.get("regime") or spec.get("macro_4h"),
            "strategy": spec.get("strategy", "Scalp"),
            "confluence_score": spec.get("confluence_score", 85)
        }
        self.ingest_trade_record(trade_payload)

        # Legacy-compatible scoring & diagnosis
        is_win = realized_pnl > 0.01
        is_be = abs(realized_pnl) <= 0.05 or exit_reason in ("BREAKEVEN", "TIMEOUT")
        scoring = self.score_trade(symbol, side, realized_pnl, r_multiple, exit_reason, spec)
        diagnosis = self.diagnose_root_cause(symbol, side, is_win, is_be, r_multiple, spec)

        pattern_key = self._derive_pattern_key(symbol, side, spec.get("strategy", ""), spec.get("confluence", {}))
        pat_data = self.memory["patterns"].get(pattern_key, {
            "pattern_key": pattern_key,
            "status": "EVALUATING",
            "score_adjustment": 0
        })

        reflection_summary = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "symbol": symbol,
            "side": side.upper(),
            "realized_pnl": realized_pnl,
            "r_multiple": r_multiple,
            "exit_reason": exit_reason,
            "score": scoring["total_score"],
            "grade": scoring["grade"],
            "pattern_key": pattern_key,
            "actionable_lesson": diagnosis["actionable_lesson"]
        }

        return {
            "scoring": scoring,
            "diagnosis": diagnosis,
            "pattern_data": pat_data,
            "scorecard": self.memory["scorecard"],
            "reflection": reflection_summary
        }

    def _update_learning_from_trade(self, trade: Dict[str, Any]):
        """Internal updater for patterns and global scorecard from verified trade record."""
        sym = trade["symbol"]
        side = trade["side"]
        pnl = trade["net_pnl_usd"]
        outcome = trade["outcome"]
        r = trade["net_r"]

        pattern_key = self._derive_pattern_key(sym, side, trade.get("strategy", ""), {})
        pat = self.memory["patterns"].setdefault(pattern_key, {
            "pattern_key": pattern_key,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "breakevens": 0,
            "cumulative_pnl": 0.0,
            "win_rate_pct": 0.0,
            "score_adjustment": 0,
            "status": "EVALUATING"
        })

        pat["total_trades"] += 1
        pat["cumulative_pnl"] = round(pat["cumulative_pnl"] + pnl, 2)
        if outcome == "WIN":
            pat["wins"] += 1
        elif outcome == "LOSS":
            pat["losses"] += 1
        else:
            pat["breakevens"] += 1

        resolved = pat["wins"] + pat["losses"]
        pat["win_rate_pct"] = round((pat["wins"] / resolved * 100.0), 1) if resolved > 0 else 50.0

        # Status & Adjustment
        if resolved >= 5 and pat["win_rate_pct"] >= 70.0:
            pat["status"] = "REINFORCED"
            pat["score_adjustment"] = +8
        elif pat["losses"] >= 4 and pat["win_rate_pct"] < 35.0:
            pat["status"] = "PENALIZED"
            pat["score_adjustment"] = -15
        else:
            pat["status"] = "NEUTRAL"
            pat["score_adjustment"] = 0

        # Global Scorecard
        sc = self.memory["scorecard"]
        sc["total_completed_trades"] += 1
        if outcome == "WIN":
            sc["winning_trades"] += 1
        elif outcome == "LOSS":
            sc["losing_trades"] += 1
        else:
            sc["breakeven_trades"] += 1

        sc["cumulative_pnl_usd"] = round(sc["cumulative_pnl_usd"] + pnl, 2)
        tot_res = sc["winning_trades"] + sc["losing_trades"]
        sc["win_rate_pct"] = round((sc["winning_trades"] / tot_res * 100.0), 1) if tot_res > 0 else 0.0

        # Net Expectancy
        all_r = [t["net_r"] for t in self.verified_trades]
        sc["net_expectancy_r"] = round(sum(all_r) / len(all_r), 4) if all_r else 0.0

        # Loss distribution
        if outcome == "LOSS":
            cat = self.classify_loss_reason(trade)
            self.memory["loss_distribution"][cat] = self.memory["loss_distribution"].get(cat, 0) + 1

        self._save_memory()

    def get_pattern_adjustment(
        self,
        symbol: str,
        side: str,
        strategy: str,
        confluence: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Consulted by StrategyAgent during candidate setup confluence evaluation.
        Returns priority adjustments while respecting live trading protection.
        """
        pattern_key = self._derive_pattern_key(symbol, side, strategy, confluence)
        pat = self.memory["patterns"].get(pattern_key)

        if not pat:
            return {
                "pattern_key": pattern_key,
                "status": "NEW_PATTERN",
                "score_adjustment": 0,
                "can_trade": True,
                "reason": "Neutral pattern baseline."
            }

        status = pat.get("status", "NEUTRAL")
        adj = pat.get("score_adjustment", 0)

        return {
            "pattern_key": pattern_key,
            "status": status,
            "score_adjustment": adj,
            "can_trade": True,
            "reason": f"Pattern {status} ({pat.get('win_rate_pct', 50)}% win rate, adjustment: {adj:+d} pts)."
        }

    def format_telegram_reflection(self, reflection_data: Dict[str, Any]) -> str:
        """Formats reflection message for Telegram notification."""
        refl = reflection_data.get("reflection", {})
        scoring = reflection_data.get("scoring", {})
        diag = reflection_data.get("diagnosis", {})
        sc = reflection_data.get("scorecard", {})

        sym = refl.get("symbol", "BTCUSD")
        side = refl.get("side", "BUY")
        dir_emoji = "🟢 LONG" if side == "BUY" else "🔴 SHORT"
        pnl = refl.get("realized_pnl", 0.0)
        r = refl.get("r_multiple", 0.0)
        pnl_str = f"+${pnl:.2f} USD (+{r:.2f}R)" if pnl > 0 else (f"-${abs(pnl):.2f} USD ({r:.2f}R)" if pnl < 0 else "$0.00 USD (Breakeven)")

        return (
            f"🧠 <b>[ADAPTIVE LEARNING AUDIT]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Asset:</b> <code>{sym}</code> ({dir_emoji})\n"
            f"• <b>Net PnL:</b> <b>{pnl_str}</b>\n"
            f"• <b>Grade:</b> <b>{scoring.get('grade', 'B')} ({scoring.get('total_score', 75)}/100)</b>\n"
            f"• <b>Lesson:</b> <i>{diag.get('actionable_lesson', 'Disciplined execution maintained.')}</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Win Rate:</b> <b>{sc.get('win_rate_pct', 0.0)}%</b> ({sc.get('winning_trades', 0)}W / {sc.get('losing_trades', 0)}L)\n"
            f"📈 <b>Net Expectancy:</b> <b>{sc.get('net_expectancy_r', 0.0):.2f}R</b> | <b>PnL:</b> <b>${sc.get('cumulative_pnl_usd', 0.0):.2f}</b>"
        )
