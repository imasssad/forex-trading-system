"""Check detailed OANDA error"""
import sys
sys.path.insert(0, '.')

import sqlite3

conn = sqlite3.connect("data/ats_trading.db")
cursor = conn.cursor()

print("\n=== DETAILED ERROR LOGS ===\n")
cursor.execute("""
    SELECT timestamp, level, message, details 
    FROM activity_log 
    WHERE level = 'error' 
    ORDER BY timestamp DESC 
    LIMIT 10
""")

rows = cursor.fetchall()
for row in rows:
    timestamp, level, message, details = row
    print(f"\n{timestamp} | {level.upper()}")
    print(f"Message: {message}")
    if details:
        print(f"Details: {details}")
    print("-" * 80)

conn.close()
