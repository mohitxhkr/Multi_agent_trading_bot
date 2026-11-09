# AGENT 5 – TIME MACHINE ENGINE DOCUMENTATION
## Delta Exchange Multi-Agent Quantitative Trading System
**Target Module:** `multiagent_team/time_machine_agent.py`  
**Role:** Quantitative Historical Replay, Statistical Probability Engine, & Parameter Backtesting Sentinel  

---

## 1. Architectural Overview

Agent 5 (Time Machine Engine) acts as the empirical validation gate in the 11-agent pipeline. It simulates trade setups across historical market data using the exact rules of Agent 4 (Strategy Agent) before capital is committed.

```
                          ┌────────────────────────┐
                          │  Strategy Agent Setup  │
                          └───────────┬────────────┘
                                      │
                                      ▼
                      ┌────────────────────────────────┐
                      │    Time Machine Simulation     │
                      │  - Replay Exact SMC Logic      │
                      │  - Intrabar 1M Resolution      │
                      │  - Friction & Funding Rate     │
                      │  - Wilson 95% CI Lower Bound   │
                      │  - Multi-Window Walk-Forward   │
                      └───────────────┬────────────────┘
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
         [APPROVED]                                [VETOED / REJECTED]
(WR >= 65%, EV >= +0.30R,                   (Sample < 8, WR < 65%,
 PF >= 1.50, OOS EV >= 0)                    EV < +0.30R, Overfitting)
```

---

## 2. Core Methodologies & Mathematical Models

### 2.1 Exact Strategy Replay Logic
The `_matches_historical_strategy` method mirrors Agent 4's Smart Money Concepts (SMC):
- **Fractal Pivots & Market Structure Shifts:** Computes Break of Structure (BOS) and Change of Character (CHOCH).
- **Fair Value Gaps (FVG):** Tracks mitigation down to 50% Consequent Encroachment (CE).
- **Liquidity Sweeps:** Verifies Buy-Side (BSL) and Sell-Side (SSL) sweeps with MSS candle body confirmation.
- **Confluence Scoring:** Confirms 1H directional alignment and 15M/5M momentum filters.

### 2.2 Intrabar Event Sequencing & Ambiguity Resolution
- **1M Intrabar Traversal:** When `candles_1m` is provided, bars within each 15m candle are traversed chronologically to establish whether take profit, stop loss, or breakeven threshold was touched first.
- **Conservative Same-Bar Resolution:** If 1M data is absent and both SL and TP are touched within the same candle:
  - Resolves conservatively to **Stop-Loss hit first** (`outcome = LOSS`).
  - Sets `ambiguity = True` and increments `ambiguous_cases`.
  - Records limitation in the simulation audit metadata.

### 2.3 Institutional Friction & Net R Calculation
Institutional friction accounts for Delta Exchange fee schedules:
- Entry Taker Fee: 0.05% (`0.0005`)
- Exit Taker Fee: 0.05% (`0.0005`)
- Slippage: 0.03% for BTC, 0.05% for altcoins
- Funding Drag: 0.01% per 8-hour funding cycle

$$\text{Initial Dollar Risk} = |\text{sim\_entry} - \text{initial\_sl}|$$
$$\text{Net PnL USD} = \text{Gross Dollar PnL} - (\text{sim\_entry} \times \text{total\_trade\_friction})$$
$$\text{Net } R = \frac{\text{Net PnL USD}}{\text{Initial Dollar Risk USD}}$$

### 2.4 Multi-Window Rolling Walk-Forward
- Partitions candle history into 3 chronological windows.
- Each window enforces: **Train (65%) -> Embargo Buffer -> Out-of-Sample (35%)**.
- Eliminates overlapping trade leakage and prevents forward-looking bias.

### 2.5 Candidate Parameter Backtesting API
The `evaluate_candidate_parameters(...)` API allows Agent 10 (Adaptive Learning) to simulate candidate parameter configurations (e.g., target RR, ATR multipliers, holding duration) against historical candle series.

---

## 3. Public Interface Specification

```python
def simulate_setup(
    self,
    setup: Dict[str, Any],
    candles_15m: Optional[Dict[str, Any]] = None,
    candles_1h: Optional[Dict[str, Any]] = None,
    candles_5m: Optional[Dict[str, Any]] = None,
    candles_1m: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]

def evaluate_candidate_parameters(
    self,
    candidate_params: Dict[str, Any],
    candles_15m: Dict[str, Any],
    candles_1h: Optional[Dict[str, Any]] = None,
    candles_5m: Optional[Dict[str, Any]] = None,
    candles_1m: Optional[Dict[str, Any]] = None,
    symbol: str = "BTCUSD",
    side: str = "buy",
    strategy_name: str = "Institutional_SSL_Sweep"
) -> Dict[str, Any]
```
