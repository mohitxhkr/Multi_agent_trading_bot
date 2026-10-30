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
        
        # Team of 5 agents + Telegram Notifier
        self.regime_analyst = RegimeAnalystAgent(self.client)
        self.strategy_agent = StrategyAgent(target_rr_ratio=target_rr_ratio)
        self.risk_gatekeeper = RiskGatekeeperAgent(self.client, self.risk_manager)
        self.execution_agent = ExecutionAgent(self.client)
        self.portfolio_monitor = PortfolioMonitorAgent(self.client)
        self.telegram = TelegramNotifier()

        raw_symbols = os.getenv("DEFAULT_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT")
        self.symbols = symbols or [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
        self.interactive = interactive
        self.leverage = leverage

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
            print(f"   • {sym:<8} Price: ${d.get('current_price', 0):<9.2f} | RSI: {d.get('rsi_14', 0):<5.1f} | Regime: {d.get('regime', 'NEUTRAL'):<16} | {liq_str}")
            if liq and liq.get("sweep_detected"):
                print(f"     🌊 [LIQUIDITY SWEEP] {liq.get('narrative')}")

        # -----------------------------------------------------------------
        # Step 3: Setup & Alpha Generation (Agent 2)
        # -----------------------------------------------------------------
        print("\n💡 [Agent 2: Strategy Agent] Evaluating trade candidate setups...")
        candidates = self.strategy_agent.find_best_candidates(scan_results)
        if not candidates:
            print("   No qualified setups found matching strict edge criteria this cycle.")
            return {"status": "NO_SETUPS_FOUND", "regime": market_regime}

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
                approved_trades.append(decision)
                # Instant Telegram alert when a perfect qualified opportunity is identified
                self.telegram.notify_perfect_trade_opportunity(decision)
            else:
                print(f"   ❌ [REJECTED] {sym}: {decision.get('reason')}")

        if not approved_trades:
            print("\n   All prospective setups rejected by Risk Gatekeeper. Capital protected.")
            return {"status": "REJECTED_BY_RISK_GATE", "regime": market_regime}

        # -----------------------------------------------------------------
        # Step 5: Execution Management (Agent 4)
        # -----------------------------------------------------------------
        executed_records = []
        for trade in approved_trades:
            print("\n🚀 [Agent 4: Execution Agent] Ready to execute:")
            print(f"   Contract: {trade['symbol']} | Side: {trade['side'].upper()} | Contracts: {trade['contracts']}")
            print(f"   Entry: ${trade['entry_price']:.2f} | Stop Loss: ${trade['stop_loss_price']:.2f} | Take Profit: ${trade['take_profit_price']:.2f}")
            print(f"   Max Risk: ${trade['dollar_risk_usd']:.2f} | Reward/Risk: {trade['reward_to_risk_ratio']:.2f}:1")

            execute_now = True
            if self.interactive:
                user_choice = input("\n   ❓ Confirm order execution on Delta Exchange? [y/N]: ").strip().lower()
                if user_choice not in ["y", "yes"]:
                    print("   ⏭️ Trade execution skipped by user.")
                    execute_now = False

            if execute_now:
                exec_res = self.execution_agent.execute_approved_trade(trade, order_type="limit_order")
                if exec_res.get("success"):
                    print(f"   🎉 Order successfully placed! Trade ID: {exec_res['trade_id']} | Order ID: {exec_res.get('order_id')}")
                    # Step 6: Journal execution into persistent memory (Agent 5)
                    self.portfolio_monitor.journal_execution(exec_res, trade)
                    executed_records.append(exec_res)
                    # Instant Telegram execution receipt
                    self.telegram.notify_trade_execution(exec_res, trade)
                else:
                    print(f"   ⚠️ Order execution failed: {exec_res.get('error')}")

        # Update daily digest
        self.portfolio_monitor.generate_daily_digest()

        return {
            "status": "COMPLETED",
            "market_regime": market_regime,
            "approved_trades_count": len(approved_trades),
            "executed_trades_count": len(executed_records),
            "executed_records": executed_records
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
