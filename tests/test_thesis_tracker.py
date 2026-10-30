from unittest.mock import patch

from commands.thesis import cmd_thesis
from thesis_memory import (
    build_thesis_record,
    check_active_theses,
    get_thesis_record,
    save_thesis_record,
)


def _sample_report(price=100.0):
    return {
        "code": "601318",
        "market": "A",
        "final_decision": {
            "signal": "BUY",
            "adjusted_score": 75.0,
            "bull_case": ["行业龙头"],
            "bear_case": ["增长放缓"],
            "invalidation_conditions": ["跌破 20 日均线支撑", "跌幅超过 8%"],
        },
        "confidence": {"level": "high", "score": 0.85},
        "technical": {"current": price, "ma20": price},
    }


def test_check_active_theses_healthy(tmp_path):
    with patch("thesis_memory.cfg_get", return_value=str(tmp_path)):
        record = build_thesis_record(_sample_report(100.0), thesis_status="active")
        save_thesis_record(record)

        # Mock kline returning higher price (105.0)
        mock_kline = [
            {"date": "2026-10-30", "close": 105.0},
            {"date": "2026-10-29", "close": 104.0},
            {"date": "2026-10-28", "close": 103.0},
        ]
        with patch("data_engine.get_kline", return_value=mock_kline):
            results = check_active_theses()

        assert len(results) == 1
        assert results[0]["status"] == "HEALTHY"
        assert results[0]["pnl_pct"] == 5.0
        assert results[0]["auto_closed"] is False


def test_check_active_theses_invalidated_and_auto_close(tmp_path):
    with patch("thesis_memory.cfg_get", return_value=str(tmp_path)):
        record = build_thesis_record(_sample_report(100.0), thesis_status="active")
        save_thesis_record(record)

        # Mock kline returning dropped price (90.0, -10%)
        mock_kline = [
            {"date": "2026-10-30", "close": 90.0},
            {"date": "2026-10-29", "close": 92.0},
            {"date": "2026-10-28", "close": 95.0},
        ]
        with patch("data_engine.get_kline", return_value=mock_kline):
            results = check_active_theses(auto_close=True)

        assert len(results) == 1
        assert results[0]["status"] == "INVALIDATED"
        assert results[0]["pnl_pct"] == -10.0
        assert results[0]["auto_closed"] is True

        # Verify thesis is now closed
        updated = get_thesis_record(thesis_id=record.thesis_id)
        assert updated is not None
        assert updated["thesis_status"] == "closed"


def test_cmd_thesis_check(tmp_path, capsys):
    import argparse

    with patch("thesis_memory.cfg_get", return_value=str(tmp_path)):
        record = build_thesis_record(_sample_report(100.0), thesis_status="active")
        save_thesis_record(record)

        mock_kline = [{"date": "2026-10-30", "close": 102.0}]
        with patch("data_engine.get_kline", return_value=mock_kline):
            args = argparse.Namespace(
                action="check",
                market="A",
                code="601318",
                auto_close=False,
                output_dir="reports",
                format="none",
            )
            cmd_thesis(args)

    out = capsys.readouterr().out
    assert "Active Thesis Health Status" in out
    assert "601318" in out
    assert "HEALTHY" in out
