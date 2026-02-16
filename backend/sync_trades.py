"""
Sync local database trades with OANDA actual trades.
Closes any orphaned trades (locally recorded but not on OANDA).
"""
import sys
sys.path.insert(0, '.')

from database import db
from brokers.oanda import OandaClient
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def sync_trades_with_oanda():
    """
    Compare local open trades with actual OANDA trades.
    Close any trades that exist locally but not on OANDA (failed executions).
    """
    # Get OANDA client
    oanda = OandaClient(
        api_key=os.getenv("OANDA_API_KEY"),
        account_id=os.getenv("OANDA_ACCOUNT_ID"),
        practice=True
    )
    
    # Get actual OANDA trades
    oanda_trades = oanda.get_open_trades()
    oanda_trade_ids = {trade.id for trade in oanda_trades}
    
    print(f"\n=== TRADE SYNC ===")
    print(f"OANDA has {len(oanda_trades)} open trades")
    for trade in oanda_trades:
        print(f"  ✓ {trade.instrument} {trade.id} ({trade.units} units)")
    
    # Get local open trades
    local_trades = db.get_open_trades()
    print(f"\nLocal DB has {len(local_trades)} open trades")
    
    orphaned_count = 0
    
    for local_trade in local_trades:
        trade_id = local_trade['id']
        oanda_id = local_trade.get('oanda_trade_id')
        instrument = local_trade['instrument']
        direction = local_trade['direction']
        
        # Check if this local trade exists on OANDA
        if oanda_id and oanda_id in oanda_trade_ids:
            print(f"  ✓ Trade #{trade_id} ({instrument} {direction.upper()}) - SYNCED with OANDA #{oanda_id}")
        else:
            # Orphaned trade - exists locally but not on OANDA
            orphaned_count += 1
            print(f"  ✗ Trade #{trade_id} ({instrument} {direction.upper()}) - ORPHANED (OANDA ID: {oanda_id or 'None'})")
            
            # Close this orphaned trade
            db.close_trade(
                trade_id=trade_id,
                exit_price=local_trade['entry_price'],  # Use entry as exit (no execution)
                profit_loss=0.0,
                profit_pips=0.0,
                close_reason="EXECUTION_FAILED - Trade never opened on OANDA"
            )
            print(f"    → Closed as FAILED")
    
    print(f"\n✓ Sync complete: {orphaned_count} orphaned trades closed\n")
    return orphaned_count

if __name__ == "__main__":
    try:
        cleaned = sync_trades_with_oanda()
        print(f"✓ Cleaned {cleaned} failed trades")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
