import os
from PIL import Image, ImageDraw, ImageFont

def create_architecture_diagram():
    # High resolution canvas (2400 x 1400)
    w, h = 2400, 1400
    img = Image.new('RGB', (w, h), color='#0d1117')
    d = ImageDraw.Draw(img)

    # Load Fonts
    font_dir = r"C:\Windows\Fonts"
    f_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 52)
    f_subtitle = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 28)
    f_card_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 32)
    f_card_sub = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
    f_body = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 22)
    f_body_bold = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
    f_btn = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 24)

    # 1. Header Banner
    d.rounded_rectangle([(60, 40), (w - 60, 170)], radius=20, fill='#161b22', outline='#30363d', width=2)
    d.text((100, 65), "🚀 DELTA EXCHANGE MULTI-AGENT TRADING BOT — WORKFLOW", fill='#ffffff', font=f_title)
    d.text((100, 125), "Autonomous Cloud Scanner  ·  5-Timeframe AI Edge  ·  Telegram Permission Gate  ·  Auto Trailing Stop", fill='#8b949e', font=f_subtitle)

    # Top Status Pill
    d.rounded_rectangle([(w - 380, 75), (w - 100, 135)], radius=12, fill='#238636', outline='#2ea043', width=2)
    d.text((w - 355, 90), "● 24/7 ACTIVE CLOUD", fill='#ffffff', font=ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22))

    # Helper function for card drawing
    def draw_card(x, y, card_w, card_h, num, title, subtitle, border_color, header_bg):
        # Card shadow & body
        d.rounded_rectangle([(x, y), (x + card_w, y + card_h)], radius=18, fill='#161b22', outline=border_color, width=3)
        # Card header bar
        d.rounded_rectangle([(x, y), (x + card_w, y + 80)], radius=18, fill=header_bg)
        d.rectangle([(x, y + 50), (x + card_w, y + 80)], fill=header_bg)  # Square off bottom of header
        
        # Step Circle
        d.ellipse([(x + 20, y + 16), (x + 68, y + 64)], fill='#ffffff')
        d.text((x + 36, y + 25), str(num), fill='#0d1117', font=ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 26))

        # Title
        d.text((x + 85, y + 23), title, fill='#ffffff', font=f_card_title)
        return x, y + 95

    # ================= ROW 1: 3 CARDS =================
    r1_y = 210
    card_w1 = 700
    card_h1 = 480

    # --- CARD 1: 24/7 Cloud Scanning ---
    cx, cy = draw_card(60, r1_y, card_w1, card_h1, 1, "24/7 Cloud Scanner (Render)", "Runs 24/7 without your laptop", "#3b82f6", "#1e3a8a")
    lines1 = [
        ("• Runs 24/7 on Cloud:", " Laptop can be completely off."),
        ("• Automated Keep-Alive:", " Pings /health every 5 minutes."),
        ("• Scan Cadence:", " Analyzes markets every 120 seconds."),
        ("• Monitored Universe (8 Assets):", ""),
        ("   BTCUSD, ETHUSD, SOLUSD, XAUUSD (Gold),", ""),
        ("   PAXGUSD, XRPUSD, DOGEUSD, ADAUSD", ""),
        ("• Account Health Check:", " Verifies margin & equity first.")
    ]
    cur_y = cy + 15
    for l1, l2 in lines1:
        if l1.startswith("•"):
            d.text((cx + 30, cur_y), l1, fill='#60a5fa', font=f_body_bold)
            d.text((cx + 30 + d.textlength(l1, font=f_body_bold) + 5, cur_y), l2, fill='#e6edf3', font=f_body)
        else:
            d.text((cx + 30, cur_y), l1, fill='#f59e0b', font=f_body_bold)
        cur_y += 38

    # --- CARD 2: 5-Timeframe Confluence ---
    cx, cy = draw_card(800, r1_y, card_w1, card_h1, 2, "5-Timeframe AI Confluence", "80-90% Win-Rate Filter", "#8b5cf6", "#4c1d95")
    lines2 = [
        ("1. 1-Month (1M):", " Ultra-Macro Trend vs Monthly Open & PMH/PML"),
        ("2. 1-Week (1W):", " Weekly EMA 21 Trend & Prior Week High/Low"),
        ("3. 1-Day (1D):", " Daily EMA 21/50 Stack & Prior Day High/Low"),
        ("4. 4-Hour (4H):", " Cycle Momentum & Dynamic Support/Resistance"),
        ("5. 1-Hour (1H):", " Fractal Liquidity Sweep (BSL/SSL) + MSS"),
        ("• Strict Veto Rule:", " NEVER short in bull trend, NEVER buy in bear!"),
        ("• Minimum Score:", " Only proposes trades scoring ≥ 70 / 100")
    ]
    cur_y = cy + 15
    for l1, l2 in lines2:
        d.text((cx + 25, cur_y), l1, fill='#a78bfa', font=f_body_bold)
        d.text((cx + 25 + d.textlength(l1, font=f_body_bold) + 5, cur_y), l2, fill='#e6edf3', font=f_body)
        cur_y += 38

    # --- CARD 3: 2-Way Telegram Confirmation ---
    cx, cy = draw_card(1540, r1_y, card_w1 + 100, card_h1, 3, "Telegram 2-Way Approval Gate", "YOU Have 100% Control", "#10b981", "#064e3b")
    lines3 = [
        ("• Full Trade Proposal Pushed to Telegram:", ""),
        ("   Includes exact 5-timeframe reasoning, entry, SL, and 1:2 TP.", ""),
        ("• Two Interactive Buttons on your phone:", "")
    ]
    cur_y = cy + 15
    for l1, l2 in lines3:
        d.text((cx + 25, cur_y), l1, fill='#34d399', font=f_body_bold)
        cur_y += 34

    # Draw Telegram Buttons
    btn_y = cur_y + 10
    d.rounded_rectangle([(cx + 35, btn_y), (cx + 360, btn_y + 60)], radius=12, fill='#10b981', outline='#34d399', width=2)
    d.text((cx + 80, btn_y + 15), "✅ Confirm & Execute", fill='#ffffff', font=f_btn)

    d.rounded_rectangle([(cx + 400, btn_y), (cx + 725, btn_y + 60)], radius=12, fill='#dc2626', outline='#f87171', width=2)
    d.text((cx + 475, btn_y + 15), "❌ Reject Trade", fill='#ffffff', font=f_btn)

    # What happens next
    cur_y = btn_y + 85
    lines3_sub = [
        ("✅ Tap Confirm:", " Order executes on Delta Exchange with receipt."),
        ("❌ Tap Reject:", " Trade is cancelled immediately. Zero risk."),
        ("⏳ No Response (10m):", " Proposal expires. ZERO trades without click!")
    ]
    for l1, l2 in lines3_sub:
        d.text((cx + 25, cur_y), l1, fill='#f59e0b', font=f_body_bold)
        d.text((cx + 25 + d.textlength(l1, font=f_body_bold) + 5, cur_y), l2, fill='#e6edf3', font=f_body)
        cur_y += 34


    # ================= ROW 2: 2 BIG WIDE CARDS =================
    r2_y = 730
    card_w2 = 1110
    card_h2 = 590

    # --- CARD 4: Execution on Delta Exchange ---
    cx, cy = draw_card(60, r2_y, card_w2, card_h2, 4, "Atomic Order Execution on Delta Exchange", "Precision Bracket Orders (Entry + SL + TP)", "#f59e0b", "#78350f")
    
    # Inner boxes for Primary + SL + TP
    sub_box_y = cy + 20
    box_w = 330
    box_h = 100

    # Entry Box
    d.rounded_rectangle([(cx + 30, sub_box_y), (cx + 30 + box_w, sub_box_y + box_h)], radius=10, fill='#1f2937', outline='#38bdf8', width=2)
    d.text((cx + 50, sub_box_y + 18), "1. LIMIT ENTRY", fill='#38bdf8', font=f_card_sub)
    d.text((cx + 50, sub_box_y + 55), "Filled at optimal market price", fill='#e6edf3', font=f_body)

    # Stop Loss Box
    d.rounded_rectangle([(cx + 390, sub_box_y), (cx + 390 + box_w, sub_box_y + box_h)], radius=10, fill='#1f2937', outline='#ef4444', width=2)
    d.text((cx + 410, sub_box_y + 18), "2. PROTECTIVE STOP LOSS", fill='#ef4444', font=f_card_sub)
    d.text((cx + 410, sub_box_y + 55), "Structural Wick + 0.15 ATR buffer", fill='#e6edf3', font=f_body)

    # Take Profit Box
    d.rounded_rectangle([(cx + 750, sub_box_y), (cx + 750 + box_w, sub_box_y + box_h)], radius=10, fill='#1f2937', outline='#10b981', width=2)
    d.text((cx + 770, sub_box_y + 18), "3. TAKE PROFIT TARGET", fill='#10b981', font=f_card_sub)
    d.text((cx + 770, sub_box_y + 55), "Exact 1:2 Starting Risk/Reward", fill='#e6edf3', font=f_body)

    # Execution Specs Details
    cur_y = sub_box_y + 130
    exec_details = [
        ("• Capital Allocation:", " Automatically uses 75% to 100% of your free available USD balance."),
        ("• Leverage Controls:", " 50x Isolated on BTC  |  25x Isolated on SOL, XAU (Gold), and Alts."),
        ("• Exchange Native Brackets:", " Stop-Loss & Take-Profit sit directly on Delta Exchange servers."),
        ("• OCO Bracket Protection:", " If Stop Loss hits, Take Profit is cancelled automatically (and vice-versa)."),
        ("• Cloud Disconnect Safe:", " Because orders are on-exchange, you are protected even if internet cuts off.")
    ]
    for l1, l2 in exec_details:
        d.text((cx + 30, cur_y), l1, fill='#fbbf24', font=f_body_bold)
        d.text((cx + 30 + d.textlength(l1, font=f_body_bold) + 5, cur_y), l2, fill='#e6edf3', font=f_body)
        cur_y += 42


    # --- CARD 5: Dynamic Trailing Stop Loss ---
    cx, cy = draw_card(1230, r2_y, card_w2 + 40, card_h2, 5, "Dynamic Trailing Stop Loss Manager", "Automated Profit Preservation & Runner Expansion", "#10b981", "#064e3b")
    
    d.text((cx + 30, cy + 15), "Checks open positions every 15 seconds. Automatically edits Delta stop-loss orders:", fill='#e6edf3', font=f_body)

    # 4 Trailing Stage Cards
    stage_y = cy + 55
    st_w = 250
    st_h = 170

    stages = [
        ("STAGE 1", "BREAKEVEN", "Profit ≥ +1.0R", "SL moved to Entry + fee buffer.", "Trade is 100% RISK FREE!", "#38bdf8"),
        ("STAGE 2", "LOCK +1R", "Profit ≥ +2.0R", "SL moved to lock +1.0R profit.", "TP extended to 1:3 R:R!", "#10b981"),
        ("STAGE 3", "LOCK +2R", "Profit ≥ +3.0R", "SL moved to lock +2.0R profit.", "TP extended to 1:5 R:R!", "#f59e0b"),
        ("STAGE 4", "RUNNER", "Profit ≥ +5.0R", "SL locked at +4.0R profit.", "Captures massive trend moves!", "#ec4899")
    ]

    for i, (s_num, s_title, s_rule, s_desc1, s_desc2, s_col) in enumerate(stages):
        sx = cx + 30 + (i * (st_w + 20))
        d.rounded_rectangle([(sx, stage_y), (sx + st_w, stage_y + st_h)], radius=12, fill='#1f2937', outline=s_col, width=2)
        d.text((sx + 15, stage_y + 15), s_num, fill='#8b949e', font=ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 16))
        d.text((sx + 15, stage_y + 35), s_title, fill=s_col, font=ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22))
        d.text((sx + 15, stage_y + 68), s_rule, fill='#ffffff', font=ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 18))
        d.text((sx + 15, stage_y + 102), s_desc1, fill='#9ca3af', font=ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 15))
        d.text((sx + 15, stage_y + 128), s_desc2, fill=s_col, font=ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 15))

    # Live verification note
    cur_y = stage_y + st_h + 35
    d.rounded_rectangle([(cx + 30, cur_y), (cx + card_w2, cur_y + 120)], radius=12, fill='#0d1117', outline='#30363d', width=2)
    d.text((cx + 50, cur_y + 20), "⚡ LIVE VERIFICATION (Currently Active on Delta Exchange):", fill='#10b981', font=f_card_sub)
    d.text((cx + 50, cur_y + 55), "• ETHUSD Long: Profit hit +1.34R → Stop Loss automatically trailed to $2,232.24 (BREAKEVEN ACTIVE)", fill='#e6edf3', font=f_body)
    d.text((cx + 50, cur_y + 85), "• BTCUSD Short: Entered at $77,931 with $78,174.66 Stop Loss and $77,443.68 Take Profit (1:2 Target)", fill='#e6edf3', font=f_body)

    # Save to disk
    out_png = r"d:\Project\Multi Agent Trading Bot\workflow_architecture_diagram.png"
    img.save(out_png, "PNG")
    print(f"High-res PNG created successfully: {out_png}")

if __name__ == "__main__":
    create_architecture_diagram()
