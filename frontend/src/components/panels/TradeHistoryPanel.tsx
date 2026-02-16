'use client';

import { useTradeHistory } from '../../lib/hooks';

export default function TradeHistoryPanel({ compact = false }: { compact?: boolean }) {
  const { trades: allTrades } = useTradeHistory();
  const trades = compact ? allTrades.slice(0, 5) : allTrades;

  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-panel-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Trade History
          </span>
          <span className="badge-neutral">{allTrades.length} total</span>
        </div>
        {compact && (
          <span className="text-2xs text-accent-cyan cursor-pointer hover:underline">
            View All →
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-2xs">
          <thead>
            <tr className="text-left text-subtle uppercase tracking-wider border-b border-panel-border">
              <th className="px-4 py-2 font-medium">Pair</th>
              <th className="px-4 py-2 font-medium">Dir</th>
              <th className="px-4 py-2 font-medium">Entry</th>
              <th className="px-4 py-2 font-medium">Exit</th>
              <th className="px-4 py-2 font-medium text-right">Pips</th>
              <th className="px-4 py-2 font-medium text-right">P&L</th>
              <th className="px-4 py-2 font-medium">Reason</th>
              <th className="px-4 py-2 font-medium">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-panel-border/30">
            {trades.map((trade) => {
              const isWin = trade.profit_loss >= 0;
              return (
                <tr
                  key={trade.id}
                  className="hover:bg-panel-hover/30 transition-colors"
                >
                  <td className="px-4 py-2.5 font-semibold text-gray-200">
                    {trade.instrument.replace('_', '/')}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={trade.direction === 'long' ? 'text-bull' : 'text-bear'}>
                      {trade.direction === 'long' ? '▲ BUY' : '▼ SELL'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-400">{trade.entry_price}</td>
                  <td className="px-4 py-2.5 text-gray-400">{trade.exit_price}</td>
                  <td className={`px-4 py-2.5 text-right font-medium ${isWin ? 'text-bull' : 'text-bear'}`}>
                    {isWin ? '+' : ''}{trade.profit_pips.toFixed(1)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-bold ${isWin ? 'text-bull' : 'text-bear'}`}>
                    {isWin ? '+' : ''}${trade.profit_loss.toFixed(2)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`badge ${
                      trade.close_reason.includes('Profit') ? 'badge-bull' :
                      trade.close_reason.includes('Stop') ? 'badge-bear' : 'badge-neutral'
                    }`}>
                      {trade.close_reason}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-subtle">
                    {new Date(trade.close_time).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
