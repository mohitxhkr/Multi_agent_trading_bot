import os
import sys
from PIL import Image, ImageDraw, ImageFont

def generate_diagram():
    w, h = 2400, 1550
    img = Image.new("RGB", (w, h), color="#0d1117")
    d = ImageDraw.Draw(img)

    # Fonts
    font_dir = r"C:\Windows\Fonts"
    f_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 44)
    f_sub = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 22)
    f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
    
    f_card_h = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 23)
    f_card_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 15)
    f_sec_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 19)
    f_box_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 17)
    f_box_sub = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 15)
    f_body = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 16)
    f_body_b = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 16)
    f_foot_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 19)
    f_foot_body = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 14)

    # 1. Header Banner
    d.rounded_rectangle([(60, 40), (w - 60, 160)], radius=18, fill="#161b22", outline="#30363d", width=2)
    # Cyan accent pill on left of header
    d.rounded_rectangle([(60, 40), (72, 160)], radius=4, fill="#06b6d4")
    
    d.text((95, 62), "⚡ DELTA EXCHANGE MULTI-AGENT QUANTITATIVE TRADING WORKFLOW", fill="#ffffff", font=f_title)
    d.text((95, 118), "11-Agent Architecture • Deterministic Safety Controller (14 Invariants) • Multi-Horizon Circuit Breakers • Authoritative SQLite Journal", fill="#8b949e", font=f_sub)

    # Top Status Pill
    d.rounded_rectangle([(w - 430, 68), (w - 80, 132)], radius=12, fill="#1f2937", outline="#10b981", width=2)
    d.ellipse([(w - 405, 93), (w - 387, 111)], fill="#10b981")
    d.text((w - 375, 88), "HARDENED PROD V2.0", fill="#ffffff", font=f_pill)

    # Card layout geometry
    card_w = 720
    card_h = 420
    col1_x = 60
    col2_x = col1_x + card_w + 30
    col3_x = col2_x + card_w + 30
    
    row1_y = 190
    row2_y = row1_y + card_h + 30

    def draw_card_base(x, y, title, badge_text, border_color, header_bg, badge_bg):
        # Card Body
        d.rounded_rectangle([(x, y), (x + card_w, y + card_h)], radius=16, fill="#161b22", outline=border_color, width=2)
        # Card Header
        d.rounded_rectangle([(x, y), (x + card_w, y + 60)], radius=16, fill=header_bg)
        d.rectangle([(x, y + 35), (x + card_w, y + 60)], fill=header_bg)
        d.text((x + 25, y + 18), title, fill="#ffffff", font=f_card_h)
        # Badge
        d.rounded_rectangle([(x + card_w - 185, y + 14), (x + card_w - 20, y + 46)], radius=8, fill=badge_bg)
        d.text((x + card_w - 172, y + 20), badge_text, fill="#ffffff", font=f_card_tag)

    # -------------------------------------------------------------
    # CARD 1: AGENTS 1-3 (REGIME ANALYST, NEWS SENTIMENT & EXPOSURE)
    # -------------------------------------------------------------
    draw_card_base(col1_x, row1_y, "🔍 AGENTS 1-3: REGIME, NEWS & EXPOSURE", "INTELLIGENCE", "#388bfd", "#1e3a5f", "#0284c7")
    cy = row1_y + 80
    d.text((col1_x + 25, cy), "Macro Order Flow, Sentiment & Market Posture Engine:", fill="#38bdf8", font=f_sec_title)
    
    box_y = cy + 30
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Agent 1 (Regime & Breadth):", fill="#38bdf8", font=f_box_title)
    d.text((col1_x + 290, box_y + 13), "6-TF EMA stacks, VWAP & Watchlist % > EMA20", fill="#c9d1d9", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Agent 2 (News & Sentiment Engine):", fill="#38bdf8", font=f_box_title)
    d.text((col1_x + 335, box_y + 13), "CoinDesk, CoinTelegraph, Decrypt & F&G Index + Telegram Alerts", fill="#c9d1d9", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Agent 3 (Exposure Coach):", fill="#38bdf8", font=f_box_title)
    d.text((col1_x + 265, box_y + 13), "Market Posture (AGGRESSIVE / DEFENSIVE / CASH) + Funding Skew", fill="#c9d1d9", font=f_box_sub)

    by = box_y + 55
    d.text((col1_x + 25, by), "• Pre-Flight Data Validation: Discards stale data (>60s) or missing candle gaps.", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 26), "• Cash Priority Gate: If Market Health < 32/100, blocks ALL trades (Cash 100%).", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 52), "• News Catalyst Classifier: Tags REGULATORY, MACRO_FED, EXPLOITS with impact.", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 78), "• Crowded Funding Shield: Rejects long entries when funding rate > +0.03%.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 2: AGENT 4 (STRATEGY GENERATOR)
    # -------------------------------------------------------------
    draw_card_base(col2_x, row1_y, "💡 AGENT 4: ALPHA STRATEGY GENERATOR", "ALPHA ENGINE", "#8b5cf6", "#3b1d6e", "#7c3aed")
    cy = row1_y + 80
    d.text((col2_x + 25, cy), "Candidate Setup Edge & Structural Invalidation:", fill="#c084fc", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Score Threshold: >= 85 / 100", fill="#c084fc", font=f_box_title)
    d.text((col2_x + 310, box_y + 13), "High-conviction sniper execution (Primary vs Secondary)", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Planned Reward-to-Risk: >= 2.20 : 1", fill="#c084fc", font=f_box_title)
    d.text((col2_x + 360, box_y + 13), "Strict asymmetric payout enforcement", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Structural Stop Loss:", fill="#c084fc", font=f_box_title)
    d.text((col2_x + 230, box_y + 13), "Anchored strictly to swing liquidity; synthetic stops prohibited", fill="#8b949e", font=f_box_sub)

    by = box_y + 55
    d.text((col2_x + 25, by), "• Tier 1 Focus Assets: BTCUSD, ETHUSD, XAUUSD (Institutional Deep Liquidity).", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 26), "• VWAP Institutional Gravity: +5/-5 alignment with intraday volume anchors.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 52), "• Spread & Slippage Filter: Bid/Ask spread strictly capped at <= 0.15%.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 78), "• Proposal TTL: Time-to-live expiration at 60 minutes prevents stale orders.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 3: AGENT 5 (TIME MACHINE PROBABILITY ENGINE)
    # -------------------------------------------------------------
    draw_card_base(col3_x, row1_y, "⏳ AGENT 5: TIME MACHINE SIMULATOR", "WALK-FORWARD OOS", "#f59e0b", "#522b07", "#d97706")
    cy = row1_y + 80
    d.text((col3_x + 25, cy), "Walk-Forward Simulation & Wilson 95% Confidence Interval:", fill="#fbbf24", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "Zero Synthetic Stats Mandate:", fill="#fbbf24", font=f_box_title)
    d.text((col3_x + 300, box_y + 13), "Returns INSUFFICIENT_DATA or INSUFFICIENT_SAMPLE", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "Walk-Forward OOS Split:", fill="#fbbf24", font=f_box_title)
    d.text((col3_x + 250, box_y + 13), "70% In-Sample Train / 30% Independent Out-of-Sample Test", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "Institutional Friction Deduction:", fill="#fbbf24", font=f_box_title)
    d.text((col3_x + 300, box_y + 13), "Delta Taker Fees (0.10%) + Slippage (0.06%) + Funding deducted", fill="#8b949e", font=f_box_sub)

    by = box_y + 55
    d.text((col3_x + 25, by), "• Strict Veto Gate: Rejects setup if Win Rate < 65% or Friction EV < +0.30R.", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 26), "• Wilson Score Lower Bound: Requires lower 95% CI bound >= 45% (Anti-overfit).", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 52), "• Minimum Sample Size: Requires >= 8 decisive historical matches to qualify.", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 78), "• Empirical Metrics: Profit Factor >= 1.50x and non-negative OOS expectancy.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 4: AGENT 6 (RISK GATEKEEPER & CIRCUIT BREAKER)
    # -------------------------------------------------------------
    draw_card_base(col1_x, row2_y, "🛡️ AGENT 6: RISK GATEKEEPER & SIZING", "HARD RISK LIMITS", "#ef4444", "#501313", "#dc2626")
    cy = row2_y + 80
    d.text((col1_x + 25, cy), "Mathematical Position Sizing & Multi-Horizon Circuit Breakers:", fill="#f87171", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Hard Dollar Cap: min(Equity × 1%, $4.00)", fill="#f87171", font=f_box_title)
    d.text((col1_x + 410, box_y + 13), "Conviction cannot breach risk ceiling", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Minimum Contract Rejection (NO_TRADE):", fill="#f87171", font=f_box_title)
    d.text((col1_x + 390, box_y + 13), "Contracts = 0 if min lot risk exceeds budget", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Multi-Horizon Drawdown Protection:", fill="#f87171", font=f_box_title)
    d.text((col1_x + 360, box_y + 13), "Daily 3% · Weekly 5% · Monthly 8% Emergency Halt", fill="#8b949e", font=f_box_sub)

    by = box_y + 55
    d.text((col1_x + 25, by), "• Authoritative MMR Liquidation Buffer: Guaranteed >= 3.0x Stop Loss distance.", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 26), "• Fail-Closed Circuit Breaker: Corrupt state fails closed; no auto-reset on day roll.", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 52), "• Consecutive Loss Cooldown: 3 consecutive stop losses triggers 30m pause.", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 78), "• Portfolio Concurrency Cap: Max 2 open positions total (Max 2 correlated crypto).", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 5: AGENT 7 & DETERMINISTIC SAFETY CONTROLLER
    # -------------------------------------------------------------
    draw_card_base(col2_x, row2_y, "🔒 AGENT 7: TELEGRAM GATE & SAFETY", "14 INVARIANTS", "#06b6d4", "#083344", "#0891b2")
    cy = row2_y + 80
    d.text((col2_x + 25, cy), "14-Criterion Pure-Code Safety Controller & User Authorization:", fill="#38bdf8", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "14 Safety Criteria Evaluated:", fill="#38bdf8", font=f_box_title)
    d.text((col2_x + 280, box_y + 13), "Issues HMAC-Signed Execution Token (30s TTL)", fill="#c9d1d9", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Telegram Sender Authentication:", fill="#38bdf8", font=f_box_title)
    d.text((col2_x + 310, box_y + 13), "Validates caller ID against AUTHORIZED_TELEGRAM_USERS", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Cryptographic Replay Shield:", fill="#38bdf8", font=f_box_title)
    d.text((col2_x + 285, box_y + 13), "Parameter-bound nonces (Symbol, Entry, SL, TP, Size, Risk)", fill="#8b949e", font=f_box_sub)

    by = box_y + 55
    d.text((col2_x + 25, by), "• Zero Orders without Valid Token: Execution agent requires unexpired HMAC token.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 26), "• Live Price Drift Revalidation: Cancels execution if mark price drifted > 0.40%.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 52), "• Auditable Log: Every proposal and decision saved to telegram_approvals_audit.json.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 78), "• Fail-Safe User Authority: Human operator retains absolute authorization control.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 6: AGENTS 8-11 (EXECUTION, SENTINEL, PERSISTENCE & COACH)
    # -------------------------------------------------------------
    draw_card_base(col3_x, row2_y, "⚡ AGENTS 8-11: EXECUTION & LEARNING", "EXECUTE & LEARN", "#10b981", "#064e3b", "#059669")
    cy = row2_y + 80
    d.text((col3_x + 25, cy), "Delta Execution, Stop Verification, Sentinel & SQLite Journal:", fill="#34d399", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "Agent 8 (Execution Idempotency):", fill="#34d399", font=f_box_title)
    d.text((col3_x + 310, box_y + 13), "client_order_id + Pre-retry history reconciliation", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "Mandatory Exchange SL Verification:", fill="#34d399", font=f_box_title)
    d.text((col3_x + 330, box_y + 13), "Verifies exchange stop order; emergency close if missing", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "Agent 8 (Multi-Stage Trailing Sentinel):", fill="#34d399", font=f_box_title)
    d.text((col3_x + 350, box_y + 13), "Breathing cushion -> Green profit lock -> Trailing runner", fill="#8b949e", font=f_box_sub)

    by = box_y + 55
    d.text((col3_x + 25, by), "• SQLite Event Store: Granular event-sourced audit log (state/trading_journal.db).", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 26), "• Breakeven Trap Eliminated: Secures positive green profit (+0.30R to +0.85R).", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 52), "• Agents 9 & 10: Empirical pattern postmortems & operating rules (/rules).", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 78), "• Volatility Buffer Active: Expands trailing threshold during market chop.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # FOOTER: INFRASTRUCTURE & LIFECYCLE SUMMARY
    # -------------------------------------------------------------
    foot_y = row2_y + card_h + 30
    foot_h = 240
    d.rounded_rectangle([(60, foot_y), (w - 60, foot_y + foot_h)], radius=16, fill="#161b22", outline="#30363d", width=2)
    # Header bar
    d.rounded_rectangle([(60, foot_y), (w - 60, foot_y + 44)], radius=16, fill="#1f2937")
    d.rectangle([(60, foot_y + 25), (w - 60, foot_y + 44)], fill="#1f2937")
    d.text((85, foot_y + 12), "🏗️ SYSTEM INFRASTRUCTURE, AUDIT ASSURANCE & ENTERPRISE RISK ARCHITECTURE", fill="#ffffff", font=f_foot_title)

    # 4 columns in footer
    fc_w = 540
    fc_gap = 20
    fc1_x = 85
    fc2_x = fc1_x + fc_w + fc_gap
    fc3_x = fc2_x + fc_w + fc_gap
    fc4_x = fc3_x + fc_w + fc_gap

    # Col 1: Cloud Runtime
    fcy = foot_y + 60
    d.text((fc1_x, fcy), "☁️ Cloud Runtime (24/7 Engine)", fill="#60a5fa", font=f_box_title)
    d.text((fc1_x, fcy + 28), "• Architecture: 6-Layer Multi-Agent System", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 50), "• Event Store: SQLite (state/trading_journal.db)", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 72), "• Sentinel Thread: 15s micro-trailing loop", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 94), "• Scanner Thread: 120s scan & validation loop", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 116), "• Healthcheck: REST /status & /health API", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 138), "• Production Status: 100% Tests Passing (19/19)", fill="#10b981", font=f_foot_body)

    # Col 2: Security Layer
    d.text((fc2_x, fcy), "🔑 Cryptographic Security", fill="#fbbf24", font=f_box_title)
    d.text((fc2_x, fcy + 28), "• Delta API: HMAC-SHA256 REST v2", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 50), "• Token Gate: HMAC-SHA256 Execution Tokens (30s TTL)", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 72), "• Telegram Security: Sender ID whitelist verification", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 94), "• Replay Shield: Parameter-bound cryptographic nonces", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 116), "• Credentials: Zero secrets in source code (.env only)", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 138), "• Permissions: Trading only (No withdrawal scope)", fill="#8b949e", font=f_foot_body)

    # Col 3: Risk Guardrails
    d.text((fc3_x, fcy), "🛑 Absolute Risk Invariants", fill="#f87171", font=f_box_title)
    d.text((fc3_x, fcy + 28), "• Hard Dollar Cap: min(Equity × 1%, $4.00 Max Risk)", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 50), "• Min Lot Enforcement: Returns NO_TRADE if over risk", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 72), "• Daily Circuit Breaker: 3.0% Max Daily Drawdown", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 94), "• Multi-Horizon Drawdown: Weekly 5% · Monthly 8% Halt", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 116), "• Fail-Closed State: Manual reset required after halt", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 138), "• Liquidation Buffer: >= 3.0x Stop Loss distance", fill="#8b949e", font=f_foot_body)

    # Col 4: Performance Profile
    d.text((fc4_x, fcy), "📊 Mathematical Edge", fill="#34d399", font=f_box_title)
    d.text((fc4_x, fcy + 28), "• Asymmetric Edge: Planned R:R strictly >= 2.2:1", fill="#10b981", font=f_foot_body)
    d.text((fc4_x, fcy + 50), "• Time Machine EV: Friction-adjusted EV >= +0.30R", fill="#10b981", font=f_foot_body)
    d.text((fc4_x, fcy + 72), "• Statistical Rigor: Wilson 95% Confidence Interval", fill="#10b981", font=f_foot_body)
    d.text((fc4_x, fcy + 94), "• Breakeven Shield: +0.30R to +0.85R green profit locked", fill="#8b949e", font=f_foot_body)
    d.text((fc4_x, fcy + 116), "• Idempotency: Exchange history reconciled on retry", fill="#8b949e", font=f_foot_body)
    d.text((fc4_x, fcy + 138), "• Stop Protection: Zero naked positions on exchange", fill="#8b949e", font=f_foot_body)

    # Save PNG
    out_path = r"d:\Project\Multi Agent Trading Bot\workflow_architecture_diagram.png"
    img.save(out_path, format="PNG", quality=95)
    print("Successfully generated high-resolution architecture diagram at:", out_path)

if __name__ == "__main__":
    generate_diagram()
