'use client';

import { useState } from 'react';
import { useOpenTrades } from '../../lib/hooks';

export default function OpenTradesPanel() {
  const { trades, refresh } = useOpenTrades();
  const [closing, setClosing] = useState<string | null>(null);
  const [closingAll, setClosingAll] = useState(false);

  const closeTrade = async (tradeId: string | number) => {
    setClosing(String(tradeId));
    try {
      const trade = trades.find(t => String(t.id) === String(tradeId));
      if (!trade) {
        alert('Trade not found.');
        return;
      }

      const exitPrice = trade.current_price || trade.entry_price;
      const profitLoss = trade.unrealized_pl || 0;

      // Ensure trade_id is sent as integer if possible
      const tradeIdInt = typeof trade.id === 'number' ? trade.id : parseInt(trade.id, 10);

      const response = await fetch('/api/trades/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trade_id: tradeIdInt,
          exit_price: exitPrice,
          profit_loss: profitLoss,
          profit_pips: 0,
          close_reason: 'manual'
        }),
      });

      if (!response.ok) {
        let errorMsg = 'Failed to close trade';
        let errorObj = null;
        try {
          errorObj = await response.json();
          errorMsg = errorObj.detail || errorMsg;
        } catch (jsonErr) {
          // If not JSON, try to get text
          try {
            errorMsg = await response.text();
          } catch {}
        }
        console.error('Close failed: Full error response:', errorObj || errorMsg);
        throw new Error(errorMsg);
      }

      refresh();
    } catch (e) {
      console.error('Close failed:', e);
      let msg = 'Unknown error';
      if (e && typeof e === 'object') {
        if ('message' in e && typeof e.message === 'string') msg = e.message;
        else if ('detail' in e && typeof e.detail === 'string') msg = e.detail;
        else msg = JSON.stringify(e);
      } else if (typeof e === 'string') {
        msg = e;
      }
      alert(`Close failed: ${msg}`);
    } finally {
      setClosing(null);
    }
  };

  const closeAll = async () => {
    setClosingAll(true);
    try {
      const response = await fetch('/api/trades/close-all', { method: 'POST' });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to close all trades');
      }
      
      refresh();
    } catch (e) {
      console.error('Close all failed:', e);
      alert(`Close all failed: ${e instanceof Error ? e.message : 'Unknown error'}`);
    } finally {
      setClosingAll(false);
    }
  };

  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-panel-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Open Positions
          </span>
          <span className="badge-neutral">{trades.length}</span>
        </div>
        {trades.length > 0 && (
          <button
            onClick={closeAll}
            disabled={closingAll}
            className="btn-danger text-2xs py-1 px-2"
          >
            {closingAll ? 'CLOSING...' : 'CLOSE ALL'}
          </button>
        )}
      </div>

      {trades.length === 0 ? (
        <div className="p-8 text-center text-muted text-xs">
          No open positions
        </div>
      ) : (
        <div className="divide-y divide-panel-border/50">
          {trades.map((trade) => {
            const isLong = trade.direction === 'long';
            const unrealizedPl = trade.unrealized_pl || 0;
            const isProfitable = unrealizedPl >= 0;
            const isClosingThis = closing === trade.id;

            return (
              <div key={trade.id} className="px-4 py-3 hover:bg-panel-hover/30 transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={`badge ${isLong ? 'badge-bull' : 'badge-bear'}`}
                    >
                      {isLong ? 'LONG' : 'SHORT'}
                    </span>
                    <span className="text-sm font-semibold text-gray-100">
                      {trade.instrument.replace('_', '/')}
                    </span>
                    <span className="text-2xs text-subtle">
                      #{trade.id}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-sm font-bold ${
                        isProfitable ? 'text-bull' : 'text-bear'
                      }`}
                    >
                      {isProfitable ? '+' : ''}
                      ${unrealizedPl.toFixed(2)}
                    </span>
                    <button
                      onClick={() => closeTrade(trade.id)}
                      disabled={isClosingThis}
                      className="text-2xs text-muted hover:text-bear transition-colors border border-panel-border rounded px-2 py-0.5 disabled:opacity-50"
                    >
                      {isClosingThis ? '...' : 'CLOSE'}
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-2xs">
                  <div>
                    <span className="text-subtle">Entry</span>
                    <div className="text-gray-300 font-medium">{trade.entry_price}</div>
                  </div>
                  <div>
                    <span className="text-subtle">Current</span>
                    <div className={`font-medium ${isProfitable ? 'text-bull' : 'text-bear'}`}>
                      {trade.current_price || trade.entry_price}
                    </div>
                  </div>
                  <div>
                    <span className="text-subtle">Opened</span>
                    <div className="text-gray-300 font-medium">
                      {trade.open_time ? new Date(trade.open_time).toLocaleString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      }) : '---'}
                    </div>
                  </div>
                  <div>
                    <span className="text-subtle">SL</span>
                    <div className="text-bear font-medium">
                      {trade.stop_loss || '---'}
                    </div>
                  </div>
                  <div>
                    <span className="text-subtle">TP</span>
                    <div className="text-bull font-medium">
                      {trade.take_profit || '---'}
                    </div>
                  </div>
                </div>

                {/* P&L progress bar */}
                <div className="mt-2 h-1 bg-panel-bg rounded-full overflow-hidden">
                  {trade.stop_loss && trade.take_profit && (
                    <div
                      className={`h-full rounded-full transition-all ${
                        isProfitable ? 'bg-bull/60' : 'bg-bear/60'
                      }`}
                      style={{
                        width: `${Math.min(
                          100,
                          Math.abs(
                            (((trade.current_price || trade.entry_price) - trade.entry_price) /
                              (trade.take_profit - trade.entry_price)) *
                              100
                          )
                        )}%`,
                      }}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
