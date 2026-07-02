from postmortem import build_postmortem_attribution
from scorecards import (
    build_diagnosis_scorecard,
    build_theme_scorecard,
    build_thesis_scorecard,
)


def test_build_diagnosis_scorecard_returns_dimensions():
    scorecard = build_diagnosis_scorecard(
        {
            "final_decision": {
                "signal": "BUY",
                "adjusted_score": 72.0,
                "bull_case": ["盈利能力较好"],
                "bear_case": ["估值保护不足"],
                "invalidation_conditions": ["跌破 20 日支撑"],
            },
            "confidence": {"score": 0.81, "notes": ["策略聚合一致性较高"]},
            "risks": {
                "risk_count": 1,
                "risk_level": "medium",
                "risks": ["high_valuation"],
            },
            "provenance": {"scope": "symbol", "source": "manual", "freshness": "fresh"},
        }
    )

    assert scorecard["name"] == "diagnosis_scorecard"
    assert len(scorecard["dimensions"]) == 5
    assert scorecard["level"] in {"high", "medium"}


def test_build_thesis_scorecard_uses_balance_and_invalidation():
    scorecard = build_thesis_scorecard(
        {
            "summary": "BUY 观点，score=72.0/100",
            "bull_case": ["盈利能力较好", "趋势修复"],
            "bear_case": ["估值保护不足"],
            "invalidation_conditions": ["跌破支撑", "盈利走弱"],
            "confidence_score": 0.81,
            "confidence_level": "high",
            "provenance": {"scope": "symbol", "source": "manual"},
        }
    )

    assert scorecard["name"] == "thesis_scorecard"
    assert any(item["name"] == "balance" for item in scorecard["dimensions"])


def test_build_theme_scorecard_uses_layers_and_checks():
    scorecard = build_theme_scorecard(
        {
            "resolved_theme": "ai_infra",
            "next_checks": ["核对订单兑现", "核对扩产节奏"],
            "layers": [
                {
                    "evidence": ["先进封装更接近扩产瓶颈"],
                    "disconfirming_signals": ["候选较少"],
                    "candidates": [{"code": "300100"}, {"code": "300200"}],
                }
            ],
        }
    )

    assert scorecard["name"] == "theme_scorecard"
    assert scorecard["dimensions"][0]["name"] == "template_fit"


def test_build_postmortem_attribution_returns_adjustments():
    attribution = build_postmortem_attribution(
        {
            "bull_case": ["盈利能力较好"],
            "bear_case": ["估值保护不足"],
            "invalidation_conditions": ["跌破支撑"],
            "scorecard": {"score": 52.0},
            "postmortem": {"outcome": "loss"},
        }
    )

    assert attribution["outcome"] == "loss"
    assert attribution["adjustments"]
