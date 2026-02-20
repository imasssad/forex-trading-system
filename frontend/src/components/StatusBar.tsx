'use client';

import { useState, useEffect } from 'react';

interface StatusBarProps {
  onMenuClick?: () => void;
}

interface SystemStatus {
  paper_trading: boolean;
  bot_running: boolean;
  uptime_hours?: number;
}

export default function StatusBar({ onMenuClick }: StatusBarProps) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('/api/status');
        if (response.ok) {
          const data = await response.json();
          setStatus(data);
        }
      } catch (error) {
        console.error('Error fetching status:', error);
      }
    };

    fetchStatus();
    const statusInterval = setInterval(fetchStatus, 5000); // Refresh every 5 seconds
    const timeInterval = setInterval(() => setTime(new Date()), 1000);
    
    return () => {
      clearInterval(statusInterval);
      clearInterval(timeInterval);
    };
  }, []);

  const isLive = status?.bot_running && !status?.paper_trading;

  return (
    <div className="bg-panel border-b border-panel-border px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-4">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="lg:hidden text-gray-400 hover:text-gray-200"
          >
            ☰
          </button>
        )}
        <div className="flex items-center gap-2">
          <span className="text-xs text-subtle">Status:</span>
          {status ? (
            <span className={`${isLive ? 'badge-bull' : 'badge-neutral'} text-xs`}>
              ● {isLive ? 'Live' : 'Paper Trading'}
            </span>
          ) : (
            <span className="badge-neutral text-xs">● Loading...</span>
          )}
        </div>
      </div>
      <div className="text-xs text-subtle">
        {time.toLocaleString()}
      </div>
    </div>
  );
}
