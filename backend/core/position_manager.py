"""
Position Manager
Handles active trade management including:
- Partial close at target (50% at 1.9R)
- Trailing stop on remaining position
- Close remaining on ATS color change
- News-based emergency close
"""

import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from brokers.oanda import OandaClient
from core.state_manager import TradeStateManager, TradeRecord, TradeResult
from news.forex_factory import NewsFilter

logger = logging.getLogger(__name__)


@dataclass
class ManagedTrade:
    """Trade being actively managed"""
    trade_id: str
    instrument: str
    direction: str  # "long" or "short"
    entry_price: float
    units: int  # Original full position size
    stop_loss: float
    take_profit: float  # First target (partial close)
    risk_distance: float  # Distance from entry to stop in price
    strategy: str = "standard"  # ATS strategy type

    # State tracking
    partial_closed: bool = False
    partial_close_units: int = 0
    remaining_units: int = 0
    trailing_stop_active: bool = False
    trailing_stop_price: float = 0.0
    highest_price: float = 0.0  # For long trailing
    lowest_price: float = 999.0  # For short trailing

    # Scaling strategy state
    scaled_in: bool = False
    scale_in_units: int = 0
    original_stop: float = 0.0  # Remember original SL for tightening

    # DPL strategy state
    dpl1_closed: bool = False
    dpl2_closed: bool = False

    # Timestamps
    entry_time: str = ""
    partial_close_time: str = ""
    
    def __post_init__(self):
        self.remaining_units = abs(self.units)
        self.entry_time = datetime.now(ZoneInfo("UTC")).isoformat()
        if self.direction == "long":
            self.highest_price = self.entry_price
        else:
            self.lowest_price = self.entry_price


class PositionManager:
    """
    Manages open positions with advanced exit logic:
    
    1. Monitor price vs take profit level
    2. At 1.9R (configurable), close 50% of position
    3. Activate trailing stop on remaining 50%
    4. Close remaining on ATS color change signal
    5. Emergency close before news events
    """
    
    PIP_SIZES = {
        "EUR_USD": 0.0001,
        "USD_JPY": 0.01,
        "GBP_USD": 0.0001,
        "AUD_USD": 0.0001,
        "NZD_USD": 0.0001,
        "USD_CHF": 0.0001,
        "USD_CAD": 0.0001,
    }
    
    def __init__(
        self,
        oanda_client: OandaClient,
        state_manager: TradeStateManager,
        news_filter: NewsFilter,
        risk_reward: float = 1.9,
        partial_close_pct: float = 50.0,
        trailing_stop_pips: float = 2.0,
    ):
        self.oanda = oanda_client
        self.state = state_manager
        self.news = news_filter
        self.risk_reward = risk_reward
        self.partial_close_pct = partial_close_pct
        self.trailing_stop_pips = trailing_stop_pips
        
        # Active managed trades
        self.managed_trades: Dict[str, ManagedTrade] = {}
        
        # Monitoring thread
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
    
    def register_trade(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        entry_price: float,
        units: int,
        stop_loss: float,
        take_profit: float,
        strategy: str = "standard"
    ) -> ManagedTrade:
        """Register a new trade for management"""
        risk_distance = abs(entry_price - stop_loss)

        managed = ManagedTrade(
            trade_id=trade_id,
            instrument=instrument,
            direction=direction,
            entry_price=entry_price,
            units=units,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_distance=risk_distance,
            strategy=strategy,
            original_stop=stop_loss,
        )

        self.managed_trades[trade_id] = managed
        logger.info(
            f"Registered trade {trade_id}: [{strategy.upper()}] {direction} {instrument} "
            f"@ {entry_price}, SL: {stop_loss}, TP: {take_profit}"
        )

        return managed
    
    def check_exit_conditions(self, trade: ManagedTrade, current_price: float) -> bool:
        """Strategy-aware exit condition check"""
        if trade.strategy == "standard":
            return self._check_standard_exit(trade, current_price)
        elif trade.strategy == "aggressive":
            return self._check_aggressive_exit(trade, current_price)
        elif trade.strategy == "scaling":
            return self._check_scaling_exit(trade, current_price)
        elif trade.strategy == "dpl":
            return self._check_dpl_exit(trade, current_price)
        return self._check_standard_exit(trade, current_price)

    def _check_standard_exit(self, trade: ManagedTrade, current_price: float) -> bool:
        """Strategy 1: 50% at 2R, rest on ATS color flip"""
        if trade.partial_closed:
            return False

        # 2R target
        target = trade.entry_price + (trade.risk_distance * 2) * (1 if trade.direction == "long" else -1)

        hit = (trade.direction == "long" and current_price >= target) or \
              (trade.direction == "short" and current_price <= target)

        if hit:
            return self._execute_partial_close(trade, pct=50.0)
        return False

    def _check_aggressive_exit(self, trade: ManagedTrade, current_price: float) -> bool:
        """Strategy 2: Full exit at 10R"""
        target = trade.entry_price + (trade.risk_distance * 10) * (1 if trade.direction == "long" else -1)

        hit = (trade.direction == "long" and current_price >= target) or \
              (trade.direction == "short" and current_price <= target)

        if hit:
            try:
                self.oanda.close_trade(trade.trade_id)
                trade.remaining_units = 0
                logger.info(f"[AGGRESSIVE] Full exit at 10R: {trade.instrument}")
                return True
            except Exception as e:
                logger.error(f"Aggressive exit failed: {e}")
        return False

    def _check_scaling_exit(self, trade: ManagedTrade, current_price: float) -> bool:
        """Strategy 3: Add at +1R, tighten SL, full exit at 3R"""
        # Scale-in at +1R
        if not trade.scaled_in:
            scale_target = trade.entry_price + (trade.risk_distance * 1) * (1 if trade.direction == "long" else -1)
            hit = (trade.direction == "long" and current_price >= scale_target) or \
                  (trade.direction == "short" and current_price <= scale_target)
            if hit:
                try:
                    # Place a second order of equal size
                    units = abs(trade.units)
                    self.oanda.place_market_order(
                        instrument=trade.instrument,
                        units=units if trade.direction == "long" else -units,
                        stop_loss_price=None,
                        take_profit_price=None,
                    )
                    trade.scaled_in = True
                    trade.scale_in_units = units
                    trade.remaining_units = units * 2

                    # Tighten SL to half of original distance
                    half_risk = trade.risk_distance / 2
                    new_sl = trade.entry_price - half_risk if trade.direction == "long" else trade.entry_price + half_risk
                    self.oanda.modify_trade(trade.trade_id, stop_loss_price=new_sl)
                    trade.stop_loss = new_sl

                    logger.info(f"[SCALING] Scaled in at +1R, SL tightened to {new_sl:.5f}")
                except Exception as e:
                    logger.error(f"Scaling entry failed: {e}")
            return False

        # Full exit at 3R
        exit_target = trade.entry_price + (trade.risk_distance * 3) * (1 if trade.direction == "long" else -1)
        hit = (trade.direction == "long" and current_price >= exit_target) or \
              (trade.direction == "short" and current_price <= exit_target)
        if hit:
            try:
                self.oanda.close_trade(trade.trade_id)
                trade.remaining_units = 0
                logger.info(f"[SCALING] Full exit at 3R: {trade.instrument}")
                return True
            except Exception as e:
                logger.error(f"Scaling exit failed: {e}")
        return False

    def _check_dpl_exit(self, trade: ManagedTrade, current_price: float) -> bool:
        """Strategy 4: 1/3 at DPL1, 1/3 at DPL2, last 1/3 at ATS color flip"""
        # DPL levels approximate: DPL1 ~ 1R, DPL2 ~ 2R (adjustable)
        dpl1 = trade.entry_price + (trade.risk_distance * 1) * (1 if trade.direction == "long" else -1)
        dpl2 = trade.entry_price + (trade.risk_distance * 2) * (1 if trade.direction == "long" else -1)

        # 1/3 at DPL1
        if not trade.dpl1_closed:
            hit = (trade.direction == "long" and current_price >= dpl1) or \
                  (trade.direction == "short" and current_price <= dpl1)
            if hit:
                return self._execute_partial_close(trade, pct=33.0, label="DPL1", move_sl_to_be=True)

        # 1/3 at DPL2
        if trade.dpl1_closed and not trade.dpl2_closed:
            hit = (trade.direction == "long" and current_price >= dpl2) or \
                  (trade.direction == "short" and current_price <= dpl2)
            if hit:
                trade.dpl2_closed = True
                return self._execute_partial_close(trade, pct=50.0, label="DPL2")

        # Last 1/3 held until ATS color flip (handled by handle_ats_exit)
        return False

    def _execute_partial_close(
        self, trade: ManagedTrade, pct: float = 50.0,
        label: str = "TP", move_sl_to_be: bool = False
    ) -> bool:
        """Execute partial close with configurable percentage"""
        try:
            close_units = int(abs(trade.remaining_units) * (pct / 100))
            if close_units < 1:
                close_units = 1

            self.oanda.close_trade(trade.trade_id, units=close_units)

            trade.partial_closed = True
            if label == "DPL1":
                trade.dpl1_closed = True
            trade.partial_close_units += close_units
            trade.remaining_units -= close_units
            trade.partial_close_time = datetime.now(ZoneInfo("UTC")).isoformat()

            # Move SL to breakeven if requested (DPL strategy)
            if move_sl_to_be:
                try:
                    self.oanda.modify_trade(trade.trade_id, stop_loss_price=trade.entry_price)
                    trade.stop_loss = trade.entry_price
                    logger.info(f"SL moved to breakeven: {trade.entry_price}")
                except Exception:
                    pass

            # Activate trailing stop for Standard strategy
            if trade.strategy == "standard" and trade.remaining_units > 0:
                trade.trailing_stop_active = True
                self._set_trailing_stop(trade)

            logger.info(
                f"[{label}] Partial close: {trade.instrument} "
                f"closed {close_units}, {trade.remaining_units} remaining"
            )
            return True

        except Exception as e:
            logger.error(f"Error executing partial close: {e}")
            return False
    
    def _set_trailing_stop(self, trade: ManagedTrade):
        """Set trailing stop on remaining position"""
        try:
            pip_size = self.PIP_SIZES.get(trade.instrument, 0.0001)
            
            self.oanda.modify_trade(
                trade_id=trade.trade_id,
                trailing_stop_pips=self.trailing_stop_pips,
                instrument=trade.instrument
            )
            
            logger.info(f"Trailing stop set: {self.trailing_stop_pips} pips on {trade.instrument}")
            
        except Exception as e:
            logger.error(f"Error setting trailing stop: {e}")
    
    def update_trailing_stop(self, trade: ManagedTrade, current_price: float):
        """Manually update trailing stop tracking"""
        if not trade.trailing_stop_active:
            return
        
        pip_size = self.PIP_SIZES.get(trade.instrument, 0.0001)
        trail_distance = self.trailing_stop_pips * pip_size
        
        if trade.direction == "long":
            if current_price > trade.highest_price:
                trade.highest_price = current_price
                trade.trailing_stop_price = current_price - trail_distance
        else:
            if current_price < trade.lowest_price:
                trade.lowest_price = current_price
                trade.trailing_stop_price = current_price + trail_distance
    
    def handle_ats_exit(self, instrument: str, new_direction: str) -> bool:
        """
        Handle ATS color change - close remaining position.
        Called when VPS receives an exit signal from TradingView.
        """
        trades_closed = 0
        
        for trade_id, trade in list(self.managed_trades.items()):
            if trade.instrument != instrument:
                continue
            
            # ATS turned red → close longs
            # ATS turned blue → close shorts
            should_close = (
                (trade.direction == "long" and new_direction == "bearish") or
                (trade.direction == "short" and new_direction == "bullish")
            )
            
            if should_close:
                try:
                    self.oanda.close_trade(trade_id)
                    
                    # Record trade result
                    bid, ask = self.oanda.get_price(instrument)
                    exit_price = bid if trade.direction == "long" else ask
                    
                    pip_size = self.PIP_SIZES.get(instrument, 0.0001)
                    
                    if trade.direction == "long":
                        pl_pips = (exit_price - trade.entry_price) / pip_size
                    else:
                        pl_pips = (trade.entry_price - exit_price) / pip_size
                    
                    result = TradeResult.WIN if pl_pips > 0 else TradeResult.LOSS
                    
                    self.state.record_trade(TradeRecord(
                        trade_id=trade_id,
                        instrument=instrument,
                        direction=trade.direction,
                        entry_price=trade.entry_price,
                        exit_price=exit_price,
                        entry_time=trade.entry_time,
                        exit_time=datetime.now(ZoneInfo("UTC")).isoformat(),
                        profit_loss=pl_pips * pip_size * abs(trade.remaining_units),
                        profit_loss_pips=pl_pips,
                        result=result,
                        exit_reason="ats_color_change"
                    ))
                    
                    del self.managed_trades[trade_id]
                    trades_closed += 1
                    
                    logger.info(f"ATS exit: Closed {instrument} {trade.direction}, P/L: {pl_pips:.1f} pips")
                    
                except Exception as e:
                    logger.error(f"Error closing trade on ATS exit: {e}")
        
        return trades_closed > 0
    
    def check_news_exits(self):
        """Check if any positions need to be closed for upcoming news"""
        for trade_id, trade in list(self.managed_trades.items()):
            should_close, reason = self.news.should_close_positions(trade.instrument)
            
            if should_close:
                try:
                    self.oanda.close_trade(trade_id)
                    logger.warning(f"News exit: Closed {trade.instrument} - {reason}")
                    
                    # Record as manual close
                    bid, ask = self.oanda.get_price(trade.instrument)
                    exit_price = bid if trade.direction == "long" else ask
                    pip_size = self.PIP_SIZES.get(trade.instrument, 0.0001)
                    
                    if trade.direction == "long":
                        pl_pips = (exit_price - trade.entry_price) / pip_size
                    else:
                        pl_pips = (trade.entry_price - exit_price) / pip_size
                    
                    result = TradeResult.WIN if pl_pips > 0 else TradeResult.LOSS
                    
                    self.state.record_trade(TradeRecord(
                        trade_id=trade_id,
                        instrument=trade.instrument,
                        direction=trade.direction,
                        entry_price=trade.entry_price,
                        exit_price=exit_price,
                        entry_time=trade.entry_time,
                        exit_time=datetime.now(ZoneInfo("UTC")).isoformat(),
                        profit_loss=pl_pips * pip_size * abs(trade.remaining_units),
                        profit_loss_pips=pl_pips,
                        result=result,
                        exit_reason="news_close"
                    ))
                    
                    del self.managed_trades[trade_id]
                    
                except Exception as e:
                    logger.error(f"Error on news exit: {e}")
    
    def monitor_cycle(self):
        """Single monitoring cycle - check all active trades"""
        for trade_id, trade in list(self.managed_trades.items()):
            try:
                # Get current price
                bid, ask = self.oanda.get_price(trade.instrument)
                current_price = (bid + ask) / 2
                
                # Check strategy-specific exit conditions
                self.check_exit_conditions(trade, current_price)
                
                # Update trailing stop
                self.update_trailing_stop(trade, current_price)
                
            except Exception as e:
                logger.error(f"Error monitoring trade {trade_id}: {e}")
        
        # Check news exits
        self.check_news_exits()
    
    def start_monitoring(self, interval_seconds: int = 5):
        """Start background monitoring thread"""
        self._running = True
        
        def _monitor_loop():
            while self._running:
                try:
                    if self.managed_trades:
                        self.monitor_cycle()
                except Exception as e:
                    logger.error(f"Monitor loop error: {e}")
                time.sleep(interval_seconds)
        
        self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Position monitor started (interval: {interval_seconds}s)")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        logger.info("Position monitor stopped")
    
    def get_managed_trades_summary(self) -> List[Dict]:
        """Get summary of all managed trades"""
        summary = []
        for trade_id, trade in self.managed_trades.items():
            summary.append({
                "trade_id": trade_id,
                "instrument": trade.instrument,
                "direction": trade.direction,
                "entry_price": trade.entry_price,
                "units": trade.units,
                "remaining_units": trade.remaining_units,
                "stop_loss": trade.stop_loss,
                "take_profit": trade.take_profit,
                "partial_closed": trade.partial_closed,
                "trailing_stop_active": trade.trailing_stop_active,
                "trailing_stop_price": trade.trailing_stop_price,
            })
        return summary
