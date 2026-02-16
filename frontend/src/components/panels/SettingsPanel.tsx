'use client';

import { useState, useEffect } from 'react';
import { useSettings } from '../../lib/hooks';
import type { TradingSettings } from '../../lib/api';

const DEFAULT_SETTINGS: TradingSettings = {
  leverage: 30,
  risk_per_trade: 0.02,
  risk_reward_ratio: 2.0,
  max_open_trades: 3,
  max_consecutive_losses: 3,
  cooldown_hours: 1,
  use_atr_stop: true,
  fixed_stop_pips: 50,
  atr_multiplier: 1.5,
  trailing_stop_pips: 20,
  partial_close_percent: 0.5,
  pre_news_minutes: 60,
  post_news_minutes: 30,
  avoid_open_minutes: 15,
  entry_timeframe: 'M15',
  confirmation_timeframe: 'H1',
  allowed_pairs: ['EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD'],
  rsi_period: 14,
  rsi_oversold: 30,
  rsi_overbought: 70,
  correlation_threshold: 0.7,
  ats_strategy: 'standard',
  paper_trading: true,
};

export default function SettingsPanel() {
  const { settings: serverSettings, updateSettings, isLive } = useSettings();
  const [localSettings, setLocalSettings] = useState<TradingSettings>(serverSettings || DEFAULT_SETTINGS);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync local state when server settings load/change
  useEffect(() => {
    if (serverSettings) {
      setLocalSettings(serverSettings);
    }
  }, [serverSettings]);

  const settings = localSettings;

  const update = <K extends keyof TradingSettings>(
    key: K,
    value: TradingSettings[K]
  ) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateSettings(localSettings);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError('Failed to save settings');
      console.error('Save error:', e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="card p-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-display font-bold text-gray-100 uppercase tracking-wider">
            Trading Configuration
          </h2>
          <p className="text-2xs text-muted mt-0.5">
            Adjust parameters and apply changes. System will use new values on next signal.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {error && <span className="text-2xs text-red-400">{error}</span>}
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? 'SAVING...' : saved ? '✓ SAVED' : 'SAVE CHANGES'}
          </button>
        </div>
      </div>

      {/* Trading Mode Banner */}
      <div className={`card p-4 flex items-center justify-between ${
        settings.paper_trading ? 'border border-warn/30 bg-warn/5' : 'border border-bull/30 bg-bull/5'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${
            settings.paper_trading ? 'bg-warn animate-pulse-slow' : 'bg-bull animate-pulse-slow'
          }`} />
          <div>
            <div className={`text-sm font-bold ${settings.paper_trading ? 'text-warn' : 'text-bull'}`}>
              {settings.paper_trading ? 'PAPER TRADING MODE' : 'LIVE TRADING MODE'}
            </div>
            <div className="text-2xs text-muted mt-0.5">
              {settings.paper_trading
                ? 'Signals are logged but NOT executed on OANDA. Safe for testing.'
                : 'Signals WILL execute real trades on your OANDA account.'}
            </div>
          </div>
        </div>
        <ToggleSwitch
          checked={!settings.paper_trading}
          onChange={(live) => update('paper_trading', !live)}
        />
      </div>

      {/* ATS Strategy Selector */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-display font-bold text-gray-100 uppercase tracking-wider">
              ATS Strategy
            </h3>
            <p className="text-2xs text-muted mt-0.5">
              Select exit strategy from the AutoTrend System guide
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {[
            { value: 'standard', label: 'Standard', desc: 'SL=swing, 50% at 2R, rest at color flip' },
            { value: 'aggressive', label: 'Aggressive', desc: 'SL=trigger bar, full exit at 10R' },
            { value: 'scaling', label: 'Scaling', desc: 'Add at +1R, tighten SL, exit at 3R' },
            { value: 'dpl', label: 'DPL', desc: '1/3 at DPL1, 1/3 at DPL2, 1/3 at flip' },
          ].map((s) => {
            const active = settings.ats_strategy === s.value;
            return (
              <button
                key={s.value}
                onClick={() => update('ats_strategy', s.value as any)}
                className={`p-3 rounded border text-left transition-all ${
                  active
                    ? 'bg-accent-cyan/10 border-accent-cyan/30'
                    : 'bg-panel-bg border-panel-border hover:border-gray-600'
                }`}
              >
                <div className={`text-xs font-semibold ${active ? 'text-accent-cyan' : 'text-gray-300'}`}>
                  {s.label}
                </div>
                <div className="text-2xs text-subtle mt-1 leading-relaxed">{s.desc}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Leverage & Risk Management */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Leverage & Risk Management
            </span>
          </div>
          <div className="p-4 space-y-4">
            <SettingRow label="Leverage" hint="Account leverage ratio (e.g., 10 = 10:1)">
              <select
                value={settings.leverage}
                onChange={(e) => update('leverage', parseInt(e.target.value))}
                className="input-field w-24"
              >
                <option value={5}>5:1</option>
                <option value={10}>10:1</option>
                <option value={20}>20:1</option>
                <option value={30}>30:1</option>
                <option value={50}>50:1</option>
                <option value={100}>100:1</option>
              </select>
            </SettingRow>
            <SettingRow label="Risk Per Trade (%)" hint="Percentage of account balance risked per trade">
              <input
                type="number"
                step="0.1"
                value={settings.risk_per_trade}
                onChange={(e) => update('risk_per_trade', parseFloat(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="Risk/Reward Ratio" hint="Target R:R (test range: 1.5 - 2.5)">
              <input
                type="number"
                step="0.1"
                value={settings.risk_reward_ratio}
                onChange={(e) => update('risk_reward_ratio', parseFloat(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="Max Open Trades">
              <input
                type="number"
                value={settings.max_open_trades}
                onChange={(e) => update('max_open_trades', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="Partial Close (%)" hint="Close this % at first target">
              <input
                type="number"
                value={settings.partial_close_percent}
                onChange={(e) => update('partial_close_percent', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
          </div>
        </div>

        {/* Stop Loss */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Stop Loss
            </span>
          </div>
          <div className="p-4 space-y-4">
            <SettingRow label="Use ATR Stop">
              <ToggleSwitch
                checked={settings.use_atr_stop}
                onChange={(v) => update('use_atr_stop', v)}
              />
            </SettingRow>
            <SettingRow label="ATR Multiplier" hint="Stop = ATR × multiplier">
              <input
                type="number"
                step="0.1"
                value={settings.atr_multiplier}
                onChange={(e) => update('atr_multiplier', parseFloat(e.target.value))}
                className="input-field w-24 text-right"
                disabled={!settings.use_atr_stop}
              />
            </SettingRow>
            <SettingRow label="Fixed Stop (pips)" hint="Used when ATR stop is off">
              <input
                type="number"
                step="0.5"
                value={settings.fixed_stop_pips}
                onChange={(e) => update('fixed_stop_pips', parseFloat(e.target.value))}
                className="input-field w-24 text-right"
                disabled={settings.use_atr_stop}
              />
            </SettingRow>
            <SettingRow label="Trailing Stop (pips)" hint="Applied after partial close">
              <input
                type="number"
                step="0.5"
                value={settings.trailing_stop_pips}
                onChange={(e) => update('trailing_stop_pips', parseFloat(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
          </div>
        </div>

        {/* Loss Streak Protection */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Loss Streak Protection
            </span>
          </div>
          <div className="p-4 space-y-4">
            <SettingRow label="Max Consecutive Losses" hint="Stop trading after this many losses">
              <input
                type="number"
                value={settings.max_consecutive_losses}
                onChange={(e) => update('max_consecutive_losses', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="Cooldown Hours" hint="Wait time after hitting loss streak">
              <input
                type="number"
                step="0.5"
                value={settings.cooldown_hours}
                onChange={(e) => update('cooldown_hours', parseFloat(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
          </div>
        </div>

        {/* News Filter */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              News & Market Hours
            </span>
          </div>
          <div className="p-4 space-y-4">
            <SettingRow label="Pre-News (min)" hint="Close positions this many minutes before news">
              <input
                type="number"
                value={settings.pre_news_minutes}
                onChange={(e) => update('pre_news_minutes', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="Post-News (min)" hint="Avoid trading for this many minutes after news">
              <input
                type="number"
                value={settings.post_news_minutes}
                onChange={(e) => update('post_news_minutes', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="Market Open Avoid (min)" hint="Skip first N minutes after session opens">
              <input
                type="number"
                value={settings.avoid_open_minutes}
                onChange={(e) => update('avoid_open_minutes', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
          </div>
        </div>

        {/* Timeframes */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Timeframes
            </span>
          </div>
          <div className="p-4 space-y-4">
            <SettingRow label="Entry Timeframe">
              <select
                value={settings.entry_timeframe}
                onChange={(e) => update('entry_timeframe', e.target.value)}
                className="input-field w-24"
              >
                <option value="M5">M5</option>
                <option value="M15">M15</option>
                <option value="M30">M30</option>
                <option value="H1">H1</option>
              </select>
            </SettingRow>
            <SettingRow label="Confirmation TF">
              <select
                value={settings.confirmation_timeframe}
                onChange={(e) => update('confirmation_timeframe', e.target.value)}
                className="input-field w-24"
              >
                <option value="M30">M30</option>
                <option value="H1">H1</option>
                <option value="H4">H4</option>
                <option value="D">D</option>
              </select>
            </SettingRow>
          </div>
        </div>

        {/* Pairs */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Trading Pairs
            </span>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-2 gap-2">
              {['EUR_USD', 'USD_JPY', 'GBP_USD', 'AUD_USD', 'NZD_USD', 'USD_CHF', 'USD_CAD'].map(
                (pair) => {
                  const active = settings.allowed_pairs.includes(pair);
                  return (
                    <button
                      key={pair}
                      onClick={() => {
                        if (active) {
                          update(
                            'allowed_pairs',
                            settings.allowed_pairs.filter((p) => p !== pair)
                          );
                        } else {
                          update('allowed_pairs', [...settings.allowed_pairs, pair]);
                        }
                      }}
                      className={`px-3 py-2 rounded border text-xs font-mono transition-all ${
                        active
                          ? 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan'
                          : 'bg-panel-bg border-panel-border text-subtle hover:text-gray-300'
                      }`}
                    >
                      {pair.replace('_', '/')}
                    </button>
                  );
                }
              )}
            </div>
          </div>
        </div>

        {/* RSI Settings */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              RSI Indicator
            </span>
          </div>
          <div className="p-4 space-y-4">
            <SettingRow label="RSI Period" hint="Lookback period for RSI calculation">
              <input
                type="number"
                value={settings.rsi_period}
                onChange={(e) => update('rsi_period', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="RSI Oversold" hint="Buy signal threshold (default: 30)">
              <input
                type="number"
                value={settings.rsi_oversold}
                onChange={(e) => update('rsi_oversold', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
            <SettingRow label="RSI Overbought" hint="Sell signal threshold (default: 70)">
              <input
                type="number"
                value={settings.rsi_overbought}
                onChange={(e) => update('rsi_overbought', parseInt(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
          </div>
        </div>

        {/* Correlation */}
        <div className="card">
          <div className="px-4 py-2.5 border-b border-panel-border">
            <span className="text-2xs font-semibold text-subtle uppercase tracking-widest">
              Correlation Filter
            </span>
          </div>
          <div className="p-4 space-y-4">
            <SettingRow label="Threshold" hint="Pairs above this correlation are blocked (0.0 - 1.0)">
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={settings.correlation_threshold}
                onChange={(e) => update('correlation_threshold', parseFloat(e.target.value))}
                className="input-field w-24 text-right"
              />
            </SettingRow>
          </div>
        </div>
      </div>
    </div>
  );
}

function SettingRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <div className="text-xs text-gray-300">{label}</div>
        {hint && <div className="text-2xs text-subtle mt-0.5">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`w-10 h-5 rounded-full transition-colors relative ${
        checked ? 'bg-accent-cyan/30' : 'bg-panel-bg border border-panel-border'
      }`}
    >
      <div
        className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${
          checked
            ? 'left-[22px] bg-accent-cyan'
            : 'left-0.5 bg-subtle'
        }`}
      />
    </button>
  );
}
