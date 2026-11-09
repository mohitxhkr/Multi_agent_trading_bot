# AGENT 9: PORTFOLIO MONITOR & CAPITAL PROTECTION SENTINEL
## QUANTITATIVE ARCHITECTURE, POSITION SURVEILLANCE & RISK RECONCILIATION SPECIFICATION

**Author:** Quantitative Trading Infrastructure & Risk Engineering  
**System Component:** Agent 9 — Portfolio Monitor  
**Target Module:** `multiagent_team/portfolio_monitor.py`  
**Classification:** Layer 4 Execution & Portfolio Surveillance Infrastructure  
**Version:** 2.0.0-PROD  

---

## 1. Executive Summary & Capital Protection Mandate

Within the Delta Exchange 11-agent algorithmic trading architecture, **Agent 9 (Portfolio Monitor)** functions as the primary real-time capital protection and risk-monitoring sentinel. While other agents focus on edge detection (Agent 4), regime analysis (Agent 1), or pre-trade validation (Agent 6 & Agent 7), Agent 9 operates with a strict mandate:

> **Capital Protection Mandate:** Continuously monitor live positions, account exposure, margin utilization, liquidation proximity, and protective order health. Treat actual exchange state as the definitive source of truth, reconcile discrepancies immediately, detect naked or vulnerable exposure, and trigger emergency containment workflows when invariants are violated.

Correctness, fail-closed safety, and low-latency detection are prioritized over speculative features.

---

## 2. Exhaustive Audit of Legacy Implementation

A thorough audit of legacy `multiagent_team/portfolio_monitor.py` revealed twelve critical architectural and quantitative vulnerabilities:

| # | Vulnerability | Severity | Root Cause in Legacy Code | Quantitative / Capital Risk |
|---|---|:---:|---|---|
| **1** | **Inverted Liquidation Distance** | **CRITICAL** | Calculated distance from entry: `abs(entry - liq) / entry * 100.0`. | Ignored mark price movement; if mark price moves toward liquidation, distance remains static, concealing imminent margin calls. |
| **2** | **Zero Protective Stop-Loss Verification** | **CRITICAL** | Failed to verify whether active stop-loss orders exist on the exchange for open positions. | Left positions completely vulnerable to naked drawdowns if orders were cancelled or rejected. |
| **3** | **Omission of Margin & Wallet Surveillance** | **CRITICAL** | Never polled `/v2/wallet/balances`; margin utilization and available collateral were completely unmonitored. | Unable to detect account-level margin degradation or cascading liquidations. |
| **4** | **Naive Contract Multipliers** | **HIGH** | Assumed universal contract multiplier ($1.0$) for all instruments. | Inaccurate notional exposure for BTC ($0.001$), ETH ($0.01$), and inverse contracts. |
| **5** | **Lack of Exchange vs Local Reconciliation** | **HIGH** | Never reconciled live exchange positions against local SQLite database (`StateManager`). | Phantom positions, quantity divergences, and manual interventions were undetectable. |
| **6** | **Absence of Drawdown & Limit Tracking** | **HIGH** | No tracking of daily/weekly drawdowns or consecutive loss limits. | Circuit breakers could be bypassed if multi-position drawdowns accumulated rapidly. |
| **7** | **Zero Concentration / Correlation Tracking** | **HIGH** | No grouping of positions across correlated clusters (e.g. BTC, ETH, SOL simultaneously Long). | Portfolios were exposed to severe compound drawdowns during market-wide crashes. |
| **8** | **Partial Fill Vulnerability** | **MEDIUM** | Never verified if stop order size matched actual position size after partial fills. | Positions could be only partially covered by stop-loss orders. |
| **9** | **Spam Alert Loops (No Deduplication)** | **MEDIUM** | Polling loops lacked alert caching or cooldown suppression. | Telegram and log spam during unresolved warnings. |
| **10** | **Fragile String-Based Date Parsing** | **MEDIUM** | Used naive `.replace("Z", "+00:00")` inside cancellation loops without fallback. | Unhandled exceptions during stale order scanning. |
| **11** | **Unstandardized Return Schema** | **MEDIUM** | Returned only `active_count` and `total_unrealized_pnl_usd`. | Downstream orchestrators lacked access to comprehensive portfolio health data. |
| **12** | **Unsafe API Error Handling** | **MEDIUM** | Returned raw error strings without setting fail-closed status. | Could lead to unhandled `KeyError` or false assumption of zero positions. |

---

## 3. Real-Time Position Monitoring Engine

For every open position on Delta Exchange, Agent 9 monitors and derives:

- **Identity & Direction:** `symbol`, `direction` (`LONG` / `SHORT`), `leverage`.
- **Pricing & Multipliers:** `entry_price`, `current_mark_price`, `contract_value`, `contract_type` (`linear` vs `inverse`).
- **Volume & Quantities:** `contracts`, `base_quantity` (e.g. $0.02$ BTC), `notional_usd`.
- **PnL Accounting:** `unrealized_pnl`, `realized_pnl`.
- **Protective Anchors:** `initial_stop_loss`, `current_stop_loss`, `take_profit_levels`.
- **Surveillance Metrics:** `liquidation_price`, `liquidation_distance_pct`, `position_age_seconds`.
- **Source of Truth:** Clearly marked with `is_exchange_confirmed: True`.

---

## 4. Mathematical Exposure and PnL Formulation

### A. Linear Contracts (USDT-Margined Perpetual Futures)
Linear contracts settle in USDT with notional values proportional to the underlying mark price.

$$\text{Base Quantity} = \text{Contracts} \times \text{Contract Value}$$

$$\text{Notional Value (USD)} = \text{Base Quantity} \times P_{\text{mark}}$$

$$\text{PnL}_{\text{Long}} = (P_{\text{mark}} - P_{\text{entry}}) \times \text{Contracts} \times \text{Contract Value}$$

$$\text{PnL}_{\text{Short}} = (P_{\text{entry}} - P_{\text{mark}}) \times \text{Contracts} \times \text{Contract Value}$$

### B. Inverse Contracts (Coin-Margined Perpetual Futures)
Inverse contracts have fixed USD contract values (e.g. $\$1.00$ per contract) and settle in the underlying cryptocurrency (e.g. BTC).

$$\text{Notional Value (USD)} = \text{Contracts} \times \text{Contract Value}$$

$$\text{Base Quantity} = \frac{\text{Notional Value}}{P_{\text{mark}}}$$

$$\text{PnL}_{\text{Long (Coin)}} = \left( \frac{1}{P_{\text{entry}}} - \frac{1}{P_{\text{mark}}} \right) \times \text{Contracts} \times \text{Contract Value}$$

$$\text{PnL}_{\text{Short (Coin)}} = \left( \frac{1}{P_{\text{mark}}} - \frac{1}{P_{\text{entry}}} \right) \times \text{Contracts} \times \text{Contract Value}$$

$$\text{PnL (USD)} = \text{PnL}_{\text{Coin}} \times P_{\text{mark}}$$

### C. Mark-to-Liquidation Distance
To eliminate the legacy flaw of measuring liquidation from entry, distance is calculated from the **live mark price**:

$$\text{Distance}_{\text{Long}} = \frac{P_{\text{mark}} - P_{\text{liq}}}{P_{\text{mark}}} \times 100\%$$

$$\text{Distance}_{\text{Short}} = \frac{P_{\text{liq}} - P_{\text{mark}}}{P_{\text{mark}}} \times 100\%$$

---

## 5. Protective Order Verification & Emergency Containment

Agent 9 performs active verification of protective stops during every monitoring cycle:

```
+-------------------------------------------------------------------------------+
|                      EXCHANGE POSITION DETECTED (e.g. BTCUSD)                 |
+-------------------------------------------------------------------------------+
                                       |
                                       v
+-------------------------------------------------------------------------------+
|         QUERY EXCHANGE OPEN ORDERS & FILTER FOR STOP-LOSS ORDERS              |
+-------------------------------------------------------------------------------+
                                       |
       +-------------------------------+-------------------------------+
       |                               |                               |
       v                               v                               v
[STOP FOUND & VALID]        [STOP QUANTITY DEFICIT]          [NO STOP FOUND]
- Side matches position     - Stop Size < Position Size      - Zero protective stops
- Quantity >= Position      - Flags partial-fill gap         - IMMEDIATE CRITICAL EVENT
- Price on correct side     - Severity: HIGH_RISK            - Trigger EmergencyController
- Status: PROTECTED         - Status: VULNERABLE             - Status: UNPROTECTED
```

### Emergency Containment Workflow
1. If an open position lacks a confirmed exchange stop-loss, `all_protected` is marked `False`.
2. A `CRITICAL` risk event is generated and logged to audit trails.
3. Telegram receives an immediate, deduplicated high-priority alert.
4. `EmergencyController.verify_and_ensure_sl_protection()` is invoked directly to place an immediate emergency protective bracket.
5. Overall portfolio status escalates to **`CRITICAL`**, preventing downstream agents from initiating new trades.

---

## 6. Exchange and Local State Reconciliation

Agent 9 bridges live exchange reality with local persistence (`StateManager` SQLite DB):

- **Discovered on Exchange:** Position exists on Delta Exchange but has no local record $\rightarrow$ auto-registered in `StateManager`.
- **Orphans Closed Locally:** Position marked `OPEN` locally but closed on exchange $\rightarrow$ marked `CLOSED` in `StateManager`.
- **Quantity Mismatch:** Position size differs between exchange and local DB $\rightarrow$ flagged and updated.
- **State Marker:** When any divergence occurs, `exchange_sync_status` transitions to **`DESYNCHRONIZED`**, prompting synchronization without overwriting conflicting state silently.

---

## 7. Correlation & Concentration Risk Engine

Monitors asset clusters to prevent compounding directional drawdowns:
- **`CRYPTO_MAJOR_ALT` Cluster:** `BTC`, `ETH`, `SOL`, `XRP`, `DOGE`, `ADA`.
- **`PRECIOUS_METALS` Cluster:** `XAU`, `XAUT`, `PAXG`.

Surveillance checks:
1. **Cluster Concurrency:** Flags warning if concurrent positions in the same direction exceed `max_correlated_positions` (default: 2).
2. **Capital Concentration:** Flags warning if cluster exposure exceeds $50\%$ of account equity.

---

## 8. Warning Tiers & Threshold Configuration

| Risk Metric | Normal / Healthy | Warning Level | High Risk Level | Critical Emergency Level |
|---|:---:|:---:|:---:|:---:|
| **Margin Utilization** | $< 70\%$ | $\ge 70\%$ | $\ge 85\%$ | $\ge 95\%$ |
| **Liquidation Distance** | $> 10\%$ | $\le 10\%$ | $\le 5\%$ | $\le 2.5\%$ |
| **Protective Stops** | $100\%$ Covered | - | Partial Deficit | Unprotected (Naked) |
| **Daily Drawdown** | $< 3.0\%$ | $\ge 2.0\%$ | $\ge 2.5\%$ | $\ge 3.0\%$ |
| **Weekly Drawdown** | $< 5.0\%$ | $\ge 3.5\%$ | $\ge 4.5\%$ | $\ge 5.0\%$ |
| **Consecutive Losses** | $< 3$ | $2$ | $\ge 3$ | $\ge 4$ |
| **Exchange Sync** | `SYNCHRONIZED` | - | - | `DESYNCHRONIZED` |

---

## 9. Output Schema Contract

Agent 9 outputs a comprehensive status dictionary that is fully backward-compatible with legacy consumers:

```json
{
  "account_equity": 10000.0,
  "available_balance": 8000.0,
  "margin_used": 2000.0,
  "margin_utilization": 20.0,
  "margin_status": "NORMAL",
  "total_open_exposure": 1200.0,
  "long_exposure": 600.0,
  "short_exposure": 600.0,
  "net_directional_exposure": 0.0,
  "gross_exposure": 1200.0,
  "total_open_risk": 35.0,
  "remaining_portfolio_risk": 15.0,
  "daily_pnl": 50.0,
  "weekly_pnl": 120.0,
  "daily_drawdown": 0.0,
  "weekly_drawdown": 0.0,
  "max_observed_drawdown": 0.0,
  "consecutive_losses": 0,
  "open_positions": [...],
  "correlated_exposure": {...},
  "liquidation_warnings": [],
  "protective_order_status": {
    "all_protected": true,
    "protected_positions": [...],
    "unprotected_positions": [],
    "insufficient_quantity_positions": [],
    "duplicate_stop_orders": []
  },
  "exchange_sync_status": "SYNCHRONIZED",
  "reconciliation_report": {...},
  "stale_data_status": {
    "is_stale": false,
    "last_poll_age_seconds": 1.2
  },
  "risk_events": [],
  "monitoring_timestamp": 1794222000.0,
  "overall_status": "HEALTHY",

  "active_count": 2,
  "total_unrealized_pnl_usd": 50.0,
  "positions": [...]
}
```

