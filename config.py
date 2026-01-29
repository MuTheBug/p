"""
Configuration Module for Trendline Strategy Trading Bot

Provides centralized configuration management with environment variable support
and validation. All settings can be overridden via environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


def get_env(key: str, default: Any = None, cast_type: type = str) -> Any:
    """Get environment variable with type casting."""
    value = os.getenv(key, default)
    if value is None:
        return default
    if cast_type == bool:
        return str(value).lower() in ("true", "1", "yes", "on")
    try:
        return cast_type(value)
    except (ValueError, TypeError):
        return default


@dataclass
class BinanceConfig:
    """Binance API configuration."""
    api_key: str = field(default_factory=lambda: get_env("BINANCE_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: get_env("BINANCE_API_SECRET", ""))
    testnet: bool = field(default_factory=lambda: get_env("BINANCE_TESTNET", True, bool))
    recv_window: int = field(default_factory=lambda: get_env("BINANCE_RECV_WINDOW", 5000, int))

    def validate(self) -> bool:
        """Validate Binance configuration."""
        if not self.api_key or not self.api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET are required")
        return True


@dataclass
class TelegramConfig:
    """Telegram notification configuration."""
    bot_token: str = field(default_factory=lambda: get_env("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: get_env("TELEGRAM_CHAT_ID", ""))
    enabled: bool = field(default_factory=lambda: get_env("TELEGRAM_ENABLED", True, bool))
    rate_limit: float = field(default_factory=lambda: get_env("TELEGRAM_RATE_LIMIT", 1.0, float))
    async_mode: bool = field(default_factory=lambda: get_env("TELEGRAM_ASYNC", True, bool))

    def validate(self) -> bool:
        """Validate Telegram configuration."""
        if self.enabled and (not self.bot_token or not self.chat_id):
            raise ValueError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required when enabled"
            )
        return True


@dataclass
class TrendlineConfig:
    """Trendline detection configuration."""
    pivot_lookback: int = field(
        default_factory=lambda: get_env("TRENDLINE_PIVOT_LOOKBACK", 5, int)
    )
    min_touchpoints: int = field(
        default_factory=lambda: get_env("TRENDLINE_MIN_TOUCHPOINTS", 2, int)
    )
    price_tolerance_pct: float = field(
        default_factory=lambda: get_env("TRENDLINE_PRICE_TOLERANCE_PCT", 0.5, float)
    )
    min_time_span_hours: float = field(
        default_factory=lambda: get_env("TRENDLINE_MIN_TIME_SPAN_HOURS", 168, float)
    )


@dataclass
class RiskConfig:
    """Risk management configuration."""
    risk_per_trade_pct: float = field(
        default_factory=lambda: get_env("RISK_PER_TRADE_PCT", 1.0, float)
    )
    max_positions: int = field(
        default_factory=lambda: get_env("MAX_POSITIONS", 3, int)
    )
    leverage: int = field(
        default_factory=lambda: get_env("LEVERAGE", 10, int)
    )
    use_isolated_margin: bool = field(
        default_factory=lambda: get_env("USE_ISOLATED_MARGIN", True, bool)
    )
    max_risk_pct: float = field(
        default_factory=lambda: get_env("MAX_RISK_PCT", 5.0, float)
    )

    def validate(self) -> bool:
        """Validate risk configuration."""
        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 10:
            raise ValueError("RISK_PER_TRADE_PCT must be between 0 and 10")
        if self.leverage < 1 or self.leverage > 125:
            raise ValueError("LEVERAGE must be between 1 and 125")
        if self.max_positions < 1:
            raise ValueError("MAX_POSITIONS must be at least 1")
        return True


@dataclass
class TradingConfig:
    """Trading strategy configuration."""
    # Timeframe
    timeframe: str = field(
        default_factory=lambda: get_env("TIMEFRAME", "4h")
    )
    kline_limit: int = field(
        default_factory=lambda: get_env("KLINE_LIMIT", 500, int)
    )

    # Entry settings
    entry_buffer_pct: float = field(
        default_factory=lambda: get_env("ENTRY_BUFFER_PCT", 0.1, float)
    )
    stop_loss_buffer_pct: float = field(
        default_factory=lambda: get_env("STOP_LOSS_BUFFER_PCT", 0.5, float)
    )

    # Setup preferences
    enable_bounce_setups: bool = field(
        default_factory=lambda: get_env("ENABLE_BOUNCE_SETUPS", True, bool)
    )
    enable_break_2pt_setups: bool = field(
        default_factory=lambda: get_env("ENABLE_BREAK_2PT_SETUPS", True, bool)
    )
    enable_break_3pt_setups: bool = field(
        default_factory=lambda: get_env("ENABLE_BREAK_3PT_SETUPS", True, bool)
    )
    min_confidence: float = field(
        default_factory=lambda: get_env("MIN_CONFIDENCE", 0.6, float)
    )

    # Trailing stop
    enable_trailing_stop: bool = field(
        default_factory=lambda: get_env("ENABLE_TRAILING_STOP", True, bool)
    )
    trail_update_interval_hours: float = field(
        default_factory=lambda: get_env("TRAIL_UPDATE_INTERVAL_HOURS", 4, float)
    )

    # Take profit
    take_profit_rr_ratio: Optional[float] = field(
        default_factory=lambda: get_env("TAKE_PROFIT_RR_RATIO", None, float)
    )

    # Monitoring
    check_interval_seconds: int = field(
        default_factory=lambda: get_env("CHECK_INTERVAL_SECONDS", 60, int)
    )
    price_near_line_pct: float = field(
        default_factory=lambda: get_env("PRICE_NEAR_LINE_PCT", 1.0, float)
    )

    # Auto trading
    auto_trade: bool = field(
        default_factory=lambda: get_env("AUTO_TRADE", False, bool)
    )


@dataclass
class BotConfig:
    """Complete bot configuration."""
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    trendline: TrendlineConfig = field(default_factory=TrendlineConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)

    # Symbols to trade
    symbols: List[str] = field(
        default_factory=lambda: get_env(
            "TRADING_SYMBOLS", "BTCUSDT,ETHUSDT"
        ).split(",")
    )

    def validate(self) -> bool:
        """Validate all configurations."""
        self.binance.validate()
        if self.telegram.enabled:
            self.telegram.validate()
        self.risk.validate()
        return True

    def to_strategy_config(self) -> Dict[str, Any]:
        """Convert to strategy configuration dictionary."""
        return {
            # Trendline detection
            "pivot_lookback": self.trendline.pivot_lookback,
            "min_touchpoints": self.trendline.min_touchpoints,
            "price_tolerance_pct": self.trendline.price_tolerance_pct,
            "min_time_span_hours": self.trendline.min_time_span_hours,

            # Timeframe
            "timeframe": self.trading.timeframe,
            "kline_limit": self.trading.kline_limit,

            # Risk management
            "risk_per_trade_pct": self.risk.risk_per_trade_pct,
            "max_positions": self.risk.max_positions,
            "leverage": self.risk.leverage,
            "use_isolated_margin": self.risk.use_isolated_margin,

            # Entry settings
            "entry_buffer_pct": self.trading.entry_buffer_pct,
            "stop_loss_buffer_pct": self.trading.stop_loss_buffer_pct,

            # Setup preferences
            "enable_bounce_setups": self.trading.enable_bounce_setups,
            "enable_break_2pt_setups": self.trading.enable_break_2pt_setups,
            "enable_break_3pt_setups": self.trading.enable_break_3pt_setups,
            "min_confidence": self.trading.min_confidence,

            # Trailing stop
            "enable_trailing_stop": self.trading.enable_trailing_stop,
            "trail_update_interval_hours": self.trading.trail_update_interval_hours,

            # Monitoring
            "check_interval_seconds": self.trading.check_interval_seconds,
            "price_near_line_pct": self.trading.price_near_line_pct,

            # Take profit
            "take_profit_rr_ratio": self.trading.take_profit_rr_ratio,
        }


def load_config() -> BotConfig:
    """Load and validate configuration from environment."""
    config = BotConfig()
    config.validate()
    return config


# Default configuration for quick access
DEFAULT_CONFIG = {
    # Trendline detection
    "pivot_lookback": 5,
    "min_touchpoints": 2,
    "price_tolerance_pct": 0.5,
    "min_time_span_hours": 168,  # 1 week

    # Timeframe
    "timeframe": "4h",
    "kline_limit": 500,

    # Risk management
    "risk_per_trade_pct": 1.0,
    "max_positions": 3,
    "leverage": 10,
    "use_isolated_margin": True,

    # Entry settings
    "entry_buffer_pct": 0.1,
    "stop_loss_buffer_pct": 0.5,

    # Setup preferences
    "enable_bounce_setups": True,
    "enable_break_2pt_setups": True,
    "enable_break_3pt_setups": True,
    "min_confidence": 0.6,

    # Trailing stop
    "enable_trailing_stop": True,
    "trail_update_interval_hours": 4,

    # Monitoring
    "check_interval_seconds": 60,
    "price_near_line_pct": 1.0,

    # Take profit
    "take_profit_rr_ratio": 2.0,  # 2:1 risk-reward
}


# Environment variable template for reference
ENV_TEMPLATE = """
# Binance API Configuration
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true
BINANCE_RECV_WINDOW=5000

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TELEGRAM_ENABLED=true
TELEGRAM_RATE_LIMIT=1.0
TELEGRAM_ASYNC=true

# Trading Symbols (comma-separated)
TRADING_SYMBOLS=BTCUSDT,ETHUSDT

# Trendline Detection
TRENDLINE_PIVOT_LOOKBACK=5
TRENDLINE_MIN_TOUCHPOINTS=2
TRENDLINE_PRICE_TOLERANCE_PCT=0.5
TRENDLINE_MIN_TIME_SPAN_HOURS=168

# Risk Management
RISK_PER_TRADE_PCT=1.0
MAX_POSITIONS=3
LEVERAGE=10
USE_ISOLATED_MARGIN=true
MAX_RISK_PCT=5.0

# Trading Settings
TIMEFRAME=4h
KLINE_LIMIT=500
ENTRY_BUFFER_PCT=0.1
STOP_LOSS_BUFFER_PCT=0.5
ENABLE_BOUNCE_SETUPS=true
ENABLE_BREAK_2PT_SETUPS=true
ENABLE_BREAK_3PT_SETUPS=true
MIN_CONFIDENCE=0.6
ENABLE_TRAILING_STOP=true
TRAIL_UPDATE_INTERVAL_HOURS=4
TAKE_PROFIT_RR_RATIO=2.0
CHECK_INTERVAL_SECONDS=60
PRICE_NEAR_LINE_PCT=1.0
AUTO_TRADE=false
"""
