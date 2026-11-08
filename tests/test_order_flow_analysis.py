"""
Comprehensive Test Suite for Institutional Order Flow Intelligence:
1. Volume Profile (VP): Point of Control (POC), Value Area (VAH/VAL 70%), Stance.
2. Cumulative Volume Delta (CVD): Delta per bar, CVD curve, Trend slope, Bullish/Bearish Divergence.
3. Level-2 Order Book Imbalance (OBI): Depth aggregation, Imbalance ratio, Resting wall detection.
4. StrategyAgent: Order flow confluence scoring & wall penalty logic.
5. RiskGatekeeperAgent: Extreme OBI veto & order flow profile validation.
"""

import unittest
from unittest.mock import MagicMock
from src.technical_analysis import (
    calculate_volume_profile,
    calculate_cumulative_volume_delta,
    calculate_order_book_imbalance,
    analyze_market_structure
)
from multiagent_team.strategy_agent import StrategyAgent
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from src.risk_manager import RiskManager


class TestOrderFlowIntelligence(unittest.TestCase):

    def test_volume_profile_poc_and_value_area(self):
        """Test that Volume Profile correctly calculates POC, VAH, VAL, and stance."""
        # 30 candles concentrated around $70,000 with a high volume cluster
        highs = [69000.0 + (i * 50.0) for i in range(30)]
        lows = [68800.0 + (i * 50.0) for i in range(30)]
        closes = [68900.0 + (i * 50.0) for i in range(30)]
        volumes = [100.0] * 30
        # Concentrate massive volume in the middle (bins around index 15: ~$69,600)
        volumes[14] = 2000.0
        volumes[15] = 5000.0
        volumes[16] = 2000.0

        vp = calculate_volume_profile(highs, lows, closes, volumes, num_bins=30, value_area_pct=0.70)

        self.assertGreater(vp["poc"], 69000.0)
        self.assertLess(vp["poc"], 70500.0)
        self.assertGreaterEqual(vp["vah"], vp["poc"])
        self.assertLessEqual(vp["val"], vp["poc"])
        self.assertGreater(vp["total_profile_volume"], 9000.0)
        self.assertIn(vp["stance"], ["ABOVE_VAH", "INSIDE_VA", "BELOW_VAL", "AT_POC"])

    def test_cvd_trend_and_accumulation(self):
        """Test Cumulative Volume Delta (CVD) running sum and upward accumulation slope."""
        # Consecutive strong green candles closing at their highs (aggressive buyers)
        opens = [100.0 + i for i in range(20)]
        lows = [99.5 + i for i in range(20)]
        highs = [102.0 + i for i in range(20)]
        closes = [102.0 + i for i in range(20)]  # Closes at highs
        volumes = [500.0] * 20

        cvd = calculate_cumulative_volume_delta(opens, highs, lows, closes, volumes)

        self.assertGreater(cvd["current_cvd"], 0.0)
        self.assertGreater(cvd["delta_last_bar"], 0.0)
        self.assertGreater(cvd["cvd_slope"], 0.0)
        self.assertEqual(cvd["cvd_trend"], "RISING_ACCUMULATION")

    def test_bullish_cvd_absorption_divergence(self):
        """Test detection of Bullish CVD Divergence (Price lower low, CVD higher low)."""
        # Part 1: Price drops to 100, CVD drops to -500
        opens = [105.0, 103.0, 102.0, 101.0, 100.0]
        highs = [106.0, 104.0, 103.0, 102.0, 101.0]
        lows = [102.0, 101.0, 100.0, 99.0, 98.0]
        closes = [103.0, 101.0, 100.0, 99.0, 98.5]
        volumes = [1000.0] * 5

        # Part 2: Small bounce
        opens.extend([99.0, 100.0, 101.0])
        highs.extend([101.0, 102.0, 103.0])
        lows.extend([98.5, 99.5, 100.0])
        closes.extend([100.5, 101.5, 102.0])
        volumes.extend([800.0, 800.0, 800.0])

        # Part 3: Price presses back to lower low (97.5), but with aggressive buying wicks (CVD holds higher low)
        opens.extend([102.0, 100.0, 98.5, 98.0])
        highs.extend([102.5, 100.5, 99.5, 101.0])
        lows.extend([99.0, 98.0, 97.5, 97.4])  # New lower low
        closes.extend([100.0, 98.5, 99.2, 100.8])  # Strong bounce wicks closing near highs
        volumes.extend([1500.0, 1500.0, 2000.0, 2500.0])

        cvd = calculate_cumulative_volume_delta(opens, highs, lows, closes, volumes, lookback=15)
        self.assertIn("cvd_series", cvd)
        self.assertIsNotNone(cvd["divergence"])

    def test_order_book_imbalance_and_walls(self):
        """Test Level-2 Order Book Imbalance ratio, depth ratio, and resting wall detection."""
        # Mock orderbook with heavy bid imbalance and a massive bid wall at $69,500
        orderbook = {
            "buy": [
                {"price": "69900", "size": "10.0"},
                {"price": "69800", "size": "15.0"},
                {"price": "69700", "size": "20.0"},
                {"price": "69500", "size": "120.0"},  # Giant Whale Wall (>= 35% of total depth)
                {"price": "69400", "size": "15.0"}
            ],
            "sell": [
                {"price": "70000", "size": "5.0"},
                {"price": "70100", "size": "8.0"},
                {"price": "70200", "size": "10.0"},
                {"price": "70300", "size": "12.0"},
                {"price": "70400", "size": "15.0"}
            ]
        }

        obi = calculate_order_book_imbalance(orderbook, depth=10)

        self.assertGreater(obi["obi_ratio"], 0.25)
        self.assertEqual(obi["imbalance_status"], "HEAVY_BID_IMBALANCE")
        self.assertGreater(obi["depth_ratio"], 1.5)
        self.assertTrue(obi["bid_wall_detected"])
        self.assertEqual(obi["bid_wall_price"], 69500.0)
        self.assertGreaterEqual(obi["bid_wall_size"], 100.0)
        self.assertFalse(obi["ask_wall_detected"])

    def test_analyze_market_structure_with_orderbook(self):
        """Test analyze_market_structure integrates Volume Profile, CVD, and OBI."""
        highs = [100.0 + i for i in range(25)]
        lows = [95.0 + i for i in range(25)]
        opens = [97.0 + i for i in range(25)]
        closes = [99.0 + i for i in range(25)]
        volumes = [1000.0 for _ in range(25)]

        orderbook = {
            "buy": [{"price": "120.0", "size": "50.0"}],
            "sell": [{"price": "121.0", "size": "20.0"}]
        }

        candles_dict = {'o': opens, 'h': highs, 'l': lows, 'c': closes, 'v': volumes}
        res = analyze_market_structure(candles_dict, orderbook=orderbook)

        self.assertIn("volume_profile", res)
        self.assertIn("cvd", res)
        self.assertIn("order_book_imbalance", res)
        self.assertIn("poc", res["volume_profile"])
        self.assertIn("current_cvd", res["cvd"])
        self.assertEqual(res["order_book_imbalance"]["imbalance_status"], "HEAVY_BID_IMBALANCE")

    def test_strategy_agent_order_flow_scoring(self):
        """Test StrategyAgent boosts score for bullish CVD divergence & heavy bid support."""
        agent = StrategyAgent()
        agent.adaptive_learner = MagicMock()
        agent.adaptive_learner.get_pattern_adjustment.return_value = {"can_trade": True, "score_adjustment": 0}

        analysis = {
            "symbol": "BTCUSD",
            "current_price": 70000.0,
            "regime": "STRONG_BULLISH",
            "rsi_14": 55.0,
            "atr_14": 400.0,
            "vwap": 69800.0,
            "vwap_analysis": {"stance": "ABOVE_VWAP", "band_location": "FAIR_VALUE_CORE", "slope": "RISING_BULLISH"},
            "liquidity": {"liquidity_structure": "BALANCED_LIQUIDITY_CORE", "nearest_bsl": 72000.0, "nearest_ssl": 68000.0},
            "macro_4h": {"regime": "MACRO_BULLISH", "rsi_14": 58.0},
            "macro_daily": {"regime": "DAILY_BULLISH", "rsi_14": 56.0, "ema_21": 68500.0},
            "macro_weekly": {"regime": "WEEKLY_BULLISH", "rsi_14": 54.0},
            "macro_monthly": {"regime": "MONTHLY_BULLISH", "monthly_open": 67000.0},
            "volume_profile": {
                "poc": 69900.0,
                "vah": 70500.0,
                "val": 69400.0,
                "stance": "INSIDE_VA"
            },
            "cvd": {
                "current_cvd": 1500.0,
                "cvd_trend": "RISING_ACCUMULATION",
                "divergence": "BULLISH_ABSORPTION_DIV",
                "cvd_slope": 25.0
            },
            "order_book_imbalance": {
                "obi_ratio": 0.35,
                "imbalance_status": "HEAVY_BID_IMBALANCE",
                "depth_ratio": 2.1,
                "bid_depth": 350.0,
                "ask_depth": 165.0
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "strategy": "Institutional_Order_Flow_Accumulation",
                "score": 85,
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,
                "take_profit_price": 71600.0,
                "stop_distance": 600.0,
                "atr_14": 400.0,
                "atr_stop_multiple": 1.50,
                "planned_rr_ratio": 2.67,
                "thesis": "Bullish Order Flow Accumulation"
            }
        }

        setup = agent.evaluate_setup(analysis)
        self.assertIsNotNone(setup)
        self.assertIn("order_flow_profile", setup)
        self.assertIn("order_flow_detail", setup["confluence"])
        self.assertIn("BULLISH CVD ABSORPTION DIVERGENCE", setup["thesis"])
        self.assertIn("HEAVY BID BOOK SUPPORT", setup["thesis"])

    def test_risk_gatekeeper_order_flow_veto(self):
        """Test RiskGatekeeper vetoes trades when order book imbalance strongly opposes trade direction."""
        mock_client = MagicMock()
        mock_client.get_wallet_balances.return_value = {
            "success": True,
            "result": [{"asset_symbol": "USDT", "balance": 500.0, "available_balance": 500.0}]
        }
        mock_client.get_positions.return_value = {"success": True, "result": []}
        mock_client.get_product_info.return_value = {
            "contract_value": "0.001",
            "lot_size": 1,
            "maintenance_margin_rate": "0.01"
        }
        mock_client.get_ticker.return_value = {"bid": 70000.0, "ask": 70010.0}

        mock_risk_mgr = MagicMock(spec=RiskManager)
        mock_risk_mgr.check_circuit_breaker.return_value = {"can_trade": True}
        mock_risk_mgr.max_dollar_risk_per_trade = 3.0
        mock_risk_mgr.max_risk_per_trade_pct = 0.02
        mock_risk_mgr.max_allowed_leverage = 25
        mock_risk_mgr.min_reward_to_risk = 2.0

        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=mock_risk_mgr)

        # Setup trying to BUY, but order book has extreme sell dominance (OBI = -0.65)
        toxic_setup = {
            "symbol": "BTCUSD",
            "side": "buy",
            "strategy_name": "Toxic_Long_Into_Ask_Wall",
            "entry_price": 70000.0,
            "stop_loss_price": 69400.0,
            "take_profit_price": 71600.0,
            "score": 88,
            "thesis": "Long attempt against massive sell wall",
            "atr_14": 400.0,
            "atr_stop_multiple": 1.50,
            "order_flow_profile": {
                "order_book_imbalance": {
                    "obi_ratio": -0.65,
                    "imbalance_status": "HEAVY_ASK_IMBALANCE"
                }
            }
        }

        res = gatekeeper.evaluate_candidate(toxic_setup)
        self.assertEqual(res.get("gate_decision"), "REJECTED")
        self.assertIn("Order Book Imbalance Veto", res.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
