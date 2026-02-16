"""
Forex Factory News Filter
Fetches economic calendar data from ForexFactory's JSON endpoint
and filters trades around high-impact news events.

Uses: https://nfs.faireconomy.media/ff_calendar_thisweek.json
Rate limit: Max 2 requests per 5 minutes (enforced by FF servers)

Rules:
- Close open positions 30 minutes BEFORE high-impact (red flag) news
- Block new trades for 30 minutes AFTER high-impact news
- Monitor currencies: USD, EUR, GBP, JPY, AUD, NZD, CHF, CAD
"""

import json
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from zoneinfo import ZoneInfo
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class NewsEvent:
    """Single economic calendar event"""
    title: str
    country: str       # Currency code: USD, EUR, GBP, etc.
    date: datetime     # Event time in UTC
    impact: str        # "High", "Medium", "Low"
    forecast: str
    previous: str
    
    @property
    def is_high_impact(self) -> bool:
        return self.impact == "High"
    
    @property
    def is_medium_impact(self) -> bool:
        return self.impact == "Medium"
    
    def affects_pair(self, instrument: str) -> bool:
        """Check if this event affects a given forex pair"""
        # Convert instrument format: EUR_USD -> EUR, USD
        pair = instrument.replace("_", "").replace("/", "")
        base = pair[:3].upper()
        quote = pair[3:].upper()
        country = self.country.upper()
        
        # "All" impacts everything
        if country == "ALL":
            return True
        
        # CNY events can affect AUD/NZD (China trade partners)
        if country == "CNY" and (base in ("AUD", "NZD") or quote in ("AUD", "NZD")):
            return True
        
        return country == base or country == quote


class NewsFilter:
    """
    Forex Factory economic calendar news filter.
    
    Fetches weekly calendar data from ForexFactory's JSON feed
    and determines if trades should be blocked or positions closed
    based on upcoming high-impact news events.
    
    Usage:
        news = NewsFilter()
        news.refresh()
        
        # Check before opening a trade
        can_trade, reason = news.can_open_trade("EUR_USD")
        
        # Check if we should close positions
        should_close, reason = news.should_close_positions("EUR_USD")
    """
    
    # ForexFactory JSON endpoint (2 requests per 5 min limit)
    JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    
    # Currencies we monitor
    MONITORED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CHF", "CAD", "CNY", "ALL"}
    
    # Pair to currency mapping for quick lookup
    PAIR_CURRENCIES = {
        "EUR_USD": ("EUR", "USD"),
        "USD_JPY": ("USD", "JPY"),
        "GBP_USD": ("GBP", "USD"),
        "AUD_USD": ("AUD", "USD"),
        "NZD_USD": ("NZD", "USD"),
        "USD_CHF": ("USD", "CHF"),
        "USD_CAD": ("USD", "CAD"),
    }
    
    def __init__(
        self,
        pre_news_minutes: int = 30,
        post_news_minutes: int = 30,
        cache_file: str = "news_cache.json",
        refresh_interval_minutes: int = 60,
    ):
        self.pre_news_minutes = pre_news_minutes
        self.post_news_minutes = post_news_minutes
        self.cache_file = Path(cache_file)
        self.refresh_interval = timedelta(minutes=refresh_interval_minutes)
        
        # Event storage
        self.events: List[NewsEvent] = []
        self.last_fetch: Optional[datetime] = None
        self._last_fetch_attempt: Optional[datetime] = None
        
        # Rate limiting (FF allows 2 requests per 5 min)
        self._request_timestamps: List[datetime] = []
        self._rate_limit_window = timedelta(minutes=5)
        self._rate_limit_max = 2
        
        # Try loading from cache on startup
        self._load_cache()
    
    def _can_make_request(self) -> bool:
        """Check if we're within rate limits"""
        now = datetime.now(ZoneInfo("UTC"))
        # Remove timestamps outside the window
        self._request_timestamps = [
            ts for ts in self._request_timestamps
            if now - ts < self._rate_limit_window
        ]
        return len(self._request_timestamps) < self._rate_limit_max
    
    def _record_request(self):
        """Record a request timestamp for rate limiting"""
        self._request_timestamps.append(datetime.now(ZoneInfo("UTC")))
    
    def refresh(self, force: bool = False) -> bool:
        """
        Fetch fresh calendar data from ForexFactory.
        Returns True if data was successfully refreshed.
        """
        now = datetime.now(ZoneInfo("UTC"))
        
        # Skip if recently refreshed (unless forced)
        if not force and self.last_fetch and (now - self.last_fetch) < self.refresh_interval:
            logger.debug("Skipping refresh - data is recent enough")
            return True
        
        # Check rate limits
        if not self._can_make_request():
            logger.warning("ForexFactory rate limit - max 2 requests per 5 minutes")
            return len(self.events) > 0  # Return True if we have cached data
        
        try:
            logger.info("Fetching ForexFactory calendar data...")
            
            response = requests.get(
                self.JSON_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
                timeout=15
            )
            
            self._record_request()
            
            if response.status_code != 200:
                logger.error(f"ForexFactory returned status {response.status_code}")
                # Check if rate limited
                if "Request Denied" in response.text or "exceeded the limit" in response.text:
                    logger.error("Rate limited by ForexFactory. Will use cached data.")
                return len(self.events) > 0
            
            raw_events = response.json()
            self.events = self._parse_events(raw_events)
            self.last_fetch = now
            
            # Cache to file
            self._save_cache(raw_events)
            
            high_count = sum(1 for e in self.events if e.is_high_impact)
            logger.info(
                f"Loaded {len(self.events)} events "
                f"({high_count} high-impact) for this week"
            )
            
            return True
            
        except requests.exceptions.Timeout:
            logger.error("ForexFactory request timed out")
            return len(self.events) > 0
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to ForexFactory")
            return len(self.events) > 0
        except json.JSONDecodeError:
            logger.error("Invalid JSON from ForexFactory")
            return len(self.events) > 0
        except Exception as e:
            logger.error(f"Error fetching news data: {e}")
            return len(self.events) > 0
    
    def _parse_events(self, raw_events: List[Dict]) -> List[NewsEvent]:
        """Parse raw JSON events into NewsEvent objects"""
        events = []
        
        for raw in raw_events:
            try:
                # Parse the ISO date string
                # ForexFactory format: "2026-02-04T08:15:00-05:00" (Eastern Time)
                date_str = raw.get("date", "")
                if not date_str:
                    continue
                
                # Parse and convert to UTC
                event_time = datetime.fromisoformat(date_str).astimezone(ZoneInfo("UTC"))
                
                country = raw.get("country", "").upper().strip()
                impact = raw.get("impact", "Low").strip()
                
                # Only keep events for currencies we care about
                if country not in self.MONITORED_CURRENCIES:
                    continue
                
                event = NewsEvent(
                    title=raw.get("title", "Unknown"),
                    country=country,
                    date=event_time,
                    impact=impact,
                    forecast=raw.get("forecast", ""),
                    previous=raw.get("previous", "")
                )
                
                events.append(event)
                
            except (ValueError, KeyError) as e:
                logger.debug(f"Skipping unparseable event: {e}")
                continue
        
        # Sort by date
        events.sort(key=lambda e: e.date)
        return events
    
    def _save_cache(self, raw_events: List[Dict]):
        """Save raw events to cache file"""
        try:
            cache_data = {
                "fetched_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "events": raw_events
            }
            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)
            logger.debug(f"Cached {len(raw_events)} events to {self.cache_file}")
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")
    
    def _load_cache(self):
        """Load events from cache file"""
        try:
            if not self.cache_file.exists():
                return
            
            with open(self.cache_file) as f:
                cache_data = json.load(f)
            
            fetched_at = datetime.fromisoformat(cache_data["fetched_at"])
            
            # Only use cache if less than 24 hours old
            if datetime.now(ZoneInfo("UTC")) - fetched_at > timedelta(hours=24):
                logger.info("Cache is stale (>24h), will refresh")
                return
            
            self.events = self._parse_events(cache_data["events"])
            self.last_fetch = fetched_at
            
            logger.info(f"Loaded {len(self.events)} events from cache (fetched {fetched_at})")
            
        except Exception as e:
            logger.warning(f"Could not load cache: {e}")
    
    def get_upcoming_events(
        self,
        instrument: Optional[str] = None,
        hours_ahead: int = 24,
        high_impact_only: bool = False
    ) -> List[NewsEvent]:
        """
        Get upcoming events within the next N hours.
        Optionally filter by instrument and impact level.
        """
        self.refresh()  # Auto-refresh if needed
        
        now = datetime.now(ZoneInfo("UTC"))
        cutoff = now + timedelta(hours=hours_ahead)
        
        upcoming = []
        for event in self.events:
            # Must be in the future (or just happened within post_news window)
            event_end = event.date + timedelta(minutes=self.post_news_minutes)
            if event_end < now:
                continue
            if event.date > cutoff:
                continue
            
            # Impact filter
            if high_impact_only and not event.is_high_impact:
                continue
            
            # Instrument filter
            if instrument and not event.affects_pair(instrument):
                continue
            
            upcoming.append(event)
        
        return upcoming
    
    def can_open_trade(self, instrument: str, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if it's safe to open a new trade based on news events.
        
        Returns:
            (True, "OK") if safe to trade
            (False, "reason") if trade should be blocked
        """
        self.refresh()
        
        now = current_time or datetime.now(ZoneInfo("UTC"))
        
        for event in self.events:
            if not event.is_high_impact:
                continue
            
            if not event.affects_pair(instrument):
                continue
            
            # Pre-news window: block trades X minutes before event
            pre_window_start = event.date - timedelta(minutes=self.pre_news_minutes)
            if pre_window_start <= now <= event.date:
                minutes_until = int((event.date - now).total_seconds() / 60)
                return (
                    False,
                    f"HIGH IMPACT NEWS in {minutes_until}min: "
                    f"{event.title} ({event.country}) at {event.date.strftime('%H:%M UTC')}"
                )
            
            # Post-news window: block trades X minutes after event
            post_window_end = event.date + timedelta(minutes=self.post_news_minutes)
            if event.date <= now <= post_window_end:
                minutes_since = int((now - event.date).total_seconds() / 60)
                return (
                    False,
                    f"POST-NEWS COOLDOWN ({minutes_since}min since): "
                    f"{event.title} ({event.country})"
                )
        
        return (True, "OK")
    
    def should_close_positions(self, instrument: str) -> Tuple[bool, str]:
        """
        Check if open positions should be closed for upcoming news.
        
        Returns:
            (True, "reason") if positions should be closed
            (False, "") if positions are safe
        """
        self.refresh()
        
        now = datetime.now(ZoneInfo("UTC"))
        
        for event in self.events:
            if not event.is_high_impact:
                continue
            
            if not event.affects_pair(instrument):
                continue
            
            # Check if event is within the pre-close window
            close_window_start = event.date - timedelta(minutes=self.pre_news_minutes)
            
            if close_window_start <= now <= event.date:
                minutes_until = int((event.date - now).total_seconds() / 60)
                return (
                    True,
                    f"CLOSE POSITION - {event.title} ({event.country}) "
                    f"in {minutes_until}min at {event.date.strftime('%H:%M UTC')}"
                )
        
        return (False, "")
    
    def is_safe_to_trade(self, instrument: str, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if it's safe to trade a given instrument.
        This is an alias for can_open_trade for compatibility.
        """
        return self.can_open_trade(instrument, current_time)
    
    def get_next_high_impact(self, instrument: Optional[str] = None) -> Optional[NewsEvent]:
        """Get the next upcoming high-impact event (optionally for a specific pair)"""
        now = datetime.now(ZoneInfo("UTC"))
        
        for event in self.events:
            if event.date < now:
                continue
            if not event.is_high_impact:
                continue
            if instrument and not event.affects_pair(instrument):
                continue
            return event
        
        return None
    
    def get_all_events(self, high_impact_only: bool = False) -> List[NewsEvent]:
        """Get all cached events for the week"""
        self.refresh()
        if high_impact_only:
            return [e for e in self.events if e.is_high_impact]
        return list(self.events)

    def get_todays_events(self, high_impact_only: bool = True) -> List[NewsEvent]:
        """Get all events for today"""
        now = datetime.now(ZoneInfo("UTC"))
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        events = []
        for event in self.events:
            if today_start <= event.date < today_end:
                if high_impact_only and not event.is_high_impact:
                    continue
                events.append(event)
        
        return events
    
    def format_calendar(self, events: Optional[List[NewsEvent]] = None) -> str:
        """Format events as a readable calendar string"""
        if events is None:
            events = self.get_todays_events(high_impact_only=False)
        
        if not events:
            return "No upcoming events."
        
        lines = []
        current_date = None
        
        for event in events:
            event_date = event.date.strftime("%Y-%m-%d")
            if event_date != current_date:
                current_date = event_date
                lines.append(f"\n=== {event_date} ===")
            
            impact_icon = "HIGH" if event.is_high_impact else "MED " if event.is_medium_impact else "LOW "
            time_str = event.date.strftime("%H:%M UTC")
            
            lines.append(
                f"  [{impact_icon}] {time_str} | {event.country:3s} | {event.title}"
                + (f" (F: {event.forecast})" if event.forecast else "")
            )
        
        return "\n".join(lines)


# ============================================================================
# Standalone usage / testing
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    news = NewsFilter(
        pre_news_minutes=30,
        post_news_minutes=30,
    )
    
    print("Fetching ForexFactory calendar...")
    success = news.refresh(force=True)
    
    if success:
        print(f"\nTotal events loaded: {len(news.events)}")
        
        # Today's high-impact events
        todays = news.get_todays_events(high_impact_only=True)
        print(f"\nToday's HIGH impact events: {len(todays)}")
        for evt in todays:
            print(f"  {evt.date.strftime('%H:%M UTC')} - {evt.country} - {evt.title}")
        
        # Check each pair
        print("\n--- Trade Checks ---")
        pairs = ["EUR_USD", "USD_JPY", "GBP_USD", "AUD_USD", "NZD_USD", "USD_CHF", "USD_CAD"]
        for pair in pairs:
            can_trade, reason = news.can_open_trade(pair)
            status = "OK" if can_trade else "BLOCKED"
            print(f"  [{status}] {pair}: {reason}")
        
        # Next high-impact event
        next_event = news.get_next_high_impact()
        if next_event:
            print(f"\nNext high-impact: {next_event.title} ({next_event.country})")
            print(f"  Time: {next_event.date.strftime('%Y-%m-%d %H:%M UTC')}")
        
        # Full calendar
        print("\n--- This Week's Calendar ---")
        print(news.format_calendar(news.events[:30]))
    else:
        print("Failed to load news data!")
