"""
News & Social Sentiment Intelligence Agent for Delta Exchange Multi-Agent Quantitative Bot.
Scrapes, parses, and analyzes breaking crypto news articles, RSS feeds, and social sentiment indicators
from across the internet (CoinDesk, CoinTelegraph, Decrypt, Google News, and Alternative.me Fear & Greed Index).

Translates global narrative catalysts and sentiment momentum into actionable bias for:
  - Agent 1 (Regime Analyst): Macro posture alignment
  - Agent 2 (Exposure Coach): Risk scaling during high-impact news
  - Agent 3 (Strategy Generator): Directional filtering & alpha validation
  - Agent 5 (Risk Gatekeeper): Dynamic leverage clamping & volatility buffers
  - Telegram Alerts: Real-time breaking news updates with estimated crypto market impact
"""

from typing import Dict, Any, List, Optional, Set
import os
import sys
import time
import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pydantic import BaseModel, Field

# Ensure UTF-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("news-sentiment-agent")

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
SENTIMENT_STATE_FILE = os.path.join(STATE_DIR, "market_sentiment_state.json")
POSTED_NEWS_CACHE_FILE = os.path.join(STATE_DIR, "posted_news_cache.json")


# -----------------------------------------------------------------------------
# Pydantic Schemas for Structured Sentiment Intelligence
# -----------------------------------------------------------------------------

class NewsArticle(BaseModel):
    id: str = Field(..., description="Unique hash ID of the article")
    title: str = Field(..., description="Headline of the article")
    source: str = Field(..., description="Publisher name (e.g. CoinDesk, CoinTelegraph, Bloomberg)")
    link: str = Field(..., description="Direct URL to article")
    published_at: str = Field(..., description="ISO 8601 published timestamp")
    sentiment_score: float = Field(..., description="Sentiment score from -1.0 (extreme bearish) to +1.0 (extreme bullish)")
    sentiment_label: str = Field(..., description="VERY_BULLISH, BULLISH, NEUTRAL, BEARISH, or VERY_BEARISH")
    impact_rating: str = Field(..., description="HIGH, MEDIUM, or LOW market impact")
    catalyst_category: str = Field(..., description="REGULATORY, MACRO_FED, INSTITUTIONAL, SECURITY_EXPLOIT, or MARKET_ACTION")
    affected_assets: List[str] = Field(default_factory=list, description="Target crypto assets (e.g. BTC, ETH, SOL)")
    summary: str = Field(..., description="Concise synopsis of the news item and its significance")
    is_critical_market_mover: bool = Field(default=False, description="True ONLY for tier-1 breaking market-moving catalysts (major hacks, ETF rulings, Fed rate moves, bankruptcy)")


class MarketSentimentReport(BaseModel):
    timestamp: str = Field(..., description="UTC generation timestamp")
    composite_score: float = Field(..., description="Normalized composite market sentiment (-1.0 to +1.0)")
    sentiment_regime: str = Field(..., description="EXTREME_FEAR, FEAR, NEUTRAL, GREED, or EXTREME_GREED")
    fear_greed_index: int = Field(default=50, description="Alternative.me Fear & Greed index (0-100)")
    fear_greed_classification: str = Field(default="Neutral", description="Fear & Greed verbal classification")
    total_articles_analyzed: int = Field(default=0, description="Total headlines evaluated")
    bullish_articles_count: int = Field(default=0, description="Count of bullish news items")
    bearish_articles_count: int = Field(default=0, description="Count of bearish news items")
    neutral_articles_count: int = Field(default=0, description="Count of neutral news items")
    top_high_impact_news: List[NewsArticle] = Field(default_factory=list, description="Top breaking high-impact articles")
    critical_market_movers: List[NewsArticle] = Field(default_factory=list, description="Strict tier-1 market-moving articles eligible for Telegram alerts")
    asset_sentiment_map: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Asset-specific sentiment breakdowns")
    trading_posture_recommendation: str = Field(..., description="Actionable guideline for execution agents")
    leverage_risk_multiplier: float = Field(default=1.0, description="Recommended leverage/risk scalar (0.5 to 1.0)")


# -----------------------------------------------------------------------------
# Institutional Sentiment & Catalyst Lexicon
# -----------------------------------------------------------------------------

BULLISH_KEYWORDS = {
    # High Impact Institutional Inflows & Adoption (+0.8 to +1.0)
    "etf approval": 1.0, "approved": 0.8, "approves": 0.8, "approval": 0.8, "record inflows": 0.9, "institutional inflow": 0.85,
    "blackrock": 0.7, "fidelity": 0.6, "microstrategy": 0.7, "saylor": 0.6,
    "strategic reserve": 1.0, "treasury reserve": 0.9, "sovereign adoption": 0.95,
    "rate cut": 0.85, "fed pivots": 0.8, "dovish": 0.75, "easing": 0.7,
    # Price Momentum & Breakouts (+0.5 to +0.8)
    "all-time high": 0.9, "ath": 0.85, "surge": 0.7, "surges": 0.7, "breakout": 0.75,
    "rally": 0.65, "rallies": 0.65, "soar": 0.75, "soars": 0.75, "skyrockets": 0.8,
    "bull market": 0.75, "bullish": 0.6, "gain": 0.5, "gains": 0.5, "accumulate": 0.6,
    "accumulation": 0.65, "whales buying": 0.75, "short squeeze": 0.7, "expansion": 0.6,
    # Regulatory Clarity & Wins (+0.7 to +1.0)
    "sec lawsuit dismissed": 0.95, "wins lawsuit": 0.9, "regulatory clarity": 0.8,
    "pro-crypto": 0.75, "partnership": 0.55, "upgrade": 0.5, "mainnet": 0.5
}

BEARISH_KEYWORDS = {
    # Severe Exploits, Hacks & Insolvency (-0.8 to -1.0)
    "hack": -0.9, "hacked": -0.95, "exploit": -0.85, "exploited": -0.9,
    "stolen": -0.85, "drain": -0.85, "drained": -0.9, "fraud": -0.9,
    "insolvent": -1.0, "insolvency": -1.0, "bankruptcy": -1.0, "bankrupt": -1.0,
    "pause withdrawals": -0.95, "halted withdrawals": -0.95, "scam": -0.85,
    # Regulatory Crackdowns & Lawsuits (-0.7 to -0.95)
    "sec lawsuit": -0.85, "sec charges": -0.85, "indicted": -0.9, "indictment": -0.9,
    "subpoena": -0.75, "investigation": -0.7, "criminal charges": -0.95, "sanction": -0.85,
    "sanctions": -0.85, "ban": -0.9, "banned": -0.9, "crackdown": -0.8,
    "rate hike": -0.8, "hawkish": -0.75, "tightening": -0.7, "cpi hot": -0.75,
    # Price Collapse & Capitulation (-0.5 to -0.8)
    "crash": -0.85, "crashes": -0.85, "plunge": -0.75, "plunges": -0.75,
    "dump": -0.7, "dumps": -0.7, "drop": -0.5, "drops": -0.5,
    "liquidation cascade": -0.8, "bear market": -0.75, "bearish": -0.6,
    "capitulation": -0.8, "sell-off": -0.65, "outflows": -0.65, "delist": -0.8
}

ASSET_REGEX_MAP = {
    "BTC": [r"\bbtc\b", r"\bbitcoin\b", r"\bsatoshi\b"],
    "ETH": [r"\beth\b", r"\bethereum\b", r"\bvitalik\b", r"\bether\b"],
    "SOL": [r"\bsol\b", r"\bsolana\b"],
    "XRP": [r"\bxrp\b", r"\bripple\b"],
    "DOGE": [r"\bdoge\b", r"\bdogecoin\b"],
    "GOLD": [r"\bgold\b", r"\bpaxg\b", r"\bxau\b"],
    "STABLECOIN": [r"\busdt\b", r"\busdc\b", r"\btether\b"]
}

# Strict Tier-1 Market-Moving Catalyst Filter (Strictly for Telegram Notifications)
# General/routine news is utilized internally by agents, but only true market movers alert Telegram
CRITICAL_MARKET_MOVER_PHRASES = [
    # Tier-1 Regulatory & ETF Decisions
    "etf approved", "etf approval", "etf rejected", "sec approved", "sec approves", "sec rejects",
    "spot etf", "sec lawsuit", "sec charges", "criminal charges", "indictment", "indicted",
    "subpoena", "ban", "banned", "crackdown", "sanction", "sanctions", "sanctioned",
    # Tier-1 Macroeconomic Central Bank Events
    "rate cut", "rate hike", "fed cut", "fed hike", "interest rate cut", "interest rate hike",
    "fomc", "cpi inflation spike", "cpi inflation drops",
    # Severe Protocol Exploits & Exchange Insolvency
    "hack", "hacked", "exploit", "exploited", "stolen", "drained", "drain",
    "insolvent", "insolvency", "bankruptcy", "bankrupt", "chapter 11",
    "halt withdrawals", "pause withdrawals", "halted withdrawals", "paused withdrawals", "freeze withdrawals",
    # Sovereign & Large Scale Institutional Adoption
    "strategic bitcoin reserve", "strategic reserve", "sovereign adoption", "legal tender",
    # Extreme Market Disruption
    "flash crash", "liquidation cascade", "circuit breaker", "all-time high", "new ath"
]

CLICKBAIT_NOISE_PHRASES = [
    "here's why", "here is why", "why bitcoin", "what happened in crypto", "price prediction",
    "analyst says", "analyst predicts", "expert predicts", "top 5", "top 3", "could reach",
    "might surge", "could hit", "meme coin", "opinion", "explainer", "guide", "how to",
    "crypto portfolio", "should you buy", "here's what", "here is what"
]


# -----------------------------------------------------------------------------
# News Sentiment Agent Implementation
# -----------------------------------------------------------------------------

class NewsSentimentAgent:
    """
    Autonomous Internet News & Social Sentiment Intelligence Agent.
    Aggregates news from CoinDesk, CoinTelegraph, Decrypt, Google News, and Alternative.me.
    Calculates multi-asset sentiment, macro catalyst classification, and market impact.
    """

    RSS_FEEDS = {
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "CoinTelegraph": "https://cointelegraph.com/rss",
        "Decrypt": "https://decrypt.co/feed",
        "Google News Crypto": "https://news.google.com/rss/search?q=crypto+OR+bitcoin+when:24h&hl=en-US&gl=US&ceid=US:en"
    }

    FEAR_GREED_API = "https://api.alternative.me/fng/?limit=1"

    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        os.makedirs(STATE_DIR, exist_ok=True)
        self.posted_news_cache: Set[str] = self._load_posted_news_cache()
        self.cached_report: Optional[MarketSentimentReport] = self._load_cached_report()

    def _load_posted_news_cache(self) -> Set[str]:
        """Load set of already notified news IDs to avoid duplicate Telegram spam."""
        if os.path.exists(POSTED_NEWS_CACHE_FILE):
            try:
                with open(POSTED_NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("posted_ids", []))
            except Exception as e:
                logger.warning(f"Failed to read posted news cache: {e}")
        return set()

    def _save_posted_news_cache(self) -> None:
        """Persist posted news IDs."""
        try:
            # Retain only the most recent 1,000 IDs to keep state file lean
            recent_ids = list(self.posted_news_cache)[-1000:]
            with open(POSTED_NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"posted_ids": recent_ids, "last_updated": datetime.now(timezone.utc).isoformat()}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save posted news cache: {e}")

    def _load_cached_report(self) -> Optional[MarketSentimentReport]:
        """Load latest sentiment report from disk."""
        if os.path.exists(SENTIMENT_STATE_FILE):
            try:
                with open(SENTIMENT_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return MarketSentimentReport(**data)
            except Exception as e:
                logger.warning(f"Failed to parse cached sentiment state: {e}")
        return None

    def _save_report(self, report: MarketSentimentReport) -> None:
        """Persist latest sentiment report to disk."""
        try:
            with open(SENTIMENT_STATE_FILE, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))
            self.cached_report = report
        except Exception as e:
            logger.error(f"Failed to save market sentiment state: {e}")

    # -------------------------------------------------------------------------
    # Scraping & Data Ingestion
    # -------------------------------------------------------------------------

    def fetch_fear_and_greed_index(self) -> Dict[str, Any]:
        """Fetch Alternative.me Fear & Greed Index."""
        try:
            req = urllib.request.Request(self.FEAR_GREED_API, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                entry = data.get("data", [])[0]
                return {
                    "value": int(entry.get("value", 50)),
                    "classification": entry.get("value_classification", "Neutral")
                }
        except Exception as e:
            logger.warning(f"NewsSentimentAgent: Fear & Greed API unavailable: {e}. Defaulting to 50 (Neutral).")
            return {"value": 50, "classification": "Neutral"}

    def fetch_rss_feed(self, source_name: str, url: str) -> List[Dict[str, str]]:
        """Fetch and parse an RSS feed with fail-safe error handling."""
        articles = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                xml_data = resp.read()
                root = ET.fromstring(xml_data)
                items = root.findall(".//item")
                for item in items[:15]:  # Take top 15 most recent
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_elem = item.find("pubDate")
                    desc_elem = item.find("description")

                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                    desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

                    # Clean basic HTML tags from description
                    clean_desc = re.sub(r"<[^>]+>", "", desc)

                    if title:
                        articles.append({
                            "source": source_name,
                            "title": title,
                            "link": link,
                            "published_at": pub_date or datetime.now(timezone.utc).isoformat(),
                            "summary": clean_desc[:250] if clean_desc else title
                        })
        except Exception as e:
            logger.warning(f"NewsSentimentAgent: Failed to fetch feed '{source_name}': {e}")
        return articles

    def collect_all_news(self) -> List[Dict[str, str]]:
        """Collect news from all registered RSS channels."""
        all_news = []
        for src, url in self.RSS_FEEDS.items():
            feed_items = self.fetch_rss_feed(src, url)
            all_news.extend(feed_items)
            logger.info(f"NewsSentimentAgent: Ingested {len(feed_items)} headlines from {src}.")
        return all_news

    # -------------------------------------------------------------------------
    # Sentiment & Catalyst Analysis Engine
    # -------------------------------------------------------------------------

    def analyze_headline(self, raw_item: Dict[str, str]) -> NewsArticle:
        """
        Analyze a single news article for sentiment polarity, market impact,
        catalyst category, and target assets.
        """
        title = raw_item.get("title", "")
        summary = raw_item.get("summary", "")
        source = raw_item.get("source", "Crypto News")
        link = raw_item.get("link", "")
        published_at = raw_item.get("published_at", "")

        combined_text = f"{title} {summary}".lower()
        clean_words = set(re.findall(r"\b[a-z]{3,}\b", combined_text))

        # 1. Detect Affected Assets
        affected = []
        for asset, regex_list in ASSET_REGEX_MAP.items():
            for r in regex_list:
                if re.search(r, combined_text):
                    affected.append(asset)
                    break
        if not affected:
            affected = ["BTC", "GLOBAL_CRYPTO"]

        # 2. Sentiment Scoring
        score = 0.0
        hits_count = 0

        # Multi-word phrase matches first
        for phrase, weight in BULLISH_KEYWORDS.items():
            if " " in phrase and phrase in combined_text:
                score += weight
                hits_count += 1
        for phrase, weight in BEARISH_KEYWORDS.items():
            if " " in phrase and phrase in combined_text:
                score += weight
                hits_count += 1

        # Single word matches
        for word, weight in BULLISH_KEYWORDS.items():
            if " " not in word and word in clean_words:
                score += weight
                hits_count += 1
        for word, weight in BEARISH_KEYWORDS.items():
            if " " not in word and word in clean_words:
                score += weight
                hits_count += 1

        normalized_score = max(-1.0, min(1.0, score / max(1, hits_count))) if hits_count > 0 else 0.0

        # Sentiment Label
        if normalized_score >= 0.50:
            sentiment_label = "VERY_BULLISH"
        elif normalized_score >= 0.15:
            sentiment_label = "BULLISH"
        elif normalized_score <= -0.50:
            sentiment_label = "VERY_BEARISH"
        elif normalized_score <= -0.15:
            sentiment_label = "BEARISH"
        else:
            sentiment_label = "NEUTRAL"

        # 3. Catalyst Classification
        if any(w in combined_text for w in ["sec", "cftc", "lawsuit", "subpoena", "court", "ruling", "regulation", "bill", "ban"]):
            catalyst_cat = "REGULATORY"
        elif any(w in combined_text for w in ["fed", "powell", "inflation", "rate cut", "interest rate", "cpi", "macro", "treasury"]):
            catalyst_cat = "MACRO_FED"
        elif any(w in combined_text for w in ["hack", "exploit", "stolen", "drain", "insolvent", "fraud", "bankruptcy", "scam"]):
            catalyst_cat = "SECURITY_EXPLOIT"
        elif any(w in combined_text for w in ["etf", "blackrock", "fidelity", "institution", "saylor", "microstrategy", "inflow"]):
            catalyst_cat = "INSTITUTIONAL"
        elif any(w in combined_text for w in ["surge", "plunge", "crash", "rally", "liquidation", "short squeeze", "ath"]):
            catalyst_cat = "MARKET_ACTION"
        else:
            catalyst_cat = "GENERAL_CRYPTO"

        # 4. Market Impact Rating
        if catalyst_cat in ("SECURITY_EXPLOIT", "REGULATORY", "MACRO_FED") and abs(normalized_score) >= 0.40:
            impact = "HIGH"
        elif "etf" in combined_text or abs(normalized_score) >= 0.60:
            impact = "HIGH"
        elif abs(normalized_score) >= 0.25:
            impact = "MEDIUM"
        else:
            impact = "LOW"

        # 5. Critical Market-Mover Determination (Strictly for Telegram Alerts)
        is_noise = any(np in combined_text for np in CLICKBAIT_NOISE_PHRASES)
        is_critical = False
        if not is_noise and impact == "HIGH":
            has_phrase = any(cp in combined_text for cp in CRITICAL_MARKET_MOVER_PHRASES)
            has_etf_catalyst = "etf" in combined_text and any(w in combined_text for w in ["approv", "reject", "inflow", "filing"])
            has_security_breach = any(w in combined_text for w in ["hack", "exploit", "stolen", "drained", "insolvent", "bankruptcy"])

            if (has_phrase or has_etf_catalyst or has_security_breach) and abs(normalized_score) >= 0.40:
                is_critical = True
            elif catalyst_cat in ("SECURITY_EXPLOIT", "REGULATORY", "MACRO_FED") and abs(normalized_score) >= 0.65:
                is_critical = True

        # Unique ID generated from title & source
        import hashlib
        art_id = hashlib.sha256(f"{source}:{title}".encode("utf-8")).hexdigest()[:12]

        return NewsArticle(
            id=art_id,
            title=title,
            source=source,
            link=link,
            published_at=published_at,
            sentiment_score=round(normalized_score, 2),
            sentiment_label=sentiment_label,
            impact_rating=impact,
            catalyst_category=catalyst_cat,
            affected_assets=affected,
            summary=summary[:180] + ("..." if len(summary) > 180 else ""),
            is_critical_market_mover=is_critical
        )

    # -------------------------------------------------------------------------
    # Comprehensive Market Sentiment Report Generation
    # -------------------------------------------------------------------------

    def generate_sentiment_report(self) -> MarketSentimentReport:
        """
        Executes full sentiment pipeline:
        1. Fetch Fear & Greed Index
        2. Ingest RSS news streams from all channels
        3. Score individual articles
        4. Synthesize composite market sentiment score
        5. Formulate actionable trading recommendations for execution agents
        """
        logger.info("NewsSentimentAgent: Initiating global crypto sentiment scan...")
        fng = self.fetch_fear_and_greed_index()
        raw_items = self.collect_all_news()

        analyzed_articles: List[NewsArticle] = []
        for item in raw_items:
            art = self.analyze_headline(item)
            analyzed_articles.append(art)

        # Aggregate metrics
        bullish_count = sum(1 for a in analyzed_articles if a.sentiment_score > 0.10)
        bearish_count = sum(1 for a in analyzed_articles if a.sentiment_score < -0.10)
        neutral_count = len(analyzed_articles) - bullish_count - bearish_count

        # News polarity score (-1.0 to +1.0)
        if analyzed_articles:
            news_polarity = sum(a.sentiment_score for a in analyzed_articles) / len(analyzed_articles)
        else:
            news_polarity = 0.0

        # Fear & Greed normalized to -1.0 to +1.0 (50 = 0.0)
        fng_normalized = (fng["value"] - 50.0) / 50.0

        # Composite score: 60% news polarity + 40% Fear & Greed index
        composite = (news_polarity * 0.60) + (fng_normalized * 0.40)
        composite = max(-1.0, min(1.0, composite))

        # Regime determination
        if composite <= -0.45 or fng["value"] <= 20:
            regime = "EXTREME_FEAR"
        elif composite <= -0.15 or fng["value"] <= 40:
            regime = "FEAR"
        elif composite >= 0.45 or fng["value"] >= 80:
            regime = "EXTREME_GREED"
        elif composite >= 0.15 or fng["value"] >= 60:
            regime = "GREED"
        else:
            regime = "NEUTRAL"

        # Asset-specific sentiment mapping
        asset_sentiment_map = {}
        for target in ["BTC", "ETH", "SOL", "GOLD", "GLOBAL_CRYPTO"]:
            relevant = [a for a in analyzed_articles if target in a.affected_assets]
            if relevant:
                avg_sc = sum(a.sentiment_score for a in relevant) / len(relevant)
                asset_sentiment_map[target] = {
                    "score": round(avg_sc, 2),
                    "sentiment": "BULLISH" if avg_sc > 0.15 else ("BEARISH" if avg_sc < -0.15 else "NEUTRAL"),
                    "articles_count": len(relevant)
                }

        # Actionable Agent Recommendations & Risk Multiplier
        if regime == "EXTREME_FEAR":
            posture = "CAPITAL_PRESERVATION: Extreme panic in headlines. Clamping leverage to max 15x. Avoid aggressive long breakout buys; prioritize SMC discount order blocks or selective short trend continuation."
            risk_mult = 0.65
        elif regime == "FEAR":
            posture = "DEFENSIVE_SELECTIVE: Negative headline skew. Demand minimum 2.5:1 R:R. Widen stop loss buffer by 15% against liquidity spikes."
            risk_mult = 0.85
        elif regime == "EXTREME_GREED":
            posture = "EUPHORIA_CAUTION: Overheated market narrative. High risk of long squeeze or sharp reversal. Trail stops tightly at +1.0R; avoid FOMO tops."
            risk_mult = 0.80
        elif regime == "GREED":
            posture = "CONSTRUCTIVE_EXPANSION: Strong institutional momentum. FVG pullbacks and 15m bullish order blocks favored for long execution."
            risk_mult = 1.0
        else:
            posture = "NEUTRAL_BALANCED: Macro news equilibrium. Rely purely on technical market microstructure, EMA alignment, and VWAP volume profiles."
            risk_mult = 1.0

        # Filter top high-impact breaking news
        high_impact = [a for a in analyzed_articles if a.impact_rating == "HIGH"]
        # Deduplicate by title similarity
        seen_titles = set()
        deduped_high = []
        for a in high_impact:
            short_t = a.title[:35].lower()
            if short_t not in seen_titles:
                seen_titles.add(short_t)
                deduped_high.append(a)

        # Filter strictly tier-1 critical market-moving catalysts (major exploits, rate cuts, ETF rulings, insolvencies)
        # Internal agents use ALL analyzed articles (composite score, regime), but Telegram only alerts on critical catalysts
        critical_movers = [a for a in deduped_high if a.is_critical_market_mover]
        for a in analyzed_articles:
            if a.is_critical_market_mover and a not in critical_movers:
                short_t = a.title[:35].lower()
                if short_t not in seen_titles:
                    seen_titles.add(short_t)
                    critical_movers.append(a)

        report = MarketSentimentReport(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            composite_score=round(composite, 2),
            sentiment_regime=regime,
            fear_greed_index=fng["value"],
            fear_greed_classification=fng["classification"],
            total_articles_analyzed=len(analyzed_articles),
            bullish_articles_count=bullish_count,
            bearish_articles_count=bearish_count,
            neutral_articles_count=neutral_count,
            top_high_impact_news=deduped_high[:5],
            critical_market_movers=critical_movers[:5],
            asset_sentiment_map=asset_sentiment_map,
            trading_posture_recommendation=posture,
            leverage_risk_multiplier=risk_mult
        )

        self._save_report(report)
        logger.info(
            f"NewsSentimentAgent: Report generated. Composite: {report.composite_score:+.2f} ({report.sentiment_regime}) | "
            f"F&G: {report.fear_greed_index} ({report.fear_greed_classification}) | Articles: {len(analyzed_articles)} | Critical Movers: {len(critical_movers)}"
        )
        return report

    # -------------------------------------------------------------------------
    # Telegram Breaking News & Sentiment Alert Dispatcher
    # -------------------------------------------------------------------------

    def dispatch_telegram_news_updates(self, notifier: Any, max_alerts_per_cycle: int = 2, report: Optional[MarketSentimentReport] = None) -> int:
        """
        Dispatches real-time Telegram cards ONLY for strict tier-1 critical market-moving catalysts.
        All other news items are used internally by autonomous trading agents, preventing Telegram spam.
        Returns count of alerts successfully posted.
        """
        if not notifier or not getattr(notifier, "enabled", False):
            logger.info("NewsSentimentAgent: TelegramNotifier is not enabled. Skipping dispatch.")
            return 0

        target_report = report if report is not None else (self.cached_report or self.generate_sentiment_report())
        alerts_sent = 0

        # Strictly notify ONLY for genuine tier-1 critical market movers
        eligible_critical_news = [
            art for art in target_report.critical_market_movers
            if art.is_critical_market_mover
        ]

        if not eligible_critical_news:
            logger.debug("NewsSentimentAgent: No critical tier-1 market-moving news to broadcast to Telegram.")
            return 0

        for art in eligible_critical_news:
            if art.id in self.posted_news_cache:
                continue

            if alerts_sent >= max_alerts_per_cycle:
                break

            # Format the Telegram Critical Market-Mover Card
            sentiment_emoji = "🟢 BULLISH" if "BULLISH" in art.sentiment_label else ("🔴 BEARISH" if "BEARISH" in art.sentiment_label else "⚪ NEUTRAL")
            impact_badge = "🚨 CRITICAL MARKET-MOVER"
            assets_str = ", ".join(f"#{a}" for a in art.affected_assets)

            msg = (
                f"🚨 <b>[CRITICAL MARKET-MOVING CRYPTO ALERT]</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⭐ <b>EVENT SEVERITY:</b> <b><u>{impact_badge}</u></b>\n"
                f"🏷️ <b>CATALYST:</b> <code>{art.catalyst_category}</code> · <b>Source:</b> <i>{art.source}</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>Headline:</b> <b>{art.title}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Sentiment Polarity:</b> <b>{sentiment_emoji} ({art.sentiment_score:+.2f})</b>\n"
                f"🎯 <b>Affected Assets:</b> <code>{assets_str}</code>\n"
                f"📝 <b>Synopsis:</b> <i>{art.summary}</i>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 <b>AGENT POSTURE IMPACT:</b>\n"
                f"• <b>Risk Multiplier:</b> <code>{target_report.leverage_risk_multiplier:.2f}x</code>\n"
                f"• <b>Guidance:</b> <i>{target_report.trading_posture_recommendation.split(':')[0]}</i>\n"
                f"• <b>Fear &amp; Greed:</b> <code>{target_report.fear_greed_index}/100 ({target_report.fear_greed_classification})</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 <a href=\"{art.link}\">Read Full Article Source</a>"
            )

            try:
                success = notifier.send_message(msg)
                if success:
                    self.posted_news_cache.add(art.id)
                    alerts_sent += 1
                    logger.info(f"NewsSentimentAgent: Dispatched breaking news alert to Telegram: '{art.title[:50]}'")
            except Exception as e:
                logger.error(f"NewsSentimentAgent: Failed to dispatch Telegram news alert: {e}")

        if alerts_sent > 0:
            self._save_posted_news_cache()

        return alerts_sent

    def dispatch_sentiment_digest_to_telegram(self, notifier: Any) -> bool:
        """
        Send a comprehensive scheduled crypto sentiment digest card to Telegram.
        """
        if not notifier or not getattr(notifier, "enabled", False):
            return False

        report = self.generate_sentiment_report()

        bias_emoji = "🟢 BULLISH BIAS" if report.composite_score > 0.15 else ("🔴 BEARISH BIAS" if report.composite_score < -0.15 else "⚪ NEUTRAL BIAS")

        top_news_bullets = ""
        for i, a in enumerate(report.top_high_impact_news[:3], 1):
            s_tag = "🟢" if "BULLISH" in a.sentiment_label else ("🔴" if "BEARISH" in a.sentiment_label else "⚪")
            top_news_bullets += f"{i}. {s_tag} <b>{a.title[:65]}...</b> (<i>{a.source}</i>)\n"

        if not top_news_bullets:
            top_news_bullets = "<i>No extreme volatility news in the last 24h. Standard market flow.</i>\n"

        msg = (
            f"🧠 <b>[CRYPTO GLOBAL SENTIMENT &amp; NEWS DIGEST]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Composite Market Score:</b> <b><u>{report.composite_score:+.2f}</u> ({bias_emoji})</b>\n"
            f"🌡️ <b>Fear &amp; Greed Index:</b> <b>{report.fear_greed_index}/100 ({report.fear_greed_classification})</b>\n"
            f"📰 <b>Headlines Scanned:</b> <code>{report.total_articles_analyzed}</code> (🟢 {report.bullish_articles_count} | 🔴 {report.bearish_articles_count} | ⚪ {report.neutral_articles_count})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 <b>TOP HIGH-IMPACT HEADLINES:</b>\n"
            f"{top_news_bullets}"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <b>AUTOMATED TRADING TEAM GUIDANCE:</b>\n"
            f"• <b>Recommended Posture:</b> <i>{report.trading_posture_recommendation}</i>\n"
            f"• <b>Risk Scaling Factor:</b> <code>{report.leverage_risk_multiplier:.2f}x</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <i>Generated: {report.timestamp} · 24/7 Multi-Agent Intelligence</i>"
        )

        return bool(notifier.send_message(msg))

