"""Check recent error logs for OANDA issues"""
import sys
sys.path.insert(0, '.')

from database import db

logs = db.get_activity_log(limit=30)

print("\n=== RECENT ACTIVITY LOGS (Last 30) ===\n")
for log in logs:
    timestamp = log["timestamp"]
    level = log["level"].upper()
    message = log["message"]
    details = log["details"] if log["details"] else ""
    
    print(f"{timestamp} | {level:8} | {message}")
    if details:
        print(f"         Details: {details}")
    print()
