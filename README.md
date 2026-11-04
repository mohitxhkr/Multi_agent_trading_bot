# ⚡ Delta Exchange Multi-Agent Trading System

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Delta Exchange](https://img.shields.io/badge/Delta%20Exchange-India%20%7C%20Global%20%7C%20Testnet-0ea5e9?style=for-the-badge)](https://delta.exchange)
[![Telegram](https://img.shields.io/badge/Telegram-Real--Time%202--Way%20Gate-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org)
[![Cloud](https://img.shields.io/badge/Cloud%20Deployment-Render%2024%2F7-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)
[![Win Rate](https://img.shields.io/badge/Target%20Precision-80%25%20--%2090%25-brightgreen?style=for-the-badge)](https://github.com/mohitxhkr/Multi_agent_trading_bot)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

**An institutional-grade, disciplined multi-agent algorithmic trading system engineered for Delta Exchange perpetual futures.**  
*Specialized for Rapid Scalping on **BTC, ETH, and XAU (Gold)** with Smart Money Concepts (SMC), 15m Microstructure Sweeps, Ultra-Tight Stop Losses, 80–90% Precision Filters, Multi-Stage Scalper Trailing Stops (+0.50R BE), and Silent 24/7 Autonomous Cloud Operation.*

</div>

---

## 🏛️ System Architecture

<p align="center">
  <a href="https://raw.githubusercontent.com/mohitxhkr/Multi_agent_trading_bot/main/workflow_architecture_diagram.png" target="_blank">
    <img src="workflow_architecture_diagram.png" alt="Delta Exchange Multi-Agent 24/7 Trading Architecture" width="100%" style="border-radius: 8px;" />
  </a>
</p>

> **📥 Downloadable Architecture Assets:**  
> • **[Download High-Resolution PNG Image (1800 × 1250)](https://raw.githubusercontent.com/mohitxhkr/Multi_agent_trading_bot/main/workflow_architecture_diagram.png)**  
> • **[Download Scalable Vector (SVG Diagram)](workflow_architecture_diagram.svg)**  
> • **[Open Interactive HTML Architecture Viewer](workflow_architecture.html)**

---

### 🔄 End-to-End Scalper Workflow Flowchart

```mermaid
flowchart TD
    subgraph Cloud ["☁️ 24/7 Cloud Autonomous Runtime (Render)"]
        Scanner["Continuous Silent Market Scanner (Every 120s)"]
        Sentinel["High-Frequency Trailing Stop Sentinel (15s Loop)"]
    end

    subgraph Analyst ["🧠 6-Timeframe Institutional Confluence (Agent 1)"]
        M15["15m Scalp Structure: BSL/SSL Sweeps + MSS + Rejection Wicks >= 25%"]
        H1_H4["1H & 4H Trend Momentum Stack (EMA 9/21/50) & RSI Support/Resistance"]
        D1_W1["Daily & Weekly Trend Anchor (Strict High-Timeframe Trend Veto)"]
    end

    subgraph StrategyRisk ["🛡️ Alpha & Discipline Gates (Agents 2 & 3)"]
        Strategy["Agent 2: Strategy Generator<br/>• Score Threshold >= 75 (80-90% Win Rate Standard)<br/>• Tight Invalidation Stop: 0.20% - 0.40%<br/>• Achievable Same-Day Target: 2.0:1 R:R"]
        Risk["Agent 3: Risk Gatekeeper<br/>• Drawdown Circuit Breaker (< 5% max)<br/>• Capital Sizing: 75% to 95% available margin<br/>• Leverage: 50x Isolated BTC / 25x Alts & Gold<br/>• Max 3 positions · 0 duplicate symbols"]
    end

    subgraph TelegramGate ["📱 Telegram 2-Way Human Gate (Agent 4)"]
        TG["Proposal Card with Full Reasoning & Confluence Proof"]
        Confirm["User Taps: [✅ Confirm & Execute]"]
        Reject["User Taps: [❌ Reject Setup]"]
    end

    subgraph ExecutionBroker ["⚡ Delta Exchange Execution Infrastructure (Agent 5)"]
        Delta["Atomic 3-in-1 Limit Bracket (Entry + Native SL + TP)"]
    end

    subgraph TrailingShield ["🔒 Real Scalper Micro-Trailing Sentinel"]
        M1["Stage 1: At +0.50R -> Move SL to Breakeven (Zero Downside)"]
        M2["Stage 2: At +0.80R -> Lock +0.35R Profit in Bank"]
        M3["Stage 3: At +1.20R -> Lock +0.75R Profit in Bank"]
        M4["Stage 4: At +1.60R -> Lock +1.25R Profit in Bank"]
        M5["Stage 5: At +2.00R -> Full 2.0R Take Profit Realized"]
    end

    Scanner --> Analyst
    Analyst --> Strategy
    Strategy --> Risk
    Risk --> TG
    TG --> Confirm
    TG --> Reject
    Reject -->|Order Discarded| Cancelled["Zero Risk · Safe Discard"]
    Confirm -->|User Confirmed| Delta
    Delta --> Sentinel
    Sentinel --> M1
    M1 --> M2
    M2 --> M3
    M3 --> M4
    M4 --> M5
```

---

## 🌟 Primary Focus Assets & Rapid Scalping Discipline

The system is engineered specifically for **rapid intraday scalp resolutions (30 minutes to 3 hours)** so traders **never wait days in floating limbo**:

| Tier | Assets | Leverage | Minimum Score | Primary Focus & Execution Rules |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1 (PRIMARY)** | **`BTCUSD`**, **`ETHUSD`**, **`XAUUSD` (Gold)** | **50x (BTC)<br/>25x (ETH/XAU)** | **$\ge$ 75** (+10 Priority Boost) | **Core Focus.** Deep institutional liquidity, tight spreads, and clean 15-minute microstructure sweeps. Always prioritized first in scanning and Telegram proposals. |
| **Tier 2 (SECONDARY)** | `SOLUSD`, `ADAUSD`, `DOGEUSD`, `XRPUSD` | **25x Isolated** | **$\ge$ 80** | Subordinate assets evaluated only when Tier-1 assets are in flat consolidation. |

### 🛑 The Core Discipline Mandate
* **Target:** Seek up to **~2 perfect trades daily** on primary focus assets (`BTC`, `ETH`, `XAU`).
* **Non-Negotiable Rule:** A trade is **ONLY** proposed if a true **A+ perfect setup** is verified.
* **Capital Preservation Above All:** If the market is choppy, noisy, or consolidating without clean liquidity sweeps, **TAKE ZERO TRADES**. Better to take 0 trades on a choppy day than take a mediocre trade that loses capital.

---

## 🎯 How the 80%–90% Win-Rate Standard is Achieved

### 1. The 5-Layer Confluence Matrix
1. **Macro Trend Guard (4H & 1D):** Never buy intraday pullbacks into a confirmed Daily/Weekly downtrend (unless capitulation RSI $< 32$). Never short into confirmed HTF bull expansion (unless overbought RSI $> 68$).
2. **15m Liquidity Sweeps:** Trades trigger exclusively when retail stop-losses are swept above structural highs (BSL) or below structural lows (SSL).
3. **Rejection Wick ($\ge 25\%$):** The sweep candle must show an absorption wick covering at least a quarter of its full range, verifying that smart money absorbed the move.
4. **Market Structure Shift (MSS):** The bot waits for the following candle to close back beyond the sweep extreme, confirming directional reversal.
5. **Score Threshold ($\ge 75$):** Eliminates low-probability chop.

### 2. Low Stop Loss & Same-Session Targets (No Waiting for Days)
* **Micro Stop Loss:** Clamped between **0.20% and 0.40%** of price *(~$160–$310 on BTC, ~$5–$8 on ETH, ~$10–$18 on XAU)*.
* **Achievable Same-Day Target:** Fixed at **2.0:1 Reward-to-Risk ratio** *(0.40%–0.80% price move)*.
* **Rapid Completion:** Setups complete within **30 minutes to 3 hours**, never lingering for days.

### 3. The Scalper Micro-Trailing Engine
Stop losses ratchet forward step-by-step behind every micro impulse move:
* **Stage 1 (At +0.50R Profit):** Stop Loss moves to **Entry Price + 0.05% fee buffer** $\rightarrow$ Downside risk is 100% eliminated (free roll).
* **Stage 2 (At +0.80R Profit):** Stop Loss moves to **+0.35R locked profit** $\rightarrow$ Trade is permanently in the green.
* **Stage 3 (At +1.20R Profit):** Stop Loss moves to **+0.75R locked profit** $\rightarrow$ 75% of initial risk banked in cash.
* **Stage 4 (At +1.60R Profit):** Stop Loss moves to **+1.25R locked profit** $\rightarrow$ Guards against pre-target double-top/bottom rejections.
* **Stage 5 (At +2.00R Target):** Full Take Profit bracket order executes on the orderbook!

---

## 🤖 The Multi-Agent Trading Team

| Agent | Module | Role & Core Responsibilities |
| :--- | :--- | :--- |
| **Agent 1: Regime Analyst** | `multiagent_team/regime_analyst.py` | 6-timeframe analysis (15m, 1H, 4H, 1D, 1W, 1M). Computes EMA stacks (9/21/50/200), RSI, ATR, and Smart Money Concepts liquidity pools. |
| **Agent 2: Strategy Generator** | `multiagent_team/strategy_agent.py` | Evaluates technical edge, scores candidates (0–100), applies Primary Asset boost, and calculates tight SL and 2.0R TP bounds. |
| **Agent 3: Risk Gatekeeper** | `multiagent_team/risk_gatekeeper.py` | Absolute veto authority. Enforces account circuit breaker ($< 5\%$ daily drawdown), sizes 75%–95% margin at 50x/25x leverage, and enforces R:R $\ge 1.5:1$. |
| **Agent 4: Telegram Two-Way Gate** | `src/telegram_bot.py` | Sends rich interactive proposal card with inline buttons. Requires explicit user tap (`[Confirm]` / `[Reject]`) before any order executes. |
| **Agent 5: Execution Engine** | `multiagent_team/execution_agent.py` | Signs HMAC-SHA256 authenticated requests. Sets leverage and places native 3-in-1 atomic bracket orders on Delta Exchange. |
| **Agent 6: Trailing Stop Sentinel** | `src/trailing_stop_manager.py` | 15-second background loop. Detects order fills, trails stops through the 5 scalper stages (+0.50R BE, +0.80R lock, +1.20R lock, +1.60R lock), and notifies Telegram. |

---

## 📱 Telegram 2-Way Gate & Silent High-Signal Mode

The system is controlled via Telegram bot (`@DeltaTradenotifier_bot`):

### 🔕 Silent Mode Engaged (Zero 30-Minute Spam):
The bot operates **100% silently** in the background, only pushing notifications when action is needed:
1. 🎯 **Trade Setup Found:** Proposal card with `[✅ Confirm & Execute]` / `[❌ Reject Setup]`.
2. ⚡ **Order Filled:** Fill price, contracts, margin, and orderbook status.
3. 🛡️ **Micro-Trailing Activated:** Stops moved to Breakeven (+0.50R) or profits locked (+0.80R, +1.20R, +1.60R).
4. 💰 **Take Profit / Stop Loss Hit:** Full exit report with realized profit ($), % return, and updated wallet balance.
5. 🧹 **Stale Order Expiry:** Automatically cancels unfilled limit entry orders older than 90m to eliminate stale fills if market structure shifts.
6. 📱 **On-Demand Slash Commands:** Real-time responses to `/positions`, `/trade`, `/status`, `/scan`, `/orders`.

### Trade Proposal Preview:
```text
🚨 [HIGH PROBABILITY TRADE SETUP]
• Symbol: BTCUSD 🔴 SHORT (🌟 PRIMARY FOCUS ASSET)
• Strategy: Intraday_Scalp_BSL_Sweep_15m (Score: 75/100)
━━━━━━━━━━━━━━━━━━━━━━
• Entry: $78,633.00 (Limit Bracket)
• Stop Loss: $78,790.27 (Tight Risk: 0.20% / $157.27)
• Take Profit: $78,318.47 (Achievable Target: 2.0:1 R:R / +$314.53)
━━━━━━━━━━━━━━━━━━━━━━
• Position Size: 15 contracts (50x Isolated Leverage)
• Required Margin: $23.59 USD | Max Risk: $2.36 USD
• Trailing Plan: +0.50R -> BE | +0.80R -> Lock +0.35R | +1.20R -> Lock +0.75R | +2.0R -> TP
━━━━━━━━━━━━━━━━━━━━━━
[✅ Confirm & Execute]   [❌ Reject Setup]
```

### Supported In-Chat Slash Commands:
| Command | Action |
| :--- | :--- |
| `/trade` | Triggers an on-demand scalp scan for A+ setups; sends proposal or confirms: *"No perfect trade or setup found in the market right now. Capital is protected."* |
| `/positions` | Displays active positions: direction, contracts, entry, current mark price, SL, TP, and unrealized PnL ($ and %). |
| `/status` | Returns 24/7 cloud health, active positions, open orders, and available wallet balance. |
| `/scan` | Triggers an immediate multi-timeframe scan across all primary and secondary assets. |
| `/orders` | Displays active bracket Stop-Loss and Take-Profit orders on Delta Exchange. |
| `/help` | Displays command usage and help manual. |

---

## ⚙️ Environment Configuration (`.env`)

```ini
# Delta Exchange API Credentials
DELTA_ENVIRONMENT=testnet_india
DELTA_BASE_URL=https://cdn-ind.testnet.deltaex.org
DELTA_API_KEY=your_api_key_here
DELTA_API_SECRET=your_api_secret_here

# Asset Prioritization
PRIMARY_SYMBOLS=BTCUSD,ETHUSD,XAUUSD
DEFAULT_SYMBOLS=BTCUSD,ETHUSD,XAUUSD,SOLUSD,ADAUSD,DOGEUSD,XRPUSD

# Risk Management & Discipline Gates
MAX_RISK_PER_TRADE_PCT=0.05
MAX_CONCURRENT_POSITIONS=3
MAX_DAILY_DRAWDOWN_PCT=0.05
MIN_REWARD_TO_RISK_RATIO=1.5

# Leverage Directives
BTC_LEVERAGE=50
ALT_LEVERAGE=25
CAPITAL_ALLOCATION_MIN_PCT=0.75
CAPITAL_ALLOCATION_MAX_PCT=0.95

# Telegram 2-Way Gate
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_NOTIFICATIONS_ENABLED=true
```

---

## ☁️ Autonomous 24/7 Cloud Deployment

The system is deployed natively on **Render.com** via [`server.py`](server.py) and [`render.yaml`](render.yaml):

1. **Deploy to Render:** Connect your GitHub repository as a Web Service with start command `python server.py`.
2. **Keep-Alive Monitor:** Ping `https://your-service.onrender.com/health` every 5 minutes using [UptimeRobot](https://uptimerobot.com) to prevent cloud sleep.
3. **True Laptop-Closed Automation:** The bot scans markets continuously every 120s, monitors active orders every 15s, trails stops automatically, and pings your phone whenever an action is needed.

---

## 🚀 Local Quickstart & Commands

```bash
# 1. Clone repository
git clone https://github.com/mohitxhkr/Multi_agent_trading_bot.git
cd Multi_agent_trading_bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Test connectivity & Delta credentials
python main.py --test

# 4. Run instant multi-timeframe market scan
python main.py --scan

# 5. Run interactive trading engine (terminal confirmation)
python main.py --trade

# 6. Run background scanner (continuous local loop)
python run_247_scanner.py --interval 120
```

---

## 📂 Project Structure

```
Multi Agent Trading Bot/
├── multiagent_team/                  # The 6 Autonomous Agents
│   ├── orchestrator.py               # Central Multi-Agent Coordinator & Scan Pipeline
│   ├── regime_analyst.py             # Agent 1: 6-Timeframe Structure & SMC Sweeps
│   ├── strategy_agent.py             # Agent 2: 80-90% Win-Rate Alpha Generator
│   ├── risk_gatekeeper.py            # Agent 3: Mathematical Sizing & Capital Allocation
│   ├── execution_agent.py            # Agent 5: Atomic Bracket Order Engine
│   └── portfolio_monitor.py          # Portfolio State & Trade Journal
├── src/                              # Core Infrastructure Engines
│   ├── delta_client.py               # HMAC-SHA256 Delta Exchange REST Client
│   ├── technical_analysis.py         # SMC Liquidity Sweeps, MSS & Indicators
│   ├── trailing_stop_manager.py      # Scalper Sentinel (+0.5R BE, +0.8R lock, +1.2R, +1.6R)
│   ├── telegram_bot.py               # Interactive 2-Way Telegram Gate & Commands
│   ├── telegram_notifier.py          # Real-Time Lifecycle Push Notifications
│   ├── risk_manager.py               # Drawdown Circuit Breakers & R:R Verification
│   └── journal.py                    # Persistent Trade Journal & Performance
├── state/                            # Persistent Runtime State
│   ├── circuit_breaker_state.json    # Drawdown & daily loss tracker
│   ├── trailing_stop_state.json      # Live bracket trailing stages
│   └── trade_journal.json            # Completed trade histories
├── server.py                         # 24/7 Cloud Health Responder & Silent Scanner Daemon
├── render.yaml                       # Cloud deployment specification
├── requirements.txt                  # Minimal Python dependencies
├── workflow_architecture_diagram.png # High-Resolution PNG Architecture Diagram
├── workflow_architecture_diagram.svg # Scalable Vector Architecture Diagram
├── workflow_architecture.html        # Interactive HTML Architecture Viewer
└── README.md                         # Documentation
```

---

## 🛡️ Risk Disclaimer

*Cryptocurrency derivatives and margin trading involve substantial risk of capital loss. The automated multi-agent architecture enforces strict mathematical capital gates, tight stop-loss invalidation, and human-in-the-loop Telegram confirmation, but past performance does not guarantee future results. Test thoroughly on Delta Exchange testnet before deploying real capital.*

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
