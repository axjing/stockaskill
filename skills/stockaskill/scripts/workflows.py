"""Deterministic workflow router for common stockaskill intents."""

from models import WorkflowRecommendation, WorkflowStep
from utils import detect_workflow_intent, normalize_code_for_market


def build_workflow_recommendation(
    goal: str,
    market: str,
    code: str = "",
    codes: list[str] | None = None,
    top_n: int = 10,
    capital: float = 1_000_000,
) -> WorkflowRecommendation:
    """Build a bounded workflow recommendation for a common user goal."""
    normalized_code = normalize_code_for_market(code, market) if code else ""
    normalized_codes = [
        normalize_code_for_market(item, market)
        for item in (codes or [])
        if str(item).strip()
    ]
    intent = detect_workflow_intent(
        goal,
        code=normalized_code,
        codes=normalized_codes,
    )

    if intent == "market_check":
        return WorkflowRecommendation(
            intent=intent,
            market=market,
            summary="先判断市场风险姿态，再决定是否继续扫描或建仓。",
            rationale=[
                "市场状态会直接影响 scan、alpha 和 portfolio 的可信度。",
                "当前仓库已经支持 risk budget，可作为后续仓位约束。",
            ],
            steps=[
                WorkflowStep(
                    title="检查市场状态",
                    command=(
                        "python stockaskill/scripts/run.py market-regime "
                        f"{market}"
                    ),
                    purpose="读取 posture、risk budget 与新增仓位允许度。",
                ),
                WorkflowStep(
                    title="如姿态允许则进入扫描",
                    command=(
                        "python stockaskill/scripts/run.py scan "
                        f"{market} --top {top_n}"
                    ),
                    purpose="在市场允许度合适时寻找候选标的。",
                ),
            ],
            notes=["若 `new_positions_allowed=no`，优先观察而不是扩张风险。"],
        )

    if intent == "theme_research":
        return WorkflowRecommendation(
            intent=intent,
            market=market,
            summary="主题研究路径先排产业链层级，再在高优先级层内找公司。",
            rationale=[
                "主题研究的关键不是先排热门股票，而是先排真实卡点层。",
                "当前主题研究模式会输出证据、反证和下一步验证项。",
            ],
            steps=[
                WorkflowStep(
                    title="执行主题研究",
                    command=(
                        "python stockaskill/scripts/run.py theme-scan "
                        "<THEME> "
                        f"--market {market} --top {min(top_n, 3)}"
                    ),
                    purpose="先按产业链层级排序，而不是直接按股票热度排序。",
                ),
                WorkflowStep(
                    title="对高优先级标的做诊断",
                    command=(
                        "python stockaskill/scripts/run.py diagnose "
                        "<TOP_CODE> "
                        f"--market {market}"
                    ),
                    purpose="验证 bull/bear、confidence 和失效条件。",
                ),
                WorkflowStep(
                    title="沉淀 thesis",
                    command=(
                        "python stockaskill/scripts/run.py thesis capture "
                        "<TOP_CODE> "
                        f"--market {market}"
                    ),
                    purpose="把主题判断沉淀到本地研究记忆里。",
                ),
            ],
            notes=["当前实现优先依赖本地股票池和缓存，不强依赖联网研究。"],
        )

    if intent == "analyze_symbol":
        return WorkflowRecommendation(
            intent=intent,
            market=market,
            summary="对单票先补齐本地数据，再做分析与诊断。",
            rationale=[
                "单票路径最依赖 symbol 级历史与基本面覆盖。",
                "先 analyze 再 diagnose，能兼顾因子视角与冲突表达。",
            ],
            steps=[
                WorkflowStep(
                    title="同步单票数据",
                    command=(
                        "python stockaskill/scripts/run.py sync symbol "
                        f"{normalized_code} --market {market}"
                    ),
                    purpose="确保本地 K 线与 fundamentals 可用。",
                ),
                WorkflowStep(
                    title="基础分析",
                    command=(
                        "python stockaskill/scripts/run.py analyze "
                        f"{normalized_code} --market {market}"
                    ),
                    purpose="查看估值、因子与策略聚合结果。",
                ),
                WorkflowStep(
                    title="深度诊断",
                    command=(
                        "python stockaskill/scripts/run.py diagnose "
                        f"{normalized_code} --market {market}"
                    ),
                    purpose="输出 bull/bear/invalidation 与 confidence。",
                ),
            ],
        )

    if intent == "diagnose_symbol":
        return WorkflowRecommendation(
            intent=intent,
            market=market,
            summary="以深度诊断为主线，先保证数据，再看冲突与失效条件。",
            rationale=[
                "当前 diagnose 已具备 confidence、bull/bear、失效条件结构。",
                "先同步可以减少深度诊断因数据缺口导致的噪声。",
            ],
            steps=[
                WorkflowStep(
                    title="同步单票数据",
                    command=(
                        "python stockaskill/scripts/run.py sync symbol "
                        f"{normalized_code} --market {market}"
                    ),
                    purpose="降低诊断阶段的数据缺口风险。",
                ),
                WorkflowStep(
                    title="执行深度诊断",
                    command=(
                        "python stockaskill/scripts/run.py diagnose "
                        f"{normalized_code} --market {market}"
                    ),
                    purpose="输出最终信号、bull case、bear case 与 invalidation。",
                ),
            ],
        )

    if intent == "build_portfolio":
        codes_arg = ",".join(normalized_codes) if normalized_codes else "<CODE1,CODE2>"
        return WorkflowRecommendation(
            intent=intent,
            market=market,
            summary="组合路径先看市场姿态，再同步候选，最后构建仓位。",
            rationale=[
                "组合构建已经接入 risk budget，先看 regime 更合理。",
                "先同步 portfolio scope，可减少建仓过程中逐票回源。",
            ],
            steps=[
                WorkflowStep(
                    title="检查市场状态",
                    command=(
                        "python stockaskill/scripts/run.py market-regime "
                        f"{market}"
                    ),
                    purpose="确认仓位预算与新增仓位允许度。",
                ),
                WorkflowStep(
                    title="同步组合候选",
                    command=(
                        "python stockaskill/scripts/run.py sync portfolio "
                        f"--codes {codes_arg} --market {market}"
                    ),
                    purpose="预热候选标的历史与基本面数据。",
                ),
                WorkflowStep(
                    title="构建组合",
                    command=(
                        "python stockaskill/scripts/run.py portfolio "
                        f"--codes {codes_arg} --market {market} "
                        f"--capital {int(capital)}"
                    ),
                    purpose="生成受市场姿态约束的组合结果。",
                ),
            ],
            notes=["如尚无候选代码，可先执行 scan 或 alpha。"],
        )

    if intent == "sync_data":
        sample_code = normalized_code or "<CODE>"
        return WorkflowRecommendation(
            intent=intent,
            market=market,
            summary="先按作用域同步数据，再用 status 校验覆盖度，然后进入分析。",
            rationale=[
                "当前仓库的正确方向是 bounded sync，而不是全市场后台同步。",
                "sync 配合 status data 才能确认本地 readiness 是否满足分析路径。",
            ],
            steps=[
                WorkflowStep(
                    title="同步单票或作用域",
                    command=(
                        "python stockaskill/scripts/run.py sync symbol "
                        f"{sample_code} --market {market}"
                    ),
                    purpose="最小化预热目标数据。",
                ),
                WorkflowStep(
                    title="检查数据状态",
                    command=(
                        "python stockaskill/scripts/run.py status data symbol "
                        f"{sample_code} --market {market}"
                    ),
                    purpose="查看 freshness、error 与 metadata 摘要。",
                ),
            ],
            notes=["若目标是批量候选扫描，可改用 `sync scan-universe`。"],
        )

    if intent == "backtest_strategy":
        return WorkflowRecommendation(
            intent=intent,
            market=market,
            summary="回测路径用于验证策略，不直接替代当前市场判断。",
            rationale=[
                "回测是验证 alpha 或组合方法稳定性的手段。",
                "历史表现不能替代当下市场姿态，因此应与 market-regime 分开看。",
            ],
            steps=[
                WorkflowStep(
                    title="运行策略回测",
                    command=(
                        "python stockaskill/scripts/run.py backtest "
                        f"--market {market}"
                    ),
                    purpose="查看 CAGR、Sharpe、回撤等历史指标。",
                ),
                WorkflowStep(
                    title="检查当前市场状态",
                    command=(
                        "python stockaskill/scripts/run.py market-regime "
                        f"{market}"
                    ),
                    purpose="避免把历史优势直接外推到当前市场。",
                ),
            ],
        )

    return WorkflowRecommendation(
        intent="opportunity_scan",
        market=market,
        summary="找机会的默认路径是先看市场，再扫描，再对候选做深度诊断。",
        rationale=[
            "scan 适合先拉出候选池，alpha 适合再做更强的排序压缩。",
            "先做 market-regime 可以避免在弱市里直接扩大风险暴露。",
        ],
        steps=[
            WorkflowStep(
                title="检查市场状态",
                command=(
                    "python stockaskill/scripts/run.py market-regime "
                    f"{market}"
                ),
                purpose="读取 posture 与 risk budget。",
            ),
            WorkflowStep(
                title="候选扫描",
                command=(
                    "python stockaskill/scripts/run.py scan "
                    f"{market} --top {top_n}"
                ),
                purpose="快速拉出可读候选列表。",
            ),
            WorkflowStep(
                title="进一步排序",
                command=(
                    "python stockaskill/scripts/run.py alpha "
                    f"{market} --top {min(top_n, 10)}"
                ),
                purpose="用 alpha momentum 进一步压缩候选池。",
            ),
            WorkflowStep(
                title="逐票深度诊断",
                command=(
                    "python stockaskill/scripts/run.py diagnose "
                    f"<TOP_CODE> --market {market}"
                ),
                purpose="检查 bull/bear、confidence 与失效条件。",
            ),
        ],
        notes=["主题研究模式尚未独立实现，当前先走 scan/alpha 主路径。"],
    )
