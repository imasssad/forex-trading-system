"""
Market Hours Filter
Handles trading restrictions around market opens and weekends
"""

from datetime import datetime, timedelta, time
from typing import Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


class MarketSession(Enum):
    SYDNEY = "Sydney"
    TOKYO = "Tokyo"
    LONDON = "London"
    NEW_YORK = "New York"


@dataclass
class SessionInfo:
    """Information about a market session"""
    name: MarketSession
    open_time: time  # In UTC
    close_time: time  # In UTC
    timezone: str
    
    def is_open(self, current_time: datetime) -> bool:
        """Check if this session is currently open"""
        current_utc = current_time.astimezone(ZoneInfo("UTC"))
        current_time_only = current_utc.time()
        
        if self.open_time <= self.close_time:
            return self.open_time <= current_time_only <= self.close_time
        else:
            # Session spans midnight
            return current_time_only >= self.open_time or current_time_only <= self.close_time


class MarketHoursFilter:
    """
    Filters trading based on market hours:
    - Avoid first 15 minutes after major market opens
    - No trading on weekends
    """
    
    # Session times (UTC) - these shift with DST
    # Using approximate times, will need adjustment for DST
    SESSIONS = {
        MarketSession.SYDNEY: SessionInfo(
            name=MarketSession.SYDNEY,
            open_time=time(21, 0),  # 9 PM UTC (7 AM Sydney)
            close_time=time(6, 0),   # 6 AM UTC (4 PM Sydney)
            timezone="Australia/Sydney"
        ),
        MarketSession.TOKYO: SessionInfo(
            name=MarketSession.TOKYO,
            open_time=time(0, 0),    # Midnight UTC (9 AM Tokyo)
            close_time=time(9, 0),   # 9 AM UTC (6 PM Tokyo)
            timezone="Asia/Tokyo"
        ),
        MarketSession.LONDON: SessionInfo(
            name=MarketSession.LONDON,
            open_time=time(7, 0),    # 7 AM UTC (8 AM London BST)
            close_time=time(16, 0),  # 4 PM UTC (5 PM London BST)
            timezone="Europe/London"
        ),
        MarketSession.NEW_YORK: SessionInfo(
            name=MarketSession.NEW_YORK,
            open_time=time(12, 0),   # 12 PM UTC (8 AM NY)
            close_time=time(21, 0),  # 9 PM UTC (5 PM NY)
            timezone="America/New_York"
        ),
    }
    
    def __init__(self, avoid_open_minutes: int = 15):
        """
        Initialize market hours filter.
        
        Args:
            avoid_open_minutes: Minutes to avoid after market open
        """
        self.avoid_minutes = avoid_open_minutes
    
    def _get_session_open_utc(
        self,
        session: MarketSession,
        date: datetime
    ) -> datetime:
        """
        Get the exact market open time in UTC for a specific date,
        accounting for DST.
        """
        session_info = self.SESSIONS[session]
        local_tz = ZoneInfo(session_info.timezone)
        utc_tz = ZoneInfo("UTC")
        
        # Standard local open times
        local_opens = {
            MarketSession.SYDNEY: time(7, 0),   # 7 AM local
            MarketSession.TOKYO: time(9, 0),    # 9 AM local
            MarketSession.LONDON: time(8, 0),   # 8 AM local
            MarketSession.NEW_YORK: time(9, 30), # 9:30 AM local (stock market)
        }
        
        # For forex, we use these opens (24hr market but these are key)
        forex_opens = {
            MarketSession.SYDNEY: time(7, 0),   # 7 AM Sydney
            MarketSession.TOKYO: time(9, 0),    # 9 AM Tokyo
            MarketSession.LONDON: time(8, 0),   # 8 AM London
            MarketSession.NEW_YORK: time(8, 0), # 8 AM NY
        }
        
        local_open = forex_opens[session]
        
        # Create datetime in local timezone
        local_dt = datetime(
            date.year, date.month, date.day,
            local_open.hour, local_open.minute,
            tzinfo=local_tz
        )
        
        # Convert to UTC
        return local_dt.astimezone(utc_tz)
    
    def is_weekend(self, current_time: datetime) -> bool:
        """
        Check if current time is during forex weekend.
        Forex market closes Friday 5PM NY and opens Sunday 5PM NY.
        """
        utc_time = current_time.astimezone(ZoneInfo("UTC"))
        ny_time = current_time.astimezone(ZoneInfo("America/New_York"))
        
        # Friday after 5 PM NY
        if ny_time.weekday() == 4 and ny_time.hour >= 17:
            return True
        
        # All day Saturday
        if ny_time.weekday() == 5:
            return True
        
        # Sunday before 5 PM NY
        if ny_time.weekday() == 6 and ny_time.hour < 17:
            return True
        
        return False
    
    def is_near_market_open(
        self,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if we're within the first X minutes of any major market open.
        
        Returns:
            Tuple of (is_near_open, which_market_if_yes)
        """
        utc_time = current_time.astimezone(ZoneInfo("UTC"))
        
        for session in MarketSession:
            open_time = self._get_session_open_utc(session, utc_time)
            
            # Handle if open time is for "yesterday" (e.g., Sydney opens at 9 PM UTC)
            if open_time > utc_time:
                # Check if it was yesterday's open
                open_time_yesterday = self._get_session_open_utc(
                    session, 
                    utc_time - timedelta(days=1)
                )
                if utc_time - open_time_yesterday <= timedelta(minutes=self.avoid_minutes):
                    return True, f"{session.value} market just opened"
            
            # Check if within avoid window of today's open
            time_since_open = utc_time - open_time
            
            if timedelta(0) <= time_since_open <= timedelta(minutes=self.avoid_minutes):
                return True, f"{session.value} market just opened"
        
        return False, None
    
    def is_safe_to_trade(
        self,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if it's safe to trade based on market hours.
        
        Returns:
            Tuple of (is_safe, reason_if_not)
        """
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        # Check weekend
        if self.is_weekend(current_time):
            return False, "Forex market is closed (weekend)"
        
        # Check market opens
        near_open, market = self.is_near_market_open(current_time)
        if near_open:
            return False, f"Within {self.avoid_minutes} minutes of {market}"
        
        return True, None
    
    def get_active_sessions(
        self,
        current_time: Optional[datetime] = None
    ) -> List[MarketSession]:
        """Get list of currently active market sessions"""
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        active = []
        for session, info in self.SESSIONS.items():
            if info.is_open(current_time):
                active.append(session)
        
        return active
    
    def get_next_market_open(
        self,
        current_time: Optional[datetime] = None
    ) -> Tuple[MarketSession, datetime]:
        """Get the next market session to open"""
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        utc_time = current_time.astimezone(ZoneInfo("UTC"))
        
        next_opens = []
        
        for session in MarketSession:
            # Get today's open
            open_today = self._get_session_open_utc(session, utc_time)
            
            # If already passed, get tomorrow's
            if open_today <= utc_time:
                open_tomorrow = self._get_session_open_utc(
                    session,
                    utc_time + timedelta(days=1)
                )
                next_opens.append((session, open_tomorrow))
            else:
                next_opens.append((session, open_today))
        
        # Return the soonest
        return min(next_opens, key=lambda x: x[1])
    
    def get_session_volatility_factor(
        self,
        pair: str,
        current_time: Optional[datetime] = None
    ) -> float:
        """
        Get a volatility factor based on active sessions.
        Used for adjusting stop losses.
        
        Returns:
            Multiplier (1.0 = normal, >1 = more volatile)
        """
        if current_time is None:
            current_time = datetime.now(ZoneInfo("UTC"))
        
        active = self.get_active_sessions(current_time)
        
        # Session overlap = higher volatility
        # London-NY overlap is most volatile
        if MarketSession.LONDON in active and MarketSession.NEW_YORK in active:
            return 1.5
        
        # Tokyo-London overlap
        if MarketSession.TOKYO in active and MarketSession.LONDON in active:
            return 1.3
        
        # Single session
        if len(active) == 1:
            # Asian session typically quieter for majors
            if active[0] in [MarketSession.SYDNEY, MarketSession.TOKYO]:
                return 0.8
        
        return 1.0


# Example usage
if __name__ == "__main__":
    from datetime import datetime
    
    filter = MarketHoursFilter(avoid_open_minutes=15)
    
    # Test current time
    now = datetime.now(ZoneInfo("UTC"))
    
    print(f"Current time (UTC): {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"Is weekend: {filter.is_weekend(now)}")
    
    is_safe, reason = filter.is_safe_to_trade(now)
    print(f"Safe to trade: {is_safe}")
    if reason:
        print(f"  Reason: {reason}")
    
    active = filter.get_active_sessions(now)
    print(f"Active sessions: {[s.value for s in active]}")
    
    next_session, next_open = filter.get_next_market_open(now)
    print(f"Next market open: {next_session.value} at {next_open.strftime('%H:%M UTC')}")
    
    # Test volatility factor
    vol_factor = filter.get_session_volatility_factor("EUR_USD", now)
    print(f"Volatility factor: {vol_factor}")
