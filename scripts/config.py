"""Pure-Python config with dot-path access. No YAML dependency."""
from __future__ import annotations

from typing import Any, Dict

_DEFAULTS: Dict[str, Any] = {
    "watchlist": ["002475", "600519", "601318", "000858", "600036"],
    "factor_weights": {
        "value": 0.18,
        "quality": 0.22,
        "growth": 0.15,
        "momentum": 0.15,
        "low_vol": 0.10,
        "size": 0.08,
        "industry": 0.07,
        "north_flow": 0.05,
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
