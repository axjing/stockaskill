"""CLI command handlers for market_regime functionality."""

import argparse

from market_regime import analyze_market_regime, summarize_market_regime
from report_generator import format_market_regime_summary

from commands._common import _cmd_output, _safe_market_regime, _save_report


def cmd_market_regime(args: argparse.Namespace) -> None:
    """Analyze current market posture and risk budget."""
    market = getattr(args, "market_flag", None) or getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    regime = analyze_market_regime(market)
    print(summarize_market_regime(regime))
    confidence = regime.get("confidence", {}) or {}
    provenance = regime.get("provenance", {}) or {}
    if confidence:
        print(
            "  Confidence:"
            f" {confidence.get('level', 'medium')}"
            f" ({float(confidence.get('score', 0.5) or 0.5):.2f})"
        )
    if provenance:
        print(
            "  Provenance:"
            f" source={provenance.get('source', 'unknown')},"
            f" status={provenance.get('source_status', 'unknown')},"
            f" freshness={provenance.get('freshness', 'unknown')}"
        )
    technical = regime.get("technical", {}) or {}
    breadth = regime.get("breadth", {}) or {}
    if technical:
        print(
            "  技术面:"
            f" current={technical.get('current', 'N/A')},"
            f" ma20={technical.get('ma20', 'N/A')},"
            f" ma60={technical.get('ma60', 'N/A')},"
            f" ret20={float(technical.get('ret20', 0) or 0) * 100:.2f}%"
        )
    if breadth:
        above_ma20 = float(breadth.get("above_ma20_ratio", 0.5) or 0.5) * 100
        above_ma60 = float(breadth.get("above_ma60_ratio", 0.5) or 0.5) * 100
        print(
            "  Breadth:"
            f" sample={breadth.get('sample_size', 0)}/{breadth.get('sample_limit', 0)},"
            f" above_ma20={above_ma20:.1f}%,"
            f" above_ma60={above_ma60:.1f}%"
        )
    for reason in regime.get("reasons", [])[:5]:
        print(f"  - {reason}")

    md = format_market_regime_summary(regime)
    _save_report(
        f"market_regime_{market}",
        fmt,
        output_dir,
        data=regime,
        md=md,
        metadata={"command": "market-regime", "market": market},
    )



def cmd_risk_alert(args: argparse.Namespace) -> None:
    """Show market risk alert with actionable suggestions."""
    market = getattr(args, "market", "A") or "A"
    output_dir, fmt = _cmd_output(args)

    regime = _safe_market_regime(market)
    posture = regime.get("posture", "neutral")
    score = float(regime.get("score", 50) or 50)
    label = regime.get("posture_label", "中性")
    risk_budget = float(regime.get("risk_budget", 1.0) or 1.0)
    allowed = regime.get("new_positions_allowed", True)

    actions = {
        "offensive": "市场积极，可正常操作",
        "constructive": "市场偏积极，可适当加仓",
        "neutral": "市场中性，控制节奏",
        "cautious": "市场谨慎，建议减仓至60%以下",
        "defensive": "市场防御，建议降至25%以下仓位，避免新仓",
    }

    print(f"\n市场风险预警 ({market})")
    print(f"  状态: {label} (score={score:.1f}/100)")
    print(f"  风险预算: {risk_budget:.0%}")
    print(f"  建议: {actions.get(posture, '观望')}")
    print(f"  新开仓: {'允许' if allowed else '不建议'}")
    print()

    technical = regime.get("technical", {}) or {}
    if technical:
        print(
            f"  技术面: 当前={technical.get('current', 'N/A')}, "
            f"MA20={technical.get('ma20', 'N/A')}, "
            f"MA60={technical.get('ma60', 'N/A')}"
        )

    for reason in regime.get("reasons", [])[:5]:
        print(f"  - {reason}")

    alert_data = {
        "market": market,
        "posture": posture,
        "posture_label": label,
        "score": score,
        "risk_budget": risk_budget,
        "new_positions_allowed": allowed,
        "suggested_action": actions.get(posture, "观望"),
        "technical": technical,
        "reasons": regime.get("reasons", [])[:5],
    }
    md = f"# 市场风险预警 ({market})\n\n"
    md += f"- 状态: {label} (score={score:.1f}/100)\n"
    md += f"- 风险预算: {risk_budget:.0%}\n"
    md += f"- 建议: {actions.get(posture, '观望')}\n"
    md += f"- 新开仓: {'允许' if allowed else '不建议'}\n"
    _save_report(
        f"risk_alert_{market}",
        fmt,
        output_dir,
        data=alert_data,
        md=md,
        metadata={"command": "risk-alert", "market": market},
    )



