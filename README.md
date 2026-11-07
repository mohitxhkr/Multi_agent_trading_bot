# ⚡ Delta Exchange Multi-Agent Quantitative Trading System

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Delta Exchange](https://img.shields.io/badge/Delta%20Exchange-India%20%7C%20Global%20%7C%20Testnet-0ea5e9?style=for-the-badge)](https://delta.exchange)
[![Architecture](https://img.shields.io/badge/Architecture-6--Layer%20%7C%2010--Agent-blueviolet?style=for-the-badge)](https://github.com/mohitxhkr/Multi_agent_trading_bot)
[![Security](https://img.shields.io/badge/Security-HMAC%20Token%20%7C%20Zero--Trust-green?style=for-the-badge)](https://github.com/mohitxhkr/Multi_agent_trading_bot)
[![Tests](https://img.shields.io/badge/Tests-16%2F16%20Passing%20(100%25)-brightgreen?style=for-the-badge)](https://github.com/mohitxhkr/Multi_agent_trading_bot)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

**An institutional-grade, evidence-driven algorithmic trading system engineered for Delta Exchange perpetual futures.**  
*Specialized for rapid intraday scalping on **BTC, ETH, and XAU (Gold)** with Smart Money Concepts (SMC), 15m Liquidity Sweeps, Walk-Forward Probability Backtests, a 14-Criterion Deterministic Safety Controller, Multi-Horizon Circuit Breakers, and Dual SQLite/JSON Event Journaling.*

</div>

---

## 🏛️ System Architecture

<p align="center">
  <img src="workflow_architecture_diagram.png" alt="Delta Exchange Multi-Agent Trading System Architecture" width="100%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);" />
</p>

---

## 🔄 End-to-End System Workflow

The system coordinates trade discovery, mathematical validation, and execution across **6 sequential layers**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LAYER 1: MARKET INTELLIGENCE                           │
│   Data Validator  ──>  Agent 1: Regime Analyst  ──>  Agent 2: Exposure Coach│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    LAYER 2: STRATEGY & VALIDATION                           │
│      Agent 3: Strategy Generator  ──>  Agent 4: Time Machine Simulator      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    LAYER 3: RISK & AUTHORIZATION                            │
│     Agent 5: Risk Gatekeeper  ──>  Agent 6: Telegram Confirmation Gate      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│             LAYER 4: DETERMINISTIC SAFETY & EXECUTION                       │
│    Deterministic Safety Controller  ──>  Agent 7: Delta Execution Engine    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                   LAYER 5: SENTINEL & LIFECYCLE JOURNAL                     │
│    Agent 8: Micro-Trailing Sentinel ──> Dual SQLite / JSON Event Store      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                   LAYER 6: CONTINUOUS LEARNING & COACHING                   │
│     Agent 9: Adaptive Learner  ──>  Agent 10: Performance Coach & Rules     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Execution Flow Sequence:
1. **Market Scanning & Validation:** The `MarketDataValidator` validates price feeds for missing bars, staleness ($>60\text{s}$), or abnormal price wicks ($>8\%$).
2. **Macro Context & Posture:** **Agent 1** analyzes 6-timeframe order flow, market-wide breadth (% of assets $> 20\text{ EMA}$), and ETH/BTC relative strength. **Agent 2** establishes the global market posture (`AGGRESSIVE_EXPANSION`, `DEFENSIVE_CAUTION`, `RECOVERY`, or `CASH_PRIORITY`).
3. **Setup Formulation:** **Agent 3** identifies 15m liquidity sweeps (BSL/SSL), verifies candle body Market Structure Shifts (MSS), and attaches structural stops (synthetic stops prohibited).
4. **Empirical Probability Simulation:** **Agent 4** simulates identical past setups across 400+ bars. It runs 70/30 in-sample and out-of-sample forward verification, deducts exchange friction, and applies a Wilson 95% Confidence Interval. If historical data is insufficient, it strictly rejects the trade (`INSUFFICIENT_DATA`).
5. **Mathematical Position Sizing:** **Agent 5** calculates contract quantities based on a hard dollar risk ceiling ($\le \$4.00$). If the exchange minimum lot exceeds the risk budget, it returns `NO_TRADE` with 0 contracts.
6. **Two-Way Confirmation Gate:** **Agent 6** delivers an interactive approval card to Telegram with cryptographic, parameter-bound nonces. Sender IDs are authenticated, and replayed callbacks are blocked.
7. **Deterministic Safety Controller:** Evaluates **14 non-negotiable risk invariants** in pure Python code. If all 14 criteria pass, it issues an HMAC-SHA256 signed execution token with a 30-second TTL.
8. **Idempotent Execution & Stop Verification:** **Agent 7** places orders carrying unique client order IDs (`client_order_id`). It reconciles order history before retrying on timeouts. After fill, it verifies that the exchange protective stop is active; if protection fails, it triggers an emergency market close.
9. **Active Position Ratchet:** **Agent 8** manages trailing stops through breathing cushions, green profit locks ($+0.30\text{R}$ to $+0.85\text{R}$), and runner targets while logging lifecycle events into the authoritative SQLite event store (`state/trading_journal.db`).
10. **Feedback & Learning:** Upon closure, **Agent 9** scores the trade ($0-100$) and records pattern metrics. **Agent 10** monitors cohort performance and updates operating rules.

---

## 🤖 Detailed Breakdown of the 10 Specialized Agents

### 1️⃣ Agent 1: Market Regime Analyst
* **Module:** [`multiagent_team/regime_analyst.py`](multiagent_team/regime_analyst.py)
* **Core Task:** Classifies market trend, structural order flow, and relative asset strength across 6 timeframes.
* **Inputs:** 15m, 1H, 4H, Daily, Weekly, and Monthly candlestick series, live Level-2 order books, and ticker statistics.
* **Processing Logic:**
  * Validates feed integrity via `MarketDataValidator`.
  * Computes 21, 50, and 200 EMAs, 14-period RSI, 14-period ADX, and intraday VWAP.
  * Measures **Market-Wide Breadth** (% of universe $> 20\text{ EMA}$) and **ETH/BTC Relative Strength**.
  * Identifies funding rate skew to filter crowded longs ($>+0.03\%$) or short cascades.
* **Output:** Regime classifications, trend directions, breadth percentage, and support/resistance anchors.

### 2️⃣ Agent 2: Exposure Coach & Market Posture Engine
* **Module:** [`multiagent_team/exposure_coach.py`](multiagent_team/exposure_coach.py)
* **Core Task:** Dictates capital exposure, allowable leverage, and portfolio risk posture based on macro health.
* **Inputs:** Agent 1 breadth metrics, account margin utilization, and consecutive loss history.
* **Processing Logic:**
  * Assesses Market Health ($0-100$).
  * Enforces Postures:
    * `AGGRESSIVE_EXPANSION` (Health $\ge 75$): 100% risk budget, up to 2 concurrent positions.
    * `MODERATE_SELECTIVE` (Health $50-74$): 75% risk budget, restricted to Tier-1 (`BTC`, `ETH`, `XAU`).
    * `DEFENSIVE_CAUTION` (Health $32-49$): 50% risk budget, max 1 open trade.
    * `RECOVERY_POSTURE`: Triggered after 2 consecutive losses; cuts risk by 50% and clamps leverage.
    * `CASH_PRIORITY` (Health $< 32$): **0% risk budget. All new entries blocked.**
* **Output:** Operational posture, leverage caps, and asset whitelist.

### 3️⃣ Agent 3: Alpha Strategy Generator
* **Module:** [`multiagent_team/strategy_agent.py`](multiagent_team/strategy_agent.py)
* **Core Task:** Formulates precise entry, stop-loss, and take-profit trade setups using Smart Money Concepts.
* **Inputs:** Multi-timeframe structures, VWAP levels, liquidity sweeps, and pattern memory adjustments.
* **Processing Logic:**
  * Rejects unconfirmed wicks: requires candle body close confirming Market Structure Shift (MSS).
  * Enforces **Structural Stop Invalidation**: Stop loss must align with structural swing extremes. Synthetic or arbitrary stops are strictly vetoed.
  * Mandates asymmetric payout: Planned Reward-to-Risk must be $\ge 2.2:1$.
  * Assigns quality scores ($0-100$). Minimum score threshold: $\ge 85$ for Primary assets; $\ge 90$ for Secondary assets.
* **Output:** Candidate trade setups with bounded 60-minute time-to-live (TTL).

### 4️⃣ Agent 4: Time Machine Probability Engine
* **Module:** [`multiagent_team/time_machine_agent.py`](multiagent_team/time_machine_agent.py)
* **Core Task:** Forward-simulates candidate setups against historical data to ensure empirical positive expectancy.
* **Inputs:** Setup parameters and 400+ historical 15m candles.
* **Processing Logic:**
  * **Zero Synthetic Stats Mandate:** If candles $< 60$, returns `INSUFFICIENT_DATA`. If matches $< 8$, returns `INSUFFICIENT_SAMPLE`. Never fabricates hypothetical wins or win rates.
  * **Walk-Forward Separation:** 70% in-sample training / 30% out-of-sample forward verification.
  * **Institutional Friction:** Deducts Delta maker/taker fees ($0.10\%$), expected slippage ($0.06\%$), and funding drag.
  * **Wilson 95% Confidence Interval:** Requires lower CI bound $\ge 45\%$ to prevent small-sample overfitting.
  * **Decision Standard:** Win Rate $\ge 65\%$, Friction EV $\ge +0.30\text{R}$, Profit Factor $\ge 1.50\text{x}$, and positive OOS expectancy.
* **Output:** Statistical approval or veto with empirical metrics.

### 5️⃣ Agent 5: Pre-Trade Risk Gatekeeper
* **Module:** [`multiagent_team/risk_gatekeeper.py`](multiagent_team/risk_gatekeeper.py)
* **Core Task:** Enforces account risk budgets, authoritative contract sizing, and exchange margin rules.
* **Inputs:** Net equity, available balance, product specifications (lot size, contract value, MMR), open positions.
* **Processing Logic:**
  * **Hard Dollar Ceiling:** Capped at $\min(\text{Equity} \times \text{max\_risk\_pct}, \$4.00)$. High conviction cannot inflate dollar risk.
  * **Minimum Lot Protection:** If the minimum contract risk exceeds the risk budget, returns `gate_decision: "NO_TRADE"` and `contracts: 0`.
  * **MMR Liquidation Buffer:** Verifies liquidation price is $\ge 3.0\times$ stop loss distance away; automatically de-leverages if buffer is insufficient.
  * **Correlated Exposure Gate:** Clamps concurrent directional crypto trades to a maximum of 2.
* **Output:** Sized trade orders or strict `NO_TRADE` / `REJECTED` decisions.

### 6️⃣ Agent 6: Telegram Two-Way Confirmation Gate
* **Module:** [`src/telegram_bot.py`](src/telegram_bot.py)
* **Core Task:** Provides secure human authorization through interactive Telegram messages.
* **Inputs:** Approved trade specifications from Agent 5.
* **Processing Logic:**
  * **Sender Authentication:** Authenticates Telegram user ID against `AUTHORIZED_TELEGRAM_USERS`.
  * **Parameter-Bound Nonces:** Binds approvals to exact trade parameters; replayed nonces are rejected.
  * **Price Drift Revalidation:** Re-queries Delta Exchange mark price upon callback click; cancels trade if price drifted $> 0.40\%$.
  * **Auditable History:** Logs all requests, timestamps, and confirmations in [`state/telegram_approvals_audit.json`](state/telegram_approvals_audit.json).
* **Output:** User authorization confirmation or timeout rejection.

### 7️⃣ Agent 7: Delta Execution Engine
* **Module:** [`multiagent_team/execution_agent.py`](multiagent_team/execution_agent.py)
* **Core Task:** Submits orders with exchange-level idempotency and validates protective stops.
* **Inputs:** Approved trade setup, signed safety token, Delta REST client.
* **Processing Logic:**
  * Validates HMAC execution token issued by the Deterministic Safety Controller.
  * Assigns unique `client_order_id`.
  * **Pre-Retry Reconciliation:** If an ambiguous network timeout occurs, queries Delta Exchange order history and open orders before retrying to prevent duplicate fills.
  * **Mandatory Stop-Loss Verification:** Verifies the protective stop exists on the exchange. If missing, places an emergency reduce-only stop. If stop placement fails, immediately executes an emergency market close.
* **Output:** Verified open position or emergency abort record.

### 8️⃣ Agent 8: Micro-Trailing Sentinel
* **Module:** [`src/trailing_stop_manager.py`](src/trailing_stop_manager.py)
* **Core Task:** Monitors active positions every 15 seconds to trail stop losses and lock in green profits.
* **Inputs:** Live mark prices, trade state, and volatility posture.
* **Processing Logic:**
  * **Stage 1 (Breathing Cushion):** At $+0.80\text{R}$ to $+0.90\text{R}$, slashes risk by 60% (moves SL to $-0.40\text{R}$), giving natural retests room without premature stops.
  * **Stage 2 (Guaranteed Green Lock):** At $+1.10\text{R}$ to $+1.20\text{R}$, locks $+0.30\text{R}$ in profit, preventing breakeven exits ($0.00).
  * **Stage 3 (Core Expansion):** At $+1.50\text{R}$ to $+1.60\text{R}$, locks $+0.85\text{R}$ profit ($8-15\%$ margin return).
  * **Stage 4 (Trailing Runner):** Trails behind 15m structural swing points toward the final target.
* **Output:** Dynamic stop adjustments, fill alerts, and closure notifications.

### 9️⃣ Agent 9: Adaptive Learning Engine
* **Module:** [`multiagent_team/adaptive_learning.py`](multiagent_team/adaptive_learning.py)
* **Core Task:** Performs evidence-based postmortems on completed trades to reinforce winning setups and penalize losers.
* **Inputs:** Closed trade records, realized PnL, R-multiple captured, MFE, and MAE.
* **Processing Logic:**
  * Scores trade execution ($0-100$).
  * Normalizes pattern keys (`ASSET_STRATEGY_DIRECTION_TREND`).
  * Adjusts pattern scores: reinforces verified patterns ($+8\text{ pts}$) and penalizes failing patterns ($-15\text{ pts}$ or blacklists).
  * Persists learning state into [`state/pattern_learning_memory.json`](state/pattern_learning_memory.json).
* **Output:** Strategy score modifiers and pattern vetoes.

### 🔟 Agent 10: Performance Coach & Operating Rules
* **Module:** [`multiagent_team/performance_coach.py`](multiagent_team/performance_coach.py)
* **Core Task:** Monitors macro performance cohorts and maintains version-controlled operating rules.
* **Inputs:** Historical journal metrics, rolling win rates, and strategy drawdowns.
* **Processing Logic:**
  * Analyzes performance variance across asset cohorts, trading sessions, and strategies.
  * Maintains institutional operating rules in [`state/active_operating_rules.json`](state/active_operating_rules.json).
  * Enforces automated rollbacks if rolling win rates degrade over a 20-trade evaluation window.
* **Output:** Dynamic operating rules and performance reports.

---

## 🔒 Deterministic Safety Controller (14 Invariants)

Positioned immediately before Agent 7, [`multiagent_team/deterministic_safety_controller.py`](multiagent_team/deterministic_safety_controller.py) validates 14 pure-code safety criteria:

| # | Safety Check | Verification Criterion | Failure Action |
|---|--------------|------------------------|----------------|
| **1** | Circuit Breaker | System state must be `TRADING_ALLOWED` (not `HALTED`, `EMERGENCY`, or `COOLDOWN`) | Execution Aborted |
| **2** | Net Equity Floor | Account net equity must be $\ge \$10.00$ | Execution Aborted |
| **3** | Portfolio Concurrency | Total open positions must be $< \text{max\_portfolio\_concurrency}$ (default: 2) | Execution Aborted |
| **4** | Dollar Risk Cap | Risk must be $\le \min(\text{Equity} \times \text{max\_risk\_pct}, \$4.00)$ | Execution Aborted |
| **5** | Leverage Ceiling | Leverage must be $\le \text{max\_allowed\_leverage}$ | Execution Aborted |
| **6** | Stop Orientation | $\text{SL} < \text{Entry}$ for Longs; $\text{SL} > \text{Entry}$ for Shorts; $\text{SL} > 0$ | Execution Aborted |
| **7** | Reward-to-Risk | Planned R:R ratio must be $\ge 2.20:1$ | Execution Aborted |
| **8** | Liquidation Buffer | Liquidation distance must be $\ge 3.0\times$ stop loss distance | Execution Aborted |
| **9** | Whitelist Check | Symbol must exist in approved instruments list | Execution Aborted |
| **10** | Spread Threshold | Orderbook bid/ask spread must be $\le 0.20\%$ | Execution Aborted |
| **11** | Feed Freshness | Candlestick and mark price timestamp must be $\le 60\text{ seconds}$ old | Execution Aborted |
| **12** | Correlation Limit | Same-side crypto positions must be $\le \text{max\_correlated\_positions}$ (2) | Execution Aborted |
| **13** | Idempotency Check | `client_order_id` must not exist in state records | Execution Aborted |
| **14** | Human Authorization | Telegram signature must be valid and non-expired | Execution Aborted |

> **Token Issuance:** When all 14 criteria pass, the controller generates an HMAC-SHA256 signature containing the trade parameters and a **30-second time-to-live (TTL)**. Orders lacking a valid token are rejected by the execution engine.

---

## 🛡️ Persistent Multi-Horizon Circuit Breaker

The circuit breaker in [`src/risk_manager.py`](src/risk_manager.py) enforces persistent risk limits across multiple horizons:

* **Daily Drawdown Limit:** $3.0\%$ max daily loss $\rightarrow$ `HALTED`
* **Weekly Drawdown Limit:** $5.0\%$ max weekly loss $\rightarrow$ `HALTED`
* **Monthly Drawdown Limit:** $8.0\%$ max monthly loss $\rightarrow$ `EMERGENCY`
* **Consecutive Loss Limit:** 3 consecutive stop losses $\rightarrow$ `COOLDOWN` (30 minutes)
* **Fail-Closed State Loader:** If state files are missing or unreadable, the system defaults to `HALTED`.
* **Administrative Reset Only:** The system does not resume automatically upon day rollover. Resuming requires an explicit call to `manual_reset(authorized_by, reason, current_equity)`.

---

## 🗄️ Dual-Store Authoritative Event Journal

The journaling engine in [`src/journal.py`](src/journal.py) logs granular events to both SQLite and JSON:

1. **SQLite Event Store ([`state/trading_journal.db`](state/trading_journal.db)):** Tracks granular lifecycle records (`SETUP_IDENTIFIED`, `RISK_EVALUATED`, `USER_PROMPTED`, `USER_DECISION_RECEIVED`, `ORDER_PLACED`, `ORDER_FILLED`, `PROTECTIVE_ORDER_PLACED`, `TRAILING_STOP_MODIFIED`, `EXIT_ORDER_FILLED`, `TRADE_CLOSED`, `POSTMORTEM_COMPLETED`).
2. **JSON Summary Store ([`state/trade_journal.json`](state/trade_journal.json)):** Maintains backward-compatible records for quick querying and Telegram status reporting.

---

## 🚀 Quickstart & Setup

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/mohitxhkr/Multi_agent_trading_bot.git
cd Multi_agent_trading_bot
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
```bash
# Delta Exchange API Credentials
DELTA_ENVIRONMENT=india
DELTA_API_KEY=your_delta_api_key_here
DELTA_API_SECRET=your_delta_api_secret_here

# Telegram Two-Way Gate Credentials
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
AUTHORIZED_TELEGRAM_USERS=your_telegram_chat_id_here

# Risk Limits
MAX_RISK_PER_TRADE_PCT=0.01          # 1% equity risk per trade
MAX_DOLLAR_RISK_PER_TRADE=4.00        # $4.00 hard cap
MAX_DAILY_DRAWDOWN_PCT=0.03          # 3% daily limit
MAX_WEEKLY_DRAWDOWN_PCT=0.05         # 5% weekly limit
MAX_MONTHLY_DRAWDOWN_PCT=0.08        # 8% monthly limit
MAX_CONSECUTIVE_LOSSES=3             # Cooldown after 3 losses
COOLDOWN_SECONDS=1800                # 30-minute cooldown
MAX_CONCURRENT_POSITIONS=2           # Max 2 simultaneous trades
MAX_ALLOWED_LEVERAGE=50              # Leverage ceiling
MIN_REWARD_TO_RISK=2.2               # Minimum 2.2:1 R:R
```

### 3. Run Test Suite
```bash
python -m unittest discover tests
```
*Expected Output: `Ran 16 tests in 0.685s - OK (100% Passing)`*

### 4. Start the Trading Bot
* **Single Scan & Execution Cycle:**
  ```bash
  python main.py --once
  ```
* **Autonomous Continuous Execution (24/7):**
  ```bash
  python main.py
  ```

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
