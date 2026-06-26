"""Position sizing models: Kelly formula and fixed fraction."""

import math
from typing import Any, Dict

from models import Position


def kelly_fraction(win_prob: float, avg_win: float, avg_loss: float) -> float:
    """Calculate Kelly fraction.

    Args:
        win_prob: Probability of winning [0, 1].
        avg_win: Average win amount (positive).
        avg_loss: Average loss amount (positive).

    Returns:
        Kelly fraction f = (bp - q) / b, clipped to [0, 0.25].
    """
    if avg_loss <= 0 or win_prob <= 0:
        return 0.0
    b = avg_win / avg_loss  # odds
    p = win_prob
    q = 1 - p
    f = (b * p - q) / b
    # Use half-Kelly for safety, cap at 25%
    return max(0, min(0.25, f * 0.5))


def fixed_fraction(
    capital: float, risk_per_trade: float = 0.02,
    stop_loss_pct: float = 0.05,
) -> float:
    """Calculate position size using fixed fraction method.

    Args:
        capital: Total portfolio capital.
        risk_per_trade: Max risk per trade as fraction of capital.
        stop_loss_pct: Stop loss percentage.

    Returns:
        Position size in currency units.
    """
    if stop_loss_pct <= 0:
        return capital * risk_per_trade
    return (capital * risk_per_trade) / stop_loss_pct


def compute_position(
    code: str, name: str, market: str,
    capital: float, score: float,
    current_price: float,
    method: str = "kelly",
    max_weight: float = 0.20,
) -> Position:
    """Compute position sizing for a stock.

    Args:
        code: Stock code.
        name: Stock name.
        market: Market identifier.
        capital: Total portfolio capital.
        score: Strategy score (0-100).
        current_price: Current stock price.
        method: 'kelly' or 'fixed'.
        max_weight: Maximum position weight.

    Returns:
        Position dataclass instance.
    """
    if current_price <= 0:
        return Position(
            code=code, name=name, market=market,
            weight=0, shares=0, cost=0, current_price=0,
        )

    if method == "kelly":
        # Estimate win_prob from score
        win_prob = min(0.9, max(0.1, score / 100))
        avg_win = 0.15  # Assume 15% avg win
        avg_loss = 0.08  # Assume 8% avg loss
        weight = kelly_fraction(win_prob, avg_win, avg_loss)
    else:
        weight = score / 100 * 0.20  # Max 20% for perfect score

    weight = min(weight, max_weight)
    allocation = capital * weight
    shares = int(allocation / current_price)
    # Round to board lots (100 for A-shares)
    shares = (shares // 100) * 100

    return Position(
        code=code, name=name, market=market,
        weight=weight, shares=shares,
        cost=current_price, current_price=current_price,
    )
