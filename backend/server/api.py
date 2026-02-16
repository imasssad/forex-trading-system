"""
ATS Trading Server (FastAPI)
- /webhook           — TradingView alert receiver
- /api/dashboard/*   — Dashboard REST endpoints
- /api/news/*        — ForexFactory calendar feed
- /api/settings/*    — Configuration CRUD
- /api/backtest/*    — Backtest trigger & results
"""

import os
import sys
import json
import asyncio
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
import logging
import copy
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from starlette.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Ensure parent package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rule_engine import TradingRuleEngine, TradingSignal, SignalType
from core.correlation_filter import OpenPosition, TradeDirection
from core.state_manager import TradeStateManager
from core.signal_generator import SignalGenerator
from core.signal_providers import signal_aggregator, ExternalSignal
from news.forex_factory import NewsFilter as FFNewsFilter
from news.investing_com import InvestingNewsFetcher
from config.settings import DEFAULT_CONFIG, TradingConfig
from database import db as database
from brokers.oanda import OandaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("ats")

# ===================== GLOBALS =====================


rule_engine: Optional[TradingRuleEngine] = None
news_filter: Optional[FFNewsFilter] = None
investing_news: Optional[InvestingNewsFetcher] = None
signal_generator: Optional[SignalGenerator] = None
signal_task: Optional[asyncio.Task] = None
external_signals_task: Optional[asyncio.Task] = None
state_manager: Optional[TradeStateManager] = None
BOT_START_TIME: Optional[datetime] = None
oanda_client: Optional[OandaClient] = None
config: TradingConfig = DEFAULT_CONFIG  # Will be loaded from DB on startup


# ===================== TRADE SYNC =====================

async def sync_trades_with_oanda(client: OandaClient) -> int:
    """
    Compare local open trades with actual OANDA trades.
    Close any trades that exist locally but not on OANDA (failed executions).
    Returns count of orphaned trades closed.
    """
    try:
        # Get actual OANDA trades
        oanda_trades = client.get_open_trades()
        oanda_trade_ids = {trade.id for trade in oanda_trades}
        
        # Get local open trades
        local_trades = database.get_open_trades()
        
        orphaned_count = 0
        
        for local_trade in local_trades:
            trade_id = local_trade['id']
            oanda_id = local_trade.get('oanda_trade_id')
            
            # Check if this local trade exists on OANDA
            if oanda_id and oanda_id in oanda_trade_ids:
                # Trade is synced
                continue
            else:
                # Orphaned trade - exists locally but not on OANDA
                orphaned_count += 1
                logger.warning(f"Orphaned trade #{trade_id} ({local_trade['instrument']} {local_trade['direction'].upper()}) - closing as FAILED")
                
                # Close this orphaned trade
                database.close_trade(
                    trade_id=trade_id,
                    exit_price=local_trade['entry_price'],
                    profit_loss=0.0,
                    profit_pips=0.0,
                    close_reason="EXECUTION_FAILED - Trade never opened on OANDA"
                )
        
        return orphaned_count
    except Exception as e:
        logger.error(f"Trade sync error: {e}")
        return 0


# ===================== LIFESPAN =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown."""
    global rule_engine, news_filter, investing_news, signal_generator, signal_task, external_signals_task, state_manager, BOT_START_TIME, config, oanda_client

    # Init database
    database.init_db()
    database.log_activity("info", "Server starting up")

    # Load settings from database (overrides defaults)
    config = database.load_settings_to_config(DEFAULT_CONFIG)
    database.log_activity("info", "Settings loaded from database")

    # Init components with loaded config
    os.makedirs("data", exist_ok=True)

    rule_engine = TradingRuleEngine(
        config=config,
        state_file="data/trading_state.json",
        history_file="data/trade_history.json",
    )
    news_filter = FFNewsFilter(
        pre_news_minutes=config.news.CLOSE_BEFORE_NEWS_MINUTES,
        post_news_minutes=config.news.AVOID_AFTER_NEWS_MINUTES,
        cache_file="data/news_cache.json",
    )
    investing_news = InvestingNewsFetcher(cache_file="data/investing_news_cache.json")
    state_manager = TradeStateManager(
        max_consecutive_losses=config.risk.MAX_CONSECUTIVE_LOSSES,
        cooldown_hours=config.risk.COOLDOWN_HOURS,
        state_file="data/trading_state.json",
        history_file="data/trade_history.json",
    )
    BOT_START_TIME = datetime.now(ZoneInfo("UTC"))

    # Init OANDA client
    try:
        oanda_client = OandaClient(practice=True)
        summary = oanda_client.get_account_summary()
        logger.info(f"OANDA connected: balance=${float(summary.get('balance', 0)):.2f}")
        database.log_activity("info", f"OANDA connected: {oanda_client.account_id}")
        
        # Sync local trades with OANDA on startup
        try:
            orphaned = await sync_trades_with_oanda(oanda_client)
            if orphaned > 0:
                logger.warning(f"Closed {orphaned} orphaned trades that failed to execute on OANDA")
                database.log_activity("info", f"Trade sync: closed {orphaned} orphaned trades")
        except Exception as sync_error:
            logger.error(f"Trade sync failed: {sync_error}")
    except Exception as e:
        logger.warning(f"OANDA client init failed: {e}")
        oanda_client = None

    # Init signal generator
    if oanda_client:
        signal_generator = SignalGenerator(config, oanda_client)
        logger.info("Signal generator initialized")

        # Start automatic signal generation
        signal_task = asyncio.create_task(signal_generator.run_signal_generation())
        logger.info("Automatic signal generation started")
    else:
        logger.warning("Signal generator not initialized - no OANDA client")

    # Initial external signals fetch
    try:
        external_signals = signal_aggregator.fetch_all_signals()
        logger.info(f"Fetched {len(external_signals)} external signals on startup")
    except Exception as e:
        logger.warning(f"Initial external signals fetch failed: {e}")

    # Start automatic external signals fetching
    async def fetch_external_signals_loop():
        """Automatically fetch external signals every 5 minutes"""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                signals = signal_aggregator.fetch_all_signals()
                if signals:
                    logger.info(f"Auto-fetched {len(signals)} external signals")
            except Exception as e:
                logger.error(f"Auto external signals fetch error: {e}")
                await asyncio.sleep(60)

    external_signals_task = asyncio.create_task(fetch_external_signals_loop())
    logger.info("Automatic external signals fetching started")

    # Initial news fetch
    try:
        news_filter.refresh(force=True)
        count = len(news_filter.events)
        database.log_activity("info", f"News data loaded: {count} events")
    except Exception as e:
        database.log_activity("warn", f"News fetch failed on startup: {e}")

    logger.info("ATS server ready")
    yield
    # Cleanup tasks
    if signal_task and not signal_task.done():
        signal_task.cancel()
        try:
            await signal_task
        except asyncio.CancelledError:
            pass
    if external_signals_task and not external_signals_task.done():
        external_signals_task.cancel()
        try:
            await external_signals_task
        except asyncio.CancelledError:
            pass
    database.log_activity("info", "Server shutting down")


# ===================== APP =====================

app = FastAPI(title="ATS Trading System", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== PYDANTIC MODELS =====================

class WebhookPayload(BaseModel):
    symbol: str
    action: str
    timeframe: str = "15"
    rsi: float = 50
    autotrend: str = "neutral"
    htf_trend: str = "neutral"
    price: float = 0
    atr: Optional[float] = None


class CloseTradeRequest(BaseModel):
    trade_id: Union[str, int]  # Database ID (int) or OANDA trade ID (string)
    exit_price: float = 0
    profit_loss: float = 0
    profit_pips: float = 0
    close_reason: str = "manual"


class ModifyTradeRequest(BaseModel):
    trade_id: Union[str, int]  # Database ID (int) or OANDA trade ID (string)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pips: Optional[float] = None


class SettingsUpdate(BaseModel):
    leverage: Optional[int] = None
    risk_per_trade: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    max_open_trades: Optional[int] = None
    max_consecutive_losses: Optional[int] = None
    cooldown_hours: Optional[float] = None
    use_atr_stop: Optional[bool] = None
    fixed_stop_pips: Optional[float] = None
    atr_multiplier: Optional[float] = None
    trailing_stop_pips: Optional[float] = None
    partial_close_percent: Optional[float] = None
    pre_news_minutes: Optional[int] = None
    post_news_minutes: Optional[int] = None
    avoid_open_minutes: Optional[int] = None
    entry_timeframe: Optional[str] = None
    confirmation_timeframe: Optional[str] = None
    allowed_pairs: Optional[List[str]] = None
    # RSI & correlation settings
    rsi_period: Optional[int] = None
    rsi_oversold: Optional[int] = None
    rsi_overbought: Optional[int] = None
    correlation_threshold: Optional[float] = None
    # ATS strategy
    ats_strategy: Optional[str] = None
    # Forward test mode
    paper_trading: Optional[bool] = None
    # Virtual balance for paper trading
    virtual_balance: Optional[float] = None


# ===================== HELPERS =====================

def _parse_signal(data: WebhookPayload) -> TradingSignal:
    """Convert webhook payload → TradingSignal."""
    symbol = data.symbol.upper()
    if len(symbol) == 6:
        instrument = f"{symbol[:3]}_{symbol[3:]}"
    else:
        instrument = symbol.replace("/", "_")

    action = data.action.lower()
    if action == "buy":
        sig = SignalType.BUY
    elif action == "sell":
        sig = SignalType.SELL
    else:
        sig = SignalType.NEUTRAL

    tf = data.timeframe
    entry_tf = f"M{tf}" if tf.isdigit() else tf

    return TradingSignal(
        instrument=instrument,
        signal_type=sig,
        timestamp=datetime.now(ZoneInfo("UTC")).isoformat(),
        entry_timeframe=entry_tf,
        rsi_value=data.rsi,
        autotrend_direction=data.autotrend.lower(),
        htf_trend=data.htf_trend.lower(),
        entry_price=data.price,
        atr_value=data.atr,
    )


def _get_open_positions_for_rules() -> List[OpenPosition]:
    """Build OpenPosition list from database open trades."""
    db_trades = database.get_open_trades()
    positions = []
    for t in db_trades:
        positions.append(OpenPosition(
            pair=t["instrument"],
            direction=TradeDirection.LONG if t["direction"] == "long" else TradeDirection.SHORT,
            entry_price=t["entry_price"],
            entry_time=t["open_time"],
            size=abs(t["units"]),
        ))
    return positions


def _build_system_status() -> Dict:
    """Build complete system status for the dashboard."""
    now = datetime.now(ZoneInfo("UTC"))
    uptime = (now - BOT_START_TIME).total_seconds() / 3600 if BOT_START_TIME else 0

    # Handle case where state_manager hasn't initialized yet
    if state_manager is None:
        return {
            "bot_running": False, "uptime_hours": 0,
            "last_signal_time": None, "last_signal_pair": None,
            "last_signal_type": None, "can_trade": False,
            "can_trade_reason": "State manager not initialized",
            "active_sessions": [], "consecutive_losses": 0,
            "cooldown_until": None,
            "daily_stats": {"trades_today": 0, "wins_today": 0, "losses_today": 0, "pnl_today": 0},
        }

    can_trade, cant_reason = state_manager.can_trade()
    in_cooldown, cooldown_info = state_manager.is_in_cooldown()

    daily = state_manager.get_daily_stats()

    # Active sessions
    from core.market_hours import MarketHoursFilter
    mh = MarketHoursFilter()
    active_sessions = [s.value for s in mh.get_active_sessions(now)]

    # Last signal from DB
    recent_signals = database.get_signals(limit=1)
    last_signal = recent_signals[0] if recent_signals else None

    return {
        "bot_running": True,
        "paper_trading": config.paper_trading,
        "uptime_hours": round(uptime, 1),
        "uptime_seconds": int((now - BOT_START_TIME).total_seconds()) if BOT_START_TIME else 0,
        "signal_generation_running": signal_task is not None and not signal_task.done(),
        "external_signals_running": external_signals_task is not None and not external_signals_task.done(),
        "last_signal_time": last_signal["timestamp"] if last_signal else None,
        "last_signal_pair": last_signal["instrument"] if last_signal else None,
        "last_signal_type": last_signal["action"] if last_signal else None,
        "can_trade": can_trade,
        "can_trade_reason": cant_reason or "OK",
        "active_sessions": active_sessions,
        "consecutive_losses": state_manager.get_consecutive_losses(),
        "cooldown_until": state_manager.state.cooldown_until,
        "daily_stats": {
            "trades_today": daily["total_trades"],
            "wins_today": daily["wins"],
            "losses_today": daily["losses"],
            "pnl_today": daily["pnl"],
        },
    }


# ===================== WEBHOOK =====================

@app.post("/webhook")
async def webhook(payload: WebhookPayload):
    """
    TradingView alert webhook.
    Receives signal → evaluates rules → logs to DB → executes if approved.
    """
    logger.info(f"Webhook: {payload.action} {payload.symbol}")

    signal = _parse_signal(payload)

    # Log signal to DB
    open_positions = _get_open_positions_for_rules()
    decision = rule_engine.evaluate_signal(signal, open_positions)

    reject_reason = None
    if not decision.should_trade and decision.checks_failed:
        reject_reason = "; ".join(
            f"{c.rule_name}: {c.reason}" for c in decision.checks_failed
        )

    sig_id = database.insert_signal(
        instrument=signal.instrument,
        action=signal.signal_type.value,
        timeframe=signal.entry_timeframe,
        rsi_value=signal.rsi_value,
        autotrend=signal.autotrend_direction,
        htf_trend=signal.htf_trend,
        price=signal.entry_price,
        atr_value=signal.atr_value,
        approved=decision.should_trade,
        reject_reason=reject_reason,
        raw_json=payload.model_dump(),
    )

    if decision.should_trade:
        direction = "long" if signal.signal_type == SignalType.BUY else "short"
        units = decision.position_size

        # Execute on OANDA if not in paper trading mode
        oanda_trade_id = None
        if not config.paper_trading and oanda_client:
            try:
                oanda_result = oanda_client.place_market_order(
                    instrument=signal.instrument,
                    units=units if direction == "long" else -units,
                    stop_loss_price=decision.stop_loss,
                    take_profit_price=decision.take_profit,
                )
                oanda_trade_id = oanda_result.get("id")
                database.log_activity(
                    "trade",
                    f"LIVE {'BUY' if direction == 'long' else 'SELL'} "
                    f"{signal.instrument} @ {signal.entry_price}",
                    f"OANDA Trade #{oanda_trade_id} | SL: {decision.stop_loss} | TP: {decision.take_profit}",
                )
            except Exception as e:
                logger.error(f"OANDA execution failed: {e}")
                database.log_activity("error", f"OANDA execution failed: {e}")
        else:
            mode = "PAPER" if config.paper_trading else "NO BROKER"
            database.log_activity(
                "trade",
                f"[{mode}] {'BUY' if direction == 'long' else 'SELL'} "
                f"{signal.instrument} @ {signal.entry_price}",
                f"SL: {decision.stop_loss} | TP: {decision.take_profit} | Signal #{sig_id}",
            )

        # Insert trade into DB
        trade_id = database.insert_trade(
            instrument=signal.instrument,
            direction=direction,
            units=units,
            entry_price=signal.entry_price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            signal_id=sig_id,
        )

        database.log_activity(
            "info",
            f"Signal APPROVED: {signal.signal_type.value} {signal.instrument}",
            f"{'LIVE' if not config.paper_trading else 'PAPER'} mode | "
            f"All {len(decision.checks_passed)} rule checks passed. Trade #{trade_id}",
        )
    else:
        database.log_activity(
            "info",
            f"Signal REJECTED: {signal.signal_type.value} {signal.instrument}",
            reject_reason,
        )

    return {
        "signal_id": sig_id,
        "approved": decision.should_trade,
        "checks_passed": [c.rule_name for c in decision.checks_passed],
        "checks_failed": [
            {"rule": c.rule_name, "reason": c.reason}
            for c in decision.checks_failed
        ],
    }


# ===================== DASHBOARD API =====================

@app.get("/api/account")
async def api_account():
    """Account summary from OANDA or virtual balance for paper trading."""
    if config.paper_trading:
        # Return virtual balance for paper trading
        virtual_balance = database.get_virtual_balance()
        open_trades = database.get_open_trades()
        
        # Calculate unrealized P&L from open trades
        unrealized_pl = 0.0
        margin_used = 0.0
        
        for trade in open_trades:
            # For paper trading, we don't have real P&L, so we'll estimate based on position
            # In a real implementation, you'd need current market prices
            margin_used += abs(trade['units']) * trade['entry_price'] * 0.01  # Rough margin estimate
        
        return {
            "balance": virtual_balance,
            "nav": virtual_balance + unrealized_pl,
            "unrealized_pl": unrealized_pl,
            "margin_used": margin_used,
            "margin_available": virtual_balance - margin_used,
            "open_trade_count": len(open_trades),
        }
    else:
        # Live trading - get real OANDA data
        if oanda_client is None:
            raise HTTPException(status_code=503, detail="OANDA not connected")
        try:
            summary = oanda_client.get_account_summary()
            return {
                "balance": float(summary.get("balance", 0)),
                "nav": float(summary.get("NAV", 0)),
                "unrealized_pl": float(summary.get("unrealizedPL", 0)),
                "margin_used": float(summary.get("marginUsed", 0)),
                "margin_available": float(summary.get("marginAvailable", 0)),
                "open_trade_count": int(summary.get("openTradeCount", 0)),
            }
        except Exception as e:
            logger.error(f"Failed to fetch OANDA account: {e}")
            raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/status")
async def api_status():
    """System status for the top bar."""
    return _build_system_status()


@app.get("/api/trades/open")
async def api_open_trades():
    """Open positions — live from OANDA when available, else from DB."""
    if oanda_client and not config.paper_trading:
        try:
            oanda_trades = oanda_client.get_open_trades()
            if oanda_trades:  # Only return OANDA trades if there are any
                trades = []
                for t in oanda_trades:
                    direction = "long" if t.units > 0 else "short"
                    trades.append({
                        "id": t.id,
                        "instrument": t.instrument,
                        "units": t.units,
                        "price": t.price,
                        "current_price": t.price,  # OANDA unrealizedPL is more accurate
                        "unrealized_pl": t.unrealized_pl,
                        "stop_loss": t.stop_loss,
                        "take_profit": t.take_profit,
                        "trailing_stop": t.trailing_stop_distance,
                        "open_time": t.open_time,
                        "direction": direction,
                    })
                return {"count": len(trades), "trades": trades}
        except Exception as e:
            logger.warning(f"OANDA trades fetch failed, falling back to DB: {e}")
    
    # Fall back to database trades (for paper mode or when OANDA has no trades)
    trades = database.get_open_trades()
    return {"count": len(trades), "trades": trades}


@app.get("/api/trades/history")
async def api_trade_history(limit: int = 100, offset: int = 0):
    """Closed trade history."""
    trades = database.get_trade_history(limit=limit, offset=offset)
    return {"count": len(trades), "trades": trades}


@app.post("/api/trades/close")
async def api_close_trade(req: CloseTradeRequest):
    """Manually close a trade on OANDA and update DB."""
    # Accept trade_id as string or int
    trade_id = req.trade_id
    if isinstance(trade_id, str):
        if trade_id.isdigit():
            trade_id = int(trade_id)
        else:
            # Try to find trade by oanda_trade_id
            open_trades = database.get_open_trades()
            found = next((t for t in open_trades if str(t.get('oanda_trade_id')) == trade_id), None)
            if found:
                trade_id = found['id']
            else:
                logger.error(f"Trade ID {trade_id} not found.")
                raise HTTPException(status_code=404, detail="Trade not found.")

    # Check if trade exists in database and get its details
    open_trades = database.get_open_trades()
    trade = next((t for t in open_trades if t['id'] == trade_id), None)
    if not trade:
        logger.error(f"Trade {trade_id} not found or already closed.")
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found or already closed.")

    # Close on OANDA only if trade has an OANDA ID and we're not in paper trading mode
    oanda_trade_id = trade.get('oanda_trade_id')
    if oanda_client and not config.paper_trading and oanda_trade_id:
        try:
            result = oanda_client.close_trade(trade_id=oanda_trade_id)
            fill_price = float(result.get("price", req.exit_price))
            realized_pl = float(result.get("pl", req.profit_loss))
            database.log_activity(
                "trade",
                f"LIVE CLOSE Trade #{trade_id} (OANDA #{oanda_trade_id})",
                f"Fill: {fill_price} | P/L: ${realized_pl:.2f}",
            )
        except Exception as e:
            logger.error(f"OANDA close failed for trade {trade_id}: {e}")
            database.log_activity("error", f"OANDA close failed: {e}")
            raise HTTPException(status_code=502, detail=f"OANDA close failed: {e}")
    else:
        mode = "PAPER" if config.paper_trading else "NO BROKER"
        database.log_activity(
            "trade",
            f"[{mode}] CLOSE Trade #{trade_id}",
            f"Exit: {req.exit_price} | P/L: {req.profit_loss}",
        )

    # Update local DB
    try:

        database.close_trade(
            trade_id=trade_id,
            exit_price=req.exit_price,
            profit_loss=req.profit_loss,
            profit_pips=req.profit_pips,
            close_reason=req.close_reason,
        )

        # Return margin to virtual balance in paper trading mode
        if config.paper_trading:
            closed_trade = next((t for t in database.get_trade_history(limit=10) if t['id'] == trade_id), None)
            if closed_trade:
                margin_returned = abs(closed_trade['units']) * closed_trade['entry_price'] * 0.01
                current_balance = database.get_virtual_balance()
                new_balance = current_balance + margin_returned
                database.update_virtual_balance(new_balance)
                logger.info(f"Paper trade closed: returned ${margin_returned:.2f} margin, balance now ${new_balance:.2f}")
            else:
                logger.warning(f"Closed trade {trade_id} not found in history for margin update.")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"DB close failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database close failed: {e}")

    return {"success": True}


@app.post("/api/trades/close-all")
async def api_close_all_trades():
    """Emergency close all open positions - both OANDA and database trades."""
    open_trades = database.get_open_trades()
    
    if not open_trades:
        return {"success": True, "closed": 0, "message": "No open trades to close"}
    
    closed_count = 0
    errors = []
    
    for trade in open_trades:
        try:
            trade_id = trade['id']
            oanda_trade_id = trade.get('oanda_trade_id')
            
            # Close on OANDA if trade has OANDA ID and we're not in paper mode
            if oanda_client and not config.paper_trading and oanda_trade_id:
                try:
                    oanda_client.close_trade(trade_id=oanda_trade_id)
                    logger.info(f"Closed OANDA trade {oanda_trade_id} (DB ID: {trade_id})")
                except Exception as e:
                    logger.error(f"Failed to close OANDA trade {oanda_trade_id}: {e}")
                    errors.append(f"Trade {trade_id}: {str(e)}")
            
            # Close in database
            database.close_trade(
                trade_id=trade_id,
                exit_price=trade['entry_price'],  # Use entry price as exit for emergency close
                profit_loss=0,
                profit_pips=0,
                close_reason="manual_close_all"
            )
            
            # Return margin for paper trading
            if config.paper_trading and trade.get('units'):
                margin_returned = abs(trade['units']) * trade['entry_price'] * 0.01
                current_balance = database.get_virtual_balance()
                database.update_virtual_balance(current_balance + margin_returned)
            
            closed_count += 1
            
        except Exception as e:
            logger.error(f"Failed to close trade {trade.get('id')}: {e}")
            errors.append(f"Trade {trade.get('id')}: {str(e)}")
    
    database.log_activity(
        "trade",
        f"CLOSE ALL — {closed_count} positions closed",
        f"Errors: {len(errors)}" if errors else "All closed successfully"
    )
    
    return {
        "success": True,
        "closed": closed_count,
        "errors": errors if errors else None
    }


@app.post("/api/trades/modify")
async def api_modify_trade(req: ModifyTradeRequest):
    """Modify stop loss, take profit, or trailing stop on OANDA."""
    if oanda_client and not config.paper_trading:
        try:
            result = oanda_client.modify_trade(
                trade_id=req.trade_id,
                stop_loss_price=req.stop_loss,
                take_profit_price=req.take_profit,
                trailing_stop_pips=req.trailing_stop_pips,
            )
            changes = []
            if req.stop_loss is not None:
                changes.append(f"SL={req.stop_loss}")
            if req.take_profit is not None:
                changes.append(f"TP={req.take_profit}")
            if req.trailing_stop_pips is not None:
                changes.append(f"Trail={req.trailing_stop_pips}pip")
            database.log_activity(
                "info",
                f"Trade #{req.trade_id} modified: {', '.join(changes)}",
            )
            return {"success": True, "updated": result}
        except Exception as e:
            logger.error(f"Modify trade failed: {e}")
            raise HTTPException(status_code=502, detail=str(e))
    else:
        return {"success": True, "mode": "paper"}


@app.post("/api/trades/sync")
async def api_sync_trades():
    """
    Sync local trades with OANDA.
    Closes any orphaned trades that exist locally but not on OANDA.
    """
    if not oanda_client:
        raise HTTPException(status_code=503, detail="OANDA client not available")
    
    try:
        orphaned_count = await sync_trades_with_oanda(oanda_client)
        message = f"Synced trades with OANDA"
        if orphaned_count > 0:
            message += f" - closed {orphaned_count} orphaned trade(s)"
            database.log_activity("info", f"Manual trade sync: closed {orphaned_count} orphaned trades")
        
        return {
            "success": True,
            "orphaned_closed": orphaned_count,
            "message": message
        }
    except Exception as e:
        logger.error(f"Trade sync failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/trades/import-history")
async def api_import_closed_trades(count: int = 500):
    """
    Import closed trades from OANDA transaction history into database.
    Useful for populating trade history from past trades.
    """
    if not oanda_client:
        raise HTTPException(status_code=503, detail="OANDA client not available")
    
    try:
        # Get closed trades from OANDA
        closed_trades = oanda_client.get_closed_trades(count=count)
        
        if not closed_trades:
            return {
                "success": True,
                "imported": 0,
                "message": "No closed trades found in OANDA history"
            }
        
        # Get existing trade IDs from database to avoid duplicates
        existing_oanda_ids = set()
        with database.get_db() as conn:
            rows = conn.execute("SELECT oanda_trade_id FROM trades WHERE oanda_trade_id IS NOT NULL").fetchall()
            existing_oanda_ids = {row[0] for row in rows}
        
        imported = 0
        for trade in closed_trades:
            oanda_id = trade["id"]
            
            # Skip if already in database
            if oanda_id in existing_oanda_ids:
                continue
            
            # Calculate profit in pips
            instrument = trade["instrument"]
            pip_size = oanda_client.PIP_SIZES.get(instrument, 0.0001)
            price_diff = trade["exit_price"] - trade["entry_price"]
            if trade["direction"] == "short":
                price_diff = -price_diff
            profit_pips = price_diff / pip_size
            
            # Insert into database
            with database.get_db() as conn:
                conn.execute("""
                    INSERT INTO trades 
                        (oanda_trade_id, instrument, direction, units, entry_price, exit_price,
                         profit_loss, profit_pips, close_reason, status, open_time, close_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?, ?)
                """, (
                    oanda_id,
                    instrument,
                    trade["direction"],
                    trade["units"],
                    trade["entry_price"],
                    trade["exit_price"],
                    trade["profit_loss"],
                    profit_pips,
                    trade.get("close_reason", "UNKNOWN"),
                    trade["open_time"],
                    trade["close_time"]
                ))
            
            imported += 1
        
        message = f"Imported {imported} closed trade(s) from OANDA"
        database.log_activity("info", message)
        logger.info(message)
        
        return {
            "success": True,
            "imported": imported,
            "total_found": len(closed_trades),
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Import closed trades failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/performance")
async def api_performance(days: int = None):
    """Performance stats + equity curve."""
    return database.calc_performance_stats(days=days)


@app.get("/api/signals")
async def api_signals(limit: int = 50, approved_only: bool = False):
    """Recent signals."""
    signals = database.get_signals(limit=limit, approved_only=approved_only)
    return {"count": len(signals), "signals": signals}


@app.post("/api/signals/start-generation")
async def start_signal_generation():
    """Start autonomous signal generation."""
    global signal_generator, signal_task

    if signal_generator is None:
        raise HTTPException(status_code=400, detail="Signal generator not initialized")

    if signal_task and not signal_task.done():
        return {"status": "already_running"}

    signal_task = asyncio.create_task(signal_generator.run_signal_generation())
    database.log_activity("info", "Signal generation started")
    return {"status": "started"}


@app.post("/api/signals/stop-generation")
async def stop_signal_generation():
    """Stop autonomous signal generation."""
    global signal_task

    if signal_task and not signal_task.done():
        signal_task.cancel()
        try:
            await signal_task
        except asyncio.CancelledError:
            pass
        database.log_activity("info", "Signal generation stopped")
        return {"status": "stopped"}

    return {"status": "not_running"}


@app.get("/api/external-signals")
async def api_external_signals(min_confidence: float = 0.5, instruments: str = None):
    """Get external signals from various providers."""
    try:
        # Parse instruments parameter
        instrument_list = None
        if instruments:
            instrument_list = [inst.strip() for inst in instruments.split(',')]

        signals = signal_aggregator.get_filtered_signals(
            min_confidence=min_confidence,
            instruments=instrument_list
        )

        return {
            "count": len(signals),
            "signals": [
                {
                    "provider": s.provider,
                    "instrument": s.instrument,
                    "action": s.action,
                    "price": s.price,
                    "timestamp": s.timestamp,
                    "confidence": s.confidence,
                    "timeframe": s.timeframe,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "metadata": s.metadata
                }
                for s in signals
            ]
        }
    except Exception as e:
        logger.error(f"External signals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/external-signals/fetch")
async def fetch_external_signals():
    """Fetch fresh signals from all providers."""
    try:
        signals = signal_aggregator.fetch_all_signals()
        stats = signal_aggregator.get_provider_stats()

        # Log to database
        database.log_activity("info", f"Fetched {len(signals)} external signals from {len(stats)} providers")

        return {
            "status": "fetched",
            "total_signals": len(signals),
            "provider_stats": stats,
            "last_update": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Fetch external signals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/external-signals/import")
async def import_external_signals(provider: str = None, min_confidence: float = 0.7):
    """Import external signals into the main signal database."""
    try:
        signals = signal_aggregator.get_filtered_signals(min_confidence=min_confidence)

        if provider:
            signals = [s for s in signals if s.provider == provider]

        imported_count = 0
        for signal in signals:
            try:
                # Convert to internal signal format
                internal_signal = TradingSignal(
                    instrument=signal.instrument,
                    signal_type=SignalType.BUY if signal.action == 'buy' else SignalType.SELL,
                    timestamp=signal.timestamp,
                    entry_timeframe=signal.timeframe,
                    rsi_value=None,  # External signals may not have RSI
                    autotrend_direction="bullish" if signal.action == 'buy' else "bearish",
                    htf_trend="bullish" if signal.action == 'buy' else "bearish",
                    entry_price=signal.price,
                    atr_value=None,
                )

                # Evaluate with rule engine
                open_positions = []  # Would need to get from database
                decision = rule_engine.evaluate_signal(internal_signal, open_positions)

                if decision.should_trade:
                    # Insert as external signal
                    database.insert_signal(
                        instrument=internal_signal.instrument,
                        action=internal_signal.signal_type.value,
                        timeframe=internal_signal.entry_timeframe,
                        rsi_value=internal_signal.rsi_value,
                        autotrend=f"external_{signal.provider}",
                        htf_trend=internal_signal.htf_trend,
                        price=internal_signal.entry_price,
                        atr_value=internal_signal.atr_value,
                        approved=True,
                        reject_reason=None,
                        raw_json={
                            "external_provider": signal.provider,
                            "external_confidence": signal.confidence,
                            "external_metadata": signal.metadata
                        }
                    )
                    imported_count += 1

            except Exception as e:
                logger.error(f"Error importing signal {signal}: {e}")

        database.log_activity("info", f"Imported {imported_count} external signals")
        return {"status": "imported", "count": imported_count}

    except Exception as e:
        logger.error(f"Import external signals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/activity")
async def api_activity(limit: int = 100, level: str = None):
    """Activity log."""
    logs = database.get_activity_log(limit=limit, level=level)
    return {"count": len(logs), "logs": logs}


@app.get("/api/equity-curve")
async def api_equity_curve(days: int = 90):
    """Equity curve from daily snapshots."""
    return database.get_equity_curve(days=days)


# ===================== NEWS API =====================

@app.get("/api/news")
async def api_news(impact: str = None):
    """
    Get this week's news events from ForexFactory.
    Returns all cached events (the full weekly calendar).
    """
    if news_filter is None:
        return {"count": 0, "last_refresh": None, "events": []}

    news_filter.refresh()
    high_only = (impact == "high")

    all_events = []
    for e in news_filter.events:
        if high_only and not e.is_high_impact:
            continue
        all_events.append(e)

    return {
        "count": len(all_events),
        "last_refresh": news_filter.last_fetch.isoformat() if news_filter.last_fetch else None,
        "events": [
            {
                "title": e.title,
                "country": e.country,
                "date": e.date.isoformat(),
                "impact": e.impact,
                "forecast": e.forecast,
                "previous": e.previous,
            }
            for e in all_events
        ],
    }


@app.get("/api/news/today")
async def api_news_today():
    """Today's news events (high impact only)."""
    if news_filter is None:
        return {"count": 0, "events": []}

    news_filter.refresh()
    events = news_filter.get_todays_events(high_impact_only=True)

    return {
        "count": len(events),
        "events": [
            {
                "title": e.title,
                "country": e.country,
                "date": e.date.isoformat(),
                "impact": e.impact,
                "forecast": e.forecast,
                "previous": e.previous,
            }
            for e in events
        ],
    }


@app.get("/api/news/check/{instrument}")
async def api_news_check(instrument: str):
    """Check if it's safe to trade a specific pair right now."""
    if news_filter is None:
        return {"instrument": instrument, "can_trade": True, "reason": "News filter offline", "should_close": False, "close_reason": ""}

    news_filter.refresh()
    can_trade, reason = news_filter.can_open_trade(instrument)
    should_close, close_reason = news_filter.should_close_positions(instrument)

    return {
        "instrument": instrument,
        "can_trade": can_trade,
        "reason": reason,
        "should_close": should_close,
        "close_reason": close_reason,
    }


# ===================== SETTINGS API =====================

@app.get("/api/correlation-status")
async def api_correlation_status():
    """Get correlation filter status showing which pairs are blocked and why."""
    from core.correlation_filter import CorrelationFilter, TradeDirection, OpenPosition
    
    # Get open positions
    open_trades = database.get_open_trades()
    open_positions = []
    for trade in open_trades:
        direction = TradeDirection.LONG if trade['direction'] == 'long' else TradeDirection.SHORT
        open_positions.append(OpenPosition(
            pair=trade['instrument'],
            direction=direction,
            entry_price=trade['entry_price'],
            entry_time=trade['open_time'],
            size=trade['units']
        ))
    
    # Check all pairs against correlation filter
    all_pairs = config.pairs.ALLOWED_PAIRS
    corr_filter = CorrelationFilter(correlation_threshold=config.indicators.CORRELATION_THRESHOLD)
    
    blocked_pairs = []
    available_pairs = []
    
    for pair in all_pairs:
        # Skip if already have open trade on this pair
        if any(pos.pair == pair for pos in open_positions):
            continue
            
        # Check both directions
        is_blocked_long, reason_long = corr_filter.would_duplicate_exposure(pair, TradeDirection.LONG, open_positions)
        is_blocked_short, reason_short = corr_filter.would_duplicate_exposure(pair, TradeDirection.SHORT, open_positions)
        
        if is_blocked_long and is_blocked_short:
            blocked_pairs.append({
                "pair": pair,
                "blocked_directions": "both",
                "reason": reason_long or reason_short
            })
        elif is_blocked_long:
            blocked_pairs.append({
                "pair": pair,
                "blocked_directions": "long",
                "reason": reason_long
            })
        elif is_blocked_short:
            blocked_pairs.append({
                "pair": pair,
                "blocked_directions": "short",
                "reason": reason_short
            })
        else:
            available_pairs.append(pair)
    
    return {
        "open_positions": [
            {"pair": pos.pair, "direction": pos.direction.value}
            for pos in open_positions
        ],
        "blocked_pairs": blocked_pairs,
        "available_pairs": available_pairs,
        "correlation_threshold": config.indicators.CORRELATION_THRESHOLD,
    }


@app.get("/api/settings")
async def api_get_settings():
    """Get current trading settings."""
    cfg = config  # Use loaded config (from DB)
    return {
        "leverage": cfg.risk.LEVERAGE,
        "risk_per_trade": cfg.risk.RISK_PER_TRADE_PERCENT,
        "risk_reward_ratio": cfg.risk.RISK_REWARD_RATIO,
        "max_open_trades": cfg.risk.MAX_OPEN_TRADES,
        "max_consecutive_losses": cfg.risk.MAX_CONSECUTIVE_LOSSES,
        "cooldown_hours": cfg.risk.COOLDOWN_HOURS,
        "use_atr_stop": cfg.risk.USE_ATR_STOP,
        "fixed_stop_pips": cfg.risk.FIXED_STOP_PIPS,
        "atr_multiplier": cfg.risk.ATR_MULTIPLIER,
        "trailing_stop_pips": cfg.risk.TRAILING_STOP_PIPS,
        "partial_close_percent": cfg.risk.PARTIAL_CLOSE_PERCENT,
        "pre_news_minutes": cfg.news.CLOSE_BEFORE_NEWS_MINUTES,
        "post_news_minutes": cfg.news.AVOID_AFTER_NEWS_MINUTES,
        "avoid_open_minutes": cfg.hours.MARKET_OPEN_AVOID_MINUTES,
        "entry_timeframe": cfg.indicators.ENTRY_TIMEFRAME.value,
        "confirmation_timeframe": cfg.indicators.CONFIRMATION_TIMEFRAME.value,
        "allowed_pairs": cfg.pairs.ALLOWED_PAIRS,
        # RSI & correlation settings
        "rsi_period": cfg.indicators.RSI_PERIOD,
        "rsi_oversold": cfg.indicators.RSI_OVERSOLD,
        "rsi_overbought": cfg.indicators.RSI_OVERBOUGHT,
        "correlation_threshold": cfg.indicators.CORRELATION_THRESHOLD,
        # ATS strategy
        "ats_strategy": cfg.ats_strategy.value,
        # Forward test mode
        "paper_trading": cfg.paper_trading,
    }


@app.put("/api/settings")
async def api_update_settings(update: SettingsUpdate):
    """Update trading settings at runtime."""
    cfg = config  # Use loaded config (from DB)
    changes = {}

    if update.leverage is not None:
        cfg.risk.LEVERAGE = update.leverage
        changes["leverage"] = update.leverage
    if update.risk_per_trade is not None:
        cfg.risk.RISK_PER_TRADE_PERCENT = update.risk_per_trade
        changes["risk_per_trade"] = update.risk_per_trade
    if update.risk_reward_ratio is not None:
        cfg.risk.RISK_REWARD_RATIO = update.risk_reward_ratio
        changes["risk_reward_ratio"] = update.risk_reward_ratio
    if update.max_open_trades is not None:
        cfg.risk.MAX_OPEN_TRADES = update.max_open_trades
        changes["max_open_trades"] = update.max_open_trades
    if update.max_consecutive_losses is not None:
        cfg.risk.MAX_CONSECUTIVE_LOSSES = update.max_consecutive_losses
        changes["max_consecutive_losses"] = update.max_consecutive_losses
    if update.cooldown_hours is not None:
        cfg.risk.COOLDOWN_HOURS = update.cooldown_hours
        changes["cooldown_hours"] = update.cooldown_hours
    if update.use_atr_stop is not None:
        cfg.risk.USE_ATR_STOP = update.use_atr_stop
        changes["use_atr_stop"] = update.use_atr_stop
    if update.fixed_stop_pips is not None:
        cfg.risk.FIXED_STOP_PIPS = update.fixed_stop_pips
        changes["fixed_stop_pips"] = update.fixed_stop_pips
    if update.atr_multiplier is not None:
        cfg.risk.ATR_MULTIPLIER = update.atr_multiplier
        changes["atr_multiplier"] = update.atr_multiplier
    if update.trailing_stop_pips is not None:
        cfg.risk.TRAILING_STOP_PIPS = update.trailing_stop_pips
        changes["trailing_stop_pips"] = update.trailing_stop_pips
    if update.partial_close_percent is not None:
        cfg.risk.PARTIAL_CLOSE_PERCENT = update.partial_close_percent
        changes["partial_close_percent"] = update.partial_close_percent
    if update.pre_news_minutes is not None:
        cfg.news.CLOSE_BEFORE_NEWS_MINUTES = update.pre_news_minutes
        changes["pre_news_minutes"] = update.pre_news_minutes
    if update.post_news_minutes is not None:
        cfg.news.AVOID_AFTER_NEWS_MINUTES = update.post_news_minutes
        changes["post_news_minutes"] = update.post_news_minutes
    if update.avoid_open_minutes is not None:
        cfg.hours.MARKET_OPEN_AVOID_MINUTES = update.avoid_open_minutes
        changes["avoid_open_minutes"] = update.avoid_open_minutes
    if update.allowed_pairs is not None:
        cfg.pairs.ALLOWED_PAIRS = update.allowed_pairs
        changes["allowed_pairs"] = update.allowed_pairs
    # RSI & correlation settings
    if update.rsi_period is not None:
        cfg.indicators.RSI_PERIOD = update.rsi_period
        changes["rsi_period"] = update.rsi_period
    if update.rsi_oversold is not None:
        cfg.indicators.RSI_OVERSOLD = update.rsi_oversold
        changes["rsi_oversold"] = update.rsi_oversold
    if update.rsi_overbought is not None:
        cfg.indicators.RSI_OVERBOUGHT = update.rsi_overbought
        changes["rsi_overbought"] = update.rsi_overbought
    if update.correlation_threshold is not None:
        cfg.indicators.CORRELATION_THRESHOLD = update.correlation_threshold
        changes["correlation_threshold"] = update.correlation_threshold
    # Timeframes
    if update.entry_timeframe is not None:
        from config.settings import TimeFrame
        try:
            cfg.indicators.ENTRY_TIMEFRAME = TimeFrame(update.entry_timeframe)
        except ValueError:
            pass
        changes["entry_timeframe"] = update.entry_timeframe
    if update.confirmation_timeframe is not None:
        from config.settings import TimeFrame
        try:
            cfg.indicators.CONFIRMATION_TIMEFRAME = TimeFrame(update.confirmation_timeframe)
        except ValueError:
            pass
        changes["confirmation_timeframe"] = update.confirmation_timeframe
    # ATS strategy
    if update.ats_strategy is not None:
        from config.settings import ATSStrategy
        try:
            cfg.ats_strategy = ATSStrategy(update.ats_strategy)
            changes["ats_strategy"] = update.ats_strategy
        except ValueError:
            pass
    # Forward test mode
    if update.paper_trading is not None:
        cfg.paper_trading = update.paper_trading
        changes["paper_trading"] = update.paper_trading

    # Persist to DB
    database.save_settings_from_config(changes)
    database.log_activity("info", "Settings updated", json.dumps(changes))

    return {"updated": changes}


# ===================== BACKTEST API =====================

@app.get("/api/backtest/runs")
async def api_backtest_runs(limit: int = 20):
    """Get previous backtest results."""
    runs = database.get_backtest_runs(limit=limit)
    return {"count": len(runs), "runs": runs}


@app.post("/api/backtest/run")
async def api_backtest_trigger(
    pair: str = "EUR_USD",
    start_date: str = "2024-01-01",
    end_date: str = "2025-12-31",
):
    """
    Trigger a single-pair backtest run. Returns results.
    Uses the backtesting module.
    """
    try:
        from backtest.engine import BacktestEngine

        engine = BacktestEngine(config=config)  # Use loaded config
        result = engine.run(pair=pair, start_date=start_date, end_date=end_date)

        # Save to DB
        run_id = database.save_backtest_run(
            config_json=json.dumps({"pair": pair}),
            pair=pair,
            start_date=start_date,
            end_date=end_date,
            total_trades=result["total_trades"],
            wins=result["wins"],
            losses=result["losses"],
            win_rate=result["win_rate"],
            profit_factor=result["profit_factor"],
            net_profit=result["net_profit"],
            max_drawdown=result["max_drawdown"],
            avg_win=result["avg_win"],
            avg_loss=result["avg_loss"],
            sharpe_ratio=result.get("sharpe_ratio"),
            trades_json=json.dumps(result.get("trades", [])),
        )

        result["run_id"] = run_id
        database.log_activity(
            "info",
            f"Backtest complete: {pair} {start_date}→{end_date}",
            f"Trades: {result['total_trades']} | WR: {result['win_rate']}% | Net: ${result['net_profit']}",
        )
        return result

    except ImportError:
        raise HTTPException(500, "Backtest module not available")
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        raise HTTPException(500, str(e))


class MultiPairBacktestRequest(BaseModel):
    pairs: List[str] = None  # None = all allowed pairs
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"


@app.post("/api/backtest/run-multi")
async def api_backtest_multi_pair(request: MultiPairBacktestRequest):
    """
    Trigger a multi-pair portfolio backtest.
    Tests correlation filters and max open trades across all pairs simultaneously.
    """
    try:
        from backtest.engine import BacktestEngine

        engine = BacktestEngine(config=config)
        pairs = request.pairs or config.pairs.ALLOWED_PAIRS
        result = engine.run_multi_pair(
            pairs=pairs,
            start_date=request.start_date,
            end_date=request.end_date
        )

        # Save to DB
        run_id = database.save_backtest_run(
            config_json=json.dumps({"pairs": pairs, "multi_pair": True}),
            pair=", ".join(pairs),
            start_date=request.start_date,
            end_date=request.end_date,
            total_trades=result["total_trades"],
            wins=result["wins"],
            losses=result["losses"],
            win_rate=result["win_rate"],
            profit_factor=result["profit_factor"],
            net_profit=result["net_profit"],
            max_drawdown=result["max_drawdown"],
            avg_win=result["avg_win"],
            avg_loss=result["avg_loss"],
            sharpe_ratio=result.get("sharpe_ratio", 0),
            trades_json=json.dumps(result.get("trades", [])),
        )

        result["run_id"] = run_id
        database.log_activity(
            "info",
            f"Multi-pair backtest complete: {len(pairs)} pairs {request.start_date}→{request.end_date}",
            f"Trades: {result['total_trades']} | WR: {result['win_rate']}% | Net: ${result['net_profit']}",
        )
        return result

    except ImportError:
        raise HTTPException(500, "Backtest module not available")
    except Exception as e:
        logger.error(f"Multi-pair backtest error: {e}")
        raise HTTPException(500, str(e))


# ------------------ Compare two backtests (server config vs overrides) ------------------
class BacktestCompareRequest(BaseModel):
    pair: str = "EUR_USD"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    atr_multiplier: Optional[float] = None
    risk_per_trade: Optional[float] = None
    risk_reward_ratio: Optional[float] = None


@app.post("/api/backtest/compare")
async def api_backtest_compare(req: BacktestCompareRequest):
    """Run server-config backtest and a second backtest with overrides — return both results + a diff."""
    try:
        from backtest.engine import BacktestEngine

        # Baseline (current server config)
        baseline_engine = BacktestEngine(config=config)
        baseline = baseline_engine.run(pair=req.pair, start_date=req.start_date, end_date=req.end_date)

        # Modified config (deep copy of server config + overrides)
        mod_cfg = copy.deepcopy(config)
        if req.atr_multiplier is not None:
            mod_cfg.risk.ATR_MULTIPLIER = req.atr_multiplier
        if req.risk_per_trade is not None:
            mod_cfg.risk.RISK_PER_TRADE_PERCENT = req.risk_per_trade
        if req.risk_reward_ratio is not None:
            mod_cfg.risk.RISK_REWARD_RATIO = req.risk_reward_ratio

        modified_engine = BacktestEngine(config=mod_cfg)
        modified = modified_engine.run(pair=req.pair, start_date=req.start_date, end_date=req.end_date)

        diff = {
            "total_trades_diff": modified["total_trades"] - baseline["total_trades"],
            "net_profit_diff": round(modified["net_profit"] - baseline["net_profit"], 2),
            "max_drawdown_diff": round(modified["max_drawdown"] - baseline["max_drawdown"], 2),
        }

        return {"baseline": baseline, "modified": modified, "diff": diff}

    except ImportError:
        raise HTTPException(500, "Backtest module not available")
    except Exception as e:
        logger.error(f"Backtest compare error: {e}")
        raise HTTPException(500, str(e))


# ---------------- Serve saved backtest compare SVGs ----------------
@app.get("/api/backtest/compare-svg")
async def api_backtest_compare_svg(filename: str = "backtest_compare_EUR_USD_2024-01-01.svg"):
    """Return a saved backtest compare SVG from backend/data/ (safe path only)."""
    safe_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    path = os.path.abspath(os.path.join(safe_root, filename))
    if not path.startswith(safe_root) or not os.path.exists(path):
        raise HTTPException(404, "SVG not found")
    return FileResponse(path, media_type="image/svg+xml")


@app.get("/api/backtest/compare-png")
async def api_backtest_compare_png(filename: str = "backtest_compare_EUR_USD_2024-01-01.png"):
    """Return a saved backtest compare PNG from backend/data/ (safe path only)."""
    safe_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    path = os.path.abspath(os.path.join(safe_root, filename))
    if not path.startswith(safe_root) or not os.path.exists(path):
        raise HTTPException(404, "PNG not found")
    return FileResponse(path, media_type="image/png")

# ===================== HEALTH =====================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(ZoneInfo("UTC")).isoformat(),
        "components": {
            "rule_engine": rule_engine is not None,
            "news_filter": news_filter is not None,
            "database": True,
        },
    }


# ===================== MAIN =====================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting ATS server on port {port}")
    uvicorn.run("server.api:app", host="0.0.0.0", port=port, reload=True)
