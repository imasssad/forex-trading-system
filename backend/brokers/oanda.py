"""
OANDA Broker Integration
Handles order execution, position management, and account data via OANDA v20 API
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import requests
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class OandaPosition:
    """Represents an open position"""
    id: str
    instrument: str
    units: int  # Positive for long, negative for short
    avg_price: float
    unrealized_pl: float
    current_price: float
    margin_used: float
    
    @property
    def is_long(self) -> bool:
        return self.units > 0
    
    @property
    def direction(self) -> str:
        return "long" if self.is_long else "short"


@dataclass
class OandaTrade:
    """Represents an individual trade"""
    id: str
    instrument: str
    units: int
    price: float
    open_time: str
    unrealized_pl: float
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    trailing_stop_distance: Optional[float] = None
    state: str = "OPEN"


@dataclass
class OandaOrder:
    """Represents a pending order"""
    id: str
    instrument: str
    units: int
    order_type: OrderType
    price: Optional[float]
    state: str
    create_time: str


class OandaClient:
    """
    Client for OANDA v20 REST API.
    Handles authentication, order execution, and position management.
    """
    
    PRACTICE_URL = "https://api-fxpractice.oanda.com"
    LIVE_URL = "https://api-fxtrade.oanda.com"
    
    # Pip values for different pairs (standard lot = 100,000 units)
    PIP_SIZES = {
        "EUR_USD": 0.0001,
        "GBP_USD": 0.0001,
        "AUD_USD": 0.0001,
        "NZD_USD": 0.0001,
        "USD_CHF": 0.0001,
        "USD_CAD": 0.0001,
        "USD_JPY": 0.01,  # JPY pairs have different pip size
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        account_id: Optional[str] = None,
        practice: bool = True
    ):
        """
        Initialize OANDA client.
        
        Args:
            api_key: OANDA API key (or set OANDA_API_KEY env var)
            account_id: OANDA account ID (or set OANDA_ACCOUNT_ID env var)
            practice: Use practice account (True) or live (False)
        """
        self.api_key = api_key or os.getenv("OANDA_API_KEY")
        self.account_id = account_id or os.getenv("OANDA_ACCOUNT_ID")
        self.base_url = self.PRACTICE_URL if practice else self.LIVE_URL
        
        if not self.api_key:
            raise ValueError("OANDA API key required. Set OANDA_API_KEY env var or pass api_key.")
        
        if not self.account_id:
            raise ValueError("OANDA account ID required. Set OANDA_ACCOUNT_ID env var or pass account_id.")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict:
        """Make API request"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = self.session.get(url, params=data)
            elif method == "POST":
                response = self.session.post(url, json=data)
            elif method == "PUT":
                response = self.session.put(url, json=data)
            elif method == "DELETE":
                response = self.session.delete(url)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            error_msg = f"OANDA API error: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg += f" | Response: {json.dumps(error_detail)}"
                except:
                    error_msg += f" | Response: {e.response.text}"
            logger.error(error_msg)
            # Re-raise with enhanced error message
            raise Exception(error_msg) from e
    
    # ==================== Account Methods ====================
    
    def get_account(self) -> Dict:
        """Get account details including balance and margin"""
        return self._request("GET", f"/v3/accounts/{self.account_id}")
    
    def get_account_summary(self) -> Dict:
        """Get account summary"""
        response = self._request("GET", f"/v3/accounts/{self.account_id}/summary")
        return response.get("account", {})
    
    def get_balance(self) -> float:
        """Get current account balance"""
        summary = self.get_account_summary()
        return float(summary.get("balance", 0))
    
    def get_nav(self) -> float:
        """Get net asset value (balance + unrealized P&L)"""
        summary = self.get_account_summary()
        return float(summary.get("NAV", 0))
    
    # ==================== Position Methods ====================
    
    def get_open_positions(self) -> List[OandaPosition]:
        """Get all open positions"""
        response = self._request("GET", f"/v3/accounts/{self.account_id}/openPositions")
        positions = []
        
        for pos in response.get("positions", []):
            instrument = pos["instrument"]
            
            # Combine long and short if both exist
            long_units = int(pos.get("long", {}).get("units", 0))
            short_units = int(pos.get("short", {}).get("units", 0))
            
            if long_units != 0:
                positions.append(OandaPosition(
                    id=f"{instrument}_long",
                    instrument=instrument,
                    units=long_units,
                    avg_price=float(pos["long"].get("averagePrice", 0)),
                    unrealized_pl=float(pos["long"].get("unrealizedPL", 0)),
                    current_price=0,  # Will be filled by pricing call
                    margin_used=float(pos.get("marginUsed", 0))
                ))
            
            if short_units != 0:
                positions.append(OandaPosition(
                    id=f"{instrument}_short",
                    instrument=instrument,
                    units=short_units,
                    avg_price=float(pos["short"].get("averagePrice", 0)),
                    unrealized_pl=float(pos["short"].get("unrealizedPL", 0)),
                    current_price=0,
                    margin_used=float(pos.get("marginUsed", 0))
                ))
        
        return positions
    
    def get_open_trades(self) -> List[OandaTrade]:
        """Get all open trades with their stop/take profit levels"""
        response = self._request("GET", f"/v3/accounts/{self.account_id}/openTrades")
        trades = []
        
        for trade in response.get("trades", []):
            trades.append(OandaTrade(
                id=trade["id"],
                instrument=trade["instrument"],
                units=int(trade["currentUnits"]),
                price=float(trade["price"]),
                open_time=trade["openTime"],
                unrealized_pl=float(trade.get("unrealizedPL", 0)),
                take_profit=float(trade["takeProfitOrder"]["price"]) if "takeProfitOrder" in trade else None,
                stop_loss=float(trade["stopLossOrder"]["price"]) if "stopLossOrder" in trade else None,
                trailing_stop_distance=float(trade["trailingStopLossOrder"]["distance"]) if "trailingStopLossOrder" in trade else None,
                state=trade.get("state", "OPEN")
            ))
        
        return trades
    
    def get_closed_trades(self, count: int = 500) -> List[Dict]:
        """
        Get recent closed trades from transaction history.
        
        Args:
            count: Number of recent transactions to fetch (max 1000)
            
        Returns:
            List of closed trade dictionaries with entry/exit info
        """
        response = self._request(
            "GET",
            f"/v3/accounts/{self.account_id}/transactions",
            {"count": min(count, 1000)}
        )
        
        closed_trades = []
        trade_opens = {}  # Map trade IDs to their open info
        
        # Parse transactions to match opens and closes
        for txn in reversed(response.get("transactions", [])):  # Process oldest first
            txn_type = txn.get("type", "")
            
            # Track trade openings
            if txn_type == "ORDER_FILL" and "tradeOpened" in txn:
                trade_id = txn["tradeOpened"]["tradeID"]
                units = float(txn["units"])
                trade_opens[trade_id] = {
                    "id": trade_id,
                    "instrument": txn["instrument"],
                    "units": abs(units),
                    "entry_price": float(txn["price"]),
                    "open_time": txn["time"],
                    "direction": "long" if units > 0 else "short"
                }
            
            # Track trade closings
            elif txn_type == "ORDER_FILL" and "tradesClosed" in txn and txn["tradesClosed"]:
                for closed in txn["tradesClosed"]:
                    trade_id = closed["tradeID"]
                    if trade_id in trade_opens:
                        trade_info = trade_opens[trade_id].copy()
                        trade_info.update({
                            "exit_price": float(txn["price"]),
                            "close_time": txn["time"],
                            "profit_loss": float(closed.get("realizedPL", 0)),
                            "close_reason": txn.get("reason", "MANUAL")
                        })
                        closed_trades.append(trade_info)
                        # Remove from opens so we don't process again
                        del trade_opens[trade_id]
        
        return closed_trades
    
    # ==================== Pricing Methods ====================
    
    def get_price(self, instrument: str) -> Tuple[float, float]:
        """
        Get current bid/ask price for instrument.
        
        Returns:
            Tuple of (bid, ask)
        """
        response = self._request(
            "GET",
            f"/v3/accounts/{self.account_id}/pricing",
            {"instruments": instrument}
        )
        
        prices = response.get("prices", [{}])[0]
        bid = float(prices.get("bids", [{"price": 0}])[0]["price"])
        ask = float(prices.get("asks", [{"price": 0}])[0]["price"])
        
        return bid, ask
    
    def get_spread_pips(self, instrument: str) -> float:
        """Get current spread in pips"""
        bid, ask = self.get_price(instrument)
        pip_size = self.PIP_SIZES.get(instrument, 0.0001)
        return (ask - bid) / pip_size
    
    # ==================== Order Methods ====================
    
    def calculate_position_size(
        self,
        instrument: str,
        stop_loss_pips: float,
        risk_percent: float = 1.0
    ) -> int:
        """
        Calculate position size based on risk percentage.
        
        Args:
            instrument: Trading pair
            stop_loss_pips: Stop loss distance in pips
            risk_percent: Percentage of account to risk
            
        Returns:
            Position size in units
        """
        balance = self.get_balance()
        risk_amount = balance * (risk_percent / 100)
        
        pip_size = self.PIP_SIZES.get(instrument, 0.0001)
        
        # For JPY pairs, pip value calculation is different
        if "JPY" in instrument:
            # Approximate pip value for JPY pairs
            pip_value_per_unit = pip_size / 100  # Rough estimate
        else:
            pip_value_per_unit = pip_size
        
        # Position size = Risk Amount / (Stop Loss Pips * Pip Value Per Unit)
        if stop_loss_pips > 0:
            units = risk_amount / (stop_loss_pips * pip_value_per_unit)
        else:
            units = 0
        
        # Round down to nearest whole unit
        return int(units)
    
    def place_market_order(
        self,
        instrument: str,
        units: int,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pips: Optional[float] = None
    ) -> Dict:
        """
        Place a market order.
        
        Args:
            instrument: Trading pair (e.g., "EUR_USD")
            units: Positive for buy, negative for sell
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price
            trailing_stop_pips: Trailing stop distance in pips
            
        Returns:
            Order response from OANDA
        """
        # Determine decimal places based on instrument
        # JPY pairs use 3 decimal places, others use 5
        decimals = 3 if "JPY" in instrument else 5
        
        order_data = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units),
                "timeInForce": "FOK",  # Fill or Kill
                "positionFill": "DEFAULT"
            }
        }
        
        # Add stop loss
        if stop_loss_price is not None:
            order_data["order"]["stopLossOnFill"] = {
                "price": f"{stop_loss_price:.{decimals}f}"
            }
        
        # Add take profit
        if take_profit_price is not None:
            order_data["order"]["takeProfitOnFill"] = {
                "price": f"{take_profit_price:.{decimals}f}"
            }
        
        # Add trailing stop
        if trailing_stop_pips is not None:
            pip_size = self.PIP_SIZES.get(instrument, 0.0001)
            distance = trailing_stop_pips * pip_size
            order_data["order"]["trailingStopLossOnFill"] = {
                "distance": f"{distance:.{decimals}f}"
            }
        
        logger.info(f"Placing market order: {units} {instrument}")
        return self._request("POST", f"/v3/accounts/{self.account_id}/orders", order_data)
    
    def modify_trade(
        self,
        trade_id: str,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pips: Optional[float] = None,
        instrument: Optional[str] = None
    ) -> Dict:
        """
        Modify stop loss, take profit, or trailing stop on an open trade.
        
        Args:
            trade_id: ID of the trade to modify
            stop_loss_price: New stop loss price
            take_profit_price: New take profit price  
            trailing_stop_pips: Trailing stop distance in pips
            instrument: Instrument (needed for pip and decimal calculation)
        """
        # Determine decimal places based on instrument
        decimals = 3 if instrument and "JPY" in instrument else 5
        
        data = {}
        
        if stop_loss_price is not None:
            data["stopLoss"] = {"price": f"{stop_loss_price:.{decimals}f}"}
        
        if take_profit_price is not None:
            data["takeProfit"] = {"price": f"{take_profit_price:.{decimals}f}"}
        
        if trailing_stop_pips is not None and instrument:
            pip_size = self.PIP_SIZES.get(instrument, 0.0001)
            distance = trailing_stop_pips * pip_size
            data["trailingStopLoss"] = {"distance": f"{distance:.{decimals}f}"}
        
        logger.info(f"Modifying trade {trade_id}: {data}")
        return self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/trades/{trade_id}/orders",
            data
        )
    
    def close_trade(
        self,
        trade_id: str,
        units: Optional[int] = None
    ) -> Dict:
        """
        Close a trade (fully or partially).
        
        Args:
            trade_id: ID of trade to close
            units: Number of units to close (None = close all)
        """
        data = {}
        if units is not None:
            data["units"] = str(abs(units))
        
        logger.info(f"Closing trade {trade_id}, units: {units or 'ALL'}")
        return self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/trades/{trade_id}/close",
            data if data else None
        )
    
    def close_all_trades(self, instrument: Optional[str] = None) -> List[Dict]:
        """Close all open trades, optionally filtered by instrument"""
        trades = self.get_open_trades()
        results = []
        
        for trade in trades:
            if instrument is None or trade.instrument == instrument:
                result = self.close_trade(trade.id)
                results.append(result)
        
        return results
    
    # ==================== Historical Data ====================
    
    def get_candles(
        self,
        instrument: str,
        granularity: str = "M15",
        count: int = 100,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None
    ) -> List[Dict]:
        """
        Get historical candlestick data.
        
        Args:
            instrument: Trading pair
            granularity: Timeframe (M1, M5, M15, M30, H1, H4, D)
            count: Number of candles (max 5000)
            from_time: Start time (RFC3339 format)
            to_time: End time (RFC3339 format)
            
        Returns:
            List of candle dictionaries with OHLC data
        """
        params = {
            "granularity": granularity,
            "count": count
        }
        
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        
        response = self._request(
            "GET",
            f"/v3/instruments/{instrument}/candles",
            params
        )
        
        candles = []
        for c in response.get("candles", []):
            if c.get("complete", True):  # Only include complete candles
                mid = c.get("mid", {})
                candles.append({
                    "time": c["time"],
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                    "volume": int(c.get("volume", 0))
                })
        
        return candles
    
    # ==================== ATR Calculation ====================
    
    def calculate_atr(
        self,
        instrument: str,
        period: int = 14,
        granularity: str = "M15"
    ) -> float:
        """
        Calculate Average True Range for an instrument.
        
        Args:
            instrument: Trading pair
            period: ATR period
            granularity: Timeframe for calculation
            
        Returns:
            ATR value in price units
        """
        # Need period + 1 candles for ATR calculation
        candles = self.get_candles(instrument, granularity, count=period + 1)
        
        if len(candles) < period + 1:
            logger.warning(f"Not enough candles for ATR calculation")
            return 0.0
        
        true_ranges = []
        
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i-1]["close"]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        # Simple moving average of true ranges
        atr = sum(true_ranges[-period:]) / period
        
        return atr
    
    def calculate_atr_pips(
        self,
        instrument: str,
        period: int = 14,
        granularity: str = "M15"
    ) -> float:
        """Calculate ATR in pips"""
        atr = self.calculate_atr(instrument, period, granularity)
        pip_size = self.PIP_SIZES.get(instrument, 0.0001)
        return atr / pip_size


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # This will fail without valid credentials, but shows the API
    print("OANDA Client initialized.")
    print("Set OANDA_API_KEY and OANDA_ACCOUNT_ID environment variables to use.")
    
    # Example of what calls would look like:
    """
    client = OandaClient(practice=True)
    
    # Get account info
    balance = client.get_balance()
    print(f"Account balance: ${balance:.2f}")
    
    # Get current price
    bid, ask = client.get_price("EUR_USD")
    print(f"EUR/USD: {bid}/{ask}")
    
    # Calculate position size
    units = client.calculate_position_size(
        "EUR_USD",
        stop_loss_pips=10,
        risk_percent=1.0
    )
    print(f"Position size for 1% risk, 10 pip SL: {units} units")
    
    # Get ATR
    atr = client.calculate_atr_pips("EUR_USD", period=14)
    print(f"EUR/USD 14-period ATR: {atr:.1f} pips")
    
    # Place an order (CAREFUL - this would be real!)
    # result = client.place_market_order(
    #     "EUR_USD",
    #     units=1000,  # Buy 1000 units
    #     stop_loss_price=1.0800,
    #     take_profit_price=1.0950
    # )
    """
