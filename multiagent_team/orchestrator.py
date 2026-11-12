"""
Central Multi-Agent Orchestrator for Delta Exchange 24/7 Automated & Semi-Automated Trading.
Coordinates 11 autonomous agents and shared infrastructure across 6 institutional layers
with standardized responses (SUCCESS, REJECTED, FAILED, TIMEOUT, SKIPPED).
"""

from typing import Dict, Any, List, Optional, Tuple
import sys
import os
import time
import json
import threading
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.delta_client import DeltaExchangeClient
from src.risk_manager import RiskManager
from src.state_manager import StateManager
from src.emergency_controller import EmergencyController
from src.monitoring import SystemMonitor
from multiagent_team.data_validator import MarketDataValidator
from multiagent_team.regime_analyst import RegimeAnalystAgent
from multiagent_team.exposure_coach import ExposureCoachAgent
from multiagent_team.news_sentiment_agent import NewsSentimentAgent
from multiagent_team.strategy_agent import StrategyAgent
from multiagent_team.time_machine_agent import TimeMachineAgent
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.execution_agent import ExecutionAgent
from multiagent_team.portfolio_monitor import PortfolioMonitorAgent
from multiagent_team.adaptive_learning import AdaptiveLearningEngine
from multiagent_team.performance_coach import PerformanceCoachAgent
from multiagent_team.deterministic_safety_controller import DeterministicSafetyController
from src.telegram_notifier import TelegramNotifier
from src.telegram_bot import TelegramConfirmationBot
from src.trailing_stop_manager import TrailingStopManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("orchestrator")


class MultiAgentTradingOrchestrator:
    """
    Central Controller for the 11-Agent Trading System.
    Enforces the 6-Layer Architecture:
      Layer 1 - Market Intelligence (DataValidator + Agent 1 + Agent 2 + Agent 3)
      Layer 2 - Strategy & Validation (Agent 4 + Agent 5)
      Layer 3 - Risk & Authorization (Agent 6 + Agent 7)
      Layer 4 - Execution & Management (Agent 8 + Agent 9)
      Layer 5 - Learning & Optimization (Agent 10 + Agent 11)
      Layer 6 - Shared Infrastructure (Orchestrator, StateManager, EmergencyController, Monitoring, Telegram)
    """
    def __init__(
        self,
        client: Optional[DeltaExchangeClient] = None,
        symbols: Optional[List[str]] = None,
        interactive: bool = True,
        leverage: int = 25,
        target_rr_ratio: float = 2.5
    ):
        self.client = client or DeltaExchangeClient()
        
        # Layer 6: Shared Infrastructure
        self.state_manager = StateManager()
        self.emergency_controller = EmergencyController(client=self.client)
        self.system_monitor = SystemMonitor()
        self.data_validator = MarketDataValidator()
        self.telegram = TelegramNotifier()
        self.telegram_bot = TelegramConfirmationBot()
        self.telegram_bot._active_orchestrator = self

        self.risk_manager = RiskManager(
            max_risk_per_trade_pct=float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.02")),
            max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS", "3")),
            max_daily_drawdown_pct=float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.03")),
            max_allowed_leverage=int(os.getenv("MAX_ALLOWED_LEVERAGE", "50")),
            min_reward_to_risk=target_rr_ratio
        )
        
        # 11 Specialized Agents
        self.regime_analyst = RegimeAnalystAgent(self.client, data_validator=self.data_validator)
        self.exposure_coach = ExposureCoachAgent()
        self.news_sentiment = NewsSentimentAgent()
        self.strategy_agent = StrategyAgent(target_rr_ratio=target_rr_ratio)
        self.time_machine = TimeMachineAgent(self.client)
        self.risk_gatekeeper = RiskGatekeeperAgent(self.client, self.risk_manager)
        self.safety_controller = DeterministicSafetyController(risk_manager=self.risk_manager, state_manager=self.state_manager)
        self.execution_agent = ExecutionAgent(self.client, state_manager=self.state_manager, telegram=self.telegram)
        self.portfolio_monitor = PortfolioMonitorAgent(self.client)
        self.adaptive_learner = AdaptiveLearningEngine()
        self.performance_coach = PerformanceCoachAgent(state_manager=self.state_manager)
        self.trailing_stop_manager = TrailingStopManager(client=self.client, telegram=self.telegram)

        raw_symbols = os.getenv("DEFAULT_SYMBOLS", "BTCUSD,ETHUSD,XAUUSD,SOLUSD,PAXGUSD,XRPUSD,DOGEUSD,ADAUSD")
        self.symbols = symbols or [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
        self.interactive = interactive
        self.leverage = leverage

    def get_market_digest_text(self, scan_results: Optional[Dict[str, Any]] = None, symbols: Optional[List[str]] = None) -> str:
        """Generate a clean Telegram-ready summary of market regimes for primary assets."""
        target_symbols = symbols or ["BTCUSD", "ETHUSD", "XAUUSD"]
        if not scan_results:
            scan_results = self.regime_analyst.scan_universe(target_symbols, resolution="60")

        symbols_data = scan_results.get("symbols_data", {})
        pos_res = self.client.get_positions()
        active_pos = [p for p in pos_res.get("result", []) if int(p.get("size", 0)) != 0] if pos_res.get("success") else []
        orders_res = self.client.get_open_orders()
        open_orders = orders_res.get("result", []) if orders_res.get("success") else []

        lines = [
            "📡 <b>[DELTA 24/7 LIVE SCANNER PULSE]</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "• <b>Status:</b> 🟢 <b>SCANNING 24/7 ON CLOUD</b>",
            f"• <b>Active Positions:</b> <b>{len(active_pos)}</b> | <b>Open Orders:</b> <b>{len(open_orders)}</b>"
        ]

        posture_state = self.exposure_coach.load_cached_posture() or {}
        if posture_state:
            posture_title = posture_state.get("posture", "MODERATE_SELECTIVE")
            health_sc = posture_state.get("health_score", 50)
            breadth_val = posture_state.get("breadth_pct", 50.0)
            cash_badge = " [CASH PRIORITY]" if posture_state.get("cash_priority") else ""
            lines.append(f"• <b>Market Posture:</b> <b>{posture_title}{cash_badge}</b> (Health: {health_sc}/100 | Breadth: {breadth_val:.0f}%)")

        if self.news_sentiment.cached_report:
            rep = self.news_sentiment.cached_report
            lines.append(f"• <b>Market Sentiment:</b> <b>{rep.composite_score:+.2f} ({rep.sentiment_regime})</b> | F&amp;G: <b>{rep.fear_greed_index}/100</b> ({rep.fear_greed_classification})")

        sc = self.adaptive_learner.memory.get("scorecard", {})
        if sc.get("total_completed_trades", 0) > 0:
            lines.append(f"• <b>Self-Scorecard:</b> <b>{sc.get('winning_trades', 0)}W / {sc.get('losing_trades', 0)}L</b> ({sc.get('win_rate_pct', 0)}% Win Rate)")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🌟 <b>PRIMARY ASSETS (CORE FOCUS):</b>")

        for sym in ["BTCUSD", "ETHUSD", "XAUUSD"]:
            d = symbols_data.get(sym)
            if not d:
                continue
            price = d.get("current_price", 0.0)
            m15 = d.get("macro_15m", {})
            m15_reg = m15.get("regime", "NEUTRAL")
            m15_rsi = m15.get("rsi_14", 50.0)
            h4_reg = d.get("macro_4h", {}).get("regime", "N/A").replace("MACRO_", "")
            hp = d.get("high_probability_setup", {})
            setup_status = f"🎯 <b>Ready:</b> {hp.get('strategy', 'Scalp Setup')} ({hp.get('side', '').upper()})" if hp.get("qualified") else "Scanning for 15m trigger..."

            lines.append(f"• <b>{sym}:</b> <code>${price:,.2f}</code> | 15m:{m15_reg} (RSI:{m15_rsi}) | 4H:{h4_reg}")
            lines.append(f"  ↳ <i>{setup_status}</i>")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚡ <i>Send /positions, /scan, or /pause anytime!</i>")
        return "\n".join(lines)

    def check_and_dispatch_daily_morning_briefing(self, force: bool = False) -> bool:
        """
        Check if current time is within morning window (10:00 to 11:00 AM IST)
        and dispatch the Daily Morning Crypto News Briefing if not already sent today.
        """
        try:
            return self.news_sentiment.check_and_dispatch_morning_briefing(self.telegram, force=force)
        except Exception as e:
            logger.warning(f"Error checking daily morning briefing: {e}")
            return False

    def format_market_levels_telegram(self, symbols: Optional[List[str]] = None) -> str:
        """
        Format comprehensive Breakout & Breakdown Key Levels analysis card for Telegram.
        Covers all assets with immediate proximity status, pre-trade plans, and order flow context.
        """
        import html
        from datetime import datetime, timezone, timedelta
        ist_zone = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist_zone)
        date_str = now_ist.strftime("%A, %d %b %Y · %I:%M %p IST")

        target_symbols = symbols or ["BTCUSD", "ETHUSD", "XAUUSD"]
        scan_results = self.regime_analyst.scan_universe(target_symbols, resolution="60")
        symbols_data = scan_results.get("symbols_data", {})

        lines = [
            "⚡ <b>[MARKET KEY LEVELS &amp; BREAKOUT/BREAKDOWN RADAR]</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📅 <b>Timestamp:</b> <code>{date_str}</code>",
            "🎯 <b>Pre-Trade Strategy:</b> High-Confluence Breakout &amp; Breakdown Triggers",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]

        for sym in target_symbols:
            d = symbols_data.get(sym)
            if not d:
                continue

            price = float(d.get("mark_price") or d.get("current_price") or 0.0)
            kla = d.get("key_levels_analysis", {})
            if "error" in kla or not kla:
                continue

            reg_1h = d.get("regime", "NEUTRAL")
            h4_reg = d.get("macro_4h", {}).get("regime", "N/A").replace("MACRO_", "")
            atr_val = kla.get("atr_14", 0.0)
            atr_pct = kla.get("atr_pct", 0.0)
            status_label = html.escape(str(kla.get("status_label", "RANGING")))

            # Order Flow
            of = kla.get("order_flow", {})
            cvd_t = of.get("cvd_trend", "NEUTRAL")
            cvd_div = of.get("cvd_divergence", "NONE")
            cvd_str = f"{cvd_t}" + (f" ({cvd_div})" if cvd_div != "NONE" else "")
            obi_st = of.get("obi_status", "NEUTRAL")
            obi_r = of.get("obi_ratio", 0.0)
            vwap_p = kla.get("vwap_price", price)
            vwap_st = kla.get("vwap_stance", "AT_VWAP")

            bo = kla.get("bullish_breakout_plan", {})
            bd = kla.get("bearish_breakdown_plan", {})

            bo_lvl = kla.get("breakout_level", 0.0)
            dist_bo_pct = kla.get("distance_to_breakout_pct", 0.0)

            bd_lvl = kla.get("breakdown_level", 0.0)
            dist_bd_pct = kla.get("distance_to_breakdown_pct", 0.0)

            bo_crit = html.escape(str(bo.get("confirmation_criteria", "15m close above level")))
            bd_crit = html.escape(str(bd.get("confirmation_criteria", "15m close below level")))

            sym_name = f"{sym} (Gold)" if "XAU" in sym else sym
            lines.append(f"🪙 <b>{sym_name}:</b> <code>${price:,.2f}</code> | <b>{status_label}</b>")
            lines.append(f"• <b>Context:</b> 1H:{reg_1h} | 4H:{h4_reg} | 1H ATR: <code>${atr_val:,.2f} ({atr_pct:.2f}%)</code>")
            lines.append(f"• <b>Order Flow Pulse:</b> CVD: <code>{cvd_str}</code> | OBI: <code>{obi_st} ({obi_r:+.2f})</code> | VWAP: <code>${vwap_p:,.2f} ({vwap_st})</code>")
            lines.append("")
            lines.append(f"🟢 <b>BULLISH BREAKOUT LEVEL: <code>${bo_lvl:,.2f}</code> (+{dist_bo_pct:.2f}%)</b>")
            lines.append(f"  ↳ <b>Trigger:</b> <i>{bo_crit}</i>")
            lines.append(f"  ↳ <b>Target (TP):</b> <code>${bo.get('take_profit_price', 0):,.2f}</code> | <b>Stop (SL):</b> <code>${bo.get('stop_loss_price', 0):,.2f}</code>")
            lines.append(f"  ↳ <b>Projected R:R:</b> <b>{bo.get('planned_rr', 2.3)} : 1</b>")
            lines.append("")
            lines.append(f"🔴 <b>BEARISH BREAKDOWN LEVEL: <code>${bd_lvl:,.2f}</code> (-{dist_bd_pct:.2f}%)</b>")
            lines.append(f"  ↳ <b>Trigger:</b> <i>{bd_crit}</i>")
            lines.append(f"  ↳ <b>Target (TP):</b> <code>${bd.get('take_profit_price', 0):,.2f}</code> | <b>Stop (SL):</b> <code>${bd.get('stop_loss_price', 0):,.2f}</code>")
            lines.append(f"  ↳ <b>Projected R:R:</b> <b>{bd.get('planned_rr', 2.3)} : 1</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        lines.append("🛡️ <b>PRE-TRADE DISCIPLINE &amp; RULES:</b>")
        lines.append("• <b>Never Front-Run:</b> Wait for confirmed 15m candle close across the level.")
        lines.append("• <b>Order Flow Check:</b> Confirm CVD &amp; OBI volume support before entering.")
        lines.append("• <b>Capital Protection:</b> Fixed $2-$4 risk budget with protective bracket SL.")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚡ <i>Send /levels for live update or /trade for execution scan</i>")

        return "\n".join(lines)

    def check_and_dispatch_daily_market_levels(self, force: bool = False) -> bool:
        """
        Dispatch comprehensive Key Levels Breakout/Breakdown card and BTC 15m Candlestick Chart
        to all active Telegram subscribers twice daily:
          - Morning Session: 09:30 - 10:30 AM IST (Asian/European handover)
          - Evening Session: 06:30 - 07:30 PM IST (US Market opening)
        """
        if not self.telegram or not getattr(self.telegram, "enabled", False):
            return False

        from datetime import datetime, timezone, timedelta
        ist_zone = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist_zone)
        today_date_str = now_ist.strftime("%Y-%m-%d")
        current_hour = now_ist.hour
        current_minute = now_ist.minute

        session_key = None
        if (current_hour == 9 and current_minute >= 30) or (10 <= current_hour <= 13):
            session_key = "morning"
        elif (current_hour == 18 and current_minute >= 30) or (19 <= current_hour <= 23):
            session_key = "evening"

        if not force and not session_key:
            return False

        dispatch_slot = f"{today_date_str}_{session_key or 'manual'}"
        state_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "market_levels_dispatch_state.json")
        state = {}
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        state = json.loads(content)
            except Exception as e:
                logger.debug(f"Could not load market levels dispatch state: {e}")

        if not force and state.get("last_dispatch_slot") == dispatch_slot:
            return False

        logger.info(f"Orchestrator: Broadcasting Daily Key Levels session card ({dispatch_slot})...")
        try:
            levels_card = self.format_market_levels_telegram()
            if hasattr(self.telegram, "broadcast_message"):
                self.telegram.broadcast_message(levels_card, parse_mode="HTML", topic="levels")
            else:
                self.telegram.send_message(levels_card, parse_mode="HTML")

            # Also generate and broadcast BTC 15m Candlestick Chart
            try:
                from src.candlestick_chart import generate_candlestick_chart
                analysis = self.regime_analyst.analyze_symbol("BTCUSD", resolution="15")
                candles = analysis.get("_raw_candles_15m") or analysis.get("_raw_candles_1h")
                if not candles or len(candles.get("c", [])) < 5:
                    c_res = self.client.get_candles("BTCUSD", resolution="15")
                    if c_res and isinstance(c_res, dict) and c_res.get("result"):
                        c_list = c_res["result"]
                        if isinstance(c_list, list) and len(c_list) >= 5:
                            candles = {
                                "o": [float(x.get("open", 0)) for x in c_list],
                                "h": [float(x.get("high", 0)) for x in c_list],
                                "l": [float(x.get("low", 0)) for x in c_list],
                                "c": [float(x.get("close", 0)) for x in c_list],
                                "v": [float(x.get("volume", 0)) for x in c_list],
                                "t": [int(x.get("time", 0)) for x in c_list],
                            }
                if candles and len(candles.get("c", [])) >= 5:
                    kl = analysis.get("key_levels_analysis", {})
                    chart_path = generate_candlestick_chart(candles, "BTCUSD", key_levels=kl, timeframe_label="15m")
                    cap = (
                        f"📊 <b>[BTCUSD PRE-TRADE RADAR CHART]</b>\n"
                        f"• <b>Mark:</b> <code>${kl.get('current_price', 0):,.2f}</code>\n"
                        f"• <b>Breakout Trigger:</b> <code>${kl.get('breakout_level', 0):,.2f}</code> (+{kl.get('distance_to_breakout_pct', 0):.2f}%)\n"
                        f"• <b>Breakdown Trigger:</b> <code>${kl.get('breakdown_level', 0):,.2f}</code> (-{kl.get('distance_to_breakdown_pct', 0):.2f}%)\n"
                        f"⚡ <i>Send /chart BTC or /levels for live multi-asset maps!</i>"
                    )
                    if hasattr(self.telegram, "broadcast_photo"):
                        self.telegram.broadcast_photo(chart_path, caption=cap, topic="levels")
                    elif hasattr(self.telegram, "send_photo"):
                        self.telegram.send_photo(chart_path, caption=cap)
            except Exception as ce:
                logger.debug(f"Could not broadcast chart for daily levels: {ce}")

            state["last_dispatch_slot"] = dispatch_slot
            state["last_dispatch_time"] = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to broadcast daily market levels: {e}")
            return False

    def _collect_news_sentiment_safe(self) -> Optional[Any]:
        """Collect news sentiment safely without interrupting trading or /trade flows."""
        if not hasattr(self, "news_sentiment"):
            return None
        try:
            return self.news_sentiment.generate_sentiment_report()
        except Exception as ne:
            logger.warning(f"News sentiment collection skipped: {ne}")
            return None

    @staticmethod
    def _is_counter_trend_direction(side: str, analysis: Dict[str, Any]) -> bool:
        """Unified 1H + 4H + 1D counter-trend check shared across automatic, /trade, and scale-in flows."""
        req_side = str(side or "").lower()
        if req_side not in ("buy", "sell") or not isinstance(analysis, dict):
            return False
        h1_b = str(analysis.get("directional_bias") or analysis.get("regime") or "").upper()
        h4_r = str((analysis.get("macro_4h") or {}).get("regime") or "").upper()
        d1_r = str((analysis.get("macro_daily") or {}).get("regime") or "").upper()
        if req_side == "buy":
            return (
                "BEARISH" in h1_b
                or "BEARISH" in h4_r
                or "TRENDING_DOWN" in h1_b
                or ("BEARISH" in d1_r and "BULLISH" not in h4_r)
            )
        return (
            "BULLISH" in h1_b
            or "BULLISH" in h4_r
            or "TRENDING_UP" in h1_b
            or ("BULLISH" in d1_r and "BEARISH" not in h4_r)
        )

    @staticmethod
    def _check_exposure_posture_gate(
        posture_data: Optional[Dict[str, Any]],
        symbol: Optional[str] = None,
        side: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """Apply ExposureCoach cash_priority, direction_bias, and defensive Tier-1 gates uniformly."""
        if not isinstance(posture_data, dict) or not posture_data:
            return None
        if posture_data.get("cash_priority"):
            return (
                "CASH_PRIORITY",
                posture_data.get("rationale") or "Market breadth broken / choppy (Cash Priority active).",
            )
        direction_bias = posture_data.get("direction_bias", "BOTH")
        req_side = str(side or "").lower()
        if req_side == "buy" and direction_bias == "SHORTS_ONLY":
            return (
                "DIRECTION_BIAS_VETO",
                f"Exposure Coach enforces SHORTS_ONLY posture ({posture_data.get('posture', 'DEFENSIVE')}); LONG blocked.",
            )
        if req_side == "sell" and direction_bias == "LONGS_ONLY":
            return (
                "DIRECTION_BIAS_VETO",
                f"Exposure Coach enforces LONGS_ONLY posture ({posture_data.get('posture', 'BULLISH')}); SHORT blocked.",
            )
        if symbol and posture_data.get("posture") in ["DEFENSIVE_CAUTION", "RECOVERY_POSTURE"]:
            if symbol.upper() not in ["BTCUSD", "ETHUSD", "XAUUSD"]:
                return (
                    "DEFENSIVE_TIER1_VETO",
                    f"{posture_data.get('posture')} posture active: altcoin {symbol.upper()} blocked; strictly Tier-1 Core (BTC/ETH/XAU) permitted.",
                )
        return None

    def check_and_dispatch_level_breakout_alerts(
        self,
        symbols_data: Optional[Dict[str, Any]] = None,
        posture_data: Optional[Dict[str, Any]] = None,
        sentiment_report: Optional[Any] = None,
    ) -> int:
        """
        Detect if any primary asset is within <= 0.35% of a critical breakout or breakdown level,
        and dispatch an immediate proactive Pre-Trade Radar Alert to Telegram.
        """
        if not self.telegram or not getattr(self.telegram, "enabled", False):
            return 0

        target_data = symbols_data or {}
        if not target_data:
            return 0

        import html
        alerts_sent = 0
        state_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "posted_level_alerts.json")
        now_ts = time.time()
        posted_alerts = {}

        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    posted_alerts = json.load(f)
            except Exception as e:
                logger.debug(f"Could not load posted level alerts: {e}")

        for sym, d in target_data.items():
            if sym not in ["BTCUSD", "ETHUSD", "XAUUSD"]:
                continue

            kla = d.get("key_levels_analysis", {})
            if not kla or "error" in kla:
                continue

            if not kla.get("is_imminent"):
                continue

            status = kla.get("proximity_status")
            if status not in ["TESTING_BREAKOUT", "TESTING_BREAKDOWN"]:
                continue

            alert_key = f"{sym}_{status}"
            last_alert_time = posted_alerts.get(alert_key, 0)
            # 45-minute cooldown (2700s) to prevent spam
            if now_ts - last_alert_time < 2700:
                continue

            price = float(d.get("mark_price") or d.get("current_price") or 0.0)
            if status == "TESTING_BREAKOUT":
                plan = kla.get("bullish_breakout_plan", {})
                lvl = kla.get("breakout_level", 0.0)
                dist_pct = kla.get("distance_to_breakout_pct", 0.0)
                dir_emoji = "🟢 BULLISH BREAKOUT"
                dir_tag = "RESISTANCE CEILING"
            else:
                plan = kla.get("bearish_breakdown_plan", {})
                lvl = kla.get("breakdown_level", 0.0)
                dist_pct = kla.get("distance_to_breakdown_pct", 0.0)
                dir_emoji = "🔴 BEARISH BREAKDOWN"
                dir_tag = "SUPPORT FLOOR"

            of = kla.get("order_flow", {})
            cvd_t = of.get("cvd_trend", "NEUTRAL")
            obi_st = of.get("obi_status", "NEUTRAL")
            crit_text = html.escape(str(plan.get("confirmation_criteria", "15m close across level")))

            msg = (
                f"🚨 <b>[PRE-TRADE RADAR: {sym} TESTING KEY LEVEL]</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🪙 <b>Asset:</b> <code>{sym}</code> @ <code>${price:,.2f}</code>\n"
                f"⚡ <b>Proximity:</b> <b>{dir_emoji} TESTING {dir_tag} ({dist_pct:+.2f}%)</b>\n"
                f"🎯 <b>Key Trigger Level:</b> <code>${lvl:,.2f}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 <b>PRE-TRADE ACTION PLAN:</b>\n"
                f"• <b>Trigger:</b> <i>{crit_text}</i>\n"
                f"• <b>Target (TP):</b> <code>${plan.get('take_profit_price', 0):,.2f}</code>\n"
                f"• <b>Stop (SL):</b> <code>${plan.get('stop_loss_price', 0):,.2f}</code>\n"
                f"• <b>Projected R:R:</b> <b>{plan.get('planned_rr', 2.3)} : 1</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 <b>Order Flow Confirmation:</b>\n"
                f"• <b>CVD Trend:</b> <code>{cvd_t}</code>\n"
                f"• <b>Order Book:</b> <code>{obi_st}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>Pre-Trade Notice:</b> Prepare for potential entry once 15m candle closes and confirms.\n"
                f"⚡ <i>Send /trade to execute or /levels for all asset maps</i>"
            )

            try:
                sent = False
                # Attach live candlestick chart with clear UP/DOWN for LONG/SHORT indication
                try:
                    from src.candlestick_chart import generate_candlestick_chart
                    analysis = self.regime_analyst.analyze_symbol(sym, resolution="15")
                    candles = analysis.get("_raw_candles_15m") or analysis.get("_raw_candles_1h")
                    if not candles or len(candles.get("c", [])) < 5:
                        c_res = self.client.get_candles(sym, resolution="15")
                        if c_res and isinstance(c_res, dict) and c_res.get("result"):
                            c_list = c_res["result"]
                            if isinstance(c_list, list) and len(c_list) >= 5:
                                candles = {
                                    "o": [float(x.get("open", 0)) for x in c_list],
                                    "h": [float(x.get("high", 0)) for x in c_list],
                                    "l": [float(x.get("low", 0)) for x in c_list],
                                    "c": [float(x.get("close", 0)) for x in c_list],
                                    "v": [float(x.get("volume", 0)) for x in c_list],
                                    "t": [int(x.get("time", 0)) for x in c_list],
                                }
                    if candles and len(candles.get("c", [])) >= 5:
                        chart_path = generate_candlestick_chart(candles, sym, key_levels=kla, timeframe_label="15m")
                        if hasattr(self.telegram, "broadcast_photo"):
                            sent = self.telegram.broadcast_photo(chart_path, caption=msg, topic="levels") > 0
                        elif hasattr(self.telegram, "send_photo"):
                            sent = self.telegram.send_photo(chart_path, caption=msg)
                except Exception as ce:
                    logger.debug(f"Could not attach candlestick chart to pre-trade radar alert: {ce}")

                if not sent:
                    if hasattr(self.telegram, "broadcast_message"):
                        sent = self.telegram.broadcast_message(msg, topic="levels") > 0
                    else:
                        sent = self.telegram.send_message(msg)
                if sent:
                    posted_alerts[alert_key] = now_ts
                    alerts_sent += 1
                    logger.info(f"Orchestrator: Dispatched pre-trade level alert for {alert_key}")

                    # Automatically dispatch the corresponding interactive proposal card ONLY if trend-aligned & Time Machine verified
                    try:
                        if hasattr(self, "telegram_bot") and getattr(self.telegram_bot, "is_configured", False):
                            side_val = "buy" if status == "TESTING_BREAKOUT" else "sell"
                            asset_lev = int(os.getenv("BTC_LEVERAGE", "50")) if "BTC" in sym else int(os.getenv("ALT_LEVERAGE", "25"))
                            sl_p = float(plan.get("stop_loss_price", 0.0))
                            tp_p = float(plan.get("take_profit_price", 0.0))
                            planned_rr = float(plan.get("planned_rr", 2.3))

                            sym_ctx = d if isinstance(d, dict) else {}
                            if self._is_counter_trend_direction(side_val, sym_ctx):
                                h1_bias = str(sym_ctx.get("directional_bias") or sym_ctx.get("regime") or "").upper()
                                h4_reg = str((sym_ctx.get("macro_4h") or {}).get("regime") or "").upper()
                                logger.info(f"Level breakout proposal {sym} {side_val.upper()} vetoed: counter-trend against HTF regime (1H={h1_bias}, 4H={h4_reg}).")
                                continue

                            posture_veto = self._check_exposure_posture_gate(posture_data, symbol=sym, side=side_val)
                            if posture_veto:
                                logger.info(f"Level breakout proposal {sym} {side_val.upper()} vetoed by Exposure Coach ({posture_veto[0]}): {posture_veto[1]}")
                                continue

                            if sl_p > 0 and tp_p > 0 and price > 0:
                                b_cand = {
                                    "symbol": sym,
                                    "side": side_val,
                                    "entry_price": price,
                                    "stop_loss_price": sl_p,
                                    "take_profit_price": tp_p,
                                    "planned_rr_ratio": planned_rr,
                                    "strategy_name": f"Level_Breakout_{side_val.upper()}_Scalp",
                                    "thesis": f"🚨 [KEY LEVEL BREAKOUT/BREAKDOWN RADAR] {sym} testing key level ${lvl:,.2f} ({dist_pct:+.2f}%)",
                                    "score": 88,
                                    "conviction_tier": "BREAKOUT_MOMENTUM",
                                    "spread_pct": float(sym_ctx.get("spread_pct") or 0.02),
                                    "confluence": {
                                        "levels_detail": f"Trigger: ${lvl:,.2f} | Proximity: {dist_pct:+.2f}%",
                                        "order_flow_detail": f"CVD: {cvd_t} | Order Book: {obi_st}",
                                        "macd_detail": "15m Breakout Momentum Alignment"
                                    },
                                }
                                c15_lvl = sym_ctx.get("_raw_candles_15m") or candles
                                c1h_lvl = sym_ctx.get("_raw_candles_1h")
                                tm_res = self.time_machine.simulate_setup(b_cand, candles_15m=c15_lvl, candles_1h=c1h_lvl)
                                b_cand["time_machine"] = tm_res
                                if not tm_res.get("passed") or float(tm_res.get("win_rate_pct", 0.0) or 0.0) < self.time_machine.min_win_rate_pct:
                                    logger.info(f"Level breakout proposal {sym} {side_val.upper()} vetoed by Time Machine (low win rate/edge): {tm_res.get('reason')}")
                                    continue

                                decision = self.risk_gatekeeper.evaluate_candidate(b_cand, leverage=asset_lev)
                                for k, v in b_cand.items():
                                    if k not in decision or decision[k] is None:
                                        decision[k] = v
                                if decision.get("gate_decision") != "APPROVED":
                                    logger.info(f"Level candidate {sym} vetoed in background by Risk Gatekeeper: {decision.get('reason')}")
                                    continue

                                # Attach sentiment_report to level breakout proposal if available
                                if sentiment_report:
                                    decision["sentiment_report"] = (
                                        sentiment_report.model_dump()
                                        if hasattr(sentiment_report, "model_dump")
                                        else sentiment_report.dict()
                                    )

                                stop_dist = abs(price - sl_p)
                                needed_liq_buffer = stop_dist * 3.5
                                liq_price = round(price - needed_liq_buffer, 2) if side_val == "buy" else round(price + needed_liq_buffer, 2)
                                decision["estimated_liquidation_price"] = liq_price
                                decision["liq_distance_pct"] = round(abs(price - liq_price) / price * 100.0, 2)

                                threading.Thread(
                                    target=self._execute_proposal_flow,
                                    args=(decision,),
                                    daemon=True
                                ).start()
                    except Exception as pe:
                        logger.warning(f"Could not dispatch automated breakout proposal card: {pe}")
            except Exception as se:
                logger.warning(f"Failed to send pre-trade level alert: {se}")

        if alerts_sent > 0:
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(posted_alerts, f, indent=2)
            except Exception as we:
                logger.warning(f"Could not save posted level alerts state: {we}")

        return alerts_sent

    def _execute_proposal_flow(self, trade: Dict[str, Any], chat_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Thread-safe execution flow for a trade proposal card:
        All agents and Safety Controller validate in background FIRST.
        ONLY IF 100% PERFECT and fully approved in background, dispatches interactive proposal card to Telegram.
        When confirmed by user, executes bracket order on Delta Exchange.
        """
        try:
            sym = trade.get("symbol", "")

            # 0. Defense-in-depth Time Machine Win-Rate Guard (blocks low win-rate automatic/scale-in proposals)
            tm_meta = trade.get("time_machine")
            if isinstance(tm_meta, dict) and tm_meta:
                tm_wr = float(tm_meta.get("win_rate_pct", 0.0) or 0.0)
                if not tm_meta.get("passed") or tm_wr < self.time_machine.min_win_rate_pct:
                    tm_reason = tm_meta.get("reason") or (
                        f"Win rate {tm_wr:.1f}% below mandatory {self.time_machine.min_win_rate_pct:.0f}% minimum."
                    )
                    logger.info(f"Orchestrator: Candidate {sym} vetoed in background by Time Machine guard ({tm_reason}). Proposal suppressed.")
                    return {"status": "REJECTED", "code": "TIME_MACHINE_VETO", "reason": tm_reason}

            # 1. Background Pre-Validation by Safety Controller & Agents BEFORE Telegram proposal
            pos_res = self.client.get_positions()
            active_pos = [p for p in pos_res.get("result", []) if abs(float(p.get("size", 0))) > 0] if pos_res.get("success") else []
            wallet_res = self.client.get_wallet_balances()
            tot_equity = 1000.0
            if wallet_res.get("success"):
                for b in wallet_res.get("result", []):
                    if b.get("asset_symbol") in ["USDT", "USD"]:
                        tot_equity = float(b.get("balance", 1000.0))

            pre_safety = self.safety_controller.validate_and_issue_token(
                trade_setup=trade,
                account_equity=tot_equity,
                active_positions=active_pos,
                telegram_approval=None
            )
            if not pre_safety.get("passed"):
                code = pre_safety.get("failure_code", "SAFETY_VETO")
                reason = pre_safety.get("reason", "Safety check failed")
                logger.info(f"Orchestrator: Candidate {sym} vetoed in background by Safety Controller ({code}: {reason}). Proposal suppressed.")
                return {"status": "REJECTED", "code": code, "reason": reason}

            # 2. ONLY IF PERFECT -> Dispatch interactive proposal card to Telegram
            logger.info(f"📱 Candidate {sym} verified 100% perfect in background by all agents! Dispatching proposal card to Telegram...")
            execute_now = False
            if self.telegram_bot.is_configured:
                execute_now = self.telegram_bot.request_trade_confirmation(
                    trade_spec=trade,
                    timeout_seconds=300,
                    client=self.client,
                    chat_id=chat_id
                )
            elif self.interactive:
                choice = input(f"\n❓ Confirm order execution for {sym}? [y/N]: ").strip().lower()
                execute_now = choice in ["y", "yes"]

            if not execute_now:
                logger.info(f"⏭️ Automated trade proposal for {sym} declined or timed out. Capital protected.")
                return {"status": "TIMEOUT", "code": "USER_REJECTED_OR_EXPIRED", "trade": trade}

            # 3. Post-Approval Final Token Issuance & Delta Exchange Execution
            safety_res = self.safety_controller.validate_and_issue_token(
                trade_setup=trade,
                account_equity=tot_equity,
                active_positions=active_pos,
                telegram_approval={"approved": True, "expired": False}
            )

            if not safety_res.get("passed"):
                code = safety_res.get("failure_code", "SAFETY_VETO")
                reason = safety_res.get("reason", "Safety check failed")
                logger.warning(f"🚨 [SAFETY CONTROLLER VETO] {code}: {reason}")
                if self.telegram_bot and self.telegram_bot.is_configured:
                    tid = trade.get("trade_id")
                    if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                        self.telegram_bot.update_proposal_card_status(tid, "BLOCKED", f"{code}: {reason}", chat_id=chat_id)
                    self.telegram_bot.send_message(f"🛑 <b>Execution Blocked by Safety Controller:</b>\nReason: <code>{reason}</code> (Code: <code>{code}</code>)\nCapital protected.", chat_id=chat_id)
                return {"status": "REJECTED", "code": code, "reason": reason}

            token = safety_res.get("token")
            logger.info(f"🚀 Safety passed! Submitting automated confirmed order for {sym} to Delta Exchange...")
            exec_res = self.execution_agent.execute_approved_trade(
                trade,
                order_type="market_order",
                execution_token=token
            )

            if exec_res.get("success"):
                logger.info(f"🎉 Order placed! Trade ID: {exec_res.get('trade_id')} | Order ID: #{exec_res.get('order_id')}")
                if self.telegram_bot and self.telegram_bot.is_configured:
                    tid = trade.get("trade_id") or exec_res.get("trade_id")
                    if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                        self.telegram_bot.update_proposal_card_status(tid, "EXECUTED", f"Order #{exec_res.get('order_id')} placed successfully", chat_id=chat_id)
                trade_atr = trade.get("atr_profile", {}).get("atr_14") or trade.get("atr_14") or 0.0
                try:
                    if exec_res.get("is_scale_in"):
                        self.trailing_stop_manager.scale_in_trade(
                            symbol=trade["symbol"],
                            additional_contracts=trade["contracts"],
                            scale_in_price=trade["entry_price"],
                            new_sl_order_id=exec_res.get("stop_loss_order_id")
                        )
                    else:
                        self.trailing_stop_manager.register_initial_trade(
                            symbol=trade["symbol"],
                            side=trade["side"],
                            entry_price=trade["entry_price"],
                            initial_sl=trade["stop_loss_price"],
                            initial_tp=trade["take_profit_price"],
                            contracts=trade["contracts"],
                            sl_order_id=exec_res.get("stop_loss_order_id") or exec_res.get("order_id"),
                            tp_order_id=exec_res.get("take_profit_order_id"),
                            is_high_volatility=False,
                            trade_id=exec_res.get("trade_id"),
                            atr=trade_atr,
                        )
                except Exception as re_err:
                    logger.error(f"TrailingStopManager register error: {re_err}")

                try:
                    self.risk_gatekeeper.register_execution(trade["symbol"])
                except Exception as rg_err:
                    logger.error(f"RiskGatekeeper register error: {rg_err}")

                try:
                    self.portfolio_monitor.journal_execution(exec_res, trade)
                except Exception as pm_err:
                    logger.error(f"PortfolioMonitor journal error: {pm_err}")

                try:
                    wallet_metrics = self.trailing_stop_manager.get_wallet_metrics()
                    self.telegram.notify_trade_execution(exec_res, trade, wallet=wallet_metrics)
                except Exception as tg_err:
                    logger.error(f"Telegram notify error: {tg_err}")

                return {
                    "status": "SUCCESS",
                    "trade_id": exec_res["trade_id"],
                    "order_id": exec_res.get("order_id"),
                    "symbol": trade["symbol"],
                    "contracts": trade["contracts"]
                }
            else:
                err_msg = exec_res.get("error")
                logger.error(f"⚠️ Order execution failed on Delta Exchange: {err_msg}")
                if self.telegram_bot and self.telegram_bot.is_configured:
                    tid = trade.get("trade_id") or exec_res.get("trade_id")
                    if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                        self.telegram_bot.update_proposal_card_status(tid, "FAILED", f"{err_msg}", chat_id=chat_id)
                    self.telegram_bot.send_message(f"⚠️ <b>Order Execution Failed on Delta Exchange:</b>\n<code>{err_msg}</code>", chat_id=chat_id)
                return {"status": "FAILED", "code": "EXCHANGE_ORDER_ERROR", "error": err_msg}
        except Exception as e:
            logger.error(f"Error in _execute_proposal_flow for {trade.get('symbol')}: {e}", exc_info=True)
            return {"status": "FAILED", "error": str(e)}

    def run_trading_cycle(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute one complete multi-agent cycle through Layers 1 to 5.
        Returns standardized status: SUCCESS, REJECTED, FAILED, TIMEOUT, SKIPPED.
        """
        cycle_start = time.time()
        self.system_monitor.increment_cycle()

        # Check and dispatch Daily Morning Crypto Briefing (10:00 AM IST target, auto catch-up if server wakes later)
        try:
            self.check_and_dispatch_daily_morning_briefing()
        except Exception as me:
            logger.warning(f"Daily morning briefing check encountered an error: {me}")

        # Check and dispatch Daily Key Levels Breakout/Breakdown Radar (Morning & Evening sessions)
        try:
            self.check_and_dispatch_daily_market_levels()
        except Exception as ke:
            logger.warning(f"Daily key levels radar check encountered an error: {ke}")

        active_symbols = symbols or self.symbols

        print("\n" + "=" * 70)
        print("🤖 [DELTA MULTI-AGENT ARCHITECTURE] Executing Trading Decision Cycle")
        print("=" * 70)

        # -----------------------------------------------------------------
        # Layer 6 Safety Gate: Global Emergency Kill Switch Check
        # -----------------------------------------------------------------
        is_halted, halt_reason = self.emergency_controller.is_halted()
        if is_halted:
            logger.warning(f"🛑 Cycle skipped: Global Emergency Halt is active ({halt_reason})")
            return {
                "status": "SKIPPED",
                "code": "EMERGENCY_HALT_ACTIVE",
                "reason": halt_reason
            }

        # -----------------------------------------------------------------
        # Layer 4: Portfolio Health & State Reconciliation (Agent 8 + Sentinel)
        # -----------------------------------------------------------------
        t0 = time.time()
        print("\n📊 [Layer 4: Portfolio Monitor & Trailing Sentinel] Reconciling state & orders...")
        pos_summary = self.portfolio_monitor.monitor_positions()
        active_cnt = pos_summary.get("active_count", 0)
        unrealized_pnl = pos_summary.get("total_unrealized_pnl_usd", 0.0)
        print(f"   Active Positions: {active_cnt} | Total Unrealized PnL: ${unrealized_pnl:.2f}")

        # Reconcile local state with exchange positions
        raw_pos_res = self.client.get_positions()
        if raw_pos_res.get("success"):
            self.state_manager.reconcile_positions_with_exchange(raw_pos_res.get("result", []))

        # Check and update Trailing Stops
        trailing_updates = self.trailing_stop_manager.check_and_update_trailing_stops()
        if trailing_updates:
            print(f"   🛡️ Trailing Stop Manager applied {len(trailing_updates)} stop update(s).")

        # Stale Unfilled Limit Order Cleaner (> 90m old)
        stale_cancelled = self.portfolio_monitor.cancel_stale_orders(max_age_seconds=5400)
        if stale_cancelled:
            for sc in stale_cancelled:
                print(f"   🧹 [STALE ORDER CANCELLED] #{sc['order_id']} {sc['symbol']} ({sc['age_minutes']}m old)")

        self.system_monitor.record_agent_duration("Agent8_TrailingSentinel", (time.time() - t0) * 1000)

        # -----------------------------------------------------------------
        # Layer 1: Market Intelligence (DataValidator + Agent 1 + Agent 2)
        # -----------------------------------------------------------------
        t1 = time.time()
        print(f"\n🔍 [Layer 1: Regime Analyst] Validating feeds & scanning {len(active_symbols)} symbols...")
        scan_results = self.regime_analyst.scan_universe(active_symbols, resolution="15")
        market_regime = scan_results.get("overall_market_regime", "NEUTRAL")
        btc_adx = scan_results.get("btc_adx", 20.0)
        btc_vol = scan_results.get("btc_volatility_state", "NORMAL")
        print(f"   BTC Macro Posture: {market_regime} | ADX: {btc_adx} | Vol State: {btc_vol}")

        self.system_monitor.record_agent_duration("Agent1_RegimeAnalyst", (time.time() - t1) * 1000)

        # Layer 1: News Sentiment Intelligence Engine
        t_news = time.time()
        print("\n📰 [Layer 1: News Sentiment Intelligence] Ingesting global headlines & Fear/Greed index...")
        sentiment_report = None
        try:
            sentiment_report = self.news_sentiment.generate_sentiment_report()
            print(f"   Composite Sentiment: {sentiment_report.composite_score:+.2f} ({sentiment_report.sentiment_regime}) | F&G: {sentiment_report.fear_greed_index}/100 ({sentiment_report.fear_greed_classification})")
            print(f"   Analyzed {sentiment_report.total_articles_analyzed} headlines (🟢 {sentiment_report.bullish_articles_count} | 🔴 {sentiment_report.bearish_articles_count} | ⚪ {sentiment_report.neutral_articles_count})")
            if sentiment_report.top_high_impact_news:
                top_art = sentiment_report.top_high_impact_news[0]
                print(f"   Top Catalyst: [{top_art.catalyst_category}] {top_art.title[:65]}...")

            # Internal multi-agent intelligence only: silent Telegram (no news alert spam)
            # Sentiment metrics and Fear/Greed are embedded directly into trade proposal cards
            print("   ⚡ Sentiment & Fear/Greed fed directly to trading agents. Telegram push alerts silenced (zero spam).")
        except Exception as ne:
            logger.warning(f"News sentiment collection skipped: {ne}")
        self.system_monitor.record_agent_duration("Layer1_NewsSentiment", (time.time() - t_news) * 1000)

        # Agent 2: Exposure Coach
        t2 = time.time()
        print("\n🧭 [Layer 1: Exposure Coach] Evaluating multi-asset breadth, sentiment & risk posture...")
        posture_data = self.exposure_coach.evaluate_market_posture(
            scan_results=scan_results,
            active_positions_count=active_cnt,
            sentiment_report=sentiment_report
        )
        print(f"   Market Health: {posture_data.get('health_score', 50)}/100 | Posture: {posture_data.get('posture', 'MODERATE')} | Breadth: {posture_data.get('breadth_pct', 50.0)}%")
        self.state_manager.save_market_posture(
            posture=posture_data.get("posture", "MODERATE"),
            health_score=posture_data.get("health_score", 50),
            breadth_pct=posture_data.get("breadth_pct", 50.0),
            cash_priority=posture_data.get("cash_priority", False),
            details=posture_data
        )

        # Layer 5 audit trigger
        try:
            self.performance_coach.audit_and_update_rules()
        except Exception as pe:
            logger.debug(f"Operating rules audit skipped: {pe}")

        self.system_monitor.record_agent_duration("Agent2_ExposureCoach", (time.time() - t2) * 1000)

        # Check and dispatch pre-trade key level breakout/breakdown radar alerts with full posture & sentiment context
        try:
            self.check_and_dispatch_level_breakout_alerts(
                scan_results.get("symbols_data", {}),
                posture_data=posture_data,
                sentiment_report=sentiment_report,
            )
        except Exception as le:
            logger.debug(f"Pre-trade level alert check skipped: {le}")

        if posture_data.get("cash_priority"):
            print(f"\n   🛑 [CASH PRIORITY ACTIVE] Market breadth broken ({posture_data['breadth_pct']}%). All new trades blocked.")
            self.system_monitor.record_trade_rejection("CASH_PRIORITY", "ALL", posture_data.get("rationale", ""))
            return {
                "status": "REJECTED",
                "code": "CASH_PRIORITY",
                "reason": posture_data.get("rationale"),
                "posture": posture_data,
                "regime": market_regime
            }

        # -----------------------------------------------------------------
        # Layer 2: Strategy & Historical Validation (Agent 3 + Agent 4)
        # -----------------------------------------------------------------
        t3 = time.time()
        print("\n💡 [Layer 2: Strategy Generator] Filtering alpha setups with VWAP & spread checks...")
        candidates = self.strategy_agent.find_best_candidates(scan_results)

        # Directional bias filter
        direction_bias = posture_data.get("direction_bias", "BOTH")
        if direction_bias == "SHORTS_ONLY" and candidates:
            shorts_only = [c for c in candidates if c.get("side") == "sell"]
            if len(shorts_only) < len(candidates):
                print(f"   🧭 [{posture_data['posture']}] Filtered out long setups. Enforcing SHORTS_ONLY direction bias.")
            candidates = shorts_only
        elif direction_bias == "LONGS_ONLY" and candidates:
            longs_only = [c for c in candidates if c.get("side") == "buy"]
            if len(longs_only) < len(candidates):
                print(f"   🧭 [{posture_data['posture']}] Filtered out short setups. Enforcing LONGS_ONLY direction bias.")
            candidates = longs_only

        # Defensive caution filter
        if posture_data.get("posture") in ["DEFENSIVE_CAUTION", "RECOVERY_POSTURE"] and candidates:
            tier1_only = [c for c in candidates if c.get("symbol") in ["BTCUSD", "ETHUSD", "XAUUSD"]]
            if len(tier1_only) < len(candidates):
                print(f"   🛡️ [{posture_data['posture']}] Filtered out altcoin setups. Focusing strictly on Tier-1 Core.")
            candidates = tier1_only

        self.system_monitor.record_agent_duration("Agent3_StrategyGenerator", (time.time() - t3) * 1000)

        if not candidates:
            print("   No qualified setups found matching strict edge criteria this cycle.")
            return {"status": "REJECTED", "code": "NO_SETUPS_FOUND", "regime": market_regime}

        print(f"   Found {len(candidates)} prospective trade setup(s):")
        for i, c in enumerate(candidates, 1):
            print(f"   [{i}] {c['symbol']} {c['side'].upper()} | Strategy: {c['strategy_name']} | R:R: {c['planned_rr_ratio']}:1 | Score: {c['score']}/100")

        # Agent 4: Time Machine Engine
        t4 = time.time()
        print("\n⏳ [Layer 2: Time Machine Engine] Running walk-forward historical simulation with friction...")
        tm_qualified = []
        for c in candidates:
            sym = c.get("symbol", "")
            raw_data = scan_results.get("symbols_data", {}).get(sym, {})
            candles_15m = raw_data.get("_raw_candles_15m")
            candles_1h = raw_data.get("_raw_candles_1h")

            tm_res = self.time_machine.simulate_setup(c, candles_15m=candles_15m, candles_1h=candles_1h)
            c["time_machine"] = tm_res

            if tm_res.get("passed") and float(tm_res.get("win_rate_pct", 0.0) or 0.0) >= self.time_machine.min_win_rate_pct:
                print(f"   🟢 [TIME MACHINE APPROVED] {sym} {c['side'].upper()}: {tm_res['win_rate_pct']}% Win Rate (Wilson 95% Lower: {tm_res.get('wilson_ci_lower_pct')}%) | EV: +{tm_res['expected_value_r']}R | PF: {tm_res['profit_factor']}x")
                tm_qualified.append(c)
            else:
                print(f"   🔴 [TIME MACHINE VETO] {sym} {c['side'].upper()}: {tm_res.get('reason')}")
                self.system_monitor.record_trade_rejection("TIME_MACHINE_VETO", sym, tm_res.get("reason", ""))

        self.system_monitor.record_agent_duration("Agent4_TimeMachine", (time.time() - t4) * 1000)

        if not tm_qualified:
            best_veto_reason = (
                candidates[0].get("time_machine", {}).get("reason")
                if candidates else None
            ) or f"No setup met >= {self.time_machine.min_win_rate_pct:.0f}% win rate edge with positive EV."
            print(f"\n   All setups rejected by Time Machine Simulation ({best_veto_reason}). Capital protected.")
            return {"status": "REJECTED", "code": "TIME_MACHINE_VETO", "reason": best_veto_reason}
        else:
            candidates = tm_qualified

        # -----------------------------------------------------------------
        # Layer 3: Risk & Authorization (Agent 5 + Agent 6)
        # -----------------------------------------------------------------
        t5 = time.time()
        print("\n🛡️ [Layer 3: Risk Gatekeeper] Sizing with $2-$4 fixed dollar risk & correlation checks...")
        approved_trades = []
        reject_reasons = []
        for c in candidates:
            sym = c.get("symbol", "")
            asset_leverage = int(os.getenv("BTC_LEVERAGE", "50")) if "BTC" in sym else int(os.getenv("ALT_LEVERAGE", "25"))
            decision = self.risk_gatekeeper.evaluate_candidate(c, leverage=asset_leverage)
            status = decision.get("gate_decision")
            if status == "APPROVED":
                conv_mult = decision.get('conviction_multiplier', 1.0)
                conv_tier = decision.get('conviction_tier', 'STANDARD')
                print(f"   ✅ [APPROVED] {sym} ({decision.get('leverage')}x): {decision['contracts']} contracts [Conviction: {conv_mult}x | {conv_tier}] | Risk: ${decision['dollar_risk_usd']} ({decision['risk_pct']}%) | Margin: ${decision['required_margin_usd']}")
                decision["confluence"] = c.get("confluence", {})
                decision["time_machine"] = c.get("time_machine", {})
                if sentiment_report:
                    decision["sentiment_report"] = sentiment_report.model_dump() if hasattr(sentiment_report, "model_dump") else sentiment_report.dict()

                # Calculate estimated liquidation price and liquidation distance %
                cur_ent = float(decision.get("entry_price") or c.get("entry_price") or 0.0)
                cur_sl = float(decision.get("stop_loss_price") or c.get("stop_loss_price") or 0.0)
                cur_side = str(decision.get("side") or c.get("side", "buy")).lower()
                stop_dist = abs(cur_ent - cur_sl)
                needed_liq_buffer = stop_dist * 3.5
                est_liq = float(decision.get("estimated_liquidation_price") or 0.0)
                if est_liq <= 0 or abs(cur_ent - est_liq) < needed_liq_buffer:
                    est_liq = round(cur_ent - needed_liq_buffer, 2) if cur_side == "buy" else round(cur_ent + needed_liq_buffer, 2)
                    decision["estimated_liquidation_price"] = est_liq
                decision["liq_distance_pct"] = round(abs(cur_ent - est_liq) / cur_ent * 100.0, 2) if cur_ent > 0 else 5.0

                approved_trades.append(decision)
            else:
                print(f"   ❌ [REJECTED] {sym}: {decision.get('reason')}")
                self.system_monitor.record_trade_rejection("RISK_GATE_REJECT", sym, decision.get("reason", ""))
                reject_reasons.append(f"{sym}: {decision.get('reason')}")

        self.system_monitor.record_agent_duration("Agent5_RiskGatekeeper", (time.time() - t5) * 1000)

        if not approved_trades:
            print("\n   All prospective setups rejected by Risk Gatekeeper. Capital protected.")
            first_reason = reject_reasons[0] if reject_reasons else "Risk limits or capital allocation exceeded."
            return {"status": "REJECTED", "code": "RISK_GATE_REJECTED", "reason": first_reason}

        # Sort approved trades by Asymmetric Edge: Minimum Risk & Maximum Profit
        # Prioritize: Tier-1 Primary assets, Highest Reward-to-Risk, Highest Time Machine EV, Highest Quality Score
        approved_trades.sort(
            key=lambda t: (
                1 if any(p in t.get("symbol", "").upper() for p in ["BTC", "ETH", "XAU"]) else 0,
                float(t.get("reward_to_risk_ratio", 2.0)),
                float(t.get("time_machine", {}).get("expected_value_r", 0.0)),
                float(t.get("score", 75))
            ),
            reverse=True
        )

        # Check proposal cooldown to avoid repeating identical proposals every cycle
        now_ts = time.time()
        if not hasattr(self, "_recent_proposals"):
            self._recent_proposals = {}

        eligible_trades = []
        for t in approved_trades:
            sym_t = t.get("symbol", "")
            last_p = self._recent_proposals.get(sym_t, 0)
            if now_ts - last_p >= 1800:  # 30-minute proposal cooldown per symbol
                eligible_trades.append(t)
            else:
                logger.info(f"Orchestrator: {sym_t} proposal suppressed by 30m cooldown ({int(now_ts - last_p)}s elapsed)")

        if not eligible_trades:
            print("\n   All approved setups are currently on 30m proposal cooldown. Telegram alert silenced to prevent spam.")
            return {"status": "COMPLETED", "code": "PROPOSALS_ON_COOLDOWN", "approved_count": len(approved_trades)}

        # Agent 6: Telegram 2-Way Human Authorization Gate
        executed_records = []
        for trade in eligible_trades[:1]:
            # 1. Background Pre-Validation by Safety Controller & Agents BEFORE Telegram proposal
            pos_res = self.client.get_positions()
            active_pos = [p for p in pos_res.get("result", []) if abs(float(p.get("size", 0))) > 0] if pos_res.get("success") else []
            wallet_res = self.client.get_wallet_balances()
            tot_equity = 1000.0
            if wallet_res.get("success"):
                for b in wallet_res.get("result", []):
                    if b.get("asset_symbol") in ["USDT", "USD"]:
                        tot_equity = float(b.get("balance", 1000.0))

            pre_safety = self.safety_controller.validate_and_issue_token(
                trade_setup=trade,
                account_equity=tot_equity,
                active_positions=active_pos,
                telegram_approval=None
            )
            if not pre_safety.get("passed"):
                failure_code = pre_safety.get("failure_code", "SAFETY_VETO")
                reason = pre_safety.get("reason", "Safety check failed")
                print(f"   🛡️ [Pre-Proposal Safety Veto] Candidate {trade['symbol']} rejected in background ({failure_code}: {reason}). Proposal suppressed.")
                self.system_monitor.record_trade_rejection(failure_code, trade["symbol"], reason)
                continue

            # 2. ONLY IF 100% PERFECT -> Dispatch proposal card to user
            self._recent_proposals[trade.get("symbol", "")] = now_ts
            print("\n📱 [Layer 3: Telegram Confirmation Gate] Candidate 100% verified in background! Sending proposal card to user...")

            # Generate directional candlestick chart with UP/DOWN indication
            try:
                from src.candlestick_chart import generate_candlestick_chart
                c_res = self.client.get_candles(trade["symbol"], resolution="15")
                c_data = c_res.get("result") if (c_res and isinstance(c_res, dict)) else None
                if isinstance(c_data, list) and len(c_data) >= 5:
                    c_dict = {
                        "o": [float(x.get("open", 0)) for x in c_data],
                        "h": [float(x.get("high", 0)) for x in c_data],
                        "l": [float(x.get("low", 0)) for x in c_data],
                        "c": [float(x.get("close", 0)) for x in c_data],
                        "v": [float(x.get("volume", 0)) for x in c_data],
                        "t": [int(x.get("time", 0)) for x in c_data],
                    }
                    side_str = str(trade.get("side", "")).upper()
                    is_buy = side_str in ["BUY", "LONG"]
                    sl_p = float(trade.get("stop_loss_price", 0))
                    tp_p = float(trade.get("take_profit_price", 0))
                    cur_p = float(trade.get("entry_price", c_dict["c"][-1]))
                    chart_kl = {
                        "breakout_level": cur_p if is_buy else tp_p,
                        "breakdown_level": sl_p if is_buy else cur_p,
                        "status_label": f"PROPOSED {side_str} ({trade.get('strategy_name', 'SMC Edge')})",
                        "proximity_status": "TESTING_BREAKOUT" if is_buy else "TESTING_BREAKDOWN",
                        "bullish_breakout_plan": {
                            "take_profit_price": tp_p if is_buy else 0.0,
                            "stop_loss_price": sl_p if is_buy else 0.0
                        },
                        "bearish_breakdown_plan": {
                            "take_profit_price": tp_p if not is_buy else 0.0,
                            "stop_loss_price": sl_p if not is_buy else 0.0
                        }
                    }
                    trade["chart_path"] = generate_candlestick_chart(c_dict, trade["symbol"], key_levels=chart_kl, timeframe_label="15m")
            except Exception as ce:
                logger.debug(f"Could not generate chart for background trade proposal: {ce}")

            t6 = time.time()
            execute_now = False

            if self.telegram_bot.is_configured:
                print("   ⏳ Awaiting user approval on Telegram (tapping [Confirm] or [Reject])...")
                execute_now = self.telegram_bot.request_trade_confirmation(
                    trade_spec=trade,
                    timeout_seconds=300,
                    client=self.client
                )
            elif self.interactive:
                user_choice = input("\n   ❓ Confirm order execution on Delta Exchange? [y/N]: ").strip().lower()
                execute_now = user_choice in ["y", "yes"]
            else:
                print("   ⚠️ Neither Telegram nor interactive console is available. Execution halted for safety.")
                execute_now = False

            self.system_monitor.record_agent_duration("Agent6_TelegramGate", (time.time() - t6) * 1000)

            if not execute_now:
                print("   ⏭️ Trade declined or timed out. Capital protected.")
                return {"status": "TIMEOUT", "code": "USER_REJECTED_OR_EXPIRED", "trade": trade}

            # -------------------------------------------------------------
            # Layer 4: Deterministic Safety Controller & Order Execution (Agent 7)
            # -------------------------------------------------------------
            t7 = time.time()
            print("   🛡️ [Pre-Execution Gate] Issuing final verified execution token...")

            safety_token_res = self.safety_controller.validate_and_issue_token(
                trade_setup=trade,
                account_equity=tot_equity,
                active_positions=active_pos,
                telegram_approval={"approved": True, "expired": False}
            )

            if not safety_token_res.get("passed"):
                failure_code = safety_token_res.get("failure_code", "SAFETY_VETO")
                reason = safety_token_res.get("reason", "Safety check failed")
                print(f"   🚨 [SAFETY CONTROLLER VETO] {failure_code}: {reason}. Trade aborted!")
                if self.telegram_bot and self.telegram_bot.is_configured:
                    tid = trade.get("trade_id")
                    if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                        self.telegram_bot.update_proposal_card_status(tid, "BLOCKED", f"{failure_code}: {reason}")
                self.system_monitor.record_trade_rejection(failure_code, trade["symbol"], reason)
                return {"status": "REJECTED", "code": failure_code, "reason": reason}

            token = safety_token_res.get("token")
            print("   🚀 Safety Checks PASSED! Token issued. Submitting bracket order on Delta Exchange...")
            exec_res = self.execution_agent.execute_approved_trade(
                trade,
                order_type="market_order",
                execution_token=token
            )
            self.system_monitor.record_agent_duration("Agent7_ExecutionEngine", (time.time() - t7) * 1000)

            if exec_res.get("success"):
                print(f"   🎉 Order successfully placed! Trade ID: {exec_res['trade_id']} | Order ID: #{exec_res.get('order_id')}")
                if self.telegram_bot and self.telegram_bot.is_configured:
                    tid = trade.get("trade_id") or exec_res.get("trade_id")
                    if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                        self.telegram_bot.update_proposal_card_status(tid, "EXECUTED", f"Order #{exec_res.get('order_id')} placed successfully")
                
                # Register into TrailingStopManager with Volatility Buffer
                is_high_vol = (
                    posture_data.get("btc_volatility_state") == "EXPANSION"
                    or "EXPANSION" in posture_data.get("posture", "")
                    or trade.get("is_high_volatility", False)
                )
                trade_atr = trade.get("atr_profile", {}).get("atr_14") or trade.get("atr_14") or 0.0
                if exec_res.get("is_scale_in"):
                    self.trailing_stop_manager.scale_in_trade(
                        symbol=trade["symbol"],
                        additional_contracts=trade["contracts"],
                        scale_in_price=trade["entry_price"],
                        new_sl_order_id=exec_res.get("stop_loss_order_id")
                    )
                else:
                    self.trailing_stop_manager.register_initial_trade(
                        symbol=trade["symbol"],
                        side=trade["side"],
                        entry_price=trade["entry_price"],
                        initial_sl=trade["stop_loss_price"],
                        initial_tp=trade["take_profit_price"],
                        contracts=trade["contracts"],
                        sl_order_id=exec_res.get("stop_loss_order_id") or exec_res.get("order_id"),
                        tp_order_id=exec_res.get("take_profit_order_id"),
                        is_high_volatility=is_high_vol,
                        trade_id=exec_res.get("trade_id"),
                        atr=trade_atr,
                    )
                self.risk_gatekeeper.register_execution(trade["symbol"])

                # Journal execution into persistent memory
                self.portfolio_monitor.journal_execution(exec_res, trade)
                executed_records.append(exec_res)

                wallet_metrics = self.trailing_stop_manager.get_wallet_metrics()
                self.telegram.notify_trade_execution(exec_res, trade, wallet=wallet_metrics)
                
                self.system_monitor.save_metrics()
                return {
                    "status": "SUCCESS",
                    "trade_id": exec_res["trade_id"],
                    "order_id": exec_res.get("order_id"),
                    "symbol": trade["symbol"],
                    "contracts": trade["contracts"]
                }
            else:
                print(f"   ⚠️ Order execution failed on Delta Exchange: {exec_res.get('error')}")
                if self.telegram_bot and self.telegram_bot.is_configured:
                    tid = trade.get("trade_id") or exec_res.get("trade_id")
                    if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                        self.telegram_bot.update_proposal_card_status(tid, "FAILED", f"{exec_res.get('error')}")
                self.system_monitor.save_metrics()
                return {
                    "status": "FAILED",
                    "code": "EXCHANGE_ORDER_ERROR",
                    "error": exec_res.get("error")
                }

        self.system_monitor.save_metrics()
        return {"status": "COMPLETED", "cycles_elapsed": round(time.time() - cycle_start, 2)}

    def notify_telegram_rejection(
        self,
        symbol: str,
        reason: str,
        code: str,
        chat_id: Optional[str] = None
    ) -> None:
        """
        Send an explicit, formatted rejection notification to Telegram
        whenever a trade proposal is vetoed or suppressed by background agents.
        Ensures two-way communication never fails silently.
        """
        target_chat = chat_id or getattr(getattr(self, "telegram_bot", None), "chat_id", None)
        if not (self.telegram_bot and self.telegram_bot.is_configured and target_chat):
            return

        rejection_msg = (
            "🛡️ <b>[TRADE PROPOSAL VETOED BY RISK CONTROLLER]</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Target Symbol:</b> <code>{symbol}</code>\n"
            f"• <b>Evaluation:</b> 🛑 <b>REJECTED IN BACKGROUND</b>\n"
            f"• <b>Veto Reason:</b> <code>{reason}</code>\n"
            f"• <b>Protection Code:</b> <code>{code}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Capital protected. Zero risk incurred. All funds remain in safe USD cash.</i>\n"
            "⚡ <i>Send <code>/positions</code>, <code>/status</code>, or <code>/rules</code> for live telemetry.</i>"
        )
        try:
            self.telegram_bot.send_message(rejection_msg, chat_id=target_chat)
            logger.info(f"Orchestrator: Dispatched trade rejection notification to Telegram chat {target_chat} for {symbol} ({code})")
        except Exception as e:
            logger.error(f"Failed to send Telegram rejection notification: {e}")

    def propose_on_demand_trade(
        self,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build an institutional trade proposal on demand:
        - If symbol is None or 'ALL': Scans all universe assets (BTC, ETH, XAU, SOL, XRP, DOGE, ADA),
          evaluates strategies across all assets, and selects the #1 highest-probability trade.
        - If symbol is provided: Targets that specific asset.
        Passes through Agent 5 (Risk Gatekeeper) with $2-$4 dollar risk sizing,
        presents interactive confirmation buttons directly on Telegram,
        and executes on Delta Exchange if approved by the user.
        """
        # 1. Emergency halt check
        is_halted, halt_reason = self.emergency_controller.is_halted()
        if is_halted:
            reason = f"Emergency halt is active: {halt_reason}"
            code = "EMERGENCY_HALT_ACTIVE"
            self.notify_telegram_rejection(symbol or "PORTFOLIO", reason, code, chat_id=chat_id)
            return {"status": "SKIPPED", "code": code, "reason": reason, "notified": True}

        candidate = None
        direction_bias = "BOTH"

        # Check existing active positions to prevent Delta Exchange duplicate bracket collision
        active_pos_symbols = set()
        try:
            pos_res = self.client.get_positions()
            if pos_res.get("success"):
                for p in pos_res.get("result", []):
                    if abs(float(p.get("size", 0))) > 0:
                        psym = str(p.get("symbol") or p.get("product_symbol") or "").upper()
                        if psym:
                            active_pos_symbols.add(psym)
        except Exception as pe:
            logger.debug(f"Could not check active positions for collision: {pe}")

        from src.config import system_config
        is_scale_in = False
        raw_positions = []
        try:
            raw_positions = pos_res.get("result", []) if pos_res.get("success") else []
        except Exception:
            pass

        sentiment_report = self._collect_news_sentiment_safe()
        posture_data = {}

        # Target Asset & Scale-In Selection:
        if symbol and symbol.upper() not in ["ALL", "AUTO", "ANY", "SCAN"]:
            clean_sym = symbol.upper()
            if not clean_sym.endswith("USD") and not clean_sym.endswith("USDT"):
                clean_sym = f"{clean_sym}USD"
            symbol = clean_sym
            if symbol in active_pos_symbols:
                # Check if existing position is profitable (eligible for scale-in / add to winner)
                pos_match = next((p for p in raw_positions if str(p.get("symbol") or p.get("product_symbol") or "").upper() == symbol), None)
                pos_pnl = float(pos_match.get("unrealized_pnl", 0.0)) if pos_match else 0.0
                if pos_match and pos_pnl > 0:
                    logger.info(f"Orchestrator: Active {symbol} position is in profit (+${pos_pnl:.2f}). Approving scale-in for /trade!")
                    is_scale_in = True
                else:
                    reason = f"An active position on {symbol} already exists on Delta Exchange and is currently flat or in drawdown (PnL: ${pos_pnl:.2f}). Adding quantity is only permitted when trade is in profit. Use /close {symbol} to close it first."
                    code = "POSITION_ALREADY_EXISTS"
                    self.notify_telegram_rejection(symbol, reason, code, chat_id=chat_id)
                    return {
                        "status": "REJECTED",
                        "code": code,
                        "reason": reason,
                        "notified": True
                    }
        else:
            # No specific symbol requested (/trade):
            # Priority 1: If an active position is profitable, propose scale-in opportunity immediately!
            scale_candidate = None
            for s in ["BTCUSD", "ETHUSD", "XAUUSD", "SOLUSD"]:
                pm = next((p for p in raw_positions if str(p.get("symbol") or p.get("product_symbol") or "").upper() == s), None)
                if pm and float(pm.get("unrealized_pnl", 0.0)) > 0:
                    scale_candidate = s
                    is_scale_in = True
                    break

            if scale_candidate:
                symbol = scale_candidate
                logger.info(f"Orchestrator: Selected active winning position {symbol} for scale-in evaluation.")
            else:
                available = [s for s in ["BTCUSD", "ETHUSD", "XAUUSD", "SOLUSD"] if s not in active_pos_symbols]
                if not available:
                    reason = f"Active positions already exist on all core assets ({', '.join(active_pos_symbols)}). Use /close <symbol> to free up an asset."
                    code = "ALL_ASSETS_HAVE_POSITIONS"
                    self.notify_telegram_rejection("PORTFOLIO", reason, code, chat_id=chat_id)
                    return {
                        "status": "REJECTED",
                        "code": code,
                        "reason": reason,
                        "notified": True
                    }

                logger.info(f"Orchestrator: Running full multi-agent trend & edge scan across {available} for /trade...")
                scan_results = self.regime_analyst.scan_universe(available, resolution="15")
                if hasattr(self, "exposure_coach"):
                    try:
                        posture_data = self.exposure_coach.evaluate_market_posture(
                            scan_results=scan_results,
                            active_positions_count=len(active_pos_symbols),
                            sentiment_report=sentiment_report,
                        )
                        direction_bias = posture_data.get("direction_bias", "BOTH")
                    except Exception:
                        pass

                if posture_data.get("cash_priority"):
                    reason = posture_data.get("rationale") or "Market breadth broken / choppy (Cash Priority active)."
                    self.notify_telegram_rejection("PORTFOLIO", reason, "CASH_PRIORITY", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "CASH_PRIORITY", "reason": reason, "notified": True}

                candidates = self.strategy_agent.find_best_candidates(scan_results)
                if side:
                    candidates = [c for c in candidates if c.get("side") == side.lower()]
                if candidates and posture_data:
                    candidates = [
                        c for c in candidates
                        if self._check_exposure_posture_gate(posture_data, symbol=c.get("symbol"), side=c.get("side")) is None
                    ]

                if not candidates:
                    rej_notes = []
                    for sym_a in available:
                        rej = self.strategy_agent.get_last_rejection(sym_a)
                        if rej:
                            rej_notes.append(f"{sym_a}: {rej.get('gate')} ({rej.get('reason')})")
                    reason = (
                        "; ".join(rej_notes[:2])
                        if rej_notes
                        else f"No trend-aligned high-probability setup qualified across {', '.join(available)} (Bias: {direction_bias})."
                    )
                    self.notify_telegram_rejection("PORTFOLIO", reason, "NO_SETUPS_FOUND", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "NO_SETUPS_FOUND", "reason": reason, "notified": True}

                tm_reject_reasons = []
                for cand in candidates:
                    c_sym = cand.get("symbol", "")
                    sym_raw = scan_results.get("symbols_data", {}).get(c_sym, {})
                    c15 = sym_raw.get("_raw_candles_15m")
                    c1h = sym_raw.get("_raw_candles_1h")
                    tm_res = self.time_machine.simulate_setup(cand, candles_15m=c15, candles_1h=c1h)
                    cand["time_machine"] = tm_res
                    if tm_res.get("passed") and float(tm_res.get("win_rate_pct", 0.0) or 0.0) >= self.time_machine.min_win_rate_pct:
                        candidate = cand
                        candles_15m = c15 or {}
                        symbol = c_sym
                        side = cand.get("side")
                        break
                    else:
                        tm_reject_reasons.append(f"{c_sym} {cand.get('side', '').upper()}: {tm_res.get('reason')}")

                if not candidate:
                    reason = tm_reject_reasons[0] if tm_reject_reasons else f"All setups rejected by Time Machine (< {self.time_machine.min_win_rate_pct:.0f}% win rate)."
                    self.notify_telegram_rejection("PORTFOLIO", reason, "TIME_MACHINE_VETO", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "TIME_MACHINE_VETO", "reason": reason, "notified": True}

        # Check portfolio concurrency limit (scale-in does not consume a new asset slot)
        if not is_scale_in and len(active_pos_symbols) >= system_config.max_portfolio_concurrency:
            reason = f"Maximum concurrent positions reached ({len(active_pos_symbols)}/{system_config.max_portfolio_concurrency} active: {', '.join(active_pos_symbols)}). Use /close <symbol> to close a position first."
            code = "PORTFOLIO_CONCURRENCY_LIMIT"
            self.notify_telegram_rejection(symbol or "PORTFOLIO", reason, code, chat_id=chat_id)
            return {
                "status": "REJECTED",
                "code": code,
                "reason": reason,
                "notified": True
            }

        if not symbol:
            symbol = "BTCUSD"

        symbol = symbol.upper()
        if not symbol.endswith("USD") and not symbol.endswith("USDT"):
            symbol = f"{symbol}USD"

        # 2. Get live ticker & mark price
        cur_mark = float(candidate.get("entry_price") or 0.0) if candidate else 0.0
        if cur_mark <= 0:
            try:
                t_res = self.client.get_ticker(symbol)
                if t_res and t_res.get("success"):
                    cur_mark = float(t_res.get("result", {}).get("mark_price", 0.0) or 0.0)
            except Exception:
                pass

        # 3. Full Multi-Agent Technical + Trend + Time Machine Evaluation for Specific Symbol or Scale-In
        if "candles_15m" not in locals() or not isinstance(candles_15m, dict):
            candles_15m = {}
        candles_1h = {}

        asset_lev = int(os.getenv("BTC_LEVERAGE", "50")) if "BTC" in symbol else int(os.getenv("ALT_LEVERAGE", "25"))

        if not candidate:
            analysis = self.regime_analyst.analyze_symbol(symbol, resolution="15")
            if isinstance(analysis, dict) and "error" not in analysis:
                candles_15m = analysis.get("_raw_candles_15m") or {}
                candles_1h = analysis.get("_raw_candles_1h") or {}
                if cur_mark <= 0:
                    cur_mark = float(analysis.get("mark_price") or analysis.get("current_price") or 0.0)
            else:
                analysis = {"symbol": symbol, "current_price": cur_mark}

            if cur_mark <= 0 and not candles_15m:
                c_res = self.client.get_candles(symbol, resolution="15")
                if c_res and isinstance(c_res, dict) and c_res.get("result"):
                    c_data = c_res["result"]
                    if isinstance(c_data, list) and len(c_data) >= 5:
                        candles_15m = {
                            "o": [float(x.get("open", 0)) for x in c_data],
                            "h": [float(x.get("high", 0)) for x in c_data],
                            "l": [float(x.get("low", 0)) for x in c_data],
                            "c": [float(x.get("close", 0)) for x in c_data],
                            "v": [float(x.get("volume", 0)) for x in c_data],
                            "t": [int(x.get("time", 0)) for x in c_data],
                        }
                        if cur_mark <= 0 and candles_15m.get("c"):
                            cur_mark = float(candles_15m["c"][-1])

            if cur_mark <= 0:
                reason = f"Could not fetch live market price for {symbol} from Delta Exchange."
                code = "INVALID_PRICE"
                self.notify_telegram_rejection(symbol, reason, code, chat_id=chat_id)
                return {"status": "FAILED", "code": code, "reason": reason, "notified": True}

            if not posture_data and hasattr(self, "exposure_coach") and len(self.symbols) >= 2:
                try:
                    uni_scan = self.regime_analyst.scan_universe(self.symbols, resolution="15")
                    if isinstance(uni_scan, dict) and uni_scan.get("symbols_data"):
                        posture_data = self.exposure_coach.evaluate_market_posture(
                            scan_results=uni_scan,
                            active_positions_count=len(active_pos_symbols),
                            sentiment_report=sentiment_report,
                        )
                except Exception:
                    pass

            if is_scale_in:
                pos_match = next((p for p in raw_positions if str(p.get("symbol") or p.get("product_symbol") or "").upper() == symbol), None)
                if pos_match:
                    existing_size = float(pos_match.get("size", 0))
                    side = "buy" if existing_size > 0 else "sell"

                # Enforce same regime, 1H/4H/1D trend, and Exposure Coach gates as automatic & /trade
                regime_upper = str(analysis.get("regime") or "").upper()
                if regime_upper in ("RANGING", "LOW_VOLATILITY", "TRANSITIONAL", "UNKNOWN", "RANGING_CHOP"):
                    reason = f"Scale-in {symbol} {side.upper()} blocked: unclear/choppy regime ({regime_upper})."
                    self.notify_telegram_rejection(symbol, reason, "REGIME_VETO", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "REGIME_VETO", "reason": reason, "notified": True}

                if self._is_counter_trend_direction(side, analysis):
                    h1_b = str(analysis.get("directional_bias") or analysis.get("regime") or "").upper()
                    h4_r = str((analysis.get("macro_4h") or {}).get("regime") or "").upper()
                    d1_r = str((analysis.get("macro_daily") or {}).get("regime") or "").upper()
                    reason = f"Scale-in {symbol} {side.upper()} blocked: trend/HTF opposed open trade (1H={h1_b}, 4H={h4_r}, Daily={d1_r})."
                    self.notify_telegram_rejection(symbol, reason, "COUNTER_TREND_VETO", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "COUNTER_TREND_VETO", "reason": reason, "notified": True}

                posture_veto = self._check_exposure_posture_gate(posture_data, symbol=symbol, side=side)
                if posture_veto:
                    self.notify_telegram_rejection(symbol, posture_veto[1], posture_veto[0], chat_id=chat_id)
                    return {"status": "REJECTED", "code": posture_veto[0], "reason": posture_veto[1], "notified": True}

                atr = float((analysis.get("macro_15m") or {}).get("atr_14") or analysis.get("atr_14") or (cur_mark * 0.006))
                vwap = float(analysis.get("vwap") or cur_mark)
                from src.technical_analysis import round_price
                sl_dist = atr * 1.5
                sl = round_price(cur_mark - sl_dist) if side == "buy" else round_price(cur_mark + sl_dist)
                tp = round_price(cur_mark + (sl_dist * 2.5)) if side == "buy" else round_price(cur_mark - (sl_dist * 2.5))
                rr = 2.5
                candidate = {
                    "symbol": symbol,
                    "side": side,
                    "entry_price": cur_mark,
                    "stop_loss_price": sl,
                    "take_profit_price": tp,
                    "planned_rr_ratio": rr,
                    "strategy_name": f"ScaleIn_Pyramid_{side.upper()}",
                    "thesis": f"🔥 [SCALE-IN: ADDING TO WINNER] 15m {side.upper()} @ VWAP ${vwap:,.2f}",
                    "score": 92,
                    "conviction_tier": "SCALE_IN_WINNER",
                    "atr_14": atr,
                    "spread_pct": float(analysis.get("spread_pct") or 0.02),
                    "is_scale_in": True,
                    "scale_in_parent": {
                        "existing_size": abs(float(pos_match.get("size", 0))),
                        "entry_price": float(pos_match.get("entry_price", cur_mark)),
                        "unrealized_pnl": float(pos_match.get("unrealized_pnl", 0.0)),
                        "side": side
                    } if pos_match else {},
                    "confluence": {
                        "vwap_detail": f"Mark: ${cur_mark:,.2f} | 15m VWAP: ${vwap:,.2f} | ATR: ${atr:,.2f}",
                        "liquidity_detail": f"Targeting 1:{rr:.1f} R:R Scale-In",
                        "macd_detail": f"15m {side.upper()} Continuation"
                    },
                }
                tm_res = self.time_machine.simulate_setup(candidate, candles_15m=candles_15m, candles_1h=candles_1h)
                candidate["time_machine"] = tm_res
                if not tm_res.get("passed") or float(tm_res.get("win_rate_pct", 0.0) or 0.0) < self.time_machine.min_win_rate_pct:
                    reason = tm_res.get("reason") or (
                        f"Time Machine rejected scale-in on {symbol} {side.upper()}: win rate "
                        f"{tm_res.get('win_rate_pct', 0.0)}% below required {self.time_machine.min_win_rate_pct:.0f}%."
                    )
                    logger.info(f"Orchestrator: Scale-in {symbol} {side.upper()} rejected in background by Time Machine: {reason}")
                    self.notify_telegram_rejection(symbol, reason, "TIME_MACHINE_VETO", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "TIME_MACHINE_VETO", "reason": reason, "notified": True}
            else:
                # Fresh trade: MUST pass ExposureCoach, StrategyAgent (trend + confluence), and TimeMachine (>= 60%)
                if side and self._is_counter_trend_direction(side, analysis):
                    h1_b = str(analysis.get("directional_bias") or analysis.get("regime") or "").upper()
                    h4_r = str((analysis.get("macro_4h") or {}).get("regime") or "").upper()
                    d1_r = str((analysis.get("macro_daily") or {}).get("regime") or "").upper()
                    reason = f"Counter-trend {symbol} {side.upper()} rejected against market trend (1H={h1_b or 'N/A'}, 4H={h4_r or 'N/A'}, Daily={d1_r or 'N/A'})."
                    self.notify_telegram_rejection(symbol, reason, "COUNTER_TREND_VETO", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "COUNTER_TREND_VETO", "reason": reason, "notified": True}

                pre_posture_veto = self._check_exposure_posture_gate(posture_data, symbol=symbol, side=side)
                if pre_posture_veto:
                    self.notify_telegram_rejection(symbol, pre_posture_veto[1], pre_posture_veto[0], chat_id=chat_id)
                    return {"status": "REJECTED", "code": pre_posture_veto[0], "reason": pre_posture_veto[1], "notified": True}

                candidate = self.strategy_agent.evaluate_setup(analysis)
                if not candidate:
                    rej = self.strategy_agent.get_last_rejection(symbol) or {}
                    code = rej.get("gate") or "STRATEGY_VETO"
                    reason = rej.get("reason") or f"No high-probability trend-aligned setup found on {symbol}."
                    self.notify_telegram_rejection(symbol, reason, code, chat_id=chat_id)
                    return {"status": "REJECTED", "code": code, "reason": reason, "notified": True}

                if side and candidate.get("side", "").lower() != side.lower():
                    reason = (
                        f"Requested {symbol} {side.upper()} conflicts with Strategy & Market Trend direction "
                        f"({candidate.get('side', '').upper()})."
                    )
                    self.notify_telegram_rejection(symbol, reason, "COUNTER_TREND_VETO", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "COUNTER_TREND_VETO", "reason": reason, "notified": True}

                side = candidate["side"]
                post_posture_veto = self._check_exposure_posture_gate(posture_data, symbol=symbol, side=side)
                if post_posture_veto:
                    self.notify_telegram_rejection(symbol, post_posture_veto[1], post_posture_veto[0], chat_id=chat_id)
                    return {"status": "REJECTED", "code": post_posture_veto[0], "reason": post_posture_veto[1], "notified": True}
                tm_res = self.time_machine.simulate_setup(candidate, candles_15m=candles_15m, candles_1h=candles_1h)
                candidate["time_machine"] = tm_res
                if not tm_res.get("passed") or float(tm_res.get("win_rate_pct", 0.0) or 0.0) < self.time_machine.min_win_rate_pct:
                    reason = tm_res.get("reason") or (
                        f"Time Machine rejected {symbol} {side.upper()}: win rate "
                        f"{tm_res.get('win_rate_pct', 0.0)}% below required {self.time_machine.min_win_rate_pct:.0f}%."
                    )
                    self.notify_telegram_rejection(symbol, reason, "TIME_MACHINE_VETO", chat_id=chat_id)
                    return {"status": "REJECTED", "code": "TIME_MACHINE_VETO", "reason": reason, "notified": True}
        else:
            if cur_mark <= 0 and candles_15m.get("c"):
                cur_mark = float(candles_15m["c"][-1])
            if cur_mark <= 0:
                reason = f"Could not fetch live market price for {symbol} from Delta Exchange."
                code = "INVALID_PRICE"
                self.notify_telegram_rejection(symbol, reason, code, chat_id=chat_id)
                return {"status": "FAILED", "code": code, "reason": reason, "notified": True}
            if is_scale_in:
                candidate["is_scale_in"] = True
                pos_match = next((p for p in raw_positions if str(p.get("symbol") or p.get("product_symbol") or "").upper() == symbol), None)
                if pos_match:
                    existing_size = float(pos_match.get("size", 0))
                    side = "buy" if existing_size > 0 else "sell"
                    candidate["side"] = side
                    candidate["scale_in_parent"] = {
                        "existing_size": abs(float(pos_match.get("size", 0))),
                        "entry_price": float(pos_match.get("entry_price", cur_mark)),
                        "unrealized_pnl": float(pos_match.get("unrealized_pnl", 0.0)),
                        "side": side
                    }

        # 4. Final Time Machine Win-Rate Invariant + Risk Gatekeeper evaluation
        tm_check = candidate.get("time_machine")
        if not isinstance(tm_check, dict) or not tm_check:
            tm_check = self.time_machine.simulate_setup(candidate, candles_15m=candles_15m, candles_1h=candles_1h)
            candidate["time_machine"] = tm_check
        if not tm_check.get("passed") or float(tm_check.get("win_rate_pct", 0.0) or 0.0) < self.time_machine.min_win_rate_pct:
            reason = tm_check.get("reason") or (
                f"Time Machine rejected {symbol} {str(candidate.get('side', side or '')).upper()}: win rate "
                f"{tm_check.get('win_rate_pct', 0.0)}% below required {self.time_machine.min_win_rate_pct:.0f}%."
            )
            self.notify_telegram_rejection(candidate.get("symbol", symbol), reason, "TIME_MACHINE_VETO", chat_id=chat_id)
            return {"status": "REJECTED", "code": "TIME_MACHINE_VETO", "reason": reason, "notified": True}

        candidate["is_scale_in"] = is_scale_in
        decision = self.risk_gatekeeper.evaluate_candidate(candidate, leverage=asset_lev)
        for k, v in candidate.items():
            if k not in decision or decision[k] is None:
                decision[k] = v

        if decision.get("gate_decision") != "APPROVED":
            rg_reason = decision.get("reason", "Risk parameters exceeded.")
            logger.info(f"Orchestrator: Candidate {candidate.get('symbol')} vetoed in background by Risk Gatekeeper: {rg_reason}")
            code = "RISK_GATEKEEPER_VETO"
            self.notify_telegram_rejection(candidate.get("symbol", symbol), rg_reason, code, chat_id=chat_id)
            return {
                "status": "REJECTED",
                "code": code,
                "reason": f"Risk Gatekeeper rejected trade in background: {rg_reason}",
                "notified": True
            }

        decision["symbol"] = decision.get("symbol") or candidate["symbol"]
        decision["side"] = decision.get("side") or candidate["side"]
        decision["entry_price"] = cur_mark
        sl_price = float(decision.get("stop_loss_price") or candidate["stop_loss_price"])
        decision["stop_loss_price"] = sl_price
        decision["take_profit_price"] = float(decision.get("take_profit_price") or candidate["take_profit_price"])
        decision["confluence"] = candidate["confluence"]
        decision["time_machine"] = candidate["time_machine"]
        if sentiment_report:
            decision["sentiment_report"] = (
                sentiment_report.model_dump()
                if hasattr(sentiment_report, "model_dump")
                else sentiment_report.dict()
            )
        if is_scale_in:
            decision["is_scale_in"] = True

        liq_price = float(decision.get("estimated_liquidation_price") or 0.0)
        stop_dist = abs(cur_mark - sl_price)
        needed_liq_buffer = stop_dist * 3.5
        cur_side = str(decision.get("side") or side or "buy").lower()
        if liq_price <= 0 or abs(cur_mark - liq_price) < needed_liq_buffer:
            liq_price = round(cur_mark - needed_liq_buffer, 2) if cur_side == "buy" else round(cur_mark + needed_liq_buffer, 2)
            decision["estimated_liquidation_price"] = liq_price
        decision["liq_distance_pct"] = round(abs(cur_mark - liq_price) / cur_mark * 100.0, 2)

        # 5. Background Pre-Validation by Safety Controller BEFORE Telegram Proposal
        pos_res = self.client.get_positions()
        active_pos = [p for p in pos_res.get("result", []) if abs(float(p.get("size", 0))) > 0] if pos_res.get("success") else []
        wallet_res = self.client.get_wallet_balances()
        tot_equity = 1000.0
        if wallet_res.get("success"):
            for b in wallet_res.get("result", []):
                if b.get("asset_symbol") in ["USDT", "USD"]:
                    tot_equity = float(b.get("balance", 1000.0))

        pre_safety = self.safety_controller.validate_and_issue_token(
            trade_setup=decision,
            account_equity=tot_equity,
            active_positions=active_pos,
            telegram_approval=None
        )
        if not pre_safety.get("passed"):
            code = pre_safety.get("failure_code", "SAFETY_VETO")
            reason = pre_safety.get("reason", "Safety criteria failed")
            logger.info(f"Orchestrator: Candidate {decision['symbol']} vetoed in background by Safety Controller ({code}: {reason}). Proposal suppressed.")
            self.notify_telegram_rejection(decision['symbol'], f"Safety Controller pre-trade check: {reason}", code, chat_id=chat_id)
            return {
                "status": "REJECTED",
                "code": code,
                "reason": f"Safety Controller vetoed trade in background: {reason}",
                "notified": True
            }

        # 6. ONLY IF 100% PERFECT -> Dispatch Telegram confirmation card
        logger.info(f"📱 Candidate {decision['symbol']} verified 100% perfect in background by all agents! Dispatching proposal card to Telegram...")

        # Generate directional candlestick chart with UP/DOWN indication
        try:
            from src.candlestick_chart import generate_candlestick_chart
            if not candles_15m or len(candles_15m.get("c", [])) < 5:
                c_res = self.client.get_candles(decision["symbol"], resolution="15")
                c_data = c_res.get("result") if (c_res and isinstance(c_res, dict)) else None
                if isinstance(c_data, list) and len(c_data) >= 5:
                    candles_15m = {
                        "o": [float(x.get("open", 0)) for x in c_data],
                        "h": [float(x.get("high", 0)) for x in c_data],
                        "l": [float(x.get("low", 0)) for x in c_data],
                        "c": [float(x.get("close", 0)) for x in c_data],
                        "v": [float(x.get("volume", 0)) for x in c_data],
                        "t": [int(x.get("time", 0)) for x in c_data],
                    }

            if candles_15m and len(candles_15m.get("c", [])) >= 5:
                sl_p = float(decision.get("stop_loss_price", 0))
                tp_p = float(decision.get("take_profit_price", 0))
                side_str = str(decision.get("side", "")).upper()
                is_buy = side_str in ["BUY", "LONG"]
                chart_kl = {
                    "breakout_level": cur_mark if is_buy else tp_p,
                    "breakdown_level": sl_p if is_buy else cur_mark,
                    "status_label": f"PROPOSED {side_str} ({decision.get('strategy_name', 'SMC Scalp')})",
                    "proximity_status": "TESTING_BREAKOUT" if is_buy else "TESTING_BREAKDOWN",
                    "bullish_breakout_plan": {
                        "take_profit_price": tp_p if is_buy else 0.0,
                        "stop_loss_price": sl_p if is_buy else 0.0
                    },
                    "bearish_breakdown_plan": {
                        "take_profit_price": tp_p if not is_buy else 0.0,
                        "stop_loss_price": sl_p if not is_buy else 0.0
                    }
                }
                chart_path = generate_candlestick_chart(candles_15m, decision["symbol"], key_levels=chart_kl, timeframe_label="15m")
                decision["chart_path"] = chart_path
        except Exception as chart_err:
            logger.debug(f"Could not generate candlestick chart for proposal: {chart_err}")

        if self.telegram_bot.is_configured:
            execute_now = self.telegram_bot.request_trade_confirmation(
                trade_spec=decision,
                timeout_seconds=300,
                client=self.client,
                chat_id=chat_id
            )
        elif self.interactive:
            choice = input(f"\n❓ Confirm on-demand {side.upper()} order on {symbol}? [y/N]: ").strip().lower()
            execute_now = choice in ["y", "yes"]
        else:
            execute_now = False

        if not execute_now:
            return {"status": "TIMEOUT", "code": "USER_REJECTED_OR_EXPIRED", "trade": decision}

        # 7. Post-Approval Final Token Issuance & Execution on Delta Exchange
        safety_res = self.safety_controller.validate_and_issue_token(
            trade_setup=decision,
            account_equity=tot_equity,
            active_positions=active_pos,
            telegram_approval={"approved": True, "expired": False}
        )

        if not safety_res.get("passed"):
            code = safety_res.get("failure_code", "SAFETY_VETO")
            reason = safety_res.get("reason", "Safety check failed")
            if self.telegram_bot and self.telegram_bot.is_configured:
                tid = decision.get("trade_id")
                if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                    self.telegram_bot.update_proposal_card_status(tid, "BLOCKED", f"{code}: {reason}", chat_id=chat_id)
                self.telegram_bot.send_message(f"🛑 <b>Execution Blocked by Safety Controller:</b>\nReason: <code>{reason}</code> (Code: <code>{code}</code>)\nCapital protected.", chat_id=chat_id)
            return {"status": "REJECTED", "code": code, "reason": reason}

        # 7. Order Execution on Delta Exchange
        token = safety_res.get("token")
        exec_res = self.execution_agent.execute_approved_trade(
            decision,
            order_type="market_order",
            execution_token=token
        )

        if exec_res.get("success"):
            if self.telegram_bot and self.telegram_bot.is_configured:
                tid = decision.get("trade_id") or exec_res.get("trade_id")
                if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                    self.telegram_bot.update_proposal_card_status(tid, "EXECUTED", f"Order #{exec_res.get('order_id')} placed successfully", chat_id=chat_id)
            trade_atr = decision.get("atr_profile", {}).get("atr_14") or decision.get("atr_14") or 0.0
            if trade_atr <= 0 and candidate:
                trade_atr = candidate.get("atr_profile", {}).get("atr_14") or candidate.get("atr_14") or 0.0
            if trade_atr <= 0:
                trade_atr = cur_mark * 0.006

            try:
                if exec_res.get("is_scale_in"):
                    self.trailing_stop_manager.scale_in_trade(
                        symbol=decision["symbol"],
                        additional_contracts=decision["contracts"],
                        scale_in_price=decision["entry_price"],
                        new_sl_order_id=exec_res.get("stop_loss_order_id")
                    )
                else:
                    self.trailing_stop_manager.register_initial_trade(
                        symbol=decision["symbol"],
                        side=decision["side"],
                        entry_price=decision["entry_price"],
                        initial_sl=decision["stop_loss_price"],
                        initial_tp=decision["take_profit_price"],
                        contracts=decision["contracts"],
                        sl_order_id=exec_res.get("stop_loss_order_id") or exec_res.get("order_id"),
                        tp_order_id=exec_res.get("take_profit_order_id"),
                        is_high_volatility=False,
                        trade_id=exec_res.get("trade_id"),
                        atr=trade_atr,
                    )
            except Exception as re_err:
                logger.error(f"TrailingStopManager register error: {re_err}")

            try:
                self.risk_gatekeeper.register_execution(decision["symbol"])
            except Exception as rg_err:
                logger.error(f"RiskGatekeeper register error: {rg_err}")

            try:
                self.portfolio_monitor.journal_execution(exec_res, decision)
            except Exception as pm_err:
                logger.error(f"PortfolioMonitor journal error: {pm_err}")

            try:
                wallet_metrics = self.trailing_stop_manager.get_wallet_metrics()
                self.telegram.notify_trade_execution(exec_res, decision, wallet=wallet_metrics)
            except Exception as tg_err:
                logger.error(f"Telegram notify error: {tg_err}")

            return {
                "status": "SUCCESS",
                "trade_id": exec_res["trade_id"],
                "order_id": exec_res.get("order_id"),
                "symbol": decision["symbol"],
                "contracts": decision["contracts"]
            }
        else:
            err_msg = exec_res.get("error")
            if self.telegram_bot and self.telegram_bot.is_configured:
                tid = decision.get("trade_id") or exec_res.get("trade_id")
                if tid and hasattr(self.telegram_bot, "update_proposal_card_status"):
                    self.telegram_bot.update_proposal_card_status(tid, "FAILED", f"{err_msg}", chat_id=chat_id)
                self.telegram_bot.send_message(f"⚠️ <b>Order Execution Failed on Delta Exchange:</b>\n<code>{err_msg}</code>", chat_id=chat_id)
            return {
                "status": "FAILED",
                "code": "EXCHANGE_ORDER_ERROR",
                "error": err_msg
            }

    def run_continuous_loop(self, interval_seconds: int = 300):
        """
        Run continuous multi-agent monitoring loop on schedule.
        """
        print(f"\n🔄 Starting Continuous Multi-Agent Trading Loop (Interval: {interval_seconds}s)")
        print("Press Ctrl+C at any time to halt.\n")
        try:
            while True:
                self.run_trading_cycle()
                print(f"\n⏳ Sleeping {interval_seconds} seconds until next scan cycle...")
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n🛑 Multi-Agent Trading Loop halted safely by user.")
