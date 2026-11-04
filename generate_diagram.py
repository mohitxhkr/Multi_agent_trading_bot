import os
import sys
from PIL import Image, ImageDraw, ImageFont

def generate_diagram():
    w, h = 2400, 1550
    img = Image.new("RGB", (w, h), color="#0d1117")
    d = ImageDraw.Draw(img)

    # Fonts
    font_dir = r"C:\Windows\Fonts"
    f_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 46)
    f_sub = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 23)
    f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
    
    f_card_h = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)
    f_card_tag = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 16)
    f_sec_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
    f_box_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 18)
    f_box_sub = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 16)
    f_body = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 17)
    f_body_b = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 17)
    f_foot_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
    f_foot_body = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 15)

    # 1. Header Banner
    d.rounded_rectangle([(60, 40), (w - 60, 160)], radius=18, fill="#161b22", outline="#30363d", width=2)
    # Cyan accent pill on left of header
    d.rounded_rectangle([(60, 40), (72, 160)], radius=4, fill="#06b6d4")
    
    d.text((95, 62), "⚡ DELTA EXCHANGE MULTI-AGENT QUANTITATIVE TRADING WORKFLOW", fill="#ffffff", font=f_title)
    d.text((95, 118), "Autonomous Cloud Operation  •  Market Posture & Breadth  •  ⏳ Time Machine Backtest  •  Fixed Dollar Risk  •  🧠 Adaptive Self-Learning", fill="#8b949e", font=f_sub)

    # Top Status Pill
    d.rounded_rectangle([(w - 420, 68), (w - 90, 132)], radius=12, fill="#1f2937", outline="#10b981", width=2)
    d.ellipse([(w - 395, 93), (w - 377, 111)], fill="#10b981")
    d.text((w - 365, 88), "24/7 ACTIVE CLOUD (Render)", fill="#ffffff", font=f_pill)

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
        d.rounded_rectangle([(x + card_w - 170, y + 14), (x + card_w - 20, y + 46)], radius=8, fill=badge_bg)
        d.text((x + card_w - 155, y + 20), badge_text, fill="#ffffff", font=f_card_tag)

    # -------------------------------------------------------------
    # CARD 1: AGENT 1 & 1.5 (REGIME ANALYST & EXPOSURE COACH)
    # -------------------------------------------------------------
    draw_card_base(col1_x, row1_y, "🔍 AGENTS 1 & 1.5: REGIME & EXPOSURE COACH", "POSTURE & BREADTH", "#388bfd", "#1e3a5f", "#0284c7")
    cy = row1_y + 80
    d.text((col1_x + 25, cy), "Macro Order Flow & Market Posture Engine:", fill="#38bdf8", font=f_sec_title)
    
    # 3 mini boxes
    box_y = cy + 30
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "1M, 1W & 1D:", fill="#38bdf8", font=f_box_title)
    d.text((col1_x + 160, box_y + 13), "Higher-TF Trend Anchor (Mandatory trend veto: no counter-trend)", fill="#c9d1d9", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Agent 1.5 Exposure Coach:", fill="#38bdf8", font=f_box_title)
    d.text((col1_x + 270, box_y + 13), "Market Breadth (% > EMA21) + Health Score (0-100)", fill="#c9d1d9", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "15m Trigger & MSS:", fill="#38bdf8", font=f_box_title)
    d.text((col1_x + 215, box_y + 13), "BSL/SSL Sweeps + Mandatory MSS Candle Body Close", fill="#c9d1d9", font=f_box_sub)

    # Bullet points
    by = box_y + 55
    d.text((col1_x + 25, by), "• Cash Priority Gate: If Market Health < 32/100, blocks ALL trades (Cash 100%).", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 26), "• Defensive Caution: Restricts candidate universe strictly to Tier-1 (BTC/ETH/XAU).", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 52), "• Optimal Trade Entry (OTE): Retest limit entry at 0.382 retracement (No chasing).", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 78), "• Institutional Killzones: Confluence boost during London & New York Open.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 2: AGENT 2 (STRATEGY GENERATOR)
    # -------------------------------------------------------------
    draw_card_base(col2_x, row1_y, "💡 AGENT 2: ALPHA & STRATEGY GENERATOR", "ALPHA ENGINE", "#8b5cf6", "#3b1d6e", "#7c3aed")
    cy = row1_y + 80
    d.text((col2_x + 25, cy), "Candidate Setup Edge & Confluence Scoring:", fill="#c084fc", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Score Threshold: >= 80 / 100", fill="#c084fc", font=f_box_title)
    d.text((col2_x + 310, box_y + 13), "Requires 4+ timeframe confluence + volume", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Planned Reward-to-Risk: >= 2.20 : 1", fill="#c084fc", font=f_box_title)
    d.text((col2_x + 360, box_y + 13), "Asymmetric payout ratio", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 12), "Ultra-Tight Scalp Stop: 0.20% - 0.40%", fill="#c084fc", font=f_box_title)
    d.text((col2_x + 365, box_y + 13), "Anchored to sweep extreme", fill="#8b949e", font=f_box_sub)

    by = box_y + 55
    d.text((col2_x + 25, by), "• Tier 1 Focus Assets: BTCUSD, ETHUSD, XAUUSD (Primary Deep Liquidity).", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 26), "• Tier 2 Secondary Assets: SOL, XRP, DOGE, ADA (Strict safety margin caps).", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 52), "• Same-Session Resolution: Rapid scalps completing in 30 mins to 3 hours.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 78), "• Trade Proposal Output: Emits exact Entry, SL, TP, and Confluence Matrix.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 3: AGENT 2.5 (TIME MACHINE SIMULATOR)
    # -------------------------------------------------------------
    draw_card_base(col3_x, row1_y, "⏳ AGENT 2.5: TIME MACHINE PROBABILITY SIMULATOR", "BACKTEST GATE", "#f59e0b", "#522b07", "#d97706")
    cy = row1_y + 80
    d.text((col3_x + 25, cy), "Pre-Execution Historical Walk-Forward Simulation:", fill="#fbbf24", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "1. 350+ Candle Lookback Scan", fill="#fbbf24", font=f_box_title)
    d.text((col3_x + 310, box_y + 13), "Matches identical RSI, EMA & sweep patterns", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "2. 48-Bar Forward Walk", fill="#fbbf24", font=f_box_title)
    d.text((col3_x + 260, box_y + 13), "Simulates bracket: Hit TP first (WIN) or SL first (LOSS)", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "3. Expected Value (EV +R)", fill="#fbbf24", font=f_box_title)
    d.text((col3_x + 280, box_y + 13), "Calculates Win Rate %, EV, Profit Factor, MAE Drawdown", fill="#8b949e", font=f_box_sub)

    by = box_y + 55
    d.text((col3_x + 25, by), "• Strict Veto Gate: Rejects setup if historical win rate < 68% or EV < +0.30R.", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 26), "• Empirical Validation: Only trades with proven past mathematical edge pass.", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 52), "• Intra-Trade Drawdown: Tracks Maximum Adverse Excursion (< 0.20% avg).", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 78), "• Telegram Proof: Past sample size, win rate %, and EV embedded into alert.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 4: AGENT 3 (RISK GATEKEEPER)
    # -------------------------------------------------------------
    draw_card_base(col1_x, row2_y, "🛡️ AGENT 3: PRE-TRADE DISCIPLINE & SIZING GATE", "RISK GATE", "#ef4444", "#501313", "#dc2626")
    cy = row2_y + 80
    d.text((col1_x + 25, cy), "Institutional Fixed Dollar Risk Model:", fill="#f87171", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Fixed Dollar Risk: $2.00 - $4.00 Max", fill="#f87171", font=f_box_title)
    d.text((col1_x + 360, box_y + 13), "Target 2% Equity per trade ceiling", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Altcoin Safety Guardrail: Max $2.00 Risk", fill="#f87171", font=f_box_title)
    d.text((col1_x + 380, box_y + 13), "Margin strictly capped at <= 10%", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col1_x + 25, box_y), (col1_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col1_x + 40, box_y + 12), "Contracts Formula: Dollar Risk / (Contract Value × Stop Dist)", fill="#f87171", font=f_box_title)

    by = box_y + 55
    d.text((col1_x + 25, by), "• Eliminates Catastrophic Losses: No trade can ever wipe out account equity.", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 26), "• Account Circuit Breaker: 5% Max Daily Drawdown hard halt locks the bot.", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 52), "• Max Concurrency: 3 active positions max (0 duplicate asset exposure).", fill="#8b949e", font=f_body)
    d.text((col1_x + 25, by + 78), "• Leverage Directives: 50x Isolated on BTC | 25x Isolated on ETH, XAU, Alts.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 5: TELEGRAM TWO-WAY HUMAN GATE
    # -------------------------------------------------------------
    draw_card_base(col2_x, row2_y, "📱 TELEGRAM 2-WAY HUMAN-IN-THE-LOOP GATE", "HUMAN GATE", "#06b6d4", "#083344", "#0891b2")
    cy = row2_y + 80
    d.text((col2_x + 25, cy), "Zero-Trust Interactive Confirmation Protocol:", fill="#38bdf8", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col2_x + 25, box_y), (col2_x + card_w - 25, box_y + 60)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col2_x + 40, box_y + 10), "Interactive Telegram Proposal Card Delivered Instantly:", fill="#38bdf8", font=f_box_title)
    d.text((col2_x + 40, box_y + 35), "Asset, Direction, Entry, SL, TP (1:2.2 R:R), Confluence Matrix & Time Machine Stats", fill="#c9d1d9", font=f_box_sub)

    # Buttons
    btn_y = box_y + 70
    d.rounded_rectangle([(col2_x + 40, btn_y), (col2_x + 330, btn_y + 44)], radius=8, fill="#238636", outline="#2ea043")
    d.text((col2_x + 90, btn_y + 10), "✅ Confirm & Execute", fill="#ffffff", font=f_box_title)

    d.rounded_rectangle([(col2_x + 360, btn_y), (col2_x + 650, btn_y + 44)], radius=8, fill="#da3633", outline="#f85149")
    d.text((col2_x + 445, btn_y + 10), "❌ Reject Trade", fill="#ffffff", font=f_box_title)

    by = btn_y + 55
    d.text((col2_x + 25, by), "• Zero-Trust Mandate: Zero orders place without user explicit tap.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 26), "• Timeout Protection: Proposal auto-expires after 5–10 mins to avoid late fills.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 52), "• Interactive Commands: /scan, /trade, /positions, /status, /close <symbol>.", fill="#8b949e", font=f_body)
    d.text((col2_x + 25, by + 78), "• User Discretion: Trader retains 100% final authority over portfolio actions.", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # CARD 6: AGENTS 4, 5, 6 & 7 (EXECUTION, LEARNING & PERFORMANCE COACH)
    # -------------------------------------------------------------
    draw_card_base(col3_x, row2_y, "⚡ AGENTS 4, 5, 6 & 7: EXECUTION & PERFORMANCE COACH", "EXECUTE & LEARN", "#10b981", "#064e3b", "#059669")
    cy = row2_y + 80
    d.text((col3_x + 25, cy), "Delta Execution, Trailing Sentinel & Performance Coach:", fill="#34d399", font=f_sec_title)

    box_y = cy + 30
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 44)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 12), "Atomic Bracket Orders & 15s Trailing Sentinel", fill="#34d399", font=f_box_title)
    d.text((col3_x + 445, box_y + 13), "+0.50R Breakeven Shield to +2.2R TP", fill="#8b949e", font=f_box_sub)

    box_y += 52
    d.rounded_rectangle([(col3_x + 25, box_y), (col3_x + card_w - 25, box_y + 60)], radius=8, fill="#0d1117", outline="#30363d")
    d.text((col3_x + 40, box_y + 10), "Agent 6 & 7: Adaptive Learning & Performance Coach:", fill="#34d399", font=f_box_title)
    d.text((col3_x + 40, box_y + 35), "0-100 Self-Scorecard · Pattern Memory · Binding Operating Rules (/rules)", fill="#c9d1d9", font=f_box_sub)

    by = box_y + 70
    d.text((col3_x + 25, by), "• Pattern Reinforcement: Winning patterns receive +8 pts confluence boost.", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 26), "• Pattern Avoidance: Failing patterns penalized (-15) or permanently blacklisted.", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 52), "• MFE & MAE Postmortem: Tracks peak potential vs adverse excursion on every exit.", fill="#8b949e", font=f_body)
    d.text((col3_x + 25, by + 78), "• Continuous Evolution: Dynamic rules update each session (/rules, /scorecard).", fill="#8b949e", font=f_body)

    # -------------------------------------------------------------
    # FOOTER: INFRASTRUCTURE & LIFECYCLE SUMMARY
    # -------------------------------------------------------------
    foot_y = row2_y + card_h + 30
    foot_h = 240
    d.rounded_rectangle([(60, foot_y), (w - 60, foot_y + foot_h)], radius=16, fill="#161b22", outline="#30363d", width=2)
    # Header bar
    d.rounded_rectangle([(60, foot_y), (w - 60, foot_y + 44)], radius=16, fill="#1f2937")
    d.rectangle([(60, foot_y + 25), (w - 60, foot_y + 44)], fill="#1f2937")
    d.text((85, foot_y + 12), "🏗️ SYSTEM INFRASTRUCTURE, SECURITY & PERFORMANCE SPECIFICATIONS", fill="#ffffff", font=f_foot_title)

    # 4 columns in footer
    fc_w = 540
    fc_gap = 20
    fc1_x = 85
    fc2_x = fc1_x + fc_w + fc_gap
    fc3_x = fc2_x + fc_w + fc_gap
    fc4_x = fc3_x + fc_w + fc_gap

    # Col 1: Cloud Runtime
    fcy = foot_y + 60
    d.text((fc1_x, fcy), "☁️ Cloud Runtime (Render 24/7)", fill="#60a5fa", font=f_box_title)
    d.text((fc1_x, fcy + 28), "• Web Service: multi-agent-trading-bot-1", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 50), "• Background Thread 1: 24/7 Scanner (120s loop)", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 72), "• Background Thread 2: Trailing Sentinel (15s loop)", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 94), "• Background Thread 3: Telegram Bot Polling", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 116), "• Healthcheck: /status & /health (HTTP 200 OK)", fill="#8b949e", font=f_foot_body)
    d.text((fc1_x, fcy + 138), "• Autonomous Uptime: 99.9% Always-On Operation", fill="#10b981", font=f_foot_body)

    # Col 2: Security Layer
    d.text((fc2_x, fcy), "🔑 API & Security Layer", fill="#fbbf24", font=f_box_title)
    d.text((fc2_x, fcy + 28), "• Exchange: Delta Exchange (India / Global)", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 50), "• Auth: HMAC-SHA256 Signature Header", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 72), "• IP Whitelist: Blank / Unrestricted IP Mode", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 94), "• Key Storage: Render Secret Store / .env", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 116), "• Permissions: Trading only (No withdrawal rights)", fill="#8b949e", font=f_foot_body)
    d.text((fc2_x, fcy + 138), "• Resiliency: Auto-retry on transient drops", fill="#8b949e", font=f_foot_body)

    # Col 3: Risk Guardrails
    d.text((fc3_x, fcy), "🛑 Risk & Drawdown Guardrails", fill="#f87171", font=f_box_title)
    d.text((fc3_x, fcy + 28), "• Dollar Sizing: $2.00 - $4.00 max risk per trade", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 50), "• Equity Ceiling: Max 2% - 3% risk on portfolio", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 72), "• Altcoin Margin Cap: Max 10% equity / $2.00 risk", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 94), "• Daily Circuit Breaker: 5% Max Daily Drawdown", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 116), "• Max Positions: 3 simultaneous active positions", fill="#8b949e", font=f_foot_body)
    d.text((fc3_x, fcy + 138), "• Correlation Guard: Zero duplicate symbols", fill="#8b949e", font=f_foot_body)

    # Col 4: Performance Profile
    d.text((fc4_x, fcy), "📊 Performance & Expectancy", fill="#34d399", font=f_box_title)
    d.text((fc4_x, fcy + 28), "• Target Precision: 80% - 90% Win Rate", fill="#10b981", font=f_foot_body)
    d.text((fc4_x, fcy + 50), "• Time Machine EV: +0.40R to +1.50R per trade", fill="#10b981", font=f_foot_body)
    d.text((fc4_x, fcy + 72), "• Profit Factor: >= 2.5x to 3.5x payout", fill="#10b981", font=f_foot_body)
    d.text((fc4_x, fcy + 94), "• Breakeven Shield: Locks entry at +0.50R move", fill="#8b949e", font=f_foot_body)
    d.text((fc4_x, fcy + 116), "• Holding Duration: 30 mins to 3 hours (Scalp)", fill="#8b949e", font=f_foot_body)
    d.text((fc4_x, fcy + 138), "• Drawdown: Low-variance equity growth", fill="#8b949e", font=f_foot_body)

    # Save PNG
    out_path = r"d:\Project\Multi Agent Trading Bot\workflow_architecture_diagram.png"
    img.save(out_path, format="PNG", quality=95)
    print("Successfully generated high-resolution architecture diagram at:", out_path)

if __name__ == "__main__":
    generate_diagram()

