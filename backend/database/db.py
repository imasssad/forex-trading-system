"""
SQLite Database Layer
Stores trades, signals, activity logs, and settings.
Single-user — no auth needed.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("ATS_DB_PATH", "data/ats_trading.db")

_SCHEMA = """
-- Signals received from TradingView webhooks
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    instrument  TEXT NOT NULL,
    action      TEXT NOT NULL,
    timeframe   TEXT,
    rsi_value   REAL,
    autotrend   TEXT,
    htf_trend   TEXT,
    price       REAL,
    atr_value   REAL,
    approved    INTEGER NOT NULL DEFAULT 0,
    reject_reason TEXT,
    raw_json    TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    oanda_trade_id  TEXT,
    instrument      TEXT NOT NULL,
    direction       TEXT NOT NULL,
    units           REAL NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL,
    stop_loss       REAL,
    take_profit     REAL,
    trailing_stop   REAL,
    open_time       TEXT NOT NULL DEFAULT (datetime('now')),
    close_time      TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    profit_loss     REAL,
    profit_pips     REAL,
    close_reason    TEXT,
    signal_id       INTEGER REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    level       TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL,
    details     TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_snapshots (
    date        TEXT PRIMARY KEY,
    balance     REAL NOT NULL,
    equity      REAL NOT NULL,
    trades      INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    losses      INTEGER NOT NULL DEFAULT 0,
    pnl         REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_time        TEXT NOT NULL DEFAULT (datetime('now')),
    config_json     TEXT NOT NULL,
    pair            TEXT,
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    total_trades    INTEGER,
    wins            INTEGER,
    losses          INTEGER,
    win_rate        REAL,
    profit_factor   REAL,
    net_profit      REAL,
    max_drawdown    REAL,
    avg_win         REAL,
    avg_loss        REAL,
    sharpe_ratio    REAL,
    trades_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument);
CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_snapshots(date);
"""


_initialized = False

@contextmanager
def get_db():
    """Context manager for database connections."""
    global _initialized
    if not _initialized:
        _do_init()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _do_init():
    """Raw init without get_db to avoid recursion."""
    global _initialized
    _initialized = True
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def init_db():
    """Create all tables."""
    _do_init()


# ===================== SIGNALS =====================

def insert_signal(
    instrument: str, action: str, timeframe: str = None,
    rsi_value: float = None, autotrend: str = None, htf_trend: str = None,
    price: float = None, atr_value: float = None, approved: bool = False,
    reject_reason: str = None, raw_json: dict = None
) -> int:
    """Insert a received signal. Returns signal id."""
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO signals
                (instrument, action, timeframe, rsi_value, autotrend, htf_trend,
                 price, atr_value, approved, reject_reason, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            instrument, action, timeframe, rsi_value, autotrend, htf_trend,
            price, atr_value, int(approved), reject_reason,
            json.dumps(raw_json) if raw_json else None
        ))
        return cur.lastrowid


def get_signals(limit: int = 50, approved_only: bool = False) -> List[Dict]:
    """Get recent signals."""
    with get_db() as conn:
        q = "SELECT * FROM signals"
        if approved_only:
            q += " WHERE approved = 1"
        q += " ORDER BY id DESC LIMIT ?"
        rows = conn.execute(q, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ===================== TRADES =====================

def insert_trade(
    instrument: str, direction: str, units: float, entry_price: float,
    stop_loss: float = None, take_profit: float = None,
    oanda_trade_id: str = None, signal_id: int = None
) -> int:
    """Insert a new open trade. Returns trade id."""
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO trades
                (instrument, direction, units, entry_price, stop_loss, take_profit,
                 oanda_trade_id, signal_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (instrument, direction, units, entry_price, stop_loss, take_profit,
              oanda_trade_id, signal_id))
        return cur.lastrowid


def close_trade(
    trade_id: int, exit_price: float, profit_loss: float,
    profit_pips: float, close_reason: str
):
    """Close an open trade."""
    with get_db() as conn:
        conn.execute("""
            UPDATE trades SET
                exit_price = ?, profit_loss = ?, profit_pips = ?,
                close_reason = ?, close_time = datetime('now'), status = 'closed'
            WHERE id = ?
        """, (exit_price, profit_loss, profit_pips, close_reason, trade_id))


def get_open_trades() -> List[Dict]:
    """Get all currently open trades."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'open' ORDER BY open_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_virtual_balance() -> float:
    """Get current virtual balance for paper trading."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'virtual_balance'").fetchone()
        return float(row[0]) if row else 10000.0


def update_virtual_balance(new_balance: float):
    """Update virtual balance for paper trading."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('virtual_balance', ?)",
            (str(new_balance),)
        )


def get_all_closed_trades() -> List[Dict]:
    """Get every closed trade (for performance stats)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'closed' ORDER BY close_time ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_trade_history(limit: int = 100, offset: int = 0) -> List[Dict]:
    """Get closed trade history with pagination."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'closed' ORDER BY close_time DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


# ===================== ACTIVITY LOG =====================

def log_activity(level: str, message: str, details: str = None):
    """Insert an activity log entry."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO activity_log (level, message, details) VALUES (?, ?, ?)",
            (level, message, details)
        )


def get_activity_log(limit: int = 100, level: str = None) -> List[Dict]:
    """Get recent activity log entries."""
    with get_db() as conn:
        if level:
            rows = conn.execute(
                "SELECT * FROM activity_log WHERE level = ? ORDER BY id DESC LIMIT ?",
                (level, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# ===================== SETTINGS =====================

def get_setting(key: str, default: str = None) -> Optional[str]:
    """Get a setting value."""
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: Any):
    """Upsert a setting."""
    val_str = json.dumps(value) if not isinstance(value, str) else value
    with get_db() as conn:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, val_str))


def get_all_settings() -> Dict[str, Any]:
    """Get all settings as dict."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = r["value"]
        return result


def save_settings_from_config(config_dict: Dict):
    """Bulk-save settings from a config dictionary."""
    for key, val in config_dict.items():
        set_setting(key, val)


def load_settings_to_config(config):
    """
    Load settings from database and apply to config object.
    Returns the modified config with DB values overriding defaults.
    """
    db_settings = get_all_settings()
    if not db_settings:
        logger.info("No saved settings in database, using defaults")
        return config

    logger.info(f"Loading {len(db_settings)} settings from database")

    # Map DB keys to config attributes
    # Risk settings
    if 'leverage' in db_settings:
        config.risk.LEVERAGE = int(db_settings['leverage'])
    if 'risk_per_trade' in db_settings:
        config.risk.RISK_PER_TRADE_PERCENT = float(db_settings['risk_per_trade'])
    if 'risk_reward_ratio' in db_settings:
        config.risk.RISK_REWARD_RATIO = float(db_settings['risk_reward_ratio'])
    if 'max_open_trades' in db_settings:
        config.risk.MAX_OPEN_TRADES = int(db_settings['max_open_trades'])
    if 'max_consecutive_losses' in db_settings:
        config.risk.MAX_CONSECUTIVE_LOSSES = int(db_settings['max_consecutive_losses'])
    if 'cooldown_hours' in db_settings:
        config.risk.COOLDOWN_HOURS = float(db_settings['cooldown_hours'])
    if 'use_atr_stop' in db_settings:
        config.risk.USE_ATR_STOP = bool(db_settings['use_atr_stop'])
    if 'fixed_stop_pips' in db_settings:
        config.risk.FIXED_STOP_PIPS = float(db_settings['fixed_stop_pips'])
    if 'atr_multiplier' in db_settings:
        config.risk.ATR_MULTIPLIER = float(db_settings['atr_multiplier'])
    if 'trailing_stop_pips' in db_settings:
        config.risk.TRAILING_STOP_PIPS = float(db_settings['trailing_stop_pips'])
    if 'partial_close_percent' in db_settings:
        config.risk.PARTIAL_CLOSE_PERCENT = float(db_settings['partial_close_percent'])

    # News filter settings
    if 'pre_news_minutes' in db_settings:
        config.news.CLOSE_BEFORE_NEWS_MINUTES = int(db_settings['pre_news_minutes'])
    if 'post_news_minutes' in db_settings:
        config.news.AVOID_AFTER_NEWS_MINUTES = int(db_settings['post_news_minutes'])

    # Market hours
    if 'avoid_open_minutes' in db_settings:
        config.hours.MARKET_OPEN_AVOID_MINUTES = int(db_settings['avoid_open_minutes'])

    # Indicator settings
    if 'rsi_period' in db_settings:
        config.indicators.RSI_PERIOD = int(db_settings['rsi_period'])
    if 'rsi_oversold' in db_settings:
        config.indicators.RSI_OVERSOLD = int(db_settings['rsi_oversold'])
    if 'rsi_overbought' in db_settings:
        config.indicators.RSI_OVERBOUGHT = int(db_settings['rsi_overbought'])
    if 'correlation_threshold' in db_settings:
        config.indicators.CORRELATION_THRESHOLD = float(db_settings['correlation_threshold'])

    # Trading pairs
    if 'allowed_pairs' in db_settings:
        pairs = db_settings['allowed_pairs']
        if isinstance(pairs, list):
            config.pairs.ALLOWED_PAIRS = pairs

    # Timeframes
    if 'entry_timeframe' in db_settings:
        from config.settings import TimeFrame
        try:
            config.indicators.ENTRY_TIMEFRAME = TimeFrame(db_settings['entry_timeframe'])
        except ValueError:
            pass
    if 'confirmation_timeframe' in db_settings:
        from config.settings import TimeFrame
        try:
            config.indicators.CONFIRMATION_TIMEFRAME = TimeFrame(db_settings['confirmation_timeframe'])
        except ValueError:
            pass

    # Forward test mode
    if 'paper_trading' in db_settings:
        config.paper_trading = bool(db_settings['paper_trading'])

    # Virtual balance for paper trading
    if 'virtual_balance' in db_settings:
        config.virtual_balance = float(db_settings['virtual_balance'])

    # ATS strategy
    if 'ats_strategy' in db_settings:
        from config.settings import ATSStrategy
        try:
            config.ats_strategy = ATSStrategy(db_settings['ats_strategy'])
        except ValueError:
            pass

    return config


# ===================== DAILY SNAPSHOTS =====================

def save_daily_snapshot(
    date: str, balance: float, equity: float,
    trades: int, wins: int, losses: int, pnl: float
):
    """Save or update today's snapshot."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO daily_snapshots (date, balance, equity, trades, wins, losses, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                balance = excluded.balance, equity = excluded.equity,
                trades = excluded.trades, wins = excluded.wins,
                losses = excluded.losses, pnl = excluded.pnl
        """, (date, balance, equity, trades, wins, losses, pnl))


def get_equity_curve(days: int = 90) -> List[Dict]:
    """Get equity curve data for the last N days."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM daily_snapshots
            ORDER BY date DESC LIMIT ?
        """, (days,)).fetchall()
        return [dict(r) for r in reversed(rows)]


# ===================== BACKTEST RESULTS =====================

def save_backtest_run(
    config_json: str, pair: str, start_date: str, end_date: str,
    total_trades: int, wins: int, losses: int, win_rate: float,
    profit_factor: float, net_profit: float, max_drawdown: float,
    avg_win: float, avg_loss: float, sharpe_ratio: float = None,
    trades_json: str = None
) -> int:
    """Save a backtest result. Returns run id."""
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO backtest_runs
                (config_json, pair, start_date, end_date, total_trades, wins, losses,
                 win_rate, profit_factor, net_profit, max_drawdown, avg_win, avg_loss,
                 sharpe_ratio, trades_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (config_json, pair, start_date, end_date, total_trades, wins, losses,
              win_rate, profit_factor, net_profit, max_drawdown, avg_win, avg_loss,
              sharpe_ratio, trades_json))
        return cur.lastrowid


def get_backtest_runs(limit: int = 20) -> List[Dict]:
    """Get recent backtest runs."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ===================== PERFORMANCE STATS =====================

def calc_performance_stats(days: int = None) -> Dict:
    """
    Calculate performance statistics from closed trades.
    If days is None, use all trades.
    """
    with get_db() as conn:
        if days:
            cutoff = (datetime.now(ZoneInfo("UTC")) - timedelta(days=days)).isoformat()
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='closed' AND close_time >= ? ORDER BY close_time",
                (cutoff,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='closed' ORDER BY close_time"
            ).fetchall()

    trades = [dict(r) for r in rows]
    if not trades:
        return _empty_stats()

    wins = [t for t in trades if (t["profit_loss"] or 0) > 0]
    losses = [t for t in trades if (t["profit_loss"] or 0) < 0]

    total_win = sum(t["profit_loss"] for t in wins)
    total_loss = abs(sum(t["profit_loss"] for t in losses))

    profit_factor = total_win / total_loss if total_loss > 0 else 999.0
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    avg_win = total_win / len(wins) if wins else 0
    avg_loss = total_loss / len(losses) if losses else 0

    # Max drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["profit_loss"] or 0
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Consecutive streaks
    max_consec_wins = 0
    max_consec_losses = 0
    cur_wins = 0
    cur_losses = 0
    for t in trades:
        if (t["profit_loss"] or 0) > 0:
            cur_wins += 1
            cur_losses = 0
            max_consec_wins = max(max_consec_wins, cur_wins)
        elif (t["profit_loss"] or 0) < 0:
            cur_losses += 1
            cur_wins = 0
            max_consec_losses = max(max_consec_losses, cur_losses)
        else:
            cur_wins = 0
            cur_losses = 0

    # Best / worst
    all_pnl = [t["profit_loss"] or 0 for t in trades]
    best_trade = max(all_pnl) if all_pnl else 0
    worst_trade = min(all_pnl) if all_pnl else 0

    # Expectancy
    expectancy = (win_rate / 100) * avg_win - ((100 - win_rate) / 100) * avg_loss

    # Equity curve from trade sequence
    equity_curve = []
    running = 0.0
    for t in trades:
        running += t["profit_loss"] or 0
        equity_curve.append({
            "date": (t.get("close_time") or t.get("open_time", ""))[:10],
            "equity": round(running, 2)
        })

    return {
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "total_profit": round(total_win, 2),
        "total_loss": round(-total_loss, 2),
        "net_profit": round(total_win - total_loss, 2),
        "max_drawdown": round(-max_dd, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(-avg_loss, 2),
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "consecutive_wins": max_consec_wins,
        "consecutive_losses": max_consec_losses,
        "expectancy": round(expectancy, 2),
        "equity_curve": equity_curve,
    }


def _empty_stats() -> Dict:
    return {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "win_rate": 0, "profit_factor": 0, "total_profit": 0,
        "total_loss": 0, "net_profit": 0, "max_drawdown": 0,
        "avg_win": 0, "avg_loss": 0, "best_trade": 0, "worst_trade": 0,
        "consecutive_wins": 0, "consecutive_losses": 0,
        "expectancy": 0, "equity_curve": [],
    }
