"""Check for OANDA errors and recent signals"""
import sys
sys.path.insert(0, '.')

from database import db

# Check for error logs
print("\n=== ERROR LOGS ===\n")
error_logs = db.get_activity_log(limit=50, level="error")
if error_logs:
    for log in error_logs:
        timestamp = log["timestamp"]
        message = log["message"]
        details = log["details"] if log["details"] else ""
        
        print(f"{timestamp} | {message}")
        if details:
            print(f"         Details: {details}")
        print()
else:
    print("No error logs found in the last 50 entries\n")

# Check recent signals
print("\n=== RECENT SIGNALS (Last 10) ===\n")
signals = db.get_signals(limit=10)
for sig in signals:
    timestamp = sig["timestamp"]
    instrument = sig["instrument"]
    action = sig["action"]
    price = sig.get("price", 0)
    approved = "✓ APPROVED" if sig["approved"] else "✗ REJECTED"
    reject_reason = sig.get("reject_reason", "")
    
    print(f"{timestamp} | {instrument:10} | {action:8} @ {price:.5f} | {approved}")
    if reject_reason:
        print(f"         Reason: {reject_reason}")
    print()

# Check recent trades
print("\n=== RECENT TRADES (Last 5) ===\n")
trades = db.get_open_trades()
if trades:
    for trade in trades:
        print(f"ID: {trade['id']} | {trade['instrument']} | {trade['direction'].upper()} | "
              f"Entry: {trade['entry_price']:.5f} | SL: {trade['stop_loss']:.5f} | "
              f"TP: {trade['take_profit']:.5f}")
else:
    print("No open trades found\n")
