from unittest.mock import patch


def test_cmd_backtest_uses_cagr_value(capsys):
    from run import cmd_backtest

    mock_result = {
        "pool_size": 10,
        "years": 5,
        "period_start": "2018-01-01",
        "period_end": "2023-01-01",
        "cagr": 0.15,
        "total_return": 0.8,
        "sharpe": 1.2,
        "max_drawdown": -0.12,
        "monthly_avg": 1.1,
    }

    with patch("portfolio.backtest_engine.AlphaMomentumBacktest") as mock_engine:
        mock_engine.return_value.run.return_value = mock_result
        with patch("run._save_report"):
            cmd_backtest(type("Args", (), {"output_dir": "reports", "format": "none"}))

    output = capsys.readouterr().out
    assert "PASS" in output
    assert "15.00%" in output


def test_cmd_scan_fund_warms_nav_history(capsys):
    from run import cmd_scan

    funds = [
        {"code": "510300", "name": "沪深300ETF"},
        {"code": "159915", "name": "创业板ETF"},
    ]
    args = type(
        "Args",
        (),
        {
            "market": "FUND",
            "top": 1,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("run.get_fund_pool", return_value=funds):
        with patch("run.ensure_fund_screen_ready") as mock_ready:
            with patch("run._save_report"):
                cmd_scan(args)

    mock_ready.assert_called_once_with(funds[:1], limit=1)
    output = capsys.readouterr().out
    assert "Scanning funds..." in output


def test_cmd_scan_snapshot_reads_cached_snapshot(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "snapshot",
            "refresh": False,
            "include_incomplete": False,
            "candidates": 0,
            "output_dir": "reports",
            "format": "none",
        },
    )
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.get_snapshot_status.return_value = {
        "market": "A",
        "latest_trade_date": "2026-06-30",
        "needs_refresh": False,
        "status": "fresh",
    }
    scanner.scan_snapshot.return_value = {
        "results": [
            {
                "code": "601318",
                "name": "PingAn",
                "total_score": 81.2,
                "f_score": 7,
            }
        ],
        "summary": {
            "trade_date": "2026-06-30",
            "total_count": 5000,
            "eligible_count": 3200,
            "filtered_count": 1800,
            "data_complete_ratio": 0.8,
            "missing_list_date_count": 10,
            "missing_fundamentals_count": 20,
            "missing_history_count": 30,
            "st_count": 40,
            "bj_count": 50,
            "new_listing_count": 60,
        },
    }

    try:
        with patch("run._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.refresh_snapshot.assert_not_called()
    scanner.scan_top.assert_not_called()
    output = capsys.readouterr().out
    assert "Snapshot date: 2026-06-30" in output
    assert "601318 PingAn: 81.2" in output


def test_cmd_scan_refresh_triggers_snapshot_build(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "snapshot",
            "refresh": True,
            "include_incomplete": False,
            "candidates": 0,
            "output_dir": "reports",
            "format": "none",
        },
    )
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.get_snapshot_status.return_value = {
        "market": "A",
        "latest_trade_date": None,
        "needs_refresh": True,
        "status": "missing",
    }
    scanner.refresh_snapshot.return_value = {
        "trade_date": "2026-06-30",
        "total_count": 100,
        "eligible_count": 80,
        "filtered_count": 20,
        "data_complete_ratio": 0.9,
        "missing_list_date_count": 1,
        "missing_fundamentals_count": 2,
        "missing_history_count": 3,
        "st_count": 4,
        "bj_count": 5,
        "new_listing_count": 6,
        "cache_reused_count": 70,
        "backfilled_count": 10,
        "excluded_count": 20,
        "history_cache_hits": 90,
        "history_fetched_count": 5,
        "history_missing_count": 5,
        "fundamentals_cache_hits": 88,
        "fundamentals_fetched_count": 7,
        "fundamentals_missing_count": 5,
    }
    scanner.scan_snapshot.return_value = {
        "results": [
            {
                "code": "601318",
                "name": "PingAn",
                "total_score": 75.0,
                "f_score": 6,
            }
        ],
        "summary": scanner.refresh_snapshot.return_value,
    }

    try:
        with patch("run._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.refresh_snapshot.assert_called_once_with("A", include_incomplete=False)
    output = capsys.readouterr().out
    assert "Refreshing full-market snapshot first" in output
    assert "Local reuse/backfill" in output


def test_cmd_scan_realtime_uses_candidate_mode(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "realtime",
            "refresh": False,
            "include_incomplete": False,
            "candidates": 123,
            "output_dir": "reports",
            "format": "none",
        },
    )
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.scan_top.return_value = [
        {"code": "601318", "name": "PingAn", "total_score": 70.0, "f_score": 5}
    ]

    try:
        with patch("run._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.scan_top.assert_called_once_with("A", 1, max_candidates=123)
    output = capsys.readouterr().out
    assert "Realtime mode is approximate" in output
