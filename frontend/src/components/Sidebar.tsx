'use client';

import type { ActiveView } from '../app/page';

const NAV_ITEMS: { key: ActiveView; label: string; icon: string }[] = [
  { key: 'overview', label: 'OVERVIEW', icon: '◫' },
  { key: 'trades', label: 'TRADES', icon: '⇅' },
  { key: 'performance', label: 'PERF', icon: '📈' },
  { key: 'signals', label: 'SIGNALS', icon: '◉' },
  { key: 'backtest', label: 'BACKTEST', icon: '⏱' },
  { key: 'news', label: 'NEWS', icon: '⚡' },
  { key: 'logs', label: 'LOGS', icon: '▤' },
  { key: 'settings', label: 'CONFIG', icon: '⚙' },
];

interface SidebarProps {
  activeView: ActiveView;
  onNavigate: (view: ActiveView) => void;
  isOpen: boolean;
  onToggle: () => void;
}

export default function Sidebar({ activeView, onNavigate, isOpen, onToggle }: SidebarProps) {
  return (
    <>
      {/* Mobile Menu Button */}
      <button
        onClick={onToggle}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-panel-surface border border-panel-border rounded-md"
      >
        <span className="text-gray-300">☰</span>
      </button>

      {/* Sidebar */}
      <aside className={`
        fixed lg:static inset-y-0 left-0 z-50
        w-64 lg:w-48
        bg-panel-surface border-r border-panel-border
        flex flex-col shrink-0
        transform transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Close button for mobile */}
        <button
          onClick={onToggle}
          className="lg:hidden absolute top-4 right-4 p-1 text-gray-400 hover:text-gray-200"
        >
          ✕
        </button>
      {/* Brand */}
      <div className="p-4 border-b border-panel-border">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded bg-accent-cyan/15 border border-accent-cyan/30 flex items-center justify-center">
            <span className="text-accent-cyan text-xs font-bold">M</span>
          </div>
          <div>
            <div className="text-xs font-display font-bold text-gray-100 tracking-wide">
              Montgomery
            </div>
            <div className="text-2xs text-muted">v2.0 · LIVE</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-0.5">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            onClick={() => onNavigate(item.key)}
            className={`nav-item w-full text-left ${
              activeView === item.key ? 'active' : ''
            }`}
          >
            <span className="text-sm w-5 text-center opacity-70">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      {/* System info */}
      <div className="p-3 border-t border-panel-border">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-1.5 h-1.5 rounded-full bg-bull animate-pulse-slow" />
          <span className="text-2xs text-muted">BOT ONLINE</span>
        </div>
        <div className="text-2xs text-subtle leading-relaxed">
          OANDA Practice<br />
          TF: M15 → H1<br />
          Pairs: 7 majors
        </div>
      </div>
    </aside>
    </>
  );
}
