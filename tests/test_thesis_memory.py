from pathlib import Path
from unittest.mock import patch

from thesis_memory import (
    build_thesis_record,
    get_thesis_record,
    list_thesis_records,
    save_thesis_record,
    update_thesis_postmortem,
)


def _sample_report():
    return {
        "code": "601318",
        "market": "A",
        "final_decision": {
            "signal": "BUY",
            "adjusted_score": 71.5,
            "bull_case": ["盈利能力较好"],
            "bear_case": ["估值保护不足"],
            "invalidation_conditions": ["跌破 20 日支撑"],
        },
        "confidence": {"level": "high", "score": 0.81, "notes": ["策略聚合一致性较高"]},
        "provenance": {"scope": "symbol", "source": "manual"},
    }


def test_save_and_get_thesis_record(tmp_path):
    with patch("thesis_memory.cfg_get", return_value=str(tmp_path)):
        record = build_thesis_record(_sample_report(), notes="first thesis")
        paths = save_thesis_record(record)

        assert Path(paths["json_path"]).exists()
        assert Path(paths["md_path"]).exists()

        loaded = get_thesis_record(thesis_id=record.thesis_id)

    assert loaded is not None
    assert loaded["code"] == "601318"
    assert loaded["notes"] == "first thesis"
    assert loaded["provenance"]["source"] == "manual"
    assert loaded["scorecard"]["name"] == "thesis_scorecard"


def test_list_thesis_records_filters_by_status(tmp_path):
    with patch("thesis_memory.cfg_get", return_value=str(tmp_path)):
        active = build_thesis_record(_sample_report(), thesis_status="active")
        closed = build_thesis_record(_sample_report(), thesis_status="closed")
        save_thesis_record(active)
        save_thesis_record(closed)

        records = list_thesis_records(thesis_status="active")

    assert len(records) == 1
    assert records[0]["thesis_status"] == "active"


def test_update_thesis_postmortem_overwrites_record(tmp_path):
    with patch("thesis_memory.cfg_get", return_value=str(tmp_path)):
        record = build_thesis_record(_sample_report(), thesis_status="active")
        save_thesis_record(record)

        updated = update_thesis_postmortem(
            outcome="win",
            notes="纪律执行到位",
            thesis_id=record.thesis_id,
            thesis_status="closed",
        )

        loaded = get_thesis_record(thesis_id=record.thesis_id)

    assert updated["postmortem"]["outcome"] == "win"
    assert loaded is not None
    assert loaded["thesis_status"] == "closed"
    assert loaded["postmortem"]["notes"] == "纪律执行到位"
    assert loaded["attribution"]["outcome"] == "win"
