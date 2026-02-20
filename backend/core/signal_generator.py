"""
Signal Generator
Generates trading signals autonomously by analyzing market data
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rule_engine import TradingRuleEngine, TradingSignal, SignalType
from core.correlation_filter import OpenPosition, TradeDirection
from brokers.oanda import OandaClient
from config.settings import TradingConfig, DEFAULT_CONFIG
from database import db as database

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates trading signals by analyzing live market data"""

    def __init__(self, config: TradingConfig, oanda_client: Optional[OandaClient] = None):
        self.config = config
        self.oanda_client = oanda_client
        self.rule_engine = TradingRuleEngine(config, "data/trading_state.json", "data/trade_history.json")

    async def generate_signals(self) -> List[TradingSignal]:
        """Generate signals for all allowed pairs"""
        signals = []

        for pair in self.config.pairs.ALLOWED_PAIRS:
            try:
                signal = self._analyze_pair(pair)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error analyzing {pair}: {e}")

        return signals

    def _analyze_pair(self, instrument: str) -> Optional[TradingSignal]:
        """Analyze a single pair and generate signal if conditions met"""
        if not self.oanda_client:
            return None

        # Check if we already have an open trade for this instrument
        open_trades = database.get_open_trades()
        for trade in open_trades:
            if trade['instrument'] == instrument:
                logger.debug(f"Skipping {instrument} - already have open trade #{trade['id']}")
                return None

        # Enforce allowed pairs
        allowed_pairs = ["EUR_USD", "USD_JPY", "GBP_USD", "AUD_USD", "NZD_USD", "USD_CHF", "USD_CAD"]
        if instrument not in allowed_pairs:
            return None

        # News filter: block trades around high-impact news
        from news.forex_factory import NewsFilter
        news_filter = NewsFilter()
        news_filter.refresh()
        can_trade, reason = news_filter.can_open_trade(instrument)
        if not can_trade:
            logger.info(f"Blocked {instrument} due to news: {reason}")
            return None

        # Get recent candles (M15)
        candles = self.oanda_client.get_candles(instrument, "M15", count=100)
        if not candles:
            return None

        # Get H1 candles for confirmation
        htf_candles = self.oanda_client.get_candles(instrument, "H1", count=50)

        # Calculate indicators
        rsi_value = self._calculate_rsi([c['close'] for c in candles[-50:]], 14)
        atr_value = self._calculate_atr(candles[-20:])
        autotrend_direction = self._calculate_autotrend(candles)
        htf_trend = self._calculate_htf_trend(htf_candles)

        # Correlation filter: avoid duplicate exposure
        from core.correlation_filter import CorrelationFilter, TradeDirection, OpenPosition
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
        corr_filter = CorrelationFilter(correlation_threshold=0.70)
        direction = TradeDirection.LONG if autotrend_direction == "bullish" else TradeDirection.SHORT
        is_duplicate, reason = corr_filter.would_duplicate_exposure(instrument, direction, open_positions)
        if is_duplicate:
            logger.info(f"Blocked {instrument} due to correlation: {reason}")
            return None

        # Check for signal
        signal_type = self._detect_signal(candles, rsi_value, autotrend_direction, htf_trend)

        if signal_type == SignalType.NEUTRAL:
            return None

        # Create signal
        current_price = candles[-1]['close']
        # Estimate spread and fee (example: 0.0002 spread, $2 fee per 100k)
        spread = 0.0002
        fee = 2 * (100000 / 100000)  # $2 per 100k units
        signal = TradingSignal(
            instrument=instrument,
            signal_type=signal_type,
            timestamp=datetime.utcnow().isoformat(),
            entry_timeframe="M15",
            rsi_value=rsi_value,
            autotrend_direction=autotrend_direction,
            htf_trend=htf_trend,
            entry_price=current_price + spread,
            atr_value=atr_value,
            spread=spread,
            fee=fee
        )

        return signal

    def _calculate_rsi(self, closes: List[float], period: int) -> float:
        """Calculate RSI"""
        if len(closes) < period + 1:
            return 50.0

        gains = []
        losses = []

        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_atr(self, candles: List[Dict], period: int = 14) -> float:
        """Calculate ATR"""
        if len(candles) < period:
            return 0.0

        tr_values = []
        for i in range(1, len(candles)):
            high = candles[i]['high']
            low = candles[i]['low']
            prev_close = candles[i-1]['close']

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)

        return sum(tr_values[-period:]) / period

    def _calculate_autotrend(self, candles: List[Dict]) -> str:
        """Calculate AutoTrend direction (simplified)"""
        # This is a placeholder - actual AutoTrend is more complex
        # For now, use simple trend based on EMA crossover
        closes = [c['close'] for c in candles[-50:]]

        if len(closes) < 50:
            return "neutral"

        ema_short = sum(closes[-10:]) / 10
        ema_long = sum(closes[-30:]) / 30

        if ema_short > ema_long:
            return "bullish"
        elif ema_short < ema_long:
            return "bearish"
        else:
            return "neutral"

    def _calculate_htf_trend(self, htf_candles: List[Dict]) -> str:
        """Calculate higher timeframe trend"""
        if not htf_candles or len(htf_candles) < 20:
            return "neutral"

        recent_closes = [c['close'] for c in htf_candles[-20:]]
        if recent_closes[-1] > recent_closes[0]:
            return "bullish"
        else:
            return "bearish"

    def _detect_signal(self, candles: List[Dict], rsi: float, autotrend: str, htf_trend: str) -> SignalType:
        """Detect if there's a valid signal"""
        if len(candles) < 5:
            return SignalType.NEUTRAL

        # Check for breakout pattern (simplified)
        current = candles[-1]
        previous = candles[-2]

        # Buy signal
        if (autotrend == "bullish" and htf_trend == "bullish" and
            rsi < self.config.indicators.RSI_OVERBOUGHT and
            current['close'] > previous['high']):
            return SignalType.BUY

        # Sell signal
        if (autotrend == "bearish" and htf_trend == "bearish" and
            rsi > self.config.indicators.RSI_OVERSOLD and
            current['close'] < previous['low']):
            return SignalType.SELL

        return SignalType.NEUTRAL

    async def _execute_trade(self, signal: TradingSignal, decision, signal_id: int):
        """Execute a trade for an approved signal"""
        try:
            # Calculate position size
            if self.oanda_client:
                pip_size = self.oanda_client.PIP_SIZES.get(signal.instrument, 0.0001)
                stop_pips = (signal.atr_value * self.config.risk.ATR_MULTIPLIER) / pip_size if signal.atr_value else self.config.risk.FIXED_STOP_PIPS
                units = self.oanda_client.calculate_position_size(
                    signal.instrument,
                    stop_pips,
                    self.config.risk.RISK_PER_TRADE_PERCENT
                )
            else:
                units = 1000  # Default for paper trading
            
            direction = "long" if signal.signal_type == SignalType.BUY else "short"
            
            # Calculate SL using ATS rules: swing low/high (if available)\n            pip_size = self.oanda_client.PIP_SIZES.get(signal.instrument, 0.0001) if self.oanda_client else 0.0001
            
            if signal.signal_type == SignalType.BUY:
                # LONG: Stop at swing low (ATS Official Rule)
                if signal.swing_low:
                    # Use swing low minus small buffer (2 pips)
                    stop_loss = signal.swing_low - (2 * pip_size)
                elif signal.atr_value:
                    # Fallback to ATR if swing not provided
                    stop_distance = signal.atr_value * self.config.risk.ATR_MULTIPLIER
                    stop_loss = signal.entry_price - stop_distance
                else:
                    # Final fallback to fixed pips
                    stop_distance = self.config.risk.FIXED_STOP_PIPS * pip_size
                    stop_loss = signal.entry_price - stop_distance
                
                # Calculate TP at 2R (will exit 50% here per ATS strategy)
                risk = signal.entry_price - stop_loss
                take_profit = signal.entry_price + (risk * self.config.risk.RISK_REWARD_RATIO)
                
            else:  # SELL
                # SHORT: Stop at swing high (ATS Official Rule)
                if signal.swing_high:
                    # Use swing high plus small buffer (2 pips)
                    stop_loss = signal.swing_high + (2 * pip_size)
                elif signal.atr_value:
                    # Fallback to ATR if swing not provided
                    stop_distance = signal.atr_value * self.config.risk.ATR_MULTIPLIER
                    stop_loss = signal.entry_price + stop_distance
                else:
                    # Final fallback to fixed pips
                    stop_distance = self.config.risk.FIXED_STOP_PIPS * pip_size
                    stop_loss = signal.entry_price + stop_distance
                
                # Calculate TP at 2R (will exit 50% here per ATS strategy)
                risk = stop_loss - signal.entry_price
                take_profit = signal.entry_price - (risk * self.config.risk.RISK_REWARD_RATIO)

            # Execute on OANDA if not in paper trading mode
            oanda_trade_id = None
            execution_success = True
            
            if not self.config.paper_trading and self.oanda_client:
                try:
                    logger.info(f"Placing OANDA order: {signal.instrument} {units if direction == 'long' else -units} units, SL: {stop_loss:.5f}, TP: {take_profit:.5f}")
                    oanda_result = self.oanda_client.place_market_order(
                        instrument=signal.instrument,
                        units=units if direction == "long" else -units,
                        stop_loss_price=stop_loss,
                        take_profit_price=take_profit,
                    )
                    
                    # Check if order was rejected by OANDA (HTTP 200 but with rejection)
                    if "orderRejectTransaction" in oanda_result:
                        execution_success = False
                        # Silently skip - OANDA couldn't execute (likely insufficient margin with existing positions)
                        return
                    
                    # Extract trade ID from successful fill
                    oanda_trade_id = oanda_result.get("orderFillTransaction", {}).get("tradeOpened", {}).get("tradeID")
                    
                    # Validate that we actually got a trade ID
                    if not oanda_trade_id:
                        execution_success = False
                        # Silently skip - OANDA couldn't execute (order cancelled)
                        return
                    
                    database.log_activity(
                        "trade",
                        f"LIVE {'BUY' if direction == 'long' else 'SELL'} "
                        f"{signal.instrument} @ {signal.entry_price}",
                        f"OANDA Trade #{oanda_trade_id} | SL: {stop_loss} | TP: {take_profit}",
                    )
                except Exception as e:
                    execution_success = False
                    error_msg = f"OANDA execution failed: {e}"
                    logger.error(error_msg)
                    database.log_activity(
                        "error", 
                        f"Failed to execute {signal.instrument} {'BUY' if direction == 'long' else 'SELL'}",
                        f"{error_msg} | Units: {units if direction == 'long' else -units} | SL: {stop_loss:.5f} | TP: {take_profit:.5f}"
                    )
                    # Don't create trade record if execution failed
                    return
            else:
                mode = "PAPER" if self.config.paper_trading else "NO BROKER"
                database.log_activity(
                    "trade",
                    f"[{mode}] {'BUY' if direction == 'long' else 'SELL'} "
                    f"{signal.instrument} @ {signal.entry_price}",
                    f"SL: {stop_loss} | TP: {take_profit} | Signal #{signal_id}",
                )

            # Insert trade into DB only if execution succeeded (or if in paper/no-broker mode)
            if execution_success:
                trade_id = database.insert_trade(
                    instrument=signal.instrument,
                    direction=direction,
                    units=units,
                    entry_price=signal.entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    signal_id=signal_id,
                    oanda_trade_id=oanda_trade_id,
                )

            # Deduct margin from virtual balance in paper trading mode
            if self.config.paper_trading:
                # Calculate margin required (rough estimate: 1% of notional value)
                margin_required = abs(units) * signal.entry_price * 0.01
                current_balance = database.get_virtual_balance()
                new_balance = current_balance - margin_required
                database.update_virtual_balance(new_balance)
                logger.info(f"Paper trade: deducted ${margin_required:.2f} margin, balance now ${new_balance:.2f}")

            database.log_activity(
                "info",
                f"Auto Signal APPROVED: {signal.signal_type.value} {signal.instrument}",
                f"{'LIVE' if not self.config.paper_trading else 'PAPER'} mode | "
                f"All {len(decision.checks_passed)} rule checks passed. Trade #{trade_id}",
            )

        except Exception as e:
            logger.error(f"Error executing auto trade: {e}")
            database.log_activity("error", f"Auto trade execution failed: {e}")

    async def run_signal_generation(self):
        """Main loop for continuous signal generation"""
        logger.info("Starting signal generation...")

        while True:
            try:
                signals = await self.generate_signals()

                for signal in signals:
                    # Get current open positions for rule evaluation
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
                    
                    # Evaluate signal with rule engine
                    decision = self.rule_engine.evaluate_signal(signal, open_positions)

                    if decision.should_trade:
                        # Insert signal to database
                        sig_id = database.insert_signal(
                            instrument=signal.instrument,
                            action=signal.signal_type.value,
                            timeframe=signal.entry_timeframe,
                            rsi_value=signal.rsi_value,
                            autotrend=signal.autotrend_direction,
                            htf_trend=signal.htf_trend,
                            price=signal.entry_price,
                            atr_value=signal.atr_value,
                            approved=True,  # Auto-approved for generated signals
                            reject_reason=None
                        )

                        logger.info(f"Generated signal: {signal.signal_type.value} {signal.instrument}")

                        # Execute the trade
                        await self._execute_trade(signal, decision, sig_id)

                # Wait before next check
                await asyncio.sleep(300)  # 5 minutes

            except Exception as e:
                logger.error(f"Error in signal generation loop: {e}")
                await asyncio.sleep(60)