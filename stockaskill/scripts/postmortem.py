"""Postmortem attribution for thesis reviews."""

from typing import Any, Dict, List

from models import AttributionReport


def build_postmortem_attribution(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic attribution summary for one thesis postmortem."""
    postmortem = record.get("postmortem", {}) or {}
    outcome = str(postmortem.get("outcome", "neutral") or "neutral")
    scorecard = record.get("scorecard", {}) or {}
    scorecard_score = float(scorecard.get("score", 50) or 50)
    negatives: List[str] = []
    positives: List[str] = []
    adjustments: List[str] = []

    bull_case = record.get("bull_case", []) or []
    bear_case = record.get("bear_case", []) or []
    invalidation = record.get("invalidation_conditions", []) or []

    if scorecard_score >= 75:
        positives.append("初始 thesis 结构完整度较高")
    else:
        negatives.append("初始 thesis 结构完整度一般")
        adjustments.append("后续 capture 时补强 bull/bear/invalidation 三段结构。")

    if len(invalidation) >= 2:
        positives.append("失效条件定义较明确")
    else:
        negatives.append("失效条件偏少，复盘锚点不足")
        adjustments.append("至少定义 2 条以上可观察的失效条件。")

    if len(bull_case) >= 2 and len(bear_case) >= 1:
        positives.append("多空两侧表达相对平衡")
    else:
        negatives.append("多空两侧表达不够平衡")
        adjustments.append("未来 thesis 需要同时写清主要正面与主要约束。")

    if outcome == "win":
        primary_driver = "thesis_quality"
        summary = "复盘显示主要收益更可能来自 thesis 结构较完整，而不是偶发噪声。"
        adjustments.append("保留当前研究框架，继续强化数据 freshness 检查。")
    elif outcome == "loss":
        primary_driver = "risk_or_invalidation"
        summary = "复盘显示亏损更可能来自风险约束或失效条件执行不足。"
        adjustments.append("未来优先检查失效条件是否及时触发并执行。")
    else:
        primary_driver = "timing_or_mixed"
        summary = "复盘结果中性，更多说明 thesis 与时点因素共同作用。"
        adjustments.append("后续把 thesis 质量与时点选择拆开复核。")

    return AttributionReport(
        outcome=outcome,
        primary_driver=primary_driver,
        summary=summary,
        positives=_dedupe(positives)[:4],
        negatives=_dedupe(negatives)[:4],
        adjustments=_dedupe(adjustments)[:4],
    ).to_dict()


def _dedupe(items: List[str]) -> List[str]:
    """Dedupe strings while preserving order."""
    result: List[str] = []
    seen = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
