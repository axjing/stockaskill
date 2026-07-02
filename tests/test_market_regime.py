from unittest.mock import patch


def _benchmark_rows(start: float = 100.0, step: float = 1.0, count: int = 140):
    rows = []
    for index in range(count):
        close = start + step * index
        rows.append(
            {
                "date": f"2026-01-{(index % 28) + 1:02d}",
                "close": close,
            }
        )
    return list(reversed(rows))


def _stock_rows(base: float = 100.0, count: int = 80):
    rows = []
    for index in range(count):
        close = base + index * 0.5
        rows.append(
            {
                "date": f"2026-02-{(index % 28) + 1:02d}",
                "close": close,
            }
        )
    return list(reversed(rows))


@patch("market_regime.get_stock_pool")
@patch("market_regime.get_kline")
@patch("market_regime.get_market_index")
@patch("market_regime.ensure_market_index_ready")
def test_analyze_market_regime_returns_offensive_posture(
    mock_ready,
    mock_index,
    mock_kline,
    mock_pool,
):
    from market_regime import analyze_market_regime

    mock_index.return_value = _benchmark_rows()
    mock_pool.return_value = [
        {"code": f"{600000 + index}", "is_active": 1} for index in range(30)
    ]
    mock_kline.return_value = _stock_rows()

    regime = analyze_market_regime("A")

    assert regime["status"] == "ok"
    assert regime["posture"] in {"offensive", "constructive"}
    assert regime["risk_budget"] >= 0.85
    assert regime["breadth"]["sample_size"] >= 15
    assert regime["confidence"]["level"] in {"high", "medium"}
    assert regime["provenance"]["scope"] == "market_regime"


@patch("market_regime.get_market_index", return_value=[])
@patch("market_regime.ensure_market_index_ready")
def test_analyze_market_regime_handles_insufficient_benchmark_history(
    mock_ready,
    mock_index,
):
    from market_regime import analyze_market_regime

    regime = analyze_market_regime("A")

    assert regime["status"] == "insufficient_data"
    assert regime["posture"] == "neutral"
    assert regime["risk_budget"] == 0.65
    assert regime["confidence"]["level"] == "low"
