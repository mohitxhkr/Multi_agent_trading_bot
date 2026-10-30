---
name: delta-trading
description: Connects to Delta Exchange via MCP tools to analyze crypto market structure, compute technical indicators (EMA, RSI, ATR, MACD), calculate disciplined position sizes, enforce circuit breaker gates, execute bracket orders (with Stop-Loss and Take-Profit), monitor active positions, and maintain a persistent trade memory journal.
---

# Delta Exchange Trading Skill

## Purpose

The **delta-trading** skill equips Claude with full agentic capabilities to interact with Delta Exchange (India, Global, and Testnet) through the Model Context Protocol (MCP). It bridges technical analysis, automated risk management, and order execution while maintaining the strict discipline standards established by `claude-trading-skills`.

---

## Tool Reference

The skill interacts with the following Delta Exchange MCP tools:

| MCP Tool Name | Category | Description |
|---|---|---|
| `delta_test_connection` | Diagnostic | Verifies API key, secret, and server connectivity |
| `delta_get_account_summary` | Portfolio | Retrieves wallet balance (USDT/BTC), available margin, and equity |
| `delta_get_positions` | Portfolio | Fetches active futures/options positions, unrealized PnL, leverage |
| `delta_get_open_orders` | Orders | Lists all pending limit and stop orders on the orderbook |
| `delta_get_order_history` | Orders | Retrieves past filled and cancelled orders |
| `delta_get_ticker` | Market Data | Real-time mark price, 24h high/low, funding rate, turnover |
| `delta_get_orderbook` | Market Data | Top 10 bids/asks and bid-ask spread |
| `delta_get_candles_analysis` | Analytics | Candlestick analysis with EMA (9/21/50/200), RSI, ATR, MACD, and regime |
| `delta_get_options_chain` | Options | Option strikes, Greeks (Delta, Gamma, Vega, Theta), and Implied Volatility |
| `delta_check_circuit_breaker` | Risk Gate | Verifies daily drawdown, peak drawdown, and max concurrent positions |
| `delta_calculate_position_size` | Risk Gate | Sizes contracts based on dollar risk tolerance, stop distance, and R:R |
| `delta_set_leverage` | Execution | Adjusts position leverage safely within account ceiling |
| `delta_place_order` | Execution | Places limit, market, or trigger orders |
| `delta_place_bracket_order` | Execution | Places entry order with protective Stop-Loss and Take-Profit legs attached |
| `delta_cancel_order` | Execution | Cancels a specific open order by ID |
| `delta_cancel_all_orders` | Execution | Cancels all open orders |
| `delta_close_position` | Execution | Closes an active position at market price |
| `delta_journal_trade` | Memory | Records trade thesis, entry, stop loss, and targets into memory |
| `delta_get_journal_stats` | Memory | Reviews overall win rate %, realized PnL, and trade history |

---

## Multi-Agent Operational Workflow

When asked to analyze or trade Delta Exchange contracts, execute this disciplined sequence:

### Step 1: Account Health & Circuit Breaker Check
Before analyzing any charts or trade candidates:
1. Call `delta_get_account_summary` to verify available USDT collateral.
2. Call `delta_check_circuit_breaker`. If the circuit breaker returns `HALT` or `MAX_CONCURRENT_POSITIONS_REACHED`, stop immediately and report the protective halt reason.

### Step 2: Market Structure & Technical Regime Assessment
For the target symbol (e.g., `BTCUSDT`, `ETHUSDT`, `SOLUSDT`):
1. Call `delta_get_candles_analysis(symbol, resolution="60")`.
2. Inspect the EMA alignment:
   - **Bullish Stack:** Price > EMA 9 > EMA 21 > EMA 50
   - **Bearish Stack:** Price < EMA 9 < EMA 21 < EMA 50
3. Inspect RSI (14) and ATR (14) for momentum and volatility bounds.
4. Call `delta_get_orderbook(symbol)` to verify liquidity and bid-ask spread.

### Step 3: Trade Sizing & Discipline Gate
1. Calculate logical Stop Loss:
   - For Longs: Below EMA 21 or 1.5 * ATR below entry.
   - For Shorts: Above EMA 21 or 1.5 * ATR above entry.
2. Establish Profit Target (minimum 2.0x Reward-to-Risk ratio).
3. Call `delta_calculate_position_size(symbol, entry_price, stop_loss_price, take_profit_price, leverage)`.
4. Verify the gate decision is `APPROVED`.

### Step 4: Trade Execution (With Protective Brackets)
1. If the user requested confirmation (Interactive Mode), present the full Trade Proposal:
   - Entry Price, Stop Loss, Take Profit
   - Contract Quantity, Dollar Risk ($ and %), Required Margin
   - Reward-to-Risk ratio and Setup Thesis
2. Call `delta_place_bracket_order` to place the order with attached Stop Loss and Take Profit legs.
3. Call `delta_journal_trade` to record the trade in `state/trade_journal.json`.

### Step 5: Post-Trade Monitoring
1. Call `delta_get_positions` to confirm the fill status.
2. Call `delta_get_journal_stats` to verify updated statistics.
