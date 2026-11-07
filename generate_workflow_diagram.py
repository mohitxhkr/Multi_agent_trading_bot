import os
import sys
from PIL import Image, ImageDraw, ImageFont

def generate_workflow():
    w, h = 2400, 1450
    img = Image.new("RGB", (w, h), color="#0d1117")
    d = ImageDraw.Draw(img)

    font_dir = r"C:\Windows\Fonts"
    f_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 42)
    f_sub = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 21)
    f_pill = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 19)
    f_step_num = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 20)
    f_step_title = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 22)
    f_step_sub = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 15)
    f_step_body = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 16)
    f_arrow = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 28)
    f_foot_t = ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), 19)
    f_foot_b = ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), 15)

    # 1. Header Banner
    d.rounded_rectangle([(60, 40), (w - 60, 150)], radius=16, fill="#161b22", outline="#30363d", width=2)
    d.rounded_rectangle([(60, 40), (72, 150)], radius=4, fill="#10b981")
    d.text((95, 60), "🔄 END-TO-END QUANTITATIVE TRADING WORKFLOW PIPELINE", fill="#ffffff", font=f_title)
    d.text((95, 112), "6 Execution Layers  •  10 Specialized Agents  •  14 Deterministic Safety Invariants  •  Authoritative SQLite Event Store", fill="#8b949e", font=f_sub)

    # Status Pill
    d.rounded_rectangle([(w - 400, 65), (w - 85, 125)], radius=10, fill="#1f2937", outline="#10b981", width=2)
    d.ellipse([(w - 378, 88), (w - 362, 104)], fill="#10b981")
    d.text((w - 350, 84), "AUTOMATED RUNTIME", fill="#ffffff", font=f_pill)

    # Workflow Grid Layout: 3 Rows of 4 Step Cards
    cols = 4
    rows = 3
    card_w = 530
    card_h = 320
    x_start = 60
    x_gap = 43
    y_start = 180
    y_gap = 45

    steps = [
        # Row 1: Layers 1 & 2
        {
            "num": "STEP 01",
            "layer": "LAYER 1: INTELLIGENCE",
            "title": "Data Feed Validation",
            "color": "#388bfd",
            "hdr_bg": "#1e3a5f",
            "bullets": [
                "• Checks 15m, 1H, 4H, Daily & Weekly feeds",
                "• Rejects missing candle intervals & gaps",
                "• Freshness guard: Vetoes stale data > 60s",
                "• Extreme price spike filter (> 8% wicks)"
            ],
            "agent": "MarketDataValidator"
        },
        {
            "num": "STEP 02",
            "layer": "LAYER 1: INTELLIGENCE",
            "title": "Regime & Breadth",
            "color": "#388bfd",
            "hdr_bg": "#1e3a5f",
            "bullets": [
                "• 6-Timeframe EMA stacks (21, 50, 200)",
                "• Market-Wide Breadth: % watchlist > 20 EMA",
                "• ETH/BTC Relative Strength leadership",
                "• Crowded funding rate filter (> +0.03%)"
            ],
            "agent": "Agent 1: Regime Analyst"
        },
        {
            "num": "STEP 03",
            "layer": "LAYER 1: POSTURE",
            "title": "Exposure & Posture",
            "color": "#06b6d4",
            "hdr_bg": "#083344",
            "bullets": [
                "• Market Health Score calculation (0-100)",
                "• AGGRESSIVE / DEFENSIVE / CASH postures",
                "• Cash Priority: Health < 32 blocks ALL entries",
                "• Clamps maximum isolated leverage (50x/25x)"
            ],
            "agent": "Agent 2: Exposure Coach"
        },
        {
            "num": "STEP 04",
            "layer": "LAYER 2: STRATEGY",
            "title": "SMC Alpha Formulation",
            "color": "#8b5cf6",
            "hdr_bg": "#3b1d6e",
            "bullets": [
                "• 15m Liquidity Sweeps (BSL / SSL)",
                "• Mandatory candle body MSS confirmation",
                "• Structural Invalidation Stop (No synthetic stops)",
                "• Strict Asymmetric Payout: Planned R:R >= 2.2:1"
            ],
            "agent": "Agent 3: Strategy Generator"
        },

        # Row 2: Layers 2 & 3
        {
            "num": "STEP 05",
            "layer": "LAYER 2: PROBABILITY",
            "title": "Time Machine Simulator",
            "color": "#f59e0b",
            "hdr_bg": "#522b07",
            "bullets": [
                "• 400+ bar walk-forward pattern simulation",
                "• 70/30 In-Sample / Out-of-Sample verification",
                "• Zero Synthetic Stats: Fails closed on low data",
                "• Wilson 95% CI lower bound >= 45% (EV >= +0.30R)"
            ],
            "agent": "Agent 4: Time Machine Engine"
        },
        {
            "num": "STEP 06",
            "layer": "LAYER 3: RISK SIZING",
            "title": "Pre-Trade Risk Sizing",
            "color": "#ef4444",
            "hdr_bg": "#501313",
            "bullets": [
                "• Hard Dollar Risk Cap: min(Equity × 1%, $4.00)",
                "• Min Lot Sizing: Returns NO_TRADE if over risk",
                "• Authoritative Delta Exchange MMR calculation",
                "• Liquidation Buffer: Guaranteed >= 3.0x Stop Loss"
            ],
            "agent": "Agent 5: Risk Gatekeeper"
        },
        {
            "num": "STEP 07",
            "layer": "LAYER 3: CIRCUIT BREAKER",
            "title": "Multi-Horizon Drawdown",
            "color": "#ef4444",
            "hdr_bg": "#501313",
            "bullets": [
                "• Daily Drawdown (3%) -> HALTED state",
                "• Weekly (5%) & Monthly (8%) Emergency Halt",
                "• Consecutive Loss Limit: 3 losses -> 30m Cooldown",
                "• Fail-Closed Persistence: Manual admin reset only"
            ],
            "agent": "src/risk_manager.py"
        },
        {
            "num": "STEP 08",
            "layer": "LAYER 3: AUTHORIZATION",
            "title": "Telegram 2-Way Gate",
            "color": "#06b6d4",
            "hdr_bg": "#083344",
            "bullets": [
                "• Authenticates callback caller ID against whitelist",
                "• Cryptographic nonces bound to trade parameters",
                "• Replay suppression prevents duplicate clicks",
                "• Live ticker revalidation: Aborts if drift > 0.40%"
            ],
            "agent": "Agent 6: Telegram Gate"
        },

        # Row 3: Layers 4, 5 & 6
        {
            "num": "STEP 09",
            "layer": "LAYER 4: DETERMINISTIC SAFETY",
            "title": "Deterministic Safety Gate",
            "color": "#10b981",
            "hdr_bg": "#064e3b",
            "bullets": [
                "• Pure-code validation of 14 risk invariants",
                "• Issues HMAC-SHA256 Signed Token (30s TTL)",
                "• Verifies spread, freshness, equity, correlation",
                "• Zero orders dispatch without unexpired token"
            ],
            "agent": "DeterministicSafetyController"
        },
        {
            "num": "STEP 10",
            "layer": "LAYER 4: EXECUTION",
            "title": "Delta Execution & SL Verify",
            "color": "#10b981",
            "hdr_bg": "#064e3b",
            "bullets": [
                "• Unique client_order_id on every submission",
                "• Pre-retry history reconciliation on network timeouts",
                "• Mandatory Stop-Loss verification on Delta orderbook",
                "• Immediate emergency market close if SL unverified"
            ],
            "agent": "Agent 7: Execution Engine"
        },
        {
            "num": "STEP 11",
            "layer": "LAYER 5: TRAILING SENTINEL",
            "title": "Micro-Trailing Sentinel",
            "color": "#388bfd",
            "hdr_bg": "#1e3a5f",
            "bullets": [
                "• 15-second high-frequency position monitor",
                "• Stage 1 (+0.80R): Risk slashed 60% (Breathing space)",
                "• Stage 2 (+1.10R): Green profit locked (+0.30R banked)",
                "• Stage 3 (+1.50R): Core +0.85R locked -> Runner trail"
            ],
            "agent": "Agent 8: Trailing Sentinel"
        },
        {
            "num": "STEP 12",
            "layer": "LAYER 6: JOURNAL & LEARNING",
            "title": "SQLite Event Store & Learn",
            "color": "#8b5cf6",
            "hdr_bg": "#3b1d6e",
            "bullets": [
                "• Authoritative SQLite DB (state/trading_journal.db)",
                "• Full lifecycle audit logging from setup to closure",
                "• Postmortem scoring (0-100) and pattern memory",
                "• Agent 10: Dynamic Operating Rules & Rollback guard"
            ],
            "agent": "Agents 9 & 10 + SQLite Journal"
        }
    ]

    for idx, s in enumerate(steps):
        r = idx // cols
        c = idx % cols
        x = x_start + c * (card_w + x_gap)
        y = y_start + r * (card_h + y_gap)

        # Card Box
        d.rounded_rectangle([(x, y), (x + card_w, y + card_h)], radius=14, fill="#161b22", outline=s["color"], width=2)
        
        # Header
        d.rounded_rectangle([(x, y), (x + card_w, y + 54)], radius=14, fill=s["hdr_bg"])
        d.rectangle([(x, y + 30), (x + card_w, y + 54)], fill=s["hdr_bg"])
        
        # Step Tag Pill
        d.rounded_rectangle([(x + 16, y + 12), (x + 115, y + 42)], radius=6, fill="#0d1117", outline=s["color"], width=1)
        d.text((x + 24, y + 15), s["num"], fill=s["color"], font=f_step_num)
        
        # Layer Name
        d.text((x + 130, y + 18), s["layer"], fill="#8b949e", font=f_step_sub)
        
        # Card Title & Agent Subtitle
        d.text((x + 20, y + 68), s["title"], fill="#ffffff", font=f_step_title)
        d.text((x + 20, y + 98), f"Module: {s['agent']}", fill=s["color"], font=f_step_sub)
        
        # Divider
        d.line([(x + 20, y + 122), (x + card_w - 20, y + 122)], fill="#30363d", width=1)

        # Bullets
        by = y + 135
        for b in s["bullets"]:
            d.text((x + 20, by), b, fill="#c9d1d9", font=f_step_body)
            by += 32

        # Draw connecting horizontal arrow to next step in row
        if c < cols - 1:
            arrow_x = x + card_w + 10
            arrow_y = y + (card_h // 2) - 15
            d.text((arrow_x, arrow_y), "➔", fill="#388bfd", font=f_arrow)

    # 3. Footer Bar
    foot_y = y_start + rows * (card_h + y_gap) - 15
    d.rounded_rectangle([(60, foot_y), (w - 60, foot_y + 80)], radius=12, fill="#161b22", outline="#30363d", width=2)
    d.text((90, foot_y + 16), "🛡️ SYSTEM GUARANTEE: ZERO ORDERS DISPATCH WITHOUT 14/14 SAFETY APPROVALS + VALIDATED STOP LOSS ON DELTA EXCHANGE", fill="#10b981", font=f_foot_t)
    d.text((90, foot_y + 45), "Authoritative Execution: All lifecycle milestones stored immutably in SQLite (state/trading_journal.db) • Tests: 16/16 Passing (100%)", fill="#8b949e", font=f_foot_b)

    out_path = r"d:\Project\Multi Agent Trading Bot\end_to_end_workflow.png"
    img.save(out_path, format="PNG", quality=95)
    print("Successfully generated high-resolution workflow diagram at:", out_path)

if __name__ == "__main__":
    generate_workflow()

