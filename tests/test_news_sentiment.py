"""
Unit tests for NewsSentimentAgent, catalyst classification, and risk integration.
"""

import unittest
from multiagent_team.news_sentiment_agent import NewsSentimentAgent, NewsArticle, MarketSentimentReport


class TestNewsSentimentAgent(unittest.TestCase):
    def setUp(self):
        self.agent = NewsSentimentAgent()

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


if __name__ == "__main__":
    unittest.main()

