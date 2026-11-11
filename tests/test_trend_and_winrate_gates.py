"""Tests enforcing strict trend-following alignment and rejecting low-win-rate setups."""

import time
import unittest
from unittest.mock import MagicMock, patch

from multiagent_team.adaptive_learning import AdaptiveLearningEngine
from multiagent_team.exposure_coach import ExposureCoachAgent
from multiagent_team.orchestrator import MultiAgentTradingOrchestrator
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.strategy_agent import StrategyAgent
from src.risk_manager import RiskManager


def _make_trend_candles(n: int = 160, direction: str = "up", base: float = 70000.0):
    now_ts = int(time.time())
    t_arr, o_arr, h_arr, l_arr, c_arr, v_arr = [], [], [], [], [], []
    step = 35.0 if direction == "up" else -35.0
    for i in range(n):
        t_arr.append(now_ts - (n - i) * 900)
        px = max(1000.0, base + i * step)
        if direction == "up":
            o_p, c_p = px - 10.0, px + 30.0
            h_p, l_p = px + 55.0, px - 35.0
        else:
            o_p, c_p = px + 10.0, px - 30.0
            h_p, l_p = px + 35.0, px - 55.0
        o_arr.append(o_p)
        h_arr.append(h_p)
        l_arr.append(l_p)
        c_arr.append(c_p)
        v_arr.append(180.0)
    return {"t": t_arr, "o": o_arr, "h": h_arr, "l": l_arr, "c": c_arr, "v": v_arr}


class TestTrendAndWinRateGates(unittest.TestCase):
    def setUp(self):
        self.strategy = StrategyAgent()
        self.strategy.adaptive_learner = MagicMock()
        self.strategy.adaptive_learner.get_pattern_adjustment.return_value = {
            "can_trade": True,
            "score_adjustment": 0,
        }

    def test_strategy_agent_vetoes_counter_trend_long_in_bearish_htf(self):
        bear_candles_1h = _make_trend_candles(60, direction="down", base=72000.0)
        analysis = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "regime": "TRENDING_DOWN",
            "directional_bias": "BEARISH",
            "_raw_candles_1h": bear_candles_1h,
            "macro_4h": {"regime": "MACRO_BEARISH"},
            "macro_daily": {"regime": "DAILY_BEARISH"},
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 95,
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,
                "take_profit_price": 71800.0,
                "atr_14": 400.0,
            },
        }
        setup = self.strategy.evaluate_setup(analysis)
        self.assertIsNone(setup)
        rej = self.strategy.get_last_rejection("BTCUSD")
        self.assertEqual(rej["gate"], "COUNTER_TREND_VETO")

    def test_strategy_agent_vetoes_counter_trend_short_in_bullish_htf(self):
        bull_candles_1h = _make_trend_candles(60, direction="up", base=68000.0)
        analysis = {
            "symbol": "ETHUSD",
            "current_price": 3200.0,
            "spread_pct": 0.02,
            "regime": "STRONG_TREND_UP",
            "directional_bias": "BULLISH",
            "_raw_candles_1h": bull_candles_1h,
            "macro_4h": {"regime": "MACRO_BULLISH"},
            "macro_daily": {"regime": "DAILY_BULLISH"},
            "high_probability_setup": {
                "qualified": True,
                "side": "sell",
                "score": 95,
                "entry_price": 3200.0,
                "stop_loss_price": 3240.0,
                "take_profit_price": 3080.0,
                "atr_14": 25.0,
            },
        }
        setup = self.strategy.evaluate_setup(analysis)
        self.assertIsNone(setup)
        rej = self.strategy.get_last_rejection("ETHUSD")
        self.assertEqual(rej["gate"], "COUNTER_TREND_VETO")

    def test_strategy_agent_vetoes_rangebound_chop_without_htf_trend(self):
        analysis = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "spread_pct": 0.02,
            "regime": "RANGING_CHOP",
            "directional_bias": "NEUTRAL",
            "macro_4h": {"regime": "MACRO_NEUTRAL"},
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "score": 88,
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,
                "take_profit_price": 71600.0,
                "atr_14": 400.0,
            },
        }
        setup = self.strategy.evaluate_setup(analysis)
        self.assertIsNone(setup)
        rej = self.strategy.get_last_rejection("BTCUSD")
        self.assertEqual(rej["gate"], "CHOP_REGIME_VETO")

    def test_exposure_coach_preserves_macro_bias_during_recovery_and_moderate(self):
        coach = ExposureCoachAgent()
        coach._check_consecutive_losses = MagicMock(return_value=2)
        scan = {
            "symbols_data": {
                "BTCUSD": {
                    "current_price": 68000.0,
                    "directional_bias": "BEARISH",
                    "macro_15m": {"ema_21": 69000.0},
                    "macro_4h": {"regime": "MACRO_BEARISH"},
                    "macro_daily": {"rsi_14": 40.0},
                    "funding_rate": 0.0,
                },
                "ETHUSD": {
                    "current_price": 3000.0,
                    "directional_bias": "BEARISH",
                    "macro_15m": {"ema_21": 3100.0},
                    "macro_4h": {"regime": "MACRO_BEARISH"},
                    "macro_daily": {"rsi_14": 38.0},
                    "funding_rate": 0.0,
                },
            },
            "macd_breadth_pct": 20.0,
            "vwap_breadth_pct": 20.0,
        }
        posture = coach.evaluate_market_posture(scan)
        self.assertEqual(posture["posture"], "RECOVERY_POSTURE")
        self.assertEqual(posture["direction_bias"], "SHORTS_ONLY")

    def test_adaptive_learning_blacklists_low_win_rate_pattern(self):
        engine = AdaptiveLearningEngine()
        key = engine._derive_pattern_key("BTCUSD", "BUY", "SMC_SCALP", {"macro_4h": "BULLISH"})
        engine.memory["patterns"][key] = {
            "wins": 1,
            "losses": 4,
            "breakevens": 0,
            "win_rate_pct": 20.0,
            "status": "PENALIZED",
            "score_adjustment": -15,
        }
        adj = engine.get_pattern_adjustment("BTCUSD", "BUY", "SMC_SCALP", {"macro_4h": "BULLISH"})
        self.assertFalse(adj["can_trade"])
        self.assertEqual(adj["status"], "BLACKLISTED_LOW_WIN_RATE")

    def test_risk_gatekeeper_rejects_low_win_rate_setup(self):
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": 1000.0, "available_balance": 1000.0}],
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        gk = RiskGatekeeperAgent(client=mock_client, risk_manager=RiskManager())
        setup = {
            "symbol": "BTCUSD",
            "side": "buy",
            "entry_price": 70000.0,
            "stop_loss_price": 69400.0,
            "take_profit_price": 71600.0,
            "spread_pct": 0.02,
            "time_machine": {
                "passed": True,
                "win_rate_pct": 42.0,
                "expected_value_r": 0.25,
            },
        }
        decision = gk.evaluate_candidate(setup, leverage=50)
        self.assertEqual(decision["gate_decision"], "REJECTED")
        self.assertIn("Low Win Rate Veto", decision["reason"])

    def test_orchestrator_never_bypasses_time_machine_veto(self):
        mock_client = MagicMock()
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": 1000.0, "available_balance": 1000.0}],
        }
        mock_client.get_open_orders.return_value = {"success": True, "result": []}

        orch = MultiAgentTradingOrchestrator(client=mock_client, symbols=["BTCUSD"], interactive=False)
        orch.trailing_stop_manager.check_and_update_trailing_stops = MagicMock()
        orch.portfolio_monitor.check_portfolio_health = MagicMock(return_value={"status": "HEALTHY", "active_positions_count": 0})
        orch.emergency_controller.is_halted = MagicMock(return_value=(False, ""))
        orch.news_sentiment.generate_sentiment_report = MagicMock(return_value=None)
        orch.exposure_coach.evaluate_market_posture = MagicMock(
            return_value={"posture": "MODERATE_SELECTIVE", "health_score": 65, "breadth_pct": 70.0, "cash_priority": False, "direction_bias": "LONGS_ONLY"}
        )
        orch.regime_analyst.scan_universe = MagicMock(
            return_value={
                "overall_market_regime": "STRONG_BULLISH",
                "btc_adx": 28.0,
                "btc_volatility_state": "NORMAL",
                "symbols_data": {"BTCUSD": {"symbol": "BTCUSD"}},
            }
        )
        # Score >= 80 primary setup that previously got promoted even when Time Machine rejected it!
        orch.strategy_agent.find_best_candidates = MagicMock(
            return_value=[
                {
                    "symbol": "BTCUSD",
                    "side": "buy",
                    "entry_price": 70000.0,
                    "stop_loss_price": 69400.0,
                    "take_profit_price": 71800.0,
                    "planned_rr_ratio": 3.0,
                    "strategy_name": "Institutional_SSL_Sweep",
                    "score": 92,
                }
            ]
        )
        orch.time_machine.simulate_setup = MagicMock(
            return_value={
                "passed": False,
                "verdict": "REJECTED",
                "win_rate_pct": 33.3,
                "expected_value_r": -0.15,
                "profit_factor": 0.85,
                "reason": "Time Machine REJECTED: Win rate 33.3% below required 60.0%.",
            }
        )

        res = orch.run_trading_cycle()
        self.assertEqual(res["status"], "REJECTED")
        self.assertEqual(res["code"], "TIME_MACHINE_VETO")
        self.assertIn("33.3%", res["reason"])

    def test_propose_on_demand_trade_rejects_counter_trend_and_low_winrate(self):
        mock_client = MagicMock()
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_ticker.return_value = {"success": True, "result": {"mark_price": 68000.0}}
        bear_candles = _make_trend_candles(120, direction="down", base=72000.0)
        mock_client.get_candles.return_value = {"success": True, "result": bear_candles}

        orch = MultiAgentTradingOrchestrator(client=mock_client, symbols=["BTCUSD"], interactive=False)
        orch.emergency_controller.is_halted = MagicMock(return_value=(False, ""))
        orch.notify_telegram_rejection = MagicMock()

        # 1. Counter-trend buy request in bearish trend must be rejected
        res_ct = orch.propose_on_demand_trade(symbol="BTCUSD", side="buy", chat_id="123")
        self.assertEqual(res_ct["status"], "REJECTED")
        self.assertEqual(res_ct["code"], "COUNTER_TREND_VETO")
        self.assertTrue(orch.notify_telegram_rejection.called)

        # 2. Trend-aligned short with low historical win rate (< 60%) must be rejected by Time Machine
        orch.notify_telegram_rejection.reset_mock()
        orch.regime_analyst.analyze_symbol = MagicMock(
            return_value={
                "symbol": "BTCUSD",
                "current_price": 68000.0,
                "mark_price": 68000.0,
                "spread_pct": 0.02,
                "regime": "TRENDING_DOWN",
                "directional_bias": "BEARISH",
                "_raw_candles_15m": bear_candles,
                "_raw_candles_1h": bear_candles,
                "macro_4h": {"regime": "MACRO_BEARISH"},
                "macro_daily": {"regime": "DAILY_BEARISH"},
                "high_probability_setup": {
                    "qualified": True,
                    "side": "sell",
                    "strategy": "Intraday_EMA_Pullback_Scalp_Short",
                    "score": 90,
                    "entry_price": 68000.0,
                    "stop_loss_price": 68400.0,
                    "take_profit_price": 67000.0,
                    "atr_14": 300.0,
                },
            }
        )
        with patch.object(
            orch.time_machine,
            "simulate_setup",
            return_value={
                "passed": False,
                "verdict": "REJECTED",
                "win_rate_pct": 38.0,
                "expected_value_r": -0.05,
                "profit_factor": 0.9,
                "reason": "Time Machine REJECTED: Win rate 38.0% below required 60.0%.",
            },
        ):
            res_wr = orch.propose_on_demand_trade(symbol="BTCUSD", side="sell", chat_id="123")

        self.assertEqual(res_wr["status"], "REJECTED")
        self.assertEqual(res_wr["code"], "TIME_MACHINE_VETO")
        self.assertTrue(orch.notify_telegram_rejection.called)


if __name__ == "__main__":
    unittest.main()
