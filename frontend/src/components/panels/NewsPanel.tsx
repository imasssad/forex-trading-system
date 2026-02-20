'use client';

import { useState, useEffect } from 'react';

interface NewsPanelProps {
  compact?: boolean;
}

interface NewsEvent {
  title: string;
  country: string;
  date: string;
  impact: string;
  forecast?: string;
  previous?: string;
}

export default function NewsPanel({ compact = false }: NewsPanelProps) {
  const [events, setEvents] = useState<NewsEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchNews = async () => {
      try {
        const response = await fetch('/api/news/today');
        if (response.ok) {
          const data = await response.json();
          setEvents(data.events || []);
        }
      } catch (error) {
        console.error('Error fetching news:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
    const interval = setInterval(fetchNews, 300000); // Refresh every 5 minutes
    return () => clearInterval(interval);
  }, []);

  const formatTime = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  const getImpactColor = (impact: string) => {
    switch (impact?.toLowerCase()) {
      case 'high': return 'text-bear';
      case 'medium': return 'text-yellow-500';
      case 'low': return 'text-gray-400';
      default: return 'text-gray-400';
    }
  };

  if (loading) {
    return (
      <div className="card">
        <div className="px-4 py-3 border-b border-panel-border">
          <span className="text-xs font-display font-semibold text-gray-200 uppercase tracking-wider">
            News Events
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
          Today's High Impact News
        </span>
      </div>
      {events.length === 0 ? (
        <div className="p-8 text-center text-muted text-xs">
          No high impact news today
        </div>
      ) : (
        <div className={`divide-y divide-panel-border/50 ${compact ? 'max-h-64' : 'max-h-96'} overflow-y-auto`}>
          {events.map((event, idx) => (
            <div key={idx} className="px-4 py-3 hover:bg-panel-hover/30 transition-colors">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-gray-100">{event.country}</span>
                    <span className={`text-2xs font-semibold ${getImpactColor(event.impact)}`}>
                      {event.impact?.toUpperCase()}
                    </span>
                  </div>
                  <div className="text-xs text-gray-300">{event.title}</div>
                  {(event.forecast || event.previous) && (
                    <div className="text-2xs text-subtle mt-1">
                      {event.forecast && `Forecast: ${event.forecast}`}
                      {event.forecast && event.previous && ' | '}
                      {event.previous && `Previous: ${event.previous}`}
                    </div>
                  )}
                </div>
                <div className="text-2xs text-subtle whitespace-nowrap">
                  {formatTime(event.date)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
