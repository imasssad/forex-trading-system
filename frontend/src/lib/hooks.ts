/**
 * Data hooks using SWR for real-time dashboard data.
 * Fetches from FastAPI backend (/api/*).
 */
'use client';

import useSWR from 'swr';
import type {
  AccountSummary,
  SystemStatus,
  OpenTrade,
  TradeHistory,
  PerformanceStats,
  NewsEvent,
  ActivityLog,
  TradingSettings,
} from './api';

const API = '/api';

async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

/** True when backend is reachable */
export function useBackendHealth() {
  const { data, error } = useSWR('/health', fetcher, {
    refreshInterval: 30_000,
    revalidateOnFocus: false,
  });
  return { online: !error && !!data, data };
}

/** OANDA account summary (balance, NAV, margin) */
export function useAccount() {
  const { data, error } = useSWR<AccountSummary>(`${API}/account`, fetcher, {
    refreshInterval: 5_000,
  });
  return {
    account: data,
    isLive: !error && !!data,
    error,
  };
}

/** System status for top bar */
export function useStatus() {
  const { data, error } = useSWR<SystemStatus>(`${API}/status`, fetcher, {
    refreshInterval: 5_000,
  });
  return {
    status: data,
    isLive: !error && !!data,
    error,
  };
}

/** Open trades */
export function useOpenTrades() {
  const { data, error, mutate } = useSWR<{ count: number; trades: OpenTrade[] }>(
    `${API}/trades/open`,
    fetcher,
    { refreshInterval: 3_000 }
  );
  return {
    trades: data?.trades ?? [],
    count: data?.count ?? 0,
    isLive: !error && !!data,
    refresh: mutate,
    error,
  };
}

/** Trade history */
export function useTradeHistory(limit = 100) {
  const { data, error } = useSWR<{ count: number; trades: TradeHistory[] }>(
    `${API}/trades/history?limit=${limit}`,
    fetcher,
    { refreshInterval: 10_000 }
  );
  return {
    trades: data?.trades ?? [],
    isLive: !error && !!data,
    error,
  };
}

/** Performance stats */
export function usePerformance(days?: number) {
  const url = days ? `${API}/performance?days=${days}` : `${API}/performance`;
  const { data, error } = useSWR<PerformanceStats>(url, fetcher, {
    refreshInterval: 30_000,
  });
  return {
    performance: data,
    isLive: !error && !!data,
    error,
  };
}

/** News from ForexFactory (real data!) */
export function useNews(impact?: string) {
  const url = impact ? `${API}/news?impact=${impact}` : `${API}/news`;
  const { data, error } = useSWR<{ count: number; events: NewsEvent[]; last_refresh: string }>(
    url,
    fetcher,
    { refreshInterval: 60_000 }
  );
  return {
    events: data?.events ?? [],
    lastRefresh: data?.last_refresh,
    isLive: !error && !!data,
    error,
  };
}

/** Activity logs */
export function useActivity(limit = 100) {
  const { data, error } = useSWR<{ count: number; logs: ActivityLog[] }>(
    `${API}/activity?limit=${limit}`,
    fetcher,
    { refreshInterval: 5_000 }
  );
  return {
    logs: data?.logs ?? [],
    isLive: !error && !!data,
    error,
  };
}

/** Trading settings */
export function useSettings() {
  const { data, error, mutate } = useSWR<TradingSettings>(
    `${API}/settings`,
    fetcher
  );

  const updateSettings = async (updates: Partial<TradingSettings>) => {
    const res = await fetch(`${API}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error('Failed to save settings');
    mutate();
    return res.json();
  };

  return {
    settings: data,
    isLive: !error && !!data,
    updateSettings,
    refresh: mutate,
    error,
  };
}

/** Backtest runs */
export function useBacktestRuns() {
  const { data, error, mutate } = useSWR<{ count: number; runs: any[] }>(
    `${API}/backtest/runs`,
    fetcher
  );

  const triggerBacktest = async (pair: string, startDate: string, endDate: string) => {
    const res = await fetch(
      `${API}/backtest/run?pair=${pair}&start_date=${startDate}&end_date=${endDate}`,
      { method: 'POST' }
    );
    if (!res.ok) throw new Error('Backtest failed');
    const result = await res.json();
    mutate();
    return result;
  };

  return {
    runs: data?.runs ?? [],
    isLive: !error && !!data,
    triggerBacktest,
    error,
  };
}

/** Compare two backtests: current server config vs overrides */
export async function compareBacktest(
  pair: string,
  startDate: string,
  endDate: string,
  overrides: { atr_multiplier?: number; risk_per_trade?: number; risk_reward_ratio?: number } = {}
) {
  const res = await fetch(`${API}/backtest/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pair, start_date: startDate, end_date: endDate, ...overrides }),
  });
  if (!res.ok) throw new Error('Compare failed');
  return res.json();
}
