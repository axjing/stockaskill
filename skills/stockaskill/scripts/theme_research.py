"""Theme research: rank supply-chain layers before ranking companies."""

from dataclasses import asdict
from typing import Any, Dict, List

from config import get as cfg_get
from data_engine import get_stock_pool
from factors.composite import CompositeAnalyzer
from models import ThemeCandidate, ThemeLayerFinding, ThemeResearchReport
from scorecards import build_theme_scorecard
from utils import is_st


def _normalize_text(*values: str) -> str:
    return " ".join(
        str(value).strip().lower() for value in values if str(value).strip()
    )


def _theme_catalog() -> Dict[str, Any]:
    return dict(cfg_get("theme_research.supported_themes", {}) or {})


def resolve_theme(theme: str) -> Dict[str, Any]:
    """Resolve a user theme string to a supported local theme template."""
    normalized = theme.strip().lower()
    catalog = _theme_catalog()
    for theme_id, definition in catalog.items():
        aliases = [str(item).strip().lower() for item in definition.get("aliases", [])]
        if normalized == theme_id or normalized in aliases:
            return {"theme_id": theme_id, "definition": definition}
        if any(alias and alias in normalized for alias in aliases):
            return {"theme_id": theme_id, "definition": definition}
    return {
        "theme_id": "custom",
        "definition": {
            "aliases": [theme],
            "key_question": "先确认这个主题真正卡住的是哪一层，而不是哪只股票最热。",
            "next_checks": [
                "核对是否存在真实需求或扩产变化",
                "核对哪一层更难替代",
                "核对最强候选是否有公开证据支持",
            ],
            "lower_priority_areas": ["只命中热门叙事、没有行业映射的方向先降级"],
            "layers": [
                {
                    "name": "核心卡点层",
                    "scarce_layer": "更难替代的核心层",
                    "why_here": "先看谁控制卡点，而不是谁蹭到叙事。",
                    "keywords": [theme],
                    "evidence": ["该主题当前缺少预置模板，先从核心卡点层排查"],
                },
                {
                    "name": "受益扩散层",
                    "scarce_layer": "中游配套/扩散受益",
                    "why_here": "次优先看配套层，而不是最末端应用层。",
                    "keywords": [theme],
                    "evidence": ["如果主题成立，扩散收益会沿配套层传导"],
                },
            ],
        },
    }


def _candidate_signal(score: float, completeness: float) -> List[str]:
    signals: List[str] = []
    if score >= 70:
        signals.append("本地因子分数处于较高区间")
    elif score >= 55:
        signals.append("本地因子分数中性偏上")
    else:
        signals.append("本地因子分数一般，仍需更多验证")

    if completeness >= 0.75:
        signals.append("元数据完整度较高")
    elif completeness >= 0.5:
        signals.append("元数据可用但不完整")
    else:
        signals.append("元数据完整度偏低")
    return signals


def build_theme_report(
    theme: str,
    market: str = "A",
    top_n: int = 3,
    candidate_limit: int = 0,
) -> ThemeResearchReport:
    """Build a local-first theme research report."""
    resolved = resolve_theme(theme)
    theme_id = str(resolved["theme_id"])
    definition = dict(resolved["definition"] or {})
    pool = get_stock_pool(market)
    if not pool:
        return ThemeResearchReport(
            theme=theme,
            resolved_theme=theme_id,
            market=market,
            summary="当前本地股票池为空，无法开展主题研究。",
            key_question=definition.get("key_question", ""),
            next_checks=["先执行 fetch pool 或相关 sync 命令补齐本地股票池"],
            lower_priority_areas=["当前没有本地股票池，主题研究无法继续下钻"],
            confidence={
                "score": 0.4,
                "level": "low",
                "notes": ["当前没有本地股票池，主题研究只能停留在模板层"],
            },
            provenance={
                "scope": "theme_research",
                "market": market,
                "freshness": "missing_pool",
                "covered_through": "",
                "source": theme_id,
                "source_status": "pool_missing",
                "metadata_completeness": 0.0,
                "inputs": ["theme_template"],
            },
            scorecard={},
        )

    usable_pool = []
    for stock in pool[
        : max(candidate_limit or cfg_get("theme_research.candidate_limit", 120), 1)
    ]:
        code = str(stock.get("code", "")).strip()
        name = str(stock.get("name", "")).strip()
        if not code or is_st(code, name) or not bool(stock.get("is_active", 1)):
            continue
        usable_pool.append(stock)

    layers: List[ThemeLayerFinding] = []
    for index, layer in enumerate(definition.get("layers", []), start=1):
        keywords = [str(item).strip().lower() for item in layer.get("keywords", [])]
        candidates: List[ThemeCandidate] = []
        for stock in usable_pool:
            text = _normalize_text(
                stock.get("name", ""),
                stock.get("sector", ""),
                stock.get("industry", ""),
            )
            hit_keywords = [
                keyword for keyword in keywords if keyword and keyword in text
            ]
            if not hit_keywords:
                continue

            factor_score = 50.0
            try:
                factor_score = float(
                    CompositeAnalyzer(str(stock.get("code", "")), market)
                    .analyze(cached_only=True)
                    .get("total_score", 50)
                    or 50
                )
            except Exception:
                factor_score = 50.0
            completeness = float(stock.get("metadata_completeness", 0) or 0)
            candidate_score = (
                (100 - index * 8)
                + len(hit_keywords) * 8
                + factor_score * 0.35
                + completeness * 12
            )
            evidence = [
                f"行业/名称命中关键词：{', '.join(hit_keywords[:3])}",
                *_candidate_signal(factor_score, completeness),
            ]
            disconfirming_signals = []
            if completeness < 0.5:
                disconfirming_signals.append("元数据完整度较低，主题映射仍偏粗糙")
            if factor_score < 55:
                disconfirming_signals.append(
                    "本地因子信号不强，可能只是主题映射而非高质量标的"
                )

            candidates.append(
                ThemeCandidate(
                    code=str(stock.get("code", "")).strip(),
                    name=str(stock.get("name", "")).strip()
                    or str(stock.get("code", "")),
                    layer=str(layer.get("name", "")).strip(),
                    layer_rank=index,
                    score=round(candidate_score, 1),
                    market=market,
                    sector=str(stock.get("sector", "")).strip(),
                    industry=str(stock.get("industry", "")).strip(),
                    evidence=evidence,
                    disconfirming_signals=disconfirming_signals,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        top_candidates = candidates[:top_n]
        layer_score = (
            round(top_candidates[0].score, 1)
            if top_candidates
            else float(100 - index * 10)
        )
        disconfirming = []
        if not top_candidates:
            disconfirming.append("当前本地股票池里没有明显命中该层的候选")
        elif len(top_candidates) < top_n:
            disconfirming.append("该层候选较少，说明映射仍不充分")

        layers.append(
            ThemeLayerFinding(
                layer=str(layer.get("name", "")).strip(),
                scarce_layer=str(layer.get("scarce_layer", "")).strip(),
                rank=index,
                score=layer_score,
                why_here=str(layer.get("why_here", "")).strip(),
                evidence=list(layer.get("evidence", []) or []),
                disconfirming_signals=disconfirming,
                candidates=top_candidates,
            )
        )

    layers.sort(key=lambda item: (item.score, -item.rank), reverse=True)
    for rank, layer in enumerate(layers, start=1):
        layer.rank = rank
        for candidate in layer.candidates:
            candidate.layer_rank = rank

    top_layer = layers[0].layer if layers else "暂无高优先级层"
    summary = (
        f"我会先看 {top_layer}。原因是它更接近当前主题的真实卡点，"
        "再在该层里排公司，而不是先追最热门股票。"
    )
    confidence = _theme_confidence(
        {
            "resolved_theme": theme_id,
            "layers": [asdict(layer) for layer in layers],
        }
    )
    provenance = _theme_provenance(
        theme_id,
        market,
        usable_pool_size=len(usable_pool),
        candidate_limit=max(
            candidate_limit or cfg_get("theme_research.candidate_limit", 120),
            1,
        ),
    )
    report = ThemeResearchReport(
        theme=theme,
        resolved_theme=theme_id,
        market=market,
        summary=summary,
        key_question=str(definition.get("key_question", "")).strip(),
        next_checks=list(definition.get("next_checks", []) or []),
        lower_priority_areas=list(definition.get("lower_priority_areas", []) or []),
        layers=layers,
        confidence=confidence,
        provenance=provenance,
    )
    report.scorecard = build_theme_scorecard(report.to_dict())
    return report


def _theme_confidence(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a bounded confidence block for theme research."""
    layers = report.get("layers", []) or []
    top_candidates = sum(len(layer.get("candidates", []) or []) for layer in layers[:2])
    score = 0.45
    if report.get("resolved_theme") != "custom":
        score += 0.2
    if layers:
        score += 0.15
    if top_candidates >= 2:
        score += 0.1
    if any(layer.get("candidates") for layer in layers):
        score += 0.1
    notes = [
        "主题研究是本地模板驱动，不是外部主题数据库",
        "先排产业链层级，再排公司",
    ]
    if report.get("resolved_theme") == "custom":
        notes.append("当前主题未命中预置模板，解释力会弱一些")
    else:
        notes.append("当前主题命中了预置模板，层级解释更稳定")
    return {
        "score": round(max(0.0, min(1.0, score)), 3),
        "level": "high" if score >= 0.8 else ("medium" if score >= 0.55 else "low"),
        "notes": notes,
    }


def _theme_provenance(
    theme_id: str,
    market: str,
    usable_pool_size: int,
    candidate_limit: int,
) -> Dict[str, Any]:
    """Build a standardized provenance block for theme research."""
    return {
        "scope": "theme_research",
        "market": market,
        "freshness": "local_first",
        "covered_through": "",
        "source": theme_id,
        "source_status": "template_matched"
        if theme_id != "custom"
        else "custom_template",
        "metadata_completeness": round(
            min(1.0, usable_pool_size / max(candidate_limit, 1)), 3
        ),
        "inputs": ["theme_template", "stock_pool_metadata", "cached_factor_scores"],
    }
