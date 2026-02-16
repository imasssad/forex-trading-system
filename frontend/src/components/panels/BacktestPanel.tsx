'use client';

import { useState } from 'react';
import { useBacktestRuns, compareBacktest } from '../../lib/hooks';

const PAIRS = ['EUR_USD', 'USD_JPY', 'GBP_USD', 'AUD_USD', 'NZD_USD', 'USD_CHF', 'USD_CAD'];

export default function BacktestPanel() {
  const { runs, triggerBacktest } = useBacktestRuns();
  const [selectedPair, setSelectedPair] = useState('EUR_USD');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2025-12-31');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Compare mode: run backtest with server config vs. overrides
  const [compareOverrides, setCompareOverrides] = useState({ atr_multiplier: 3.0, risk_per_trade: 2.0, risk_reward_ratio: 2.5 });
  const [compareResult, setCompareResult] = useState<any>(null);
  const [comparing, setComparing] = useState(false);

  // Compute drawdown info from an equity curve so the UI shows context (dollar + percent)
  function calcDrawdown(curve: { date: string; equity: number }[] | undefined) {
    if (!curve || curve.length === 0) return null;
    let peak = curve[0].equity;
    let peakIdx = 0;
    let maxDd = 0;
    let troughIdx = 0;
    let peakAtMaxDd = peak;

    for (let i = 0; i < curve.length; i++) {
      const v = curve[i].equity;
      if (v > peak) { peak = v; peakIdx = i; }
      const dd = peak - v;
      if (dd > maxDd) {
        maxDd = dd;
        troughIdx = i;
        peakAtMaxDd = curve[peakIdx].equity;
      }
    }

    const pct = peakAtMaxDd > 0 ? (maxDd / peakAtMaxDd) * 100 : 0;
    return { maxDrawdown: maxDd, peakIndex: peakIdx, troughIndex: troughIdx, peakValue: peakAtMaxDd, pct };
  }

  const drawdownInfo = result?.equity_curve ? calcDrawdown(result.equity_curve) : null;
  const computedMaxDrawdown = drawdownInfo ? drawdownInfo.maxDrawdown : Math.abs(result?.max_drawdown ?? 0);
  const computedMaxDrawdownPct = drawdownInfo ? drawdownInfo.pct : 0;

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    setCompareResult(null);
    try {
      const res = await triggerBacktest(selectedPair, startDate, endDate);
      setResult(res);
    } catch (e: any) {
      setError(e.message || 'Backtest failed');
    } finally {
      setRunning(false);
    }
  };

  const handleCompare = async () => {
    setComparing(true);
    setError(null);
    setCompareResult(null);
    try {
      const res = await compareBacktest(
        selectedPair,
        startDate,
        endDate,
        {
          atr_multiplier: Number(compareOverrides.atr_multiplier),
          risk_per_trade: Number(compareOverrides.risk_per_trade),
          risk_reward_ratio: Number(compareOverrides.risk_reward_ratio),
        }
      );
      setCompareResult(res);
    } catch (e: any) {
      setError(e.message || 'Compare failed');
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* Controls */}
      <div className="card p-4">
        <h2 className="text-sm font-display font-bold text-gray-100 uppercase tracking-wider mb-3">
          Run Backtest
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-2xs text-subtle block mb-1">Pair</label>
            <select
              value={selectedPair}
              onChange={(e) => setSelectedPair(e.target.value)}
              className="input-field w-32"
            >
              {PAIRS.map((p) => (
                <option key={p} value={p}>
                  {p.replace('_', '/')}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-2xs text-subtle block mb-1">Start</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="input-field w-36"
            />
          </div>
          <div>
            <label className="text-2xs text-subtle block mb-1">End</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="input-field w-36"
            />
          </div>
          <button
            onClick={handleRun}
            disabled={running}
            className="btn-primary"
          >
            {running ? 'RUNNING...' : 'RUN BACKTEST'}
          </button>

          {/* Quick compare controls */}
          <div className="w-full border-t border-panel-border mt-3 pt-3">
            <div className="flex items-center gap-3">
              <div className="text-2xs text-subtle mr-2">Compare overrides</div>
              <div className="flex items-center gap-2">
                <label className="text-2xs text-subtle">ATR ×</label>
                <input
                  className="input-field w-20"
                  type="number"
                  step="0.1"
                  value={compareOverrides.atr_multiplier}
                  onChange={(e) => setCompareOverrides((s) => ({ ...s, atr_multiplier: Number(e.target.value) }))}
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-2xs text-subtle">Risk %</label>
                <input
                  className="input-field w-20"
                  type="number"
                  step="0.1"
                  value={compareOverrides.risk_per_trade}
                  onChange={(e) => setCompareOverrides((s) => ({ ...s, risk_per_trade: Number(e.target.value) }))}
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-2xs text-subtle">R:R</label>
                <input
                  className="input-field w-20"
                  type="number"
                  step="0.1"
                  value={compareOverrides.risk_reward_ratio}
                  onChange={(e) => setCompareOverrides((s) => ({ ...s, risk_reward_ratio: Number(e.target.value) }))}
                />
              </div>
              <button onClick={handleCompare} disabled={comparing} className="btn-secondary">
                {comparing ? 'COMPARE...' : 'COMPARE'}
              </button>
            </div>
          </div>
        </div>
        {error && <p className="text-2xs text-red-400 mt-2">{error}</p>}
      </div>

      {/* Results */}
      {result && (
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border flex items-center justify-between">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Results — {selectedPair.replace('_', '/')}
            </span>
            <span className={`text-sm font-bold ${
              (result.net_profit ?? 0) >= 0 ? 'text-bull' : 'text-bear'
            }`}>
              {(result.net_profit ?? 0) >= 0 ? '+' : ''}${(result.net_profit ?? 0).toFixed(2)}
            </span>
          </div>
          <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Total Trades" value={result.total_trades ?? '—'} />
            <Stat label="Win Rate" value={`${(result.win_rate ?? 0).toFixed(1)}%`} />
            <Stat label="Profit Factor" value={(result.profit_factor ?? 0).toFixed(2)} />
            <Stat label="Max Drawdown" value={`-$${computedMaxDrawdown.toFixed(2)} (${computedMaxDrawdownPct.toFixed(1)}%)`} />
            <Stat label="Wins" value={result.winning_trades ?? '—'} />
            <Stat label="Losses" value={result.losing_trades ?? '—'} />
            <Stat label="Avg Win" value={`$${(result.avg_win ?? 0).toFixed(2)}`} />
            <Stat label="Avg Loss" value={`$${(result.avg_loss ?? 0).toFixed(2)}`} />
            <Stat label="Sharpe Ratio" value={(result.sharpe_ratio ?? 0).toFixed(2)} />
            <Stat label="Best Trade" value={`$${(result.best_trade ?? 0).toFixed(2)}`} />
            <Stat label="Worst Trade" value={`$${(result.worst_trade ?? 0).toFixed(2)}`} />
            <Stat label="Expectancy" value={`$${(result.expectancy ?? 0).toFixed(2)}`} />
          </div>

          {/* Equity curve */}
          {result.equity_curve && result.equity_curve.length > 0 && (
            <div className="px-4 pb-4">
              <div className="text-2xs text-subtle mb-2">Equity Curve</div>
              <EquityCurve data={result.equity_curve} drawdownInfo={drawdownInfo} />
            </div>
          )}

          {/* Trade list */}
          {result.trades && result.trades.length > 0 && (
            <div className="border-t border-panel-border">
              <div className="px-4 py-2 text-2xs text-subtle">
                Last 20 trades
              </div>
              <div className="max-h-64 overflow-auto">
                <table className="w-full text-2xs">
                  <thead className="text-subtle sticky top-0 bg-panel-surface">
                    <tr>
                      <th className="text-left px-4 py-1">Pair</th>
                      <th className="text-left px-2 py-1">Dir</th>
                      <th className="text-right px-2 py-1">Entry</th>
                      <th className="text-right px-2 py-1">Exit</th>
                      <th className="text-right px-2 py-1">P/L</th>
                      <th className="text-left px-2 py-1">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-panel-border/30">
                    {result.trades.slice(-20).reverse().map((t: any, i: number) => (
                      <tr key={i} className="hover:bg-panel-hover/20">
                        <td className="px-4 py-1 text-gray-300">{(t.instrument || t.pair || '').replace('_', '/')}</td>
                        <td className={`px-2 py-1 ${t.direction === 'long' ? 'text-bull' : 'text-bear'}`}>
                          {t.direction === 'long' ? 'LONG' : 'SHORT'}
                        </td>
                        <td className="px-2 py-1 text-right text-gray-400">{t.entry_price}</td>
                        <td className="px-2 py-1 text-right text-gray-400">{t.exit_price}</td>
                        <td className={`px-2 py-1 text-right font-medium ${
                          (t.profit_loss ?? t.pnl ?? 0) >= 0 ? 'text-bull' : 'text-bear'
                        }`}>
                          {(t.profit_loss ?? t.pnl ?? 0) >= 0 ? '+' : ''}
                          ${(t.profit_loss ?? t.pnl ?? 0).toFixed(2)}
                        </td>
                        <td className="px-2 py-1 text-subtle">{t.close_reason || t.exit_reason || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Compare results (server config vs overrides) */}
      {compareResult && (
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border flex items-center justify-between">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">Compare Backtest</span>
            <span className="text-2xs text-subtle">Overrides: ATR×{compareOverrides.atr_multiplier} · Risk% {compareOverrides.risk_per_trade} · R:R {compareOverrides.risk_reward_ratio}</span>
          </div>
          <div className="p-4 grid grid-cols-2 gap-4">
            {['baseline', 'modified'].map((k) => {
              const r = compareResult[k as 'baseline' | 'modified'];
              return (
                <div key={k} className="border rounded p-3 bg-panel-surface">
                  <div className="text-2xs text-subtle mb-2 font-semibold">{k === 'baseline' ? 'Server config' : 'Overrides'}</div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-2xs text-muted">Total Trades</div>
                    <div className="text-sm font-semibold">{r.total_trades}</div>
                  </div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-2xs text-muted">Net Profit</div>
                    <div className={`text-sm font-semibold ${r.net_profit >= 0 ? 'text-bull' : 'text-bear'}`}>{r.net_profit >= 0 ? '+' : ''}${r.net_profit.toFixed(2)}</div>
                  </div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-2xs text-muted">Max Drawdown</div>
                    <div className="text-sm font-semibold text-bear">-${Math.abs(r.max_drawdown).toFixed(2)}</div>
                  </div>
                  <div className="text-2xs text-subtle mt-2">Sample trades (first 12)</div>
                  <div className="mt-2 max-h-44 overflow-auto">
                    <table className="w-full text-2xs">
                      <thead className="text-subtle sticky top-0 bg-panel-surface">
                        <tr>
                          <th className="text-left px-2 py-1">Time</th>
                          <th className="text-right px-2 py-1">Entry</th>
                          <th className="text-right px-2 py-1">Stop</th>
                          <th className="text-right px-2 py-1">P/L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-panel-border/30">
                        {((r.trades || []).slice(0, 12) || []).map((t: any, i: number) => (
                          <tr key={i}>
                            <td className="px-2 py-1 text-gray-300">{new Date(t.open_time || t.entry_time).toLocaleString()}</td>
                            <td className="px-2 py-1 text-right text-gray-400">{t.entry_price?.toFixed(5)}</td>
                            <td className="px-2 py-1 text-right font-mono text-gray-200">{t.stop_loss?.toFixed(5)}</td>
                            <td className={`px-2 py-1 text-right ${ (t.profit_loss ?? t.pnl ?? 0) >= 0 ? 'text-bull' : 'text-bear' }`}>{(t.profit_loss ?? t.pnl ?? 0) >= 0 ? '+' : ''}${(t.profit_loss ?? t.pnl ?? 0).toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="px-4 py-3 border-t border-panel-border text-2xs text-subtle">
            Diff — Trades: {compareResult.diff.total_trades_diff >= 0 ? '+' : ''}{compareResult.diff.total_trades_diff} · Net: {compareResult.diff.net_profit_diff >= 0 ? '+' : ''}${compareResult.diff.net_profit_diff} · DD: {compareResult.diff.max_drawdown_diff >= 0 ? '+' : ''}${compareResult.diff.max_drawdown_diff}
          </div>
        </div>
      )}

      {/* Previous Runs */}
      {runs.length > 0 && (
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Previous Runs
            </span>
          </div>
          <div className="divide-y divide-panel-border/50">
            {runs.map((run: any, i: number) => (
              <div key={i} className="px-4 py-2 flex items-center justify-between text-2xs">
                <div>
                  <span className="text-gray-300 font-medium">{(run.pair || '').replace('_', '/')}</span>
                  <span className="text-subtle ml-2">
                    {run.start_date} → {run.end_date}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-subtle">{run.total_trades} trades</span>
                  <span className="text-subtle">{(run.win_rate ?? 0).toFixed(1)}% WR</span>
                  <span className={`font-medium ${
                    (run.net_profit ?? 0) >= 0 ? 'text-bull' : 'text-bear'
                  }`}>
                    {(run.net_profit ?? 0) >= 0 ? '+' : ''}${(run.net_profit ?? 0).toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-2xs text-subtle">{label}</div>
      <div className="text-sm font-semibold text-gray-200">{value}</div>
    </div>
  );
}

function EquityCurve({ data, drawdownInfo }: { data: { date: string; equity: number }[]; drawdownInfo?: { maxDrawdown: number; peakIndex: number; troughIndex: number; peakValue: number; pct: number } | null }) {
  if (data.length < 2) return null;

  const W = 600;
  const H = 140;
  const PAD = { top: 12, right: 40, bottom: 28, left: 56 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;

  const values = data.map((d) => d.equity);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = maxVal - minVal || 1;

  const points = data.map((d, i) => ({
    x: PAD.left + (i / (data.length - 1 || 1)) * chartW,
    y: PAD.top + chartH - ((d.equity - minVal) / range) * chartH,
    date: d.date,
    equity: d.equity,
    idx: i,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${PAD.top + chartH} L ${points[0].x} ${PAD.top + chartH} Z`;

  const startVal = values[0];
  const endVal = values[values.length - 1];
  const isPositive = endVal >= startVal;
  const strokeColor = isPositive ? 'var(--color-bull, #22c55e)' : 'var(--color-bear, #ef4444)';
  const fillId = isPositive ? 'gradGreenBacktest' : 'gradRedBacktest';

  // Y-axis labels (min, mid, max)
  const yLabels = [minVal, minVal + range / 2, maxVal].map((v) => ({
    label: `$${v.toFixed(0)}`,
    y: PAD.top + chartH - ((v - minVal) / range) * chartH,
  }));

  const xTicks = [0, Math.floor(data.length / 2), data.length - 1];

  const ddTroughPoint = drawdownInfo ? points[drawdownInfo.troughIndex] : null;
  const ddLabel = drawdownInfo ? `Max DD -$${drawdownInfo.maxDrawdown.toFixed(0)} (${drawdownInfo.pct.toFixed(1)}%) on ${new Date(points[drawdownInfo.troughIndex].date).toLocaleDateString()}` : null;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-32" preserveAspectRatio="none">
      <defs>
        <linearGradient id="gradGreenBacktest" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="gradRedBacktest" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Y grid + labels */}
      {yLabels.map((y, i) => (
        <g key={i}>
          <line x1={PAD.left} y1={y.y} x2={W - PAD.right} y2={y.y} stroke="#1E2530" strokeDasharray="4,4" />
          <text x={PAD.left - 8} y={y.y + 4} textAnchor="end" className="fill-muted text-2xs">{y.label}</text>
        </g>
      ))}

      {/* Area fill + line */}
      <path d={areaPath} fill={`url(#${fillId})`} />
      <path d={linePath} fill="none" stroke={strokeColor} strokeWidth={2} strokeLinecap="round" />

      {/* Current value marker */}
      <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r={3.5} fill={strokeColor} className="animate-pulse-slow" />

      {/* Max drawdown annotation */}
      {ddTroughPoint && (
        <g>
          <line x1={ddTroughPoint.x} x2={ddTroughPoint.x} y1={PAD.top} y2={PAD.top + chartH} stroke="#FF7A7A" strokeDasharray="3,3" />
          <circle cx={ddTroughPoint.x} cy={ddTroughPoint.y} r={4} fill="#FF4757" stroke="#fff" strokeWidth={1} />
          <text x={Math.min(ddTroughPoint.x + 8, W - PAD.right - 80)} y={Math.max(ddTroughPoint.y - 8, PAD.top + 12)} className="fill-muted text-2xs" style={{ fontWeight: 600 }}>
            {ddLabel}
          </text>
        </g>
      )}

      {/* X-axis dates */}
      {xTicks.map((idx) => (
        <text key={idx} x={points[idx]?.x || 0} y={H - 6} textAnchor="middle" className="fill-muted text-2xs">
          {data[idx] ? new Date(data[idx].date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
        </text>
      ))}
    </svg>
  );
}
