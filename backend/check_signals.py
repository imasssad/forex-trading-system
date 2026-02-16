#!/usr/bin/env python3
"""Quick script to check signals in database"""

from database.db import get_db

with get_db() as conn:
    cursor = conn.cursor()
    
    # Count total signals
    cursor.execute('SELECT COUNT(*) FROM signals')
    total = cursor.fetchone()[0]
    print(f"Total signals in database: {total}")
    
    # Get latest signals
    cursor.execute('SELECT id, timestamp, instrument, action, approved FROM signals ORDER BY timestamp DESC LIMIT 5')
    rows = cursor.fetchall()
    print("\nLatest 5 signals:")
    for row in rows:
        print(f"  ID {row[0]}: {row[1]} | {row[2]} | {row[3]} | Approved: {row[4]}")
    
    # Check settings
    cursor.execute('SELECT key, value FROM settings WHERE key IN ("paper_trading", "oanda_account_id")')
    settings = cursor.fetchall()
    print("\nRelevant settings:")
    for key, val in settings:
        print(f"  {key} = {val}")
