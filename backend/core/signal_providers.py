"""
External Signal Providers
Integrates signals from various trading platforms and signal services
"""

import logging
import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod
import time
import re
from dataclasses import dataclass

# Import configuration
try:
    from config.signal_providers import SIGNAL_PROVIDER_CONFIG, EXTERNAL_SIGNALS_CONFIG
except ImportError:
    # Fallback if config not found
    SIGNAL_PROVIDER_CONFIG = {}
    EXTERNAL_SIGNALS_CONFIG = {
        "enabled_providers": ["tradingview", "forexsignals"],
        "min_confidence_threshold": 0.6
    }

logger = logging.getLogger(__name__)


@dataclass
class ExternalSignal:
    """Signal from external provider"""
    provider: str
    instrument: str
    action: str  # 'buy' or 'sell'
    price: float
    timestamp: str
    confidence: float  # 0-1
    timeframe: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = None


class SignalProvider(ABC):
    """Base class for signal providers"""

    def __init__(self, name: str, api_key: Optional[str] = None):
        self.name = name
        self.api_key = api_key
        self.last_fetch = None
        self.cache_duration = 300  # 5 minutes

    @abstractmethod
    def fetch_signals(self) -> List[ExternalSignal]:
        """Fetch signals from the provider"""
        pass

    def _normalize_instrument(self, instrument: str) -> str:
        """Normalize instrument names to OANDA format"""
        # Common mappings
        mappings = {
            'EURUSD': 'EUR_USD',
            'GBPUSD': 'GBP_USD',
            'USDJPY': 'USD_JPY',
            'AUDUSD': 'AUD_USD',
            'USDCAD': 'USD_CAD',
            'USDCHF': 'USD_CHF',
            'NZDUSD': 'NZD_USD',
            'EURJPY': 'EUR_JPY',
            'GBPJPY': 'GBP_JPY',
            'BTCUSD': 'BTC_USD',
            'ETHUSD': 'ETH_USD',
        }
        return mappings.get(instrument.upper(), instrument)


class TradingViewProvider(SignalProvider):
    """Fetch signals from TradingView screener or community"""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("tradingview", api_key)
        self.base_url = "https://www.tradingview.com/api/v1"

    def fetch_signals(self) -> List[ExternalSignal]:
        """Fetch signals from TradingView (limited public API)"""
        signals = []

        try:
            # This is a simplified example - TradingView has limited public APIs
            # In practice, you'd need to use their private APIs or web scraping
            # For now, we'll simulate some signals

            # Popular forex pairs to check
            pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD']

            for pair in pairs:
                # Simulate fetching technical analysis
                signal = self._analyze_pair(pair)
                if signal:
                    signals.append(signal)

        except Exception as e:
            logger.error(f"TradingView fetch error: {e}")

        return signals

    def _analyze_pair(self, pair: str) -> Optional[ExternalSignal]:
        """Analyze a pair using TradingView-like logic"""
        # This would normally fetch from TradingView API
        # For demo purposes, return occasional signals
        import random

        if random.random() < 0.1:  # 10% chance of signal
            action = 'buy' if random.random() > 0.5 else 'sell'
            price = 1.0 + random.random() * 0.1  # Mock price

            return ExternalSignal(
                provider=self.name,
                instrument=self._normalize_instrument(pair),
                action=action,
                price=round(price, 5),
                timestamp=datetime.utcnow().isoformat(),
                confidence=0.7,
                timeframe='H1',
                metadata={'source': 'technical_analysis'}
            )

        return None


class ForexSignalsProvider(SignalProvider):
    """Fetch signals from forexsignals.com"""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("forexsignals", api_key)
        self.base_url = "https://www.forexsignals.com"

    def fetch_signals(self) -> List[ExternalSignal]:
        """Fetch signals from ForexSignals.com"""
        signals = []

        try:
            # Note: This would require web scraping or API access
            # Most signal sites don't have public APIs
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(f"{self.base_url}/signals", headers=headers, timeout=10)
            response.raise_for_status()

            # Parse HTML for signals (simplified)
            signals = self._parse_forexsignals_html(response.text)

        except Exception as e:
            logger.error(f"ForexSignals fetch error: {e}")

        return signals

    def _parse_forexsignals_html(self, html: str) -> List[ExternalSignal]:
        """Parse signals from ForexSignals HTML"""
        signals = []

        # This is a simplified parser - would need proper HTML parsing
        # Look for signal patterns in the HTML
        signal_patterns = [
            r'(\w+/\w+)\s+(BUY|SELL)\s+@?\s*([\d.]+)',
            r'Signal:\s*(\w+/\w+)\s+(BUY|SELL)',
        ]

        for pattern in signal_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if len(match) >= 2:
                    instrument = match[0].replace('/', '_')
                    action = match[1].lower()
                    price = float(match[2]) if len(match) > 2 else None

                    signals.append(ExternalSignal(
                        provider=self.name,
                        instrument=self._normalize_instrument(instrument),
                        action=action,
                        price=price,
                        timestamp=datetime.utcnow().isoformat(),
                        confidence=0.8,
                        timeframe='H1',
                        metadata={'source': 'forexsignals_com'}
                    ))

        return signals


class ZuluTradeProvider(SignalProvider):
    """Fetch signals from ZuluTrade"""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("zulutrade", api_key)
        self.base_url = "https://www.zulutrade.com"

    def fetch_signals(self) -> List[ExternalSignal]:
        """Fetch signals from ZuluTrade"""
        signals = []

        try:
            # ZuluTrade has an API for signal providers
            if self.api_key:
                headers = {'Authorization': f'Bearer {self.api_key}'}
                response = requests.get(f"{self.base_url}/api/signals", headers=headers, timeout=10)
                response.raise_for_status()

                data = response.json()
                signals = self._parse_zulutrade_api(data)
            else:
                logger.warning("ZuluTrade API key required")

        except Exception as e:
            logger.error(f"ZuluTrade fetch error: {e}")

        return signals

    def _parse_zulutrade_api(self, data: Dict) -> List[ExternalSignal]:
        """Parse ZuluTrade API response"""
        signals = []

        for signal_data in data.get('signals', []):
            signals.append(ExternalSignal(
                provider=self.name,
                instrument=self._normalize_instrument(signal_data['instrument']),
                action=signal_data['action'].lower(),
                price=signal_data.get('price'),
                timestamp=signal_data['timestamp'],
                confidence=signal_data.get('confidence', 0.7),
                timeframe=signal_data.get('timeframe', 'H1'),
                stop_loss=signal_data.get('stop_loss'),
                take_profit=signal_data.get('take_profit'),
                metadata={'zulutrade_id': signal_data.get('id')}
            ))

        return signals


class SignalAggregator:
    """Aggregates signals from multiple providers"""

    def __init__(self):
        self.providers: List[SignalProvider] = []
        self.last_signals: List[ExternalSignal] = []
        self.signal_cache = {}

    def add_provider(self, provider: SignalProvider):
        """Add a signal provider"""
        self.providers.append(provider)
        logger.info(f"Added signal provider: {provider.name}")

    def fetch_all_signals(self) -> List[ExternalSignal]:
        """Fetch signals from all providers"""
        all_signals = []

        for provider in self.providers:
            try:
                signals = provider.fetch_signals()
                all_signals.extend(signals)
                logger.info(f"Fetched {len(signals)} signals from {provider.name}")
            except Exception as e:
                logger.error(f"Error fetching from {provider.name}: {e}")

        # Cache signals
        self.last_signals = all_signals
        self.signal_cache['last_update'] = datetime.utcnow()

        return all_signals

    def get_filtered_signals(self, min_confidence: float = 0.6,
                           instruments: List[str] = None) -> List[ExternalSignal]:
        """Get filtered signals"""
        signals = self.last_signals

        if min_confidence > 0:
            signals = [s for s in signals if s.confidence >= min_confidence]

        if instruments:
            signals = [s for s in signals if s.instrument in instruments]

        return signals

    def get_provider_stats(self) -> Dict[str, int]:
        """Get signal count by provider"""
        stats = {}
        for signal in self.last_signals:
            stats[signal.provider] = stats.get(signal.provider, 0) + 1
        return stats

class MyfxbookProvider(SignalProvider):
    """Fetch signals from Myfxbook signal providers"""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__("myfxbook", api_key)
        self.base_url = "https://www.myfxbook.com"

    def fetch_signals(self) -> List[ExternalSignal]:
        """Fetch signals from Myfxbook (requires API access)"""
        signals = []

        try:
            if not self.api_key:
                logger.warning("Myfxbook API key required")
                return signals

            # Myfxbook has an API for signal providers
            headers = {'Authorization': f'Bearer {self.api_key}'}
            response = requests.get(f"{self.base_url}/api/signals", headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            signals = self._parse_myfxbook_api(data)

        except Exception as e:
            logger.error(f"Myfxbook fetch error: {e}")

        return signals

    def _parse_myfxbook_api(self, data: Dict) -> List[ExternalSignal]:
        """Parse Myfxbook API response"""
        signals = []

        for signal_data in data.get('signals', []):
            signals.append(ExternalSignal(
                provider=self.name,
                instrument=self._normalize_instrument(signal_data['symbol']),
                action=signal_data['type'].lower(),  # 'buy' or 'sell'
                price=signal_data.get('price'),
                timestamp=signal_data['timestamp'],
                confidence=signal_data.get('confidence', 0.8),
                timeframe=signal_data.get('timeframe', 'H1'),
                stop_loss=signal_data.get('stopLoss'),
                take_profit=signal_data.get('takeProfit'),
                metadata={'myfxbook_id': signal_data.get('id')}
            ))

        return signals

# Global aggregator instance
signal_aggregator = SignalAggregator()

# Initialize with configured providers
for provider_name in EXTERNAL_SIGNALS_CONFIG.get("enabled_providers", []):
    config = SIGNAL_PROVIDER_CONFIG.get(provider_name, {})
    if config.get("enabled", True):
        api_key = config.get("api_key")

        if provider_name == "zulutrade":
            signal_aggregator.add_provider(ZuluTradeProvider(api_key))
        elif provider_name == "forexsignals":
            signal_aggregator.add_provider(ForexSignalsProvider(api_key))
        elif provider_name == "tradingview":
            signal_aggregator.add_provider(TradingViewProvider(api_key))
        elif provider_name == "myfxbook":
            signal_aggregator.add_provider(MyfxbookProvider(api_key))
        # Add more providers as implemented