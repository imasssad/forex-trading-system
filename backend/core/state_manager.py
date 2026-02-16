"""
Trade State Manager
Tracks trading state including consecutive losses, cooldowns, and position history
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


class TradeResult(Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


@dataclass
class TradeRecord:
    """Record of a completed trade"""
    trade_id: str
    instrument: str
    direction: str  # "long" or "short"
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    profit_loss: float
    profit_loss_pips: float
    result: TradeResult
    exit_reason: str  # "take_profit", "stop_loss", "trailing_stop", "manual", "news"
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["result"] = self.result.value
        return d
    
    @classmethod
    def from_dict(cls, d: Dict) -> "TradeRecord":
        d["result"] = TradeResult(d["result"])
        return cls(**d)


@dataclass
class TradingState:
    """Current trading state"""
    consecutive_losses: int = 0
    last_trade_time: Optional[str] = None
    cooldown_until: Optional[str] = None
    daily_trades: int = 0
    daily_wins: int = 0
    daily_losses: int = 0
    daily_pnl: float = 0.0
    last_reset_date: str = field(default_factory=lambda: datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d"))
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> "TradingState":
        return cls(**d)


class TradeStateManager:
    """
    Manages trading state including:
    - Consecutive loss tracking
    - Cooldown periods after loss streaks
    - Daily statistics
    - Trade history
    """
    
    def __init__(
        self,
        max_consecutive_losses: int = 4,
        cooldown_hours: float = 6.0,
        state_file: str = "trading_state.json",
        history_file: str = "trade_history.json"
    ):
        """
        Initialize state manager.
        
        Args:
            max_consecutive_losses: Number of losses before cooldown
            cooldown_hours: Hours to pause trading after loss streak
            state_file: File to persist state
            history_file: File to persist trade history
        """
        self.max_losses = max_consecutive_losses
        self.cooldown_hours = cooldown_hours
        self.state_file = state_file
        self.history_file = history_file
        
        self.state = self._load_state()
        self.history: List[TradeRecord] = self._load_history()
        
        # Check if we need to reset daily stats
        self._check_daily_reset()
    
    def _load_state(self) -> TradingState:
        """Load state from file or create new"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    return TradingState.from_dict(data)
            except Exception as e:
                logger.warning(f"Could not load state file: {e}")
        
        return TradingState()
    
    def _save_state(self):
        """Save state to file"""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Could not save state file: {e}")
    
    def _load_history(self) -> List[TradeRecord]:
        """Load trade history from file"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    return [TradeRecord.from_dict(d) for d in data]
            except Exception as e:
                logger.warning(f"Could not load history file: {e}")
        
        return []
    
    def _save_history(self):
        """Save trade history to file"""
        try:
            with open(self.history_file, "w") as f:
                data = [t.to_dict() for t in self.history]
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save history file: {e}")
    
    def _check_daily_reset(self):
        """Reset daily stats if it's a new day"""
        today = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d")
        
        if self.state.last_reset_date != today:
            logger.info(f"New trading day. Resetting daily stats.")
            self.state.daily_trades = 0
            self.state.daily_wins = 0
            self.state.daily_losses = 0
            self.state.daily_pnl = 0.0
            self.state.last_reset_date = today
            self._save_state()
    
    def record_trade(self, trade: TradeRecord):
        """
        Record a completed trade and update state.
        
        Args:
            trade: The completed trade record
        """
        self.history.append(trade)
        self._save_history()
        
        # Update daily stats
        self.state.daily_trades += 1
        self.state.daily_pnl += trade.profit_loss
        self.state.last_trade_time = trade.exit_time
        
        if trade.result == TradeResult.WIN:
            self.state.daily_wins += 1
            self.state.consecutive_losses = 0
            self.state.cooldown_until = None
            
        elif trade.result == TradeResult.LOSS:
            self.state.daily_losses += 1
            self.state.consecutive_losses += 1
            
            # Check if we need to enter cooldown
            if self.state.consecutive_losses >= self.max_losses:
                cooldown_end = datetime.now(ZoneInfo("UTC")) + timedelta(hours=self.cooldown_hours)
                self.state.cooldown_until = cooldown_end.isoformat()
                logger.warning(
                    f"Hit {self.state.consecutive_losses} consecutive losses. "
                    f"Entering cooldown until {cooldown_end.strftime('%H:%M UTC')}"
                )
        
        else:  # BREAKEVEN
            # Breakeven doesn't affect loss streak
            pass
        
        self._save_state()
        
        logger.info(
            f"Trade recorded: {trade.instrument} {trade.direction} - "
            f"P/L: {trade.profit_loss:.2f} ({trade.result.value}). "
            f"Consecutive losses: {self.state.consecutive_losses}"
        )
    
    def is_in_cooldown(self) -> tuple[bool, Optional[str]]:
        """
        Check if trading is currently in cooldown.
        
        Returns:
            Tuple of (is_in_cooldown, reason_or_time_remaining)
        """
        if self.state.cooldown_until is None:
            return False, None
        
        cooldown_end = datetime.fromisoformat(self.state.cooldown_until)
        now = datetime.now(ZoneInfo("UTC"))
        
        if now >= cooldown_end:
            # Cooldown has ended
            self.state.cooldown_until = None
            self.state.consecutive_losses = 0  # Reset loss counter
            self._save_state()
            return False, None
        
        # Still in cooldown
        remaining = cooldown_end - now
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        
        return True, f"In cooldown after {self.max_losses} losses. {hours}h {minutes}m remaining"
    
    def can_trade(self) -> tuple[bool, Optional[str]]:
        """
        Check if trading is allowed based on state.
        
        Returns:
            Tuple of (can_trade, reason_if_not)
        """
        # Check cooldown
        in_cooldown, reason = self.is_in_cooldown()
        if in_cooldown:
            return False, reason
        
        return True, None
    
    def get_consecutive_losses(self) -> int:
        """Get current consecutive loss count"""
        return self.state.consecutive_losses
    
    def get_daily_stats(self) -> Dict:
        """Get today's trading statistics"""
        self._check_daily_reset()
        
        win_rate = 0
        if self.state.daily_trades > 0:
            win_rate = (self.state.daily_wins / self.state.daily_trades) * 100
        
        return {
            "date": self.state.last_reset_date,
            "total_trades": self.state.daily_trades,
            "wins": self.state.daily_wins,
            "losses": self.state.daily_losses,
            "breakeven": self.state.daily_trades - self.state.daily_wins - self.state.daily_losses,
            "win_rate": round(win_rate, 1),
            "pnl": round(self.state.daily_pnl, 2),
            "consecutive_losses": self.state.consecutive_losses,
            "in_cooldown": self.state.cooldown_until is not None
        }
    
    def get_history_summary(
        self,
        days: int = 30
    ) -> Dict:
        """Get summary of recent trading history"""
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        recent_trades = [t for t in self.history if t.exit_time >= cutoff_str]
        
        if not recent_trades:
            return {
                "period_days": days,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "profit_factor": 0
            }
        
        wins = [t for t in recent_trades if t.result == TradeResult.WIN]
        losses = [t for t in recent_trades if t.result == TradeResult.LOSS]
        
        total_wins = sum(t.profit_loss for t in wins) if wins else 0
        total_losses = abs(sum(t.profit_loss for t in losses)) if losses else 0
        
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        return {
            "period_days": days,
            "total_trades": len(recent_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(recent_trades) * 100, 1),
            "total_pnl": round(sum(t.profit_loss for t in recent_trades), 2),
            "avg_win": round(total_wins / len(wins), 2) if wins else 0,
            "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
            "profit_factor": round(profit_factor, 2)
        }
    
    def reset_cooldown(self):
        """Manually reset cooldown (admin function)"""
        self.state.cooldown_until = None
        self.state.consecutive_losses = 0
        self._save_state()
        logger.info("Cooldown manually reset")
    
    def reset_all(self):
        """Reset all state (use with caution)"""
        self.state = TradingState()
        self._save_state()
        logger.info("All trading state reset")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create state manager
    manager = TradeStateManager(
        max_consecutive_losses=4,
        cooldown_hours=6.0,
        state_file="/tmp/test_state.json",
        history_file="/tmp/test_history.json"
    )
    
    # Check if we can trade
    can_trade, reason = manager.can_trade()
    print(f"Can trade: {can_trade}")
    if reason:
        print(f"  Reason: {reason}")
    
    # Simulate some trades
    from datetime import datetime
    
    # Record a winning trade
    manager.record_trade(TradeRecord(
        trade_id="1",
        instrument="EUR_USD",
        direction="long",
        entry_price=1.0850,
        exit_price=1.0900,
        entry_time=datetime.now(ZoneInfo("UTC")).isoformat(),
        exit_time=datetime.now(ZoneInfo("UTC")).isoformat(),
        profit_loss=50.0,
        profit_loss_pips=50,
        result=TradeResult.WIN,
        exit_reason="take_profit"
    ))
    
    # Record some losing trades
    for i in range(4):
        manager.record_trade(TradeRecord(
            trade_id=str(i+2),
            instrument="GBP_USD",
            direction="short",
            entry_price=1.2650,
            exit_price=1.2670,
            entry_time=datetime.now(ZoneInfo("UTC")).isoformat(),
            exit_time=datetime.now(ZoneInfo("UTC")).isoformat(),
            profit_loss=-20.0,
            profit_loss_pips=-20,
            result=TradeResult.LOSS,
            exit_reason="stop_loss"
        ))
    
    # Check if we're in cooldown now
    can_trade, reason = manager.can_trade()
    print(f"\nAfter 4 losses - Can trade: {can_trade}")
    if reason:
        print(f"  Reason: {reason}")
    
    # Get daily stats
    print(f"\nDaily stats: {manager.get_daily_stats()}")
