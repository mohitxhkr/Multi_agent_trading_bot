"""
Institutional Dark-Theme Candlestick Chart Generator for Delta Exchange.
Renders high-resolution candlestick charts overlaid with:
  - Breakout Resistance Ceilings (Green dashed line + badge)
  - Breakdown Support Floors (Red dashed line + badge)
  - Current Mark Price (Yellow solid line + badge)
  - Session VWAP (Cyan dotted line)
  - 21 EMA & 50 EMA Trend Ribbons
  - Trading Volume Subplot
"""

import os
import sys
import tempfile
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta

# Set headless Matplotlib configuration directory before importing
os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "delta_mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.lines as mlines
from matplotlib.gridspec import GridSpec

# Windows UTF-8 configuration
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

CHARTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


def calculate_ema_series(prices: List[float], period: int) -> List[float]:
    """Calculate EMA series for plotting."""
    if len(prices) < period:
        return [prices[-1]] * len(prices)
    k = 2.0 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(p * k + ema[-1] * (1.0 - k))
    # Pad beginning
    pad = [ema[0]] * (len(prices) - len(ema))
    return pad + ema


def generate_candlestick_chart(
    candles: Dict[str, Any],
    symbol: str,
    key_levels: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    max_bars: int = 50,
    timeframe_label: str = "15m"
) -> str:
    """
    Generate an institutional dark-theme candlestick chart and save to disk.

    Args:
        candles: Delta candle dict with 'o', 'h', 'l', 'c', 'v', 't'
        symbol: Asset symbol (e.g. BTCUSD, ETHUSD, XAUUSD)
        key_levels: Dict containing breakout_level, breakdown_level, vwap_price, etc.
        output_path: Optional custom file path to save PNG
        max_bars: Number of recent candles to render (default 50)
        timeframe_label: Chart resolution label for header (e.g. '15m' or '1H')

    Returns:
        Absolute file path of generated PNG chart
    """
    highs = candles.get("h", [])
    lows = candles.get("l", [])
    opens = candles.get("o", [])
    closes = candles.get("c", [])
    volumes = candles.get("v", [])
    timestamps = candles.get("t", [])

    n = len(closes)
    if n < 5:
        raise ValueError(f"Insufficient candles for {symbol} (only {n} bars available)")

    # Slice to most recent bars
    slice_idx = max(0, n - max_bars)
    h_s = [float(x) for x in highs[slice_idx:]]
    l_s = [float(x) for x in lows[slice_idx:]]
    o_s = [float(x) for x in opens[slice_idx:]]
    c_s = [float(x) for x in closes[slice_idx:]]
    v_s = [float(x) for x in volumes[slice_idx:]] if volumes else [1.0] * len(c_s)
    t_s = timestamps[slice_idx:] if timestamps else []

    bars_count = len(c_s)
    indices = list(range(bars_count))

    current_price = c_s[-1]
    ema21 = calculate_ema_series(c_s, min(21, bars_count))
    ema50 = calculate_ema_series(c_s, min(50, bars_count))

    # Extract Key Levels & Pre-Trade Action Plans
    kl = key_levels or {}
    breakout_level = float(kl.get("breakout_level") or 0.0)
    breakdown_level = float(kl.get("breakdown_level") or 0.0)
    vwap_price = float(kl.get("vwap_price") or 0.0)
    status_label = kl.get("status_label", "MARKET SCAN")
    bo_plan = kl.get("bullish_breakout_plan", {})
    bd_plan = kl.get("bearish_breakdown_plan", {})
    bullish_tp = float(bo_plan.get("take_profit_price") or 0.0)
    bullish_sl = float(bo_plan.get("stop_loss_price") or 0.0)
    bearish_tp = float(bd_plan.get("take_profit_price") or 0.0)
    bearish_sl = float(bd_plan.get("stop_loss_price") or 0.0)

    # Dark Theme Palette
    BG_COLOR = "#0F141C"        # Deep charcoal slate
    PANEL_COLOR = "#161D27"     # Card panel background
    GRID_COLOR = "#222D3D"      # Subtle grid lines
    TEXT_COLOR = "#E2E8F0"      # Off-white text
    MUTED_TEXT = "#8899A6"      # Muted grey
    BULL_COLOR = "#00C853"      # Emerald green
    BEAR_COLOR = "#FF3D00"      # Crimson red
    BREAKOUT_COLOR = "#00E676"  # Bright neon green
    BREAKDOWN_COLOR = "#FF1744" # Bright neon red
    MARK_COLOR = "#FFD600"      # Vivid gold
    VWAP_COLOR = "#00E5FF"      # Electric cyan

    # Create figure with 2 subplots (Price 80%, Volume 20%)
    fig = plt.figure(figsize=(12, 7), facecolor=BG_COLOR, dpi=150)
    gs = GridSpec(nrows=4, ncols=1, figure=fig, hspace=0.08)
    ax_price = fig.add_subplot(gs[0:3, 0])
    ax_vol = fig.add_subplot(gs[3, 0], sharex=ax_price)

    ax_price.set_facecolor(PANEL_COLOR)
    ax_vol.set_facecolor(PANEL_COLOR)

    # Plot Candlesticks
    candle_width = 0.55
    wick_width = 1.2

    for i in range(bars_count):
        o = o_s[i]
        c = c_s[i]
        h = h_s[i]
        l = l_s[i]
        is_bullish = c >= o
        color = BULL_COLOR if is_bullish else BEAR_COLOR

        # Upper & Lower Wicks
        ax_price.plot([i, i], [l, h], color=color, linewidth=wick_width, zorder=2)

        # Candle Body
        body_bottom = min(o, c)
        body_height = max(abs(c - o), current_price * 0.0004)  # Ensure non-zero height for dojis
        rect = patches.Rectangle(
            (i - candle_width / 2.0, body_bottom),
            candle_width,
            body_height,
            facecolor=color,
            edgecolor=color,
            linewidth=1.0,
            zorder=3
        )
        ax_price.add_patch(rect)

        # Volume Bar
        ax_vol.bar(i, v_s[i], color=color, width=candle_width, alpha=0.6, zorder=2)

    # Plot EMA lines
    ax_price.plot(indices, ema21, color="#FFA726", linewidth=1.3, label="EMA 21", alpha=0.85, zorder=4)
    ax_price.plot(indices, ema50, color="#AB47BC", linewidth=1.3, label="EMA 50", alpha=0.85, zorder=4)

    # Plot VWAP if valid
    if vwap_price > 0:
        ax_price.axhline(vwap_price, color=VWAP_COLOR, linestyle=":", linewidth=1.4, alpha=0.85, zorder=4)
        ax_price.text(
            bars_count - 1.2, vwap_price, f" VWAP ${vwap_price:,.2f}",
            color=VWAP_COLOR, fontsize=8, verticalalignment="center",
            bbox=dict(boxstyle="square,pad=0.2", facecolor=PANEL_COLOR, edgecolor=VWAP_COLOR, alpha=0.85),
            zorder=6
        )

    # Determine Directional Bias Badge (LONG / UP vs SHORT / DOWN)
    prox_status = kl.get("proximity_status", "")
    if "BREAKOUT" in str(status_label).upper() or prox_status == "TESTING_BREAKOUT":
        bias_text = "[PRE-TRADE INDICATION: UP]  ▲  GO LONG (BREAKOUT IMMINENT)"
        bias_bg = "#00C853"
        bias_fg = "#FFFFFF"
    elif "BREAKDOWN" in str(status_label).upper() or prox_status == "TESTING_BREAKDOWN":
        bias_text = "[PRE-TRADE INDICATION: DOWN]  ▼  GO SHORT (BREAKDOWN IMMINENT)"
        bias_bg = "#D50000"
        bias_fg = "#FFFFFF"
    else:
        bias_text = "[PRE-TRADE RADAR]  ▲ LONG ABOVE BREAKOUT  |  ▼ SHORT BELOW BREAKDOWN"
        bias_bg = "#1E293B"
        bias_fg = "#94A3B8"

    ax_price.text(
        0.5, 0.94, f"  {bias_text}  ",
        transform=ax_price.transAxes,
        color=bias_fg, fontsize=9.0, fontweight="bold", ha="center", va="top",
        bbox=dict(boxstyle="round,pad=0.35", facecolor=bias_bg, edgecolor="none", alpha=0.95),
        zorder=8
    )

    # Plot Breakout Level (LONG / UP Trigger)
    if breakout_level > 0:
        dist_bo = ((breakout_level - current_price) / current_price) * 100.0
        ax_price.axhline(breakout_level, color=BREAKOUT_COLOR, linestyle="--", linewidth=1.8, alpha=0.9, zorder=5)
        ax_price.text(
            1.0, breakout_level, f" ▲ BREAKOUT LEVEL: ${breakout_level:,.2f} (+{dist_bo:.2f}%) ➔ GO LONG (UP) ",
            color="#FFFFFF", fontsize=9, fontweight="bold", verticalalignment="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#00A844", edgecolor=BREAKOUT_COLOR, linewidth=1.2, alpha=0.95),
            zorder=6
        )

        # Plot Bullish Take-Profit (Target) if available
        if bullish_tp > 0:
            ax_price.axhline(bullish_tp, color="#00E676", linestyle=":", linewidth=1.2, alpha=0.75, zorder=4)
            ax_price.text(
                bars_count - 1.2, bullish_tp, f" [TP] LONG TARGET ${bullish_tp:,.2f} ",
                color="#00E676", fontsize=8, fontweight="bold", verticalalignment="center",
                bbox=dict(boxstyle="square,pad=0.2", facecolor=PANEL_COLOR, edgecolor="#00E676", alpha=0.85),
                zorder=6
            )

    # Plot Breakdown Level (SHORT / DOWN Trigger)
    if breakdown_level > 0:
        dist_bd = ((current_price - breakdown_level) / current_price) * 100.0
        ax_price.axhline(breakdown_level, color=BREAKDOWN_COLOR, linestyle="--", linewidth=1.8, alpha=0.9, zorder=5)
        ax_price.text(
            1.0, breakdown_level, f" ▼ BREAKDOWN LEVEL: ${breakdown_level:,.2f} (-{dist_bd:.2f}%) ➔ GO SHORT (DOWN) ",
            color="#FFFFFF", fontsize=9, fontweight="bold", verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#C62828", edgecolor=BREAKDOWN_COLOR, linewidth=1.2, alpha=0.95),
            zorder=6
        )

        # Plot Bearish Take-Profit (Target) if available
        if bearish_tp > 0:
            ax_price.axhline(bearish_tp, color="#FF1744", linestyle=":", linewidth=1.2, alpha=0.75, zorder=4)
            ax_price.text(
                bars_count - 1.2, bearish_tp, f" [TP] SHORT TARGET ${bearish_tp:,.2f} ",
                color="#FF1744", fontsize=8, fontweight="bold", verticalalignment="center",
                bbox=dict(boxstyle="square,pad=0.2", facecolor=PANEL_COLOR, edgecolor="#FF1744", alpha=0.85),
                zorder=6
            )

    # Plot Current Mark Price Line
    ax_price.axhline(current_price, color=MARK_COLOR, linestyle="-", linewidth=1.2, alpha=0.75, zorder=4)
    ax_price.text(
        bars_count - 1.2, current_price, f" ● MARK ${current_price:,.2f} ",
        color="#000000", fontsize=8.5, fontweight="bold", verticalalignment="center",
        bbox=dict(boxstyle="round,pad=0.25", facecolor=MARK_COLOR, edgecolor="none"),
        zorder=7
    )

    # Formatting Price Axis
    y_min = min(l_s)
    y_max = max(h_s)
    if breakout_level > 0:
        y_max = max(y_max, breakout_level * 1.002)
    if breakdown_level > 0:
        y_min = min(y_min, breakdown_level * 0.998)
    if bullish_tp > 0:
        y_max = max(y_max, bullish_tp * 1.002)
    if bearish_tp > 0:
        y_min = min(y_min, bearish_tp * 0.998)
    padding = (y_max - y_min) * 0.10
    ax_price.set_ylim(y_min - padding, y_max + padding)
    ax_price.set_xlim(-1, bars_count + 8)  # Extra right space for level labels & arrows

    # Directional Arrows on the Right Side
    arrow_x = bars_count + 3.5
    if breakout_level > 0:
        ax_price.annotate(
            "▲ UP\n(LONG)",
            xy=(arrow_x, breakout_level),
            xytext=(arrow_x, min(y_max - padding * 0.2, breakout_level + (y_max - y_min) * 0.14)),
            arrowprops=dict(facecolor="#00E676", edgecolor="#00E676", width=2.5, headwidth=8, headlength=7, shrink=0.08),
            color="#00E676", fontsize=8.5, fontweight="bold", ha="center", va="bottom", zorder=7
        )
    if breakdown_level > 0:
        ax_price.annotate(
            "▼ DOWN\n(SHORT)",
            xy=(arrow_x, breakdown_level),
            xytext=(arrow_x, max(y_min + padding * 0.2, breakdown_level - (y_max - y_min) * 0.14)),
            arrowprops=dict(facecolor="#FF1744", edgecolor="#FF1744", width=2.5, headwidth=8, headlength=7, shrink=0.08),
            color="#FF1744", fontsize=8.5, fontweight="bold", ha="center", va="top", zorder=7
        )

    # Grid & Spines
    for ax in [ax_price, ax_vol]:
        ax.grid(True, color=GRID_COLOR, linestyle="--", linewidth=0.6, alpha=0.7)
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)
        ax.tick_params(colors=MUTED_TEXT, labelsize=8)

    plt.setp(ax_price.get_xticklabels(), visible=False)

    # Format Volume Y-axis
    ax_vol.set_ylim(0, max(v_s) * 2.5 if v_s else 100)
    ax_vol.set_ylabel("VOL", color=MUTED_TEXT, fontsize=8, fontweight="bold")
    ax_vol.yaxis.set_label_position("right")
    ax_vol.yaxis.tick_right()

    # Format Price Y-axis
    ax_price.yaxis.set_label_position("right")
    ax_price.yaxis.tick_right()
    ax_price.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"${x:,.2f}" if x >= 1 else f"${x:,.4f}"))

    # Time X-axis labels
    if t_s:
        step = max(1, bars_count // 7)
        xticks = list(range(0, bars_count, step))
        xtick_labels = []
        ist_zone = timezone(timedelta(hours=5, minutes=30))
        for idx in xticks:
            ts = t_s[idx]
            dt = datetime.fromtimestamp(ts, tz=ist_zone)
            xtick_labels.append(dt.strftime("%H:%M"))
        ax_vol.set_xticks(xticks)
        ax_vol.set_xticklabels(xtick_labels, color=MUTED_TEXT, fontsize=8)

    # Header Titles
    sym_title = f"{symbol} (GOLD)" if "XAU" in symbol else symbol
    fig.suptitle(
        f"DELTA MULTI-AGENT QUANT SYSTEM  ·  {sym_title} ({timeframe_label.upper()})",
        color=TEXT_COLOR, fontsize=13, fontweight="bold", x=0.12, y=0.96, horizontalalignment="left"
    )

    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST")
    ax_price.set_title(
        f"Mark: ${current_price:,.2f}  |  Status: {status_label}  |  Generated: {now_ist}",
        color=MUTED_TEXT, fontsize=9, loc="left", pad=10
    )

    # Watermark Footer
    fig.text(
        0.5, 0.02,
        "⚡ Automated Real-Time Microstructure & Order Flow Engine  ·  Delta Exchange",
        color=MUTED_TEXT, fontsize=7.5, ha="center", alpha=0.6
    )

    # Determine Output Path
    if not output_path:
        output_path = os.path.join(CHARTS_DIR, f"{symbol.lower()}_candlestick_{timeframe_label}.png")

    fig.savefig(output_path, facecolor=BG_COLOR, edgecolor="none", bbox_inches="tight", dpi=150)
    plt.close(fig)

    return os.path.abspath(output_path)

