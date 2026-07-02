from unittest.mock import patch


def test_build_deep_diagnosis_adds_long_form_sections():
    from deep_diagnosis import build_deep_diagnosis

    base_report = {
        "code": "601318",
        "market": "A",
        "final_decision": {
            "signal": "BUY",
            "adjusted_score": 72.0,
            "bull_case": ["盈利能力处于较好区间"],
            "bear_case": ["估值保护不足"],
            "invalidation_conditions": ["跌破 20 日支撑位 55.00 后未能快速收回"],
        },
        "technical": {"trend": "bullish"},
        "fundamentals": {
            "checks": {"profitability": "good", "valuation": "expensive"}
        },
        "risks": {"risk_level": "medium", "risk_count": 1, "risks": ["high_valuation"]},
        "sentiment": {"adjustment_factor": 0.98},
        "confidence": {
            "level": "medium",
            "score": 0.73,
            "notes": ["策略聚合一致性较高"],
        },
        "provenance": {"source": "manual", "freshness": "stale"},
    }

    with patch("deep_diagnosis.StockDiagnosis") as mock_diag:
        mock_diag.return_value.full_report.return_value = base_report
        report = build_deep_diagnosis("601318", "A")

    assert report["mode"] == "deep-diagnose"
    assert "executive_summary" in report
    assert report["variant_perception"]["market_misread"]
    assert report["supporting_evidence"]
    assert report["conflict_matrix"]
    assert report["next_checks"]
    assert report["diagnosis_report"] == base_report


def test_build_deep_diagnosis_surfaces_conflicted_rows():
    from deep_diagnosis import build_deep_diagnosis

    base_report = {
        "code": "AAPL",
        "market": "US",
        "final_decision": {
            "signal": "BUY",
            "adjusted_score": 68.0,
            "bull_case": ["短中期均线结构偏多"],
            "bear_case": ["估值保护不足"],
            "invalidation_conditions": ["风险项继续增加并抬升到 high risk"],
        },
        "technical": {"trend": "bullish"},
        "fundamentals": {
            "checks": {"profitability": "good", "valuation": "expensive"}
        },
        "risks": {"risk_level": "high", "risk_count": 2, "risks": ["high_valuation"]},
        "sentiment": {"adjustment_factor": 0.96},
        "confidence": {"level": "high", "score": 0.82, "notes": []},
        "provenance": {"source": "manual", "freshness": "fresh"},
    }

    with patch("deep_diagnosis.StockDiagnosis") as mock_diag:
        mock_diag.return_value.full_report.return_value = base_report
        report = build_deep_diagnosis("AAPL", "US")

    topics = {item["topic"]: item["status"] for item in report["conflict_matrix"]}
    assert topics["trend_vs_risk"] == "conflicted"
    assert topics["quality_vs_valuation"] == "conflicted"
    assert "复核冲突项 trend_vs_risk" in "\n".join(report["next_checks"])
