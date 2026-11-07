import os
import sys
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

pdf_out = r"D:\Project\Multi Agent Trading Bot\Delta_Exchange_MultiAgent_Trading_System_Documentation.pdf"
docs_pdf_out = r"D:\Project\Multi Agent Trading Bot\docs\Delta_Exchange_MultiAgent_Trading_System_Documentation.pdf"
artifact_pdf_out = r"C:\Users\DELL\.gemini\antigravity\brain\84b64d4a-5947-4739-a58e-3523f1ee3dea\Delta_Exchange_MultiAgent_Trading_System_Documentation.pdf"


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Do not draw running header on cover/first page
        if self._pageNumber > 1:
            self.drawString(36, 11 * inch - 30, "Delta Exchange Multi-Agent Trading System — Complete Technical Documentation")
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.5)
            self.line(36, 11 * inch - 34, 8.5 * inch - 36, 11 * inch - 34)

        # Running footer on all pages
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(36, 36, 8.5 * inch - 36, 36)

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * inch - 36, 24, page_str)
        self.drawString(36, 24, "CONFIDENTIAL & PROPRIETARY — DELTA EXCHANGE INSTITUTIONAL BOT")
        self.restoreState()


def create_pdf():
    doc = SimpleDocTemplate(
        pdf_out,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#ffffff')
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#94a3b8')
    )

    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=16,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#0369a1'),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    h3_style = ParagraphStyle(
        'H3',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=4
    )

    callout_style = ParagraphStyle(
        'Callout',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )

    code_style = ParagraphStyle(
        'Code',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#0f172a')
    )

    th_style = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#ffffff')
    )

    td_style = ParagraphStyle(
        'TD',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1e293b')
    )

    story = []

    # -------------------------------------------------------------
    # COVER BANNER
    # -------------------------------------------------------------
    banner_data = [
        [
            Paragraph("<b>DELTA EXCHANGE MULTI-AGENT TRADING SYSTEM</b>", title_style)
        ],
        [
            Paragraph("Complete End-to-End Architectural &amp; Operational Documentation", subtitle_style)
        ],
        [
            Paragraph(
                "<font color='#38bdf8'><b>Version:</b> 2.5.0 Institutional</font> &nbsp;|&nbsp; "
                "<font color='#ffffff'><b>Architecture:</b> 10 Agents / 6 Layers</font> &nbsp;|&nbsp; "
                "<font color='#ffffff'><b>Exchange:</b> Delta Exchange India</font> &nbsp;|&nbsp; "
                "<font color='#38bdf8'><b>R:R Target:</b> &ge; 2.5:1</font>",
                callout_style
            )
        ]
    ]
    banner_table = Table(banner_data, colWidths=[540])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0,0), (-1,-1), 16),
        ('BOTTOMPADDING', (0,0), (-1,-1), 16),
        ('LEFTPADDING', (0,0), (-1,-1), 20),
        ('RIGHTPADDING', (0,0), (-1,-1), 20),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 14))

    # -------------------------------------------------------------
    # 1. EXECUTIVE OVERVIEW
    # -------------------------------------------------------------
    story.append(Paragraph("1. Executive Overview &amp; Design Philosophy", h1_style))
    story.append(Paragraph(
        "The <b>Delta Exchange Multi-Agent Trading System</b> is an institutional-grade algorithmic trading architecture "
        "designed specifically for crypto perpetual swaps and futures. Rather than relying on a single fallible model or "
        "rigid rule set, the platform divides the full quantitative trading lifecycle among <b>10 specialized autonomous AI agents</b> "
        "operating across <b>6 hierarchical layers</b>.",
        body_style
    ))

    # Executive Principles Callout Box
    core_tenets = [
        [Paragraph("<b>CORE OPERATIONAL TENETS</b>", ParagraphStyle('BTitle', parent=th_style, textColor=colors.HexColor('#0f172a')))],
        [Paragraph("• <b>Asymmetric Risk/Reward (&ge; 2.5:1)</b>: Every trade proposal must mathematically target at least 2.5 times the risked capital.", bullet_style)],
        [Paragraph("• <b>Strict Sniper Selectivity (Floor &ge; 85/100)</b>: 'Take fewer trades, but higher-conviction trades for maximum net profit.' Zero trades in neutral chop.", bullet_style)],
        [Paragraph("• <b>Mandatory Bracket Protection</b>: Every order placed on Delta Exchange is submitted with simultaneous, hard Stop Loss and Take Profit child orders.", bullet_style)],
        [Paragraph("• <b>Milestone Trailing Stop Schedule</b>: Eliminates the 'breakeven trap' by cutting downside risk by 60% at +0.8R (leaves 1.2R+ cushion), then locking +0.3R green profit at +1.1R.", bullet_style)],
        [Paragraph("• <b>Continuous Self-Auditing Memory</b>: Every closed trade is reflected on, graded (A+ to F), and used to update persistent pattern win/loss memory.", bullet_style)]
    ]
    ct_table = Table(core_tenets, colWidths=[540])
    ct_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#0284c7')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(ct_table)
    story.append(Spacer(1, 14))

    # -------------------------------------------------------------
    # 2. 6-LAYER HIERARCHY
    # -------------------------------------------------------------
    story.append(Paragraph("2. System Architecture &amp; 6-Layer Hierarchy", h1_style))
    story.append(Paragraph(
        "The system enforces strict directional separation of concerns. Data and decisions flow through six sequential layers:",
        body_style
    ))

    layer_summary_data = [
        [Paragraph("Layer", th_style), Paragraph("Component / Agents", th_style), Paragraph("Primary Core Function", th_style)],
        [
            Paragraph("<b>Layer 1</b><br/>Market Intelligence", td_style),
            Paragraph("• MarketDataValidator<br/>• Agent 1: RegimeAnalyst<br/>• Agent 2: ExposureCoach", td_style),
            Paragraph("Validates live feed sanity, maps 6-timeframe structure (15m to Monthly), detects SMC liquidity sweeps, and scores cross-asset market breadth health (0-100).", td_style)
        ],
        [
            Paragraph("<b>Layer 2</b><br/>Alpha &amp; Validation", td_style),
            Paragraph("• Agent 3: StrategyAgent<br/>• Agent 4: TimeMachineAgent", td_style),
            Paragraph("Generates IVL setups scoring &ge; 85/100; forward-simulates setups across 400 historical candles; verifies positive expected value (EV &ge; +0.35R).", td_style)
        ],
        [
            Paragraph("<b>Layer 3</b><br/>Risk Governance", td_style),
            Paragraph("• Agent 5: RiskGatekeeper<br/>• RiskManager Engine", td_style),
            Paragraph("Enforces fixed dollar risk ($2-$4 USD), conviction multipliers (up to 2.0x for A+ setups), max 2 correlated crypto positions, and liquidation buffer (&ge; 3x SL).", td_style)
        ],
        [
            Paragraph("<b>Layer 4</b><br/>Execution &amp; Management", td_style),
            Paragraph("• Agent 6: ExecutionAgent<br/>• Agent 7: TrailingStopManager<br/>• Agent 8: PortfolioMonitor", td_style),
            Paragraph("Submits bracket limit orders with idempotency; manages multi-stage trailing SL (+0.8R risk cut, +1.1R green lock, +1.5R, +2.5R TP); reconciles journal fills.", td_style)
        ],
        [
            Paragraph("<b>Layer 5</b><br/>Learning &amp; Optimization", td_style),
            Paragraph("• Agent 9: AdaptiveLearningEngine<br/>• Agent 10: PerformanceCoach", td_style),
            Paragraph("Conducts post-trade post-mortem reflection; grades trades (A+ to F); reinforces winning patterns (+10 pts) and blacklists failing ones; audits rule degradation.", td_style)
        ],
        [
            Paragraph("<b>Layer 6</b><br/>Infrastructure &amp; Protocol", td_style),
            Paragraph("• Orchestrator<br/>• DeltaExchangeClient<br/>• DeltaMCPServer<br/>• TelegramBot", td_style),
            Paragraph("Direct HMAC-SHA256 REST API communications; Model Context Protocol (MCP) server; 2-way Telegram confirmation approval buttons; emergency killswitch.", td_style)
        ]
    ]
    l_table = Table(layer_summary_data, colWidths=[90, 150, 300])
    l_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(l_table)
    story.append(Spacer(1, 14))

    # -------------------------------------------------------------
    # 3. EXHAUSTIVE AGENT BREAKDOWN
    # -------------------------------------------------------------
    story.append(Paragraph("3. Detailed Tasks of Every Agent &amp; Engine", h1_style))

    agents_data = [
        ("Agent 1: Multi-Timeframe Regime Analyst", "multiagent_team/regime_analyst.py", [
            "Synchronizes 6 distinct timeframes (15m, 1H, 4H, Daily, Weekly, Monthly) to eliminate single-timeframe bias.",
            "Calculates EMA ribbons (9, 21, 50, 200), RSI(14), ATR(14), MACD(12,26,9), and ADX(14) trend strength.",
            "Detects Smart Money Concepts (SMC): Buy-Side Liquidity (BSL) and Sell-Side Liquidity (SSL) pivot sweeps.",
            "Validates Market Structure Shifts (MSS) to ensure displacement confirms reversals before entering.",
            "Classifies candlestick patterns (Pinbars, Engulfing, Doji) and chart patterns (Double Tops/Bottoms, Trendline Slopes)."
        ]),
        ("Agent 2: Exposure Coach & Cross-Asset Breadth", "multiagent_team/exposure_coach.py", [
            "Computes universe Market Breadth: % of assets trading above their 21-period EMA.",
            "Monitors perpetual swap funding rates to detect extreme crowd crowding and squeeze risks.",
            "Synthesizes cross-asset metrics into a deterministic Market Health score (0-100).",
            "Determines Market Posture: AGGRESSIVE_EXPANSION (Health &ge; 75), MODERATE_SELECTIVE (50-74), DEFENSIVE_CAUTION (32-49), CASH_PRIORITY (< 32, zero new trades authorized).",
            "Engages RECOVERY_POSTURE after &ge; 2 consecutive stop-outs, slashing risk to 50% ($2.00 max risk) and clamping concurrency to 1."
        ]),
        ("Agent 3: Alpha & Strategy Generator", "multiagent_team/strategy_agent.py", [
            "Evaluates setups against hard veto gates: major economic news, wide bid-ask spread (> 0.15%), or price drift (> 0.50%).",
            "Prioritizes the battle-tested Institutional Liquidity Sweep & Absorption (IVL) strategy.",
            "Enforces strict Sniper Quality Floor: minimum score &ge; 85/100 for primary assets (BTC, ETH, XAU) and &ge; 90/100 for secondary altcoins.",
            "Generates trade setup specifications with entry price, structural stop loss, and take profit targeting &ge; 2.5:1 R:R."
        ]),
        ("Agent 4: Time Machine Probability Engine", "multiagent_team/time_machine_agent.py", [
            "Simulates proposed setups backwards across 400 historical candles under identical market conditions.",
            "Deducts realistic institutional friction: taker fees (0.10% round-trip), slippage (0.06%), and funding drag.",
            "Calculates the Wilson Score 95% Confidence Interval lower bound to prevent small-sample statistical illusions.",
            "Enforces an empirical expected value hurdle: requires EV &ge; +0.35R and historical win rate &ge; 70%."
        ]),
        ("Agent 5: Risk & Discipline Gatekeeper", "multiagent_team/risk_gatekeeper.py", [
            "Applies a fixed dollar risk sizing model ($2.00 to $4.00 USD), scaling to 75%-100% available capital when safe.",
            "Executes Conviction Sizing: Tier 1 (A+ Prime Conviction) gets up to 2.0x contract boost on primary assets.",
            "Enforces Correlated Exposure Limits: maximum 2 open positions on the same side of correlated crypto assets.",
            "Verifies Liquidation Armor: confirms liquidation price is at least 3x farther than stop loss distance.",
            "Applies Drawdown Scaling: automatically scales position sizing down by 30% if drawdown exceeds 2%."
        ]),
        ("Agent 6: Execution & Orderbook Engine", "multiagent_team/execution_agent.py", [
            "Translates approved trade decisions into signed bracket orders on Delta Exchange.",
            "Applies idempotency tokens (client_order_id) to prevent duplicate execution during network retries.",
            "Submits limit entry with slippage guards alongside native Stop Loss and Take Profit child orders.",
            "Executes post-fill verification: if an entry fills without a confirmed Stop Loss order, it immediately submits an emergency protective stop."
        ]),
        ("Agent 7: Trailing Stop Loss & Profit Sentinel", "src/trailing_stop_manager.py", [
            "Continuously monitors live position mark prices against entry price and risk units.",
            "Milestone 1 (+0.8R to +0.9R): Slashes risk by 60% (moves SL to -0.40R), leaving 1.2R+ breathing space to avoid breakeven traps.",
            "Milestone 2 (+1.1R to +1.2R): Locks in guaranteed positive green profit (+0.30R), ensuring trade cannot exit at $0 breakeven.",
            "Milestone 3 (+1.5R to +1.6R): Advances stop to lock +0.85R profit.",
            "Milestone 4 (+2.5R to +2.6R): Executes full Take Profit target.",
            "Engages High-Volatility Buffer: widens trailing thresholds during expansion regimes to prevent stop hunting."
        ]),
        ("Agent 8: Portfolio Monitor & Memory Journaler", "multiagent_team/portfolio_monitor.py", [
            "Polls active Delta Exchange positions, liquidation margins, and unrealized PnL.",
            "Reconciles closed fills and writes complete trade ledgers to state/trade_journal.json.",
            "Generates daily and weekly performance digests summarizing win rate, profit factor, and net PnL."
        ]),
        ("Agent 9: Adaptive Learning & Pattern Diagnosis", "multiagent_team/adaptive_learning.py", [
            "Conducts an automated post-mortem audit after every closed trade.",
            "Assigns institutional letter grades (A+ to F) and self-scores execution discipline.",
            "Diagnoses exact root causes of wins and losses via feature attribution.",
            "Maintains persistent memory in pattern_learning_memory.json: awards +10 pt bonuses to winning patterns and blacklists failing ones."
        ]),
        ("Agent 10: Performance Coach & Operating Rules", "multiagent_team/performance_coach.py", [
            "Tracks planned vs. actual execution variance and slippage drag.",
            "Monitors trailing win rates over 5-trade cohorts; triggers safety rollbacks if win rate drops below 20%.",
            "Maintains version-controlled active operating rules in state/active_operating_rules.json."
        ])
    ]

    for title, filepath, tasks in agents_data:
        story.append(Paragraph(f"<b>{title}</b>", h2_style))
        story.append(Paragraph(f"<i>Source: {filepath}</i>", ParagraphStyle('SubSrc', parent=body_style, textColor=colors.HexColor('#64748b'), fontSize=8.5)))
        for t in tasks:
            story.append(Paragraph(f"• {t}", bullet_style))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 10))

    # -------------------------------------------------------------
    # 4. PROPRIETARY STRATEGY (IVL)
    # -------------------------------------------------------------
    story.append(Paragraph("4. The Proprietary Strategy: Institutional Volatility-Liquidity (IVL) Absorption", h1_style))
    story.append(Paragraph(
        "The system's core edge is the <b>IVL (Institutional Volatility-Liquidity Absorption &amp; Value Retest)</b> strategy. "
        "Rigorous backtesting across 1,920 15m historical candles on Delta Exchange confirmed <b>56.2% - 59.4% Win Rate, "
        "1.53x - 1.71x Profit Factor, and +6.34R to +8.39R Net Profit</b> with 0.08R fee/slippage friction deducted per trade.",
        body_style
    ))

    strat_rules_data = [
        [Paragraph("Rule Component", th_style), Paragraph("Mathematical Trigger &amp; Logic", th_style), Paragraph("Purpose &amp; Failure It Prevents", th_style)],
        [
            Paragraph("<b>1. Coiled Volatility</b>", td_style),
            Paragraph("ATR(14) &le; 1.05 &times; SMA30(ATR)", td_style),
            Paragraph("Ensures energy is coiled before expansion; avoids buying into exhausted blowoff moves.", td_style)
        ],
        [
            Paragraph("<b>2. Volume Absorption</b>", td_style),
            Paragraph("Volume &ge; 1.20 &times; SMA20(Volume)", td_style),
            Paragraph("Confirms whale and institutional accumulation rather than low-volume retail drift.", td_style)
        ],
        [
            Paragraph("<b>3. Liquidity Pivot Sweep</b>", td_style),
            Paragraph("Price sweeps 10-12 bar swing extreme, closes back inside range", td_style),
            Paragraph("Exploits retail breakout traps; enters when market makers reverse after grabbing stop orders.", td_style)
        ],
        [
            Paragraph("<b>4. Absorption Wick</b>", td_style),
            Paragraph("Lower wick &ge; 40% (Buy) or Upper wick &ge; 40% (Sell)", td_style),
            Paragraph("Proves aggressive price rejection and value retest.", td_style)
        ],
        [
            Paragraph("<b>5. Macro Confluence</b>", td_style),
            Paragraph("EMA21/50 stack &amp; Price vs. EMA200", td_style),
            Paragraph("Never trades against higher-timeframe momentum; aligns with 1H/4H trend.", td_style)
        ],
        [
            Paragraph("<b>6. Structural Noise Buffer</b>", td_style),
            Paragraph("SL &ge; 0.35% for BTCUSD | SL &ge; 0.25% for ETHUSD (Max 0.65%)", td_style),
            Paragraph("Prevents normal 15m ATR random walk ($300-$500 on $80k BTC) from choking trades prematurely.", td_style)
        ],
        [
            Paragraph("<b>7. Milestone Trailing SL</b>", td_style),
            Paragraph("At +0.8R: SL to -0.4R (cut risk 60%)<br/>At +1.1R: SL to +0.3R (lock green)", td_style),
            Paragraph("Eliminates breakeven stops while protecting capital and letting runners hit +2.5R to +2.6R target.", td_style)
        ]
    ]
    s_table = Table(strat_rules_data, colWidths=[120, 180, 240])
    s_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(s_table)
    story.append(Spacer(1, 14))

    # -------------------------------------------------------------
    # 5. CLI & OPERATIONAL GUIDE
    # -------------------------------------------------------------
    story.append(Paragraph("5. Execution Commands &amp; Operational Guide", h1_style))

    cli_data = [
        [Paragraph("Operational Mode", th_style), Paragraph("Command Line", th_style), Paragraph("Description", th_style)],
        [
            Paragraph("<b>Interactive Mode</b><br/>(Recommended)", td_style),
            Paragraph("<code>python main.py trade --symbols BTCUSD,ETHUSD --leverage 25</code>", code_style),
            Paragraph("Scans markets, calculates sizing, dispatches approval cards with inline buttons to Telegram and terminal before executing.", td_style)
        ],
        [
            Paragraph("<b>24/7 Scanner Loop</b>", td_style),
            Paragraph("<code>python run_247_scanner.py --symbols BTCUSD,ETHUSD --interval 120</code>", code_style),
            Paragraph("Autonomous background loop executing periodic multi-timeframe scans, trailing stop updates, and state reconciliation.", td_style)
        ],
        [
            Paragraph("<b>One-Time Scan</b>", td_style),
            Paragraph("<code>python main.py scan --symbols BTCUSD,ETHUSD</code>", code_style),
            Paragraph("Single inspection cycle printing market regime, liquidity sweeps, and qualified alpha setups without placing orders.", td_style)
        ],
        [
            Paragraph("<b>MCP Server</b>", td_style),
            Paragraph("<code>python main.py mcp</code>", code_style),
            Paragraph("Launches the Model Context Protocol server exposing Delta Exchange tools to AI assistants (Claude, Cursor, Antigravity).", td_style)
        ],
        [
            Paragraph("<b>Daily Digest</b>", td_style),
            Paragraph("<code>python main.py digest</code>", code_style),
            Paragraph("Generates an executive performance summary of completed trades, realized PnL, win rates, and fee drag.", td_style)
        ],
        [
            Paragraph("<b>Connectivity Test</b>", td_style),
            Paragraph("<code>python main.py test</code>", code_style),
            Paragraph("Tests Delta Exchange API authentication, HMAC-SHA256 signature generation, and live wallet balances.", td_style)
        ]
    ]
    cli_table = Table(cli_data, colWidths=[110, 230, 200])
    cli_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(cli_table)
    story.append(Spacer(1, 14))

    # -------------------------------------------------------------
    # 6. SAFETY & STATE FILES
    # -------------------------------------------------------------
    story.append(Paragraph("6. Safety Controls, Failsafes &amp; State Files", h1_style))
    story.append(Paragraph(
        "The system persists all historical actions in human-readable JSON files in the <code>state/</code> directory:",
        body_style
    ))
    story.append(Paragraph("• <b>state/trade_journal.json</b>: Master ledger of every trade entry, exit price, R-multiple captured, and net realized PnL.", bullet_style))
    story.append(Paragraph("• <b>state/trailing_stop_state.json</b>: Real-time tracking of active positions, trailing stop stages, and parent/child order IDs.", bullet_style))
    story.append(Paragraph("• <b>state/pattern_learning_memory.json</b>: Agent 9's dynamic pattern memory, win/loss scores, and active pattern bonuses/penalties.", bullet_style))
    story.append(Paragraph("• <b>state/active_operating_rules.json</b>: Agent 10's version-controlled institutional operating rules and safety parameters.", bullet_style))
    story.append(Paragraph("• <b>state/system_state.json</b>: Portfolio health scores, daily drawdown counters, and circuit breaker status.", bullet_style))

    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Built-In Failsafe Safeguards:</b>", h2_style))
    story.append(Paragraph("• <b>3.0% Max Daily Drawdown Circuit Breaker</b>: Halts all new orders immediately if daily losses reach 3.0% of portfolio equity.", bullet_style))
    story.append(Paragraph("• <b>Orphan Bracket Order Cleanup</b>: Automatically cancels leftover stop-loss or take-profit orders when a position closes, eliminating rogue fills.", bullet_style))
    story.append(Paragraph("• <b>Liquidation Armor</b>: Guarantees liquidation distance is &ge; 3x the stop-loss distance, preventing liquidation under all circumstances.", bullet_style))
    story.append(Paragraph("• <b>Emergency Killswitch</b>: Available in terminal or Telegram to instantly cancel all open orders and market-close all positions in 1 click.", bullet_style))

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully compiled at: {pdf_out} (Size: {os.path.getsize(pdf_out)} bytes)")

    import shutil
    shutil.copy2(pdf_out, docs_pdf_out)
    print(f"Copied to: {docs_pdf_out}")
    shutil.copy2(pdf_out, artifact_pdf_out)
    print(f"Copied to: {artifact_pdf_out}")

if __name__ == '__main__':
    create_pdf()
