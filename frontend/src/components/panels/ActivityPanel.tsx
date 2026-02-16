'use client';

import { useState } from 'react';
import { useActivity } from '../../lib/hooks';

const LEVEL_STYLES = {
  info: { dot: 'bg-accent-blue', text: 'text-gray-300' },
  warn: { dot: 'bg-warn', text: 'text-warn' },
  error: { dot: 'bg-bear', text: 'text-bear' },
  trade: { dot: 'bg-accent-cyan', text: 'text-accent-cyan' },
};

export default function ActivityPanel({ compact = false }: { compact?: boolean }) {
  const { logs: allLogs } = useActivity();
  const [expanded, setExpanded] = useState(false);
  
  const isCompact = compact && !expanded;
  const logs = isCompact ? allLogs.slice(0, 6) : allLogs;

  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-panel-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            Activity Log
          </span>
        </div>
        {compact && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-2xs text-accent-cyan hover:underline transition-colors"
          >
            {expanded ? '← Collapse' : 'View All →'}
          </button>
        )}
      </div>

      <div className={isCompact ? 'max-h-56 overflow-y-auto' : 'max-h-[70vh] overflow-y-auto'}>
        {logs.length === 0 ? (
          <div className="p-4 text-center text-muted text-xs">No activity yet</div>
        ) : (
          logs.map((log) => {
            const styles = LEVEL_STYLES[log.level] || LEVEL_STYLES.info;
            const time = new Date(log.timestamp);

            return (
              <div
                key={log.id}
                className="data-row items-start"
              >
                <div className="flex items-start gap-2.5 flex-1 min-w-0">
                  <div
                    className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${styles.dot}`}
                  />
                  <div className="min-w-0">
                    <div className={`text-xs ${styles.text} break-words`}>
                      {log.message}
                    </div>
                    {log.details && (
                      <div className="text-2xs text-subtle mt-0.5 font-mono">
                        {log.details}
                      </div>
                    )}
                  </div>
                </div>
                <div className="text-2xs text-subtle shrink-0 ml-3 tabular-nums">
                  {time.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false,
                  })}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
