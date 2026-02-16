#!/usr/bin/env python3
"""
Test script for external signal providers
Run this to test signal fetching without starting the full server
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.signal_providers import signal_aggregator

def main():
    print("🔍 Testing External Signal Providers")
    print("=" * 50)

    # Fetch signals from all providers
    print("📡 Fetching signals from providers...")
    signals = signal_aggregator.fetch_all_signals()

    print(f"✅ Found {len(signals)} signals")

    # Show provider stats
    stats = signal_aggregator.get_provider_stats()
    print("\n📊 Signals by Provider:")
    for provider, count in stats.items():
        print(f"  {provider}: {count} signals")

    # Show sample signals
    print("\n🎯 Sample Signals:")
    for i, signal in enumerate(signals[:5]):  # Show first 5
        print(f"  {i+1}. {signal.provider.upper()} - {signal.action.upper()} {signal.instrument} @ {signal.price} (Confidence: {signal.confidence:.1%})")

    # Test filtering
    print("\n🔍 High Confidence Signals (>70%):")
    high_conf_signals = signal_aggregator.get_filtered_signals(min_confidence=0.7)
    for signal in high_conf_signals[:3]:
        print(f"  {signal.provider.upper()} - {signal.action.upper()} {signal.instrument} (Confidence: {signal.confidence:.1%})")

    print("\n✨ Test completed!")

if __name__ == "__main__":
    main()