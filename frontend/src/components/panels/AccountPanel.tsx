'use client';

import { useAccount, useStatus } from '../../lib/hooks';

export default function AccountPanel() {
  const { account: a, isLive: accountLive } = useAccount();
  const { status: s, isLive: statusLive } = useStatus();

  // Default values
  const account = a || {
    nav: 0,
    unrealized_pl: 0,
    open_trade_count: 0,
    margin_used: 0,
    balance: 0
  };

  const status = s || {
    can_trade: false,
    consecutive_losses: 0,
    uptime_hours: 0
  };

  const stats = [
    {
      label: 'NAV',
      value: accountLive ? `$${account.nav.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '--',
      color: 'text-gray-100',
    },
    {
      label: 'Unrealized P&L',
      value: accountLive ? `${account.unrealized_pl >= 0 ? '+' : ''}$${account.unrealized_pl.toFixed(2)}` : '--',
      color: accountLive && account.unrealized_pl >= 0 ? 'text-bull' : 'text-bear',
    },
    {
      label: 'Open Trades',
      value: accountLive ? `${account.open_trade_count} / ${statusLive && status.can_trade ? '3 max' : 'PAUSED'}` : '--',
      color: 'text-gray-100',
    },
    {
      label: 'Margin Used',
      value: accountLive ? `$${account.margin_used.toFixed(2)}` : '--',
      color: 'text-gray-400',
    },
    {
      label: 'Loss Streak',
      value: statusLive ? `${status.consecutive_losses} / 4` : '--',
      color: statusLive && status.consecutive_losses >= 3 ? 'text-warn' : 'text-gray-400',
    },
    {
      label: 'Uptime',
      value: statusLive ? `${status.uptime_hours.toFixed(1)}h` : '--',
      color: 'text-gray-400',
    },
  ];

  return (
    <div className="card p-0">
      <div className="glow-line" />
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-x divide-panel-border">
        {stats.map((stat) => (
          <div key={stat.label} className="p-3">
            <div className="stat-label mb-1">{stat.label}</div>
            <div className={`stat-value text-lg ${stat.color}`}>{stat.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
