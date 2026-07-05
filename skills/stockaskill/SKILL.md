---
name: stockaskill
description: >-
  Multi-market intelligent stock selection for A-share, HK, US, and
  ETF-first workflows. Use when Codex needs to analyze individual
  stocks, run market scans, build portfolios, backtest strategies,
  diagnose BUY/SELL/HOLD signals, or warm bounded local market data.
  Triggers on stock codes (600519, AAPL, 0700.HK), ETF codes
  (510300, 159915), Chinese stock names (贵州茅台), and queries with
  keywords like 分析, 选股, scan, portfolio, backtest, 因子, 评分, ETF,
  场内基金, BUY/SELL/HOLD, or 诊断. Do not use for broad mutual-fund
  platforms or full-universe market-data sync requests.
---

# Smart Stock Selector

Multi-market stock selection with AKShare + SQLite caching. Covers A-shares, HK, US, and ETF-first fund workflows.

## Core promise

Given a stock code, market, or investment theme, return actionable signals with scores.
Use local cache first. Only fetch missing or stale pool, history, fundamentals, or index data.
Warm data by task scope, not by blind full-market full-history refresh.
Do not treat this skill as a warehouse or full-market sync platform.

## Scope boundary

- Treat this skill as a local-first analysis and decision engine.
- Prefer bounded sync for symbol, watchlist, portfolio, scan-universe, and ETF scopes.
- Treat `FUND` as ETF-first behavior for now.
- Do not use this skill as if it provided broad mutual-fund research or full-market daily sync orchestration.

## Triggers

Activate on any of these user intents:

| Keyword / pattern | Likely intent |
|---|---|
| Code like 600519, AAPL, 0700.HK, 510300 | Single stock analysis or diagnosis |
| Chinese name like 贵州茅台 | Resolve from pool, then analyze |
| Find top stocks in [market] | Market scan |
| Ranking, alpha, momentum | Alpha momentum scan |
| Portfolio, 组合, allocation | Portfolio construction |
| Backtest, 回测, validation | Historical backtest |
| ETF, 场内基金, 510300, 159915 | ETF screening / ETF data sync |
| Workflow, route, routine, 路线图?| Workflow recommendation / manifest routine |
| Thesis, postmortem, 复盘, thesis memory | Thesis capture / review / postmortem |
| Theme, 主题, 产业链?| Theme research |
| Scorecard, attribution, 评分卡?| Structured evaluation / attribution |
| Sentiment, sentiment, 情绪 | Market sentiment check |
| Refresh, 刷新, cache | Data operations |

## Before you start

Check the Python environment first:

    python --version
    uv pip list >/dev/null

If `python` is not `>=3.10`, or `uv pip list` fails because the environment is
missing, build a local environment with `uv`:

    uv venv --python 3.10 "$SKILL/.venv"
    # On Linux/macOS:
    source "$SKILL/.venv/bin/activate"
    # On Windows:
    # "$SKILL\.venv\Scripts\activate.ps1"
    uv pip install akshare efinance baostock pandas numpy scipy

The skill scripts live under the skill installation directory. On most systems
this is `~/.agents/skills/stockaskill/` (Linux/macOS) or
`%USERPROFILE%\.agents\skills\stockaskill\` (Windows). Use the absolute path
to `run.py`:

    # Use the skill-local Python environment for all commands:
    # Linux/macOS:
    "$SKILL/.venv/bin/python" "$SKILL/scripts/run.py" f`fetch pool`

    # Windows:
    "$SKILL\.venv\Scripts\python.exe" "$SKILL\scripts\run.py" f`fetch pool`

For brevity, commands below use `$SKILL` to mean the skill installation directory.

If the cache is cold, `analyze`, `diagnose`, `scan`, `alpha`, `portfolio`,
and `backtest` now warm only the data they actually need before scoring.

## Local cache and data strategy

All market data is stored in a local SQLite database at <skill-root>/.cache/quant_cache.db
relative to the project root. The cache follows a **cache-first + incremental sync** strategy:

1. **Read from cache first** — Every data request checks SQLite before making any API call.
2. **Fetch only missing gaps** — If cache has data through date X, only fetch from X to today (with 3-day overlap for corrections). Never redownload full history.
3. **Cold start seeds full history** — First run for a symbol pulls from a safe baseline (A: 2000-01-01, HK: 1995-01-01, US: 1990-01-01). Subsequent reads are incremental.
4. **Multi-source fallback** — AKShare (primary) -> baostock -> efinance. Sources with repeated failures are backed off automatically.
5. **UPSERT writes** — Latest data always wins; duplicates are overwritten.

The cache contains:

| Table | Content |
|---|---|
| stock_pool | A/HK/US/FUND symbol lists with metadata |
| daily_price | K-line history (OHLCV), keyed by code+date |
| `factor_snapshot` | Fundamental snapshots (PE/PB/ROE/etc.) |
| computed_factors | Pre-computed factor scores |
| `fund_info` | ETF pool metadata |
| `fund_nav` | ETF NAV history |
| market_index | Index K-line history |
| `api_usage` | Daily API call tracking |
| sync_state | Per-symbol sync status and covered dates |

The cache is created automatically on first data fetch or sync. Safe to delete
and re-warm via `fetch pool` or sync symbol <code>.

## Workflows

### 1. Single stock analysis

Normalize code by convention: 6xxxxx/0xxxxx/3xxxxx = A, xxxx.HK = HK, plain ticker = US.

    uv run python "$SKILL/scripts/run.py" analyze 600519 --market A

Output: PE/PB/ROE/Dividend, composite factor scores, strategy signal.

### 2. Deep diagnosis

Comprehensive BUY/SELL/HOLD with risk assessment:

    uv run python "$SKILL/scripts/run.py" diagnose 600519 --market A

JSON structure: final_decision.signal, adjusted_score, factors, strategy,
technical, sentiment, fundamentals, risks.

Present results:
- BUY  -> include stop-loss and take-profit references
- SELL -> explain risk factors
- HOLD -> explain what would need to change

For long-form reports:

    uv run python "$SKILL/scripts/run.py" deep-diagnose 600519 --market A --format both

Use `deep-diagnose` when the user wants a full memo-style diagnosis with
decision summary, evidence, risks, invalidation, and follow-up questions.

### 3. Workflow routing and manifests

Recommend a bounded workflow for a user goal:

    uv run python "$SKILL/scripts/run.py" route "复盘当前市场并筛选候选股"

Inspect built-in workflow manifests:

    uv run python "$SKILL/scripts/run.py" workflow list
    uv run python "$SKILL/scripts/run.py" workflow run market-regime-daily --market A

Important: `workflow run` only resolves a manifest into a concrete routine. It
does not execute shell commands or background jobs.

### 4. Market scan

    uv run python "$SKILL/scripts/run.py" scan A --top 20
    # default mode=auto: prefer fresh snapshot, else fallback to bounded realtime
    # Also: scan HK --top 10, scan US --top 15, scan FUND --top 20

Explicit modes:

    uv run python "$SKILL/scripts/run.py" scan A --mode snapshot --top 20
    uv run python "$SKILL/scripts/run.py" scan A --mode realtime --top 20

If scan returns all zeros, fall back to alpha mode:

    uv run python "$SKILL/scripts/run.py" alpha A --top 20 --candidates 200

For sector-filtered scanning:

    python -c "from advisor.scanner import MarketScanner; print(MarketScanner().scan_by_sector('A', top_n=5))"

**Note**: When running ad-hoc Python one-liners or importing skill modules, ensure
you are using the skill-local Python environment (`$SKILL/.venv/bin/python` or
`$SKILL\.venv\Scripts\python.exe`) so that dependencies resolve correctly.

### 5. Alpha momentum scan

Full multi-factor ranking with thread-parallel scoring:

    uv run python "$SKILL/scripts/run.py" alpha A --top 10 --candidates 200

Results include ranked list with scores, signals, F-Score, and BUY summary.
Explain which factors drove top rankings (momentum + low-vol + quality ~73% combined).

### 6. Portfolio construction

Both `portfolio` and `portfolio-enhanced` now follow a sync-then-cached-only flow:
they first sync missing history/fundamentals for the target symbols, then score
entirely from local cache. This avoids duplicate API fetches during analysis.

Standard portfolio:

    uv run python "$SKILL/scripts/run.py" portfolio --codes 600519,000858,002475 --capital 1000000 --market A

Enhanced core-satellite:

    uv run python "$SKILL/scripts/run.py" portfolio-enhanced --capital 1000000

Pre-warm portfolio data independently (optional):

    uv run python "$SKILL/scripts/run.py" sync portfolio --codes 600519,000858,002475 --market A

### 7. Backtest

Standard backtest (Alpha Momentum, 2018-2026):

    uv run python "$SKILL/scripts/run.py" backtest

Enhanced backtest (core-satellite):

    uv run python "$SKILL/scripts/run.py" backtest-enhanced

Backtest paths warm a bounded batch of missing symbols plus market index data.
They do not force a full-market historical sync on every run.

### 8. Fund/ETF screening

    uv run python "$SKILL/scripts/run.py" scan FUND --top 20

For deeper programmatic access:

    from data_engine import get_etf_pool, get_etf_nav
    funds = get_etf_pool()
    nav = get_etf_nav("510300", days=365)

Current `FUND` behavior is ETF-first. Broad mutual-fund NAV ingestion is not a
core supported workflow yet.

### 9. Research memory and theme workflows

Thesis memory:

    uv run python "$SKILL/scripts/run.py" thesis capture 600519 --market A
    uv run python "$SKILL/scripts/run.py" thesis list --market A
    uv run python "$SKILL/scripts/run.py" thesis review --code 600519 --market A
    uv run python "$SKILL/scripts/run.py" thesis postmortem --code 600519 --market A --outcome win

Theme research:

    uv run python "$SKILL/scripts/run.py" theme-scan AI 算力 --market A --top 5

Scorecards:

    uv run python "$SKILL/scripts/run.py" scorecard diagnose 600519 --market A
    uv run python "$SKILL/scripts/run.py" scorecard thesis --code 600519 --market A
    uv run python "$SKILL/scripts/run.py" scorecard theme AI 算力 --market A --top 5

Use these when the user wants a saved research trail, a review loop, or a
structured scorecard rather than a one-off diagnosis.

### 10. Data operations

    uv run python "$SKILL/scripts/run.py" f`fetch pool`                # full pool refresh
    uv run python "$SKILL/scripts/run.py" fetch kline 600519        # single stock K-line
    uv run python "$SKILL/scripts/run.py" fetch fundamentals 600519 # single stock fundamentals

Bounded sync and diagnostics:

    uv run python "$SKILL/scripts/run.py" sync symbol 600519 --market A
    uv run python "$SKILL/scripts/run.py" sync watchlist --market US
    uv run python "$SKILL/scripts/run.py" sync portfolio --codes 0700,9988 --market HK
    uv run python "$SKILL/scripts/run.py" sync etf --codes 510300,159915
    uv run python "$SKILL/scripts/run.py" sync scan-universe --market A --limit 200
    uv run python "$SKILL/scripts/run.py" status data symbol 600519 --market A
    uv run python "$SKILL/scripts/run.py" status data watchlist --market US
    uv run python "$SKILL/scripts/run.py" status data etf --codes 510300,159915
    uv run python "$SKILL/scripts/run.py" status data pool --market A
    uv run python "$SKILL/scripts/run.py" market-regime --market A

## Output guidelines

### Terminal output (auto-detected):

Use indicators for scannability:

    600519 贵州茅台
    评分 82.3/100 | 信号: BUY (F=8)
    核心驱动: 质量(88.7) + 动量(76.5)
    风险: 低
    参考止损/止盈: 1480.50 / 1980.00

### Full diagnosis report format:

1. Decision signal and score
2. Top-3 driving factors
3. Strategy that triggered the signal
4. Sentiment adjustment if >5% impact
5. Risk level and key risks
6. Stop-loss and take-profit reference prices

### JSON output (--format json):

All scripts accept --format json,md,both,none. JSON for programmatic use, MD for readable reports.

### Language:

Use Chinese for A-share content unless the user writes in English. Use English for US/HK.

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| ModuleNotFoundError: No module named config | Wrong working directory | Run from project root and call `uv run python "$SKILL/scripts/run.py" ...` |
| Scan returns 0 results | Cache empty or candidate history missing | run `uv run python "$SKILL/scripts/run.py" f`fetch pool`` once, then retry |
| Daily API limit reached | Local API budget or upstream throttling reached | Wait; use cached data |
| No BUY signals | Market weakness or cold cache | Run diagnose on individual stocks |
| import akshare fails | Not installed | uv pip install akshare efinance baostock |
| Code not found | Pool not fetched for that market | `uv run python "$SKILL/scripts/run.py" f`fetch pool`` |
| Backtest fails | Too much history missing on a cold cache | rerun after bounded warmup completes, or pref`fetch pool`s first |
| HK/US candidates look noisy | Cross-market metadata incomplete | check `status data` metadata summary before trusting rankings |

## Key principles

1. **Local-first, fetch on miss** — SQLite quant_cache.db before any AKShare API call. Incrementally backfill only missing date ranges. Never download full history on a warm cache. Reuse cached data whenever it is sufficient and fresh.
2. **Multi-factor, multi-strategy** - Weighted vote across 6 strategies from 7 factor dimensions.
3. **Task-scoped warmup** - `analyze`/`scan`/`backtest` fetch only the minimal missing pool, history, fundamentals, or index data.
4. **Market-aware caching** - A/HK/US/FUND pools and TTL metadata are tracked independently.
5. **ETF-first fund semantics** - `FUND` currently means exchange-traded ETF workflows, not broad mutual-fund coverage.
6. **Metadata-aware cross-market support** - HK/US pools carry source, status, and completeness signals; low-quality metadata may be soft-penalized in ranking.
7. **Script-driven** - Run `uv run python "$SKILL/scripts/run.py"`, never reimplement logic.
8. **Parallel scoring** - Thread pool (8 workers) for alpha scans.
9. **Research-memory aware** - Prefer thesis/theme/scorecard workflows when the user asks for follow-up, review, or attribution.
10. **Graceful degradation** - Cache-only mode on API limit. Partial results over failures.

## Reference files

Load only the references needed for the current task:

- Single-stock analysis, diagnosis, or factor explanations:
  `references/factors.md`, `references/strategies.md`
- CLI/Python usage, programmatic integration, or code-level questions:
  `references/python-api.md`
- ETF/core-satellite workflows:
  `references/enhanced-momentum.md`
- Data-source coverage, market limitations, or cache/sync behavior:
  `references/market-source-playbook.md`,
  `references/akshare_official_docs.md`
- Workflow routing or manifest routines:
  `references/workflows.md`
- Deep diagnosis long-report output:
  `references/deep-diagnosis.md`
- Thesis memory / postmortem:
  `references/thesis-memory.md`
- Theme research:
  `references/theme-research.md`
- Scorecards / attribution:
  `references/scorecards.md`
- Output wording and response style:
  `references/output-style-and-language.md`
- Sentiment-specific work:
  `references/sentiment.md`
- Research background:
  `references/research-sources.md`
- Risk, disclaimer, or policy-sensitive output:
  `references/risk-and-compliance.md`
- Dialogue constraints specific to this skill:
  `references/serenity-dialogue-protocol.md`

Skill version: `1.4`

## Output file specs

1. **Path**: ./reports/
2. **Naming**: YYYY-MM-DD-HHMM_Short Title.json or .md
3. **Format**: Standard Markdown with hierarchy

## Risk disclaimer

For investment reference only, not investment advice. Data sources are third-party public platforms with 10-15 minute delay. Past performance does not guarantee future returns.
