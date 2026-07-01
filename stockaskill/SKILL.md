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
| Sentiment, sentiment, 情绪 | Market sentiment check |
| Refresh, 刷新, cache | Data operations |

## Before you start

Check the Python environment first:

    python --version
    uv pip list >/dev/null

If `python` is not `>=3.10`, or `uv pip list` fails because the environment is
missing, build a local environment with `uv`:

    uv venv --python 3.10 .venv
    source .venv/bin/activate
    uv pip install akshare efinance baostock pandas numpy scipy

Optional cold-start bootstrap:

    python stockaskill/scripts/run.py fetch pool

If the cache is cold, `analyze`, `diagnose`, `scan`, `alpha`, `portfolio`,
and `backtest` now warm only the data they actually need before scoring.

## Workflows

### 1. Single stock analysis

Normalize code by convention: 6xxxxx/0xxxxx/3xxxxx = A, xxxx.HK = HK, plain ticker = US.

    python stockaskill/scripts/run.py analyze 600519 --market A

Output: PE/PB/ROE/Dividend, composite factor scores, strategy signal.

### 2. Deep diagnosis

Comprehensive BUY/SELL/HOLD with risk assessment:

    python stockaskill/scripts/run.py diagnose 600519 --market A

JSON structure: final_decision.signal, adjusted_score, factors, strategy,
technical, sentiment, fundamentals, risks.

Present results:
- BUY  -> include stop-loss and take-profit references
- SELL -> explain risk factors
- HOLD -> explain what would need to change

### 3. Market scan

    python stockaskill/scripts/run.py scan A --top 20
    # default mode=auto: prefer fresh snapshot, else fallback to bounded realtime
    # Also: scan HK --top 10, scan US --top 15, scan FUND --top 20

Explicit modes:

    python stockaskill/scripts/run.py scan A --mode snapshot --top 20
    python stockaskill/scripts/run.py scan A --mode realtime --top 20

If scan returns all zeros, fall back to alpha mode:

    python stockaskill/scripts/run.py alpha A --top 20 --candidates 200

For sector-filtered scanning:

    python -c "from advisor.scanner import MarketScanner; print(MarketScanner().scan_by_sector('A', top_n=5))"

### 4. Alpha momentum scan

Full multi-factor ranking with thread-parallel scoring:

    python stockaskill/scripts/run.py alpha A --top 10 --candidates 200

Results include ranked list with scores, signals, F-Score, and BUY summary.
Explain which factors drove top rankings (momentum + low-vol + quality ~73% combined).

### 5. Portfolio construction

Standard portfolio:

    python stockaskill/scripts/run.py portfolio --codes 600519,000858,002475 --capital 1000000 --market A

Enhanced core-satellite:

    python stockaskill/scripts/run.py portfolio-enhanced --capital 1000000

### 6. Backtest

Standard backtest (Alpha Momentum, 2018-2026):

    python stockaskill/scripts/run.py backtest

Enhanced backtest (core-satellite):

    python stockaskill/scripts/run.py backtest-enhanced

Backtest paths warm a bounded batch of missing symbols plus market index data.
They do not force a full-market historical sync on every run.

### 7. Fund/ETF screening

    python stockaskill/scripts/run.py scan FUND --top 20

For deeper programmatic access:

    from data_engine import get_etf_pool, get_etf_nav
    funds = get_etf_pool()
    nav = get_etf_nav("510300", days=365)

Current `FUND` behavior is ETF-first. Broad mutual-fund NAV ingestion is not a
core supported workflow yet.

### 8. Data operations

    python stockaskill/scripts/run.py fetch pool                # full pool refresh
    python stockaskill/scripts/run.py fetch kline 600519        # single stock K-line
    python stockaskill/scripts/run.py fetch fundamentals 600519 # single stock fundamentals

Bounded sync and diagnostics:

    python stockaskill/scripts/run.py sync symbol 600519 --market A
    python stockaskill/scripts/run.py sync watchlist --market US
    python stockaskill/scripts/run.py sync portfolio --codes 0700,9988 --market HK
    python stockaskill/scripts/run.py sync etf --codes 510300,159915
    python stockaskill/scripts/run.py sync scan-universe --market A --limit 200
    python stockaskill/scripts/run.py status data symbol 600519 --market A
    python stockaskill/scripts/run.py status data watchlist --market US
    python stockaskill/scripts/run.py status data etf --codes 510300,159915

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
| ModuleNotFoundError: No module named config | Wrong working directory | Run from project root and call `python stockaskill/scripts/run.py ...` |
| Scan returns 0 results | Cache empty or candidate history missing | run `python stockaskill/scripts/run.py fetch pool` once, then retry |
| Daily API limit reached | Local API budget or upstream throttling reached | Wait; use cached data |
| No BUY signals | Market weakness or cold cache | Run diagnose on individual stocks |
| import akshare fails | Not installed | pip install akshare efinance baostock |
| Code not found | Pool not fetched for that market | `python stockaskill/scripts/run.py fetch pool` |
| Backtest fails | Too much history missing on a cold cache | rerun after bounded warmup completes, or prefetch pools first |
| HK/US candidates look noisy | Cross-market metadata incomplete | check `status data` metadata summary before trusting rankings |

## Key principles

1. **Local-first, fetch on miss** - SQLite cache before AKShare API. Reuse cached data whenever it is sufficient and fresh.
2. **Multi-factor, multi-strategy** - Weighted vote across 6 strategies from 7 factor dimensions.
3. **Task-scoped warmup** - `analyze`/`scan`/`backtest` fetch only the minimal missing pool, history, fundamentals, or index data.
4. **Market-aware caching** - A/HK/US/FUND pools and TTL metadata are tracked independently.
5. **ETF-first fund semantics** - `FUND` currently means exchange-traded ETF workflows, not broad mutual-fund coverage.
6. **Metadata-aware cross-market support** - HK/US pools carry source, status, and completeness signals; low-quality metadata may be soft-penalized in ranking.
7. **Script-driven** - Run `python stockaskill/scripts/run.py`, never reimplement logic.
8. **Parallel scoring** - Thread pool (8 workers) for alpha scans.
9. **Graceful degradation** - Cache-only mode on API limit. Partial results over failures.

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

Skill version: `1.3`

## Output file specs

1. **Path**: ./reports/
2. **Naming**: YYYY-MM-DD-HHMM_Short Title.json or .md
3. **Format**: Standard Markdown with hierarchy

## Risk disclaimer

For investment reference only, not investment advice. Data sources are third-party public platforms with 10-15 minute delay. Past performance does not guarantee future returns.
