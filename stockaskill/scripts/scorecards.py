"""Research scorecards for diagnosis, thesis, and theme workflows."""

from typing import Any, Dict, List

from models import ScorecardDimension, ScorecardReport


def build_diagnosis_scorecard(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a scorecard from a diagnosis report."""
    decision = report.get("final_decision", {}) or {}
    confidence = report.get("confidence", {}) or {}
    risks = report.get("risks", {}) or {}
    bull_case = decision.get("bull_case", []) or []
    bear_case = decision.get("bear_case", []) or []
    invalidation = decision.get("invalidation_conditions", []) or []
    provenance = report.get("provenance", {}) or {}

    dimensions = [
        _dimension(
            "signal_strength",
            min(100.0, max(0.0, float(decision.get("adjusted_score", 50) or 50))),
            [
                f"signal={decision.get('signal', 'HOLD')}",
                f"adjusted_score={float(decision.get('adjusted_score', 50) or 50):.1f}",
            ],
        ),
        _dimension(
            "conflict_visibility",
            _ratio_score(len(bull_case) + len(bear_case) + len(invalidation), 6),
            [
                f"bull_case={len(bull_case)}",
                f"bear_case={len(bear_case)}",
                f"invalidation={len(invalidation)}",
            ],
        ),
        _dimension(
            "confidence_quality",
            float(confidence.get("score", 0.5) or 0.5) * 100,
            list(confidence.get("notes", []) or [])[:3],
        ),
        _dimension(
            "risk_explicitness",
            _ratio_score(int(risks.get("risk_count", 0) or 0) + len(bear_case), 4),
            [
                f"risk_level={risks.get('risk_level', 'unknown')}",
                f"risk_items={len(risks.get('risks', []) or [])}",
            ],
        ),
        _dimension(
            "provenance_visibility",
            _provenance_score(provenance),
            [
                f"source={provenance.get('source', 'unknown')}",
                f"freshness={provenance.get('freshness', 'unknown')}",
            ],
        ),
    ]
    return _finalize_scorecard("diagnosis_scorecard", dimensions)


def build_thesis_scorecard(record: Dict[str, Any]) -> Dict[str, Any]:
    """Build a scorecard from a thesis record."""
    dimensions = [
        _dimension(
            "thesis_clarity",
            _ratio_score(len(str(record.get("summary", "")).strip()), 80),
            [str(record.get("summary", "")).strip()[:80] or "missing_summary"],
        ),
        _dimension(
            "balance",
            _ratio_score(
                len(record.get("bull_case", []) or [])
                + len(record.get("bear_case", []) or []),
                4,
            ),
            [
                f"bull_case={len(record.get('bull_case', []) or [])}",
                f"bear_case={len(record.get('bear_case', []) or [])}",
            ],
        ),
        _dimension(
            "invalidation_quality",
            _ratio_score(len(record.get("invalidation_conditions", []) or []), 3),
            list(record.get("invalidation_conditions", []) or [])[:2]
            or ["missing_invalidation"],
        ),
        _dimension(
            "confidence_quality",
            float(record.get("confidence_score", 0.5) or 0.5) * 100,
            [f"confidence_level={record.get('confidence_level', 'medium')}"],
        ),
        _dimension(
            "provenance_visibility",
            _provenance_score(record.get("provenance", {}) or {}),
            [
                f"source={record.get('provenance', {}).get('source', 'unknown')}",
                f"scope={record.get('provenance', {}).get('scope', 'unknown')}",
            ],
        ),
    ]
    return _finalize_scorecard("thesis_scorecard", dimensions)


def build_theme_scorecard(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a scorecard from a theme research report."""
    layers = report.get("layers", []) or []
    top_candidates = sum(len(layer.get("candidates", []) or []) for layer in layers[:2])
    dimensions = [
        _dimension(
            "template_fit",
            85.0 if report.get("resolved_theme") != "custom" else 55.0,
            [f"resolved_theme={report.get('resolved_theme', 'custom')}"],
        ),
        _dimension(
            "layer_coverage",
            _ratio_score(len(layers), 3),
            [f"layers={len(layers)}"],
        ),
        _dimension(
            "candidate_depth",
            _ratio_score(top_candidates, 4),
            [f"top_candidates={top_candidates}"],
        ),
        _dimension(
            "evidence_quality",
            _theme_evidence_score(layers),
            _theme_evidence_preview(layers),
        ),
        _dimension(
            "next_checks_quality",
            _ratio_score(len(report.get("next_checks", []) or []), 3),
            list(report.get("next_checks", []) or [])[:2] or ["missing_next_checks"],
        ),
    ]
    return _finalize_scorecard("theme_scorecard", dimensions)


def _theme_evidence_score(layers: List[Dict[str, Any]]) -> float:
    """Estimate theme evidence quality from layer content."""
    evidence_count = 0
    disconfirm_count = 0
    for layer in layers[:3]:
        evidence_count += len(layer.get("evidence", []) or [])
        disconfirm_count += len(layer.get("disconfirming_signals", []) or [])
    return min(100.0, evidence_count * 14 + disconfirm_count * 10)


def _theme_evidence_preview(layers: List[Dict[str, Any]]) -> List[str]:
    """Collect short evidence previews for a theme scorecard."""
    preview: List[str] = []
    for layer in layers[:2]:
        preview.extend((layer.get("evidence", []) or [])[:1])
        preview.extend((layer.get("disconfirming_signals", []) or [])[:1])
    return preview[:3] or ["missing_layer_evidence"]


def _provenance_score(provenance: Dict[str, Any]) -> float:
    """Score how visible and complete provenance fields are."""
    checks = [
        bool(provenance.get("source")),
        bool(provenance.get("freshness")),
        bool(provenance.get("scope")),
        provenance.get("metadata_completeness") is not None,
    ]
    return sum(1 for item in checks if item) / max(len(checks), 1) * 100


def _dimension(name: str, score: float, evidence: List[str]) -> ScorecardDimension:
    """Build one scorecard dimension with a normalized verdict."""
    normalized = round(max(0.0, min(100.0, score)), 1)
    if normalized >= 75:
        verdict = "strong"
    elif normalized >= 55:
        verdict = "adequate"
    else:
        verdict = "weak"
    return ScorecardDimension(
        name=name,
        score=normalized,
        verdict=verdict,
        evidence=[str(item) for item in evidence if str(item).strip()],
    )


def _ratio_score(value: int, target: int) -> float:
    """Convert a bounded count into a 0-100 score."""
    if target <= 0:
        return 0.0
    return min(100.0, max(0.0, value / target * 100))


def _finalize_scorecard(
    name: str,
    dimensions: List[ScorecardDimension],
) -> Dict[str, Any]:
    """Aggregate dimensions into a unified scorecard."""
    score = round(
        sum(dimension.score for dimension in dimensions) / max(len(dimensions), 1),
        1,
    )
    if score >= 75:
        level = "high"
    elif score >= 55:
        level = "medium"
    else:
        level = "low"
    strengths = [
        f"{dimension.name}: {dimension.verdict}"
        for dimension in dimensions
        if dimension.score >= 75
    ][:4]
    gaps = [
        f"{dimension.name}: {dimension.verdict}"
        for dimension in dimensions
        if dimension.score < 55
    ][:4]
    summary = (
        f"{name}={score:.1f}/100，level={level}。"
        f" strengths={len(strengths)}，gaps={len(gaps)}。"
    )
    return ScorecardReport(
        name=name,
        score=score,
        level=level,
        summary=summary,
        dimensions=dimensions,
        strengths=strengths,
        gaps=gaps,
    ).to_dict()
