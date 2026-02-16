'use client';

import { useState } from 'react';
import { useNews } from '../../lib/hooks';

const IMPACT_STYLES: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  High: { bg: 'bg-bear/15', text: 'text-bear', border: 'border-bear/20', dot: 'bg-bear' },
  Medium: { bg: 'bg-warn/15', text: 'text-warn', border: 'border-warn/20', dot: 'bg-warn' },
  Low: { bg: 'bg-subtle/30', text: 'text-subtle', border: 'border-subtle/20', dot: 'bg-subtle' },
};

const COUNTRY_FLAGS: Record<string, string> = {
  USD: '🇺🇸',
  EUR: '🇪🇺',
  GBP: '🇬🇧',
  JPY: '🇯🇵',
  AUD: '🇦🇺',
  NZD: '🇳🇿',
  CHF: '🇨🇭',
  CAD: '🇨🇦',
};

export default function NewsPanel({ compact = false }: { compact?: boolean }) {
  const { events: allEvents, lastRefresh } = useNews();
  const [expanded, setExpanded] = useState(false);

  const isCompact = compact && !expanded;
  const events = isCompact ? allEvents.filter((e) => e.impact === 'High').slice(0, 4) : allEvents;
  const now = new Date();

  // Group by date
  const grouped: Record<string, typeof events> = {};
  events.forEach((e) => {
    const dateKey = new Date(e.date).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
    if (!grouped[dateKey]) grouped[dateKey] = [];
    grouped[dateKey].push(e);
  });

  return (
    <div className="card">
      <div className="px-4 py-3 border-b border-panel-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            {isCompact ? 'Upcoming News' : 'Economic Calendar'}
          </span>
          {isCompact && (
            <span className="badge-bear">HIGH IMPACT</span>
          )}
          {!isCompact && lastRefresh && (
            <span className="text-2xs text-subtle">
              Updated {new Date(lastRefresh).toLocaleTimeString()}
            </span>
          )}
        </div>
        {compact && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-2xs text-accent-cyan hover:underline transition-colors"
          >
            {expanded ? '← Collapse' : 'Full Calendar →'}
          </button>
        )}
      </div>

      <div className={isCompact ? 'max-h-64 overflow-y-auto' : expanded ? 'max-h-[70vh] overflow-y-auto' : ''}>
        {Object.keys(grouped).length === 0 ? (
          <div className="p-4 text-center text-muted text-xs">No upcoming news events</div>
        ) : (
          Object.entries(grouped).map(([date, dayEvents]) => (
            <div key={date}>
              <div className="px-4 py-1.5 bg-panel-bg/50 border-y border-panel-border/30">
                <span className="text-2xs font-semibold text-subtle uppercase tracking-wider">
                  {date}
                </span>
              </div>
              {dayEvents.map((event, idx) => {
                const styles = IMPACT_STYLES[event.impact] || IMPACT_STYLES.Low;
                const eventDate = new Date(event.date);
                const isPast = eventDate < now;
                const isSoon =
                  !isPast && eventDate.getTime() - now.getTime() < 2 * 60 * 60 * 1000; // 2hrs

                return (
                  <div
                    key={`${event.title}-${idx}`}
                    className={`data-row ${isPast ? 'opacity-40' : ''} ${
                      isSoon ? 'bg-bear/5' : ''
                    }`}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className={`w-1.5 h-1.5 rounded-full ${styles.dot} shrink-0`} />
                      <span className="text-sm">{COUNTRY_FLAGS[event.country] || ''}</span>
                      <div className="min-w-0">
                        <div className="text-xs text-gray-200 truncate">
                          {event.title}
                        </div>
                        <div className="text-2xs text-subtle">
                          {event.country} ·{' '}
                          {eventDate.toLocaleTimeString('en-US', {
                            hour: '2-digit',
                            minute: '2-digit',
                            timeZone: 'UTC',
                          })}{' '}
                          UTC
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 shrink-0 text-2xs">
                      {event.forecast && (
                        <div className="text-right">
                          <div className="text-subtle">Fcst</div>
                          <div className="text-gray-300 font-medium">{event.forecast}</div>
                        </div>
                      )}
                      {event.previous && (
                        <div className="text-right">
                          <div className="text-subtle">Prev</div>
                          <div className="text-gray-400">{event.previous}</div>
                        </div>
                      )}
                      <span
                        className={`badge ${styles.bg} ${styles.text} border ${styles.border}`}
                      >
                        {event.impact}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
