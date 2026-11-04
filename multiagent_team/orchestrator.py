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
from multiagent_team.strategy_agent import StrategyAgent
from multiagent_team.risk_gatekeeper import RiskGatekeeperAgent
from multiagent_team.execution_agent import ExecutionAgent
from multiagent_team.portfolio_monitor import PortfolioMonitorAgent
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
        self.strategy_agent = StrategyAgent(target_rr_ratio=target_rr_ratio)
        self.risk_gatekeeper = RiskGatekeeperAgent(self.client, self.risk_manager)
        self.execution_agent = ExecutionAgent(self.client)
        self.portfolio_monitor = PortfolioMonitorAgent(self.client)
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
            f"• <b>Active Positions:</b> <b>{len(active_pos)}</b> | <b>Open Orders:</b> <b>{len(open_orders)}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "🌟 <b>PRIMARY ASSETS (CORE FOCUS):</b>"
        ]

        for sym in ["BTCUSD", "ETHUSD", "XAUUSD"]:
            d = symbols_data.get(sym)
            if not d:
                continue
            price = d.get("current_price", 0.0)
            m_reg = d.get("macro_monthly", {}).get("regime", "N/A").replace("MONTHLY_", "")
            w_reg = d.get("macro_weekly", {}).get("regime", "N/A").replace("WEEKLY_", "")
            d_reg = d.get("macro_daily", {}).get("regime", "N/A").replace("DAILY_", "")
            h4_reg = d.get("macro_4h", {}).get("regime", "N/A").replace("MACRO_", "")
            liq = d.get("liquidity", {})
            sweep = liq.get("sweep_type", "NONE")
            sweep_txt = f"Sweep: {sweep}" if liq.get("sweep_detected") else "Consolidating (No Sweep)"

            lines.append(f"• <b>{sym}:</b> <code>${price:,.2f}</code> | 1M:{m_reg} 1W:{w_reg} 1D:{d_reg} 4H:{h4_reg}")
            lines.append(f"  ↳ <i>{sweep_txt}</i>")

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
        lines.append("⚡ <i>Send /scan or /status anytime to get instant updates!</i>")
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
        # Step 3: Setup & Alpha Generation (Agent 2)
        # -----------------------------------------------------------------
        print("\n💡 [Agent 2: Strategy Agent] Evaluating trade candidate setups...")
        candidates = self.strategy_agent.find_best_candidates(scan_results)
        if not candidates:
            print("   No qualified setups found matching strict edge criteria this cycle.")
            return {"status": "NO_SETUPS_FOUND", "regime": market_regime, "scan_results": scan_results}

        print(f"   Found {len(candidates)} prospective trade setup(s):")
        for i, c in enumerate(candidates, 1):
            print(f"   [{i}] {c['symbol']} {c['side'].upper()} | Strategy: {c['strategy_name']} | R:R: {c['planned_rr_ratio']}:1")

        # -----------------------------------------------------------------
        # Step 4: Pre-Trade Discipline & Sizing Gate (Agent 3)
        # -----------------------------------------------------------------
        print("\n🛡️ [Agent 3: Risk Gatekeeper] Running Pre-Trade Discipline Gates...")
        approved_trades = []
        for c in candidates:
            sym = c.get("symbol", "")
            asset_leverage = int(os.getenv("BTC_LEVERAGE", "50")) if "BTC" in sym else int(os.getenv("ALT_LEVERAGE", "25"))
            decision = self.risk_gatekeeper.evaluate_candidate(c, leverage=asset_leverage)
            status = decision.get("gate_decision")
            if status == "APPROVED":
                print(f"   ✅ [APPROVED] {sym} ({decision.get('leverage', asset_leverage)}x): {decision['contracts']} contracts | Risk: ${decision['dollar_risk_usd']} ({decision['risk_pct']}%) | Margin: ${decision['required_margin_usd']}")
                # Propagate confluence details into trade spec
                decision["confluence"] = c.get("confluence", {})
                approved_trades.append(decision)
            else:
                print(f"   ❌ [REJECTED] {sym}: {decision.get('reason')}")

        if not approved_trades:
            print("\n   All prospective setups rejected by Risk Gatekeeper. Capital protected.")
            return {"status": "REJECTED_BY_RISK_GATE", "regime": market_regime, "scan_results": scan_results}

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
