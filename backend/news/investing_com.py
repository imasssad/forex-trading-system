"""
Investing.com News Fetcher
Fetches economic calendar data from Investing.com's public API or web page.
"""

import json
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
from zoneinfo import ZoneInfo
from pathlib import Path
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

@dataclass
class InvestingNewsEvent:
    title: str
    country: str
    date: datetime
    impact: str
    forecast: str
    previous: str

    @property
    def is_high_impact(self) -> bool:
        return self.impact == "High"

    @property
    def is_medium_impact(self) -> bool:
        return self.impact == "Medium"

class InvestingNewsFetcher:
    CALENDAR_URL = "https://www.investing.com/economic-calendar/"

    def __init__(self, cache_file: str = "investing_news_cache.json"):
        self.cache_file = Path(cache_file)
        self.events: List[InvestingNewsEvent] = []
        self.last_fetch: Optional[datetime] = None
        self._load_cache()

    def fetch(self) -> bool:
        try:
            logger.info("Fetching Investing.com economic calendar...")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml",
            }
            response = requests.get(self.CALENDAR_URL, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.error(f"Investing.com returned status {response.status_code}")
                return False
            soup = BeautifulSoup(response.text, "html.parser")
            self.events = list(reversed(self._parse_events(soup)))
            self.last_fetch = datetime.now(ZoneInfo("UTC"))
            self._save_cache()
            logger.info(f"Loaded {len(self.events)} events from Investing.com")
            return True
        except Exception as e:
            logger.error(f"Error fetching Investing.com news: {e}")
            return False

    def _parse_events(self, soup) -> List[InvestingNewsEvent]:
        events = []
        table = soup.find("table", id="economicCalendarData")
        if not table:
            logger.error("Could not find economic calendar table on Investing.com")
            return events
        for row in table.find_all("tr", class_="js-event-item"):
            try:
                date_str = row.get("data-event-datetime")
                if not date_str:
                    continue
                event_time = datetime.fromisoformat(date_str).astimezone(ZoneInfo("UTC"))
                country = row.get("data-country") or ""
                impact = row.get("data-impact") or ""
                title = row.get("data-event-title") or "Unknown"
                forecast = row.get("data-event-forecast") or ""
                previous = row.get("data-event-previous") or ""
                events.append(InvestingNewsEvent(
                    title=title,
                    country=country,
                    date=event_time,
                    impact=impact,
                    forecast=forecast,
                    previous=previous
                ))
            except Exception as e:
                logger.debug(f"Skipping event: {e}")
                continue
        return events

    def _save_cache(self):
        try:
            cache_data = {
                "fetched_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                "events": [e.__dict__ for e in self.events]
            }
            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Could not save Investing.com cache: {e}")

    def _load_cache(self):
        try:
            if not self.cache_file.exists():
                return
            with open(self.cache_file) as f:
                cache_data = json.load(f)
            self.events = [InvestingNewsEvent(**e) for e in cache_data["events"]]
            self.last_fetch = datetime.fromisoformat(cache_data["fetched_at"])
        except Exception as e:
            logger.warning(f"Could not load Investing.com cache: {e}")
