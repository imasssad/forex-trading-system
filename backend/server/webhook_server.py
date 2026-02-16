"""
Webhook Server for TradingView Alerts
Receives alerts from TradingView and processes them through the rule engine
"""

from flask import Flask, request, jsonify
from datetime import datetime
from typing import Dict, Optional
from zoneinfo import ZoneInfo
import logging
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rule_engine import TradingRuleEngine, TradingSignal, SignalType
from core.correlation_filter import OpenPosition, TradeDirection
from brokers.oanda import OandaClient
from config.settings import DEFAULT_CONFIG

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize components (will be set up on startup)
rule_engine: Optional[TradingRuleEngine] = None
oanda_client: Optional[OandaClient] = None


def initialize_components():
    """Initialize the trading components"""
    global rule_engine, oanda_client
    
    logger.info("Initializing trading components...")
    
    # Initialize rule engine
    rule_engine = TradingRuleEngine(
        config=DEFAULT_CONFIG,
        state_file="data/trading_state.json",
        history_file="data/trade_history.json"
    )
    
    # Initialize OANDA client (if credentials available)
    try:
        oanda_client = OandaClient(practice=True)
        logger.info("OANDA client initialized")
    except ValueError as e:
        logger.warning(f"OANDA client not initialized: {e}")
        oanda_client = None
    
    logger.info("Components initialized")


def parse_tradingview_alert(data: Dict) -> Optional[TradingSignal]:
    """
    Parse incoming TradingView alert into a TradingSignal.
    
    Expected JSON format from TradingView:
    {
        "symbol": "EURUSD",
        "action": "buy" or "sell",
        "timeframe": "15",
        "rsi": 35.5,
        "autotrend": "bullish" or "bearish",
        "htf_trend": "bullish" or "bearish",
        "price": 1.0850,
        "atr": 0.0015
    }
    """
    try:
        # Parse symbol - convert from TradingView format to OANDA format
        symbol = data.get("symbol", "").upper()
        if len(symbol) == 6:
            # Convert EURUSD to EUR_USD
            instrument = f"{symbol[:3]}_{symbol[3:]}"
        else:
            instrument = symbol.replace("/", "_")
        
        # Parse action
        action = data.get("action", "").lower()
        if action == "buy":
            signal_type = SignalType.BUY
        elif action == "sell":
            signal_type = SignalType.SELL
        else:
            signal_type = SignalType.NEUTRAL
        
        # Parse timeframe
        tf = data.get("timeframe", "15")
        entry_timeframe = f"M{tf}" if tf.isdigit() else tf
        
        # Create signal
        signal = TradingSignal(
            instrument=instrument,
            signal_type=signal_type,
            timestamp=datetime.now(ZoneInfo("UTC")).isoformat(),
            entry_timeframe=entry_timeframe,
            rsi_value=float(data.get("rsi", 50)),
            autotrend_direction=data.get("autotrend", "neutral").lower(),
            htf_trend=data.get("htf_trend", "neutral").lower(),
            entry_price=float(data.get("price", 0)),
            atr_value=float(data.get("atr", 0)) if data.get("atr") else None
        )
        
        return signal
        
    except Exception as e:
        logger.error(f"Error parsing alert: {e}")
        return None


def get_open_positions() -> list:
    """Get current open positions from OANDA"""
    if oanda_client is None:
        return []
    
    try:
        trades = oanda_client.get_open_trades()
        
        positions = []
        for trade in trades:
            direction = TradeDirection.LONG if trade.units > 0 else TradeDirection.SHORT
            positions.append(OpenPosition(
                pair=trade.instrument,
                direction=direction,
                entry_price=trade.price,
                entry_time=trade.open_time,
                size=abs(trade.units)
            ))
        
        return positions
        
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return []


def execute_trade(signal: TradingSignal, decision) -> Dict:
    """Execute a trade based on the signal and decision"""
    if oanda_client is None:
        return {"error": "OANDA client not initialized"}
    
    try:
        config = DEFAULT_CONFIG
        
        # Calculate stop loss
        if config.risk.USE_ATR_STOP and signal.atr_value:
            stop_distance = signal.atr_value * config.risk.ATR_MULTIPLIER
        else:
            pip_size = oanda_client.PIP_SIZES.get(signal.instrument, 0.0001)
            stop_distance = config.risk.FIXED_STOP_PIPS * pip_size
        
        # Calculate position size
        stop_pips = stop_distance / oanda_client.PIP_SIZES.get(signal.instrument, 0.0001)
        units = oanda_client.calculate_position_size(
            signal.instrument,
            stop_pips,
            config.risk.RISK_PER_TRADE_PERCENT
        )
        
        # Determine direction
        if signal.signal_type == SignalType.SELL:
            units = -units
        
        # Calculate SL and TP prices
        if signal.signal_type == SignalType.BUY:
            stop_loss = signal.entry_price - stop_distance
            take_profit = signal.entry_price + (stop_distance * config.risk.RISK_REWARD_RATIO)
        else:
            stop_loss = signal.entry_price + stop_distance
            take_profit = signal.entry_price - (stop_distance * config.risk.RISK_REWARD_RATIO)
        
        # Place order
        result = oanda_client.place_market_order(
            instrument=signal.instrument,
            units=units,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit
        )
        
        logger.info(f"Trade executed: {signal.instrument} {units} units")
        
        return {
            "success": True,
            "instrument": signal.instrument,
            "units": units,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        return {"error": str(e)}


# ==================== API Routes ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(ZoneInfo("UTC")).isoformat(),
        "rule_engine": rule_engine is not None,
        "oanda_client": oanda_client is not None
    })


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Main webhook endpoint for TradingView alerts.
    
    Receives alert, evaluates against rules, and executes trade if approved.
    """
    logger.info("Webhook received")
    
    # Get data
    try:
        if request.is_json:
            data = request.json
        else:
            # Try to parse as JSON string
            data = json.loads(request.data.decode())
    except Exception as e:
        logger.error(f"Error parsing webhook data: {e}")
        return jsonify({"error": "Invalid JSON"}), 400
    
    logger.info(f"Alert data: {json.dumps(data, indent=2)}")
    
    # Parse signal
    signal = parse_tradingview_alert(data)
    if signal is None:
        return jsonify({"error": "Could not parse signal"}), 400
    
    logger.info(f"Parsed signal: {signal.instrument} {signal.signal_type.value}")
    
    # Get current positions
    open_positions = get_open_positions()
    
    # Evaluate against rules
    decision = rule_engine.evaluate_signal(signal, open_positions)
    
    response = {
        "signal": {
            "instrument": signal.instrument,
            "action": signal.signal_type.value,
            "rsi": signal.rsi_value,
            "autotrend": signal.autotrend_direction,
            "htf_trend": signal.htf_trend
        },
        "decision": {
            "approved": decision.should_trade,
            "checks_passed": [c.rule_name for c in decision.checks_passed],
            "checks_failed": [
                {"rule": c.rule_name, "reason": c.reason}
                for c in decision.checks_failed
            ]
        }
    }
    
    # Execute trade if approved
    if decision.should_trade:
        trade_result = execute_trade(signal, decision)
        response["trade"] = trade_result
    
    return jsonify(response)


@app.route('/status', methods=['GET'])
def status():
    """Get current trading status"""
    if rule_engine is None:
        return jsonify({"error": "Rule engine not initialized"}), 500
    
    return jsonify(rule_engine.get_status())


@app.route('/positions', methods=['GET'])
def positions():
    """Get current open positions"""
    positions = get_open_positions()
    return jsonify({
        "count": len(positions),
        "positions": [
            {
                "pair": p.pair,
                "direction": p.direction.value,
                "entry_price": p.entry_price,
                "size": p.size
            }
            for p in positions
        ]
    })


@app.route('/close-all', methods=['POST'])
def close_all():
    """Emergency close all positions"""
    if oanda_client is None:
        return jsonify({"error": "OANDA client not initialized"}), 500
    
    try:
        results = oanda_client.close_all_trades()
        return jsonify({
            "success": True,
            "closed": len(results)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/test-signal', methods=['POST'])
def test_signal():
    """
    Test a signal without executing.
    Useful for debugging rule logic.
    """
    try:
        data = request.json
        signal = parse_tradingview_alert(data)
        
        if signal is None:
            return jsonify({"error": "Could not parse signal"}), 400
        
        open_positions = get_open_positions()
        decision = rule_engine.evaluate_signal(signal, open_positions)
        
        return jsonify({
            "would_trade": decision.should_trade,
            "checks_passed": [c.rule_name for c in decision.checks_passed],
            "checks_failed": [
                {"rule": c.rule_name, "reason": c.reason}
                for c in decision.checks_failed
            ]
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== Main ====================

if __name__ == '__main__':
    # Create data directory
    os.makedirs("data", exist_ok=True)
    
    # Initialize components
    initialize_components()
    
    # Get port from environment or default
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"Starting webhook server on port {port}")
    
    # Run server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('DEBUG', 'false').lower() == 'true'
    )
