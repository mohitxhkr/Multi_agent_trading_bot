# ⚡ Delta Exchange Multi-Agent Trading System

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Delta Exchange](https://img.shields.io/badge/Delta%20Exchange-India%20%7C%20Global%20%7C%20Testnet-0ea5e9?style=for-the-badge)](https://delta.exchange)
[![Telegram](https://img.shields.io/badge/Telegram-Real--Time%20Alerts-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org)
[![Cloud](https://img.shields.io/badge/Cloud%20Deployment-Render%2024%2F7-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

**An institutional-grade, disciplined multi-agent algorithmic trading bot designed for Delta Exchange perpetual futures.**  
*Powered by Smart Money Concepts (SMC), Liquidity Sweep Detection, strict Risk Gatekeepers, and 24/7 Telegram push notifications.*

</div>

---

## 🏛️ System Architecture

![Multi-Agent Architecture](workflow_architecture_diagram.png)

> **📥 Downloadable Architecture Formats:**  
> • **[High-Resolution Graphic (PNG Image)](workflow_architecture_diagram.png)**  
> • **[Vector Diagram (Scalable SVG)](workflow_architecture_diagram.svg)**  
> • **[Interactive HTML Viewer &amp; Print/PDF Layout](workflow_architecture.html)**

```
                           24/7 CLOUD AUTONOMOUS SCANNER (Render)
                              (server.py / run_247_scanner.py)
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
      [Agent 1: 5-Timeframe Scout]                    [Agent 5: Portfolio Monitor]
   1M (Month Open) · 1W (Weekly EMA)                Monitors PnL & Circuit Breaker
    1D (Daily Stack) · 4H (Cycle)                                  │
    1H (Liquidity Sweep + MSS)                                     │
                       │                                           │
                       └─────────────────────┬─────────────────────┘
                                             │  Qualified Setup (Score >= 70, R:R >= 2.0)
                                             ▼
                                [Agent 3: Risk Gatekeeper]
                               Sizes 75%–100% Available Capital
                                50x BTC / 25x SOL, XAU (Gold), Alts
                                             │
                                             ▼
                             📱 TELEGRAM 2-WAY CONFIRMATION GATE
                         Pushes Full Reasoning & Confluence to Phone
                         [✅ Confirm & Execute]   [❌ Reject Trade]
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
             [❌ User Taps Reject]                       [✅ User Taps Confirm]
          Order Dropped · Zero Risk                                │
                                                                   ▼
                                                       🚀 [Agent 4: Execution]
                                                     Places 3-in-1 Bracket Order
                                                  (Entry + Protective SL + 1:2 TP)
                                                                   │
                                                                   ▼
                                                    🛡️ TRAILING STOP MANAGER (15s Loop)
                                                    • +1.0R ──► Breakeven (0 Risk)
                                                    • +2.0R ──► Lock +1.0R & TP to 1:3
                                                    • +3.0R ──► Lock +2.0R & TP to 1:5
```

---

## 🤖 The 5-Agent Trading Team

The architecture separates responsibilities into specialized autonomous agents:

| Agent | Module | Role & Responsibilities |
| :--- | :--- | :--- |
| **Agent 1: Regime Analyst** | `multiagent_team/regime_analyst.py` | Multi-timeframe trend analysis (EMA 9/21/50/200, RSI-14, ATR-14, MACD) and **Smart Money Concepts (SMC)** Liquidity Sweep mapping (Buy-Side vs. Sell-Side Liquidity). |
| **Agent 2: Strategy Generator** | `multiagent_team/strategy_agent.py` | Generates high-expectancy trade setups with explicit Entry, Stop-Loss, and Take-Profit. Enforces non-negotiable **$\ge$ 2.0 : 1 Reward-to-Risk ratio**. |
| **Agent 3: Risk Gatekeeper** | `multiagent_team/risk_gatekeeper.py` | Absolute veto authority. Enforces account circuit breaker (< 5% daily drawdown), allocates **75% to 100% capital**, and sizes positions at **50x on BTC** and **25x on Alts & Gold**. |
| **Agent 4: Execution Agent** | `multiagent_team/execution_agent.py` | HMAC-SHA256 authenticated execution. Submits **Atomic 3-in-1 Bracket Orders** (Entry + OCO Stop-Loss + OCO Take-Profit) directly to Delta Exchange. |
| **Agent 5: Portfolio Monitor** | `multiagent_team/portfolio_monitor.py` | Real-time mark-to-market PnL monitoring, liquidation distance tracking, trade journaling to `state/trade_journal.json`, and daily performance digest generation. |

---

## 🌊 Smart Money Concepts & Liquidity Sweeps

Every trading decision is rooted in institutional order flow mechanics:

* **Buy-Side Liquidity (BSL):** Resting stop-losses of short sellers clustered above structural swing highs.
* **Sell-Side Liquidity (SSL):** Resting stop-losses of breakout buyers clustered below key swing lows.
* **Turtle-Soup / Stop-Runs:** When price pierces a liquidity level (wick sweep) and aggressively rejects, smart money absorbs retail stops:
  * **Bearish BSL Sweep:** Wicks above resistance $\rightarrow$ Order flow expands **DOWNSIDE** targeting Sell-Side Liquidity.
  * **Bullish SSL Sweep:** Wicks below support $\rightarrow$ Order flow expands **UPSIDE** targeting Buy-Side Liquidity.

---

## ⚙️ Configuration (`.env`)

```ini
# Delta Exchange API Credentials
DELTA_ENVIRONMENT=testnet_india
DELTA_BASE_URL=https://cdn-ind.testnet.deltaex.org
DELTA_API_KEY=your_api_key_here
DELTA_API_SECRET=your_api_secret_here

# Risk Management & Circuit Breaker
MAX_RISK_PER_TRADE_PCT=0.05
MAX_CONCURRENT_POSITIONS=3
MAX_DAILY_DRAWDOWN_PCT=0.05
MAX_ALLOWED_LEVERAGE=50
MIN_REWARD_TO_RISK_RATIO=2.0

# Leverage & Capital Allocation Directives
CAPITAL_ALLOCATION_MIN_PCT=0.75
CAPITAL_ALLOCATION_MAX_PCT=1.00
BTC_LEVERAGE=50
ALT_LEVERAGE=25

# Multi-Agent Scan Settings
DEFAULT_SYMBOLS=BTCUSD,ETHUSD,SOLUSD,XAUUSD,PAXGUSD,XRPUSD,DOGEUSD,ADAUSD
TRADING_MODE=interactive

# Telegram Bot Push Alerts
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_NOTIFICATIONS_ENABLED=true
```

---

## 🚀 Quickstart & Execution Modes

### 1. Installation
```bash
git clone https://github.com/mohitxhkr/Multi_agent_trading_bot.git
cd Multi_agent_trading_bot
pip install -r requirements.txt
```

### 2. Run Diagnostics & Connectivity Test
```bash
python main.py --test
```

### 3. Run Single Analysis & Market Scan
```bash
python main.py --scan
```

### 4. Interactive Semi-Autonomous Mode
Prompts for your explicit confirmation (`[y/N]`) before any order is submitted:
```bash
python main.py --trade
```

### 5. Run Continuous 24/7 Scanner (Local)
Silently hunts for liquidity sweeps every 120s and alerts your Telegram:
```bash
python run_247_scanner.py --interval 120
```

---

## ☁️ 24/7 Cloud Deployment (Runs When PC is Off)

The bot includes cloud-native support for **Render.com** (100% Free Tier) via [`server.py`](server.py) and [`render.yaml`](render.yaml):

1. **Deploy to Render:** Connect your GitHub repo as a **Web Service** on Render with start command: `python server.py`.
2. **Keep Awake via UptimeRobot:** Render's free tier sleeps after 15 minutes of inactivity. Set up a free monitor at [UptimeRobot](https://uptimerobot.com) to ping `https://your-service.onrender.com/health` every 5 minutes.
3. **True 24/7 Independence:** Your bot runs continuously in the cloud, placing bracket trades and pushing notifications to your phone even if your computer is completely turned off.

---

## 📂 Project Structure

```
Multi Agent Trading Bot/
├── .agents/                          # Custom agent guidelines & rules
├── multiagent_team/                  # The 5 Autonomous Trading Agents
│   ├── orchestrator.py               # Central Multi-Agent Pipeline Coordinator
│   ├── regime_analyst.py             # Agent 1: Market Structure & Technicals
│   ├── strategy_agent.py             # Agent 2: Setup & Alpha Generation
│   ├── risk_gatekeeper.py            # Agent 3: Mathematical Sizing & Veto Gates
│   ├── execution_agent.py            # Agent 4: Atomic Bracket Order Manager
│   └── portfolio_monitor.py          # Agent 5: Real-Time PnL & Trade Journal
├── src/                              # Core Infrastructure Engines
│   ├── delta_client.py               # HMAC-SHA256 Delta Exchange REST Client
│   ├── technical_analysis.py         # Indicators & SMC Liquidity Sweep Engine
│   ├── risk_manager.py               # Drawdown Circuit Breakers & Sizing Math
│   ├── telegram_notifier.py          # Real-Time Push Notification Engine
│   └── journal.py                    # Trade Execution Journal & Analytics
├── state/                            # Persistent Runtime State
│   ├── circuit_breaker_state.json    # Drawdown tracking
│   └── trade_journal.json            # Execution logs
├── reports/                          # Markdown Performance Digests
├── main.py                           # Unified Multi-Agent CLI
├── server.py                         # Cloud Healthcheck Server (24/7 Daemon)
├── run_247_scanner.py                # Standalone Background Scanner
├── Dockerfile                        # Container specification
├── render.yaml                       # Cloud deployment blueprint
├── requirements.txt                  # Minimal Python dependencies
└── README.md                         # Documentation
```

---

## 🛡️ Risk Disclaimer

*Cryptocurrency derivatives trading involves substantial risk of loss and is not suitable for every investor. The high degree of leverage can work against you as well as for you. Always test trading algorithms thoroughly in a testnet/demo environment before deploying real capital.*

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
