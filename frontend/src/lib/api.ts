// API base URL - proxied through Next.js rewrites to FastAPI backend
const API_BASE = '/api';

export async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
}

// Types matching the backend models
export interface AccountSummary {
  balance: number;
  nav: number;
  unrealized_pl: number;
  margin_used: number;
  margin_available: number;
  open_trade_count: number;
}

export interface OpenTrade {
  id: string | number;
  instrument: string;
  units: number;
  price: number;
  entry_price: number;
  current_price: number;
  unrealized_pl: number;
  stop_loss: number | null;
  take_profit: number | null;
  trailing_stop: number | null;
  open_time: string;
  direction: 'long' | 'short';
}

export interface TradeHistory {
  id: string;
  instrument: string;
  direction: 'long' | 'short';
  units: number;
  entry_price: number;
  exit_price: number;
  profit_loss: number;
  profit_pips: number;
  open_time: string;
  close_time: string;
  close_reason: string;
}

export interface PerformanceStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  total_profit: number;
  total_loss: number;
  net_profit: number;
  max_drawdown: number;
  avg_win: number;
  avg_loss: number;
  best_trade: number;
  worst_trade: number;
  consecutive_wins: number;
  consecutive_losses: number;
  equity_curve: { date: string; equity: number }[];
}

export interface NewsEvent {
  title: string;
  country: string;
  date: string;
  impact: 'High' | 'Medium' | 'Low';
  forecast: string;
  previous: string;
}

export interface SystemStatus {
  bot_running: boolean;
  paper_trading: boolean;
  uptime_hours: number;
  uptime_seconds: number;
  signal_generation_running: boolean;
  external_signals_running: boolean;
  last_signal_time: string | null;
  last_signal_pair: string | null;
  last_signal_type: string | null;
  daily_stats: {
    trades_today: number;
    wins_today: number;
    losses_today: number;
    pnl_today: number;
  };
  can_trade: boolean;
  can_trade_reason: string;
  active_sessions: string[];
  consecutive_losses: number;
  cooldown_until: string | null;
}

export interface RuleCheck {
  rule_name: string;
  passed: boolean;
  reason: string | null;
}

export interface ActivityLog {
  id: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'trade';
  message: string;
  details?: string;
}

export interface TradingSettings {
  leverage: number;
  risk_per_trade: number;
  risk_reward_ratio: number;
  max_open_trades: number;
  max_consecutive_losses: number;
  cooldown_hours: number;
  use_atr_stop: boolean;
  fixed_stop_pips: number;
  atr_multiplier: number;
  trailing_stop_pips: number;
  partial_close_percent: number;
  pre_news_minutes: number;
  post_news_minutes: number;
  avoid_open_minutes: number;
  entry_timeframe: string;
  confirmation_timeframe: string;
  allowed_pairs: string[];
  // RSI & indicator settings
  rsi_period: number;
  rsi_oversold: number;
  rsi_overbought: number;
  correlation_threshold: number;
  // ATS strategy
  ats_strategy: 'standard' | 'aggressive' | 'scaling' | 'dpl';
  // Forward test mode
  paper_trading: boolean;
}
