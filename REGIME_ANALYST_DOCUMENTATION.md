# AGENT 1: REGIME ANALYST (MARKET REGIME & CONTEXT ENGINE)
## QUANTITATIVE ARCHITECTURE, 9-REGIME CLASSIFICATION & MULTI-TIMEFRAME SPECIFICATION

**Author:** Quantitative Trading Systems Engineering & Algorithmic Architecture  
**System Component:** Agent 1 — Regime Analyst  
**Target Module:** `multiagent_team/regime_analyst.py`  
**Classification:** Layer 1 Market Intelligence & Directional Context Infrastructure  
**Version:** 2.0.0-PROD  

---

## 1. Executive Summary & Quantitative Mandate

Within the Delta Exchange 11-agent multi-agent algorithmic trading system, **Agent 1 (Regime Analyst)** operates as the fundamental sensory and contextual gateway. Its quantitative mandate is to diagnose the prevailing state of the market across BTC, ETH, SOL, XRP, and XAU perpetual futures contracts before any tactical setups are evaluated.

### The Core Objective
The purpose of the Regime Analyst is **NOT** to forecast prices or predict directional pivots. The explicit objective is **objective, deterministic market state identification**:
- Classifying the prevailing regime into one of 9 canonical market states.
- Establishing the macro directional bias on 1H that anchors lower-timeframe tactical entries.
- Identifying volatility regimes (expansion, compression, calm) to calibrate risk parameters.
- Filtering out choppy, trendless, or wildly chaotic conditions where scalping strategies suffer from elevated friction and false breakouts.

---

## 2. Exhaustive Audit of Legacy Implementation

A line-by-line audit of legacy `multiagent_team/regime_analyst.py` and its interaction with `src/technical_analysis.py` identified eight primary vulnerabilities:

| # | Audit Dimension | Legacy Implementation Flaw | Severity | Quantitative / Operational Risk |
|---|---|---|---|---|
| **1** | **Coarse Regime Classification** | Only supported 5 simplistic regimes (`STRONG_BULLISH`, `MILD_BULLISH`, `STRONG_BEARISH`, `MILD_BEARISH`, `NEUTRAL_RANGEBOUND`) based almost entirely on moving average order. | **CRITICAL** | Failed to distinguish high-volatility expansions, low-volatility compressions, or transition states. |
| **2** | **Omission of 5M Timeframe** | Claimed multi-timeframe scalping support but only fetched 15M and 1H data; 5M (the primary scalp entry timeframe) was completely omitted from ingestion. | **CRITICAL** | Lower-timeframe momentum and entry environment were completely invisible to Layer 1. |
| **3** | **Unstable Regime Whipsawing** | Calculated regime snapshot candle-by-candle with zero hysteresis or confirmation memory. A single wick could flip the regime from Bullish to Neutral to Bearish. | **HIGH** | Rapid regime flipping causing strategic whiplash in downstream agents. |
| **4** | **Uniform Hardcoded Volatility Thresholds** | Applied universal scalar thresholds (e.g., ATR $> 3.0\%$ = high volatility) without asset-specific calibration for assets with differing volatilities (e.g., SOL vs XAU). | **HIGH** | Over-flagged volatile alts (SOL/XRP) as dangerous while under-detecting dangerous volatility spikes in Gold (XAU). |
| **5** | **Lack of Transition Detection** | Had no concept of regime transitions (e.g., trend weakening, range breakout, volatility squeeze), presenting every state as static. | **MEDIUM** | Inability to alert Agent 4 to prepare for breakout entries or tighten trailing stops. |
| **6** | **Uncalibrated Confidence Scoring** | Reported arbitrary confidence scores or defaulted to static numbers (e.g. 50/100) without mathematical decomposition. | **MEDIUM** | Risk Gatekeeper and Orchestrator could not objectively weigh conviction. |
| **7** | **Incomplete / Forming Candle Ambiguity** | Evaluated live forming candle `closes[-1]` interchangeably with closed candles without explicit provisional tagging. | **HIGH** | Repainting risks where regime signals appear mid-bar and disappear by candle close. |
| **8** | **Lack of Structured Fallback on Data Errors** | In `analyze_symbol`, if 1H data failed, it returned an error dictionary that forced downstream agents to handle raw error strings rather than a clean `UNKNOWN` status. | **MEDIUM** | Potential unhandled exceptions in downstream consumer loops. |

---

## 3. The 9 Canonical Market Regimes

The upgraded Regime Analyst deterministically maps market conditions into one of 9 canonical regimes:

```
                               +------------------------------------+
                               |     MARKET REGIME TAXONOMY        |
                               +------------------------------------+
                                                 |
         +---------------------------------------+---------------------------------------+
         |                                       |                                       |
         v                                       v                                       v
   [TRENDING]                               [VOLATILITY]                             [SPECIAL]
   - STRONG_UPTREND                         - HIGH_VOLATILITY                        - TRANSITIONAL
   - WEAK_UPTREND                           - LOW_VOLATILITY                         - UNKNOWN
   - STRONG_DOWNTREND                       - RANGING (Sideways/Choppy)
   - WEAK_DOWNTREND
```

### Deterministic State Definitions:

1. **`STRONG_UPTREND`**:
   - $P_{1H} > \text{EMA}_{50} \ge \text{EMA}_{200}$
   - $\text{ADX}_{1H} \ge \text{ADX}_{\text{strong}}$ (e.g. $\ge 30$) with $+DI > -DI$
   - Structural Higher Highs and Higher Lows confirmed on 15M/1H
   - Directional Bias: **`BULLISH`** | Trend Strength: **`STRONG`**
2. **`WEAK_UPTREND`**:
   - $P_{1H} > \text{EMA}_{50}$ with $+DI > -DI$, but $\text{EMA}_{50}$ not decisively above $\text{EMA}_{200}$ OR $\text{ADX} \in [20, 30)$
   - Upward structural bias with moderate momentum
   - Directional Bias: **`BULLISH`** | Trend Strength: **`WEAK` / `MODERATE`**
3. **`STRONG_DOWNTREND`**:
   - $P_{1H} < \text{EMA}_{50} \le \text{EMA}_{200}$
   - $\text{ADX}_{1H} \ge \text{ADX}_{\text{strong}}$ with $-DI > +DI$
   - Structural Lower Highs and Lower Lows confirmed on 15M/1H
   - Directional Bias: **`BEARISH`** | Trend Strength: **`STRONG`**
4. **`WEAK_DOWNTREND`**:
   - $P_{1H} < \text{EMA}_{50}$ with $-DI > +DI$, but $\text{EMA}_{50}$ not decisively below $\text{EMA}_{200}$ OR $\text{ADX} \in [20, 30)$
   - Downward structural bias with moderate momentum
   - Directional Bias: **`BEARISH`** | Trend Strength: **`WEAK` / `MODERATE`**
5. **`RANGING`**:
   - $\text{ADX}_{1H} < \text{ADX}_{\text{trend}}$ (e.g. $< 20-22$)
   - Price oscillating around moving averages without sustained displacement
   - Directional Bias: **`NEUTRAL`** | Trend Strength: **`NONE`**
6. **`HIGH_VOLATILITY`**:
   - Normalized $\text{ATR}\% > \text{Threshold}_{\text{high}}$ OR sudden ATR expansion ($\text{ATR} \ge 1.8\times \text{SMA}_{20}(\text{ATR})$)
   - Large candles with elevated risk of stop hunting and whipsaw
   - Volatility State: **`HIGH_VOLATILITY`** | Directional Bias: **`NEUTRAL` / CAUTION**
7. **`LOW_VOLATILITY`**:
   - Normalized $\text{ATR}\% < \text{Threshold}_{\text{low}}$ AND volatility compression ($\text{ATR} \le 0.70\times \text{SMA}_{20}(\text{ATR})$)
   - Tight price consolidation pre-breakout
   - Volatility State: **`LOW_VOLATILITY`** | Directional Bias: **`NEUTRAL`**
8. **`TRANSITIONAL`**:
   - Market undergoing structural shift (e.g. 15M CHOCH breaking 1H trend, or trend weakening into range)
   - Provisional state during hysteresis confirmation window
   - Directional Bias: **`NEUTRAL` / TRANSITIONAL**
9. **`UNKNOWN`**:
   - Returned when data is missing, stale, or corrupted beyond safe pre-flight validation.
   - Fails closed to protect downstream systems.

---

## 4. Multi-Timeframe Analysis Engine

The multi-timeframe framework operates across three tightly integrated tiers:

```
+-------------------------------------------------------------------------------+
| 1H TIMEFRAME: Macro Directional Context & Volatility Anchor                   |
| - Higher Highs/Lows vs Lower Highs/Lows                                       |
| - EMA 50 / EMA 200 Slope & Separation                                         |
| - ADX(14) Trend Strength & Directional Movement (+DI / -DI)                   |
| - Normalized ATR% Volatility Classification                                   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| 15M TIMEFRAME: Market Structure & Structural Confirmation                     |
| - Confirmed Fractal Swings & Local Trend                                      |
| - Break of Structure (BOS) & Change of Character (CHOCH) Alignment            |
| - Donchian Channel Range Width & Support/Resistance Bounds                    |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| 5M TIMEFRAME: Short-Term Momentum & Entry Environment                         |
| - Short-Term Momentum (5M RSI, 5M EMA9/21 Alignment)                         |
| - Intraday Entry Environment Check                                            |
| - ABSOLUTE INVARIANT: 5M CANNOT independently reverse 1H Macro Bias           |
+-------------------------------------------------------------------------------+
```

---

## 5. Regime Transition Engine & Anti-Whipsaw Hysteresis

To prevent rapid flipping ("whipsaw") caused by temporary noise or intra-candle spikes:
1. **Rolling Regime History:** Maintains a rolling window of recent regime classifications per symbol.
2. **Hysteresis Confirmation Period:** A transition from an established trend regime (`STRONG_UPTREND` / `STRONG_DOWNTREND`) to a different regime requires **at least $N$ consecutive confirming bars** (configurable `hysteresis_bars`, default 2).
3. **Provisional Marking:** If only a single bar shows conflicting evidence, the regime is marked as `TRANSITIONAL` with `is_provisional = True`, alerting Agent 4 to exercise caution without prematurely flipping the entire macro bias.
4. **Transition Types Monitored:**
   - `TREND_WEAKENING`: ADX drops below threshold; price tests opposite side of EMA50.
   - `TREND_TO_RANGE`: Price compresses between moving averages with low ADX.
   - `RANGE_BREAKOUT`: Candle close breaks Donchian 20-bar channel with expanding ATR.
   - `VOLATILITY_EXPANSION`: Current ATR $\ge 1.50\times$ 20-period moving average of ATR.
   - `VOLATILITY_COMPRESSION`: Current ATR $\le 0.70\times$ 20-period moving average of ATR.

---

## 6. Asset-Specific Microstructure Calibration

Thresholds are normalized using percentage measurements and calibrated to each asset's volatility characteristics:

```python
ASSET_REGIME_CONFIGS = {
    "BTCUSD": {
        "adx_trend_threshold": 22.0,
        "adx_strong_trend_threshold": 30.0,
        "volatility_high_atr_pct": 2.5,   # % of price
        "volatility_low_atr_pct": 0.8,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "ETHUSD": {
        "adx_trend_threshold": 22.0,
        "adx_strong_trend_threshold": 32.0,
        "volatility_high_atr_pct": 3.0,
        "volatility_low_atr_pct": 1.0,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "XAUUSD": {
        "adx_trend_threshold": 20.0,
        "adx_strong_trend_threshold": 28.0,
        "volatility_high_atr_pct": 1.8,   # Gold has lower % ATR
        "volatility_low_atr_pct": 0.6,
        "hysteresis_bars": 2,
        "is_primary": True
    },
    "SOLUSD": {
        "adx_trend_threshold": 25.0,      # Higher altcoin volatility
        "adx_strong_trend_threshold": 35.0,
        "volatility_high_atr_pct": 4.5,
        "volatility_low_atr_pct": 1.5,
        "hysteresis_bars": 2,
        "is_primary": False
    },
    "XRPUSD": {
        "adx_trend_threshold": 24.0,
        "adx_strong_trend_threshold": 34.0,
        "volatility_high_atr_pct": 4.0,
        "volatility_low_atr_pct": 1.2,
        "hysteresis_bars": 2,
        "is_primary": False
    }
}
```

---

## 7. Explainable Confidence Calibration Model

The `confidence_score` (0 to 100) measures **empirical alignment**, not probability of winning:

$$\text{Confidence Score} = \text{Base} (20) + C_{\text{MTF}} (30) + C_{\text{ADX}} (25) + C_{\text{Structure}} (15) + C_{\text{Quality}} (10) - \text{Penalties}$$

- **Multi-Timeframe Agreement (+30 pts):** Awarded when 1H, 15M, and 5M share identical directional alignment.
- **Trend Strength (+25 pts):** Awarded when ADX $\ge \text{Threshold}_{\text{strong}}$ with clean DI separation.
- **Structural Confirmation (+15 pts):** Awarded when swing pivot structure matches EMA slope.
- **Data Freshness & Integrity (+10 pts):** Awarded when feeds pass pre-flight checks without lag.
- **Conflict Deductions (-25 pts):** Subtracted when 15M or 5M contradicts 1H.
- **Provisional State Deductions (-15 pts):** Subtracted during unconfirmed hysteresis periods.

---

## 8. Public Interface & Schema Specifications

The upgraded Agent 1 outputs a complete, backward-compatible payload:

```python
{
    "symbol": "BTCUSD",
    "regime": "STRONG_UPTREND",
    "directional_bias": "BULLISH",
    "trend_strength": "STRONG",
    "volatility_state": "NORMAL",
    "confidence_score": 88,
    "timeframe_analysis": {
        "1h": {"direction": "BULLISH", "adx": 34.2, "volatility": "NORMAL", "ema50": 68500.0, "ema200": 66200.0},
        "15m": {"trend": "BULLISH", "structure": "BULLISH_BOS", "rsi": 58.4},
        "5m": {"momentum": "BULLISH_ALIGNED", "rsi": 54.2}
    },
    "regime_transition": {
        "transition_detected": False,
        "transition_type": "NONE",
        "prior_regime": "STRONG_UPTREND",
        "hysteresis_confirmed": True
    },
    "supporting_evidence": [
        "1H Price ($70,000.00) above EMA50 ($68,500.00) and EMA200 ($66,200.00)",
        "ADX(14) is 34.2 (Strong Trend) with +DI > -DI",
        "15M structural trend confirms Higher Highs and Higher Lows",
        "Multi-timeframe 1H and 15M alignment verified"
    ],
    "conflicting_evidence": [],
    "data_timestamp": 1700000000,
    "is_provisional": False,
    "reason": "Strong 1H/15M bullish trend alignment with ADX 34.2 and confirmed structural higher highs.",
    "status": "CONFIRMED",
    # Preserved backward-compatible keys consumed by downstream agents:
    "current_price": 70000.0,
    "spread_pct": 0.02,
    "atr_14": 400.0,
    "atr_pct": 0.57,
    "vwap": 69800.0,
    "vwap_analysis": {...},
    "liquidity": {...},
    "fvg": {...},
    "volume_profile": {...},
    "cvd": {...},
    "order_book_imbalance": {...},
    "macro_15m": {...},
    "macro_4h": {...},
    "macro_daily": {...},
    "macro_weekly": {...},
    "_raw_candles_15m": {...},
    "_raw_candles_1h": {...},
    "high_probability_setup": {...}
}
```

---

## 9. Conclusion

The upgraded **Regime Analyst (Agent 1)** provides a robust, mathematically sound, anti-whipsaw foundation for the Delta Exchange trading bot. It eliminates lookahead bias, respects the multi-timeframe hierarchy, provides calibrated confidence metrics, and gives Agent 4 (Strategy Agent) reliable, noise-filtered market context.

