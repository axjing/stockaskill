"""Asset allocation strategies."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np


def equal_weights(n: int) -> List[float]:
    """Equal weight allocation."""
    if n <= 0:
        return []
    return [1.0 / n] * n


def risk_parity(
    cov_matrix: np.ndarray,
    target_vol: float = 0.10,
) -> List[float]:
    """Risk parity allocation: equal risk contribution.

    Args:
        cov_matrix: Covariance matrix of asset returns.
        target_vol: Target portfolio volatility.

    Returns:
        Weight list summing to 1.
    """
    n = cov_matrix.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    # Initialize with equal weights
    weights = np.ones(n) / n

    # Simple iterative risk parity (approximation)
    for _ in range(100):
        risk_contrib = weights * (cov_matrix @ weights)
        total_risk = risk_contrib.sum()
        if total_risk <= 0:
            break
        target_contrib = total_risk / n
        weights = weights * np.sqrt(target_contrib / np.maximum(risk_contrib, 1e-10))
        weights = weights / weights.sum()

    # Scale to target volatility
    port_vol = np.sqrt(weights @ cov_matrix @ weights)
    if port_vol > 0:
        weights = weights * target_vol / port_vol

    weights = np.maximum(weights, 0)
    weights = weights / weights.sum()
    return weights.tolist()


def min_variance(
    cov_matrix: np.ndarray,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> List[float]:
    """Minimum variance portfolio (analytical solution).

    Args:
        cov_matrix: Covariance matrix.
        min_weight: Minimum weight per asset.
        max_weight: Maximum weight per asset.

    Returns:
        Weight list summing to 1.
    """
    n = cov_matrix.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    try:
        cov_inv = np.linalg.inv(cov_matrix)
        ones = np.ones(n)
        weights = cov_inv @ ones
        denom = ones @ cov_inv @ ones
        if denom == 0:
            return equal_weights(n)
        weights = weights / denom
    except np.linalg.LinAlgError:
        return equal_weights(n)

    # Clip weights
    weights = np.clip(weights, min_weight, max_weight)
    weights = weights / weights.sum()
    return weights.tolist()


def signal_weighted(
    scores: List[float],
    min_weight: float = 0.02,
    max_weight: float = 0.30,
) -> List[float]:
    """Weight assets proportional to strategy scores.

    Args:
        scores: List of scores (0-100).
        min_weight: Minimum weight.
        max_weight: Maximum weight.

    Returns:
        Weight list summing to 1.
    """
    if not scores:
        return []
    # Use softmax-like weighting
    scores_arr = np.array(scores, dtype=float)
    # Shift to positive
    scores_arr = np.maximum(scores_arr, 0)
    total = scores_arr.sum()
    if total <= 0:
        return equal_weights(len(scores))

    weights = scores_arr / total
    # Clip
    weights = np.clip(weights, min_weight, max_weight)
    weights = weights / weights.sum()
    return weights.tolist()
