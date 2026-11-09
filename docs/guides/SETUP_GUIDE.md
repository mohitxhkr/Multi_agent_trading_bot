# Complete Setup & Connection Guide: Delta Exchange MCP & Multi-Agent Trading Team

This guide walks you step-by-step through setting up your **Delta Exchange** account, generating secure API keys, configuring the **Model Context Protocol (MCP)** server, and running the **Multi-Agent Trading Team** (inspired by `claude-trading-skills`).

---

## Table of Contents
1. [Overview & Architecture](#1-overview--architecture)
2. [Delta Exchange Account Setup](#2-delta-exchange-account-setup)
3. [Creating API Credentials](#3-creating-api-credentials)
4. [Local Project Installation & Configuration](#4-local-project-installation--configuration)
5. [Connecting to Claude Desktop](#5-connecting-to-claude-desktop)
6. [Connecting to Claude Code & Antigravity IDE](#6-connecting-to-claude-code--antigravity-ide)
7. [Running the Multi-Agent Trading Team](#7-running-the-multi-agent-trading-team)
8. [Testing Safely on Delta Testnet First](#8-testing-safely-on-delta-testnet-first)
9. [Troubleshooting & FAQs](#9-troubleshooting--faqs)

---

## 1. Overview & Architecture

This system combines two powerful layers:
1. **Delta Exchange MCP Server (`run_mcp.py` / `src/delta_mcp_server.py`)**:
   Exposes 19 high-level tools to Claude and Antigravity, including live wallet balances, positions, orderbook, candlestick analytics (EMA 9/21/50/200, RSI, ATR, MACD), risk circuit breakers, disciplined position sizing, and protective bracket orders (entry + Stop-Loss + Take-Profit).
2. **Multi-Agent Trading Team (`multiagent_team/`)**:
   - **Agent 1: Market Regime & Technical Analyst**: Evaluates trend structure, RSI momentum, ATR volatility, and support/resistance levels.
   - **Agent 2: Strategy & Alpha Generator**: Discovers trade setups (momentum continuation, support bounce) with strict 2:1 Reward-to-Risk criteria.
   - **Agent 3: Risk & Discipline Gatekeeper**: Enforces non-negotiable risk rules (maximum 1% account risk per trade, daily drawdown circuit breaker, position sizing).
   - **Agent 4: Execution & Order Manager**: Submits signed bracket orders to Delta Exchange with protective stops.
   - **Agent 5: Portfolio Monitor & Memory Journaler**: Tracks live positions, trailing stops, logs trades into `state/trade_journal.json`, and generates daily reports.

---

## 2. Delta Exchange Account Setup

Delta Exchange operates in two primary jurisdictions:
- **Delta Exchange India** (Compliant with FIU-IND regulations for Indian residents): [https://india.delta.exchange](https://india.delta.exchange)
- **Delta Exchange Global** (International traders): [https://www.delta.exchange](https://www.delta.exchange)
- **Delta Exchange Testnet** (Risk-free testing with paper money): [https://testnet.delta.exchange](https://testnet.delta.exchange) or [https://cdn-ind.testnet.deltaex.org](https://cdn-ind.testnet.deltaex.org)

### Steps:
1. Register your account using your email and password.
2. Complete KYC identity verification if required by your jurisdiction.
3. Deposit trading collateral (USDT, BTC, or INR for Delta India).

---

## 3. Creating API Credentials

To allow Claude and your multi-agent team to interact with your account, create an API Key.

### Crucial Security Best Practice
> ⚠️ **CRITICAL SECURITY RULE:** Never enable "Withdrawal" permissions on any trading API key. 
> Only enable **Read** and **Trade**. If withdrawal is disabled, funds can NEVER leave your exchange account even if credentials are leaked.

### Step-by-Step API Key Generation:
1. Log in to your Delta Exchange dashboard.
2. Click your Profile icon in the top right corner and navigate to **Settings** > **API Keys** (or go directly to `/app/settings/api-keys`).
3. Click **Create New API Key**.
4. Configure key settings:
   - **Name / Label**: e.g., `Claude-Delta-MCP`
   - **Permissions**:
     - ✅ **Read** (View balances, positions, open orders)
     - ✅ **Trade** (Place orders, cancel orders, set leverage)
     - ❌ **Withdraw** (**Leave UNCHECKED / DISABLED**)
   - **IP Whitelist** (Optional but recommended): If your machine has a static IP, enter it here for maximum security.
5. Click **Create Key**. Enter your 2FA authentication code.
6. **Immediately copy both:**
   - **API Key**
   - **API Secret** (Note: Delta only displays the API Secret once!)

---

## 4. Local Project Installation & Configuration

### Prerequisites
- Python 3.10, 3.11, or 3.12 installed on your system.

### Step 1: Install Python Dependencies
Open PowerShell or your terminal in the project directory (`d:\Project\Claude Code`):

```powershell
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:

```powershell
cp .env.example .env
```

Open `.env` in your text editor and fill in your details:

```env
# Choose environment: "india", "global", or "testnet"
DELTA_ENVIRONMENT=india

# Paste your API credentials
DELTA_API_KEY=your_actual_api_key_here
DELTA_API_SECRET=your_actual_api_secret_here

# Risk Parameters
MAX_RISK_PER_TRADE_PCT=0.01       # 1% max account risk per trade
MAX_CONCURRENT_POSITIONS=3         # Max 3 open positions at once
MAX_DAILY_DRAWDOWN_PCT=0.05        # 5% daily drawdown circuit breaker
MAX_ALLOWED_LEVERAGE=10            # Max 10x leverage ceiling
MIN_REWARD_TO_RISK_RATIO=2.0       # Minimum 2:1 R:R

# Symbols to monitor
DEFAULT_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT
```

### Step 3: Verify Connection
Test your setup using the built-in diagnostic tool:

```powershell
python main.py test
```

Expected output when properly configured:
```
Connection Results:
--------------------------------------------------
  Target Environment : india
  Base URL           : https://api.india.delta.exchange
  Public API Status  : [CONNECTED]
  Authenticated Status: [SUCCESS]
  Details            : Authenticated successfully with Delta Exchange.

  Live Account Balances:
   • USDT: Balance = 500.00 (Available: 500.00)
--------------------------------------------------
```

---

## 5. Connecting to Claude Desktop

You can connect this MCP server directly to the official **Claude Desktop** application to let Claude execute trades and monitor positions interactively in chat.

### Step 1: Open Claude Desktop Configuration
On Windows, navigate to:
`%APPDATA%\Claude\claude_desktop_config.json`
*(e.g., `C:\Users\<YourUsername>\AppData\Roaming\Claude\claude_desktop_config.json`)*

On macOS:
`~/Library/Application Support/Claude/claude_desktop_config.json`

### Step 2: Add the Delta Exchange MCP Configuration
Add the `delta-exchange` MCP server entry:

```json
{
  "mcpServers": {
    "delta-exchange": {
      "command": "python",
      "args": [
        "d:/Project/Claude Code/run_mcp.py"
      ],
      "env": {
        "DELTA_ENVIRONMENT": "india",
        "DELTA_API_KEY": "your_actual_api_key_here",
        "DELTA_API_SECRET": "your_actual_api_secret_here",
        "MAX_RISK_PER_TRADE_PCT": "0.01",
        "MAX_DAILY_DRAWDOWN_PCT": "0.05",
        "MAX_ALLOWED_LEVERAGE": "10",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### Step 3: Restart Claude Desktop
Completely quit and restart Claude Desktop. When you start a new conversation, click the **Hammer / Tools** icon at the bottom of the prompt window. You will see all `delta_*` tools loaded!

You can now ask Claude:
- *"Check my Delta Exchange wallet balances and circuit breaker status."*
- *"Analyze the 1-hour chart of BTCUSDT on Delta and tell me the market regime."*
- *"Size a 1% risk long position for BTCUSDT with entry at current price and stop loss below EMA 21."*
- *"Place a bracket order for BTCUSDT with 2:1 reward-to-risk ratio."*

---

## 6. Connecting to Claude Code & Antigravity IDE

### For Claude Code CLI
Add the MCP server to Claude Code using the CLI command:

```bash
claude mcp add delta-exchange "python d:/Project/Claude Code/run_mcp.py"
```

Or configure `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "delta-exchange": {
      "command": "python",
      "args": ["d:/Project/Claude Code/run_mcp.py"]
    }
  }
}
```

### For Antigravity IDE
In Antigravity IDE, customizations are managed via customization roots. Add the server to your `mcp_config.json` in `.gemini/config/mcp_config.json` or `.agents/mcp_config.json`:

```json
{
  "mcpServers": {
    "delta-exchange": {
      "command": "python",
      "args": ["d:/Project/Claude Code/run_mcp.py"]
    }
  }
}
```

---

## 7. Running the Multi-Agent Trading Team

The multi-agent system can also be executed autonomously or semi-autonomously via the command line.

### A. One-Time Market Scan
Scans your watched symbols, computes indicator stacks, and evaluates candidate trade setups:

```powershell
python main.py scan --symbols BTCUSDT,ETHUSDT,SOLUSDT
```

### B. Interactive Trading Mode (Recommended for Live Trading)
Runs the full multi-agent pipeline. If Agent 1, 2, and 3 approve a trade, it presents the complete trade plan and prompts you for confirmation `[y/N]` before submitting:

```powershell
python main.py trade --symbols BTCUSDT,ETHUSDT --leverage 5
```

### C. Autonomous Continuous Loop
Runs every `interval` seconds (default 300s = 5 minutes). Evaluates market structure, checks the circuit breaker gate, and automatically executes setups that pass all 5 agent gates:

```powershell
python main.py auto --interval 300 --leverage 5
```

### D. View Performance Digest & Journal
Displays active positions, total unrealized PnL, win rate %, and past trade records:

```powershell
python main.py digest
```

---

## 8. Testing Safely on Delta Testnet First

Before trading with real capital, test everything on the Delta Exchange Testnet:

1. Create a free account on [https://testnet.delta.exchange](https://testnet.delta.exchange).
2. Generate an API Key on the testnet.
3. In your `.env` file, set:
   ```env
   DELTA_ENVIRONMENT=testnet
   DELTA_API_KEY=your_testnet_api_key
   DELTA_API_SECRET=your_testnet_api_secret
   ```
4. Fund your testnet wallet using the free testnet faucet button in the UI.
5. Run `python main.py test` to verify testnet connectivity.
6. Run `python main.py trade --symbols BTCUSDT` to simulate paper order execution.

---

## 9. Troubleshooting & FAQs

### Q1: `401 Unauthorized` / `Invalid Signature` error
- **Cause**: Delta Exchange requires timestamps to match server time within 5 seconds.
- **Solution**: Check that your computer clock is synchronized via NTP (Windows Settings > Time & Language > Date & Time > "Sync now"). Ensure no trailing spaces exist in your API key or secret in `.env`.

### Q2: Order rejected with `open_order_not_found` when updating bracket
- **Cause**: If an entry order fills immediately at market, the parent order is closed and Delta spawns separate stop orders on the book.
- **Solution**: The MCP server handles this by using atomic bracket submission (`delta_place_bracket_order`) so that Stop Loss and Take Profit legs are registered upon entry.

### Q3: `HALT_CIRCUIT_BREAKER` triggered
- **Cause**: Daily account loss exceeded the `MAX_DAILY_DRAWDOWN_PCT` (default 5%).
- **Solution**: This is a core safety feature from `claude-trading-skills` to prevent revenge trading. Trading is safely halted until the next calendar day, or until you inspect and reset `state/circuit_breaker_state.json`.

### Q4: Unicode / Emoji error on Windows PowerShell
- **Solution**: The project has native UTF-8 reconfigure built-in. If your console uses legacy codepages, run `chcp 65001` in your terminal prior to running commands.
