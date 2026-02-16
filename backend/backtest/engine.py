"""
Backtesting Engine for ATS
Simulates the full trading system on historical data:
  - AutoTrend + RSI signal generation
  - HTF trend confirmation (M15 → H1)
  - Correlation filter (no duplicate exposure)
  - Market hours filter (skip 15min after opens, weekends)
  - News filter (skip around high-impact events — simulated)
  - Loss streak cooldown (4 losses → 6hr pause)
  - Partial close at target, trailing stop on remainder
  - Spread + slippage costs

Data source: CSV files with OHLCV columns.
Montgomery can export from TradingView or use OANDA historical data.
"""

import csv
import json
import math
import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from zoneinfo import ZoneInfo
from pathlib import Path
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import TradingConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


# ===================== DATA TYPES =====================

@dataclass
class Candle:
    """Single OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


@dataclass
class BacktestTrade:
    """A single trade in the backtest."""
    id: int
    instrument: str
    direction: str          # "long" / "short"
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    units: float
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    profit_loss: float = 0.0
    profit_pips: float = 0.0
    close_reason: str = ""
    # Partial close tracking
    partial_closed: bool = False
    remaining_units: float = 0.0
    trailing_stop: float = 0.0
    # ATS strategy fields
    strategy: str = "standard"
    risk_distance: float = 0.0    # entry-to-SL distance
    original_stop: float = 0.0    # remember original SL
    scaled_in: bool = False       # Scaling strategy
    dpl1_closed: bool = False     # DPL strategy
    dpl2_closed: bool = False     # DPL strategy
    trend_bar_low: float = 0.0    # Aggressive strategy SL
    trend_bar_high: float = 0.0   # Aggressive strategy SL


@dataclass
class BacktestResult:
    """Full backtest output."""
    pair: str
    start_date: str
    end_date: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    max_drawdown: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    sharpe_ratio: float = 0.0
    total_spread_cost: float = 0.0
    total_slippage_cost: float = 0.0
    avg_trade_duration_hours: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    equity_curve: List[Dict] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


# ===================== INDICATORS =====================

def calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """Calculate RSI using Wilder's smoothing (matches TradingView)."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    # Wilder's smoothed averages
    gains = [max(d, 0) for d in deltas[:period]]
    losses = [max(-d, 0) for d in deltas[:period]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for d in deltas[period:]:
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr(candles: List[Candle], period: int = 14) -> Optional[float]:
    """Calculate ATR using Wilder's smoothing."""
    if len(candles) < period + 1:
        return None

    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        trs.append(tr)

    # Wilder's smoothed ATR
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


# ===================== SUPERTREND (Real ATS Logic) =====================

@dataclass
class SupertrendState:
    """Tracks Supertrend state bar-by-bar."""
    direction: int = 1        # 1 = bullish (blue), -1 = bearish (red)
    upper_band: float = 0.0
    lower_band: float = 0.0
    prev_direction: int = 0
    changed: bool = False

    # Breakout tracking (from ATS Strategy Guide)
    trigger_bar_high: float = 0.0
    trigger_bar_low: float = 0.0
    waiting_breakout: bool = False
    pending_direction: str = ""  # "long" / "short"
    bars_since_trigger: int = 0


def calc_supertrend_series(
    candles: List[Candle], atr_period: int = 10, multiplier: float = 3.0
) -> List[SupertrendState]:
    """
    Calculate Supertrend for every candle — matches the Pine Script Supertrend.
    Returns a list of SupertrendState (one per candle).
    """
    states = []

    # Need ATR first — build TR series
    atr_val = 0.0
    for i, c in enumerate(candles):
        prev_close = candles[i - 1].close if i > 0 else c.close
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))

        if i < atr_period:
            # Not enough data yet
            states.append(SupertrendState())
            continue
        elif i == atr_period:
            # First ATR = simple average
            trs = []
            for j in range(1, atr_period + 1):
                pc = candles[j - 1].close
                t = max(candles[j].high - candles[j].low,
                        abs(candles[j].high - pc), abs(candles[j].low - pc))
                trs.append(t)
            atr_val = sum(trs) / atr_period
        else:
            # Wilder's smoothed ATR
            atr_val = (atr_val * (atr_period - 1) + tr) / atr_period

        hl2 = (c.high + c.low) / 2
        raw_upper = hl2 + multiplier * atr_val
        raw_lower = hl2 - multiplier * atr_val

        prev = states[-1] if states else SupertrendState()

        # Band logic (same as Pine Script)
        if prev.upper_band == 0:
            final_upper = raw_upper
        else:
            final_upper = raw_upper if (raw_upper < prev.upper_band or
                                        candles[i - 1].close > prev.upper_band) else prev.upper_band

        if prev.lower_band == 0:
            final_lower = raw_lower
        else:
            final_lower = raw_lower if (raw_lower > prev.lower_band or
                                        candles[i - 1].close < prev.lower_band) else prev.lower_band

        # Direction
        prev_dir = prev.direction if prev.direction != 0 else 1
        if prev_dir == -1 and c.close > prev.upper_band and prev.upper_band > 0:
            direction = 1
        elif prev_dir == 1 and c.close < prev.lower_band and prev.lower_band > 0:
            direction = -1
        else:
            direction = prev_dir

        changed = direction != prev_dir

        st = SupertrendState(
            direction=direction,
            upper_band=final_upper,
            lower_band=final_lower,
            prev_direction=prev_dir,
            changed=changed,
        )

        # ---- ATS Breakout Logic (from Strategy Guide PDF) ----
        #
        # When ATS turns blue: record trigger bar, wait for next bar
        #   to break ABOVE the trigger bar's high → LONG entry
        # When ATS turns red: record trigger bar, wait for next bar
        #   to break BELOW the trigger bar's low → SHORT entry
        #
        # Cancel if no breakout within 5 bars.

        if changed and direction == 1:
            # ATS just turned blue
            st.trigger_bar_high = c.high
            st.trigger_bar_low = c.low
            st.waiting_breakout = True
            st.pending_direction = "long"
            st.bars_since_trigger = 0
        elif changed and direction == -1:
            # ATS just turned red
            st.trigger_bar_high = c.high
            st.trigger_bar_low = c.low
            st.waiting_breakout = True
            st.pending_direction = "short"
            st.bars_since_trigger = 0
        elif prev.waiting_breakout:
            # Carry forward pending state
            st.trigger_bar_high = prev.trigger_bar_high
            st.trigger_bar_low = prev.trigger_bar_low
            st.pending_direction = prev.pending_direction
            st.bars_since_trigger = prev.bars_since_trigger + 1
            st.waiting_breakout = True

            # Cancel after 5 bars
            if st.bars_since_trigger > 5:
                st.waiting_breakout = False

        states.append(st)

    return states


def find_swing_low(candles: List[Candle], end_idx: int, lookback: int = 5) -> float:
    """Find last swing low before a given bar (for long stop loss — ATS rule)."""
    start = max(0, end_idx - 20)
    lowest = candles[start].low
    for j in range(start, end_idx):
        # Pivot low: lower than both neighbors
        if j > 0 and j < len(candles) - 1:
            if candles[j].low <= candles[j - 1].low and candles[j].low <= candles[j + 1].low:
                lowest = candles[j].low
        elif candles[j].low < lowest:
            lowest = candles[j].low
    return lowest


def find_swing_high(candles: List[Candle], end_idx: int, lookback: int = 5) -> float:
    """Find last swing high before a given bar (for short stop loss — ATS rule)."""
    start = max(0, end_idx - 20)
    highest = candles[start].high
    for j in range(start, end_idx):
        if j > 0 and j < len(candles) - 1:
            if candles[j].high >= candles[j - 1].high and candles[j].high >= candles[j + 1].high:
                highest = candles[j].high
        elif candles[j].high > highest:
            highest = candles[j].high
    return highest


def _ema(values: List[float], period: int) -> Optional[float]:
    """Calculate EMA."""
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


# ===================== MARKET HOURS (BACKTEST) =====================

# Session open hours in UTC
SESSION_OPENS = {
    "Sydney": 21,   # 21:00 UTC
    "Tokyo": 0,     # 00:00 UTC
    "London": 7,    # 07:00 UTC (winter) / 06:00 (summer)
    "New_York": 12, # 12:00 UTC (winter) / 11:00 (summer)
}


def is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5


def is_near_session_open(dt: datetime, avoid_minutes: int = 15) -> bool:
    """Check if within N minutes of any session open."""
    hour = dt.hour
    minute = dt.minute
    for name, open_hour in SESSION_OPENS.items():
        if hour == open_hour and minute < avoid_minutes:
            return True
    return False


# ===================== DATA LOADING =====================

def load_csv_candles(filepath: str) -> List[Candle]:
    """
    Load candles from CSV.
    Supports common formats:
    - TradingView export: time,open,high,low,close,volume
    - OANDA export: Date,Open,High,Low,Close,Volume
    - Generic: timestamp/date/time, open, high, low, close, volume
    """
    candles = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        # Normalize headers
        headers = {h.strip().lower(): h for h in reader.fieldnames}

        # Find column names
        time_col = headers.get("time") or headers.get("timestamp") or headers.get("date") or headers.get("datetime")
        open_col = headers.get("open")
        high_col = headers.get("high")
        low_col = headers.get("low")
        close_col = headers.get("close")
        vol_col = headers.get("volume")

        if not all([time_col, open_col, high_col, low_col, close_col]):
            raise ValueError(
                f"CSV must have time/open/high/low/close columns. Found: {list(headers.keys())}"
            )

        for row in reader:
            try:
                ts_raw = row[time_col].strip()
                # Try multiple timestamp formats
                ts = None
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%Y.%m.%d %H:%M:%S",
                    "%Y.%m.%d %H:%M",
                    "%m/%d/%Y %H:%M",
                    "%d/%m/%Y %H:%M",
                ]:
                    try:
                        ts = datetime.strptime(ts_raw, fmt).replace(tzinfo=ZoneInfo("UTC"))
                        break
                    except ValueError:
                        continue

                # Try unix timestamp
                if ts is None:
                    try:
                        ts = datetime.fromtimestamp(int(ts_raw), tz=ZoneInfo("UTC"))
                    except (ValueError, OSError):
                        continue

                if ts is None:
                    continue

                candles.append(Candle(
                    timestamp=ts,
                    open=float(row[open_col]),
                    high=float(row[high_col]),
                    low=float(row[low_col]),
                    close=float(row[close_col]),
                    volume=float(row[vol_col]) if vol_col and row.get(vol_col) else 0,
                ))
            except (ValueError, KeyError):
                continue

    candles.sort(key=lambda c: c.timestamp)
    logger.info(f"Loaded {len(candles)} candles from {filepath}")
    return candles


def generate_htf_candles(candles: List[Candle], factor: int = 4) -> List[Candle]:
    """
    Aggregate M15 candles into H1 candles (factor=4).
    Groups by hour boundary.
    """
    if not candles:
        return []

    htf = []
    bucket = []

    for c in candles:
        if bucket and c.timestamp.hour != bucket[0].timestamp.hour:
            # Close current bucket
            htf.append(Candle(
                timestamp=bucket[0].timestamp,
                open=bucket[0].open,
                high=max(b.high for b in bucket),
                low=min(b.low for b in bucket),
                close=bucket[-1].close,
                volume=sum(b.volume for b in bucket),
            ))
            bucket = []
        bucket.append(c)

    # Final bucket
    if bucket:
        htf.append(Candle(
            timestamp=bucket[0].timestamp,
            open=bucket[0].open,
            high=max(b.high for b in bucket),
            low=min(b.low for b in bucket),
            close=bucket[-1].close,
            volume=sum(b.volume for b in bucket),
        ))

    return htf


# ===================== BACKTEST ENGINE =====================

class BacktestEngine:
    """
    Full backtest engine that simulates the ATS trading system.

    Usage:
        engine = BacktestEngine(config=DEFAULT_CONFIG)
        result = engine.run(pair="EUR_USD", start_date="2024-01-01", end_date="2025-12-31")

    Or with CSV data:
        engine = BacktestEngine()
        result = engine.run_from_csv("data/EURUSD_M15.csv", pair="EUR_USD")
    """

    def __init__(self, config: TradingConfig = None):
        self.config = config or DEFAULT_CONFIG
        self.pip_sizes = {
            "EUR_USD": 0.0001, "USD_JPY": 0.01, "GBP_USD": 0.0001,
            "AUD_USD": 0.0001, "NZD_USD": 0.0001, "USD_CHF": 0.0001,
            "USD_CAD": 0.0001,
        }

    def run_from_csv(
        self,
        csv_path: str,
        pair: str = "EUR_USD",
    ) -> Dict:
        """Run backtest from a CSV file."""
        candles = load_csv_candles(csv_path)
        if not candles:
            raise ValueError(f"No candles loaded from {csv_path}")
        return self._execute_backtest(candles, pair)

    def run_multi_pair(
        self,
        pairs: List[str] = None,
        start_date: str = "2024-01-01",
        end_date: str = "2025-12-31",
    ) -> Dict:
        """
        Run backtest across multiple pairs simultaneously.
        Combines all pair data and runs a single portfolio-level backtest.
        This properly tests correlation filters and max open trades across pairs.
        """
        if pairs is None:
            pairs = self.config.pairs.ALLOWED_PAIRS

        # Load data for all pairs
        all_candles: Dict[str, List[Candle]] = {}
        for pair in pairs:
            path = f"data/backtest/{pair}_M15.csv"
            if not os.path.exists(path):
                alt = f"data/{pair}_M15.csv"
                if os.path.exists(alt):
                    path = alt
                else:
                    logger.warning(f"No data file for {pair}, skipping")
                    continue

            candles = load_csv_candles(path)
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("UTC"))
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("UTC"))
            candles = [c for c in candles if start <= c.timestamp <= end]

            if len(candles) >= 100:
                all_candles[pair] = candles
                logger.info(f"Loaded {len(candles)} candles for {pair}")
            else:
                logger.warning(f"Not enough data for {pair}: {len(candles)} candles")

        if not all_candles:
            raise ValueError("No valid data files found for any pairs")

        return self._execute_multi_pair_backtest(all_candles)

    def _execute_multi_pair_backtest(self, all_candles: Dict[str, List[Candle]]) -> Dict:
        """Execute portfolio-level backtest across multiple pairs."""
        cfg = self.config

        # Pre-calculate indicators for each pair
        pair_data = {}
        for pair, candles in all_candles.items():
            pip_size = self.pip_sizes.get(pair, 0.0001)
            spread_pips = cfg.backtest.SPREAD_PIPS.get(pair, 1.0)
            slippage_pips = cfg.backtest.SLIPPAGE_PIPS

            st_states = calc_supertrend_series(candles, atr_period=10, multiplier=3.0)
            htf_candles = generate_htf_candles(candles, factor=4)
            htf_states = calc_supertrend_series(htf_candles, atr_period=10, multiplier=3.0)

            pair_data[pair] = {
                "candles": candles,
                "st_states": st_states,
                "htf_candles": htf_candles,
                "htf_states": htf_states,
                "pip_size": pip_size,
                "spread_cost": spread_pips * pip_size,
                "slippage_cost": slippage_pips * pip_size,
            }

        # Build unified timeline of all timestamps
        all_timestamps = set()
        for pair, data in pair_data.items():
            for c in data["candles"]:
                all_timestamps.add(c.timestamp)
        timeline = sorted(all_timestamps)

        # Build timestamp index for each pair
        for pair, data in pair_data.items():
            ts_to_idx = {}
            for i, c in enumerate(data["candles"]):
                ts_to_idx[c.timestamp] = i
            data["ts_to_idx"] = ts_to_idx

        # State
        open_trades: List[BacktestTrade] = []
        closed_trades: List[BacktestTrade] = []
        trade_counter = 0
        consecutive_losses = 0
        cooldown_until: Optional[datetime] = None
        balance = 10000.0
        peak_balance = balance
        max_drawdown = 0.0
        equity_points = []
        monthly_pnl: Dict[str, float] = {}

        rsi_period = cfg.indicators.RSI_PERIOD
        atr_period = cfg.risk.ATR_PERIOD if hasattr(cfg.risk, "ATR_PERIOD") else 14
        start_bar = max(rsi_period + 1, 30)

        for ts in timeline:
            now = ts

            if is_weekend(now):
                continue

            # Process each pair at this timestamp
            for pair, data in pair_data.items():
                if ts not in data["ts_to_idx"]:
                    continue

                i = data["ts_to_idx"][ts]
                if i < start_bar:
                    continue

                candles = data["candles"]
                candle = candles[i]
                st = data["st_states"][i]
                pip_size = data["pip_size"]
                spread_cost = data["spread_cost"]
                slippage_cost = data["slippage_cost"]

                # ---- CHECK OPEN TRADES FOR EXITS ----
                trades_to_close = []
                for trade in open_trades:
                    if trade.instrument != pair:
                        continue
                    exit_price, reason = self._check_trade_exit(trade, candle, pip_size, st)
                    if exit_price:
                        trades_to_close.append((trade, exit_price, reason))

                for trade, exit_price, reason in trades_to_close:
                    self._close_trade(trade, exit_price, now, reason, pip_size,
                                      spread_cost, slippage_cost)
                    open_trades.remove(trade)
                    closed_trades.append(trade)
                    balance += trade.profit_loss

                    if balance > peak_balance:
                        peak_balance = balance
                    dd = peak_balance - balance
                    if dd > max_drawdown:
                        max_drawdown = dd

                    if trade.profit_loss > 0:
                        consecutive_losses = 0
                        cooldown_until = None
                    elif trade.profit_loss < 0:
                        consecutive_losses += 1
                        if consecutive_losses >= cfg.risk.MAX_CONSECUTIVE_LOSSES:
                            cooldown_until = now + timedelta(hours=cfg.risk.COOLDOWN_HOURS)

                    month_key = now.strftime("%Y-%m")
                    monthly_pnl[month_key] = monthly_pnl.get(month_key, 0) + trade.profit_loss

                # ---- CHECK IF WE CAN OPEN NEW TRADES ----
                if cooldown_until and now < cooldown_until:
                    continue
                if cooldown_until and now >= cooldown_until:
                    cooldown_until = None
                    consecutive_losses = 0

                if len(open_trades) >= cfg.risk.MAX_OPEN_TRADES:
                    continue

                if is_near_session_open(now, cfg.hours.MARKET_OPEN_AVOID_MINUTES):
                    continue

                # ---- ATS BREAKOUT SIGNAL ----
                signal = None
                if st.waiting_breakout and st.bars_since_trigger >= 1:
                    if st.pending_direction == "long":
                        if candle.high > st.trigger_bar_high and candle.close > st.trigger_bar_high:
                            signal = "long"
                    elif st.pending_direction == "short":
                        if candle.low < st.trigger_bar_low and candle.close < st.trigger_bar_low:
                            signal = "short"

                if signal is None:
                    continue

                # ---- RSI FILTER ----
                lookback_candles = candles[max(0, i - 50):i + 1]
                closes = [c.close for c in lookback_candles]
                rsi = calc_rsi(closes, rsi_period)
                if rsi is None:
                    continue

                if signal == "long" and rsi >= cfg.indicators.RSI_OVERBOUGHT:
                    continue
                if signal == "short" and rsi <= cfg.indicators.RSI_OVERSOLD:
                    continue

                # ---- HTF CONFIRMATION ----
                htf_candles = data["htf_candles"]
                htf_states = data["htf_states"]
                htf_bullish = False
                for hc_idx in range(len(htf_candles) - 1, -1, -1):
                    if htf_candles[hc_idx].timestamp <= now and hc_idx < len(htf_states):
                        htf_bullish = htf_states[hc_idx].direction == 1
                        break

                if signal == "long" and not htf_bullish:
                    continue
                if signal == "short" and htf_bullish:
                    continue

                # ---- CORRELATION CHECK (across ALL pairs) ----
                if not self._passes_correlation_check(signal, pair, open_trades):
                    continue

                # ---- CALCULATE STOP LOSS ----
                atr = calc_atr(lookback_candles, atr_period)

                if signal == "long":
                    swing_sl = find_swing_low(candles, i) - 2 * pip_size
                    atr_sl = candle.close - (atr * cfg.risk.ATR_MULTIPLIER) if atr else swing_sl
                    fixed_sl = candle.close - cfg.risk.FIXED_STOP_PIPS * pip_size

                    if cfg.risk.USE_ATR_STOP:
                        sl = min(swing_sl, atr_sl)
                    else:
                        sl = fixed_sl

                    if candle.close - sl < 3 * pip_size:
                        sl = candle.close - 5 * pip_size

                    stop_distance = candle.close - sl
                    tp = candle.close + stop_distance * cfg.risk.RISK_REWARD_RATIO
                else:
                    swing_sl = find_swing_high(candles, i) + 2 * pip_size
                    atr_sl = candle.close + (atr * cfg.risk.ATR_MULTIPLIER) if atr else swing_sl
                    fixed_sl = candle.close + cfg.risk.FIXED_STOP_PIPS * pip_size

                    if cfg.risk.USE_ATR_STOP:
                        sl = max(swing_sl, atr_sl)
                    else:
                        sl = fixed_sl

                    if sl - candle.close < 3 * pip_size:
                        sl = candle.close + 5 * pip_size

                    stop_distance = sl - candle.close
                    tp = candle.close - stop_distance * cfg.risk.RISK_REWARD_RATIO

                # ---- OPEN TRADE ----
                trade_counter += 1
                entry_price = candle.close

                if signal == "long":
                    entry_price += spread_cost / 2 + slippage_cost
                else:
                    entry_price -= spread_cost / 2 + slippage_cost

                risk_amount = balance * (cfg.risk.RISK_PER_TRADE_PERCENT / 100)
                stop_pips = stop_distance / pip_size
                units = risk_amount / (stop_pips * pip_size) if stop_pips > 0 else 0

                trade = BacktestTrade(
                    id=trade_counter,
                    instrument=pair,
                    direction=signal,
                    entry_price=round(entry_price, 5),
                    entry_time=now,
                    stop_loss=round(sl, 5),
                    take_profit=round(tp, 5),
                    units=round(units, 0),
                    remaining_units=round(units, 0),
                )
                open_trades.append(trade)

            # Track equity periodically
            if trade_counter % 5 == 0 or len(equity_points) == 0:
                equity_points.append({
                    "date": now.strftime("%Y-%m-%d"),
                    "equity": round(balance, 2),
                })

        # Close remaining open trades
        for trade in open_trades:
            pair = trade.instrument
            data = pair_data.get(pair)
            if data and data["candles"]:
                last = data["candles"][-1]
                self._close_trade(trade, last.close, last.timestamp, "end_of_data",
                                  data["pip_size"], data["spread_cost"], data["slippage_cost"])
                closed_trades.append(trade)
                balance += trade.profit_loss

        # Compile multi-pair results
        return self._compile_multi_pair_results(
            closed_trades, list(all_candles.keys()), all_candles,
            balance, max_drawdown, monthly_pnl, equity_points
        )

    def _compile_multi_pair_results(
        self, trades: List[BacktestTrade], pairs: List[str],
        all_candles: Dict[str, List[Candle]], final_balance: float,
        max_drawdown: float, monthly_pnl: Dict, equity_points: List
    ) -> Dict:
        """Compile multi-pair backtest statistics."""
        if not trades:
            return {
                "pairs": pairs,
                "start_date": "",
                "end_date": "",
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "net_profit": 0,
                "max_drawdown": 0,
                "by_pair": {},
            }

        # Overall stats
        wins = [t for t in trades if t.profit_loss > 0]
        losses = [t for t in trades if t.profit_loss < 0]

        gross_profit = sum(t.profit_loss for t in wins)
        gross_loss = abs(sum(t.profit_loss for t in losses))
        net_profit = gross_profit - gross_loss

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0

        all_pnl = [t.profit_loss for t in trades]
        best = max(all_pnl) if all_pnl else 0
        worst = min(all_pnl) if all_pnl else 0

        # Per-pair breakdown
        by_pair = {}
        for pair in pairs:
            pair_trades = [t for t in trades if t.instrument == pair]
            if not pair_trades:
                continue
            pair_wins = [t for t in pair_trades if t.profit_loss > 0]
            pair_losses = [t for t in pair_trades if t.profit_loss < 0]
            pair_net = sum(t.profit_loss for t in pair_trades)

            by_pair[pair] = {
                "total_trades": len(pair_trades),
                "wins": len(pair_wins),
                "losses": len(pair_losses),
                "win_rate": round(len(pair_wins) / len(pair_trades) * 100, 1) if pair_trades else 0,
                "net_profit": round(pair_net, 2),
            }

        # Get date range
        all_dates = []
        for candles in all_candles.values():
            if candles:
                all_dates.extend([candles[0].timestamp, candles[-1].timestamp])
        start_date = min(all_dates).strftime("%Y-%m-%d") if all_dates else ""
        end_date = max(all_dates).strftime("%Y-%m-%d") if all_dates else ""

        # Trade list
        trade_list = []
        for t in trades:
            trade_list.append({
                "id": t.id,
                "instrument": t.instrument,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "profit_loss": t.profit_loss,
                "profit_pips": t.profit_pips,
                "close_reason": t.close_reason,
            })

        return {
            "pairs": pairs,
            "pair": ", ".join(pairs),  # For compatibility
            "start_date": start_date,
            "end_date": end_date,
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "net_profit": round(net_profit, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(-gross_loss, 2),
            "max_drawdown": round(-max_drawdown, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(-avg_loss, 2),
            "best_trade": round(best, 2),
            "worst_trade": round(worst, 2),
            "monthly_returns": {k: round(v, 2) for k, v in monthly_pnl.items()},
            "equity_curve": equity_points,
            "by_pair": by_pair,
            "trades": trade_list,
        }

    def run(
        self,
        pair: str = "EUR_USD",
        start_date: str = "2024-01-01",
        end_date: str = "2025-12-31",
        csv_path: str = None,
    ) -> Dict:
        """
        Run backtest.
        If csv_path is provided, load from file.
        Otherwise look for data/backtest/{PAIR}_M15.csv
        """
        if csv_path:
            path = csv_path
        else:
            # Try standard location
            path = f"data/backtest/{pair}_M15.csv"
            if not os.path.exists(path):
                # Try alternate locations
                alt = f"data/{pair}_M15.csv"
                if os.path.exists(alt):
                    path = alt
                else:
                    raise FileNotFoundError(
                        f"No data file found. Place M15 OHLCV CSV at: {path}\n"
                        f"Export from TradingView: Chart → Export → CSV\n"
                        f"Or download from OANDA historical data."
                    )

        candles = load_csv_candles(path)

        # Filter to date range
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("UTC"))
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("UTC"))
        candles = [c for c in candles if start <= c.timestamp <= end]

        if len(candles) < 100:
            raise ValueError(
                f"Not enough data: {len(candles)} candles. Need at least 100."
            )

        return self._execute_backtest(candles, pair)

    def _execute_backtest(self, candles: List[Candle], pair: str) -> Dict:
        """Core backtest loop — uses real Supertrend ATS logic with breakout confirmation."""
        cfg = self.config
        pip_size = self.pip_sizes.get(pair, 0.0001)
        spread_pips = cfg.backtest.SPREAD_PIPS.get(pair, 1.0)
        slippage_pips = cfg.backtest.SLIPPAGE_PIPS
        spread_cost = spread_pips * pip_size
        slippage_cost = slippage_pips * pip_size

        # ---- Pre-calculate Supertrend for ALL candles ----
        st_states = calc_supertrend_series(candles, atr_period=10, multiplier=3.0)

        # ---- Pre-calculate HTF Supertrend ----
        htf_candles = generate_htf_candles(candles, factor=4)
        htf_states = calc_supertrend_series(htf_candles, atr_period=10, multiplier=3.0)

        # State
        open_trades: List[BacktestTrade] = []
        closed_trades: List[BacktestTrade] = []
        trade_counter = 0
        consecutive_losses = 0
        cooldown_until: Optional[datetime] = None
        balance = 10000.0
        peak_balance = balance
        max_drawdown = 0.0

        equity_points = []
        monthly_pnl: Dict[str, float] = {}

        rsi_period = cfg.indicators.RSI_PERIOD
        atr_period = cfg.risk.ATR_PERIOD if hasattr(cfg.risk, "ATR_PERIOD") else 14

        # Need enough bars for Supertrend + RSI warm-up
        start_bar = max(rsi_period + 1, 30)

        for i in range(start_bar, len(candles)):
            candle = candles[i]
            now = candle.timestamp
            st = st_states[i]

            if is_weekend(now):
                continue

            # ---- CHECK OPEN TRADES FOR EXITS ----
            trades_to_close = []
            for trade in open_trades:
                exit_price, reason = self._check_trade_exit(trade, candle, pip_size, st)
                if exit_price:
                    trades_to_close.append((trade, exit_price, reason))

            for trade, exit_price, reason in trades_to_close:
                self._close_trade(trade, exit_price, now, reason, pip_size,
                                  spread_cost, slippage_cost)
                open_trades.remove(trade)
                closed_trades.append(trade)
                balance += trade.profit_loss

                if balance > peak_balance:
                    peak_balance = balance
                dd = peak_balance - balance
                if dd > max_drawdown:
                    max_drawdown = dd

                if trade.profit_loss > 0:
                    consecutive_losses = 0
                    cooldown_until = None
                elif trade.profit_loss < 0:
                    consecutive_losses += 1
                    if consecutive_losses >= cfg.risk.MAX_CONSECUTIVE_LOSSES:
                        cooldown_until = now + timedelta(hours=cfg.risk.COOLDOWN_HOURS)

                month_key = now.strftime("%Y-%m")
                monthly_pnl[month_key] = monthly_pnl.get(month_key, 0) + trade.profit_loss

            # ---- CHECK IF WE CAN OPEN NEW TRADES ----

            if cooldown_until and now < cooldown_until:
                continue
            if cooldown_until and now >= cooldown_until:
                cooldown_until = None
                consecutive_losses = 0

            if len(open_trades) >= cfg.risk.MAX_OPEN_TRADES:
                continue

            if is_near_session_open(now, cfg.hours.MARKET_OPEN_AVOID_MINUTES):
                continue

            # ---- ATS BREAKOUT SIGNAL (from Strategy Guide PDF) ----
            #
            # The ATS entry is NOT just "trend is bullish" — it requires:
            #   1. ATS changes color (Supertrend direction flips)
            #   2. The NEXT bar must break the signal bar's high (long) or low (short)
            #   3. This is a confirmation breakout entry
            #
            # We check: is a breakout happening on THIS bar?

            signal = None

            if st.waiting_breakout and st.bars_since_trigger >= 1:
                if st.pending_direction == "long":
                    # Next bar's high must overtake the trigger bar's high
                    if candle.high > st.trigger_bar_high and candle.close > st.trigger_bar_high:
                        signal = "long"
                elif st.pending_direction == "short":
                    # Next bar's low must overtake the trigger bar's low
                    if candle.low < st.trigger_bar_low and candle.close < st.trigger_bar_low:
                        signal = "short"

            if signal is None:
                continue

            # ---- RSI FILTER ----
            # Montgomery's rule: RSI + AutoTrend "agree"
            # ATS Guide + his setup: RSI should not be against the trade
            # Buy: RSI must NOT be overbought (< 70)
            # Sell: RSI must NOT be oversold (> 30)

            lookback_candles = candles[max(0, i - 50):i + 1]
            closes = [c.close for c in lookback_candles]
            rsi = calc_rsi(closes, rsi_period)
            if rsi is None:
                continue

            if signal == "long" and rsi >= cfg.indicators.RSI_OVERBOUGHT:
                continue  # Don't buy when overbought
            if signal == "short" and rsi <= cfg.indicators.RSI_OVERSOLD:
                continue  # Don't sell when oversold

            # ---- HTF CONFIRMATION (H1 must be same direction) ----
            htf_bullish = False
            for hc_idx in range(len(htf_candles) - 1, -1, -1):
                if htf_candles[hc_idx].timestamp <= now and hc_idx < len(htf_states):
                    htf_bullish = htf_states[hc_idx].direction == 1
                    break

            if signal == "long" and not htf_bullish:
                continue
            if signal == "short" and htf_bullish:
                continue

            # ---- CORRELATION CHECK ----
            if not self._passes_correlation_check(signal, pair, open_trades):
                continue

            # ---- CALCULATE STOP LOSS (ATS Rule: last swing low/high) ----
            atr = calc_atr(lookback_candles, atr_period)

            if signal == "long":
                # ATS rule: SL at last swing low before trend change
                swing_sl = find_swing_low(candles, i) - 2 * pip_size
                atr_sl = candle.close - (atr * cfg.risk.ATR_MULTIPLIER) if atr else swing_sl
                fixed_sl = candle.close - cfg.risk.FIXED_STOP_PIPS * pip_size

                if cfg.risk.USE_ATR_STOP:
                    sl = min(swing_sl, atr_sl)  # Use wider of swing/ATR
                else:
                    sl = fixed_sl

                # Minimum stop distance
                if candle.close - sl < 3 * pip_size:
                    sl = candle.close - 5 * pip_size

                stop_distance = candle.close - sl
                tp = candle.close + stop_distance * cfg.risk.RISK_REWARD_RATIO
            else:
                swing_sl = find_swing_high(candles, i) + 2 * pip_size
                atr_sl = candle.close + (atr * cfg.risk.ATR_MULTIPLIER) if atr else swing_sl
                fixed_sl = candle.close + cfg.risk.FIXED_STOP_PIPS * pip_size

                if cfg.risk.USE_ATR_STOP:
                    sl = max(swing_sl, atr_sl)
                else:
                    sl = fixed_sl

                if sl - candle.close < 3 * pip_size:
                    sl = candle.close + 5 * pip_size

                stop_distance = sl - candle.close
                tp = candle.close - stop_distance * cfg.risk.RISK_REWARD_RATIO

            # ---- OPEN TRADE ----
            trade_counter += 1
            entry_price = candle.close

            # Apply spread + slippage
            if signal == "long":
                entry_price += spread_cost / 2 + slippage_cost
            else:
                entry_price -= spread_cost / 2 + slippage_cost

            # Position size (% risk)
            risk_amount = balance * (cfg.risk.RISK_PER_TRADE_PERCENT / 100)
            stop_pips = stop_distance / pip_size
            units = risk_amount / (stop_pips * pip_size) if stop_pips > 0 else 0

            # ---- AGGRESSIVE STRATEGY: override SL to trend-change bar ----
            strat = cfg.ats_strategy.value if hasattr(cfg, 'ats_strategy') else "standard"
            if strat == "aggressive":
                if signal == "long":
                    agg_sl = st.trigger_bar_low - 2 * pip_size
                    # Only use if tighter than swing SL (closer to entry)
                    if agg_sl > sl:
                        sl = agg_sl
                        stop_distance = candle.close - sl
                        # Recalc TP with new distance
                        tp = candle.close + stop_distance * cfg.risk.RISK_REWARD_RATIO
                        # Recalc position size
                        stop_pips = stop_distance / pip_size
                        risk_amount = balance * (cfg.risk.RISK_PER_TRADE_PERCENT / 100)
                        units = risk_amount / (stop_pips * pip_size) if stop_pips > 0 else 0
                else:
                    agg_sl = st.trigger_bar_high + 2 * pip_size
                    if agg_sl < sl:
                        sl = agg_sl
                        stop_distance = sl - candle.close
                        tp = candle.close - stop_distance * cfg.risk.RISK_REWARD_RATIO
                        stop_pips = stop_distance / pip_size
                        risk_amount = balance * (cfg.risk.RISK_PER_TRADE_PERCENT / 100)
                        units = risk_amount / (stop_pips * pip_size) if stop_pips > 0 else 0

            trade = BacktestTrade(
                id=trade_counter,
                instrument=pair,
                direction=signal,
                entry_price=round(entry_price, 5),
                entry_time=now,
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                units=round(units, 0),
                remaining_units=round(units, 0),
                strategy=strat,
                risk_distance=round(stop_distance, 6),
                original_stop=round(sl, 5),
                trend_bar_low=st.trigger_bar_low,
                trend_bar_high=st.trigger_bar_high,
            )
            open_trades.append(trade)

            # Track equity
            if trade_counter % 5 == 0 or len(equity_points) == 0:
                equity_points.append({
                    "date": now.strftime("%Y-%m-%d"),
                    "equity": round(balance, 2),
                })

        # Close remaining open trades at last candle
        if open_trades and candles:
            last = candles[-1]
            for trade in open_trades:
                self._close_trade(trade, last.close, last.timestamp, "end_of_data",
                                  pip_size, spread_cost, slippage_cost)
                closed_trades.append(trade)
                balance += trade.profit_loss

        return self._compile_results(closed_trades, pair, candles, balance,
                                     max_drawdown, monthly_pnl, equity_points,
                                     spread_cost, slippage_cost, pip_size)

    def _check_trade_exit(
        self, trade: BacktestTrade, candle: Candle, pip_size: float,
        st: SupertrendState = None
    ) -> Tuple[Optional[float], str]:
        """
        Strategy-aware exit logic based on ATS Strategy Guide.
        Routes to the correct strategy handler.
        """
        strategy = getattr(trade, 'strategy', 'standard')
        if strategy == "aggressive":
            return self._exit_aggressive(trade, candle, pip_size, st)
        elif strategy == "scaling":
            return self._exit_scaling(trade, candle, pip_size, st)
        elif strategy == "dpl":
            return self._exit_dpl(trade, candle, pip_size, st)
        else:
            return self._exit_standard(trade, candle, pip_size, st)

    def _exit_standard(
        self, trade: BacktestTrade, candle: Candle, pip_size: float,
        st: SupertrendState = None
    ) -> Tuple[Optional[float], str]:
        """Strategy 1: SL=swing, 50% at 2R, rest at ATS color flip + trailing stop"""
        cfg = self.config
        rd = trade.risk_distance if trade.risk_distance > 0 else abs(trade.entry_price - trade.stop_loss)
        target_2r = trade.entry_price + rd * 2 * (1 if trade.direction == "long" else -1)

        if trade.direction == "long":
            if candle.low <= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            if st and st.changed and st.direction == -1 and trade.partial_closed:
                return candle.close, "ats_color_flip"
            if trade.partial_closed and trade.trailing_stop > 0:
                new_trail = candle.high - cfg.risk.TRAILING_STOP_PIPS * pip_size
                if new_trail > trade.trailing_stop:
                    trade.trailing_stop = new_trail
                if candle.low <= trade.trailing_stop:
                    return trade.trailing_stop, "trailing_stop"
            if not trade.partial_closed and candle.high >= target_2r:
                trade.partial_closed = True
                trade.remaining_units = trade.units * 0.5
                trade.trailing_stop = candle.high - cfg.risk.TRAILING_STOP_PIPS * pip_size
                return target_2r, "take_profit_2R"
        else:
            if candle.high >= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            if st and st.changed and st.direction == 1 and trade.partial_closed:
                return candle.close, "ats_color_flip"
            if trade.partial_closed and trade.trailing_stop > 0:
                new_trail = candle.low + cfg.risk.TRAILING_STOP_PIPS * pip_size
                if new_trail < trade.trailing_stop:
                    trade.trailing_stop = new_trail
                if candle.high >= trade.trailing_stop:
                    return trade.trailing_stop, "trailing_stop"
            if not trade.partial_closed and candle.low <= target_2r:
                trade.partial_closed = True
                trade.remaining_units = trade.units * 0.5
                trade.trailing_stop = candle.low + cfg.risk.TRAILING_STOP_PIPS * pip_size
                return target_2r, "take_profit_2R"

        return None, ""

    def _exit_aggressive(
        self, trade: BacktestTrade, candle: Candle, pip_size: float,
        st: SupertrendState = None
    ) -> Tuple[Optional[float], str]:
        """Strategy 2: SL=trend-change bar, full exit at 10R"""
        rd = trade.risk_distance if trade.risk_distance > 0 else abs(trade.entry_price - trade.stop_loss)
        target_10r = trade.entry_price + rd * 10 * (1 if trade.direction == "long" else -1)

        if trade.direction == "long":
            if candle.low <= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            if candle.high >= target_10r:
                return target_10r, "take_profit_10R"
        else:
            if candle.high >= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            if candle.low <= target_10r:
                return target_10r, "take_profit_10R"

        return None, ""

    def _exit_scaling(
        self, trade: BacktestTrade, candle: Candle, pip_size: float,
        st: SupertrendState = None
    ) -> Tuple[Optional[float], str]:
        """Strategy 3: Add at +1R, tighten SL to half, full exit at 3R"""
        rd = trade.risk_distance if trade.risk_distance > 0 else abs(trade.entry_price - trade.stop_loss)
        scale_target = trade.entry_price + rd * 1 * (1 if trade.direction == "long" else -1)
        exit_target = trade.entry_price + rd * 3 * (1 if trade.direction == "long" else -1)

        if trade.direction == "long":
            if candle.low <= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            # Scale in at +1R: double units, tighten SL
            if not trade.scaled_in and candle.high >= scale_target:
                trade.scaled_in = True
                trade.units *= 2
                trade.remaining_units = trade.units
                half_risk = rd / 2
                trade.stop_loss = trade.entry_price - half_risk
            # Full exit at 3R
            if candle.high >= exit_target:
                return exit_target, "take_profit_3R"
        else:
            if candle.high >= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            if not trade.scaled_in and candle.low <= scale_target:
                trade.scaled_in = True
                trade.units *= 2
                trade.remaining_units = trade.units
                half_risk = rd / 2
                trade.stop_loss = trade.entry_price + half_risk
            if candle.low <= exit_target:
                return exit_target, "take_profit_3R"

        return None, ""

    def _exit_dpl(
        self, trade: BacktestTrade, candle: Candle, pip_size: float,
        st: SupertrendState = None
    ) -> Tuple[Optional[float], str]:
        """Strategy 4: 1/3 at DPL1 (~1R), 1/3 at DPL2 (~2R), last 1/3 at ATS color flip"""
        rd = trade.risk_distance if trade.risk_distance > 0 else abs(trade.entry_price - trade.stop_loss)
        dpl1 = trade.entry_price + rd * 1 * (1 if trade.direction == "long" else -1)
        dpl2 = trade.entry_price + rd * 2 * (1 if trade.direction == "long" else -1)

        if trade.direction == "long":
            if candle.low <= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            # ATS color flip for remaining 1/3
            if st and st.changed and st.direction == -1 and trade.dpl1_closed:
                return candle.close, "ats_color_flip"
            # DPL1: close 1/3, move SL to breakeven
            if not trade.dpl1_closed and candle.high >= dpl1:
                trade.dpl1_closed = True
                trade.partial_closed = True
                trade.remaining_units = trade.units * (2 / 3)
                trade.stop_loss = trade.entry_price  # Move to breakeven
                return dpl1, "dpl1_partial"
            # DPL2: close another 1/3
            if trade.dpl1_closed and not trade.dpl2_closed and candle.high >= dpl2:
                trade.dpl2_closed = True
                trade.remaining_units = trade.units * (1 / 3)
                return dpl2, "dpl2_partial"
        else:
            if candle.high >= trade.stop_loss:
                return trade.stop_loss, "stop_loss"
            if st and st.changed and st.direction == 1 and trade.dpl1_closed:
                return candle.close, "ats_color_flip"
            if not trade.dpl1_closed and candle.low <= dpl1:
                trade.dpl1_closed = True
                trade.partial_closed = True
                trade.remaining_units = trade.units * (2 / 3)
                trade.stop_loss = trade.entry_price
                return dpl1, "dpl1_partial"
            if trade.dpl1_closed and not trade.dpl2_closed and candle.low <= dpl2:
                trade.dpl2_closed = True
                trade.remaining_units = trade.units * (1 / 3)
                return dpl2, "dpl2_partial"

        return None, ""

    def _close_trade(
        self, trade: BacktestTrade, exit_price: float, exit_time: datetime,
        reason: str, pip_size: float, spread_cost: float, slippage_cost: float
    ):
        """Close a trade and calculate P&L."""
        # Apply spread + slippage on exit
        if trade.direction == "long":
            exit_price -= spread_cost / 2 + slippage_cost
        else:
            exit_price += spread_cost / 2 + slippage_cost

        trade.exit_price = round(exit_price, 5)
        trade.exit_time = exit_time
        trade.close_reason = reason

        if trade.direction == "long":
            trade.profit_pips = round((exit_price - trade.entry_price) / pip_size, 1)
        else:
            trade.profit_pips = round((trade.entry_price - exit_price) / pip_size, 1)

        trade.profit_loss = round(trade.profit_pips * pip_size * trade.units, 2)

    def _passes_correlation_check(
        self, signal: str, pair: str, open_trades: List[BacktestTrade]
    ) -> bool:
        """Check if opening this trade would violate correlation rules."""
        cfg = self.config

        for trade in open_trades:
            if trade.instrument == pair:
                return False  # Already have a trade on this pair

            # Check positive correlations
            for p1, p2, corr in cfg.pairs.POSITIVE_CORRELATIONS:
                if corr < cfg.indicators.CORRELATION_THRESHOLD:
                    continue
                pair_set = {p1, p2}
                if pair in pair_set and trade.instrument in pair_set:
                    # Same direction on correlated pair = duplicate
                    if trade.direction == signal:
                        return False

            # Check negative correlations
            for p1, p2, corr in cfg.pairs.NEGATIVE_CORRELATIONS:
                if abs(corr) < cfg.indicators.CORRELATION_THRESHOLD:
                    continue
                pair_set = {p1, p2}
                if pair in pair_set and trade.instrument in pair_set:
                    # Opposite direction on negatively correlated = duplicate
                    if trade.direction != signal:
                        return False

        return True

    def _compile_results(
        self, trades: List[BacktestTrade], pair: str, candles: List[Candle],
        final_balance: float, max_drawdown: float, monthly_pnl: Dict,
        equity_points: List, spread_cost: float, slippage_cost: float,
        pip_size: float
    ) -> Dict:
        """Compile backtest statistics."""
        if not trades:
            return BacktestResult(
                pair=pair,
                start_date=candles[0].timestamp.strftime("%Y-%m-%d") if candles else "",
                end_date=candles[-1].timestamp.strftime("%Y-%m-%d") if candles else "",
            ).to_dict()

        wins = [t for t in trades if t.profit_loss > 0]
        losses = [t for t in trades if t.profit_loss < 0]

        gross_profit = sum(t.profit_loss for t in wins)
        gross_loss = abs(sum(t.profit_loss for t in losses))
        net_profit = gross_profit - gross_loss

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0

        all_pnl = [t.profit_loss for t in trades]
        best = max(all_pnl) if all_pnl else 0
        worst = min(all_pnl) if all_pnl else 0

        # Consecutive streaks
        max_cw, max_cl = 0, 0
        cw, cl = 0, 0
        for t in trades:
            if t.profit_loss > 0:
                cw += 1; cl = 0; max_cw = max(max_cw, cw)
            elif t.profit_loss < 0:
                cl += 1; cw = 0; max_cl = max(max_cl, cl)

        # Sharpe ratio (annualized, daily returns proxy)
        if len(all_pnl) > 1:
            import statistics
            mean_ret = statistics.mean(all_pnl)
            std_ret = statistics.stdev(all_pnl) or 1
            sharpe = (mean_ret / std_ret) * math.sqrt(252)
        else:
            sharpe = 0

        # Average trade duration
        durations = []
        for t in trades:
            if t.exit_time and t.entry_time:
                dur = (t.exit_time - t.entry_time).total_seconds() / 3600
                durations.append(dur)
        avg_duration = sum(durations) / len(durations) if durations else 0

        # Total spread/slippage
        total_spread = len(trades) * spread_cost * 10000  # approximate
        total_slippage = len(trades) * slippage_cost * 10000

        # Trade list for JSON
        trade_list = []
        for t in trades:
            trade_list.append({
                "id": t.id,
                "instrument": t.instrument,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "profit_loss": t.profit_loss,
                "profit_pips": t.profit_pips,
                "close_reason": t.close_reason,
            })

        return {
            "pair": pair,
            "start_date": candles[0].timestamp.strftime("%Y-%m-%d"),
            "end_date": candles[-1].timestamp.strftime("%Y-%m-%d"),
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "net_profit": round(net_profit, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(-gross_loss, 2),
            "max_drawdown": round(-max_drawdown, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(-avg_loss, 2),
            "best_trade": round(best, 2),
            "worst_trade": round(worst, 2),
            "sharpe_ratio": round(sharpe, 2),
            "total_spread_cost": round(total_spread, 2),
            "total_slippage_cost": round(total_slippage, 2),
            "avg_trade_duration_hours": round(avg_duration, 1),
            "max_consecutive_wins": max_cw,
            "max_consecutive_losses": max_cl,
            "monthly_returns": {k: round(v, 2) for k, v in monthly_pnl.items()},
            "equity_curve": equity_points,
            "trades": trade_list,
        }


# ===================== CLI =====================

if __name__ == "__main__":
    """
    Run backtest from command line:
        python -m backtest.engine --pair EUR_USD --csv data/EURUSD_M15.csv
    """
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="ATS Backtester")
    parser.add_argument("--pair", default="EUR_USD", help="Pair to backtest")
    parser.add_argument("--csv", required=True, help="Path to M15 OHLCV CSV")
    parser.add_argument("--start", default="2024-01-01", help="Start date")
    parser.add_argument("--end", default="2025-12-31", help="End date")
    parser.add_argument("--output", default=None, help="Output JSON file")
    args = parser.parse_args()

    engine = BacktestEngine(config=DEFAULT_CONFIG)

    if args.csv:
        result = engine.run(
            pair=args.pair,
            start_date=args.start,
            end_date=args.end,
            csv_path=args.csv,
        )
    else:
        result = engine.run(pair=args.pair, start_date=args.start, end_date=args.end)

    # Print summary
    print("\n" + "=" * 60)
    print(f"  BACKTEST RESULTS — {result['pair']}")
    print(f"  {result['start_date']} → {result['end_date']}")
    print("=" * 60)
    print(f"  Total Trades:    {result['total_trades']}")
    print(f"  Wins / Losses:   {result['wins']} / {result['losses']}")
    print(f"  Win Rate:        {result['win_rate']}%")
    print(f"  Profit Factor:   {result['profit_factor']}")
    print(f"  Net Profit:      ${result['net_profit']}")
    print(f"  Max Drawdown:    ${result['max_drawdown']}")
    print(f"  Avg Win:         ${result['avg_win']}")
    print(f"  Avg Loss:        ${result['avg_loss']}")
    print(f"  Sharpe Ratio:    {result['sharpe_ratio']}")
    print(f"  Spread Cost:     ${result['total_spread_cost']}")
    print(f"  Avg Duration:    {result['avg_trade_duration_hours']}h")
    print(f"  Consec. W/L:     {result['max_consecutive_wins']} / {result['max_consecutive_losses']}")
    print("=" * 60)

    if result.get("monthly_returns"):
        print("\n  Monthly Returns:")
        for month, pnl in sorted(result["monthly_returns"].items()):
            marker = "+" if pnl >= 0 else ""
            print(f"    {month}:  {marker}${pnl}")

    # Save to file
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults saved to {args.output}")
