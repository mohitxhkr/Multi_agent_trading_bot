"""
Tests for Smart Money Concepts (SMC) Fair Value Gap (FVG) Engine:
1. Bullish FVG Detection (Candle 3 Low > Candle 1 High).
2. Bearish FVG Detection (Candle 3 High < Candle 1 Low).
3. 50% Consequent Encroachment (CE) Midpoint Calculation.
4. Mitigation Life-cycle: UNTESTED -> RETESTING -> CE_RETESTED -> MITIGATED.
5. Intraday Retest & Institutional Wick Rejection Detection.
6. StrategyAgent FVG Confluence Scoring & Overhead/Support Penalty Logic.
7. RiskGatekeeper FVG Profile Validation.
"""

import unittest
from unittest.mock import MagicMock
from src.technical_analysis import detect_fair_value_gaps, analyze_market_structure
from multiagent_team.strategy_agent import StrategyAgent
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent


class TestFairValueGapEngine(unittest.TestCase):

    def test_bullish_fvg_detection_and_ce(self):
        """Test accurate detection of a 3-candle Bullish FVG and 50% Consequent Encroachment."""
        # Candle 0: High = 100.0
        # Candle 1: Big green expansion bar (Low = 99.0, High = 112.0)
        # Candle 2: Low = 104.0 (Leaves gap between 100.0 and 104.0)
        # Candle 3: Stays above (Low = 106.0, High = 115.0)
        opens = [95.0, 100.0, 108.0, 107.0]
        highs = [100.0, 112.0, 110.0, 115.0]
        lows = [94.0, 99.0, 104.0, 106.0]
        closes = [99.0, 111.0, 109.0, 114.0]

        res = detect_fair_value_gaps(highs, lows, closes, opens=opens, min_gap_pct=0.01)

        self.assertGreater(len(res["bullish_fvgs"]), 0)
        bfvg = res["bullish_fvgs"][0]
        self.assertEqual(bfvg["type"], "BULLISH_FVG")
        self.assertEqual(bfvg["gap_bottom"], 100.0)  # Candle 0 High
        self.assertEqual(bfvg["gap_top"], 104.0)     # Candle 2 Low
        self.assertEqual(bfvg["ce"], 102.0)          # 50% CE: (100 + 104) / 2
        self.assertFalse(bfvg["mitigated"])
        self.assertEqual(bfvg["state"], "UNTESTED")

    def test_bearish_fvg_detection_and_ce(self):
        """Test accurate detection of a 3-candle Bearish FVG and 50% Consequent Encroachment."""
        # Candle 0: Low = 100.0
        # Candle 1: Big red dump bar (High = 101.0, Low = 88.0)
        # Candle 2: High = 95.0 (Leaves gap between 95.0 and 100.0)
        # Candle 3: Stays below (High = 94.0, Low = 86.0)
        opens = [105.0, 100.0, 92.0, 93.0]
        highs = [106.0, 101.0, 95.0, 94.0]
        lows = [100.0, 88.0, 90.0, 86.0]
        closes = [101.0, 89.0, 91.0, 87.0]

        res = detect_fair_value_gaps(highs, lows, closes, opens=opens, min_gap_pct=0.01)

        self.assertGreater(len(res["bearish_fvgs"]), 0)
        bfvg = res["bearish_fvgs"][0]
        self.assertEqual(bfvg["type"], "BEARISH_FVG")
        self.assertEqual(bfvg["gap_bottom"], 95.0)   # Candle 2 High
        self.assertEqual(bfvg["gap_top"], 100.0)     # Candle 0 Low
        self.assertEqual(bfvg["ce"], 97.5)           # 50% CE: (95 + 100) / 2
        self.assertFalse(bfvg["mitigated"])
        self.assertEqual(bfvg["state"], "UNTESTED")

    def test_fvg_mitigation_lifecycle(self):
        """Test the lifecycle from UNTESTED -> RETESTING -> CE_RETESTED -> MITIGATED."""
        # 1. Formation (Candles 0-2)
        # Candle 0: High = 100.0
        # Candle 1: Expansion High = 112.0
        # Candle 2: Low = 106.0 (Gap: [100.0, 106.0], CE = 103.0)
        # 2. Shallow Retest (Candle 3: Low = 105.0 > CE)
        opens = [95.0, 100.0, 108.0, 107.0]
        highs = [100.0, 112.0, 110.0, 108.0]
        lows = [94.0, 99.0, 106.0, 105.0]
        closes = [99.0, 111.0, 109.0, 107.0]

        res_retest = detect_fair_value_gaps(highs, lows, closes, opens=opens, min_gap_pct=0.01)
        fvg1 = res_retest["bullish_fvgs"][0]
        self.assertTrue(fvg1["tested"])
        self.assertFalse(fvg1["ce_tested"])
        self.assertEqual(fvg1["state"], "RETESTING")

        # 3. CE Retest (Candle 4: Low dips to 102.0 <= CE 103.0, but closes at 104.5)
        opens.append(107.0)
        highs.append(108.0)
        lows.append(102.0)
        closes.append(104.5)

        res_ce = detect_fair_value_gaps(highs, lows, closes, opens=opens, min_gap_pct=0.01)
        fvg2 = res_ce["bullish_fvgs"][0]
        self.assertTrue(fvg2["ce_tested"])
        self.assertFalse(fvg2["mitigated"])
        self.assertEqual(fvg2["state"], "CE_RETESTED")

        # 4. Mitigation / Invalidation (Candle 5: Closes at 98.0 below gap bottom 100.0)
        opens.append(104.5)
        highs.append(105.0)
        lows.append(97.0)
        closes.append(98.0)

        res_mitigated = detect_fair_value_gaps(highs, lows, closes, opens=opens, min_gap_pct=0.01)
        fvg3 = res_mitigated["bullish_fvgs"][0]
        self.assertTrue(fvg3["mitigated"])
        self.assertEqual(fvg3["state"], "MITIGATED")

    def test_active_retest_and_wick_rejection(self):
        """Test detection of an active FVG retest on the current candle with confirmed wick rejection."""
        # Formation at candles 0-2 (Gap: [100.0, 108.0], CE = 104.0)
        opens = [95.0, 100.0, 110.0]
        highs = [100.0, 115.0, 112.0]
        lows = [94.0, 99.0, 108.0]
        closes = [99.0, 114.0, 111.0]

        # Candle 3: Stays higher
        opens.append(111.0); highs.append(116.0); lows.append(110.0); closes.append(115.0)
        
        # Candle 4 (Current bar): Retests FVG at CE 103.0, strong lower wick bounce to close at 107.0
        # Lower wick = 106.0 - 102.0 = 4.0 out of range 6.0 (66% rejection wick!)
        opens.append(106.0)
        highs.append(108.0)
        lows.append(102.0)
        closes.append(107.0)

        res = detect_fair_value_gaps(highs, lows, closes, opens=opens, min_gap_pct=0.01)

        self.assertTrue(res["retest_active"])
        self.assertEqual(res["retest_type"], "BULLISH_FVG_RETEST")
        self.assertTrue(res["ce_tested"])
        self.assertTrue(res["wick_rejection"])
        self.assertEqual(res["bias"], "BULLISH")
        self.assertIn("Bullish FVG Retest", res["narrative"])

    def test_analyze_market_structure_includes_fvg(self):
        """Test that analyze_market_structure includes rich FVG analysis and metrics."""
        # Generate 25 candles with an embedded bullish FVG
        highs = [100.0 + i for i in range(25)]
        lows = [95.0 + i for i in range(25)]
        opens = [97.0 + i for i in range(25)]
        closes = [99.0 + i for i in range(25)]
        volumes = [1000.0 for _ in range(25)]

        # Inject an FVG at index 18
        highs[18] = 116.0  # Candle 18 High
        opens[19] = 117.0
        highs[19] = 126.0  # Big expansion
        lows[19] = 117.0
        closes[19] = 125.0
        lows[20] = 119.0   # Candle 20 Low (leaves gap [116.0, 119.0])
        highs[20] = 128.0

        candles_dict = {'o': opens, 'h': highs, 'l': lows, 'c': closes, 'v': volumes}
        res = analyze_market_structure(candles_dict)

        self.assertIn("fvg", res)
        fvg_data = res["fvg"]
        self.assertIn("bullish_fvgs", fvg_data)
        self.assertIn("bearish_fvgs", fvg_data)
        self.assertIn("active_bullish_count", fvg_data)
        self.assertIn("narrative", fvg_data)

    def test_strategy_agent_fvg_scoring_and_penalties(self):
        """Test that StrategyAgent awards points for FVG CE retests and penalizes overhead unmitigated FVG."""
        agent = StrategyAgent()
        agent.adaptive_learner = MagicMock()
        agent.adaptive_learner.get_pattern_adjustment.return_value = {"can_trade": True, "score_adjustment": 0}

        # Mock setup with active Bullish FVG Retest and CE Tap
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
            "fvg": {
                "retest_active": True,
                "retest_type": "BULLISH_FVG_RETEST",
                "ce_tested": True,
                "wick_rejection": True,
                "active_bullish_count": 2,
                "active_bearish_count": 0,
                "nearest_bullish_fvg": {"gap_top": 70100.0, "gap_bottom": 69600.0, "ce": 69850.0},
                "nearest_bearish_fvg": None,
                "bullish_fvg_distance_pct": 0.15,
                "bearish_fvg_distance_pct": None,
                "active_retest_fvg": {"gap_top": 70100.0, "gap_bottom": 69600.0, "ce": 69850.0}
            },
            "high_probability_setup": {
                "qualified": True,
                "side": "buy",
                "strategy": "Institutional_SMC_Bullish_FVG_Retest",
                "score": 85,
                "entry_price": 70000.0,
                "stop_loss_price": 69400.0,
                "take_profit_price": 71600.0,
                "stop_distance": 600.0,
                "atr_14": 400.0,
                "atr_stop_multiple": 1.50,
                "planned_rr_ratio": 2.67,
                "thesis": "SMC FVG Retest with confirmed CE defense"
            }
        }

        setup = agent.evaluate_setup(analysis)
        self.assertIsNotNone(setup)
        self.assertIn("fvg_profile", setup)
        self.assertEqual(setup["fvg_profile"]["retest_type"], "BULLISH_FVG_RETEST")
        self.assertTrue(setup["fvg_profile"]["ce_tested"])
        self.assertIn("fvg_detail", setup["confluence"])
        self.assertIn("BULLISH FVG CE RETEST", setup["thesis"])

    def test_risk_gatekeeper_fvg_profile_preservation(self):
        """Test that RiskGatekeeper preserves fvg_profile in the approved trade specification."""
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

        from src.risk_manager import RiskManager
        mock_risk_mgr = MagicMock(spec=RiskManager)
        mock_risk_mgr.check_circuit_breaker.return_value = {"can_trade": True}
        mock_risk_mgr.max_dollar_risk_per_trade = 3.0
        mock_risk_mgr.max_risk_per_trade_pct = 0.02
        mock_risk_mgr.max_allowed_leverage = 25
        mock_risk_mgr.min_reward_to_risk = 2.0

        gatekeeper = RiskGatekeeperAgent(client=mock_client, risk_manager=mock_risk_mgr)

        setup = {
            "symbol": "BTCUSD",
            "side": "buy",
            "strategy_name": "Institutional_SMC_Bullish_FVG_Retest",
            "entry_price": 70000.0,
            "stop_loss_price": 69400.0,
            "take_profit_price": 71600.0,
            "score": 92,
            "thesis": "SMC Bullish FVG CE Retest with wick defense",
            "atr_14": 400.0,
            "atr_stop_multiple": 1.50,
            "confluence": {
                "fvg_detail": "Retest: BULLISH_FVG_RETEST (CE: YES | Wick: YES)"
            },
            "fvg_profile": {
                "retest_type": "BULLISH_FVG_RETEST",
                "ce_tested": True,
                "wick_rejection": True,
                "active_bullish_count": 1,
                "active_bearish_count": 0,
                "nearest_bullish_fvg": {"gap_top": 70050.0, "gap_bottom": 69500.0, "ce": 69775.0},
                "nearest_bearish_fvg": None
            }
        }

        vetted = gatekeeper.evaluate_candidate(setup)
        self.assertEqual(vetted.get("gate_decision"), "APPROVED")
        self.assertIn("fvg_profile", vetted)
        self.assertEqual(vetted["fvg_profile"]["retest_type"], "BULLISH_FVG_RETEST")
        self.assertTrue(vetted["fvg_profile"]["ce_tested"])
        self.assertTrue(vetted["fvg_profile"]["wick_rejection"])


if __name__ == "__main__":
    unittest.main()
