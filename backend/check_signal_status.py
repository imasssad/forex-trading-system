#!/usr/bin/env python3
"""Check why signals aren't being generated"""

from database.db import get_db
from datetime import datetime, timedelta

print("=" * 60)
print("SIGNAL GENERATION DIAGNOSTIC")
print("=" * 60)

with get_db() as conn:
    cursor = conn.cursor()
    
    # Check total signals
    cursor.execute('SELECT COUNT(*) FROM signals')
    total = cursor.fetchone()[0]
    print(f"\n📊 Total Signals in DB: {total}")
    
    # Check recent signals (last hour)
    cursor.execute('SELECT COUNT(*) FROM signals WHERE timestamp > datetime("now", "-1 hour")')
    recent = cursor.fetchone()[0]
    print(f"📊 Signals in Last Hour: {recent}")
    
    # Last 5 signals
    cursor.execute('SELECT id, timestamp, instrument, action, approved FROM signals ORDER BY timestamp DESC LIMIT 5')
    print("\n📋 Last 5 Signals:")
    for row in cursor.fetchall():
        status = "✓ APPROVED" if row[4] else "✗ REJECTED"
        print(f"  #{row[0]}: {row[1]} | {row[2]} {row[3].upper()} | {status}")
    
    # Check open trades
    cursor.execute('SELECT COUNT(*) FROM trades WHERE status="open"')
    open_trades = cursor.fetchone()[0]
    print(f"\n📈 Open Trades: {open_trades}")
    
    if open_trades > 0:
        cursor.execute('SELECT instrument, direction FROM trades WHERE status="open"')
        print("  Open Positions:")
        for row in cursor.fetchall():
            print(f"    - {row[0]} {row[1].upper()}")
    
    # Recent activity logs (last 30)
    cursor.execute('SELECT timestamp, level, message, details FROM activity_log ORDER BY timestamp DESC LIMIT 30')
    print("\n📝 Recent Activity (Last 30):")
    for row in cursor.fetchall():
        timestamp = row[0]
        level = row[1].upper()
        message = row[2]
        details = row[3] if row[3] else ""
        
        # Highlight important messages
        if "Blocked" in message or "signal" in message.lower():
            print(f"  ⚠️  {timestamp} [{level}] {message}")
            if details and len(details) < 150:
                print(f"      └─ {details}")
        elif "error" in level.lower():
            print(f"  ❌ {timestamp} [{level}] {message}")
            if details and len(details) < 150:
                print(f"      └─ {details}")
        elif "LIVE" in message or "PAPER" in message:
            print(f"  💰 {timestamp} [{level}] {message}")
        else:
            # Only print first 80 chars for other messages
            msg_short = message[:80] + "..." if len(message) > 80 else message
            print(f"  •  {timestamp} [{level}] {msg_short}")

print("\n" + "=" * 60)
print("ANALYSIS:")
print("=" * 60)

with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM signals WHERE timestamp > datetime("now", "-1 hour")')
    recent_signals = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM trades WHERE status="open"')
    open_count = cursor.fetchone()[0]
    
    if recent_signals == 0:
        print("⚠️  NO SIGNALS in last hour")
        print("\nPossible Reasons:")
        print("  1. No pairs meeting technical criteria (AutoTrend + HTF + RSI + breakout)")
        print("  2. News filter blocking (high impact news nearby)")
        print("  3. Correlation filter blocking (similar pairs already open)")
        if open_count > 0:
            print(f"  4. Already have {open_count} open position(s) - correlated pairs blocked")
        print("  5. Signal generator may not be running (check backend logs)")
        print("\n💡 This is NORMAL - system only signals when conditions align!")
    else:
        print(f"✓ System is generating signals ({recent_signals} in last hour)")
        print("  Signal generation is WORKING correctly")

print("=" * 60)
