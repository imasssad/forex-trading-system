"""
Configuration for External Signal Providers
Add your API keys and settings here
"""

from typing import Dict, Any

# External Signal Provider Configuration
# Add your API keys and settings below

SIGNAL_PROVIDER_CONFIG = {
    "zulutrade": {
        "api_key": None,  # Add your ZuluTrade API key here
        "enabled": False,
        "min_confidence": 0.7,
    },

    "forexsignals": {
        "api_key": None,  # ForexSignals.com may not have API, uses web scraping
        "enabled": True,
        "min_confidence": 0.6,
    },

    "tradingview": {
        "api_key": None,  # TradingView has limited public API
        "enabled": True,
        "min_confidence": 0.5,
    },

    # Add more providers as needed
    "myfxbook": {
        "api_key": None,
        "enabled": False,
        "min_confidence": 0.8,
    },

    "signalstart": {
        "api_key": None,
        "enabled": False,
        "min_confidence": 0.7,
    },
}

# Global settings
EXTERNAL_SIGNALS_CONFIG = {
    "auto_fetch_interval": 300,  # seconds (5 minutes)
    "min_confidence_threshold": 0.6,  # minimum confidence to import
    "max_signals_per_provider": 10,  # limit signals per fetch
    "enabled_providers": ["tradingview", "forexsignals"],  # enabled by default
}