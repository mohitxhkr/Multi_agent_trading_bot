"""
Agent 3: Alpha & Strategy Generator.
Evaluates technical regime insights from Agent 1 and generates high-conviction trade setups
with explicit Entry, ATR-calibrated Stop Loss, Take Profit targets, VWAP alignment,
order-book spread filters, setup expiration timestamps, and strict hard veto separation.
"""

from typing import Dict, Any, List, Optional
import time
import logging
from multiagent_team.adaptive_learning import AdaptiveLearningEngine

logger = logging.getLogger("strategy-agent")


class StrategyAgent:
    def __init__(self, target_rr_ratio: float = 2.5, max_allowed_spread_pct: float = 0.15):
        self.target_rr_ratio = target_rr_ratio
        self.max_allowed_spread_pct = max_allowed_spread_pct
        self.adaptive_learner = AdaptiveLearningEngine()

    def evaluate_setup(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single symbol analysis and generate a trade proposal ONLY if high-probability edge exists.
        Separates Hard Rejection Gates from Strategy Scoring.
        """
        symbol = analysis.get("symbol")
        hp_setup = analysis.get("high_probability_setup")

        if not hp_setup or not hp_setup.get("qualified"):
            return None

        # -------------------------------------------------------------
        # 1. Hard Rejection Gates (Vetoes)
        # -------------------------------------------------------------
        # Hard Veto A: Major economic news / abnormal volatility spike
        if analysis.get("news_blocked"):
            logger.warning(f"StrategyAgent VETO on {symbol}: {analysis.get('news_reason')}")
            return None

        # Hard Veto B: Excessive bid-ask spread / illiquid book
        spread_pct = float(analysis.get("spread_pct") or 0.0)
        if spread_pct > self.max_allowed_spread_pct:
            logger.warning(f"StrategyAgent VETO on {symbol}: Spread {spread_pct}% exceeds max allowed {self.max_allowed_spread_pct}%")
            return None

        # Hard Veto C: Extreme entry price deviation
        current_price = float(analysis.get("current_price") or 0.0)
        entry = float(hp_setup.get("entry_price") or current_price)
        if entry > 0 and current_price > 0:
            price_deviation_pct = abs(current_price - entry) / entry * 100.0
            if price_deviation_pct > 0.50:
                logger.warning(f"StrategyAgent VETO on {symbol}: Price has drifted {price_deviation_pct:.2f}% from optimal entry ${entry:.2f}")
                return None

        side = hp_setup.get("side")
        sl = float(hp_setup.get("stop_loss_price") or 0.0)
        tp = float(hp_setup.get("take_profit_price") or 0.0)
        score = int(hp_setup.get("score") or 70)
        thesis = hp_setup.get("thesis", "High probability edge verified.")
        macro_4h = analysis.get("macro_4h", {})
        macro_daily = analysis.get("macro_daily", {})
        macro_weekly = analysis.get("macro_weekly", {})
        macro_monthly = analysis.get("macro_monthly", {})
        macro_15m = analysis.get("macro_15m", {})
        liq = analysis.get("liquidity", {})

        # Structural Invalidation Stop Loss & Asymmetric R:R Calibration (Minimum Risk, Maximum Profit)
        # CRITICAL: Reject setups with missing or invalid structural stops instead of generating arbitrary stops
        if sl <= 0 or entry <= 0 or sl == entry:
            logger.warning(f"StrategyAgent VETO on {symbol}: Missing or invalid structural stop loss (${sl:.4f}). Arbitrary stops prohibited.")
            return None

        # Verify stop loss orientation
        if side == "buy" and sl >= entry:
            logger.warning(f"StrategyAgent VETO on {symbol}: Structural stop loss (${sl:.4f}) is above or at entry (${entry:.4f}) for buy order.")
            return None
        elif side == "sell" and sl <= entry:
            logger.warning(f"StrategyAgent VETO on {symbol}: Structural stop loss (${sl:.4f}) is below or at entry (${entry:.4f}) for sell order.")
            return None

        stop_distance = abs(entry - sl)
        planned_rr = abs(tp - entry) / stop_distance if stop_distance > 0 else 0.0

        # ATR Volatility Stop Calibration & Validation
        atr_15m = float(macro_15m.get("atr_14") or hp_setup.get("atr_14") or analysis.get("atr_14") or 0.0)
        atr_multiple = round(stop_distance / atr_15m, 2) if atr_15m > 0 else 1.0

        if atr_15m > 0:
            # Hard Veto 1: Sub-ATR micro-stop (vulnerable to normal market noise)
            if atr_multiple < 0.40:
                logger.warning(
                    f"StrategyAgent VETO on {symbol}: Stop loss distance (${stop_distance:.2f}) is only "
                    f"{atr_multiple:.2f}x ATR (< 0.40x ATR of ${atr_15m:.2f}). Highly vulnerable to noise stop-outs."
                )
                return None

            # Hard Veto 2: Excessively loose stop (inefficient capital allocation)
            if atr_multiple > 3.0:
                logger.warning(
                    f"StrategyAgent VETO on {symbol}: Stop loss distance (${stop_distance:.2f}) is "
                    f"{atr_multiple:.2f}x ATR (> 3.0x ATR of ${atr_15m:.2f}). Exceeds acceptable volatility risk bounds."
                )
                return None

        # Enforce minimum R:R ratio
        if planned_rr < self.target_rr_ratio or tp <= 0:
            tp = round(entry + (self.target_rr_ratio * stop_distance), 4) if side == "buy" else round(entry - (self.target_rr_ratio * stop_distance), 4)
            planned_rr = abs(tp - entry) / stop_distance

        if planned_rr < 2.2:
            logger.warning(f"StrategyAgent VETO on {symbol}: Planned R:R ({planned_rr:.2f}:1) is below 2.2:1 minimum threshold.")
            return None

        # -------------------------------------------------------------
        # 2. Strategy Confluence Scoring
        # -------------------------------------------------------------
        is_primary = any(p in (symbol or "").upper() for p in ["BTC", "ETH", "XAU", "GOLD"])
        priority_tag = "PRIMARY" if is_primary else "SECONDARY"
        adjusted_score = score + (10 if is_primary else 0)

        # ATR Stop Calibration Edge: Award bonus points for optimal 0.70x - 1.50x ATR buffer
        atr_boost = 0
        if 0.70 <= atr_multiple <= 1.50:
            atr_boost += 4
            thesis = f"🛡️ [OPTIMAL {atr_multiple:.1f}x ATR STOP] {thesis}"
        elif atr_multiple < 0.50:
            atr_boost -= 4

        adjusted_score += atr_boost

        # VWAP Institutional Level & Standard Deviation Band Alignment
        vwap_val = float(analysis.get("vwap") or 0.0)
        vwap_info = analysis.get("vwap_analysis") or {}
        v_stance = vwap_info.get("stance", "AT_VWAP" if (vwap_val > 0 and abs(current_price - vwap_val)/vwap_val <= 0.002) else ("ABOVE_VWAP" if current_price > vwap_val else "BELOW_VWAP"))
        v_band = vwap_info.get("band_location", "FAIR_VALUE_CORE")
        v_slope = vwap_info.get("slope", "FLAT")

        vwap_boost = 0
        if vwap_val > 0:
            if side == "buy":
                if v_stance in ("ABOVE_VWAP", "AT_VWAP"):
                    vwap_boost += 5
                else:
                    vwap_boost -= 5  # Fighting immediate VWAP gravity

                if v_band in ("FAIR_VALUE_CORE", "DISCOUNT_BAND") and v_slope == "RISING_BULLISH":
                    vwap_boost += 4  # Institutional pullback entry into rising VWAP
                    thesis = f"💎 [INSTITUTIONAL VWAP ACCUMULATION] {thesis}"
                elif v_band == "OVERBOUGHT_EXTENSION":
                    vwap_boost -= 8  # Chasing overextended above +2 sigma band

            elif side == "sell":
                if v_stance in ("BELOW_VWAP", "AT_VWAP"):
                    vwap_boost += 5
                else:
                    vwap_boost -= 5  # Fighting immediate VWAP gravity

                if v_band in ("FAIR_VALUE_CORE", "PREMIUM_BAND") and v_slope == "FALLING_BEARISH":
                    vwap_boost += 4  # Institutional rejection from falling VWAP
                    thesis = f"💎 [INSTITUTIONAL VWAP DISTRIBUTION] {thesis}"
                elif v_band == "OVERSOLD_CAPITULATION":
                    vwap_boost -= 8  # Shorting into oversold exhaustion below -2 sigma band

        adjusted_score += vwap_boost

        # MACD Multi-Timeframe Momentum Confluence
        macd_1h = analysis.get("macd", {})
        macro_15m = analysis.get("macro_15m", {})
        macd_15m = macro_15m.get("macd", {}) if macro_15m else macd_1h

        m15_cross = macd_15m.get("crossover", "NONE")
        m15_phase = macd_15m.get("momentum_phase", "NEUTRAL")
        m15_hist = float(macd_15m.get("histogram") or 0.0)
        m1h_bias = macd_1h.get("bias", "NEUTRAL")

        macd_boost = 0
        if side == "buy":
            if m15_cross in ("BULLISH_CROSS", "BULLISH_ALIGNED") or m15_phase == "BULLISH_EXPANSION":
                macd_boost += 6
                thesis = f"📈 [MACD BULLISH MOMENTUM] {thesis}"
            elif m15_hist > 0 or "BULLISH" in m1h_bias:
                macd_boost += 3
            elif m15_phase == "BEARISH_EXPANSION" and m15_hist < 0:
                macd_boost -= 6  # Buying against expanding bearish MACD
        elif side == "sell":
            if m15_cross in ("BEARISH_CROSS", "BEARISH_ALIGNED") or m15_phase == "BEARISH_EXPANSION":
                macd_boost += 6
                thesis = f"📉 [MACD BEARISH MOMENTUM] {thesis}"
            elif m15_hist < 0 or "BEARISH" in m1h_bias:
                macd_boost += 3
            elif m15_phase == "BULLISH_EXPANSION" and m15_hist > 0:
                macd_boost -= 6  # Shorting against expanding bullish MACD

        adjusted_score += macd_boost

        # SMC Liquidity Pool & Sweep Confluence
        liq_structure = liq.get("liquidity_structure", "BALANCED_LIQUIDITY_CORE")
        sweep_type = liq.get("sweep_type")
        mss_confirmed = liq.get("mss_confirmed", False)
        nearest_bsl = float(liq.get("nearest_bsl") or 0.0)
        nearest_ssl = float(liq.get("nearest_ssl") or 0.0)
        bsl_dist_pct = liq.get("bsl_distance_pct")
        ssl_dist_pct = liq.get("ssl_distance_pct")

        liq_boost = 0
        if side == "buy":
            if sweep_type == "BULLISH_SSL_SWEEP":
                if mss_confirmed or liq_structure == "SWEEP_MSS_CONFIRMED":
                    liq_boost += 8
                    thesis = f"💧 [BULLISH SSL SWEEP + MSS CONFIRMED] {thesis}"
                else:
                    liq_boost += 4
                    thesis = f"💧 [BULLISH SSL SWEEP] {thesis}"
            if nearest_bsl > entry:
                liq_boost += 3
            if liq_structure == "TESTING_BSL_LIQUIDITY":
                liq_boost -= 4
        elif side == "sell":
            if sweep_type == "BEARISH_BSL_SWEEP":
                if mss_confirmed or liq_structure == "SWEEP_MSS_CONFIRMED":
                    liq_boost += 8
                    thesis = f"💧 [BEARISH BSL SWEEP + MSS CONFIRMED] {thesis}"
                else:
                    liq_boost += 4
                    thesis = f"💧 [BEARISH BSL SWEEP] {thesis}"
            if nearest_ssl > 0 and nearest_ssl < entry:
                liq_boost += 3
            if liq_structure == "TESTING_SSL_LIQUIDITY":
                liq_boost -= 4

        adjusted_score += liq_boost

        # Smart Money Concepts (SMC) Fair Value Gap (FVG) Confluence
        fvg_1h = analysis.get("fvg", {})
        macro_15m = analysis.get("macro_15m", {})
        fvg_15m = macro_15m.get("fvg", {}) if macro_15m else {}
        fvg_data = fvg_15m if fvg_15m.get("retest_active") else fvg_1h

        retest_type = fvg_data.get("retest_type", "NONE")
        ce_tested = fvg_data.get("ce_tested", False)
        wick_rejection = fvg_data.get("wick_rejection", False)
        nearest_bullish_fvg = fvg_data.get("nearest_bullish_fvg")
        nearest_bearish_fvg = fvg_data.get("nearest_bearish_fvg")
        bull_fvg_dist = fvg_data.get("bullish_fvg_distance_pct")
        bear_fvg_dist = fvg_data.get("bearish_fvg_distance_pct")

        fvg_boost = 0
        if side == "buy":
            if retest_type == "BULLISH_FVG_RETEST":
                if ce_tested and wick_rejection:
                    fvg_boost += 10
                    thesis = f"🔥 [BULLISH FVG CE RETEST + WICK REJECTION] {thesis}"
                elif ce_tested:
                    fvg_boost += 8
                    thesis = f"🔥 [BULLISH FVG CE RETEST] {thesis}"
                else:
                    fvg_boost += 5
                    thesis = f"🔥 [BULLISH FVG BOUNDARY RETEST] {thesis}"
            # Overhead unmitigated Bearish FVG penalty (buying directly into supply)
            if nearest_bearish_fvg and bear_fvg_dist is not None and bear_fvg_dist <= 0.35:
                fvg_boost -= 6
                thesis = f"⚠️ [OVERHEAD BEARISH FVG SUPPLY NEARBY] {thesis}"

        elif side == "sell":
            if retest_type == "BEARISH_FVG_RETEST":
                if ce_tested and wick_rejection:
                    fvg_boost += 10
                    thesis = f"🔥 [BEARISH FVG CE RETEST + WICK REJECTION] {thesis}"
                elif ce_tested:
                    fvg_boost += 8
                    thesis = f"🔥 [BEARISH FVG CE RETEST] {thesis}"
                else:
                    fvg_boost += 5
                    thesis = f"🔥 [BEARISH FVG BOUNDARY RETEST] {thesis}"
            # Underlying unmitigated Bullish FVG penalty (shorting directly into demand)
            if nearest_bullish_fvg and bull_fvg_dist is not None and bull_fvg_dist <= 0.35:
                fvg_boost -= 6
                thesis = f"⚠️ [SUPPORT BULLISH FVG DEMAND NEARBY] {thesis}"

        adjusted_score += fvg_boost

        # -------------------------------------------------------------
        # Institutional Order Flow Confluence (Volume Profile, CVD & OBI)
        # -------------------------------------------------------------
        vp_1h = analysis.get("volume_profile", {})
        cvd_1h = analysis.get("cvd", {})
        obi_1h = analysis.get("order_book_imbalance", {})

        vp_15m = macro_15m.get("volume_profile", {}) if macro_15m else {}
        cvd_15m = macro_15m.get("cvd", {}) if macro_15m else {}
        obi_15m = macro_15m.get("order_book_imbalance", {}) if macro_15m else {}

        active_vp = vp_15m if vp_15m.get("poc", 0) > 0 else vp_1h
        active_cvd = cvd_15m if cvd_15m.get("current_cvd", 0) != 0 else cvd_1h
        active_obi = obi_15m if obi_15m.get("obi_ratio", 0) != 0 else obi_1h

        cvd_div = active_cvd.get("divergence", "NONE")
        cvd_trend = active_cvd.get("cvd_trend", "FLAT_NEUTRAL")
        obi_status = active_obi.get("imbalance_status", "BALANCED_ORDER_BOOK")
        obi_ratio = float(active_obi.get("obi_ratio") or 0.0)
        vp_stance = active_vp.get("stance", "INSIDE_VA")
        vp_poc = float(active_vp.get("poc") or 0.0)
        vp_vah = float(active_vp.get("vah") or 0.0)
        vp_val = float(active_vp.get("val") or 0.0)

        order_flow_boost = 0
        if side == "buy":
            # 1. Bullish CVD Absorption Divergence
            if cvd_div == "BULLISH_ABSORPTION_DIV":
                order_flow_boost += 10
                thesis = f"🌊 [BULLISH CVD ABSORPTION DIVERGENCE] {thesis}"
            elif cvd_trend == "RISING_ACCUMULATION":
                order_flow_boost += 5
                thesis = f"📈 [CVD ACCUMULATION DELTA] {thesis}"
            elif cvd_div == "BEARISH_EXHAUSTION_DIV":
                order_flow_boost -= 8  # Chasing against bearish exhaustion divergence
                thesis = f"⚠️ [BEARISH CVD DIVERGENCE WARNING] {thesis}"

            # 2. Order Book Imbalance (Resting Bid Support)
            if obi_status == "HEAVY_BID_IMBALANCE" or obi_ratio >= 0.25:
                order_flow_boost += 6
                thesis = f"🧱 [HEAVY BID BOOK SUPPORT (OBI {obi_ratio:+.2f})] {thesis}"
            elif obi_status == "HEAVY_ASK_IMBALANCE" or obi_ratio <= -0.25:
                order_flow_boost -= 7  # Buying directly into thick ask resistance wall
                thesis = f"⚠️ [HEAVY ASK WALL RESISTANCE (OBI {obi_ratio:+.2f})] {thesis}"

            # 3. Volume Profile Value Area Stance
            if vp_stance in ("INSIDE_VA", "ABOVE_VAH") and entry >= vp_val:
                order_flow_boost += 4  # Holding value area support / POC
            elif vp_stance == "BELOW_VAL" and entry < vp_val * 0.99:
                order_flow_boost -= 4  # Trapped below Value Area Low

        elif side == "sell":
            # 1. Bearish CVD Exhaustion Divergence
            if cvd_div == "BEARISH_EXHAUSTION_DIV":
                order_flow_boost += 10
                thesis = f"🌊 [BEARISH CVD EXHAUSTION DIVERGENCE] {thesis}"
            elif cvd_trend == "FALLING_DISTRIBUTION":
                order_flow_boost += 5
                thesis = f"📉 [CVD DISTRIBUTION DELTA] {thesis}"
            elif cvd_div == "BULLISH_ABSORPTION_DIV":
                order_flow_boost -= 8  # Shorting against bullish absorption divergence
                thesis = f"⚠️ [BULLISH CVD DIVERGENCE WARNING] {thesis}"

            # 2. Order Book Imbalance (Resting Ask Resistance)
            if obi_status == "HEAVY_ASK_IMBALANCE" or obi_ratio <= -0.25:
                order_flow_boost += 6
                thesis = f"🧱 [HEAVY ASK BOOK RESISTANCE (OBI {obi_ratio:+.2f})] {thesis}"
            elif obi_status == "HEAVY_BID_IMBALANCE" or obi_ratio >= 0.25:
                order_flow_boost -= 7  # Shorting directly into thick bid support wall
                thesis = f"⚠️ [HEAVY BID WALL SUPPORT (OBI {obi_ratio:+.2f})] {thesis}"

            # 3. Volume Profile Value Area Stance
            if vp_stance in ("INSIDE_VA", "BELOW_VAL") and entry <= vp_vah:
                order_flow_boost += 4  # Respecting value area distribution / POC
            elif vp_stance == "ABOVE_VAH" and entry > vp_vah * 1.01:
                order_flow_boost -= 4  # Shorting above Value Area High

        adjusted_score += order_flow_boost

        # Adaptive Learning Check
        raw_strat = hp_setup.get("strategy") or f"Institutional_SMC_{priority_tag}_{side.upper()}"
        confluence_summary = {
            "macro_4h": macro_4h.get("regime", "NEUTRAL"),
            "macro_daily": macro_daily.get("regime", "NEUTRAL")
        }
        pat_check = self.adaptive_learner.get_pattern_adjustment(
            symbol=symbol,
            side=side,
            strategy=raw_strat,
            confluence=confluence_summary
        )

        if not pat_check.get("can_trade", True):
            logger.warning(f"StrategyAgent VETO: Pattern blacklisted: {pat_check.get('reason')}")
            return None

        pat_adj = pat_check.get("score_adjustment", 0)
        adjusted_score += pat_adj
        if pat_adj > 0:
            thesis = f"⚡ [REINFORCED PATTERN +{pat_adj}pts] {thesis}"
        elif pat_adj < 0:
            thesis = f"⚠️ [PENALIZED PATTERN {pat_adj}pts] {thesis}"

        # Strict Sniper Quality Floor: 85 / 100 for Primary (BTC, ETH, XAU), 90 / 100 for Secondary
        # Enforces 'Take less trades, but more accurate for maximum profit'
        min_threshold = 85 if is_primary else 90
        if adjusted_score < min_threshold:
            return None

        formatted_thesis = f"🌟 [PRIMARY FOCUS ASSET] {thesis}" if is_primary else f"⚪ [SECONDARY ASSET] {thesis}"
        now_ts = time.time()
        expires_at = now_ts + 3600  # Valid for 60 minutes

        return {
            "symbol": symbol,
            "strategy_name": f"{raw_strat}_{adjusted_score}pts",
            "side": side,
            "entry_price": entry,
            "stop_loss_price": sl,
            "take_profit_price": tp,
            "stop_distance_pct": round((stop_distance / entry) * 100, 2),
            "planned_rr_ratio": round(abs(tp - entry) / stop_distance, 2),
            "score": adjusted_score,
            "is_primary": is_primary,
            "priority_tier": 1 if is_primary else 2,
            "thesis": formatted_thesis,
            "expires_at": expires_at,
            "created_at": now_ts,
            "vwap": vwap_val,
            "spread_pct": spread_pct,
            "atr_14": atr_15m,
            "atr_stop_multiple": atr_multiple,
            "fvg_profile": {
                "retest_type": retest_type,
                "ce_tested": ce_tested,
                "wick_rejection": wick_rejection,
                "active_bullish_count": fvg_data.get("active_bullish_count", 0),
                "active_bearish_count": fvg_data.get("active_bearish_count", 0),
                "nearest_bullish_fvg": nearest_bullish_fvg,
                "nearest_bearish_fvg": nearest_bearish_fvg,
                "active_retest_fvg": fvg_data.get("active_retest_fvg")
            },
            "order_flow_profile": {
                "volume_profile": {
                    "poc": vp_poc,
                    "vah": vp_vah,
                    "val": vp_val,
                    "stance": vp_stance
                },
                "cvd": {
                    "current_cvd": active_cvd.get("current_cvd", 0.0),
                    "cvd_trend": cvd_trend,
                    "divergence": cvd_div,
                    "cvd_slope": active_cvd.get("cvd_slope", 0.0)
                },
                "order_book_imbalance": {
                    "obi_ratio": obi_ratio,
                    "imbalance_status": obi_status,
                    "depth_ratio": active_obi.get("depth_ratio", 1.0),
                    "bid_depth": active_obi.get("bid_depth", 0.0),
                    "ask_depth": active_obi.get("ask_depth", 0.0),
                    "bid_wall_detected": active_obi.get("bid_wall_detected", False),
                    "bid_wall_price": active_obi.get("bid_wall_price"),
                    "ask_wall_detected": active_obi.get("ask_wall_detected", False),
                    "ask_wall_price": active_obi.get("ask_wall_price")
                }
            },
            "confluence": {
                "execution_15m": f"{macro_15m.get('regime', 'NEUTRAL')} (RSI: {macro_15m.get('rsi_14', 'N/A')} | ATR: {macro_15m.get('atr_14', 'N/A')})",
                "monthly": f"{macro_monthly.get('regime', 'NEUTRAL')} (M-Open: ${macro_monthly.get('monthly_open', 'N/A')})",
                "weekly": f"{macro_weekly.get('regime', 'NEUTRAL')} (W-RSI: {macro_weekly.get('rsi_14', 'N/A')})",
                "daily": f"{macro_daily.get('regime', 'NEUTRAL')} (EMA21: ${macro_daily.get('ema_21', 'N/A')} | RSI: {macro_daily.get('rsi_14', 'N/A')})",
                "macro_4h": f"{macro_4h.get('regime', 'NEUTRAL')} (4H RSI: {macro_4h.get('rsi_14', 'N/A')})",
                "structure_detail": f"{liq.get('sweep_type', 'Structure Test')} | MSS: {'YES' if liq.get('mss_confirmed') else 'ALIGNED'}",
                "patterns_detail": f"Candle: {analysis.get('candlestick_pattern', 'Normal')} | Chart: {analysis.get('chart_pattern', 'Normal')} | Trendline: {analysis.get('trendline_direction', 'Aligned')}",
                "levels_detail": f"Support: ${analysis.get('support', 0):,.2f} | Resistance: ${analysis.get('resistance', 0):,.2f} | BSL: ${liq.get('nearest_bsl', 0):,.2f} | SSL: ${liq.get('nearest_ssl', 0):,.2f}",
                "volume_rsi": f"1H RSI: {analysis.get('rsi_14', 50.0)} | Vol: {'CONFIRMED' if liq.get('volume_confirmed') else 'NORMAL'}",
                "macd_detail": f"15m: {m15_cross} ({m15_phase}) | 1H: {m1h_bias}",
                "vwap_detail": f"${vwap_val:,.2f} ({v_stance} | {v_band} | {v_slope})",
                "liquidity_detail": f"BSL: ${nearest_bsl:,.2f} ({f'{bsl_dist_pct:+.2f}%' if bsl_dist_pct is not None else 'N/A'}) | SSL: ${nearest_ssl:,.2f} ({f'{ssl_dist_pct:+.2f}%' if ssl_dist_pct is not None else 'N/A'}) | State: {liq_structure} | Spread: {spread_pct:.3f}%",
                "atr_detail": f"15m ATR: ${atr_15m:,.2f} ({round(atr_15m/entry*100, 2) if entry > 0 else 0}%) | SL Multiple: {atr_multiple:.2f}x ATR",
                "fvg_detail": f"Retest: {retest_type} (CE: {'YES' if ce_tested else 'NO'} | Wick: {'YES' if wick_rejection else 'NO'}) | Bull FVG: ${nearest_bullish_fvg['gap_top']:,.2f} ({f'{bull_fvg_dist:.2f}%' if bull_fvg_dist is not None else 'N/A'})" if nearest_bullish_fvg else f"Retest: {retest_type} | Bear FVG: ${nearest_bearish_fvg['gap_bottom']:,.2f} ({f'{bear_fvg_dist:.2f}%' if bear_fvg_dist is not None else 'N/A'})" if nearest_bearish_fvg else f"Retest: {retest_type} | None",
                "order_flow_detail": f"VP POC: ${vp_poc:,.2f} ({vp_stance} | VAH: ${vp_vah:,.2f} | VAL: ${vp_val:,.2f}) | CVD: {cvd_trend} ({cvd_div}) | OBI: {obi_status} ({obi_ratio:+.2f} · Depth: {active_obi.get('depth_ratio', 1.0):.1f}x)"
            }
        }

    def find_best_candidates(self, scan_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan all symbols from RegimeAnalyst and return list of qualified setups.
        Primary assets (BTC, ETH, XAU) are prioritized first.
        """
        candidates = []
        symbols_data = scan_results.get("symbols_data", {})
        for sym, analysis in symbols_data.items():
            if not analysis.get("symbol"):
                analysis["symbol"] = sym
            setup = self.evaluate_setup(analysis)
            if setup:
                candidates.append(setup)
                
        # Rank by: Primary tier first, then Asymmetric Profit Ratio (planned R:R), then score
        candidates.sort(
            key=lambda s: (
                1 if s.get("is_primary") else 0,
                s.get("planned_rr_ratio", 0.0),
                s.get("score", 0)
            ),
            reverse=True
        )
        return candidates
