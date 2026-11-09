"""
Unit tests for NewsSentimentAgent, catalyst classification, and risk integration.
"""

import os
import unittest
from multiagent_team.news_sentiment_agent import NewsSentimentAgent, NewsArticle, MarketSentimentReport


class TestNewsSentimentAgent(unittest.TestCase):
    def setUp(self):
        self.agent = NewsSentimentAgent()
        self.agent.posted_news_cache = set()

    def test_bullish_headline_classification(self):
        item = {
            "title": "Bitcoin surges to new record high after massive institutional ETF approval and record inflows",
            "summary": "BlackRock spot ETF breaks records as sovereign wealth funds accumulate.",
            "source": "CoinDesk",
            "link": "https://example.com/btc-etf",
            "published_at": "2026-11-08T00:00:00Z"
        }
        art = self.agent.analyze_headline(item)
        self.assertGreater(art.sentiment_score, 0.3)
        self.assertIn(art.sentiment_label, ["BULLISH", "VERY_BULLISH"])
        self.assertEqual(art.catalyst_category, "INSTITUTIONAL")
        self.assertIn("BTC", art.affected_assets)
        self.assertEqual(art.impact_rating, "HIGH")

    def test_bearish_exploit_classification(self):
        item = {
            "title": "Major crypto exchange hacked, $200M stolen in massive protocol exploit, withdrawals halted",
            "summary": "Criminal hackers drain customer funds as emergency pause is initiated.",
            "source": "CoinTelegraph",
            "link": "https://example.com/hack",
            "published_at": "2026-11-08T00:00:00Z"
        }
        art = self.agent.analyze_headline(item)
        self.assertLess(art.sentiment_score, -0.3)
        self.assertIn(art.sentiment_label, ["BEARISH", "VERY_BEARISH"])
        self.assertEqual(art.catalyst_category, "SECURITY_EXPLOIT")
        self.assertEqual(art.impact_rating, "HIGH")

    def test_fear_and_greed_fallback_safety(self):
        res = self.agent.fetch_fear_and_greed_index()
        self.assertIn("value", res)
        self.assertIn("classification", res)
        self.assertIsInstance(res["value"], int)

    def test_critical_market_mover_identification(self):
        # Critical event: SEC ETF approval
        critical_item = {
            "title": "SEC approves first spot Solana ETF in historic regulatory breakthrough",
            "summary": "The SEC has granted approval for spot SOL ETFs today.",
            "source": "CoinDesk",
            "link": "https://example.com/sol-etf",
            "published_at": "2026-11-08T00:00:00Z"
        }
        art_crit = self.agent.analyze_headline(critical_item)
        self.assertTrue(art_crit.is_critical_market_mover)

        # Non-critical event: Routine market commentary / prediction
        noise_item = {
            "title": "Crypto trader explains why Ethereum could outpace Solana according to chart patterns",
            "summary": "A popular market analyst shares opinions on future trading setups.",
            "source": "CoinTelegraph",
            "link": "https://example.com/opinion",
            "published_at": "2026-11-08T00:00:00Z"
        }
        art_noise = self.agent.analyze_headline(noise_item)
        self.assertFalse(art_noise.is_critical_market_mover)

    def test_telegram_dispatch_filters_routine_news(self):
        class MockNotifier:
            def __init__(self):
                self.enabled = True
                self.messages = []
            def send_message(self, msg):
                self.messages.append(msg)
                return True

        notifier = MockNotifier()
        # Mock cached report containing 1 critical mover and 1 routine headline
        art_crit = self.agent.analyze_headline({
            "title": "Major bridge hacked, $150M stolen in massive security exploit",
            "summary": "Hackers drained funds from cross-chain bridge.",
            "source": "CoinDesk",
            "link": "https://example.com/bridge-hack",
            "published_at": "2026-11-08T00:00:00Z"
        })
        art_routine = self.agent.analyze_headline({
            "title": "Top 5 altcoins to watch this weekend according to analysts",
            "summary": "Routine weekend market outlook.",
            "source": "Decrypt",
            "link": "https://example.com/routine",
            "published_at": "2026-11-08T00:00:00Z"
        })

        self.agent.cached_report = MarketSentimentReport(
            timestamp="2026-11-08 00:00:00 UTC",
            composite_score=-0.25,
            sentiment_regime="FEAR",
            total_articles_analyzed=2,
            top_high_impact_news=[art_crit, art_routine],
            critical_market_movers=[art_crit],
            trading_posture_recommendation="DEFENSIVE",
            leverage_risk_multiplier=0.85
        )

        sent_count = self.agent.dispatch_telegram_news_updates(notifier, max_alerts_per_cycle=5)
        self.assertEqual(sent_count, 1)
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("CRITICAL MARKET-MOVING CRYPTO ALERT", notifier.messages[0])
        self.assertIn("Major bridge hacked", notifier.messages[0])

    def test_trade_proposal_card_includes_sentiment_and_fear_greed(self):
        from src.telegram_bot import TelegramConfirmationBot
        bot = TelegramConfirmationBot(token="MOCK_TOKEN", authorized_chat_ids=["123456"])
        
        trade_spec = {
            "trade_id": "prop_test_001",
            "symbol": "BTCUSD",
            "side": "BUY",
            "entry_price": 70000.0,
            "stop_loss_price": 69000.0,
            "take_profit_price": 73000.0,
            "reward_to_risk_ratio": 3.0,
            "contracts": 1,
            "leverage": 25,
            "required_margin_usd": 28.0,
            "dollar_risk_usd": 2.50,
            "strategy": "Bullish Order Block",
            "score": 92,
            "sentiment_report": {
                "fear_greed_index": 78,
                "fear_greed_classification": "Extreme Greed",
                "composite_score": 0.42,
                "sentiment_regime": "EXTREME_GREED",
                "asset_sentiment_map": {
                    "BTC": {"sentiment": "BULLISH", "score": 0.55}
                }
            }
        }

        # Mock send_message and edit_message_text
        captured_messages = []
        bot.send_message = lambda text, reply_markup=None: (captured_messages.append(text), 999)[1]
        bot.edit_message_text = lambda *args, **kwargs: True

        import unittest.mock as mock
        import itertools
        time_gen = itertools.count(1000.0, 50.0)
        with mock.patch("time.time", side_effect=lambda: next(time_gen)):
            bot.request_trade_confirmation(trade_spec, timeout_seconds=10)

        self.assertEqual(len(captured_messages), 1)
        card_text = captured_messages[0]
        self.assertIn("MARKET SENTIMENT &amp; MACRO PULSE", card_text)
        self.assertIn("78/100 (Extreme Greed)", card_text)
        self.assertIn("BULLISH BIAS (+0.42)", card_text)
        self.assertIn("BTC Sentiment: BULLISH", card_text)

    def test_daily_morning_briefing_formatting(self):
        art1 = self.agent.analyze_headline({
            "title": "Bitcoin surges above $75K as ETF inflows hit new records",
            "summary": "Massive institutional buying drives Bitcoin past previous resistance.",
            "source": "CoinDesk",
            "link": "https://example.com/btc",
            "published_at": "2026-11-09T00:00:00Z"
        })
        art2 = self.agent.analyze_headline({
            "title": "Solana foundation addresses recent exploit and outlines protocol upgrade",
            "summary": "Developers publish security roadmap following bridge incident.",
            "source": "CoinTelegraph",
            "link": "https://example.com/sol",
            "published_at": "2026-11-09T00:00:00Z"
        })

        mock_report = MarketSentimentReport(
            timestamp="2026-11-09 10:00:00 UTC",
            composite_score=0.35,
            sentiment_regime="GREED",
            fear_greed_index=72,
            fear_greed_classification="Greed",
            total_articles_analyzed=50,
            bullish_articles_count=20,
            bearish_articles_count=10,
            neutral_articles_count=20,
            top_high_impact_news=[art1, art2],
            critical_market_movers=[art1],
            trading_posture_recommendation="CONSTRUCTIVE_EXPANSION: Strong institutional momentum.",
            leverage_risk_multiplier=1.0
        )

        card = self.agent.format_daily_morning_briefing(mock_report)
        self.assertIn("DAILY CRYPTO MORNING BRIEFING", card)
        self.assertIn("TODAY'S MARKET SENTIMENT", card)
        self.assertIn("72/100 (Greed)", card)
        self.assertIn("TOP IMPORTANT CRYPTO NEWS", card)
        self.assertIn("Bitcoin surges above $75K", card)
        self.assertIn("MORNING SESSION GAMEPLAN", card)

    def test_daily_morning_briefing_dispatch(self):
        class MockNotifier:
            def __init__(self):
                self.enabled = True
                self.messages = []
            def send_message(self, msg, parse_mode="HTML"):
                self.messages.append(msg)
                return True

        notifier = MockNotifier()
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_state_path = tf.name

        import multiagent_team.news_sentiment_agent as nsa_mod
        old_state_file = nsa_mod.MORNING_NEWS_STATE_FILE
        try:
            nsa_mod.MORNING_NEWS_STATE_FILE = temp_state_path
            # Test force dispatch
            res = self.agent.check_and_dispatch_morning_briefing(notifier, force=True)
            self.assertTrue(res)
            self.assertEqual(len(notifier.messages), 1)
            self.assertIn("DAILY CRYPTO MORNING BRIEFING", notifier.messages[0])
        finally:
            nsa_mod.MORNING_NEWS_STATE_FILE = old_state_file
            if os.path.exists(temp_state_path):
                os.remove(temp_state_path)


if __name__ == "__main__":
    unittest.main()

