"""
Central Multi-Agent Orchestrator for Delta Exchange 24/7 Automated & Semi-Automated Trading.
Coordinates 11 autonomous agents and shared infrastructure across 6 institutional layers
with standardized responses (SUCCESS, REJECTED, FAILED, TIMEOUT, SKIPPED).
"""

from typing import Dict, Any, List, Optional
import sys
import os
import time
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

    def check_and_dispatch_level_breakout_alerts(self, symbols_data: Optional[Dict[str, Any]] = None) -> int:
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
                sent = self.telegram.send_message(msg)
                if sent:
                    posted_alerts[alert_key] = now_ts
                    alerts_sent += 1
                    logger.info(f"Orchestrator: Dispatched pre-trade level alert for {alert_key}")
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

    def run_trading_cycle(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute one complete multi-agent cycle through Layers 1 to 5.
        Returns standardized status: SUCCESS, REJECTED, FAILED, TIMEOUT, SKIPPED.
        """
        cycle_start = time.time()
        self.system_monitor.increment_cycle()

        # Check and dispatch Daily Morning Crypto Briefing between 10:00 and 11:00 AM IST
        try:
            self.check_and_dispatch_daily_morning_briefing()
        except Exception as me:
            logger.debug(f"Daily morning briefing check skipped: {me}")

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
        scan_results = self.regime_analyst.scan_universe(active_symbols, resolution="60")
        market_regime = scan_results.get("overall_market_regime", "NEUTRAL")
        btc_adx = scan_results.get("btc_adx", 20.0)
        btc_vol = scan_results.get("btc_volatility_state", "NORMAL")
        print(f"   BTC Macro Posture: {market_regime} | ADX: {btc_adx} | Vol State: {btc_vol}")

        self.system_monitor.record_agent_duration("Agent1_RegimeAnalyst", (time.time() - t1) * 1000)

        # Check and dispatch pre-trade key level breakout/breakdown radar alerts
        try:
            self.check_and_dispatch_level_breakout_alerts(scan_results.get("symbols_data", {}))
        except Exception as le:
            logger.debug(f"Pre-trade level alert check skipped: {le}")

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

            if tm_res.get("passed"):
                print(f"   🟢 [TIME MACHINE APPROVED] {sym} {c['side'].upper()}: {tm_res['win_rate_pct']}% Win Rate (Wilson 95% Lower: {tm_res.get('wilson_ci_lower_pct')}%) | EV: +{tm_res['expected_value_r']}R | PF: {tm_res['profit_factor']}x")
                tm_qualified.append(c)
            else:
                print(f"   🔴 [TIME MACHINE VETO] {sym} {c['side'].upper()}: {tm_res.get('reason')}")
                self.system_monitor.record_trade_rejection("TIME_MACHINE_VETO", sym, tm_res.get("reason", ""))

        self.system_monitor.record_agent_duration("Agent4_TimeMachine", (time.time() - t4) * 1000)

        if not tm_qualified:
            print("\n   All setups rejected by Time Machine Simulation (insufficient statistical edge). Capital protected.")
            return {"status": "REJECTED", "code": "TIME_MACHINE_VETO", "reason": "No setup met >= 65% win rate edge with positive EV."}

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
                    decision["sentiment_report"] = sentiment_report.dict() if hasattr(sentiment_report, "dict") else (sentiment_report.model_dump() if hasattr(sentiment_report, "model_dump") else {})
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

        # Agent 6: Telegram 2-Way Human Authorization Gate
        executed_records = []
        for trade in approved_trades[:1]:
            print("\n📱 [Layer 3: Telegram Confirmation Gate] Sending proposal card to user...")
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
            print("   🛡️ [Pre-Execution Gate] Validating 14 Deterministic Safety Criteria...")
            
            # Fetch fresh active positions and equity for safety validation
            pos_res = self.client.get_positions()
            active_pos = [p for p in pos_res.get("result", []) if abs(float(p.get("size", 0))) > 0] if pos_res.get("success") else []
            wallet_res = self.client.get_wallet_balances()
            tot_equity = 1000.0
            if wallet_res.get("success"):
                for b in wallet_res.get("result", []):
                    if b.get("asset_symbol") in ["USDT", "USD"]:
                        tot_equity = float(b.get("balance", 1000.0))

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
                self.system_monitor.record_trade_rejection(failure_code, trade["symbol"], reason)
                return {"status": "REJECTED", "code": failure_code, "reason": reason}

            token = safety_token_res.get("token")
            print("   🚀 Safety Checks PASSED! Token issued. Submitting bracket order on Delta Exchange...")
            exec_res = self.execution_agent.execute_approved_trade(
                trade,
                order_type="limit_order",
                execution_token=token
            )
            self.system_monitor.record_agent_duration("Agent7_ExecutionEngine", (time.time() - t7) * 1000)

            if exec_res.get("success"):
                print(f"   🎉 Order successfully placed! Trade ID: {exec_res['trade_id']} | Order ID: #{exec_res.get('order_id')}")
                
                # Register into TrailingStopManager with Volatility Buffer
                is_high_vol = (
                    posture_data.get("btc_volatility_state") == "EXPANSION"
                    or "EXPANSION" in posture_data.get("posture", "")
                    or trade.get("is_high_volatility", False)
                )
                trade_atr = trade.get("atr_profile", {}).get("atr_14") or trade.get("atr_14") or 0.0
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
                self.system_monitor.save_metrics()
                return {
                    "status": "FAILED",
                    "code": "EXCHANGE_ORDER_ERROR",
                    "error": exec_res.get("error")
                }

        self.system_monitor.save_metrics()
        return {"status": "COMPLETED", "cycles_elapsed": round(time.time() - cycle_start, 2)}

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
