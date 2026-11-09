# 🟢 Beginner's Manual: How This Trading Bot Works & How to Use It

Welcome! If you are new to automated trading, crypto, or AI bots, **this guide is written specifically for you**. 

You do **not** need to be a programmer or a professional Wall Street trader to use this system. Follow this simple guide step-by-step.

---

## 📑 Table of Contents
1. [What Is This Bot in Simple Words?](#1-what-is-this-bot-in-simple-words)
2. [How the 5 AI Agents Protect Your Money](#2-how-the-5-ai-agents-protect-your-money)
3. [Quick Start: How to Run It in 3 Easy Steps](#3-quick-start-how-to-use-it-in-3-easy-steps)
4. [The 3 Ways to Use the Bot](#4-the-3-ways-to-use-the-bot)
5. [How to Talk to the Bot in Chat](#5-how-to-talk-to-the-bot-in-chat)
6. [What Happened in Our Real Demo Trade?](#6-what-happened-in-our-real-demo-trade)
7. [The "Panic Button" (Emergency Stop)](#7-the-panic-button-emergency-stop)
8. [The 4 Golden Rules for Beginners](#8-the-4-golden-rules-for-beginners)

---

## 1. What Is This Bot in Simple Words?

Normally, when people trade crypto, they sit in front of charts, get excited, buy at the top, panic when the price drops, and lose money.

**This bot eliminates human emotions.**

It is an automated trading system connected to **Delta Exchange** (India, Global, or Testnet paper trading). Instead of placing risky bets, it has **5 specialized AI helpers** that work together to:
1. Scan Bitcoin, Ethereum, Solana, and XRP prices.
2. Find only safe, high-reward opportunities.
3. Check your account balance so you **never risk more than 1%** on any trade.
4. Automatically attach an **emergency exit (Stop-Loss)** and a **cash-out target (Take-Profit)** the moment a trade is placed.
5. Move your safety exit to your purchase price once the trade is winning, making it a **risk-free trade (Free-Roll)**.

---

## 2. How the 5 AI Agents Protect Your Money

Think of the bot as a **5-person trading team** working for you 24/7:

```
[Delta Market Data]
        │
        ▼
1. 🔍 THE SCOUT (Regime Analyst)      ──> "Is the market trending up, down, or messy?"
        │
        ▼
2. 💡 THE PLANNER (Strategy Agent)    ──> "Here is a trade idea where we make $2 for every $1 risked."
        │
        ▼
3. 🛡️ THE RISK BOSS (Gatekeeper)      ──> "CHECK: Max risk is 1%. No big losses allowed. APPROVED!"
        │
        ▼
4. 🚀 THE PILOT (Execution Agent)     ──> "Submitting order with built-in Stop-Loss and Take-Profit."
        │
        ▼
5. 📊 THE ACCOUNTANT (Portfolio Monitor) ──> "Trade is in profit! Moving stop to breakeven (Zero Risk)."
```

### The Most Important Agent: Agent 3 (The Risk Boss)
The Risk Boss has **unilateral veto power**. Even if a trade looks exciting, if it risks too much of your money or if your account lost 5% today, the Risk Boss slams the brakes and says **"REJECTED. Capital Protected."**

---

## 3. Quick Start: How to Use It in 3 Easy Steps

Open **PowerShell** or your terminal in this folder (`d:\Project\Claude Code`):

### Step 1: Check your connection and balance
Run this command to make sure your API keys work:
```powershell
python test_delta_connection.py
```
**What you will see:**
It will show `[SUCCESS] Authenticated successfully with Delta Exchange!` and print your current wallet balance.

---

### Step 2: Let the bot scan the market
Run this command to see what the bot thinks of current prices:
```powershell
python main.py scan
```
**What you will see:**
- The Scout will report whether Bitcoin, Ethereum, Solana, or XRP are Bullish or Bearish.
- The Planner will list any prospective setups.
- The Risk Boss will calculate the exact contract size for your wallet.

---

### Step 3: Run Interactive Mode (Recommended for Beginners!)
In Interactive Mode, the bot does all the research, but **it will ask for your permission** before placing any order:
```powershell
python main.py interactive
```
**What happens:**
When a qualified setup is found, it will print:
```text
🚀 [Agent 4: Execution Agent] Ready to execute:
   Contract: BTCUSDT | Side: BUY | Contracts: 1
   Entry: $80,957.50 | Stop Loss: $79,355.40 | Take Profit: $81,760.10
   Max Risk: $0.80 | Reward/Risk: 2.00:1

❓ Confirm order execution on Delta Exchange? [y/N]:
```
- If you type **`y`** (Yes) ➔ The bot places the trade with attached Stop-Loss and Take-Profit.
- If you type **`n`** (No) or press Enter ➔ The bot skips it. No money is touched!

---

## 4. The 3 Ways to Use the Bot

| Mode | Command | How It Works | Best For |
|---|---|---|---|
| **1. Interactive Mode** | `python main.py interactive` | Finds setups, sizes them, and asks you `[y/N]` before doing anything. | **Beginners & Daily use** |
| **2. Continuous Auto-Pilot** | `python main.py auto` | Scans automatically every 5 minutes in the background and places approved trades. | **Hands-off trading** |
| **3. Chatting with AI** | *Just ask in chat!* | You can chat in plain English with Claude or Antigravity IDE. | **Conversational trading** |

---

## 5. How to Talk to the Bot in Chat

Because the bot is integrated via **Model Context Protocol (MCP)**, you don't even have to use terminal commands if you don't want to. You can simply ask questions in plain English:

- *"Check my Delta Exchange wallet balances and open positions."*
- *"Scan Bitcoin and Ethereum and tell me if the market is bullish."*
- *"What is my daily drawdown and circuit breaker status?"*
- *"Find a 1% risk trade setup for BTCUSDT with a 2:1 profit target."*
- *"Move my stop-loss to breakeven on my open Bitcoin trade."*

---

## 6. What Happened in Our Real Demo Trade?

Here is what we actually executed on your demo account today:

1. **Your Balance**: You had **$204.83 USD** of demo funds on Delta Testnet.
2. **The Analysis**: The Scout saw Bitcoin trending up strongly at **$81,061** with positive momentum.
3. **The Risk Check**: The Risk Boss calculated that a 1% risk limit was **$2.04**. It sized the trade to 1 contract of Bitcoin, risking just **$0.80**.
4. **The Execution**: The Pilot placed the order at **$80,957.50**. At the exact same second, it set:
   - **Take-Profit Target**: at **$81,760.10** (to lock in profit).
   - **Emergency Stop-Loss**: at **$79,355.40** (to cut loss if wrong).
5. **The Upgrade (Free-Roll)**: When Bitcoin climbed into profit, we adjusted the Stop-Loss to your entry price (**$80,957.50**). 
   - Now, if Bitcoin crashes, you exit at entry for **$0.00 loss**. 
   - If it continues up, you hit your target for **pure profit**!

---

## 7. The "Panic Button" (Emergency Stop)

If major news breaks or you just want to completely close everything immediately:

### Option A: In Chat
Simply type:
> *"Close all my positions and cancel all open orders immediately."*

### Option B: In Terminal
Copy and paste this one command:
```powershell
python -c "from src.delta_client import DeltaExchangeClient; c = DeltaExchangeClient(); c.cancel_all_orders(); c.close_position('BTCUSDT')"
```
This instantly cancels every resting order and sells all active positions at market price.

---

## 8. The 4 Golden Rules for Beginners

1. **Always Start on Testnet (Demo)**
   - Keep `DELTA_ENVIRONMENT=testnet_india` in your `.env` until you have watched the bot trade for at least a week and feel 100% confident.
2. **Never Enable "Withdrawal" on API Keys**
   - When generating API keys on Delta Exchange, only check **Read** and **Trade**. Never check Withdraw. This ensures your funds can never leave your exchange account.
3. **Never Risk More Than 1% per Trade**
   - Keep `MAX_RISK_PER_TRADE_PCT=0.01` in `.env`. Even if you have 5 bad trades in a row, you still keep 95% of your money.
4. **Never Remove the Stop-Loss**
   - The bot attaches a stop-loss automatically. Never manually cancel it on the exchange without replacing it, because the stop-loss is your safety airbag.

---

### Need More Details?
- 📄 Read the [Beginner's PDF Guide](Delta_Trading_Beginners_Guide.pdf) *(with illustrations and analogies)*
- 📘 Read the [Complete Technical Specification](Delta_Exchange_Comprehensive_MultiAgent_Architecture.pdf)
- 🛠️ Read the [Setup Runbook](SETUP_GUIDE.md)

