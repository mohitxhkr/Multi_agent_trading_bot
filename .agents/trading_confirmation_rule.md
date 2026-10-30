# Trading Confirmation & Sizing Rules

## USER SIZING & LEVERAGE DIRECTIVES (MANDATORY)
1. **Capital Allocation**: Always use **75% to 100% of available account capital** for position margin sizing.
2. **Leverage by Asset Class**:
   - **BTC (BTCUSD, BTCUSDT)**: **50x leverage**
   - **All Other Assets (ETH, SOL, PAXG/XAU, etc.)**: **25x leverage**
3. **Position Sizing Formula**:
   - `Allocated Margin = Available Balance * (0.75 to 1.00)`
   - `Max Notional = Allocated Margin * Leverage`
   - `Contracts = floor(Max Notional / (Entry Price * Contract Value))`
   - Ensure `Required Margin <= Available Collateral`

## MANDATORY WORKFLOW — Never Skip Steps

When a user asks to "place a trade", "take a trade", or anything involving order execution,
you MUST follow this exact sequence — no exceptions:

### Step 1: GATHER DATA (silent)
- Fetch live wallet balance
- Fetch live mark price + ticker
- Fetch 1H candles (last 100 bars)
- Run full technical analysis (EMA, RSI, MACD, ATR, support/resistance)

### Step 2: SHOW ANALYSIS & EXACT SIZING (always — before any order)
Present a clear summary card showing:
- Current price
- Regime & indicators
- Proposed direction (LONG or SHORT) with technical reasoning
- Entry, Take Profit, and Stop Loss levels with % distances and >= 2.0x R:R
- **Exact Sizing**: 75%-100% capital used, Leverage applied (50x for BTC, 25x for others), exact contracts count, and required margin.

### Step 3: ASK FOR CONFIRMATION
End with an explicit question asking for confirmation before order placement.

### Step 4: EXECUTE ONLY AFTER USER CONFIRMS
- Only place the order AFTER the user explicitly confirms (e.g., YES, execute, go ahead).


