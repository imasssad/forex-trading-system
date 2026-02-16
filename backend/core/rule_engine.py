"""
Trading Rule Engine
Central decision maker that combines all filters and rules
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.correlation_filter import CorrelationFilter, TradeDirection, OpenPosition
from core.market_hours import MarketHoursFilter
from core.state_manager import TradeStateManager
from news.forex_factory import NewsFilter
from config.settings import TradingConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


@dataclass
class TradingSignal:
    """Signal from indicators"""
    instrument: str
    signal_type: SignalType
    timestamp: str
    entry_timeframe: str

    # Indicator values
    rsi_value: float
    autotrend_direction: str  # "bullish", "bearish", "neutral"
    htf_trend: str  # Higher timeframe trend

    # Calculated levels
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    atr_value: Optional[float] = None

    # New fields for cost modeling
    spread: Optional[float] = None
    fee: Optional[float] = None


@dataclass
class RuleCheckResult:
    """Result of rule check"""
    passed: bool
    rule_name: str
    reason: Optional[str] = None


@dataclass
class TradeDecision:
    """Final trade decision"""
    should_trade: bool
    signal: Optional[TradingSignal]
    checks_passed: List[RuleCheckResult]
    checks_failed: List[RuleCheckResult]
    position_size: int = 0
    stop_loss: float = 0
    take_profit: float = 0
    
    def get_summary(self) -> str:
        """Get human-readable summary"""
        if self.should_trade:
            return (
                f"TRADE: {self.signal.signal_type.value.upper()} {self.signal.instrument}\n"
                f"  Entry: {self.signal.entry_price:.5f}\n"
                f"  Stop Loss: {self.stop_loss:.5f}\n"
                f"  Take Profit: {self.take_profit:.5f}\n"
                f"  Size: {self.position_size} units"
            )
        else:
            failed_rules = ", ".join([c.rule_name for c in self.checks_failed])
            return f"NO TRADE: Failed checks - {failed_rules}"


class TradingRuleEngine:
    """
    Main rule engine that decides whether to take a trade.
    Combines all filters: correlation, news, market hours, loss streak, etc.
    """
    
    def __init__(
        self,
        config: TradingConfig = DEFAULT_CONFIG,
        state_file: str = "trading_state.json",
        history_file: str = "trade_history.json"
    ):
        """
        Initialize rule engine with all filters.
        
        Args:
            config: Trading configuration
            state_file: File for persisting trading state
            history_file: File for trade history
        """
        self.config = config
        
        # Initialize filters
        self.correlation_filter = CorrelationFilter(
            correlation_threshold=config.indicators.CORRELATION_THRESHOLD
        )
        
        self.market_hours_filter = MarketHoursFilter(
            avoid_open_minutes=config.hours.MARKET_OPEN_AVOID_MINUTES
        )
        
        self.news_filter = NewsFilter(
            pre_news_minutes=config.news.CLOSE_BEFORE_NEWS_MINUTES,
            post_news_minutes=config.news.AVOID_AFTER_NEWS_MINUTES
        )
        
        self.state_manager = TradeStateManager(
            max_consecutive_losses=config.risk.MAX_CONSECUTIVE_LOSSES,
            cooldown_hours=config.risk.COOLDOWN_HOURS,
            state_file=state_file,
            history_file=history_file
        )
        
        logger.info("Trading Rule Engine initialized")
    
    def check_signal_valid(self, signal: TradingSignal) -> RuleCheckResult:
        """Check if the signal itself is valid"""
        # Must have a clear direction
        if signal.signal_type == SignalType.NEUTRAL:
            return RuleCheckResult(
                passed=False,
                rule_name="signal_valid",
                reason="Signal is neutral (no clear direction)"
            )
        
        # RSI must confirm
        if signal.signal_type == SignalType.BUY:
            # For buy, RSI should be coming out of oversold
            if signal.rsi_value > self.config.indicators.RSI_OVERBOUGHT:
                return RuleCheckResult(
                    passed=False,
                    rule_name="signal_valid",
                    reason=f"RSI is overbought ({signal.rsi_value:.1f}) for buy signal"
                )
        
        elif signal.signal_type == SignalType.SELL:
            # For sell, RSI should be coming out of overbought
            if signal.rsi_value < self.config.indicators.RSI_OVERSOLD:
                return RuleCheckResult(
                    passed=False,
                    rule_name="signal_valid",
                    reason=f"RSI is oversold ({signal.rsi_value:.1f}) for sell signal"
                )
        
        # AutoTrend must agree with signal
        expected_trend = "bullish" if signal.signal_type == SignalType.BUY else "bearish"
        if signal.autotrend_direction != expected_trend:
            return RuleCheckResult(
                passed=False,
                rule_name="signal_valid",
                reason=f"AutoTrend is {signal.autotrend_direction}, expected {expected_trend}"
            )
        
        return RuleCheckResult(passed=True, rule_name="signal_valid")
    
    def check_htf_trend(self, signal: TradingSignal) -> RuleCheckResult:
        """Check if higher timeframe trend aligns"""
        expected = "bullish" if signal.signal_type == SignalType.BUY else "bearish"
        
        if signal.htf_trend != expected:
            return RuleCheckResult(
                passed=False,
                rule_name="htf_trend",
                reason=f"Higher timeframe trend is {signal.htf_trend}, trade requires {expected}"
            )
        
        return RuleCheckResult(passed=True, rule_name="htf_trend")
    
    def check_pair_allowed(self, signal: TradingSignal) -> RuleCheckResult:
        """Check if pair is in allowed list"""
        if signal.instrument not in self.config.pairs.ALLOWED_PAIRS:
            return RuleCheckResult(
                passed=False,
                rule_name="pair_allowed",
                reason=f"{signal.instrument} is not in allowed pairs list"
            )
        
        return RuleCheckResult(passed=True, rule_name="pair_allowed")
    
    def check_market_hours(
        self, 
        current_time: Optional[datetime] = None
    ) -> RuleCheckResult:
        """Check market hours restrictions"""
        is_safe, reason = self.market_hours_filter.is_safe_to_trade(current_time)
        
        if not is_safe:
            return RuleCheckResult(
                passed=False,
                rule_name="market_hours",
                reason=reason
            )
        
        return RuleCheckResult(passed=True, rule_name="market_hours")
    
    def check_news_filter(
        self,
        signal: TradingSignal,
        current_time: Optional[datetime] = None
    ) -> RuleCheckResult:
        """Check news filter"""
        is_safe, reason = self.news_filter.is_safe_to_trade(
            signal.instrument, 
            current_time
        )
        
        if not is_safe:
            return RuleCheckResult(
                passed=False,
                rule_name="news_filter",
                reason=reason
            )
        
        return RuleCheckResult(passed=True, rule_name="news_filter")
    
    def check_correlation(
        self,
        signal: TradingSignal,
        open_positions: List[OpenPosition]
    ) -> RuleCheckResult:
        """Check for duplicate exposure via correlation"""
        direction = TradeDirection.LONG if signal.signal_type == SignalType.BUY else TradeDirection.SHORT
        
        is_duplicate, reason = self.correlation_filter.would_duplicate_exposure(
            signal.instrument,
            direction,
            open_positions
        )
        
        if is_duplicate:
            return RuleCheckResult(
                passed=False,
                rule_name="correlation",
                reason=reason
            )
        
        return RuleCheckResult(passed=True, rule_name="correlation")
    
    def check_max_positions(
        self,
        open_positions: List[OpenPosition]
    ) -> RuleCheckResult:
        """Check if we're at max open positions"""
        if len(open_positions) >= self.config.risk.MAX_OPEN_TRADES:
            return RuleCheckResult(
                passed=False,
                rule_name="max_positions",
                reason=f"Already at max positions ({self.config.risk.MAX_OPEN_TRADES})"
            )
        
        return RuleCheckResult(passed=True, rule_name="max_positions")
    
    def check_loss_streak(self) -> RuleCheckResult:
        """Check if in cooldown due to loss streak"""
        can_trade, reason = self.state_manager.can_trade()
        
        if not can_trade:
            return RuleCheckResult(
                passed=False,
                rule_name="loss_streak",
                reason=reason
            )
        
        return RuleCheckResult(passed=True, rule_name="loss_streak")
    
    def evaluate_signal(
        self,
        signal: TradingSignal,
        open_positions: List[OpenPosition],
        current_time: Optional[datetime] = None
    ) -> TradeDecision:
        """
        Evaluate a trading signal against all rules.
        
        Args:
            signal: The trading signal to evaluate
            open_positions: List of current open positions
            current_time: Current time (default: now)
            
        Returns:
            TradeDecision with whether to trade and why
        """
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        checks_passed = []
        checks_failed = []
        
        # Run all checks
        checks = [
            self.check_signal_valid(signal),
            self.check_pair_allowed(signal),
            self.check_htf_trend(signal),
            self.check_market_hours(current_time),
            self.check_news_filter(signal, current_time),
            self.check_correlation(signal, open_positions),
            self.check_max_positions(open_positions),
            self.check_loss_streak(),
        ]
        
        for check in checks:
            if check.passed:
                checks_passed.append(check)
            else:
                checks_failed.append(check)
                logger.info(f"Rule failed: {check.rule_name} - {check.reason}")
        
        # Decision
        should_trade = len(checks_failed) == 0
        
        decision = TradeDecision(
            should_trade=should_trade,
            signal=signal if should_trade else None,
            checks_passed=checks_passed,
            checks_failed=checks_failed
        )
        
        if should_trade:
            logger.info(f"Signal APPROVED: {signal.signal_type.value} {signal.instrument}")
        else:
            logger.info(f"Signal REJECTED: {signal.instrument} - {len(checks_failed)} rules failed")
        
        return decision
    
    def should_close_for_news(
        self,
        instrument: str,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if position should be closed due to upcoming news"""
        return self.news_filter.should_close_positions(instrument, current_time)
    
    def get_status(self) -> Dict:
        """Get current status of rule engine"""
        return {
            "daily_stats": self.state_manager.get_daily_stats(),
            "can_trade": self.state_manager.can_trade()[0],
            "market_open": self.market_hours_filter.is_safe_to_trade()[0],
            "active_sessions": [
                s.value for s in self.market_hours_filter.get_active_sessions()
            ],
        }


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create rule engine
    engine = TradingRuleEngine()
    
    # Create a test signal
    signal = TradingSignal(
        instrument="EUR_USD",
        signal_type=SignalType.BUY,
        timestamp=datetime.now(ZoneInfo("UTC")).isoformat(),
        entry_timeframe="M15",
        rsi_value=35.0,  # Coming out of oversold
        autotrend_direction="bullish",
        htf_trend="bullish",
        entry_price=1.0850,
    )
    
    # Test with no open positions
    decision = engine.evaluate_signal(signal, [])
    
    print("\n" + "="*50)
    print("TRADE DECISION")
    print("="*50)
    print(decision.get_summary())
    
    print("\nChecks passed:")
    for check in decision.checks_passed:
        print(f"  ✓ {check.rule_name}")
    
    print("\nChecks failed:")
    for check in decision.checks_failed:
        print(f"  ✗ {check.rule_name}: {check.reason}")
    
    # Get status
    print("\n" + "="*50)
    print("ENGINE STATUS")
    print("="*50)
    status = engine.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
