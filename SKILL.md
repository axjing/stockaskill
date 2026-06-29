---
name: stockaskill
description: >-
  Multi-market intelligent stock selection for A-share/HK/US stocks and
  ETFs. Use when user asks about stock analysis, market scanning,
  portfolio construction, factor screening, quantitative strategy
  signals, fund screening, backtesting, or investment diagnosis.
  Triggers on stock codes (600519, AAPL, 0700.HK), Chinese stock names
  (贵州茅台), fund codes (510300), and queries with keywords like
  "分析", "选股", "scan", "portfolio", "backtest", "因子", "评分",
  "BUY/SELL/HOLD", or "诊断".
license: MIT
compatibility: Requires Python 3.10+, akshare/efinance/baostock for data,
  network access (free, no API key), SQLite for caching.
metadata:
  author: stockaskill-team
  version: "1.1"
  short-description: Multi-market intelligent stock selection with AKShare
---

# Smart Stock Selector

Multi-market intelligent stock selection with AKShare + SQLite caching.
Covers A-shares, HK stocks, US stocks, and funds (ETF/LOF/active).

## Core promise

Given a stock code, market, or investment theme, run quantitative analysis
and return actionable signals with scores. All analysis is script-driven
and cache-backed for speed.

## When to Use

- Single stock analysis by code (600519, AAPL, 0700.HK) or name (贵州茅台)
- Deep diagnosis with BUY/SELL/HOLD recommendation
- Market scanning for top-ranked stocks in A/HK/US/FUND
- Momentum-driven alpha ranking with multi-factor scoring
- Portfolio construction with Kelly sizing and allocation methods
- Historical backtest to validate strategy performance
- Fund/ETF screening by NAV, scale, and performance
- Sentiment / market breadth check
- Data cache management and refresh

## When Not to Use

- Direct trade execution or brokerage API integration
- Real-time tick-level or Level-2 data
- Manual financial statement reading for deep fundamental research
- Macroeconomic analysis without stock-specific context
- Crypto or futures market analysis

## Prerequisites

1. **Install dependencies**:
   `pip install akshare efinance baostock pandas numpy scipy`

2. **Working directory**: Run commands from project root (where `scripts/` is directly accessible).

3. **UTF-8 support**: The CLI forces UTF-8 on Windows automatically.

4. **First run**: Refresh all data pools before scanning:
   `python scripts/run.py fetch pool`

## Default behavior

Check cache first for all data fetches. Refresh only when:
- TTL expired (pool: 24h, fundamentals: 7d, sentiment: 1h, K-line: incremental).
- User explicitly requests fresh data.
- `cached_only` flag is not set.

If cache is empty, fetch from AKShare automatically. Run the full pipeline before giving a final answer.

When the user gives a Chinese stock name like "贵州茅台" instead of a code, resolve it from the stock pool before analysis.

## Request router

| User intent | Workflow |
|-------------|----------|
| Single stock code or name | Run single stock analysis |
| Comprehensive report with BUY/SELL/HOLD | Run deep diagnosis |
| "Find top stocks in [market]" | Run market scan (fallback to alpha scan if empty) |
| Momentum-driven ranking | Run alpha momentum scan |
| Multiple codes or portfolio build | Run portfolio construction |
| Validate strategy historically | Run backtest |
| Fund/ETF query | Run fund screening |
| Market sentiment or north-bound flow | Run sentiment check |
| Cache refresh or stale data | Run data operations |

## Workflows

### 1. Single Stock Analysis

Normalize code by market convention:
- `6xxxxx`, `0xxxxx`, `3xxxxx` → A-share
- `xxxx.HK`, `0xxxx.HK` → HK
- Plain ticker (`AAPL`) → US

```bash
python scripts/run.py analyze 600519 --market A
```

Output includes PE/PB/ROE/Dividend, composite factor score by dimension, and strategy signal.

### 2. Deep Diagnosis

Comprehensive BUY/SELL/HOLD with risk assessment:
```bash
python scripts/run.py diagnose 600519 --market A
```

JSON output includes: `final_decision.signal`, `adjusted_score`, `factors`, `strategy`, `technical`, `sentiment`, `fundamentals`, `risks`.

Present the result:
- BUY → include stop-loss and take-profit reference prices
- SELL → explain risk factors
- HOLD → explain what would need to change

### 3. Market Scan

```bash
python scripts/run.py scan A --top 20
# Also: scan HK --top 10, scan US --top 15, scan FUND --top 20
```

If scan returns all zeros, fall back to alpha mode:
```bash
python scripts/run.py alpha A --top 20 --candidates 200
```

For sector-filtered scanning:
```bash
python -c "from advisor.scanner import MarketScanner; MarketScanner().scan_by_sector('A', top_n=5)"
```

### 4. Alpha Momentum Scan

Full multi-factor ranking with thread-parallel scoring:
```bash
python scripts/run.py alpha A --top 10 --candidates 200
```

Output includes ranked list with scores, signals, and F-Score, plus BUY summary.

When reporting, explain:
- Which factors drove top rankings (momentum + low-vol + quality weighted ~73% combined)
- Whether top candidates show sector concentration
- How Enhanced Momentum variant differs (see [references/enhanced-momentum.md](references/enhanced-momentum.md) if user mentions "enhanced")

### 5. Portfolio Construction

Standard portfolio:
```bash
python scripts/run.py portfolio --codes 600519,000858,002475 --capital 1000000 --market A
```

Enhanced core-satellite:
```bash
python scripts/run.py portfolio-enhanced --capital 1000000
```

For custom allocation methods via Python API (equal weight, signal-weighted, risk parity, min variance), load [references/python-api.md](references/python-api.md).

### 6. Backtest

Standard backtest (Alpha Momentum, 2018-2026):
```bash
python scripts/run.py backtest
```

Enhanced backtest (core-satellite):
```bash
python scripts/run.py backtest-enhanced
```

Requires >= 1500 trading days in cache. When reporting results, explain:
- CAGR target (12% standard, 18% enhanced)
- Whether result passed or failed
- That past performance does not guarantee future returns

### 7. Fund/ETF Screening

```bash
python scripts/run.py scan FUND --top 20
```

For deeper analysis:
```python
from data_engine import get_fund_pool, get_fund_nav
funds = get_fund_pool()
nav = get_fund_nav("510300", days=365)
```

### 8. Data Operations

```bash
# Full pool refresh
python scripts/run.py fetch pool

# Single stock K-line
python scripts/run.py fetch kline 600519 --market A

# Single stock fundamentals
python scripts/run.py fetch fundamentals 600519 --market A
```

## Output guidelines

Quick answer format:
```
600519 贵州茅台:
  评分 82.3/100 | 信号: BUY (F=8)
  核心驱动: 质量(88.7) + 动量(76.5)
  风险: 低
  参考止损/止盈: 1480.50 / 1980.00
```

Full diagnosis report format:
1. Decision signal and score
2. Top-3 driving factors
3. Strategy that triggered the signal
4. Sentiment adjustment if >5% impact
5. Risk level and key risks
6. Stop-loss and take-profit reference prices

Use Chinese for A-share content unless the user writes in English. Use English for US/HK content.

## Gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'config'` | Wrong working directory | Run from project root (where scripts/ is) |
| Scan returns 0 results | Cache empty or TTL expired | `python scripts/run.py fetch pool` first |
| "Daily API limit reached" | AKShare rate limit (500/day) | Wait until next day; use cached data |
| No BUY signals in alpha scan | Market weakness or cache cold | Run `diagnose` on individual stocks to build cache |
| `import akshare` fails | Package not installed | `pip install akshare efinance baostock` |
| Code not found (e.g. "贵州茅台") | Pool not fetched | `python scripts/run.py fetch pool` to resolve names |
| Diagnose returns partial data | K-line cache too short | `python scripts/run.py fetch kline <code> --market A` |
| Backtest fails | Insufficient historical data | Ensure >= 1500 trading days cached |

Safe API fallback pattern:
```python
from data_engine import get_kline
kline = get_kline("600519", "A", days=365, cached_only=True)
```

## Key Principles

1. **Cache first, fetch on miss** — All data operations check SQLite cache before hitting AKShare API. Only refresh when TTL expires or user requests.
2. **Multi-factor, multi-strategy** — No single factor or strategy drives decisions. Final signal is a weighted vote across 6 strategies built from 7 factor dimensions.
3. **Script-driven analysis** — All workflows use `scripts/run.py` CLI. The agent runs commands, never reimplements logic.
4. **Parallel by default** — Alpha momentum scoring uses thread pool (8 workers) for speed. Market scans factor scores concurrently.
5. **Graceful degradation** — When API limit reached, system auto-degrades to cache-only mode. Partial results better than failures.

## Reference files

Load only what is needed:

- **Factor weights & scoring details**: [references/factors.md](references/factors.md) — load when explaining factor breakdown or scoring logic
- **Strategy weights & signal logic**: [references/strategies.md](references/strategies.md) — load when explaining strategy signals or enhanced weights
- **Sentiment adjustment**: [references/sentiment.md](references/sentiment.md) — load when running diagnosis or sentiment analysis
- **Python API & code structure**: [references/python-api.md](references/python-api.md) — load when user asks for programmatic access
- **Enhanced Momentum details**: [references/enhanced-momentum.md](references/enhanced-momentum.md) — load when user mentions "enhanced" or "core-satellite"
- **Market source paths**: [references/market-source-playbook.md](references/market-source-playbook.md)
- **AKShare official docs**: [references/akshare_official_docs.md](references/akshare_official_docs.md)
- **Output style & language**: [references/output-style-and-language.md](references/output-style-and-language.md)
- **Research sources**: [references/research-sources.md](references/research-sources.md)
- **Risk & compliance**: [references/risk-and-compliance.md](references/risk-and-compliance.md)
- **Serenity dialogue protocol**: [references/serenity-dialogue-protocol.md](references/serenity-dialogue-protocol.md)

## Output File Specifications

1. **Storage path**: `./reports/`
2. **Naming rule**: `{YYYY-MM-DD-HHMM}_{Short Title}.md`
3. **Format**: Standard Markdown with clear hierarchy and unified formatting for direct reuse

## Risk disclaimer

Output is for investment reference only, not investment advice. Data sources are third-party public platforms with 10-15 minute delay. Historical backtest results do not represent future returns.
