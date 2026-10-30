# Delta Exchange Risk Rules & Sizing Methodology

Inspired by `claude-trading-skills` risk principles (`drawdown-circuit-breaker`, `position-sizer`, and `pre-trade-discipline-gate`).

## Core Invariants

1. **Never Trade Without a Stop Loss**: Every order placed on Delta Exchange must have an explicit stop price defined before submission.
2. **Fixed Fractional Risk (Default 1%)**: Maximum dollar loss on any single trade cannot exceed 1% (or user-defined `MAX_RISK_PER_TRADE_PCT`) of total account equity.
3. **Minimum 2:1 Reward-to-Risk (R:R)**: Profit target distance must be at least twice the stop distance.
4. **Daily Drawdown Circuit Breaker (Default 5%)**: If equity falls by 5% from the daily start, all new trade openings are halted.
5. **Position Concurrency Limit (Default 3)**: Maximum of 3 open margined positions at any one time.
6. **Leverage Ceiling (Default 10x)**: Maximum leverage allowed by the system is clamped to 10x (or `MAX_ALLOWED_LEVERAGE`) to avoid liquidation cascades.

## Contract Sizing Formula

Delta Exchange uses contract units with specified `contract_value` multipliers (e.g., 1 contract of `BTCUSDT` = `0.001 BTC`):

$$\text{Dollar Risk} = \text{Account Equity} \times \text{Risk \%}$$

$$\text{Stop Distance} = |\text{Entry Price} - \text{Stop Loss Price}|$$

$$\text{Risk Per Contract} = \text{Stop Distance} \times \text{Contract Value}$$

$$\text{Contracts} = \text{floor}\left(\frac{\text{Dollar Risk}}{\text{Risk Per Contract}}\right)$$

$$\text{Required Margin} = \frac{\text{Contracts} \times \text{Contract Value} \times \text{Entry Price}}{\text{Leverage}}$$

If $\text{Required Margin} > \text{Available Collateral} \times 0.95$, the trade is **REJECTED** by the Risk Gatekeeper.
