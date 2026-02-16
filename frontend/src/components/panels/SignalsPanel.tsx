'use client';

import { useState, useCallback, useRef } from 'react';
import useSWR from 'swr';

interface Signal {
  id: number;
  timestamp: string;
  instrument: string;
  action: string;
  price: number;
  rsi: number;
  atr_value: number | null;
  approved: boolean;
  reject_reason: string | null;
}

interface ExternalSignal {
  provider: string;
  instrument: string;
  action: string;
  price: number;
  timestamp: string;
  confidence: number;
  timeframe: string;
  stop_loss: number | null;
  take_profit: number | null;
  metadata: any;
}

async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

interface SystemStatus {
  bot_running: boolean;
  uptime_hours: number;
  uptime_seconds: number;
  signal_generation_running: boolean;
  external_signals_running: boolean;
  last_signal_time: string | null;
  last_signal_pair: string | null;
  last_signal_type: string | null;
}

interface CorrelationStatus {
  open_positions: { pair: string; direction: string }[];
  blocked_pairs: { pair: string; blocked_directions: string; reason: string }[];
  available_pairs: string[];
  correlation_threshold: number;
}

export default function SignalsPanel() {
  const [filter, setFilter] = useState<'all' | 'approved' | 'rejected'>('all');
  const [showExternal, setShowExternal] = useState(false);
  const [showCorrelation, setShowCorrelation] = useState(false);
  const [notifications, setNotifications] = useState<{ id: string; message: string; type: 'success' | 'error' | 'info' }[]>([]);
  const notificationTimeoutRef = useRef<{ [key: string]: NodeJS.Timeout }>({});

  const showNotification = useCallback((message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = Date.now().toString();
    setNotifications((prev) => [...prev, { id, message, type }]);

    // Auto-dismiss after 3 seconds
    notificationTimeoutRef.current[id] = setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id));
      delete notificationTimeoutRef.current[id];
    }, 3000);
  }, []);

  const { data, error } = useSWR<{ count: number; signals: Signal[] }>(
    `/api/signals?limit=50${filter === 'approved' ? '&approved_only=true' : ''}`,
    fetcher,
    { refreshInterval: 5_000 }
  );

  const { data: status } = useSWR<SystemStatus>('/api/status', fetcher, {
    refreshInterval: 2_000,
  });

  const { data: correlationStatus } = useSWR<CorrelationStatus>(
    '/api/correlation-status',
    fetcher,
    { refreshInterval: 5_000 }
  );

  const { data: externalData, error: externalError } = useSWR<{ count: number; signals: ExternalSignal[] }>(
    showExternal ? '/api/external-signals?min_confidence=0.5' : null,
    fetcher,
    { refreshInterval: 10_000 }
  );

  const signals = data?.signals ?? [];
  const filtered =
    filter === 'rejected'
      ? signals.filter((s) => !s.approved)
      : signals;

  const externalSignals = externalData?.signals ?? [];

  const formatUptime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) return `${hrs}h ${mins}m`;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-panel-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Trading Signals
          </span>
          <span className="badge-neutral">{filtered.length}</span>
          {showExternal && (
            <span className="badge-accent">{externalSignals.length} external</span>
          )}
          {status && (
            <span className="text-2xs text-subtle">•</span>
          )}
          {status && (
            <span className="text-2xs text-subtle">
              Runtime: {formatUptime(status.uptime_seconds)}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setShowCorrelation(!showCorrelation)}
            className={`text-2xs px-2 py-1 rounded transition-colors ${
              showCorrelation
                ? 'bg-accent-orange/15 text-accent-orange border border-accent-orange/30'
                : 'text-subtle hover:text-gray-300 border border-transparent'
            }`}
            title="Show correlation filter status"
          >
            CORRELATION
          </button>
          <button
            onClick={() => setShowExternal(!showExternal)}
            className={`text-2xs px-2 py-1 rounded transition-colors ${
              showExternal
                ? 'bg-accent-purple/15 text-accent-purple border border-accent-purple/30'
                : 'text-subtle hover:text-gray-300 border border-transparent'
            }`}
          >
            EXTERNAL
          </button>
          {(['all', 'approved', 'rejected'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-2xs px-2 py-1 rounded transition-colors ${
                filter === f
                  ? 'bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30'
                  : 'text-subtle hover:text-gray-300 border border-transparent'
              }`}
            >
              {f.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Signal Generation Controls */}
      <div className="px-4 py-2 border-b border-panel-border bg-panel-hover/20">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-300">Auto Signal Generation</span>
            {status && (
              <div className="flex items-center gap-1.5">
                <div
                  className={`w-2 h-2 rounded-full ${
                    status.signal_generation_running
                      ? 'bg-bull animate-pulse'
                      : 'bg-gray-600'
                  }`}
                />
                <span
                  className={`text-2xs font-medium ${
                    status.signal_generation_running
                      ? 'text-bull'
                      : 'text-gray-500'
                  }`}
                >
                  {status.signal_generation_running ? 'RUNNING' : 'STOPPED'}
                </span>
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={async () => {
                try {
                  const res = await fetch('/api/signals/start-generation', { method: 'POST' });
                  const result = await res.json();
                  if (res.ok) {
                    if (result.status === 'already_running') {
                      showNotification('Signal generation is already running', 'info');
                    } else {
                      showNotification('✓ Signal generation started', 'success');
                    }
                  } else {
                    showNotification('Failed to start signal generation', 'error');
                  }
                } catch (e) {
                  showNotification('Error starting signal generation', 'error');
                }
              }}
              disabled={status?.signal_generation_running}
              className={`text-2xs px-3 py-1 rounded transition-colors ${
                status?.signal_generation_running
                  ? 'bg-gray-700 text-gray-500 border border-gray-600 cursor-not-allowed'
                  : 'bg-bull/20 text-bull border border-bull/30 hover:bg-bull/30'
              }`}
            >
              START
            </button>
            <button
              onClick={async () => {
                try {
                  const res = await fetch('/api/signals/stop-generation', { method: 'POST' });
                  if (res.ok) showNotification('✓ Signal generation stopped', 'success');
                  else showNotification('Failed to stop signal generation', 'error');
                } catch (e) {
                  showNotification('Error stopping signal generation', 'error');
                }
              }}
              disabled={!status?.signal_generation_running}
              className={`text-2xs px-3 py-1 rounded transition-colors ${
                !status?.signal_generation_running
                  ? 'bg-gray-700 text-gray-500 border border-gray-600 cursor-not-allowed'
                  : 'bg-bear/20 text-bear border border-bear/30 hover:bg-bear/30'
              }`}
            >
              STOP
            </button>
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-300">External Signal Providers</span>
            {status && status.last_signal_time && (
              <span className="text-2xs text-subtle">
                Last: {status.last_signal_pair} {status.last_signal_type?.toUpperCase()}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={async () => {
                try {
                  const res = await fetch('/api/external-signals/fetch', { method: 'POST' });
                  const data = await res.json();
                  showNotification(`Fetched ${data.total_signals} signals from ${Object.keys(data.provider_stats).length} providers`, 'success');
                } catch (e) {
                  showNotification('Error fetching external signals', 'error');
                }
              }}
              className="text-2xs px-3 py-1 bg-accent-purple/20 text-accent-purple border border-accent-purple/30 rounded hover:bg-accent-purple/30 transition-colors"
            >
              FETCH
            </button>
            <button
              onClick={async () => {
                try {
                  const res = await fetch('/api/external-signals/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ min_confidence: 0.7 })
                  });
                  const data = await res.json();
                  showNotification(`Imported ${data.count} external signals`, 'success');
                } catch (e) {
                  showNotification('Error importing external signals', 'error');
                }
              }}
              className="text-2xs px-3 py-1 bg-accent-green/20 text-accent-green border border-accent-green/30 rounded hover:bg-accent-green/30 transition-colors"
            >
              IMPORT
            </button>
          </div>
        </div>
      </div>

      {/* Correlation Filter Status */}
      {showCorrelation && correlationStatus && (
        <div className="px-4 py-3 border-b border-panel-border bg-accent-orange/5">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold text-accent-orange uppercase tracking-wider">
              Correlation Filter Status
            </h3>
            <span className="text-2xs text-subtle">
              Threshold: {(correlationStatus.correlation_threshold * 100).toFixed(0)}%
            </span>
          </div>
          
          {correlationStatus.open_positions.length > 0 && (
            <div className="mb-3">
              <div className="text-2xs text-gray-400 mb-1">Open Positions:</div>
              <div className="flex flex-wrap gap-1.5">
                {correlationStatus.open_positions.map((pos, i) => (
                  <span
                    key={i}
                    className="text-2xs px-2 py-1 rounded bg-bull/10 text-bull border border-bull/30"
                  >
                    {pos.pair.replace('_', '/')} {pos.direction.toUpperCase()}
                  </span>
                ))}
              </div>
            </div>
          )}
          
          {correlationStatus.blocked_pairs.length > 0 && (
            <div className="mb-3">
              <div className="text-2xs text-gray-400 mb-1">❌ Blocked Pairs:</div>
              <div className="space-y-1.5">
                {correlationStatus.blocked_pairs.map((blocked, i) => (
                  <div
                    key={i}
                    className="text-2xs px-2 py-1.5 rounded bg-bear/5 border border-bear/20"
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-semibold text-bear">
                        {blocked.pair.replace('_', '/')}
                      </span>
                      <span className="text-subtle">
                        {blocked.blocked_directions === 'both'
                          ? 'BOTH DIRECTIONS'
                          : blocked.blocked_directions.toUpperCase() + ' ONLY'}
                      </span>
                    </div>
                    <div className="text-subtle leading-relaxed">{blocked.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {correlationStatus.available_pairs.length > 0 && (
            <div>
              <div className="text-2xs text-gray-400 mb-1">✓ Available Pairs:</div>
              <div className="flex flex-wrap gap-1.5">
                {correlationStatus.available_pairs.map((pair, i) => (
                  <span
                    key={i}
                    className="text-2xs px-2 py-1 rounded bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30"
                  >
                    {pair.replace('_', '/')}
                  </span>
                ))}
              </div>
            </div>
          )}
          
          {correlationStatus.open_positions.length === 0 && (
            <div className="text-2xs text-subtle text-center py-2">
              No open positions — all pairs available
            </div>
          )}
        </div>
      )}

      {error && !data ? (
        <div className="p-8 text-center text-muted text-xs">
          Signals load when backend is running
        </div>
      ) : (filtered.length === 0 && (!showExternal || externalSignals.length === 0)) ? (
        <div className="p-8 text-center text-muted text-xs">
          No signals yet — start auto-generation, fetch external signals, or wait for TradingView webhooks
        </div>
      ) : (
        <div className="divide-y divide-panel-border/50 max-h-[600px] overflow-auto">
          {/* Internal Signals */}
          {filtered.map((sig) => (
            <div
              key={`internal-${sig.id}`}
              className="px-4 py-3 hover:bg-panel-hover/30 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="badge-neutral text-2xs">INTERNAL</span>
                  <span
                    className={`badge ${
                      sig.action.toLowerCase() === 'buy' ? 'badge-bull' : 'badge-bear'
                    }`}
                  >
                    {sig.action.toUpperCase()}
                  </span>
                  <span className="text-sm font-semibold text-gray-100">
                    {sig.instrument.replace('_', '/')}
                  </span>
                  <span className="text-2xs text-subtle">
                    @ {sig.price}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-2xs font-medium px-2 py-0.5 rounded ${
                      sig.approved
                        ? 'bg-bull/10 text-bull border border-bull/20'
                        : 'bg-bear/10 text-bear border border-bear/20'
                    }`}
                  >
                    {sig.approved ? 'APPROVED' : 'REJECTED'}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-4 text-2xs text-subtle">
                <span>RSI: {sig.rsi?.toFixed(1) ?? '—'}</span>
                {sig.atr_value && <span>ATR: {sig.atr_value.toFixed(5)}</span>}
                <span>{new Date(sig.timestamp).toLocaleString()}</span>
              </div>

              {!sig.approved && sig.reject_reason && (
                <div className="mt-1 text-2xs text-bear/80">
                  {sig.reject_reason}
                </div>
              )}
            </div>
          ))}

          {/* External Signals */}
          {showExternal && externalSignals.map((sig, index) => (
            <div
              key={`external-${index}`}
              className="px-4 py-3 hover:bg-panel-hover/30 transition-colors border-l-2 border-accent-purple/30"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="badge-accent text-2xs">{sig.provider.toUpperCase()}</span>
                  <span
                    className={`badge ${
                      sig.action.toLowerCase() === 'buy' ? 'badge-bull' : 'badge-bear'
                    }`}
                  >
                    {sig.action.toUpperCase()}
                  </span>
                  <span className="text-sm font-semibold text-gray-100">
                    {sig.instrument.replace('_', '/')}
                  </span>
                  <span className="text-2xs text-subtle">
                    @ {sig.price?.toFixed(5) ?? '—'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xs font-medium px-2 py-0.5 rounded bg-accent-purple/10 text-accent-purple border border-accent-purple/20">
                    {(sig.confidence * 100).toFixed(0)}% CONF
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-4 text-2xs text-subtle">
                <span>Timeframe: {sig.timeframe}</span>
                {sig.stop_loss && <span>SL: {sig.stop_loss.toFixed(5)}</span>}
                {sig.take_profit && <span>TP: {sig.take_profit.toFixed(5)}</span>}
                <span>{new Date(sig.timestamp).toLocaleString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Toast Notifications */}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {notifications.map((notification) => (
          <div
            key={notification.id}
            className={`
              animate-in slide-in-from-right-full fade-in duration-200
              px-4 py-3 rounded border backdrop-blur-sm
              flex items-center gap-3 max-w-sm shadow-lg
              ${
                notification.type === 'success'
                  ? 'bg-bull/10 border-bull/30 text-bull'
                  : notification.type === 'error'
                  ? 'bg-bear/10 border-bear/30 text-bear'
                  : 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan'
              }
            `}
          >
            <span className="text-lg font-semibold">
              {notification.type === 'success'
                ? '✓'
                : notification.type === 'error'
                ? '✕'
                : 'ℹ'}
            </span>
            <span className="text-sm font-medium">{notification.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
