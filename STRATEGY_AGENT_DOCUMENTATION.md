# AGENT 4: STRATEGY AGENT (ALPHA GENERATOR)
## QUANTITATIVE ARCHITECTURE, MULTI-TIMEFRAME SPECIFICATION & SMC AUDIT

**Author:** Quantitative Trading Systems Engineering & Algorithmic Architecture  
**System Component:** Agent 4 — Strategy Agent (Alpha Generator)  
**Target Module:** `multiagent_team/strategy_agent.py`  
**Classification:** Mission-Critical Alpha Generation & Technical Decision Layer  
**Version:** 2.0.0-PROD  

---

## 1. Executive Summary & Quantitative Mandate

Within the Delta Exchange 11-agent multi-agent algorithmic trading system, **Agent 4 (Strategy Agent)** is the primary technical alpha engine. It evaluates multi-timeframe market regime intelligence produced by Agent 1 (Regime Analyst), incorporates exposure guidance from Agent 2, respects news risk and sentiment from Agent 3, and generates disciplined, high-conviction trade setups for BTC, ETH, SOL, XRP, and XAU perpetual markets.

### The Core Objective
The goal is **NOT** to maximize trading frequency. The mandate is to generate **fewer, higher-conviction, mathematically verified setups** with asymmetric reward-to-risk profiles ($\text{Net } R:R \ge 2.2:1$), disciplined invalidation stops, and zero lookahead bias.

Every generated setup must:
1. Conform to a strict multi-timeframe hierarchy: **1H** (Macro Direction), **15M** (Smart Money Structure), **5M** (Primary Entry Confirmation), and **1M** (Execution Refinement).
2. Use deterministic Smart Money Concepts (SMC): confirmed swing pivots, Break of Structure (BOS), Change of Character (CHOCH), Liquidity Sweeps, Fair Value Gaps (FVG), and Consequent Encroachment (CE).
3. Employ a lean, non-redundant indicator stack with normalized confluence scoring.
4. Maintain full deterministic compatibility with Agent 5 (Time Machine Agent), Agent 6 (Risk Gatekeeper), Agent 7 (Deterministic Safety Controller), and the Central Orchestrator.

---

## 2. Exhaustive Audit of Legacy Implementation

Before implementing improvements, a comprehensive code audit of `multiagent_team/strategy_agent.py` and its interacting dependencies was conducted:

| # | Audit Dimension | Legacy Implementation Finding | Severity | Quantitative / Operational Risk |
|---|---|---|---|---|
| **1** | **Pass-Through Shell Weakness** | The legacy Strategy Agent acted largely as a score modifier over `src/technical_analysis.py`. If `high_probability_setup["qualified"]` was not already set, it returned `None`, without independent multi-timeframe analysis. | **CRITICAL** | Total reliance on an upstream function without independent validation or fallback. |
| **2** | **Absence of True BOS & CHOCH Engine** | Neither `strategy_agent.py` nor `technical_analysis.py` had an objective, pivot-based Break of Structure (BOS) or Change of Character (CHOCH) detection mechanism. | **CRITICAL** | Trades entered without structural trend-continuation or trend-reversal confirmation. |
| **3** | **Missing Timeframe Hierarchy (1H $\rightarrow$ 15M $\rightarrow$ 5M $\rightarrow$ 1M)** | Timeframes were inspected ad-hoc without a structured hierarchical pipeline. 5M primary entry triggers and 1M execution refinements were completely absent. | **HIGH** | Premature entries on 15m candle bodies; inability to time entries precisely. |
| **4** | **Arbitrary Additive Point Stacking** | Boosts were summed directly without normalization: `score + 10 (primary) + 4 (ATR) + 9 (VWAP) + 6 (MACD) + 11 (Liq) + 10 (FVG) + 16 (Order Flow)`. Scores could wildly exceed 120+ points. Correlated indicators were double-counted. | **HIGH** | Score inflation masking failed structural conditions. False sense of setup quality. |
| **5** | **Silent Failures & Lack of NO_TRADE Telemetry** | When any filter failed, `evaluate_setup` silently returned `None`. There was no structured record explaining why a symbol was rejected (`no_trade_reason`, failed gates, component scores). | **MEDIUM** | Inability for the Orchestrator, logs, or user to understand why setups were passed over. |
| **6** | **Lack of Asset-Specific Calibration** | BTC, ETH, SOL, XRP, and XAU used identical hard-coded thresholds (spread limit $0.15\%$, min R:R 2.2, min score 85/90) regardless of distinct liquidity, volatility, and tick specifications. | **HIGH** | Either over-rejecting volatile assets (SOL/XRP) or under-protecting tight assets (BTC/ETH). |
| **7** | **Candle Completion Ambiguity** | Interchanged the live forming candle (`closes[-1]`) with closed candles without explicit lookahead prevention. | **HIGH** | Intra-candle repainting where signals appear and disappear before candle close. |
| **8** | **Discrepancy with Time Machine Archetypes** | Generated labels did not always deterministically correspond to the historical replay archetypes required by the Time Machine probability engine. | **CRITICAL** | Time Machine rejects valid setups or validates mismatched setups due to naming divergence. |

---

## 3. Multi-Timeframe Strategy Architecture

The upgraded Strategy Agent operates across a four-tier hierarchical timeframe structure:

```
+-------------------------------------------------------------------------------+
| 1H TIMEFRAME: Market Direction & Macro Regime Context                         |
| - Higher Highs/Lows vs Lower Highs/Lows (Swing Structure)                     |
| - Trend Classification: BULLISH, BEARISH, NEUTRAL_RANGEBOUND                  |
| - Volatility Classification: HIGH_VOLATILITY, LOW_VOLATILITY, NORMAL (ATR/ADX)|
| - Trend Alignment: EMA 50 / EMA 200 Slope & Stance                            |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| 15M TIMEFRAME: Smart Money Structure & Institutional Liquidity                |
| - Break of Structure (BOS) - Trend Continuation Close                         |
| - Change of Character (CHOCH) - Trend Reversal Close                          |
| - Liquidity Sweeps (BSL / SSL) with Reclaim & 25%+ Wick Rejection             |
| - Fair Value Gaps (FVG) & 50% Consequent Encroachment (CE) Retest             |
| - High-Displacement Structural Order Blocks                                   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| 5M TIMEFRAME: Primary Entry Confirmation & Trigger Execution                  |
| - Confirmed Sweep / CHOCH / FVG Retest / EMA21 Pullback Confirmation          |
| - Session VWAP Intraday Alignment & Value Area Stance                         |
| - Realized Asymmetric Risk-to-Reward (Net R:R >= 2.2:1)                       |
| - Volume Surge Confirmation (Volume >= 1.2x SMA20)                            |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| 1M TIMEFRAME (Optional): Execution Refinement                                 |
| - Micro-structure pullback to optimize entry price closer to invalidation stop|
| - Strict Rule: 1M CANNOT override 1H/15M direction or widen risk budget      |
+-------------------------------------------------------------------------------+
```

---

## 4. Smart Money Concepts: Deterministic Formulation

### A. Liquidity Sweep Detection
- **Swing Points:** Identified using lookahead-free fractal pivots (configurable `pivot_window`, default 2 bars).
- **Sweep Event:**
  - **Bearish BSL Sweep:** Candle high spikes above prior swing high ($H_i > \text{BSL}$), but candle closes back below ($\text{Close}_i < \text{BSL}$). Upper wick ratio $\ge 25\%$ of candle range.
  - **Bullish SSL Sweep:** Candle low sweeps below prior swing low ($L_i < \text{SSL}$), but candle closes back above ($\text{Close}_i > \text{SSL}$). Lower wick ratio $\ge 25\%$ of candle range.
- **Genuine Breakout vs Sweep:** A true breakout requires candle body close *beyond* the level with volume expansion; a sweep shows immediate wick rejection back into the range.
- **Duplicate Prevention:** Tracks `last_swept_level` per asset to prevent re-signaling on identical price levels.

### B. Break of Structure (BOS) vs Change of Character (CHOCH)
- **Methodology:** Requires **candle-close confirmation** beyond the swing pivot. Wick-only breaches are classified as liquidity sweeps or tests, not structural breaks.
- **Bullish BOS:** In an existing bullish trend, candle close exceeds the previous swing high ($\text{Close}_i > \text{SwingHigh}_{\text{prev}}$).
- **Bearish BOS:** In an existing bearish trend, candle close breaks below the previous swing low ($\text{Close}_i < \text{SwingLow}_{\text{prev}}$).
- **Bullish CHOCH:** In a prevailing bearish trend, candle close breaks above the most recent swing high, indicating institutional structural reversal.
- **Bearish CHOCH:** In a prevailing bullish trend, candle close breaks below the most recent swing low, indicating institutional structural reversal.

### C. Fair Value Gap (FVG) Life-Cycle & 50% Consequent Encroachment (CE)
- **3-Candle Imbalance:**
  - **Bullish FVG:** $L_i > H_{i-2}$. Imbalance zone: $[H_{i-2}, L_i]$. Midpoint: $CE = (H_{i-2} + L_i) / 2.0$.
  - **Bearish FVG:** $H_i < L_{i-2}$. Imbalance zone: $[H_i, L_{i-2}]$. Midpoint: $CE = (H_i + L_{i-2}) / 2.0$.
- **Mitigation & Invalidation:**
  - `UNTESTED`: Price has not re-entered the zone.
  - `RETESTING`: Price has tapped into the gap boundary.
  - `CE_RETESTED`: Price has tested the 50% CE level and closed with a rejection wick.
  - `MITIGATED`: Price has closed completely through the opposite boundary. Mitigated gaps are permanently purged from generating entry signals.
- **Supply/Demand Filters:** Rejects buy setups if unmitigated Bearish FVG supply sits within $0.35\%$ overhead; rejects sell setups if unmitigated Bullish FVG demand sits within $0.35\%$ underneath.

---

## 5. Lean Indicator Stack & Normalized Confluence Scoring

To eliminate collinearity and double-counting of correlated momentum indicators, the strategy enforces a **100-point normalized scoring model**:

| Confluence Dimension | Weight | Criteria Evaluated |
|---|---:|---|
| **1H Macro Market Context** | **15%** | Higher Highs/Lows trend alignment, EMA 50 / 200 slope, ADX $\ge 20$, non-conflicting macro regime. |
| **15M Market Structure & BOS/CHOCH** | **25%** | Confirmed structural trend, BOS continuation, or confirmed CHOCH structural reversal. |
| **Liquidity Event / Sweep** | **20%** | Bullish SSL or Bearish BSL sweep with $\ge 25\%$ wick rejection, or defense of institutional liquidity pool. |
| **FVG & Retracement Quality** | **15%** | 50% CE test, wick rejection at FVG boundary, or optimal 0.618 Fibonacci retracement into discount/premium. |
| **5M Entry & Momentum Trigger** | **15%** | 5M trigger alignment: EMA21 support/resistance bounce, RSI momentum corridor ($40 \le RSI \le 75$ for Long, $25 \le RSI \le 60$ for Short), session VWAP alignment. |
| **Volume & Order Flow Confirmation** | **10%** | Volume surge $\ge 1.2\times$ SMA20, CVD absorption/exhaustion divergence, or favorable order book depth imbalance (OBI). |
| **Total Normalized Score** | **100%** | Normalized composite score. Must meet asset-specific floor ($\ge 80 - 85$). |

### Mandatory Hard Vetoes (Score Bypassing Prohibited)
Even if an asset achieves an 95/100 score, the trade is **immediately rejected (VETOED)** if any of the following mandatory conditions fail:
1. **Spread Gate:** Current spread exceeds asset-specific `max_spread_pct`.
2. **Structural Stop Gate:** Stop loss is missing, inverted, or placed without technical structure.
3. **ATR Volatility Gate:** Stop distance is $< 0.40$x ATR (noise stop) or $> 3.0$x ATR (capital inefficiency).
4. **Asymmetric R:R Gate:** Planned Net Risk-to-Reward ratio $< 2.2:1$.
5. **Macro Conflict Gate:** Taking Long into a confirmed 4H Bearish trend (unless confirmed by 15m CHOCH).
6. **News Risk Gate:** Trade blocked during high-impact breaking news or abnormal volatility spike.
7. **Entry Drift Gate:** Current price has drifted $> 0.50\%$ from the optimal entry trigger.

---

## 6. Asset-Specific Configurations

Every supported asset has dedicated parameters reflecting its unique market microstructure:

```python
ASSET_CONFIGS = {
    "BTCUSD": {
        "max_spread_pct": 0.05,       # Ultra-tight institutional spread
        "target_rr_ratio": 2.5,
        "min_confluence_score": 85,   # Strict primary asset floor
        "atr_stop_min_mult": 0.45,
        "atr_stop_max_mult": 2.5,
        "fvg_min_gap_pct": 0.03,
        "is_primary": True,
        "priority_tier": 1
    },
    "ETHUSD": {
        "max_spread_pct": 0.07,
        "target_rr_ratio": 2.5,
        "min_confluence_score": 85,
        "atr_stop_min_mult": 0.45,
        "atr_stop_max_mult": 2.5,
        "fvg_min_gap_pct": 0.04,
        "is_primary": True,
        "priority_tier": 1
    },
    "XAUUSD": {
        "max_spread_pct": 0.10,       # Gold market microstructure
        "target_rr_ratio": 2.4,
        "min_confluence_score": 85,
        "atr_stop_min_mult": 0.50,
        "atr_stop_max_mult": 2.5,
        "fvg_min_gap_pct": 0.03,
        "is_primary": True,
        "priority_tier": 1
    },
    "SOLUSD": {
        "max_spread_pct": 0.12,       # Higher altcoin volatility & spread
        "target_rr_ratio": 2.6,
        "min_confluence_score": 80,
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.05,
        "is_primary": False,
        "priority_tier": 2
    },
    "XRPUSD": {
        "max_spread_pct": 0.15,
        "target_rr_ratio": 2.6,
        "min_confluence_score": 80,
        "atr_stop_min_mult": 0.40,
        "atr_stop_max_mult": 3.0,
        "fvg_min_gap_pct": 0.05,
        "is_primary": False,
        "priority_tier": 2
    }
}
```

---

## 7. Entry, Stop-Loss, and Take-Profit Formulation

### Entry
- Entries execute strictly **after candle-close confirmation** or at the retest of an identified institutional level (e.g. 50% CE of FVG, swept level reclaim, or EMA21 test).
- Market chasing is prevented via the $0.50\%$ maximum entry drift threshold.

### Stop-Loss (Technical Invalidation + ATR Buffer)
- Placed objectively beyond the setup invalidation level:
  - **Long:** $\text{SL} = \min(\text{Sweep Low}, \text{FVG Bottom}, \text{Swing Low}) - (0.10 \times \text{ATR}_{15m})$.
  - **Short:** $\text{SL} = \max(\text{Sweep High}, \text{FVG Top}, \text{Swing High}) + (0.10 \times \text{ATR}_{15m})$.
- Enforces $0.40\text{x} \le \frac{\text{Stop Distance}}{\text{ATR}_{15m}} \le 3.0\text{x}$.

### Take-Profit & Partial Scaled Targets
- **TP1 (Partial Scale-out 50%):** Placed at $+1.50R$ to $+2.00R$. Once TP1 is achieved, Risk Gatekeeper / Trailing Engine locks the stop to Breakeven ($+0.50R$).
- **TP2 (Final Runner):** Placed at the opposing major liquidity pool (nearest BSL for Longs, nearest SSL for Shorts) or structural swing target, achieving minimum planned $R:R \ge 2.2:1$.

---

## 8. Signal Output Contract & Schema

The upgraded Strategy Agent returns a rich, strictly typed trade proposal payload:

```python
{
    "symbol": "BTCUSD",
    "strategy_name": "Institutional_SSL_Sweep_15m_92pts",
    "side": "buy",
    "direction": "buy",
    "setup_type": "SWEEP_REVERSAL",
    "timeframe": "15m",
    "entry_price": 70000.0,
    "stop_loss_price": 69400.0,
    "stop_loss": 69400.0,
    "take_profit_price": 71600.0,
    "take_profit": 71600.0,
    "partial_targets": [
        {"target_price": 70900.0, "portion_pct": 50, "label": "TP1_SCALE_OUT_LOCK_BREAKEVEN"},
        {"target_price": 71600.0, "portion_pct": 50, "label": "TP2_RUNNER_BSL_TARGET"}
    ],
    "stop_distance_pct": 0.86,
    "planned_rr_ratio": 2.67,
    "planned_risk_reward": 2.67,
    "score": 92,
    "confidence_score": 92,
    "confluence_breakdown": {
        "macro_1h_score": 15,
        "market_structure_15m_score": 25,
        "liquidity_event_score": 20,
        "fvg_retracement_score": 12,
        "entry_trigger_5m_score": 12,
        "volume_order_flow_score": 8,
        "total_score": 92
    },
    "market_regime": "STRONG_BULLISH",
    "liquidity_level": 69350.0,
    "fvg_details": {"type": "BULLISH_FVG", "ce": 69850.0, "state": "CE_RETESTED"},
    "structure_confirmation": "BULLISH_CHOCH_CONFIRMED",
    "invalidation_reason": "Close below SSL sweep low ($69,350.00)",
    "signal_timestamp": 1700000000.0,
    "data_timestamp": 1700000000.0,
    "expires_at": 1700003600.0,
    "signal_expiry": 1700003600.0,
    "no_trade_reason": None,
    "is_primary": True,
    "priority_tier": 1,
    "thesis": "🌟 [PRIMARY FOCUS ASSET] 🛡️ [OPTIMAL 1.5x ATR STOP] 💧 [BULLISH SSL SWEEP + MSS CONFIRMED]...",
    "created_at": 1700000000.0,
    "vwap": 69800.0,
    "spread_pct": 0.02,
    "atr_14": 400.0,
    "atr_stop_multiple": 1.50,
    "fvg_profile": {...},
    "order_flow_profile": {...},
    "confluence": {...}
}
```

---

## 9. Agent Workflow Integration

```
[Agent 1: Regime Analyst] ------> Raw Multi-Timeframe Candles & Indicator Feeds
                                             |
[Agent 2: Exposure Coach] ------> Portfolio Exposure Limits & Adaptive Memory
                                             |
[Agent 3: News Sentiment] ------> Global Macro Risk & Breaking News Vetoes
                                             |
                                             v
                             +-------------------------------+
                             |    AGENT 4: STRATEGY AGENT    |
                             |  - 1H Macro Direction         |
                             |  - 15M SMC Structure (BOS/CHO)|
                             |  - 5M Primary Setup & Trigger |
                             |  - 100pt Normalized Confluence|
                             |  - Asset-Specific Calibration |
                             +-------------------------------+
                                             |
                                    Qualified Setups
                                             |
                                             v
                             [Agent 5: Time Machine Engine]   <-- Historical Simulation
                                             |
                                     Approved Setups
                                             |
                                             v
                             [Agent 6: Risk Gatekeeper]       <-- Sizing & Margin Validation
                                             |
                                     Approved Trades
                                             |
                                             v
                             [Agent 7: Safety Controller]     <-- Deterministic Hard Invariants
                                             |
                                       Valid Token
                                             |
                                             v
                             [Central Orchestrator]           <-- Telegram 2-Way Authorization
```

---

## 10. Conclusion

The upgraded **Strategy Agent (Agent 4)** transforms the trading system from an ad-hoc score adder into an institutional, multi-timeframe SMC scalping engine. It guarantees that setups are structurally sound, ATR-protected, asymmetric in payoff, free of lookahead bias, and fully aligned with the rest of the multi-agent pipeline.

