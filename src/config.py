"""
Central Validated Configuration Engine for Delta Exchange Multi-Agent Quantitative Bot.
All settings are loaded deterministically from environment variables with strict typing,
safe defaults, and zero hardcoded secrets.
"""

import os
from typing import List, Optional
# pyrefly: ignore[missing-import]
from pydantic import BaseModel, Field, field_validator
# pyrefly: ignore[missing-import]
from dotenv import load_dotenv

load_dotenv()


class SystemConfig(BaseModel):
    # -------------------------------------------------------------------------
    # 1. Delta Exchange API Credentials & Connectivity
    # -------------------------------------------------------------------------
    delta_environment: str = Field(
        default_factory=lambda: os.getenv("DELTA_ENVIRONMENT", "production").lower()
    )
    delta_api_key: str = Field(
        default_factory=lambda: os.getenv("DELTA_API_KEY", "").strip()
    )
    delta_api_secret: str = Field(
        default_factory=lambda: os.getenv("DELTA_API_SECRET", "").strip()
    )
    delta_base_url: str = Field(
        default_factory=lambda: os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange").strip()
    )
    request_timeout: int = Field(default=10, ge=3, le=60)

    # -------------------------------------------------------------------------
    # 2. Hard Risk Limits (Non-Negotiable Absolute Ceilings)
    # -------------------------------------------------------------------------
    max_risk_per_trade_pct: float = Field(
        default_factory=lambda: float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.02")),
        ge=0.001,
        le=0.05,
        description="Max percentage of total equity risked on a single trade (0.1% to 5.0%)"
    )
    max_dollar_risk_per_trade: float = Field(
        default_factory=lambda: float(os.getenv("MAX_DOLLAR_RISK_PER_TRADE", "25.00")),
        ge=0.50,
        le=500.0,
        description="Absolute hard dollar cap on any single trade loss"
    )
    max_daily_drawdown_pct: float = Field(
        default_factory=lambda: float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.03")),
        ge=0.01,
        le=0.10,
        description="Daily drawdown circuit breaker threshold (default: 3%)"
    )
    max_weekly_drawdown_pct: float = Field(
        default_factory=lambda: float(os.getenv("MAX_WEEKLY_DRAWDOWN_PCT", "0.05")),
        ge=0.02,
        le=0.20,
        description="Weekly drawdown circuit breaker threshold (default: 5%)"
    )
    max_monthly_drawdown_pct: float = Field(
        default_factory=lambda: float(os.getenv("MAX_MONTHLY_DRAWDOWN_PCT", "0.08")),
        ge=0.03,
        le=0.30,
        description="Monthly drawdown emergency halt threshold (default: 8%)"
    )
    max_consecutive_losses: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3")),
        ge=1,
        le=10,
        description="Consecutive stop losses triggering cooldown mode"
    )
    cooldown_seconds: int = Field(
        default_factory=lambda: int(os.getenv("COOLDOWN_SECONDS", "1800")),
        ge=300,
        le=86400,
        description="Cooldown duration in seconds after loss streaks"
    )
    max_portfolio_concurrency: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_POSITIONS", "2")),
        ge=1,
        le=5,
        description="Maximum simultaneous open positions across the portfolio"
    )
    max_correlated_positions: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CORRELATED_POSITIONS", "2")),
        ge=1,
        le=3,
        description="Maximum same-side concurrent positions on correlated crypto assets"
    )
    max_allowed_leverage: int = Field(
        default_factory=lambda: int(os.getenv("MAX_ALLOWED_LEVERAGE", "50")),
        ge=1,
        le=100,
        description="Absolute hard cap on leverage multiplier"
    )
    min_reward_to_risk: float = Field(
        default_factory=lambda: float(os.getenv("MIN_REWARD_TO_RISK", "2.2")),
        ge=1.5,
        le=10.0,
        description="Minimum planned R:R ratio required for trade qualification"
    )
    liquidation_buffer_multiple: float = Field(
        default=3.0,
        ge=2.5,
        le=10.0,
        description="Estimated liquidation distance must be at least Nx the stop distance"
    )

    # -------------------------------------------------------------------------
    # 3. Telegram Security & Human-in-the-Loop Governance
    # -------------------------------------------------------------------------
    telegram_bot_token: Optional[str] = Field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    )
    telegram_chat_id: Optional[str] = Field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    )
    authorized_user_ids: List[int] = Field(default_factory=list)
    approval_expiry_seconds: int = Field(
        default_factory=lambda: int(os.getenv("APPROVAL_EXPIRY_SECONDS", "300")),
        ge=60,
        le=900,
        description="Time limit for manual Telegram trade confirmation"
    )
    max_price_drift_pct: float = Field(
        default=1.00,
        ge=0.10,
        le=3.0,
        description="Max permitted price drift between proposal and execution approval"
    )
    data_freshness_max_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Max age of live ticker/candle data allowed before order authorization"
    )

    # -------------------------------------------------------------------------
    # 4. Quantitative Backtesting & Time Machine Engine
    # -------------------------------------------------------------------------
    tm_min_win_rate_pct: float = Field(default=65.0, ge=50.0, le=95.0)
    tm_min_expected_value_r: float = Field(default=0.35, ge=0.10, le=2.0)
    tm_min_sample_size: int = Field(default=6, ge=4, le=100)
    tm_lookback_candles: int = Field(default=400, ge=100, le=2000)
    tm_max_simulation_bars: int = Field(default=48, ge=12, le=200)

    # -------------------------------------------------------------------------
    # 5. Trading Universe & Asset Scope
    # -------------------------------------------------------------------------
    default_symbols: List[str] = Field(
        default_factory=lambda: [
            s.strip().upper()
            for s in os.getenv("DEFAULT_SYMBOLS", "BTCUSD,ETHUSD,XAUUSD,PAXGUSD,XAUTUSD,SOLUSD,XRPUSD,DOGEUSD,ADAUSD").split(",")
            if s.strip()
        ]
    )

    @property
    def approved_symbols(self) -> List[str]:
        return self.default_symbols

    @field_validator("authorized_user_ids", mode="before")
    @classmethod
    def parse_authorized_users(cls, v):
        if isinstance(v, list):
            return [int(x) for x in v if str(x).strip().lstrip('-').isdigit()]
        env_val = os.getenv("AUTHORIZED_TELEGRAM_USERS", "")
        chat_id_val = os.getenv("TELEGRAM_CHAT_ID", "")
        user_ids = set()
        if env_val:
            for item in env_val.split(","):
                item_clean = item.strip()
                if item_clean.lstrip('-').isdigit():
                    user_ids.add(int(item_clean))
        if chat_id_val and chat_id_val.strip().lstrip('-').isdigit():
            user_ids.add(int(chat_id_val.strip()))
        return list(user_ids)

    @property
    def is_telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def is_api_configured(self) -> bool:
        return bool(self.delta_api_key and self.delta_api_secret)


# Global singleton configuration instance
config = SystemConfig()
system_config = config
