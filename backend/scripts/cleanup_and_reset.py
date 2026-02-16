#!/usr/bin/env python3
"""
Cleanup and Reset Script
- Closes ALL open OANDA positions
- Clears database (trades, signals, activity_log)
- Syncs fresh state between OANDA and database
"""

import os
import sys
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from brokers.oanda import OandaClient


def main():
    print("\n" + "="*60)
    print("  ATS CLEANUP & RESET SCRIPT")
    print("="*60)
    
    # Initialize OANDA client
    print("\n[1/4] Connecting to OANDA...")
    try:
        client = OandaClient(practice=True)
        account = client.get_account_summary()
        print(f"  ✓ Connected to account: {client.account_id}")
        print(f"  ✓ Balance: ${account.get('balance', 'N/A')}")
    except Exception as e:
        print(f"  ✗ Failed to connect to OANDA: {e}")
        return 1
    
    # Close all OANDA trades
    print("\n[2/4] Closing all OANDA positions...")
    try:
        trades = client.get_open_trades()
        if not trades:
            print("  ✓ No open trades on OANDA")
        else:
            print(f"  Found {len(trades)} open trade(s)")
            for trade in trades:
                print(f"    Closing #{trade.id}: {trade.instrument} {trade.units} units...")
                try:
                    result = client.close_trade(trade.id)
                    if result:
                        print(f"    ✓ Closed #{trade.id}")
                except Exception as e:
                    print(f"    ✗ Failed to close #{trade.id}: {e}")
            
            # Verify all closed
            remaining = client.get_open_trades()
            if not remaining:
                print(f"  ✓ All {len(trades)} trades closed successfully")
            else:
                print(f"  ⚠ {len(remaining)} trades still open")
    except Exception as e:
        print(f"  ✗ Error closing trades: {e}")
    
    # Clear database
    print("\n[3/4] Clearing database...")
    db_path = os.environ.get("ATS_DB_PATH", "data/ats_trading.db")
    
    # Handle relative path
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)
    
    if not os.path.exists(db_path):
        print(f"  ⚠ Database not found at {db_path}")
    else:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Count records before
            cursor.execute("SELECT COUNT(*) FROM trades")
            trades_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM signals")
            signals_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM activity_log")
            activity_count = cursor.fetchone()[0]
            
            print(f"  Found: {trades_count} trades, {signals_count} signals, {activity_count} activity logs")
            
            # Clear tables
            cursor.execute("DELETE FROM trades")
            cursor.execute("DELETE FROM signals")
            cursor.execute("DELETE FROM activity_log")
            cursor.execute("DELETE FROM daily_snapshots")
            
            # Reset auto-increment
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('trades', 'signals', 'activity_log', 'daily_snapshots')")
            
            conn.commit()
            conn.close()
            
            print("  ✓ Cleared: trades, signals, activity_log, daily_snapshots")
        except Exception as e:
            print(f"  ✗ Database error: {e}")
    
    # Verify sync
    print("\n[4/4] Verifying sync...")
    try:
        oanda_trades = client.get_open_trades()
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'")
        db_open = cursor.fetchone()[0]
        conn.close()
        
        print(f"  OANDA open trades: {len(oanda_trades)}")
        print(f"  Database open trades: {db_open}")
        
        if len(oanda_trades) == 0 and db_open == 0:
            print("  ✓ OANDA and Database are in sync (both empty)")
        else:
            print("  ⚠ Mismatch detected - manual intervention needed")
    except Exception as e:
        print(f"  ✗ Verification error: {e}")
    
    # Final summary
    print("\n" + "="*60)
    print("  CLEANUP COMPLETE")
    print("="*60)
    print("\nNext steps:")
    print("  1. Restart the FastAPI server to clear cached state")
    print("  2. On server: systemctl restart fastapi")
    print("  3. Dashboard should now show empty state")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
