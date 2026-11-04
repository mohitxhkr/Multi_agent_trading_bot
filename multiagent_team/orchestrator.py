"""
Multi-Agent Orchestrator for Delta Exchange Automated & Semi-Automated Trading.
Coordinates Regime Analyst, Strategy Agent, Risk Gatekeeper, Execution Agent,
and Portfolio Monitor into an integrated, disciplined workflow.
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
from multiagent_team.regime_analyst import RegimeAnalystAgent
from multiagent_team.exposure_coach import ExposureCoachAgent
from multiagent_team.strategy_agent import StrategyAgent
from multiagent_team.time_machine_agent import TimeMachineAgent
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.execution_agent import ExecutionAgent
from multiagent_team.portfolio_monitor import PortfolioMonitorAgent
from multiagent_team.adaptive_learning import AdaptiveLearningEngine
from multiagent_team.performance_coach import PerformanceCoachAgent
from src.telegram_notifier import TelegramNotifier
from src.telegram_bot import TelegramConfirmationBot
from src.trailing_stop_manager import TrailingStopManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("orchestrator")


class MultiAgentTradingOrchestrator:
    def __init__(
        self,
        client: Optional[DeltaExchangeClient] = None,
        symbols: Optional[List[str]] = None,
        interactive: bool = True,
        leverage: int = 5,
        target_rr_ratio: float = 2.0
    ):
        self.client = client or DeltaExchangeClient()
        self.risk_manager = RiskManager(
            max_risk_per_trade_pct=float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.01")),
            max_concurrent_positions=int(os.getenv("MAX_CONCURRENT_POSITIONS", "3")),
            max_daily_drawdown_pct=float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.05")),
            max_allowed_leverage=int(os.getenv("MAX_ALLOWED_LEVERAGE", "50")),
            min_reward_to_risk=target_rr_ratio
        )
        
        # Team of agents + Telegram Confirmation Bot + Trailing Stop Manager
        self.regime_analyst = RegimeAnalystAgent(self.client)
        self.exposure_coach = ExposureCoachAgent()
        self.strategy_agent = StrategyAgent(target_rr_ratio=target_rr_ratio)
        self.time_machine = TimeMachineAgent(self.client)
        self.risk_gatekeeper = RiskGatekeeperAgent(self.client, self.risk_manager)
        self.execution_agent = ExecutionAgent(self.client)
        self.portfolio_monitor = PortfolioMonitorAgent(self.client)
        self.adaptive_learner = AdaptiveLearningEngine()
        self.performance_coach = PerformanceCoachAgent()
        self.telegram = TelegramNotifier()
        self.telegram_bot = TelegramConfirmationBot()
        self.trailing_stop_manager = TrailingStopManager(client=self.client, telegram=self.telegram)

        raw_symbols = os.getenv("DEFAULT_SYMBOLS", "BTCUSD,ETHUSD,XAUUSD,SOLUSD,PAXGUSD,XRPUSD,DOGEUSD,ADAUSD")
        self.symbols = symbols or [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
        self.interactive = interactive
        self.leverage = leverage

    def get_market_digest_text(self, scan_results: Optional[Dict[str, Any]] = None) -> str:
        """Generate a clean Telegram-ready summary of market regimes for primary assets."""
        if not scan_results:
            scan_results = self.regime_analyst.scan_universe(self.symbols, resolution="60")

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

        sc = self.adaptive_learner.memory.get("scorecard", {})
        if sc.get("total_completed_trades", 0) > 0:
            lines.append(f"• <b>Self-Scorecard:</b> <b>{sc.get('winning_trades', 0)}W / {sc.get('losing_trades', 0)}L</b> ({sc.get('win_rate_pct', 0)}% Win Rate | {sc.get('average_trade_score', 0)}/100 Grade)")

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
        lines.append("⚪ <b>SECONDARY ASSETS (LESS IMPORTANT):</b>")
        for sym in ["SOLUSD", "XRPUSD", "DOGEUSD", "ADAUSD"]:
            d = symbols_data.get(sym)
            if not d:
                continue
            price = d.get("current_price", 0.0)
            liq = d.get("liquidity", {})
            sweep = liq.get("sweep_type", "NONE")
            sweep_tag = f"Sweep: {sweep}" if liq.get("sweep_detected") else "No Sweep"
            lines.append(f"• <code>{sym}</code>: ${price:.4f} ({sweep_tag})")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚡ <i>Send /positions, /trade, or /scan anytime!</i>")
        return "\n".join(lines)

    def run_trading_cycle(self) -> Dict[str, Any]:
        """
        Execute one full multi-agent trading decision pipeline.
        """
        print("\n" + "=" * 70)
        print("🤖 [DELTA EXCHANGE MULTI-AGENT TEAM] Starting Analysis & Trading Cycle")
        print("=" * 70)

        # -----------------------------------------------------------------
        # Step 1: Portfolio Health & Open Positions Check (Agent 5)
        # -----------------------------------------------------------------
        print("\n📊 [Agent 5: Portfolio Monitor] Inspecting current portfolio state...")
        pos_summary = self.portfolio_monitor.monitor_positions()
        active_cnt = pos_summary.get("active_count", 0)
        unrealized_pnl = pos_summary.get("total_unrealized_pnl_usd", 0.0)
        print(f"   Active Positions: {active_cnt} | Total Unrealized PnL: ${unrealized_pnl:.2f}")

        # Trailing Stop Protection for Active Positions
        trailing_updates = self.trailing_stop_manager.check_and_update_trailing_stops()
        if trailing_updates:
            print(f"   🛡️ Trailing Stop Manager applied {len(trailing_updates)} stop update(s).")

        # Stale Unfilled Limit Order Cleaner (> 90m old)
        stale_cancelled = self.portfolio_monitor.cancel_stale_orders(max_age_seconds=5400)
        if stale_cancelled:
            for sc in stale_cancelled:
                print(f"   🧹 [STALE ORDER CANCELLED] #{sc['order_id']} {sc['symbol']} ({sc['age_minutes']}m old)")
                if self.telegram_bot.is_configured:
                    self.telegram.send_message(
                        f"🧹 <b>[STALE ENTRY ORDER CANCELLED]</b>\n"
                        f"• Order <b>#{sc['order_id']}</b> ({sc['symbol']} {sc['side'].upper()})\n"
                        f"• Age: <b>{sc['age_minutes']} minutes</b> unfilled\n"
                        f"• Removed from orderbook to protect capital from outdated market levels."
                    )

        # -----------------------------------------------------------------
        # Step 2: Market Regime Analysis (Agent 1)
        # -----------------------------------------------------------------
        print(f"\n🔍 [Agent 1: Regime Analyst] Scanning {len(self.symbols)} symbols: {', '.join(self.symbols)}...")
        scan_results = self.regime_analyst.scan_universe(self.symbols, resolution="60")
        market_regime = scan_results.get("overall_market_regime", "NEUTRAL")
        print(f"   Overall Market Posture (BTC Anchor): {market_regime}")
        for sym, d in scan_results.get("symbols_data", {}).items():
            liq = d.get("liquidity", {})
            liq_str = f"Sweep: {liq.get('sweep_type', 'NONE')} -> Bias: {liq.get('bias', 'NEUTRAL')}" if liq else ""
            m_reg = d.get("macro_monthly", {}).get("regime", "N/A").replace("MONTHLY_", "")
            w_reg = d.get("macro_weekly", {}).get("regime", "N/A").replace("WEEKLY_", "")
            d_reg = d.get("macro_daily", {}).get("regime", "N/A").replace("DAILY_", "")
            h4_reg = d.get("macro_4h", {}).get("regime", "N/A").replace("MACRO_", "")
            print(f"   • {sym:<8} Price: ${d.get('current_price', 0):<9.2f} | 1M:{m_reg} 1W:{w_reg} 1D:{d_reg} 4H:{h4_reg} | {liq_str}")
            if liq and liq.get("sweep_detected"):
                print(f"     🌊 [LIQUIDITY SWEEP] {liq.get('narrative')}")

        # -----------------------------------------------------------------
        # Step 2.5: Exposure Coach & Market Posture Gate (Agent 1.5)
        # -----------------------------------------------------------------
        print("\n🧭 [Agent 1.5: Exposure Coach] Evaluating multi-asset breadth & market posture...")
        posture_data = self.exposure_coach.evaluate_market_posture(
            scan_results=scan_results,
            active_positions_count=active_cnt
        )
        print(f"   Market Health: {posture_data['health_score']}/100 | Posture: {posture_data['posture']} | Breadth: {posture_data['breadth_pct']}%")
        print(f"   Guidance: {posture_data['rationale']}")

        # Audit and refresh Next-Session Operating Rules
        try:
            self.performance_coach.audit_and_update_rules()
        except Exception as pe:
            logger.debug(f"Operating rules audit skipped: {pe}")

        if posture_data.get("cash_priority"):
            print(f"\n   🛑 [CASH PRIORITY HALT] Market breadth broken ({posture_data['breadth_pct']}%). All new trades blocked.")
            return {
                "status": "CASH_PRIORITY_HALT",
                "reason": posture_data.get("rationale"),
                "posture": posture_data,
                "regime": market_regime,
                "scan_results": scan_results
            }

        # -----------------------------------------------------------------
        # Step 3: Setup & Alpha Generation (Agent 2)
        # -----------------------------------------------------------------
        print("\n💡 [Agent 2: Strategy Agent] Evaluating trade candidate setups...")
        candidates = self.strategy_agent.find_best_candidates(scan_results)

        # In Defensive Caution, strictly filter out secondary altcoins to protect capital
        if posture_data.get("posture") == "DEFENSIVE_CAUTION" and candidates:
            tier1_only = [c for c in candidates if c.get("symbol") in ["BTCUSD", "ETHUSD", "XAUUSD"]]
            if len(tier1_only) < len(candidates):
                print(f"   🛡️ [DEFENSIVE CAUTION] Filtered out {len(candidates) - len(tier1_only)} altcoin setup(s). Focusing strictly on Tier-1 Core.")
            candidates = tier1_only

        if not candidates:
            print("   No qualified setups found matching strict edge criteria this cycle.")
            return {"status": "NO_SETUPS_FOUND", "regime": market_regime, "scan_results": scan_results}

        print(f"   Found {len(candidates)} prospective trade setup(s):")
        for i, c in enumerate(candidates, 1):
            print(f"   [{i}] {c['symbol']} {c['side'].upper()} | Strategy: {c['strategy_name']} | R:R: {c['planned_rr_ratio']}:1")

        # -----------------------------------------------------------------
        # Step 3.5: Time Machine Historical Simulation & Probability Engine (Agent 2.5)
        # -----------------------------------------------------------------
        print("\n⏳ [Agent 2.5: Time Machine Probability Engine] Simulating candidate setups against historical data...")
        tm_qualified_candidates = []
        for c in candidates:
            sym = c.get("symbol", "")
            raw_data = scan_results.get("symbols_data", {}).get(sym, {})
            candles_15m = raw_data.get("_raw_candles_15m")
            candles_1h = raw_data.get("_raw_candles_1h")

            tm_res = self.time_machine.simulate_setup(c, candles_15m=candles_15m, candles_1h=candles_1h)
            c["time_machine"] = tm_res

            if tm_res.get("passed"):
                print(f"   🟢 [TIME MACHINE CONFIRMED] {sym} {c['side'].upper()}: {tm_res['win_rate_pct']}% Win Rate ({tm_res['wins']}W/{tm_res['losses']}L) | EV: +{tm_res['expected_value_r']}R | PF: {tm_res['profit_factor']}x")
                tm_qualified_candidates.append(c)
            else:
                print(f"   🔴 [TIME MACHINE VETO] {sym} {c['side'].upper()}: {tm_res.get('reason')}")

        if not tm_qualified_candidates:
            print("\n   All prospective setups rejected by Time Machine Simulation (insufficient historical edge). Capital protected.")
            return {"status": "REJECTED_BY_TIME_MACHINE", "reason": "No setup met >= 68% historical win-rate edge with positive EV.", "regime": market_regime, "scan_results": scan_results}

        candidates = tm_qualified_candidates

        # -----------------------------------------------------------------
        # Step 4: Pre-Trade Discipline & Sizing Gate (Agent 3)
        # -----------------------------------------------------------------
        print("\n🛡️ [Agent 3: Risk Gatekeeper] Running Pre-Trade Discipline Gates...")
        approved_trades = []
        reject_reasons = []
        for c in candidates:
            sym = c.get("symbol", "")
            asset_leverage = int(os.getenv("BTC_LEVERAGE", "50")) if "BTC" in sym else int(os.getenv("ALT_LEVERAGE", "25"))
            decision = self.risk_gatekeeper.evaluate_candidate(c, leverage=asset_leverage)
            status = decision.get("gate_decision")
            if status == "APPROVED":
                print(f"   ✅ [APPROVED] {sym} ({decision.get('leverage', asset_leverage)}x): {decision['contracts']} contracts | Risk: ${decision['dollar_risk_usd']} ({decision['risk_pct']}%) | Margin: ${decision['required_margin_usd']}")
                # Propagate confluence & time machine details into trade spec
                decision["confluence"] = c.get("confluence", {})
                decision["time_machine"] = c.get("time_machine", {})
                approved_trades.append(decision)
            else:
                print(f"   ❌ [REJECTED] {sym}: {decision.get('reason')}")
                reject_reasons.append(f"{sym}: {decision.get('reason')}")

        if not approved_trades:
            print("\n   All prospective setups rejected by Risk Gatekeeper. Capital protected.")
            first_reason = reject_reasons[0] if reject_reasons else "Risk limits or capital allocation exceeded."
            return {"status": "REJECTED_BY_RISK_GATE", "reason": first_reason, "regime": market_regime, "scan_results": scan_results}

        # -----------------------------------------------------------------
        # Step 5: Telegram 2-Way Execution Gate (Agent 4 + Telegram Bot)
        # -----------------------------------------------------------------
        executed_records = []
        # Propose the top-ranked approved trade (since capital sizing allocates 75%-100% margin)
        for trade in approved_trades[:1]:
            print("\n📱 [Telegram 2-Way Confirmation Gate] Sending proposal to Telegram & awaiting confirmation...")
            print(f"   Contract: {trade['symbol']} | Side: {trade['side'].upper()} | Contracts: {trade['contracts']}")
            print(f"   Entry: ${trade['entry_price']:.2f} | Stop Loss: ${trade['stop_loss_price']:.2f} | Take Profit: ${trade['take_profit_price']:.2f}")
            print(f"   Max Risk: ${trade['dollar_risk_usd']:.2f} | Initial R:R: {trade['reward_to_risk_ratio']:.2f}:1")

            execute_now = False

            # First priority: 2-way Telegram confirmation
            if self.telegram_bot.is_configured:
                print("   ⏳ Awaiting user approval on Telegram (tapping [Confirm] or [Reject])...")
                execute_now = self.telegram_bot.request_trade_confirmation(trade, timeout_seconds=300)
            elif self.interactive:
                user_choice = input("\n   ❓ Confirm order execution on Delta Exchange? [y/N]: ").strip().lower()
                execute_now = user_choice in ["y", "yes"]
            else:
                print("   ⚠️ Neither Telegram nor interactive console is available. Execution halted for safety.")
                execute_now = False

            if execute_now:
                print("   🚀 User APPROVED! Executing bracket order on Delta Exchange...")
                exec_res = self.execution_agent.execute_approved_trade(trade, order_type="limit_order")
                if exec_res.get("success"):
                    print(f"   🎉 Order successfully placed! Trade ID: {exec_res['trade_id']} | Order ID: {exec_res.get('order_id')}")
                    # Register into TrailingStopManager
                    self.trailing_stop_manager.register_initial_trade(
                        symbol=trade["symbol"],
                        side=trade["side"],
                        entry_price=trade["entry_price"],
                        initial_sl=trade["stop_loss_price"],
                        initial_tp=trade["take_profit_price"],
                        contracts=trade["contracts"],
                        sl_order_id=exec_res.get("stop_loss_order_id") or exec_res.get("order_id"),
                        tp_order_id=exec_res.get("take_profit_order_id"),
                    )
                    # Journal execution into persistent memory (Agent 5)
                    self.portfolio_monitor.journal_execution(exec_res, trade)
                    executed_records.append(exec_res)
                    # Instant Telegram execution receipt
                    wallet_metrics = self.trailing_stop_manager.get_wallet_metrics()
                    self.telegram.notify_trade_execution(exec_res, trade, wallet=wallet_metrics)
                else:
                    print(f"   ⚠️ Order execution failed: {exec_res.get('error')}")
            else:
                print("   ⏭️ Trade skipped or rejected by user. Capital protected.")

        # Update daily digest
        self.portfolio_monitor.generate_daily_digest()

        return {
            "status": "COMPLETED",
            "market_regime": market_regime,
            "approved_trades_count": len(approved_trades),
            "executed_trades_count": len(executed_records),
            "executed_records": executed_records,
            "scan_results": scan_results
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
