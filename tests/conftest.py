import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_repo_root = Path(__file__).resolve().parent.parent
_scripts = _repo_root / "stockaskill" / "scripts"
_skill_root = _repo_root / "stockaskill"

if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
if str(_skill_root) not in sys.path:
    sys.path.insert(0, str(_skill_root))


@pytest.fixture
def mock_fundamentals() -> Dict[str, Any]:
    return {
        "code": "601318",
        "date": "2025-01-01",
        "market_cap": 1.2e12,
        "pe_ttm": 8.5,
        "pe_static": 8.0,
        "pb": 0.95,
        "ps_ttm": 1.5,
        "pcf_ttm": 5.0,
        "dividend_yield": 4.2,
        "roe": 0.15,
        "roa": 0.05,
        "gross_margin": 0.35,
        "net_margin": 0.20,
        "revenue_growth": 0.12,
        "profit_growth": 0.15,
        "debt_ratio": 0.40,
        "current_ratio": 1.5,
        "eps": 8.0,
        "bvps": 50.0,
    }


@pytest.fixture
def mock_kline_rising() -> List[Dict[str, Any]]:
    kline = []
    price = 60.0
    for i in range(250):
        price *= 1.001 + (i % 5) * 0.0005
        kline.append({
            "date": f"2024-{i//30+1:02d}-{(i%30)+1:02d}",
            "open": price * 0.99,
            "high": price * 1.02,
            "low": price * 0.98,
            "close": price,
            "volume": 1e7 + i * 1000,
            "amount": price * (1e7 + i * 1000),
        })
    return kline


@pytest.fixture
def mock_kline_declining() -> List[Dict[str, Any]]:
    kline = []
    price = 100.0
    for i in range(250):
        price *= 0.998
        kline.append({
            "date": f"2024-{i//30+1:02d}-{(i%30)+1:02d}",
            "open": price * 1.01,
            "high": price * 1.02,
            "low": price * 0.99,
            "close": price,
            "volume": 1e7 - i * 1000,
            "amount": price * (1e7 - i * 1000),
        })
    return kline
