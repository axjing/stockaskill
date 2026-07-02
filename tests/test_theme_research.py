from unittest.mock import patch

from theme_research import build_theme_report, resolve_theme


def test_resolve_known_theme():
    resolved = resolve_theme("AI基础设施")

    assert resolved["theme_id"] == "ai_infra"


def test_build_theme_report_ranks_layers_and_candidates():
    pool = [
        {
            "code": "300100",
            "name": "先进封装设备",
            "sector": "半导体设备",
            "industry": "先进封装",
            "metadata_completeness": 1.0,
            "is_active": 1,
        },
        {
            "code": "300200",
            "name": "高速光模块",
            "sector": "光通信",
            "industry": "光模块",
            "metadata_completeness": 0.75,
            "is_active": 1,
        },
        {
            "code": "300300",
            "name": "服务器电源",
            "sector": "电源设备",
            "industry": "服务器电源",
            "metadata_completeness": 0.75,
            "is_active": 1,
        },
    ]

    with patch("theme_research.get_stock_pool", return_value=pool):
        with patch("theme_research.CompositeAnalyzer") as mock_analyzer:
            mock_analyzer.return_value.analyze.return_value = {"total_score": 72.0}
            report = build_theme_report("AI基础设施", market="A", top_n=2)

    payload = report.to_dict()
    assert payload["resolved_theme"] == "ai_infra"
    assert payload["layers"][0]["layer"] == "先进封装与测试"
    assert payload["layers"][0]["candidates"][0]["code"] == "300100"
    assert payload["confidence"]["level"] in {"high", "medium"}
    assert payload["provenance"]["source"] == "ai_infra"
    assert payload["scorecard"]["name"] == "theme_scorecard"


def test_build_theme_report_handles_empty_pool():
    with patch("theme_research.get_stock_pool", return_value=[]):
        report = build_theme_report("机器人", market="A", top_n=2)

    assert "当前本地股票池为空" in report.summary
