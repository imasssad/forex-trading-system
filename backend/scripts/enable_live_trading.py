"""
Enable live trading on OANDA (disable paper trading mode)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db as database

# Update paper_trading setting to False
database.set_setting('paper_trading', 'false')
print("✅ Live trading enabled (paper_trading = False)")
print("⚠️  WARNING: Trades will now execute on your OANDA account!")
print("⚠️  Make sure you're using the practice account (fxpractice) for testing.")
