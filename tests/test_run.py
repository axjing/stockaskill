from unittest.mock import patch


def test_cmd_backtest_uses_cagr_value(capsys):
    from run import cmd_backtest

    mock_result = {
        "pool_size": 10,
        "years": 5,
        "period_start": "2018-01-01",
        "period_end": "2023-01-01",
        "cagr": 0.15,
        "total_return": 0.8,
        "sharpe": 1.2,
        "max_drawdown": -0.12,
        "monthly_avg": 1.1,
    }

    with patch("portfolio.backtest_engine.AlphaMomentumBacktest") as mock_engine:
        mock_engine.return_value.run.return_value = mock_result
        with patch("commands.backtest._save_report"):
            cmd_backtest(type("Args", (), {"output_dir": "reports", "format": "none"}))

    output = capsys.readouterr().out
    assert "PASS" in output
    assert "15.00%" in output


def test_cmd_market_regime_prints_summary(capsys):
    from run import cmd_market_regime

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "output_dir": "reports",
            "format": "none",
        },
    )
    regime = {
        "market": "A",
        "status": "ok",
        "score": 72.5,
        "posture": "constructive",
        "posture_label": "偏积极",
        "risk_budget": 0.85,
        "new_positions_allowed": True,
        "technical": {"current": 3800, "ma20": 3720, "ma60": 3600, "ret20": 0.06},
        "breadth": {
            "sample_size": 30,
            "sample_limit": 60,
            "above_ma20_ratio": 0.63,
            "above_ma60_ratio": 0.58,
        },
        "reasons": ["指数位于短中期均线上方", "样本 breadth 较强"],
        "confidence": {
            "level": "high",
            "score": 0.86,
            "notes": ["市场基准历史覆盖较充分"],
        },
        "provenance": {"source": "000300", "source_status": "ok", "freshness": "fresh"},
    }

    with patch("commands.market_regime.analyze_market_regime", return_value=regime):
        with patch("commands.market_regime._save_report"):
            cmd_market_regime(args)

    output = capsys.readouterr().out
    assert "市场状态: 偏积极" in output
    assert "risk_budget=0.85" in output
    assert "Confidence: high (0.86)" in output
    assert "样本 breadth 较强" in output


def test_cmd_route_recommends_opportunity_scan(capsys):
    from run import cmd_route

    args = type(
        "Args",
        (),
        {
            "goal": ["我要找", "A股", "机会"],
            "market": "A",
            "code": "",
            "codes": "",
            "top": 5,
            "capital": 1000000,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.route._save_report"):
        cmd_route(args)

    output = capsys.readouterr().out
    assert "Intent: opportunity_scan" in output
    assert "python stockaskill/scripts/run.py market-regime A" in output
    assert "python stockaskill/scripts/run.py scan A --top 5" in output


def test_cmd_route_recommends_portfolio_flow(capsys):
    from run import cmd_route

    args = type(
        "Args",
        (),
        {
            "goal": ["构建", "组合"],
            "market": "A",
            "code": "",
            "codes": "600519,000858",
            "top": 10,
            "capital": 500000,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.route._save_report"):
        cmd_route(args)

    output = capsys.readouterr().out
    assert "Intent: build_portfolio" in output
    assert "sync portfolio --codes 600519,000858 --market A" in output
    assert "portfolio --codes 600519,000858 --market A --capital 500000" in output


def test_cmd_route_recommends_theme_research(capsys):
    from run import cmd_route

    args = type(
        "Args",
        (),
        {
            "goal": ["帮我做", "AI", "主题研究"],
            "market": "A",
            "code": "",
            "codes": "",
            "top": 3,
            "capital": 1000000,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.route._save_report"):
        cmd_route(args)

    output = capsys.readouterr().out
    assert "Intent: theme_research" in output
    assert (
        "python stockaskill/scripts/run.py theme-scan <THEME> --market A --top 3"
        in output
    )


def test_cmd_workflow_list_prints_builtin_manifests(capsys):
    from run import cmd_workflow

    args = type(
        "Args",
        (),
        {
            "action": "list",
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.route.list_workflow_manifests") as mock_list:
        mock_list.return_value = [
            "market-regime-daily",
            "portfolio-review-weekly",
        ]
        with patch("commands.route._save_report"):
            cmd_workflow(args)

    output = capsys.readouterr().out
    assert "Available workflows (2):" in output
    assert "market-regime-daily" in output


def test_cmd_workflow_run_prints_resolved_steps(capsys):
    from run import cmd_workflow

    args = type(
        "Args",
        (),
        {
            "action": "run",
            "name": "theme-research-weekly",
            "market": "A",
            "code": "300100",
            "codes": "",
            "theme": ["AI基础设施"],
            "top": 3,
            "capital": 1000000,
            "output_dir": "reports",
            "format": "none",
        },
    )
    plan = {
        "name": "theme-research-weekly",
        "market": "A",
        "summary": "每周主题研究例行：主题拆解、单票深诊断、再沉淀 thesis。",
        "description": "desc",
        "manifest_path": "stockaskill/workflows/theme-research-weekly.yaml",
        "context": {"market": "A", "theme": "AI基础设施", "code": "300100"},
        "missing_params": [],
        "steps": [
            {
                "title": "执行主题研究",
                "command": (
                    "python stockaskill/scripts/run.py theme-scan "
                    "AI基础设施 --market A --top 3"
                ),
                "purpose": "先排产业链层级，再缩小到高优先级候选公司。",
            }
        ],
        "notes": ["note"],
        "tags": ["weekly"],
    }

    with patch("commands.route.build_workflow_run_plan") as mock_plan:
        mock_plan.return_value = type("Plan", (), {"to_dict": lambda self=None: plan})()
        with patch("commands.route._save_report"):
            cmd_workflow(args)

    output = capsys.readouterr().out
    assert "Workflow: theme-research-weekly (market=A)" in output
    assert "theme-scan AI基础设施 --market A --top 3" in output
    assert "Note: note" in output


def test_cmd_scorecard_thesis_prints_score(capsys):
    from run import cmd_scorecard

    args = type(
        "Args",
        (),
        {
            "action": "thesis",
            "thesis_id": "A_601318_1",
            "code": "",
            "market": "A",
            "output_dir": "reports",
            "format": "none",
        },
    )
    record = {
        "thesis_id": "A_601318_1",
        "code": "601318",
        "market": "A",
        "scorecard": {"name": "thesis_scorecard", "score": 78.0, "level": "high"},
    }

    with patch("commands.scorecard.get_thesis_record", return_value=record):
        with patch("commands.scorecard._save_report"):
            cmd_scorecard(args)

    output = capsys.readouterr().out
    assert "Scorecard thesis 601318 (score=78.0, level=high)" in output


def test_cmd_scorecard_theme_prints_score(capsys):
    from run import cmd_scorecard

    args = type(
        "Args",
        (),
        {
            "action": "theme",
            "theme": ["AI基础设施"],
            "market": "A",
            "top": 3,
            "candidates": 0,
            "output_dir": "reports",
            "format": "none",
        },
    )
    report = {
        "scorecard": {"name": "theme_scorecard", "score": 71.0, "level": "medium"}
    }

    with patch("commands.scorecard.build_theme_report") as mock_build:
        mock_build.return_value = type(
            "ThemeReport", (), {"to_dict": lambda self=None: report}
        )()
        with patch("commands.scorecard._save_report"):
            cmd_scorecard(args)

    output = capsys.readouterr().out
    assert "Scorecard theme AI基础设施 (score=71.0, level=medium)" in output


def test_cmd_theme_scan_prints_ranked_layers(capsys):
    from run import cmd_theme_scan

    args = type(
        "Args",
        (),
        {
            "theme": ["AI基础设施"],
            "market": "A",
            "top": 2,
            "candidates": 0,
            "output_dir": "reports",
            "format": "none",
        },
    )
    report = {
        "theme": "AI基础设施",
        "resolved_theme": "ai_infra",
        "market": "A",
        "summary": "我会先看先进封装与测试。",
        "key_question": "真实扩产首先卡在哪一层",
        "confidence": {
            "level": "medium",
            "score": 0.72,
            "notes": ["主题命中了预置模板"],
        },
        "provenance": {
            "source": "ai_infra",
            "source_status": "template_matched",
            "freshness": "local_first",
        },
        "layers": [
            {
                "rank": 1,
                "layer": "先进封装与测试",
                "scarce_layer": "先进封装设备/测试验证",
                "score": 88.0,
                "candidates": [
                    {"code": "300100", "name": "先进封装设备", "score": 78.0}
                ],
            }
        ],
        "lower_priority_areas": [],
        "next_checks": [],
    }

    with patch("commands.theme.build_theme_report") as mock_build:
        mock_build.return_value = type(
            "ThemeReport",
            (),
            {"to_dict": lambda self=None: report},
        )()
        with patch("commands.theme._save_report"):
            cmd_theme_scan(args)

    output = capsys.readouterr().out
    assert "Theme research: AI基础设施 (market=A)" in output
    assert "Confidence: medium (0.72)" in output
    assert "1. 先进封装与测试 | 卡点=先进封装设备/测试验证 | score=88.0" in output
    assert "300100 先进封装设备: 78.0" in output


def test_cmd_deep_diagnose_prints_conflicts_and_checks(capsys):
    from run import cmd_deep_diagnose

    args = type(
        "Args",
        (),
        {
            "code": "601318",
            "market": "A",
            "output_dir": "reports",
            "format": "none",
        },
    )
    report = {
        "code": "601318",
        "market": "A",
        "mode": "deep-diagnose",
        "executive_summary": "BUY 倾向，综合分数 72.0/100。",
        "final_decision": {"signal": "BUY", "adjusted_score": 72.0},
        "confidence": {"level": "medium", "score": 0.73},
        "conflict_matrix": [
            {
                "topic": "trend_vs_risk",
                "status": "conflicted",
                "implication": "若风险继续累积，趋势信号的解释力会被削弱。",
            }
        ],
        "next_checks": [
            "复核冲突项 trend_vs_risk: 若风险继续累积，趋势信号的解释力会被削弱。"
        ],
    }

    with patch("commands.analyze.build_deep_diagnosis", return_value=report):
        with patch("commands.analyze._save_report"):
            cmd_deep_diagnose(args)

    output = capsys.readouterr().out
    assert "Deep diagnosing 601318 (market=A)" in output
    assert "Signal / Score: BUY / 72.0" in output
    assert "Conflict trend_vs_risk: conflicted" in output
    assert "Next check: 复核冲突项 trend_vs_risk" in output


def test_cmd_thesis_capture_persists_record(capsys):
    from run import cmd_thesis

    args = type(
        "Args",
        (),
        {
            "action": "capture",
            "code": "601318",
            "market": "A",
            "status": "active",
            "notes": "跟踪用例",
            "output_dir": "reports",
            "format": "none",
        },
    )
    report = {
        "code": "601318",
        "market": "A",
        "final_decision": {
            "signal": "BUY",
            "adjusted_score": 72.0,
            "bull_case": ["盈利能力较好"],
            "bear_case": ["估值保护不足"],
            "invalidation_conditions": ["跌破 20 日支撑"],
        },
        "confidence": {"level": "high", "score": 0.81, "notes": []},
    }
    record = {
        "thesis_id": "A_601318_20260702_000000",
        "code": "601318",
        "market": "A",
        "created_at": "2026-07-02T00:00:00Z",
        "source": "diagnose",
        "thesis_status": "active",
        "signal": "BUY",
        "score": 72.0,
        "confidence_level": "high",
        "confidence_score": 0.81,
        "summary": "BUY 观点",
        "bull_case": ["盈利能力较好"],
        "bear_case": ["估值保护不足"],
        "invalidation_conditions": ["跌破 20 日支撑"],
        "notes": "跟踪用例",
        "postmortem": None,
        "diagnosis_report": report,
    }

    with patch("advisor.diagnosis.StockDiagnosis") as mock_diag:
        mock_diag.return_value.full_report.return_value = report
        with patch("commands.thesis.build_thesis_record") as mock_build:
            mock_build.return_value = type(
                "Record",
                (),
                {"thesis_id": record["thesis_id"], "to_dict": lambda self=None: record},
            )()
            with patch("commands.thesis.save_thesis_record") as mock_save:
                mock_save.return_value = {
                    "json_path": "memory/theses/A_601318.json",
                    "md_path": "memory/theses/A_601318.md",
                }
                with patch("commands.thesis._save_report"):
                    cmd_thesis(args)

    output = capsys.readouterr().out
    assert "Capturing thesis for 601318" in output
    assert "Thesis JSON: memory/theses/A_601318.json" in output


def test_cmd_thesis_list_prints_records(capsys):
    from run import cmd_thesis

    args = type(
        "Args",
        (),
        {
            "action": "list",
            "market": "A",
            "code": "",
            "status": "",
            "limit": 10,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.thesis.list_thesis_records") as mock_list:
        mock_list.return_value = [
            {
                "thesis_id": "A_601318_1",
                "code": "601318",
                "market": "A",
                "signal": "BUY",
                "score": 71.5,
                "thesis_status": "active",
                "summary": "BUY 观点",
            }
        ]
        with patch("commands.thesis._save_report"):
            cmd_thesis(args)

    output = capsys.readouterr().out
    assert "Thesis records (1):" in output
    assert "A_601318_1 601318 A BUY score=71.5 status=active" in output


def test_cmd_thesis_postmortem_updates_record(capsys):
    from run import cmd_thesis

    args = type(
        "Args",
        (),
        {
            "action": "postmortem",
            "thesis_id": "A_601318_1",
            "code": "",
            "market": "A",
            "outcome": "win",
            "notes": "执行到位",
            "status": "closed",
            "output_dir": "reports",
            "format": "none",
        },
    )

    updated = {
        "thesis_id": "A_601318_1",
        "code": "601318",
        "market": "A",
        "created_at": "2026-07-02T00:00:00Z",
        "source": "diagnose",
        "thesis_status": "closed",
        "signal": "BUY",
        "score": 72.0,
        "confidence_level": "high",
        "confidence_score": 0.81,
        "summary": "BUY 观点",
        "bull_case": [],
        "bear_case": [],
        "invalidation_conditions": [],
        "notes": "",
        "postmortem": {
            "outcome": "win",
            "reviewed_at": "2026-07-03T00:00:00Z",
            "notes": "执行到位",
            "thesis_status": "closed",
        },
        "diagnosis_report": {},
    }

    with patch("commands.thesis.update_thesis_postmortem", return_value=updated):
        with patch("commands.thesis._save_report"):
            cmd_thesis(args)

    output = capsys.readouterr().out
    assert "## Postmortem" in output
    assert "Outcome: win" in output


def test_format_diagnosis_summary_includes_cases_and_confidence():
    from report_generator import format_diagnosis_summary

    report = {
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
        "provenance": {
            "scope": "symbol",
            "source": "manual",
            "metadata_completeness": 1.0,
        },
        "factors": {"factors": {"quality": 82.0}},
        "technical": {
            "trend": "bullish",
            "rsi_14": 62,
            "support_20d": 55,
            "resistance_20d": 63,
        },
        "risks": {"risk_level": "medium", "risks": ["high_valuation"]},
    }

    md = format_diagnosis_summary(report)

    assert "Confidence" in md
    assert "Provenance" in md
    assert "Bull Case" in md
    assert "Bear Case" in md
    assert "Invalidation" in md


def test_format_deep_diagnosis_summary_includes_long_form_sections():
    from report_generator import format_deep_diagnosis_summary

    md = format_deep_diagnosis_summary(
        {
            "code": "601318",
            "market": "A",
            "mode": "deep-diagnose",
            "executive_summary": "BUY 倾向，综合分数 72.0/100。",
            "final_decision": {"signal": "BUY", "adjusted_score": 72.0},
            "confidence": {
                "level": "medium",
                "score": 0.73,
                "notes": ["策略聚合一致性较高"],
            },
            "provenance": {"scope": "symbol", "source": "manual", "freshness": "stale"},
            "variant_perception": {
                "summary": "价格结构已改善，但市场可能尚未充分定价趋势修复。",
                "market_misread": ["价格结构已改善，但市场可能尚未充分定价趋势修复。"],
                "what_has_to_be_true": ["盈利能力处于较好区间"],
            },
            "supporting_evidence": [
                {
                    "category": "bull_case",
                    "strength": "high",
                    "detail": "盈利能力处于较好区间",
                }
            ],
            "conflict_matrix": [
                {
                    "topic": "trend_vs_risk",
                    "bull": "趋势结构偏多",
                    "bear": "风险等级=medium",
                    "status": "conflicted",
                    "implication": "若风险继续累积，趋势信号的解释力会被削弱。",
                }
            ],
            "bear_case": ["估值保护不足"],
            "invalidation_conditions": ["跌破 20 日支撑位 55.00 后未能快速收回"],
            "next_checks": [
                "复核冲突项 trend_vs_risk: 若风险继续累积，趋势信号的解释力会被削弱。"
            ],
        }
    )

    assert "Executive Summary" in md
    assert "Variant Perception" in md
    assert "Supporting Evidence" in md
    assert "Conflict Matrix" in md
    assert "Next Checks" in md


def test_format_workflow_run_summary_includes_context_and_missing_params():
    from report_generator import format_workflow_run_summary

    md = format_workflow_run_summary(
        {
            "name": "portfolio-review-weekly",
            "market": "A",
            "manifest_path": "stockaskill/workflows/portfolio-review-weekly.yaml",
            "summary": "每周组合复核",
            "description": "desc",
            "context": {"market": "A", "capital": 1000000},
            "missing_params": ["codes"],
            "steps": [
                {
                    "title": "重建组合视图",
                    "command": (
                        "python stockaskill/scripts/run.py portfolio "
                        "--codes {codes} --market A --capital 1000000"
                    ),
                    "purpose": "重新审视组合权重建议。",
                    "artifact": "portfolio_A.json/.md",
                }
            ],
            "notes": ["缺少必要参数时，命令会保留占位符。"],
        }
    )

    assert "## Context" in md
    assert "## Missing Params" in md
    assert "## Steps" in md
    assert "portfolio --codes {codes}" in md


def test_format_thesis_summary_includes_postmortem():
    from report_generator import format_thesis_summary

    md = format_thesis_summary(
        {
            "thesis_id": "A_601318_1",
            "code": "601318",
            "market": "A",
            "created_at": "2026-07-02T00:00:00Z",
            "source": "diagnose",
            "thesis_status": "closed",
            "signal": "BUY",
            "score": 72.0,
            "confidence_level": "high",
            "confidence_score": 0.81,
            "summary": "BUY 观点",
            "provenance": {
                "scope": "symbol",
                "source": "manual",
                "metadata_completeness": 1.0,
            },
            "scorecard": {"name": "thesis_scorecard", "score": 78.0, "level": "high"},
            "attribution": {
                "outcome": "win",
                "primary_driver": "thesis_quality",
                "summary": "复盘显示主要收益更可能来自 thesis 结构较完整。",
            },
            "postmortem": {
                "outcome": "win",
                "reviewed_at": "2026-07-03T00:00:00Z",
                "notes": "执行到位",
                "thesis_status": "closed",
            },
        }
    )

    assert "## Postmortem" in md
    assert "Outcome: win" in md
    assert "## Provenance" in md
    assert "## Scorecard" in md
    assert "## Attribution" in md


def test_format_theme_research_includes_ranked_layers():
    from report_generator import format_theme_research

    md = format_theme_research(
        {
            "theme": "AI基础设施",
            "resolved_theme": "ai_infra",
            "market": "A",
            "summary": "先看先进封装",
            "key_question": "卡点在哪一层",
            "confidence": {
                "level": "medium",
                "score": 0.7,
                "notes": ["主题命中了预置模板"],
            },
            "provenance": {
                "scope": "theme_research",
                "source": "ai_infra",
                "metadata_completeness": 0.8,
            },
            "scorecard": {"name": "theme_scorecard", "score": 71.0, "level": "medium"},
            "layers": [
                {
                    "rank": 1,
                    "layer": "先进封装与测试",
                    "scarce_layer": "先进封装设备/测试验证",
                    "why_here": "更接近扩产瓶颈",
                    "evidence": ["设备验证周期长"],
                    "disconfirming_signals": ["候选较少"],
                    "candidates": [
                        {
                            "code": "300100",
                            "name": "先进封装设备",
                            "evidence": ["关键词命中", "元数据完整度较高"],
                            "disconfirming_signals": ["-"],
                        }
                    ],
                }
            ],
            "lower_priority_areas": [],
            "next_checks": ["核对订单兑现"],
        }
    )

    assert "## Ranked Layers" in md
    assert "## Confidence" in md
    assert "## Scorecard" in md
    assert "先进封装与测试" in md
    assert "## Next Checks" in md


def test_format_scorecard_renders_dimensions():
    from report_generator import format_scorecard

    md = format_scorecard(
        {
            "name": "thesis_scorecard",
            "score": 78.0,
            "level": "high",
            "summary": "summary",
            "dimensions": [
                {
                    "name": "balance",
                    "score": 80.0,
                    "verdict": "strong",
                    "evidence": ["bull_case=2", "bear_case=1"],
                }
            ],
            "strengths": ["balance: strong"],
            "gaps": [],
        }
    )

    assert "## Scorecard" in md
    assert "balance" in md
    assert "Strengths" in md


def test_cmd_scan_fund_warms_etf_scope(capsys):
    from run import cmd_scan

    funds = [
        {"code": "510300", "name": "沪深300ETF"},
        {"code": "159915", "name": "创业板ETF"},
    ]
    args = type(
        "Args",
        (),
        {
            "market": "FUND",
            "top": 1,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.scan.get_etf_pool", return_value=funds):
        with patch("commands.scan.ensure_etf_ready") as mock_ready:
            with patch("commands.scan._save_report"):
                cmd_scan(args)

    mock_ready.assert_called_once_with(["510300"], limit=1)
    output = capsys.readouterr().out
    assert "Scanning ETFs..." in output


def test_cmd_scan_prints_market_regime_summary(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "realtime",
            "refresh": False,
            "include_incomplete": False,
            "candidates": 10,
            "output_dir": "reports",
            "format": "none",
        },
    )
    regime = {
        "market": "A",
        "status": "ok",
        "score": 68.0,
        "posture": "constructive",
        "posture_label": "偏积极",
        "risk_budget": 0.85,
        "new_positions_allowed": True,
        "reasons": [],
        "breadth": {},
        "technical": {},
    }
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.scan_top.return_value = [
        {"code": "601318", "name": "PingAn", "total_score": 70.0, "f_score": 5}
    ]

    try:
        with patch("commands.scan._safe_market_regime", return_value=regime):
            with patch("commands.scan._save_report"):
                cmd_scan(args)
    finally:
        patch.stopall()

    output = capsys.readouterr().out
    assert "市场状态: 偏积极" in output


def test_cmd_scan_snapshot_reads_cached_snapshot(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "snapshot",
            "refresh": False,
            "include_incomplete": False,
            "candidates": 0,
            "output_dir": "reports",
            "format": "none",
        },
    )
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.get_snapshot_status.return_value = {
        "market": "A",
        "latest_trade_date": "2026-06-30",
        "needs_refresh": False,
        "status": "fresh",
    }
    scanner.scan_snapshot.return_value = {
        "results": [
            {
                "code": "601318",
                "name": "PingAn",
                "total_score": 81.2,
                "f_score": 7,
            }
        ],
        "summary": {
            "trade_date": "2026-06-30",
            "total_count": 5000,
            "eligible_count": 3200,
            "filtered_count": 1800,
            "data_complete_ratio": 0.8,
            "missing_list_date_count": 10,
            "missing_fundamentals_count": 20,
            "missing_history_count": 30,
            "st_count": 40,
            "bj_count": 50,
            "new_listing_count": 60,
            "metadata_quality": {"complete": 100, "partial": 50, "low": 10},
        },
    }

    try:
        with patch("commands.scan._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.refresh_snapshot.assert_not_called()
    scanner.scan_top.assert_not_called()
    output = capsys.readouterr().out
    assert "Snapshot date: 2026-06-30" in output
    assert "Metadata quality: complete=100, partial=50, low=10" in output
    assert "601318 PingAn: 81.2" in output


def test_cmd_scan_refresh_triggers_snapshot_build(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "snapshot",
            "refresh": True,
            "include_incomplete": False,
            "candidates": 0,
            "output_dir": "reports",
            "format": "none",
        },
    )
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.get_snapshot_status.return_value = {
        "market": "A",
        "latest_trade_date": None,
        "needs_refresh": True,
        "status": "missing",
    }
    scanner.refresh_snapshot.return_value = {
        "trade_date": "2026-06-30",
        "total_count": 100,
        "eligible_count": 80,
        "filtered_count": 20,
        "data_complete_ratio": 0.9,
        "missing_list_date_count": 1,
        "missing_fundamentals_count": 2,
        "missing_history_count": 3,
        "st_count": 4,
        "bj_count": 5,
        "new_listing_count": 6,
        "cache_reused_count": 70,
        "backfilled_count": 10,
        "excluded_count": 20,
        "history_cache_hits": 90,
        "history_fetched_count": 5,
        "history_missing_count": 5,
        "fundamentals_cache_hits": 88,
        "fundamentals_fetched_count": 7,
        "fundamentals_missing_count": 5,
    }
    scanner.scan_snapshot.return_value = {
        "results": [
            {
                "code": "601318",
                "name": "PingAn",
                "total_score": 75.0,
                "f_score": 6,
            }
        ],
        "summary": scanner.refresh_snapshot.return_value,
    }

    try:
        with patch("commands.scan._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.refresh_snapshot.assert_called_once_with("A", include_incomplete=False)
    output = capsys.readouterr().out
    assert "Refreshing full-market snapshot first" in output
    assert "Local reuse/backfill" in output


def test_cmd_scan_auto_falls_back_to_realtime_when_snapshot_missing(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "auto",
            "refresh": False,
            "include_incomplete": False,
            "candidates": 88,
            "output_dir": "reports",
            "format": "none",
        },
    )
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.get_snapshot_status.return_value = {
        "market": "A",
        "latest_trade_date": None,
        "needs_refresh": True,
        "status": "missing",
    }
    scanner.scan_top.return_value = [
        {"code": "601318", "name": "PingAn", "total_score": 78.0, "f_score": 6}
    ]

    try:
        with patch("commands.scan._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.scan_top.assert_called_once_with("A", 1, max_candidates=88)
    scanner.refresh_snapshot.assert_not_called()
    output = capsys.readouterr().out
    assert "回退到有界 realtime candidate scan" in output
    assert "601318 PingAn: 78.0" in output


def test_cmd_scan_realtime_uses_candidate_mode(capsys):
    from run import cmd_scan

    args = type(
        "Args",
        (),
        {
            "market": "A",
            "top": 1,
            "mode": "realtime",
            "refresh": False,
            "include_incomplete": False,
            "candidates": 123,
            "output_dir": "reports",
            "format": "none",
        },
    )
    scanner = patch("advisor.scanner.MarketScanner").start().return_value
    scanner.scan_top.return_value = [
        {"code": "601318", "name": "PingAn", "total_score": 70.0, "f_score": 5}
    ]

    try:
        with patch("commands.scan._save_report"):
            cmd_scan(args)
    finally:
        patch.stopall()

    scanner.scan_top.assert_called_once_with("A", 1, max_candidates=123)
    output = capsys.readouterr().out
    assert "Realtime mode is approximate" in output


def test_cmd_portfolio_applies_market_risk_budget(capsys):
    from run import cmd_portfolio

    args = type(
        "Args",
        (),
        {
            "codes": "AAA,BBB",
            "capital": 100000,
            "market": "A",
            "output_dir": "reports",
            "format": "none",
        },
    )
    regime = {
        "market": "A",
        "status": "ok",
        "score": 30.0,
        "posture": "cautious",
        "posture_label": "谨慎",
        "risk_budget": 0.45,
        "new_positions_allowed": False,
        "reasons": [],
        "breadth": {},
        "technical": {},
    }

    builder_cls = patch("portfolio.builder.PortfolioBuilder").start()
    builder = builder_cls.return_value
    builder.build.return_value = type(
        "Portfolio",
        (),
        {
            "name": "My Portfolio",
            "positions": [],
            "metrics": {},
            "summary": lambda self=None: "Portfolio summary",
        },
    )()

    try:
        with patch("commands.portfolio._safe_market_regime", return_value=regime):
            with patch("commands.portfolio._save_report"):
                cmd_portfolio(args)
    finally:
        patch.stopall()

    builder.build.assert_called_once()
    assert builder.build.call_args.kwargs["capital_fraction"] == 0.45
    output = capsys.readouterr().out
    assert "市场状态: 谨慎" in output


def test_cmd_sync_symbol_reports_summary(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "symbol",
            "code": "601318",
            "market": "A",
            "days": 365,
            "skip_fundamentals": False,
            "full_history": False,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.sync.sync_symbol_data") as mock_sync:
        mock_sync.return_value = {
            "code": "601318",
            "market": "A",
            "history_before": 10,
            "history_after": 365,
            "history_ready": True,
            "history_covered_through": "2026-07-01",
            "fundamentals_required": True,
            "fundamentals_before": False,
            "fundamentals_after": True,
            "fundamentals_covered_through": "2026-07-01",
            "ready": True,
            "errors": [],
        }
        with patch("commands.sync._save_report"):
            cmd_sync(args)

    output = capsys.readouterr().out
    assert "Synchronizing symbol 601318" in output
    assert "History: before=10, after=365" in output
    assert "Ready: yes" in output


def test_cmd_sync_watchlist_reports_scope_summary(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "watchlist",
            "market": "A",
            "days": 365,
            "skip_fundamentals": False,
            "full_history": False,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.sync.sync_watchlist_data") as mock_sync:
        mock_sync.return_value = {
            "requested": 3,
            "ready": 2,
            "cache_hits": 1,
            "history_fetched_count": 2,
            "fundamentals_fetched_count": 1,
            "covered_through": "2026-07-01",
            "missing_codes": ["600519"],
            "symbols": [],
        }
        with patch("commands.sync._save_report"):
            cmd_sync(args)

    output = capsys.readouterr().out
    assert "Synchronizing watchlist" in output
    assert "Scope watchlist: requested=3, ready=2" in output
    assert "Missing codes: 600519" in output


def test_cmd_sync_portfolio_uses_codes(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "portfolio",
            "codes": "600519,000858",
            "market": "A",
            "days": 365,
            "skip_fundamentals": False,
            "full_history": False,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.sync.sync_portfolio_data") as mock_sync:
        mock_sync.return_value = {
            "requested": 2,
            "ready": 2,
            "cache_hits": 2,
            "history_fetched_count": 0,
            "fundamentals_fetched_count": 0,
            "covered_through": "2026-07-01",
            "missing_codes": [],
            "symbols": [],
        }
        with patch("commands.sync._save_report"):
            cmd_sync(args)

    mock_sync.assert_called_once_with(
        ["600519", "000858"],
        market="A",
        history_days=365,
        need_fundamentals=True,
        full_history=False,
    )


def test_cmd_sync_etf_uses_etf_scope(capsys):
    from run import cmd_sync

    args = type(
        "Args",
        (),
        {
            "type": "etf",
            "codes": "510300,159915",
            "days": 365,
            "output_dir": "reports",
            "format": "none",
        },
    )

    with patch("commands.sync.sync_etf_data") as mock_sync:
        mock_sync.return_value = {
            "requested": 2,
            "ready": 2,
            "cache_hits": 1,
            "history_fetched_count": 1,
            "fundamentals_fetched_count": 0,
            "covered_through": "2026-07-01",
            "missing_codes": [],
            "symbols": [],
        }
        with patch("commands.sync._save_report"):
            cmd_sync(args)

    mock_sync.assert_called_once_with(
        ["510300", "159915"],
        history_days=365,
    )
    output = capsys.readouterr().out
    assert "Synchronizing ETFs (2 symbols, days=365)" in output
    assert "Scope etf: requested=2, ready=2" in output


def test_cmd_status_symbol_reads_sync_state(capsys):
    from run import cmd_status

    args = type(
        "Args",
        (),
        {
            "type": "symbol",
            "code": "601318",
            "market": "A",
        },
    )

    with (
        patch("commands.sync.get_cache") as mock_get_cache,
        patch("commands.sync.get_stock_pool") as mock_pool,
    ):
        mock_pool.return_value = [
            {
                "code": "601318",
                "metadata_completeness": 1.0,
                "metadata_source": "manual",
                "metadata_status": "active",
                "is_active": 1,
            }
        ]
        mock_get_cache.return_value.get_sync_state.return_value = [
            {
                "data_kind": "history",
                "code": "601318",
                "status": "ok",
                "last_covered_date": "2026-07-01",
                "last_success_at": "2026-07-01 10:00:00",
                "last_error": "",
            }
        ]
        cmd_status(args)

    output = capsys.readouterr().out
    assert "Sync state for symbol" in output
    assert "Metadata symbol: complete=1, partial=0, low=0" in output
    assert "status=ok" in output


def test_cmd_status_watchlist_prints_scope_summary(capsys):
    from run import cmd_status

    args = type(
        "Args",
        (),
        {
            "type": "watchlist",
            "market": "A",
        },
    )

    with (
        patch("commands.sync.get_cache") as mock_get_cache,
        patch("commands.sync.cfg_get") as mock_cfg,
        patch("commands.sync.get_stock_pool") as mock_pool,
    ):
        mock_cfg.side_effect = lambda key, default=None: {
            "watchlist": ["600519", "000858"],
            "cache_ttl.daily_kline": 3600,
            "cache_ttl.financial": 604800,
            "cache_ttl.fund_nav": 3600,
        }.get(key, default)
        mock_pool.return_value = [
            {
                "code": "600519",
                "metadata_completeness": 1.0,
                "metadata_source": "manual",
                "metadata_status": "active",
                "is_active": 1,
            },
            {
                "code": "000858",
                "metadata_completeness": 0.25,
                "metadata_source": "manual",
                "metadata_status": "active",
                "is_active": 1,
            },
        ]
        mock_get_cache.return_value.get_sync_state.side_effect = [
            [
                {
                    "data_kind": "summary",
                    "code": "",
                    "status": "partial",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2026-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "history",
                    "code": "600519",
                    "status": "ok",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2099-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "history",
                    "code": "000858",
                    "status": "partial",
                    "last_covered_date": "",
                    "last_success_at": "",
                    "last_error": "timeout",
                }
            ],
        ]
        cmd_status(args)

    output = capsys.readouterr().out
    assert "Scope watchlist: requested=2" in output
    assert "Metadata watchlist: complete=1, partial=0, low=1" in output
    assert "Top missing/problem symbols: 000858" in output


def test_cmd_status_etf_prints_scope_summary(capsys):
    from run import cmd_status

    args = type(
        "Args",
        (),
        {
            "type": "etf",
            "codes": "510300,159915",
        },
    )

    with (
        patch("commands.sync.get_cache") as mock_get_cache,
        patch("commands.sync.cfg_get") as mock_cfg,
        patch("commands.sync.get_etf_pool") as mock_pool,
    ):
        mock_cfg.side_effect = lambda key, default=None: {
            "cache_ttl.daily_kline": 3600,
            "cache_ttl.financial": 604800,
            "cache_ttl.fund_nav": 3600,
        }.get(key, default)
        mock_pool.return_value = [
            {
                "code": "510300",
                "metadata_completeness": 0.75,
                "metadata_source": "akshare_fund_etf_spot_em",
                "metadata_status": "active",
                "is_active": 1,
            },
            {
                "code": "159915",
                "metadata_completeness": 0.25,
                "metadata_source": "akshare_fund_etf_spot_em",
                "metadata_status": "active",
                "is_active": 1,
            },
        ]
        mock_get_cache.return_value.get_sync_state.side_effect = [
            [
                {
                    "data_kind": "summary",
                    "code": "",
                    "status": "partial",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2026-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "nav",
                    "code": "510300",
                    "status": "ok",
                    "last_covered_date": "2026-07-01",
                    "last_success_at": "2099-07-01 10:00:00",
                    "last_error": "",
                }
            ],
            [
                {
                    "data_kind": "nav",
                    "code": "159915",
                    "status": "partial",
                    "last_covered_date": "",
                    "last_success_at": "",
                    "last_error": "timeout",
                }
            ],
        ]
        cmd_status(args)

    output = capsys.readouterr().out
    assert "Scope etf: requested=2" in output
    assert "Metadata etf: complete=1, partial=0, low=1" in output
    assert "Sync state for etf (market=FUND)" in output
