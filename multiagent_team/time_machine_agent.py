"""
Agent 4: Time Machine Historical Simulation & Probability Engine.
Simulates candidate trade setups backwards through historical price data to calculate
empirical success rate, expected value (EV), fees/funding/slippage friction,
Wilson score confidence intervals, out-of-sample validation, and Profit Factor
BEFORE any trade is submitted to the Risk Gatekeeper or user for execution.

CRITICAL COMPLIANCE:
All synthetic fallbacks and fabricated backtest approvals have been completely removed.
If data is missing or samples are small, the agent fails closed with INSUFFICIENT_DATA
or INSUFFICIENT_SAMPLE.
"""

from typing import Dict, Any, List, Optional
import time
import math
import logging
from src.delta_client import DeltaExchangeClient
from src.technical_analysis import calculate_ema, calculate_rsi

logger = logging.getLogger("time-machine-agent")


def calculate_wilson_lower_bound(wins: int, n: int, confidence: float = 0.95) -> float:
    """
    Calculate the lower bound of the Wilson Score 95% Confidence Interval.
    Prevents trusting small sample flukes (e.g. 2 wins out of 2 trades).
    """
    if n <= 0:
        return 0.0
    p = wins / n
    z = 1.96  # 95% confidence
    denominator = 1.0 + (z ** 2) / n
    centre_adjusted = p + (z ** 2) / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) + (z ** 2) / (4.0 * n)) / n)
    lower_bound = (centre_adjusted - spread) / denominator
    return round(max(0.0, lower_bound) * 100.0, 1)


class TimeMachineAgent:
    """
    The 'Time Machine' Probability Engine.
    Evaluates every candidate trade by forward-simulating identical historical patterns
    across past candles to ensure positive mathematical expectancy without data snooping.
    """
    def __init__(
        self,
        client: Optional[DeltaExchangeClient] = None,
        min_win_rate_pct: float = 65.0,
        min_expected_value_r: float = 0.30,
        lookback_candles: int = 400,
        max_simulation_bars: int = 48,
        min_sample_size: int = 8,
        min_oos_sample_size: int = 3
    ):
        self.client = client
        self.min_win_rate_pct = min_win_rate_pct
        self.min_expected_value_r = min_expected_value_r
        self.lookback_candles = lookback_candles
        self.max_simulation_bars = max_simulation_bars
        self.min_sample_size = min_sample_size
        self.min_oos_sample_size = min_oos_sample_size

        # Institutional Friction Assumptions for Delta Exchange
        self.taker_fee_pct = 0.0005    # 0.05% per leg = 0.10% round-trip
        self.slippage_pct = 0.0003     # 0.03% per leg = 0.06% round-trip
        self.funding_est_pct = 0.0001  # 0.01% estimated funding drag
        self.total_friction_pct = (self.taker_fee_pct * 2) + (self.slippage_pct * 2) + self.funding_est_pct

    def simulate_setup(
        self,
        setup: Dict[str, Any],
        candles_15m: Optional[Dict[str, Any]] = None,
        candles_1h: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run walk-forward simulation with out-of-sample validation, friction deduction,
        and Wilson confidence intervals.
        Deterministic and evidence-driven: returns INSUFFICIENT_DATA or INSUFFICIENT_SAMPLE
        when real statistical evidence is absent.
        """
        symbol = setup.get("symbol", "BTCUSD")
        side = setup.get("side", "buy").lower()
        entry = float(setup.get("entry_price", 0.0))
        sl = float(setup.get("stop_loss_price", 0.0))
        tp = float(setup.get("take_profit_price", 0.0))

        if entry <= 0 or sl <= 0 or tp <= 0 or entry == sl:
            return {
                "passed": False,
                "verdict": "VETOED_INVALID_PRICES",
                "sample_size": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_pct": 0.0,
                "wilson_ci_lower_pct": 0.0,
                "expected_value_r": 0.0,
                "profit_factor": 0.0,
                "reason": "Invalid entry, stop loss, or take profit values for simulation."
            }

        sl_dist_pct = abs(entry - sl) / entry
        tp_dist_pct = abs(tp - entry) / entry
        planned_rr = tp_dist_pct / sl_dist_pct if sl_dist_pct > 0 else 2.0

        # Fetch historical 15m candles if not supplied
        if not candles_15m or len(candles_15m.get("c", [])) < 80:
            if self.client:
                try:
                    now = int(time.time())
                    from_t = now - (900 * self.lookback_candles)
                    res = self.client.get_candles(symbol, resolution="15", from_time=from_t, to_time=now)
                    candles_15m = res.get("result", {}) if res and res.get("success") else {}
                except Exception as e:
                    logger.error(f"TimeMachine: Failed to fetch candles for {symbol}: {e}")
                    candles_15m = {}
            else:
                candles_15m = {}

        closes = [float(x) for x in candles_15m.get("c", [])]
        highs = [float(x) for x in candles_15m.get("h", [])]
        lows = [float(x) for x in candles_15m.get("l", [])]
        opens = [float(x) for x in candles_15m.get("o", [])]

        total_bars = len(closes)
        if total_bars < 60:
            logger.warning(f"TimeMachine: Insufficient historical candles ({total_bars}) for {symbol}. VETOING.")
            return {
                "passed": False,
                "verdict": "INSUFFICIENT_DATA",
                "sample_size": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_pct": 0.0,
                "wilson_ci_lower_pct": 0.0,
                "expected_value_r": 0.0,
                "profit_factor": 0.0,
                "reason": f"INSUFFICIENT_DATA: Only {total_bars} candles available for {symbol} (minimum 60 required). Real statistical simulation cannot be executed."
            }

        # Calculate indicators across history (strictly zero lookahead)
        rsi_series = calculate_rsi(closes, 14)
        ema21_series = calculate_ema(closes, 21)
        ema50_series = calculate_ema(closes, 50) if total_bars >= 50 else ema21_series

        # Out-of-sample partition (70% in-sample train, 30% out-of-sample validation)
        split_idx = int(total_bars * 0.70)

        matches = []
        i = 30
        end_idx = total_bars - self.max_simulation_bars

        # Historical Pattern Matching Walk
        while i < end_idx:
            c_price = closes[i]
            c_rsi = rsi_series[i]
            c_ema21 = ema21_series[i]
            c_ema50 = ema50_series[i]

            is_match = False

            if side == "buy":
                recent_low = min(lows[max(0, i - 10):i]) if i >= 10 else lows[i]
                recent_high = max(highs[max(0, i - 10):i]) if i >= 10 else highs[i]
                swept_low = lows[i] < recent_low and closes[i] > recent_low
                is_oversold_bounce = c_rsi < 40 and closes[i] > opens[i]
                trend_aligned = c_price >= c_ema21 or c_ema21 >= c_ema50
                is_breakout = highs[i] > recent_high and trend_aligned
                is_ema_bounce = lows[i] <= c_ema21 * 1.002 and closes[i] >= c_ema21 and trend_aligned
                is_momentum_impulse = closes[i] > opens[i] and c_rsi >= 45 and trend_aligned
                if (swept_low or is_oversold_bounce or is_breakout or is_ema_bounce or is_momentum_impulse) and trend_aligned:
                    is_match = True

            elif side == "sell":
                recent_high = max(highs[max(0, i - 10):i]) if i >= 10 else highs[i]
                recent_low = min(lows[max(0, i - 10):i]) if i >= 10 else lows[i]
                swept_high = highs[i] > recent_high and closes[i] < recent_high
                is_overbought_reject = c_rsi > 60 and closes[i] < opens[i]
                trend_aligned = c_price <= c_ema21 or c_ema21 <= c_ema50
                is_breakdown = lows[i] < recent_low and trend_aligned
                is_ema_reject = highs[i] >= c_ema21 * 0.998 and closes[i] <= c_ema21 and trend_aligned
                is_momentum_impulse = closes[i] < opens[i] and c_rsi <= 55 and trend_aligned
                if (swept_high or is_overbought_reject or is_breakdown or is_ema_reject or is_momentum_impulse) and trend_aligned:
                    is_match = True

            if is_match:
                sim_entry = opens[i + 1]
                sim_sl = sim_entry * (1.0 - sl_dist_pct) if side == "buy" else sim_entry * (1.0 + sl_dist_pct)
                sim_tp = sim_entry * (1.0 + tp_dist_pct) if side == "buy" else sim_entry * (1.0 - tp_dist_pct)

                outcome = "TIMEOUT"
                bars_held = 0
                max_adverse = 0.0
                sim_bars = 16 if sl_dist_pct <= 0.008 else self.max_simulation_bars

                for step in range(1, sim_bars + 1):
                    bar_idx = i + 1 + step
                    if bar_idx >= total_bars:
                        break

                    b_high = highs[bar_idx]
                    b_low = lows[bar_idx]
                    bars_held = step

                    if side == "buy":
                        adverse = max(0.0, (sim_entry - b_low) / sim_entry)
                        if adverse > max_adverse:
                            max_adverse = adverse

                        # Scalper Breakeven Shield: At +0.50R profit, Stop Loss snaps to entry
                        if b_high >= sim_entry + (0.50 * sim_entry * sl_dist_pct):
                            sim_sl = max(sim_sl, sim_entry)

                        # Check SL / TP
                        if b_low <= sim_sl:
                            outcome = "BREAKEVEN" if sim_sl >= sim_entry else "LOSS"
                            break
                        if b_high >= sim_tp:
                            outcome = "WIN"
                            break

                    elif side == "sell":
                        adverse = max(0.0, (b_high - sim_entry) / sim_entry)
                        if adverse > max_adverse:
                            max_adverse = adverse

                        # Scalper Breakeven Shield: At +0.50R profit, Stop Loss snaps to entry
                        if b_low <= sim_entry - (0.50 * sim_entry * sl_dist_pct):
                            sim_sl = min(sim_sl, sim_entry)

                        if b_high >= sim_sl:
                            outcome = "BREAKEVEN" if sim_sl <= sim_entry else "LOSS"
                            break
                        if b_low <= sim_tp:
                            outcome = "WIN"
                            break

                matches.append({
                    "bar_index": i,
                    "is_out_of_sample": i >= split_idx,
                    "outcome": outcome,
                    "bars_held": bars_held,
                    "max_adverse_pct": max_adverse * 100.0
                })

                # Skip forward past simulated trade to prevent overlapping lookahead bias
                i += max(bars_held, 4)
            else:
                i += 1

        resolved_trades = [m for m in matches if m["outcome"] in ["WIN", "LOSS", "BREAKEVEN"]]
        wins = sum(1 for m in resolved_trades if m["outcome"] == "WIN")
        losses = sum(1 for m in resolved_trades if m["outcome"] == "LOSS")
        breakevens = sum(1 for m in resolved_trades if m["outcome"] == "BREAKEVEN")
        total_resolved = len(resolved_trades)
        total_decisive = wins + losses

        # Minimum sample size requirement: NO SYNTHETIC FALLBACKS
        if total_decisive < self.min_sample_size:
            return {
                "passed": False,
                "verdict": "INSUFFICIENT_SAMPLE",
                "sample_size": total_decisive,
                "wins": wins,
                "losses": losses,
                "win_rate_pct": round((wins / total_decisive * 100.0), 1) if total_decisive > 0 else 0.0,
                "wilson_ci_lower_pct": calculate_wilson_lower_bound(wins, total_decisive) if total_decisive > 0 else 0.0,
                "expected_value_r": 0.0,
                "profit_factor": 0.0,
                "reason": (
                    f"INSUFFICIENT_SAMPLE: Found only {total_decisive} decisive historical trade matches "
                    f"({self.min_sample_size} minimum required). Trade candidate rejected to prevent overfitting."
                )
            }

        win_rate = round((wins / max(1, total_decisive)) * 100.0, 1)
        wilson_lower = calculate_wilson_lower_bound(wins, total_decisive)

        # Friction-Adjusted Expectancy (Delta fees + slippage + funding deducted)
        friction_r_penalty = self.total_friction_pct / sl_dist_pct if sl_dist_pct > 0 else 0.08
        ev_r = round(((win_rate / 100.0) * planned_rr) - ((1.0 - (win_rate / 100.0)) * 1.0) - friction_r_penalty, 2)

        # Profit Factor with friction
        gross_profit = wins * max(0.0001, tp_dist_pct - self.total_friction_pct)
        gross_loss = losses * (sl_dist_pct + self.total_friction_pct)
        profit_factor = round(gross_profit / max(gross_loss, 0.0001), 2)

        avg_mae = round(sum(m["max_adverse_pct"] for m in matches) / len(matches), 2) if matches else 0.0
        avg_bars = round(sum(m["bars_held"] for m in matches) / len(matches), 1) if matches else 0.0

        # Out-of-sample validation check (strict: no synthetic fallback)
        oos_matches = [m for m in resolved_trades if m.get("is_out_of_sample")]
        oos_decisive = [m for m in oos_matches if m["outcome"] in ["WIN", "LOSS"]]
        oos_wins = sum(1 for m in oos_decisive if m["outcome"] == "WIN")
        
        oos_valid = len(oos_decisive) >= self.min_oos_sample_size
        oos_win_rate = round((oos_wins / len(oos_decisive) * 100.0), 1) if oos_valid else None
        oos_ev_r = (
            round(((oos_win_rate / 100.0) * planned_rr) - ((1.0 - (oos_win_rate / 100.0)) * 1.0) - friction_r_penalty, 2)
            if oos_valid and oos_win_rate is not None else None
        )

        # Statistical Sharpe Ratio estimation (if N >= 10)
        sharpe_ratio = None
        if total_decisive >= 10:
            returns_r = [planned_rr if m["outcome"] == "WIN" else -1.0 for m in resolved_trades if m["outcome"] in ["WIN", "LOSS"]]
            mean_r = sum(returns_r) / len(returns_r)
            var_r = sum((x - mean_r) ** 2 for x in returns_r) / (len(returns_r) - 1)
            std_r = math.sqrt(var_r) if var_r > 0 else 0.0
            if std_r > 0:
                sharpe_ratio = round((mean_r / std_r) * math.sqrt(252 * 4), 2)  # annualized assuming 4 trades/day

        # Decision standard:
        # 1. In-sample empirical edge: win_rate >= min_win_rate_pct or (planned_rr >= 2.4 and win_rate >= 60.0)
        # 2. Friction-adjusted EV >= min_expected_value_r
        # 3. Profit Factor >= 1.50x
        # 4. Out-of-sample validation must be valid and positive (or if OOS sample too small, require higher Wilson CI)
        edge_passed = (win_rate >= self.min_win_rate_pct or (planned_rr >= 2.4 and win_rate >= 60.0))
        ev_passed = (ev_r >= self.min_expected_value_r)
        pf_passed = (profit_factor >= 1.50)
        oos_passed = (oos_ev_r >= 0.0) if (oos_valid and oos_ev_r is not None) else (wilson_lower >= 45.0)

        passed = edge_passed and ev_passed and pf_passed and oos_passed

        verdict = "APPROVED" if passed else "REJECTED"
        reasons = []
        if not edge_passed:
            reasons.append(f"Win rate {win_rate}% below required {self.min_win_rate_pct}%")
        if not ev_passed:
            reasons.append(f"Friction-adjusted EV {ev_r:+.2f}R below minimum {self.min_expected_value_r}R")
        if not pf_passed:
            reasons.append(f"Profit factor {profit_factor}x below 1.50x")
        if not oos_passed:
            reasons.append(f"Out-of-sample validation failed (OOS Win Rate: {oos_win_rate}%, Wilson Lower: {wilson_lower}%)")

        reason_str = (
            f"Time Machine APPROVED: {win_rate}% Win Rate ({wins}W / {losses}L / {breakevens}BE, Wilson 95% Lower: {wilson_lower}%), "
            f"Friction-Adjusted EV: +{ev_r}R, Profit Factor: {profit_factor}x, OOS Win Rate: {oos_win_rate if oos_win_rate is not None else 'N/A'}%."
            if passed else
            f"Time Machine REJECTED: {'; '.join(reasons)}."
        )

        return {
            "passed": passed,
            "verdict": verdict,
            "sample_size": total_decisive,
            "total_matches": total_resolved,
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "win_rate_pct": win_rate,
            "wilson_ci_lower_pct": wilson_lower,
            "oos_valid": oos_valid,
            "oos_sample_size": len(oos_decisive),
            "oos_win_rate_pct": oos_win_rate,
            "oos_expected_value_r": oos_ev_r,
            "expected_value_r": ev_r,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "avg_mae_pct": avg_mae,
            "avg_bars_to_target": avg_bars,
            "friction_deducted_pct": round(self.total_friction_pct * 100, 3),
            "reason": reason_str
        }
