'use client';

import { useStatus, useAccount } from '../lib/hooks';

interface StatusBarProps {
  onMenuClick?: () => void;
}

export default function StatusBar({ onMenuClick }: StatusBarProps) {
  const { status: s, error: statusError, isLive: statusLive } = useStatus();
  const { account: a, error: accountError, isLive: accountLive } = useAccount();

  // Default values when data is not available
  const defaultStatus = {
    bot_running: false,
    active_sessions: [],
    can_trade: false,
    can_trade_reason: 'Backend Offline',
    daily_stats: {
      pnl_today: 0,
      wins_today: 0,
      losses_today: 0
    }
  };

  const defaultAccount = {
    balance: 0,
    nav: 0,
    unrealized_pl: 0,
    margin_used: 0,
    margin_available: 0,
    open_trade_count: 0
  };

  const status = s || defaultStatus;
  const account = a || defaultAccount;

  return (
    <div className="h-10 bg-panel-surface border-b border-panel-border flex items-center px-4 gap-6 shrink-0">
      {/* Mobile menu button - only visible on mobile, positioned absolutely */}
      {onMenuClick && (
        <button
          onClick={onMenuClick}
          className="lg:hidden mr-2 p-1 text-gray-400 hover:text-gray-200"
        >
          ☰
        </button>
      )}

      {/* System status */}
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            statusLive && status.bot_running ? 'bg-bull animate-pulse-slow' : 'bg-bear'
          }`}
        />
        <span className="text-2xs text-muted uppercase tracking-wider">
          {statusLive && status.bot_running ? 'System Active' : 'System Offline'}
        </span>
      </div>

      <div className="h-4 w-px bg-panel-border" />

      {/* Sessions */}
      <div className="flex items-center gap-1.5">
        <span className="text-2xs text-subtle">Sessions:</span>
        {status.active_sessions && status.active_sessions.length > 0 ? (
          status.active_sessions.map((session) => (
            <span
              key={session}
              className="badge-neutral text-2xs"
            >
              {session}
            </span>
          ))
        ) : (
          <span className="text-2xs text-muted">None</span>
        )}
      </div>

      <div className="h-4 w-px bg-panel-border" />

      {/* Can trade status */}
      <div className="flex items-center gap-1.5">
        <div
          className={`w-1.5 h-1.5 rounded-full ${
            statusLive && status.can_trade ? 'bg-bull' : 'bg-bear'
          }`}
        />
        <span className="text-2xs text-muted">
          {statusLive && status.can_trade ? 'CLEAR TO TRADE' : (status.can_trade_reason || 'Backend Offline')}
        </span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Today's P&L */}
      <div className="flex items-center gap-3">
        <div className="text-right">
          <div className="text-2xs text-subtle">TODAY P&L</div>
          <div
            className={`text-xs font-semibold ${
              statusLive && status.daily_stats && status.daily_stats.pnl_today >= 0 ? 'text-bull' : 'text-bear'
            }`}
          >
            {statusLive && status.daily_stats ? (
              <>
                {status.daily_stats.pnl_today >= 0 ? '+' : ''}
                ${status.daily_stats.pnl_today.toFixed(2)}
              </>
            ) : (
              '--'
            )}
          </div>
        </div>

        <div className="h-4 w-px bg-panel-border" />

        <div className="text-right">
          <div className="text-2xs text-subtle">BALANCE</div>
          <div className="text-xs font-semibold text-gray-200">
            {accountLive && account.balance ? (
              `$${account.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
            ) : (
              '--'
            )}
          </div>
        </div>

        <div className="h-4 w-px bg-panel-border" />

        <div className="text-right">
          <div className="text-2xs text-subtle">W/L TODAY</div>
          <div className="text-xs font-semibold">
            {statusLive && status.daily_stats ? (
              <>
                <span className="text-bull">{status.daily_stats.wins_today || 0}</span>
                <span className="text-subtle">/</span>
                <span className="text-bear">{status.daily_stats.losses_today || 0}</span>
              </>
            ) : (
              <span className="text-muted">--/--</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
