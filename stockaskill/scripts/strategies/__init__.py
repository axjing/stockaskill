"""Quantitative strategy module."""

from models import Signal

from strategies.aggregator import StrategyAggregator
from strategies.alpha_momentum import AlphaMomentumStrategy
from strategies.base import Strategy
from strategies.contrarian import ContrarianStrategy
from strategies.deep_value import DeepValueStrategy
from strategies.garp import GARPStrategy
from strategies.ma_trend import MATrendStrategy
from strategies.momentum_enhanced import MomentumEnhancedStrategy
from strategies.multi_factor import MultiFactorStrategy

__all__ = [
    "Strategy",
    "Signal",
    "StrategyAggregator",
    "AlphaMomentumStrategy",
    "ContrarianStrategy",
    "DeepValueStrategy",
    "GARPStrategy",
    "MATrendStrategy",
    "MultiFactorStrategy",
    "MomentumEnhancedStrategy",
]
