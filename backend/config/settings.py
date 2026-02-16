"""
Trading System Configuration
All parameters are configurable for backtesting and optimization
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from enum import Enum

class TimeFrame(Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D"


class ATSStrategy(Enum):
    """ATS exit strategy types from the Strategy Guide"""
    STANDARD = "standard"        # Strategy 1: SL=swing, 50% at 2R, rest at ATS color flip
    AGGRESSIVE = "aggressive"    # Strategy 2: SL=trend-bar, full exit at 10R
    SCALING = "scaling"          # Strategy 3: SL=swing, add at 1R, tighten SL, exit at 3R
    DPL = "dpl"                  # Strategy 4: SL=swing, 1/3 at DPL1, 1/3 at DPL2, rest at color flip


@dataclass
class TradingPairs:
    """Allowed trading pairs - major pairs only"""
    ALLOWED_PAIRS: List[str] = field(default_factory=lambda: [
        "EUR_USD", "USD_JPY", "GBP_USD", "AUD_USD", 
        "NZD_USD", "USD_CHF", "USD_CAD"
    ])
    
    # Positive correlations (move same direction) - avoid same direction trades
    # Format: (pair1, pair2, correlation_coefficient)
    POSITIVE_CORRELATIONS: List[Tuple[str, str, float]] = field(default_factory=lambda: [
        ("EUR_USD", "GBP_USD", 0.91),
        ("EUR_USD", "AUD_USD", 0.79),
        ("GBP_USD", "AUD_USD", 0.74),
        ("GBP_USD", "NZD_USD", 0.73),
        ("AUD_USD", "NZD_USD", 0.85),  # Added - very high correlation
        ("USD_CHF", "USD_CAD", 0.81),
    ])
    
    # Negative correlations (move opposite direction) - avoid opposite direction trades
    NEGATIVE_CORRELATIONS: List[Tuple[str, str, float]] = field(default_factory=lambda: [
        ("EUR_USD", "USD_CHF", -0.99),
        ("EUR_USD", "USD_CAD", -0.82),
        ("GBP_USD", "USD_CHF", -0.88),
        ("GBP_USD", "USD_CAD", -0.89),
        ("AUD_USD", "USD_CHF", -0.79),
        ("NZD_USD", "USD_CAD", -0.80),
    ])


@dataclass
class RiskManagement:
    """Risk management parameters - all testable"""

    # Leverage
    LEVERAGE: int = 10  # Account leverage (e.g., 10 = 10:1)

    # Position sizing
    RISK_PER_TRADE_PERCENT: float = 1.0  # Risk 1% of account per trade
    
    # Stop loss options
    USE_ATR_STOP: bool = True  # If False, use fixed pip stop
    FIXED_STOP_PIPS: float = 5.0  # Fixed stop loss in pips (if USE_ATR_STOP=False)
    ATR_MULTIPLIER: float = 1.5  # ATR multiplier for stop loss
    ATR_PERIOD: int = 14  # ATR calculation period
    
    # Take profit / Risk-Reward
    RISK_REWARD_RATIO: float = 1.9  # Test range: 1.5 - 2.5
    
    # Partial close settings
    PARTIAL_CLOSE_ENABLED: bool = True
    PARTIAL_CLOSE_PERCENT: float = 50.0  # Close 50% at first target
    
    # Trailing stop (after partial close)
    TRAILING_STOP_PIPS: float = 2.0  # Test different values
    TRAILING_STOP_ENABLED: bool = True
    
    # Maximum concurrent positions
    MAX_OPEN_TRADES: int = 3
    
    # Loss streak protection
    MAX_CONSECUTIVE_LOSSES: int = 4
    COOLDOWN_HOURS: float = 6.0  # Hours to wait after hitting loss streak


@dataclass
class MarketHours:
    """Market session times in UTC"""
    
    # Session open times (UTC)
    SYDNEY_OPEN: int = 21  # 21:00 UTC (varies with DST)
    TOKYO_OPEN: int = 0    # 00:00 UTC
    LONDON_OPEN: int = 7   # 07:00 UTC (08:00 BST)
    NEW_YORK_OPEN: int = 12  # 12:00 UTC (13:00 EDT)
    
    # Minutes to avoid after market open
    MARKET_OPEN_AVOID_MINUTES: int = 15
    
    # Weekend - no trading
    WEEKEND_DAYS: List[int] = field(default_factory=lambda: [5, 6])  # Sat=5, Sun=6


@dataclass
class NewsFilter:
    """News event filtering settings"""
    
    # Minutes before red flag news to close positions
    CLOSE_BEFORE_NEWS_MINUTES: int = 30
    
    # Minutes after red flag news to avoid trading
    AVOID_AFTER_NEWS_MINUTES: int = 30
    
    # Impact levels to filter (ForexFactory uses: Low, Medium, High)
    FILTER_IMPACT_LEVELS: List[str] = field(default_factory=lambda: ["High"])
    
    # Currencies to monitor for news (matches our trading pairs)
    MONITORED_CURRENCIES: List[str] = field(default_factory=lambda: [
        "USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CHF", "CAD"
    ])


@dataclass
class IndicatorSettings:
    """Technical indicator parameters - all adjustable via dashboard"""

    # RSI Settings
    RSI_PERIOD: int = 14
    RSI_OVERSOLD: int = 30
    RSI_OVERBOUGHT: int = 70

    # Correlation threshold - pairs above this are considered "mirroring"
    CORRELATION_THRESHOLD: float = 0.70
    
    # Timeframes
    ENTRY_TIMEFRAME: TimeFrame = TimeFrame.M15
    CONFIRMATION_TIMEFRAME: TimeFrame = TimeFrame.H1  # Higher TF for trend confirmation
    
    # AutoTrend settings (placeholder - will be populated from their rules)
    AUTOTREND_SETTINGS: Dict = field(default_factory=lambda: {
        # These will be filled in once we have the AutoTrend documentation
        "enabled": True,
        "require_confirmation": True,
    })


@dataclass
class BacktestSettings:
    """Backtesting configuration"""
    
    # Test period
    BACKTEST_YEARS: int = 2
    
    # Costs simulation
    SPREAD_PIPS: Dict[str, float] = field(default_factory=lambda: {
        "EUR_USD": 0.8,
        "USD_JPY": 0.9,
        "GBP_USD": 1.2,
        "AUD_USD": 1.0,
        "NZD_USD": 1.5,
        "USD_CHF": 1.2,
        "USD_CAD": 1.3,
    })
    
    # Commission per lot (if applicable)
    COMMISSION_PER_LOT: float = 0.0  # Oanda typically no commission, just spread
    
    # Slippage estimation (pips)
    SLIPPAGE_PIPS: float = 0.3


@dataclass
class OandaSettings:
    """OANDA broker configuration"""
    
    # API endpoints
    PRACTICE_URL: str = "https://api-fxpractice.oanda.com"
    LIVE_URL: str = "https://api-fxtrade.oanda.com"
    
    # Use practice account for testing
    USE_PRACTICE: bool = True
    
    # These should be loaded from environment variables
    API_KEY: str = ""  # Set via OANDA_API_KEY env var
    ACCOUNT_ID: str = ""  # Set via OANDA_ACCOUNT_ID env var


@dataclass
class TradingConfig:
    """Master configuration combining all settings"""
    pairs: TradingPairs = field(default_factory=TradingPairs)
    risk: RiskManagement = field(default_factory=RiskManagement)
    hours: MarketHours = field(default_factory=MarketHours)
    news: NewsFilter = field(default_factory=NewsFilter)
    indicators: IndicatorSettings = field(default_factory=IndicatorSettings)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)
    oanda: OandaSettings = field(default_factory=OandaSettings)
    # ATS Strategy selection
    ats_strategy: ATSStrategy = ATSStrategy.STANDARD
    # Forward test mode: log trades but don't execute on OANDA
    paper_trading: bool = False
    # Virtual balance for paper trading simulation
    virtual_balance: float = 10000.0


# Default configuration instance
DEFAULT_CONFIG = TradingConfig()


# Configuration presets for testing different strategies
CONSERVATIVE_CONFIG = TradingConfig(
    risk=RiskManagement(
        RISK_PER_TRADE_PERCENT=0.5,
        RISK_REWARD_RATIO=2.0,
        MAX_OPEN_TRADES=2,
        MAX_CONSECUTIVE_LOSSES=3,
        COOLDOWN_HOURS=8.0,
    )
)

AGGRESSIVE_CONFIG = TradingConfig(
    risk=RiskManagement(
        RISK_PER_TRADE_PERCENT=2.0,
        RISK_REWARD_RATIO=1.5,
        MAX_OPEN_TRADES=4,
        MAX_CONSECUTIVE_LOSSES=5,
        COOLDOWN_HOURS=4.0,
    )
)
