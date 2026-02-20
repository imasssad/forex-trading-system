'use client';

import { useState, useEffect } from 'react';

interface ActivityPanelProps {
  compact?: boolean;
}

interface ActivityLog {
  id: number;
  timestamp: string;
  level: string;
  action: string;
  details: string;
}

export default function ActivityPanel({ compact = false }: ActivityPanelProps) {
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchActivity = async () => {
      try {
        const limit = compact ? 10 : 50;
        const response = await fetch(`/api/activity?limit=${limit}`);
        if (response.ok) {
          const data = await response.json();
          setLogs(data.logs || []);
        }
      } catch (error) {
        console.error('Error fetching activity:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchActivity();
    const interval = setInterval(fetchActivity, 10000); // Refresh every 10 seconds
    return () => clearInterval(interval);
  }, [compact]);

  const formatTime = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    } catch {
      return timestamp;
    }
  };

  const getLevelColor = (level: string) => {
    switch (level?.toLowerCase()) {
      case 'error': return 'text-bear';
      case 'warning': return 'text-yellow-500';
      case 'success': return 'text-bull';
      default: return 'text-gray-400';
    }
  };

  if (loading) {
    return (
      <div className="card">
        <div className="px-4 py-3 border-b border-panel-border">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Activity Log
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
      <div className="px-4 py-3 border-b border-panel-border">
        <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
          Activity Log
        </span>
      </div>
      {logs.length === 0 ? (
        <div className="p-8 text-center text-muted text-xs">
          No recent activity
        </div>
      ) : (
        <div className={`divide-y divide-panel-border/50 ${compact ? 'max-h-64' : 'max-h-96'} overflow-y-auto`}>
          {logs.map((log) => (
            <div key={log.id} className="px-4 py-2 hover:bg-panel-hover/30 transition-colors">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-2xs font-semibold ${getLevelColor(log.level)}`}>
                      {log.level?.toUpperCase()}
                    </span>
                    <span className="text-2xs text-gray-400">{log.action}</span>
                  </div>
                  <div className="text-xs text-gray-300 truncate">{log.details}</div>
                </div>
                <div className="text-2xs text-subtle whitespace-nowrap">
                  {formatTime(log.timestamp)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
