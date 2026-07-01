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


def test_cmd_scan_fund_warms_etf_scope(capsys):
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

    with patch("run.get_etf_pool", return_value=funds):
        with patch("run.ensure_etf_ready") as mock_ready:
            with patch("run._save_report"):
                cmd_scan(args)

    mock_ready.assert_called_once_with(["510300"], limit=1)
    output = capsys.readouterr().out
    assert "Scanning ETFs..." in output


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
            "metadata_quality": {"complete": 100, "partial": 50, "low": 10},
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
    assert "Metadata quality: complete=100, partial=50, low=10" in output
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


def test_cmd_scan_auto_falls_back_to_realtime_when_snapshot_missing(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "auto",
            "refresh": False,
            "include_incomplete": False,
            "candidates": 88,
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
    scanner.scan_top.return_value = [
        {"code": "601318", "name": "PingAn", "total_score": 78.0, "f_score": 6}
    ]

    try:
        with patch("run._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.scan_top.assert_called_once_with("A", 1, max_candidates=88)
    scanner.refresh_snapshot.assert_not_called()
    output = capsys.readouterr().out
    assert "回退到有界 realtime candidate scan" in output
    assert "601318 PingAn: 78.0" in output


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


def test_cmd_sync_symbol_reports_summary(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "symbol",
            "code": "601318",
            "market": "A",
            "days": 365,
            "skip_fundamentals": False,
            "full_history": False,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("run.sync_symbol_data") as mock_sync:
        mock_sync.return_value = {
            "code": "601318",
            "market": "A",
            "history_before": 10,
            "history_after": 365,
            "history_ready": True,
            "history_covered_through": "2026-07-01",
            "fundamentals_required": True,
            "fundamentals_before": False,
            "fundamentals_after": True,
            "fundamentals_covered_through": "2026-07-01",
            "ready": True,
            "errors": [],
        }
        with patch("run._save_report"):
            cmd_sync(args)

    output = capsys.readouterr().out
    assert "Synchronizing symbol 601318" in output
    assert "History: before=10, after=365" in output
    assert "Ready: yes" in output


def test_cmd_sync_watchlist_reports_scope_summary(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "watchlist",
            "market": "A",
            "days": 365,
            "skip_fundamentals": False,
            "full_history": False,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("run.sync_watchlist_data") as mock_sync:
        mock_sync.return_value = {
            "requested": 3,
            "ready": 2,
            "cache_hits": 1,
            "history_fetched_count": 2,
            "fundamentals_fetched_count": 1,
            "covered_through": "2026-07-01",
            "missing_codes": ["600519"],
            "symbols": [],
        }
        with patch("run._save_report"):
            cmd_sync(args)

    output = capsys.readouterr().out
    assert "Synchronizing watchlist" in output
    assert "Scope watchlist: requested=3, ready=2" in output
    assert "Missing codes: 600519" in output


def test_cmd_sync_portfolio_uses_codes(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "portfolio",
            "codes": "600519,000858",
            "market": "A",
            "days": 365,
            "skip_fundamentals": False,
            "full_history": False,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("run.sync_portfolio_data") as mock_sync:
        mock_sync.return_value = {
            "requested": 2,
            "ready": 2,
            "cache_hits": 2,
            "history_fetched_count": 0,
            "fundamentals_fetched_count": 0,
            "covered_through": "2026-07-01",
            "missing_codes": [],
            "symbols": [],
        }
        with patch("run._save_report"):
            cmd_sync(args)

    mock_sync.assert_called_once_with(
        ["600519", "000858"],
        market="A",
        history_days=365,
        need_fundamentals=True,
        full_history=False,
    )


def test_cmd_sync_etf_uses_etf_scope(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "etf",
            "codes": "510300,159915",
            "days": 365,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("run.sync_etf_data") as mock_sync:
        mock_sync.return_value = {
            "requested": 2,
            "ready": 2,
            "cache_hits": 1,
            "history_fetched_count": 1,
            "fundamentals_fetched_count": 0,
            "covered_through": "2026-07-01",
            "missing_codes": [],
            "symbols": [],
        }
        with patch("run._save_report"):
            cmd_sync(args)

    mock_sync.assert_called_once_with(
        ["510300", "159915"],
        history_days=365,
    )
    output = capsys.readouterr().out
    assert "Synchronizing ETFs (2 symbols, days=365)" in output
    assert "Scope etf: requested=2, ready=2" in output


def test_cmd_status_symbol_reads_sync_state(capsys):
    from run import cmd_status

    args = type(
        "Args",
        (),
        {
            "type": "symbol",
            "code": "601318",
            "market": "A",
        },
    )

    with patch("run.get_cache") as mock_get_cache, patch(
        "run.get_stock_pool"
    ) as mock_pool:
        mock_pool.return_value = [
            {
                "code": "601318",
                "metadata_completeness": 1.0,
                "metadata_source": "manual",
                "metadata_status": "active",
                "is_active": 1,
            }
        ]
        mock_get_cache.return_value.get_sync_state.return_value = [
            {
                "data_kind": "history",
                "code": "601318",
                "status": "ok",
                "last_covered_date": "2026-07-01",
                "last_success_at": "2026-07-01 10:00:00",
                "last_error": "",
            }
        ]
        cmd_status(args)

    output = capsys.readouterr().out
    assert "Sync state for symbol" in output
    assert "Metadata symbol: complete=1, partial=0, low=0" in output
    assert "status=ok" in output


def test_cmd_status_watchlist_prints_scope_summary(capsys):
    from run import cmd_status

    args = type(
        "Args",
        (),
        {
            "type": "watchlist",
            "market": "A",
        },
    )

    with patch("run.get_cache") as mock_get_cache, patch(
        "run.cfg_get"
    ) as mock_cfg, patch("run.get_stock_pool") as mock_pool:
        mock_cfg.side_effect = lambda key, default=None: {
            "watchlist": ["600519", "000858"],
            "cache_ttl.daily_kline": 3600,
            "cache_ttl.financial": 604800,
            "cache_ttl.fund_nav": 3600,
        }.get(key, default)
        mock_pool.return_value = [
            {
                "code": "600519",
                "metadata_completeness": 1.0,
                "metadata_source": "manual",
                "metadata_status": "active",
                "is_active": 1,
            },
            {
                "code": "000858",
                "metadata_completeness": 0.25,
                "metadata_source": "manual",
                "metadata_status": "active",
                "is_active": 1,
            },
        ]
        mock_get_cache.return_value.get_sync_state.side_effect = [
            [
                {
                    "data_kind": "summary",
                    "code": "",
                    "status": "partial",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2026-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "history",
                    "code": "600519",
                    "status": "ok",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2099-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "history",
                    "code": "000858",
                    "status": "partial",
                    "last_covered_date": "",
                    "last_success_at": "",
                    "last_error": "timeout",
                }
            ],
        ]
        cmd_status(args)

    output = capsys.readouterr().out
    assert "Scope watchlist: requested=2" in output
    assert "Metadata watchlist: complete=1, partial=0, low=1" in output
    assert "Top missing/problem symbols: 000858" in output


def test_cmd_status_etf_prints_scope_summary(capsys):
    from run import cmd_status

    args = type(
        "Args",
        (),
        {
            "type": "etf",
            "codes": "510300,159915",
        },
    )

    with patch("run.get_cache") as mock_get_cache, patch(
        "run.cfg_get"
    ) as mock_cfg, patch("run.get_etf_pool") as mock_pool:
        mock_cfg.side_effect = lambda key, default=None: {
            "cache_ttl.daily_kline": 3600,
            "cache_ttl.financial": 604800,
            "cache_ttl.fund_nav": 3600,
        }.get(key, default)
        mock_pool.return_value = [
            {
                "code": "510300",
                "metadata_completeness": 0.75,
                "metadata_source": "akshare_fund_etf_spot_em",
                "metadata_status": "active",
                "is_active": 1,
            },
            {
                "code": "159915",
                "metadata_completeness": 0.25,
                "metadata_source": "akshare_fund_etf_spot_em",
                "metadata_status": "active",
                "is_active": 1,
            },
        ]
        mock_get_cache.return_value.get_sync_state.side_effect = [
            [
                {
                    "data_kind": "summary",
                    "code": "",
                    "status": "partial",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2026-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "nav",
                    "code": "510300",
                    "status": "ok",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2099-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "nav",
                    "code": "159915",
                    "status": "partial",
                    "last_covered_date": "",
                    "last_success_at": "",
                    "last_error": "timeout",
                }
            ],
        ]
        cmd_status(args)

    output = capsys.readouterr().out
    assert "Scope etf: requested=2" in output
    assert "Metadata etf: complete=1, partial=0, low=1" in output
    assert "Sync state for etf (market=FUND)" in output
