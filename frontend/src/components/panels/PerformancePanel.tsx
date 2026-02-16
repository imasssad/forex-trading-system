'use client';

import { usePerformance } from '../../lib/hooks';

export default function PerformancePanel() {
  const { performance: p, isLive } = usePerformance();

  // Default performance values
  const performance = p || {
    total_trades: 0,
    win_rate: 0,
    profit_factor: 0,
    winning_trades: 0,
    losing_trades: 0,
    net_profit: 0,
    total_profit: 0,
    total_loss: 0,
    max_drawdown: 0,
    avg_win: 0,
    avg_loss: 0,
    best_trade: 0,
    worst_trade: 0,
    consecutive_wins: 0,
    consecutive_losses: 0,
    equity_curve: []
  };

  // derive max-drawdown percent from equity_curve (if available) so UI shows context
  function calcDrawdown(curve: { date: string; equity: number }[] | undefined) {
    if (!curve || curve.length === 0) return 0;
    let peak = curve[0].equity;
    let maxDd = 0;
    let peakIdx = 0;
    let peakAtMaxDd = peak;
    for (let i = 0; i < curve.length; i++) {
      const v = curve[i].equity;
      if (v > peak) { peak = v; peakIdx = i; }
      const dd = peak - v;
      if (dd > maxDd) {
        maxDd = dd;
        peakAtMaxDd = curve[peakIdx].equity;
      }
    }
    return peakAtMaxDd > 0 ? (maxDd / peakAtMaxDd) * 100 : 0;
  }

  const computedMaxDrawdownPct = calcDrawdown(performance.equity_curve);

  const statGroups = [
    {
      title: 'WIN / LOSS',
      items: [
        { label: 'Total Trades', value: isLive ? performance.total_trades : '--', color: 'text-gray-200' },
        { label: 'Win Rate', value: isLive ? `${performance.win_rate}%` : '--', color: isLive && performance.win_rate > 55 ? 'text-bull' : 'text-warn' },
        { label: 'Profit Factor', value: isLive ? performance.profit_factor.toFixed(2) : '--', color: isLive && performance.profit_factor > 1.5 ? 'text-bull' : 'text-warn' },
        { label: 'Wins / Losses', value: isLive ? `${performance.winning_trades} / ${performance.losing_trades}` : '--', color: 'text-gray-200' },
      ],
    },
    {
      title: 'PROFIT',
      items: [
        { label: 'Net Profit', value: isLive ? `$${performance.net_profit.toFixed(2)}` : '--', color: isLive && performance.net_profit >= 0 ? 'text-bull' : 'text-bear' },
        { label: 'Total Wins', value: isLive ? `+$${performance.total_profit.toFixed(2)}` : '--', color: 'text-bull' },
        { label: 'Total Losses', value: isLive ? `-$${Math.abs(performance.total_loss).toFixed(2)}` : '--', color: 'text-bear' },
        { label: 'Max Drawdown', value: isLive ? `-$${Math.abs(performance.max_drawdown).toFixed(2)} (${computedMaxDrawdownPct.toFixed(1)}%)` : '--', color: 'text-bear' },
      ],
    },
    {
      title: 'AVERAGES',
      items: [
        { label: 'Avg Win', value: isLive ? `+$${performance.avg_win.toFixed(2)}` : '--', color: 'text-bull' },
        { label: 'Avg Loss', value: isLive ? `-$${Math.abs(performance.avg_loss).toFixed(2)}` : '--', color: 'text-bear' },
        { label: 'Best Trade', value: isLive ? `+$${performance.best_trade.toFixed(2)}` : '--', color: 'text-bull' },
        { label: 'Worst Trade', value: isLive ? `-$${Math.abs(performance.worst_trade).toFixed(2)}` : '--', color: 'text-bear' },
      ],
    },
    {
      title: 'STREAKS',
      items: [
        { label: 'Consec. Wins', value: isLive ? performance.consecutive_wins : '--', color: 'text-bull' },
        { label: 'Consec. Losses', value: isLive ? performance.consecutive_losses : '--', color: 'text-bear' },
        { label: 'Expectancy', value: isLive ? `$${((performance.win_rate / 100) * performance.avg_win - ((100 - performance.win_rate) / 100) * Math.abs(performance.avg_loss)).toFixed(2)}` : '--', color: 'text-accent-cyan' },
        { label: 'Risk/Reward', value: isLive && performance.avg_loss !== 0 ? `1 : ${(performance.avg_win / Math.abs(performance.avg_loss)).toFixed(1)}` : '—', color: 'text-gray-200' },
      ],
    },
  ];

  return (
    <div className="space-y-3">
      {/* Equity Curve */}
      <div className="card">
        <div className="px-4 py-3 border-b border-panel-border">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Equity Curve
          </span>
        </div>
        <div className="p-4">
          <EquityChart data={performance.equity_curve || []} />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {statGroups.map((group) => (
          <div key={group.title} className="card">
            <div className="px-4 py-2 border-b border-panel-border">
              <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
                {group.title}
              </span>
            </div>
            <div className="p-3 space-y-2.5">
              {group.items.map((item) => (
                <div key={item.label} className="flex items-center justify-between">
                  <span className="text-2xs text-muted">{item.label}</span>
                  <span className={`text-xs font-semibold ${item.color}`}>
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Win rate visual */}
      <div className="card p-4">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-2xs text-subtle uppercase tracking-widest font-semibold">Win Distribution</span>
        </div>
        <div className="flex h-6 rounded overflow-hidden">
          <div
            className="bg-bull/70 flex items-center justify-center"
            style={{ width: `${performance.win_rate}%` }}
          >
            <span className="text-2xs font-bold text-white/90">
              {performance.win_rate}% W
            </span>
          </div>
          <div
            className="bg-bear/70 flex items-center justify-center"
            style={{ width: `${100 - performance.win_rate}%` }}
          >
            <span className="text-2xs font-bold text-white/90">
              {(100 - performance.win_rate).toFixed(1)}% L
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Simple SVG equity chart - no external dependencies needed */
function EquityChart({ data }: { data: { date: string; equity: number }[] }) {
  if (!data.length) return (
    <div className="h-48 flex items-center justify-center text-subtle text-xs">
      No equity data yet
    </div>
  );

  const W = 800;
  const H = 200;
  const PAD = { top: 20, right: 40, bottom: 30, left: 60 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;

  const values = data.map((d) => d.equity);
  const minVal = Math.min(...values) * 0.999;
  const maxVal = Math.max(...values) * 1.001;
  const range = maxVal - minVal || 1;

  const points = data.map((d, i) => ({
    x: PAD.left + (i / (data.length - 1 || 1)) * chartW,
    y: PAD.top + chartH - ((d.equity - minVal) / range) * chartH,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${PAD.top + chartH} L ${points[0].x} ${PAD.top + chartH} Z`;

  const startVal = values[0];
  const endVal = values[values.length - 1];
  const isPositive = endVal >= startVal;
  const strokeColor = isPositive ? '#00D4AA' : '#FF4757';
  const fillColor = isPositive ? 'url(#gradGreen)' : 'url(#gradRed)';

  // Y-axis labels
  const yLabels = [minVal, minVal + range / 2, maxVal].map((v) => ({
    value: `$${v.toFixed(0)}`,
    y: PAD.top + chartH - ((v - minVal) / range) * chartH,
  }));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-48">
      <defs>
        <linearGradient id="gradGreen" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#00D4AA" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#00D4AA" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="gradRed" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FF4757" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#FF4757" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yLabels.map((l, i) => (
        <g key={i}>
          <line
            x1={PAD.left}
            y1={l.y}
            x2={W - PAD.right}
            y2={l.y}
            stroke="#1E2530"
            strokeDasharray="4,4"
          />
          <text x={PAD.left - 8} y={l.y + 3} textAnchor="end" className="fill-muted text-2xs">
            {l.value}
          </text>
        </g>
      ))}

      {/* Area fill */}
      <path d={areaPath} fill={fillColor} />

      {/* Line */}
      <path d={linePath} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" />

      {/* Current value dot */}
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r="4"
        fill={strokeColor}
        className="animate-pulse-slow"
      />

      {/* X-axis dates */}
      {[0, Math.floor(data.length / 2), data.length - 1].map((idx) => (
        <text
          key={idx}
          x={points[idx]?.x || 0}
          y={H - 5}
          textAnchor="middle"
          className="fill-muted text-2xs"
        >
          {data[idx] ? new Date(data[idx].date).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          }) : ''}
        </text>
      ))}
    </svg>
  );
}
