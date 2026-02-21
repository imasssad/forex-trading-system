"""
Correlation Filter Module
Prevents taking trades on pairs that would duplicate exposure
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class OpenPosition:
    """Represents an open trading position"""
    pair: str
    direction: TradeDirection
    entry_price: float
    entry_time: str
    size: float


class CorrelationFilter:
    """
    Checks if a new trade would create duplicate exposure based on
    pair correlations with existing open positions.
    """
    
    # Positive correlations - pairs that move in same direction
    POSITIVE_CORRELATIONS = {
        ("EUR_USD", "GBP_USD"): 0.91,
        ("EUR_USD", "AUD_USD"): 0.79,
        ("GBP_USD", "AUD_USD"): 0.74,
        ("GBP_USD", "NZD_USD"): 0.73,
        ("AUD_USD", "NZD_USD"): 0.85,
        ("USD_CHF", "USD_CAD"): 0.81,
    }
    
    # Negative correlations - pairs that move in opposite directions
    NEGATIVE_CORRELATIONS = {
        ("EUR_USD", "USD_CHF"): -0.99,
        ("EUR_USD", "USD_CAD"): -0.82,
        ("GBP_USD", "USD_CHF"): -0.88,
        ("GBP_USD", "USD_CAD"): -0.89,
        ("AUD_USD", "USD_CHF"): -0.79,
        ("NZD_USD", "USD_CAD"): -0.80,
    }
    
    # Risk-on cluster - treat as similar trades
    RISK_ON_CLUSTER = {"EUR_USD", "GBP_USD", "AUD_USD", "NZD_USD"}
    
    # Safe-haven / commodity cluster
    SAFE_HAVEN_CLUSTER = {"USD_CHF", "USD_CAD", "USD_JPY"}
    
    def __init__(self, correlation_threshold: float = 0.70):
        """
        Initialize correlation filter.
        
        Args:
            correlation_threshold: Minimum correlation to consider pairs as "mirroring"
        """
        self.threshold = correlation_threshold
        self._build_correlation_map()
    
    def _build_correlation_map(self):
        """Build a quick lookup map for correlations"""
        self.correlation_map: Dict[Tuple[str, str], float] = {}
        
        # Add positive correlations (both directions for easy lookup)
        for (pair1, pair2), corr in self.POSITIVE_CORRELATIONS.items():
            self.correlation_map[(pair1, pair2)] = corr
            self.correlation_map[(pair2, pair1)] = corr
        
        # Add negative correlations
        for (pair1, pair2), corr in self.NEGATIVE_CORRELATIONS.items():
            self.correlation_map[(pair1, pair2)] = corr
            self.correlation_map[(pair2, pair1)] = corr
    
    def get_correlation(self, pair1: str, pair2: str) -> Optional[float]:
        """
        Get correlation between two pairs.
        
        Returns:
            Correlation coefficient or None if not tracked
        """
        return self.correlation_map.get((pair1, pair2))
    
    def would_duplicate_exposure(
        self,
        new_pair: str,
        new_direction: TradeDirection,
        open_positions: List[OpenPosition]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a new trade would create duplicate exposure.
        
        Rules:
        1. Positively correlated pairs in SAME direction = duplicate
        2. Negatively correlated pairs in OPPOSITE direction = duplicate
        
        Args:
            new_pair: The pair we want to trade
            new_direction: Direction of proposed trade
            open_positions: List of current open positions
            
        Returns:
            Tuple of (is_duplicate, reason_string)
        """
        if not open_positions:
            return False, None
        
        for position in open_positions:
            # Check if same pair
            if position.pair == new_pair:
                return True, f"Already have position in {new_pair}"
            
            correlation = self.get_correlation(new_pair, position.pair)
            
            if correlation is None:
                # No known correlation - allow trade
                continue
            
            abs_correlation = abs(correlation)
            
            if abs_correlation < self.threshold:
                # Correlation below threshold - allow trade
                continue
            
            # Positive correlation check
            if correlation > 0:
                # Same direction on positively correlated pairs = duplicate
                if new_direction == position.direction:
                    return True, (
                        f"Duplicate exposure: {new_pair} {new_direction.value} mirrors "
                        f"existing {position.pair} {position.direction.value} "
                        f"(correlation: {correlation:.2f})"
                    )
            
            # Negative correlation check
            else:
                # Opposite direction on negatively correlated pairs = duplicate
                # (e.g., LONG EUR/USD + SHORT USD/CHF is same bet)
                if new_direction != position.direction:
                    return True, (
                        f"Duplicate exposure: {new_pair} {new_direction.value} mirrors "
                        f"existing {position.pair} {position.direction.value} "
                        f"(inverse correlation: {correlation:.2f})"
                    )
        
        return False, None
    
    def get_allowed_pairs(
        self,
        direction: TradeDirection,
        open_positions: List[OpenPosition],
        available_pairs: List[str]
    ) -> List[str]:
        """
        Get list of pairs that can be traded without creating duplicate exposure.
        
        Args:
            direction: Direction of proposed trade
            open_positions: Current open positions
            available_pairs: All pairs we're allowed to trade
            
        Returns:
            List of pairs that would not duplicate exposure
        """
        allowed = []
        
        for pair in available_pairs:
            is_duplicate, _ = self.would_duplicate_exposure(
                pair, direction, open_positions
            )
            if not is_duplicate:
                allowed.append(pair)
        
        return allowed
    
    def analyze_portfolio_exposure(
        self,
        open_positions: List[OpenPosition]
    ) -> Dict:
        """
        Analyze current portfolio exposure by currency and direction.
        
        Returns:
            Dictionary with exposure analysis
        """
        exposure = {
            "USD": 0,
            "EUR": 0,
            "GBP": 0,
            "JPY": 0,
            "AUD": 0,
            "NZD": 0,
            "CHF": 0,
            "CAD": 0,
        }
        
        for position in open_positions:
            if "_" not in position.pair:
                logger.warning(f"Skipping malformed pair in portfolio analysis: {position.pair}")
                continue
            base, quote = position.pair.split("_")
            multiplier = 1 if position.direction == TradeDirection.LONG else -1

            # Long EUR/USD = +EUR, -USD
            exposure[base] = exposure.get(base, 0) + multiplier
            exposure[quote] = exposure.get(quote, 0) - multiplier
        
        return {
            "currency_exposure": exposure,
            "net_usd_exposure": exposure["USD"],
            "position_count": len(open_positions),
            "risk_on_exposure": sum(
                1 for p in open_positions 
                if p.pair in self.RISK_ON_CLUSTER and p.direction == TradeDirection.LONG
            ),
        }


# Example usage and testing
if __name__ == "__main__":
    filter = CorrelationFilter(correlation_threshold=0.70)
    
    # Test scenarios
    test_positions = [
        OpenPosition(
            pair="EUR_USD",
            direction=TradeDirection.LONG,
            entry_price=1.0850,
            entry_time="2024-01-15T10:00:00Z",
            size=10000
        )
    ]
    
    # Test 1: GBP/USD LONG should be blocked (positive correlation, same direction)
    is_dup, reason = filter.would_duplicate_exposure(
        "GBP_USD", TradeDirection.LONG, test_positions
    )
    print(f"GBP/USD LONG with EUR/USD LONG: blocked={is_dup}")
    print(f"  Reason: {reason}")
    
    # Test 2: USD/CHF LONG should be allowed (negative correlation, same direction)
    is_dup, reason = filter.would_duplicate_exposure(
        "USD_CHF", TradeDirection.LONG, test_positions
    )
    print(f"\nUSD/CHF LONG with EUR/USD LONG: blocked={is_dup}")
    print(f"  Reason: {reason}")
    
    # Test 3: USD/CHF SHORT should be blocked (negative correlation, opposite direction)
    is_dup, reason = filter.would_duplicate_exposure(
        "USD_CHF", TradeDirection.SHORT, test_positions
    )
    print(f"\nUSD/CHF SHORT with EUR/USD LONG: blocked={is_dup}")
    print(f"  Reason: {reason}")
    
    # Test 4: USD/JPY should be allowed (low correlation)
    is_dup, reason = filter.would_duplicate_exposure(
        "USD_JPY", TradeDirection.LONG, test_positions
    )
    print(f"\nUSD/JPY LONG with EUR/USD LONG: blocked={is_dup}")
    print(f"  Reason: {reason}")
