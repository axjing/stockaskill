"""Pure-Python config with dot-path access. No YAML dependency."""

from typing import Any, Dict

_DEFAULTS: Dict[str, Any] = {
    "watchlist": ["002475", "600519", "601318", "000858", "600036"],
    "factor_weights": {
        "value": 0.2,
        "quality": 0.25,
        "growth": 0.17,
        "momentum": 0.17,
        "low_vol": 0.11,
        "size": 0.09,
    },
    "enhanced_weights": {
        "momentum": 0.35,
        "low_vol": 0.18,
        "quality": 0.20,
        "value": 0.17,
        "growth": 0.10,
    },
    "etf_core": [
        {"code": "510300", "name": "沪深300ETF", "target": 0.17},
        {"code": "159915", "name": "创业板ETF", "target": 0.12},
        {"code": "588000", "name": "科创50ETF", "target": 0.11},
    ],
    "strategy_target": {
        "cagr": 0.18,
        "max_drawdown": 0.20,
        "max_positions": 6,
    },
    "cache_ttl": {
        "realtime": 60,
        "daily_kline": 3600,
        "financial": 604800,
        "sentiment": 3600,
        "pool": 86400,
        "fund_nav": 3600,
    },
    "daily_api_limit": 500,
    "scan_max_candidates": 200,
    "request_interval": [0.5, 2.0],
    "retry_max": 3,
    "retry_base": 2,
    "kline_years": 3,
    "financial_reports": 8,
    "low_vol_min": 0.4,
    "commission": 0.0003,
    "stamp_tax": 0.001,
    "slippage": 0.001,
    "factor_ranges": {
        "value": {
            "A": {"pe": [5, 80], "pb": [0.5, 10], "dy": [0, 6]},
            "HK": {"pe": [2, 60], "pb": [0.2, 8], "dy": [0, 8]},
            "US": {"pe": [5, 100], "pb": [0.5, 15], "dy": [0, 4]},
        },
        "size": {
            "A": {"mcap": [23.03, 28.73]},
            "HK": {"mcap": [22.33, 29.53]},
            "US": {"mcap": [24.63, 31.93]},
        },
        "low_vol": {
            "A": {"vol": [0.01, 0.05], "max_drop": [0.03, 0.10]},
            "HK": {"vol": [0.015, 0.06], "max_drop": [0.03, 0.12]},
            "US": {"vol": [0.015, 0.07], "max_drop": [0.04, 0.15]},
        },
        "growth": {
            "A": {"revenue": [-0.5, 1.0], "profit": [-0.8, 2.0], "accel": [-0.3, 0.3]},
            "HK": {"revenue": [-0.6, 1.0], "profit": [-1.0, 2.0], "accel": [-0.3, 0.3]},
            "US": {"revenue": [-0.4, 1.0], "profit": [-0.8, 1.5], "accel": [-0.2, 0.4]},
        },
        "quality": {
            "A": {"roe": [-0.2, 0.4], "gross_margin": [0, 0.8], "debt": [0, 1], "net_margin": [-0.1, 0.3]},
            "HK": {"roe": [-0.15, 0.35], "gross_margin": [0, 0.7], "debt": [0, 1], "net_margin": [-0.1, 0.4]},
            "US": {"roe": [-0.25, 0.5], "gross_margin": [0, 0.85], "debt": [0, 1], "net_margin": [-0.15, 0.35]},
        },
        "momentum": {
            "A": {"ret_6m": [-0.4, 0.8]},
            "HK": {"ret_6m": [-0.5, 0.9]},
            "US": {"ret_6m": [-0.5, 1.0]},
        },
    },
}

_cache: Dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* and return *base*."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> Dict[str, Any]:
    """Return cached defaults. Supports env override via STOCKSKILL_CONFIG."""
    global _cache
    if _cache is not None:
        return _cache
    _cache = dict(_DEFAULTS)
    return _cache


def get(key: str, default: Any = None) -> Any:
    """Dot-path access: get('factor_weights.value') -> 0.18."""
    parts = key.split(".")
    val: Any = load_config()
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p, default)
        else:
            return default
    return val
