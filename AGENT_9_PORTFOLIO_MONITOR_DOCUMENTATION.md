# AGENT 9 – PORTFOLIO MONITOR DOCUMENTATION
## Delta Exchange Multi-Agent Quantitative Trading System
**Target Module:** `multiagent_team/portfolio_monitor.py`  
**Role:** Continuous Position Monitoring, Exposure Aggregation, Liquidation Surveillance, & Capital Protection Sentinel  

---

## 1. Architectural Overview

Agent 9 (Portfolio Monitor) operates as the primary capital protection sentinel. It continuously polls exchange open positions, compares live state with local `StateManager`, monitors mark-to-liquidation distances, verifies protective stop orders, and coordinates emergency intervention when safety invariants are breached.

```
                  ┌─────────────────────────────────────┐
                  │       Exchange Position Feeds       │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │      Portfolio Monitor Agent        │
                  │  - Linear & Inverse Calculations    │
                  │  - Mark-to-Liquidation Tracking     │
                  │  - State Reconciliation             │
                  │  - Missing Stop Order Detection     │
                  └──────────────────┬──────────────────┘
                                     │
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                        ▼
     [HEALTHY / OK]          [HIGH_RISK WARNING]         [CRITICAL ABORT]
 (All protected, margin   (Deficit stops, margin    (Missing stop, liquidation
  < 70%, liq > 10%)        > 85%, liq 2.5%-5.0%)     < 2.5%, desync error)
```

---

## 2. Core Methodologies & Mathematical Models

### 2.1 Contract Specifications & Exposure Calculations
Delta Exchange supports both linear and inverse contracts:

#### Linear Contracts (ETHUSD, SOLUSD, XRPUSD, XAUUSD):
- $\text{Base Quantity} = \text{contracts} \times \text{contract\_value}$
- $\text{Notional USD} = \text{Base Quantity} \times \text{mark\_price}$
- $\text{Unrealized PnL (Long)} = (\text{mark\_price} - \text{entry\_price}) \times \text{contracts} \times \text{contract\_value}$
- $\text{Unrealized PnL (Short)} = (\text{entry\_price} - \text{mark\_price}) \times \text{contracts} \times \text{contract\_value}$

#### Inverse Contracts (BTCUSD):
- $\text{Notional USD} = \text{contracts} \times \text{contract\_value}$
- $\text{Base Quantity} = \frac{\text{Notional USD}}{\text{mark\_price}}$
- $\text{Unrealized PnL (Long)} = \left(\frac{1}{\text{entry\_price}} - \frac{1}{\text{mark\_price}}\right) \times \text{contracts} \times \text{contract\_value} \times \text{mark\_price}$
- $\text{Unrealized PnL (Short)} = \left(\frac{1}{\text{mark\_price}} - \frac{1}{\text{entry\_price}}\right) \times \text{contracts} \times \text{contract\_value} \times \text{mark\_price}$

### 2.2 True Mark-to-Liquidation Surveillance
Liquidation distance is measured from the **current mark price** to the liquidation price:
- Long: $\text{Distance \%} = \frac{\text{mark\_price} - \text{liq\_price}}{\text{mark\_price}} \times 100$
- Short: $\text{Distance \%} = \frac{\text{liq\_price} - \text{mark\_price}}{\text{mark\_price}} \times 100$

#### Alert Tiers:
- **WARNING:** Distance $\le 10.0\%$
- **HIGH_RISK:** Distance $\le 5.0\%$
- **CRITICAL:** Distance $\le 2.5\%$

### 2.3 Strict Missing Data Handling
- Never substitutes `entry_price` for missing `mark_price`.
- Never defaults missing liquidation distance to safe `999.0%`.
- If critical metrics are missing or zero, sets values to `None`, returns status `UNKNOWN`, and issues an alert.

### 2.4 Protective Stop Order Reconciliation & Emergency Trigger
- Reconciles exchange positions with active stop-loss orders.
- If a position is unprotected (`protective_order_status.all_protected == False`), triggers `EmergencyController.verify_and_ensure_sl_protection(...)`.
- If emergency placement fails, triggers an immediate market exit to prevent unhedged liquidation.

---

## 3. Public Interface Specification

```python
def monitor_positions(self) -> Dict[str, Any]
def calculate_position_metrics(
    position: Dict[str, Any],
    contract_spec: Dict[str, Any],
    mark_price_override: Optional[float] = None
) -> Dict[str, Any]
def get_contract_spec(
    symbol: str,
    client: Optional[DeltaExchangeClient] = None,
    raw_product: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]
```
