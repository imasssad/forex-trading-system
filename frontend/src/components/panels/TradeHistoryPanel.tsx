'use client';

import { useState, useEffect } from 'react';

interface ClosedTrade {
  id: number;
  instrument: string;
  direction: string;
  units: number;
  entry_price: number;
  exit_price: number;
  profit_loss: number;
  profit_pips: number;
  close_reason: string;
  open_time: string;
  close_time: string;
}

interface TradeHistoryPanelProps {
  compact?: boolean;
}

export default function TradeHistoryPanel({ compact = false }: TradeHistoryPanelProps) {
  const [trades, setTrades] = useState<ClosedTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [limit, setLimit] = useState(compact ? 5 : 10);
  const [offset, setOffset] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [viewAll, setViewAll] = useState(false);

  const fetchTrades = async (newLimit?: number, newOffset?: number) => {
    try {
      setLoading(true);
      const l = newLimit ?? limit;
      const o = newOffset ?? offset;
      
      const response = await fetch(`/api/trades/history?limit=${l}&offset=${o}`);
      if (!response.ok) throw new Error('Failed to fetch trade history');
      
      const data = await response.json();
      setTrades(data.trades || []);
      setTotalCount(data.count || 0);
    } catch (error) {
      console.error('Error fetching trade history:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
  }, [limit, offset]);

  const handleViewAll = () => {
    setViewAll(true);
    setLimit(1000);
    setOffset(0);
  };

  const handleViewLess = () => {
    setViewAll(false);
    setLimit(compact ? 5 : 10);
    setOffset(0);
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return '---';
    try {
      return new Date(dateString).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  if (loading && trades.length === 0) {
    return (
      <div className="card">
        <div className="px-4 py-3 border-b border-panel-border">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Trade History
          </span>
        </div>
        <div className="p-8 text-center text-muted text-xs">
          Loading...
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-panel-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Trade History
          </span>
          <span className="badge-neutral">{trades.length}</span>
        </div>
        {trades.length > 0 && !viewAll && (
          <button
            onClick={handleViewAll}
            className="text-2xs text-muted hover:text-gray-300 transition-colors"
          >
            VIEW ALL →
          </button>
        )}
        {viewAll && (
          <button
            onClick={handleViewLess}
            className="text-2xs text-muted hover:text-gray-300 transition-colors"
          >
            ← VIEW LESS
          </button>
        )}
      </div>

      {trades.length === 0 ? (
        <div className="p-8 text-center text-muted text-xs">
          No closed trades yet
        </div>
      ) : (
        <div className="divide-y divide-panel-border/50 max-h-96 overflow-y-auto">
          {trades.map((trade) => {
            const isLong = trade.direction === 'long';
            const isProfit = trade.profit_loss >= 0;

            return (
              <div key={trade.id} className="px-4 py-3 hover:bg-panel-hover/30 transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`badge text-2xs ${isLong ? 'badge-bull' : 'badge-bear'}`}>
                      {isLong ? 'LONG' : 'SHORT'}
                    </span>
                    <span className="text-sm font-semibold text-gray-100">
                      {trade.instrument.replace('_', '/')}
                    </span>
                    <span className="text-2xs text-subtle">
                      #{trade.id}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-bold ${isProfit ? 'text-bull' : 'text-bear'}`}>
                      {isProfit ? '+' : ''}${trade.profit_loss.toFixed(2)}
                    </div>
                    <div className={`text-2xs ${isProfit ? 'text-bull/70' : 'text-bear/70'}`}>
                      {isProfit ? '+' : ''}{trade.profit_pips.toFixed(1)} pips
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-2xs">
                  <div>
                    <span className="text-subtle">Entry</span>
                    <div className="text-gray-300 font-medium">{trade.entry_price.toFixed(5)}</div>
                  </div>
                  <div>
                    <span className="text-subtle">Exit</span>
                    <div className="text-gray-300 font-medium">{trade.exit_price.toFixed(5)}</div>
                  </div>
                  <div>
                    <span className="text-subtle">Opened</span>
                    <div className="text-gray-300 font-medium">{formatDate(trade.open_time)}</div>
                  </div>
                  <div>
                    <span className="text-subtle">Closed</span>
                    <div className="text-gray-300 font-medium">{formatDate(trade.close_time)}</div>
                  </div>
                  <div>
                    <span className="text-subtle">Reason</span>
                    <div className="text-gray-300 font-medium capitalize">
                      {trade.close_reason.replace(/_/g, ' ')}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
