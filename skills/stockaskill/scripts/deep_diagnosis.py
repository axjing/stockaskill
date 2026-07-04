"""Long-form deep diagnosis built on top of the base stock diagnosis."""

from typing import Any, Dict, List

from advisor.diagnosis import StockDiagnosis


def build_deep_diagnosis(code: str, market: str = "A") -> Dict[str, Any]:
    """Build a heavier, structured diagnosis report for one symbol.

    Args:
        code: Symbol code.
        market: Market code.

    Returns:
        A long-form diagnosis payload suitable for JSON and Markdown reporting.
    """
    base_report = StockDiagnosis(code, market).full_report()
    decision = base_report.get("final_decision", {}) or {}
    confidence = base_report.get("confidence", {}) or {}
    provenance = base_report.get("provenance", {}) or {}

    executive_summary = _build_executive_summary(base_report)
    variant_perception = _build_variant_perception(base_report)
    supporting_evidence = _build_supporting_evidence(base_report)
    conflict_matrix = _build_conflict_matrix(base_report)
    next_checks = _build_next_checks(base_report, conflict_matrix)

    return {
        "code": base_report.get("code", code),
        "market": base_report.get("market", market),
        "mode": "deep-diagnose",
        "executive_summary": executive_summary,
        "variant_perception": variant_perception,
        "supporting_evidence": supporting_evidence,
        "conflict_matrix": conflict_matrix,
        "bear_case": decision.get("bear_case", []) or [],
        "invalidation_conditions": decision.get("invalidation_conditions", []) or [],
        "next_checks": next_checks,
        "final_decision": decision,
        "confidence": confidence,
        "provenance": provenance,
        "diagnosis_report": base_report,
    }


def _build_executive_summary(report: Dict[str, Any]) -> str:
    """Summarize the primary stance and major caveat in one paragraph."""
    decision = report.get("final_decision", {}) or {}
    signal = decision.get("signal", "HOLD")
    score = float(decision.get("adjusted_score", 50) or 50)
    bull_case = decision.get("bull_case", []) or []
    bear_case = decision.get("bear_case", []) or []
    confidence = report.get("confidence", {}) or {}
    confidence_level = confidence.get("level", "medium")

    positive = bull_case[0] if bull_case else "当前正面证据主要来自综合打分"
    risk = bear_case[0] if bear_case else "当前负面证据仍需继续跟踪"
    return (
        f"{signal} 倾向，综合分数 {score:.1f}/100，confidence={confidence_level}。"
        f" 主要正面依据是：{positive}。"
        f" 主要约束是：{risk}。"
    )


def _build_variant_perception(report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract what the market may be under- or over-pricing."""
    decision = report.get("final_decision", {}) or {}
    technical = report.get("technical", {}) or {}
    fundamentals = report.get("fundamentals", {}) or {}
    risks = report.get("risks", {}) or {}

    market_misread: List[str] = []
    if technical.get("trend") == "bullish" and decision.get("signal") == "BUY":
        market_misread.append("价格结构已改善，但市场可能尚未充分定价趋势修复。")
    if fundamentals.get("checks", {}).get("profitability") == "good":
        market_misread.append("盈利质量处于较好区间，市场可能低估其基本面韧性。")
    if fundamentals.get("checks", {}).get("valuation") == "expensive":
        market_misread.append("估值保护不足，市场可能对乐观预期定价过满。")
    if risks.get("risk_level") == "high":
        market_misread.append("风险项已抬升到 high，当前价格可能低估尾部风险。")

    what_has_to_be_true = list(decision.get("bull_case", [])[:3])
    if not what_has_to_be_true:
        what_has_to_be_true.append("后续数据至少需要维持当前中性偏正的综合判断。")

    return {
        "summary": market_misread[0]
        if market_misread
        else "当前并无强烈的市场误判信号。",
        "market_misread": _dedupe_keep_order(market_misread)[:4],
        "what_has_to_be_true": _dedupe_keep_order(what_has_to_be_true)[:4],
    }


def _build_supporting_evidence(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build a deterministic evidence chain from the base report."""
    decision = report.get("final_decision", {}) or {}
    technical = report.get("technical", {}) or {}
    fundamentals = report.get("fundamentals", {}) or {}
    risks = report.get("risks", {}) or {}
    confidence = report.get("confidence", {}) or {}

    evidence: List[Dict[str, Any]] = []
    for item in decision.get("bull_case", [])[:3]:
        evidence.append(
            {
                "category": "bull_case",
                "strength": "high",
                "detail": item,
            }
        )
    if technical.get("trend"):
        evidence.append(
            {
                "category": "technical",
                "strength": "high" if technical.get("trend") == "bullish" else "low",
                "detail": (
                    "均线结构偏多。"
                    if technical.get("trend") == "bullish"
                    else "均线结构仍偏弱。"
                ),
            }
        )
    if fundamentals.get("checks", {}).get("profitability"):
        profitability = fundamentals.get("checks", {}).get("profitability")
        evidence.append(
            {
                "category": "fundamental",
                "strength": "high" if profitability == "good" else "medium",
                "detail": f"盈利能力检查结果：{profitability}。",
            }
        )
    evidence.append(
        {
            "category": "risk",
            "strength": "low" if risks.get("risk_level") == "high" else "medium",
            "detail": (
                f"风险等级={risks.get('risk_level', 'unknown')}, "
                f"风险项数={int(risks.get('risk_count', 0) or 0)}。"
            ),
        }
    )
    evidence.append(
        {
            "category": "confidence",
            "strength": confidence.get("level", "medium"),
            "detail": "；".join((confidence.get("notes", []) or [])[:2])
            or "confidence 中性",
        }
    )
    return evidence[:8]


def _build_conflict_matrix(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Make conflicts explicit instead of burying them in prose."""
    decision = report.get("final_decision", {}) or {}
    technical = report.get("technical", {}) or {}
    fundamentals = report.get("fundamentals", {}) or {}
    risks = report.get("risks", {}) or {}
    sentiment = report.get("sentiment", {}) or {}

    valuation = fundamentals.get("checks", {}).get("valuation", "unknown")
    profitability = fundamentals.get("checks", {}).get("profitability", "unknown")
    trend = technical.get("trend", "unknown")
    sentiment_factor = float(sentiment.get("adjustment_factor", 1.0) or 1.0)
    risk_level = risks.get("risk_level", "unknown")

    rows = [
        _conflict_row(
            topic="trend_vs_risk",
            bull="趋势结构偏多" if trend == "bullish" else "暂无趋势优势",
            bear=f"风险等级={risk_level}",
            status="conflicted"
            if trend == "bullish" and risk_level in {"medium", "high"}
            else "aligned",
            implication="若风险继续累积，趋势信号的解释力会被削弱。",
        ),
        _conflict_row(
            topic="quality_vs_valuation",
            bull=f"盈利能力={profitability}",
            bear=f"估值={valuation}",
            status="conflicted"
            if profitability == "good" and valuation == "expensive"
            else "mixed",
            implication="需要确认基本面改善能否覆盖当前估值约束。",
        ),
        _conflict_row(
            topic="signal_vs_sentiment",
            bull=f"最终信号={decision.get('signal', 'HOLD')}",
            bear=f"情绪调整因子={sentiment_factor:.2f}",
            status="conflicted"
            if decision.get("signal") == "BUY" and sentiment_factor < 1.0
            else "aligned",
            implication="若情绪仍压制，短期交易兑现可能弱于中期逻辑。",
        ),
    ]
    return rows


def _build_next_checks(
    report: Dict[str, Any],
    conflict_matrix: List[Dict[str, Any]],
) -> List[str]:
    """Convert risks and gaps into concrete next research checks."""
    checks: List[str] = []
    decision = report.get("final_decision", {}) or {}
    confidence = report.get("confidence", {}) or {}
    provenance = report.get("provenance", {}) or {}
    risks = report.get("risks", {}) or {}

    for row in conflict_matrix:
        if row.get("status") == "conflicted":
            checks.append(f"复核冲突项 {row.get('topic')}: {row.get('implication')}")
    for item in decision.get("invalidation_conditions", [])[:2]:
        checks.append(f"持续跟踪失效条件: {item}")
    if confidence.get("level") != "high":
        checks.append("补齐缺失数据或重新检查策略分歧来源。")
    if provenance.get("freshness") not in {"fresh", "local_first"}:
        checks.append("确认底层数据 freshness 是否足以支撑当前结论。")
    if risks.get("risk_level") == "high":
        checks.append("优先验证高风险项是否仍在恶化。")
    return _dedupe_keep_order(checks)[:6]


def _conflict_row(
    topic: str,
    bull: str,
    bear: str,
    status: str,
    implication: str,
) -> Dict[str, str]:
    """Create a uniform conflict-matrix row."""
    return {
        "topic": topic,
        "bull": bull,
        "bear": bear,
        "status": status,
        "implication": implication,
    }


def _dedupe_keep_order(items: List[str]) -> List[str]:
    """Dedupe a string list while preserving order."""
    result: List[str] = []
    seen = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
