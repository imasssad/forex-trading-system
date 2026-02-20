'use client';

interface SidebarProps {
  activeView: string;
  onNavigate: (view: any) => void;
  isOpen: boolean;
  onToggle: () => void;
}

export default function Sidebar({ activeView, onNavigate, isOpen, onToggle }: SidebarProps) {
  const views = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'trades', label: 'Trades', icon: '💹' },
    { id: 'performance', label: 'Performance', icon: '📈' },
    { id: 'signals', label: 'Signals', icon: '🎯' },
    { id: 'backtest', label: 'Backtest', icon: '🔬' },
    { id: 'news', label: 'News', icon: '📰' },
    { id: 'logs', label: 'Logs', icon: '📝' },
    { id: 'settings', label: 'Settings', icon: '⚙️' },
  ];

  return (
    <aside 
      className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-panel border-r border-panel-border transform transition-transform duration-200 ease-in-out ${
        isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
      }`}
    >
      <div className="p-4 border-b border-panel-border">
        <h1 className="text-xl font-bold text-gray-100">ATS Trading</h1>
      </div>
      <nav className="p-2">
        {views.map((view) => (
          <button
            key={view.id}
            onClick={() => onNavigate(view.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
              activeView === view.id
                ? 'bg-primary/20 text-primary'
                : 'text-gray-400 hover:bg-panel-hover hover:text-gray-200'
            }`}
          >
            <span className="text-xl">{view.icon}</span>
            <span className="font-medium">{view.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
