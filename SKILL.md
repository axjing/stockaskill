---
name: stockaskill
description: >-
  Multi-market intelligent stock selection agent for A-share/HK/US markets and
  ETFs/mutual funds. Supports 7-factor analysis (value/quality/growth/momentum/
  low-vol/size/F-Score), 6 quantitative strategies (multi-factor/deep-value/
  GARP/MA-trend/contrarian/alpha-momentum), portfolio construction with Kelly
  sizing, backtesting, and sentiment aggregation. Use when the user asks about
  stock analysis, market scanning, portfolio construction, factor screening,
  quantitative strategy signals, fund screening, backtesting, or investment
  diagnosis for Chinese A-shares, Hong Kong stocks, US stocks, or ETFs/mutual
  funds.
license: MIT
compatibility: >-
  Requires Python 3.10+, pip packages (akshare, efinance, baostock, pandas,
  numpy, scipy), network access for AKShare data (free, no API key), and SQLite
  for caching (A-share/HK/US markets and
  ETFs/mutual funds).
metadata:
  author: stockaskill-team
  version: "1.1"
  short-description: Multi-market intelligent stock selection with AKShare, 7-factor
    analysis, 6 quant strategies, and portfolio management
---

# Smart Stock Selector

Multi-market intelligent stock selection system with AKShare + SQLite caching.
Covers A-shares, HK stocks, US stocks, and funds (ETF/LOF/active).

## Core promise

Given a stock code, market, or investment theme, run quantitative analysis and return actionable signals with scores. All analysis is script-driven and cache-backed for speed.

## Request router

Classify the user request and run the matching workflow:

- **Single stock analysis** — User gives a code like `600519`, `AAPL`, `0700.HK`: run 7-factor analysis + strategy signals + technical indicators.
- **Deep diagnosis** — User asks for comprehensive report with BUY/SELL/HOLD: run full pipeline including sentiment and risk.
- **Market scan** — User asks to find top stocks in a market: use scanner to rank by composite score.
- **Alpha momentum** — User wants momentum-driven ranking: run alpha momentum strategy with multi-factor optimization.
- **Portfolio construction** — User gives multiple codes or wants to build a portfolio: use builder with allocation strategies.
- **Backtest** — User wants to validate a strategy historically: run backtest engine.
- **Fund/ETF screening** — User asks about funds or ETFs: fetch fund pool and NAV data.
- **Sentiment check** — User asks about market sentiment or north-bound flow: run sentiment aggregation.
- **Data refresh** — Cache is stale or user explicitly asks to refresh: run fetch commands.

## Default behavior

Check the cache first for all data fetches. Refresh only when:
- TTL has expired (pool: 24h, fundamentals: 7d, sentiment: 1h, K-line: incremental).
- User explicitly requests fresh data.
- `cached_only` flag is not set.

If cache is empty, fetch from AKShare automatically. Run the full pipeline before giving a final answer.

When the user gives a Chinese stock name like "贵州茅台" instead of a code, use the stock pool to resolve it to a code before analysis.

## Prerequisites

Run these steps if the environment hasn't been set up:

1. Install dependencies:
   `pip install akshare efinance baostock pandas numpy scipy`

2. Set the project root as working directory (where `scripts/` is directly accessible).

3. Verify the shell has UTF-8 support (the CLI forces UTF-8 on Windows automatically).

## Workflows

### 1. Market Scan

Use when the user wants to find top stocks in a market.

Steps:
1. If cache is empty or stale, run `python scripts/run.py fetch pool` to refresh stock pool.
2. Run the CLI scanner:
   `python scripts/run.py scan A --top 20`
   For other markets: `scan HK --top 10`, `scan US --top 15`, `scan FUND --top 20`.
3. If `scan` returns no results (all scored 0), switch to alpha mode with full scoring:
   `python scripts/run.py alpha A --top 20 --candidates 200`

Output format:
```
排名  代码        名称        得分   信号   F
-------------------------------------------------
1     600519     贵州茅台     85.3   BUY    8
2     000858     五粮液       78.1   BUY    7
...
```

If the user wants sector-filtered scanning, use the Python API:
`python -c "from advisor.scanner import MarketScanner; scanner = MarketScanner(); results = scanner.scan_by_sector('A', top_n=5)"`

### 2. Single Stock Analysis

Use when the user gives a stock code for basic information.

Steps:
1. Normalize the code if needed. Detect market from prefix conventions:
   - `6xxxxx`, `0xxxxx`, `3xxxxx` → A-share
   - `xxxx.HK`, `0xxxx.HK` → HK
   - Ticker without prefix, `AAPL` pattern → US
2. Run the CLI: `python scripts/run.py analyze 600519 --market A`
3. The output shows: K-line cache status, fundamentals (PE/PB/ROE/Dividend), composite factor score by dimension, and strategy signal.

Output fundamentals explained:
```
Analyzing 600519 (market=A)...
  K-line data: 245 days cached
  PE(TTM):    28.5
  PB:         6.2
  ROE:        21.3%
  DivYld:     1.8%
  MktCap:     2,150,000,000,000
  Composite Score: 82.3/100
    value:    45.2  (PE/PB percentile relative to A-share)
    quality:  88.7  (ROE, margins, debt safety)
    growth:   72.1  (revenue/profit YoY)
    momentum: 76.5  (6-month price, MA alignment)
    low_vol:  65.0  (12-month volatility)
    size:     30.2  (large-cap penalty)
  Strategy Signal: BUY (score=78.5)
```

### 3. Deep Diagnosis

Use when the user wants a comprehensive BUY/SELL/HOLD recommendation with risk assessment.

Steps:
1. Run: `python scripts/run.py diagnose 600519 --market A`
2. Parse the JSON output:
   - `final_decision.signal` — BUY/SELL/HOLD
   - `adjusted_score` — 0-100 after sentiment adjustment
   - `factors` — 7-dimension factor scores with details
   - `strategy` — 6-strategy aggregation with individual signals
   - `technical` — MA alignment, support/resistance, RSI-14
   - `sentiment` — market breadth + north flow + guba adjustment factor
   - `fundamentals` — valuation assessment, financial health
   - `risks` — identified risk factors and severity

Output format:
```json
{
  "code": "600519",
  "final_decision": {
    "signal": "BUY",
    "adjusted_score": 72.5,
    "base_score": 68.0,
    "stop_loss": 1480.50,
    "take_profit": 1980.00
  },
  "factors": { "total_score": 82.3, "f_score": 8 },
  "strategy": { "final_signal": "BUY", "final_score": 68.0 },
  "technical": {
    "ma5": 1580, "ma10": 1550, "ma20": 1520, "ma60": 1450,
    "rsi_14": 62.5, "trend": "bullish"
  },
  "risks": { "risk_level": "low", "risks": [] }
}
```

3. Present the result to the user. For BUY signals, include stop-loss and take-profit reference prices. For SELL, explain the risk factors. For HOLD, explain what would need to change.

### 4. Alpha Momentum Scan

Use when the user wants a momentum-driven, multi-factor ranking. More comprehensive than scan, uses full scoring (not cache-only).

Steps:
1. Ensure stock pool is cached: `python scripts/run.py fetch pool`
2. Run: `python scripts/run.py alpha A --top 10 --candidates 200`
3. The output includes ranked list with scores, signals, and F-Score, plus a summary of BUY-signal stocks.

Output format:
```
排名   代码         名称       得分    信号   F
-------------------------------------------------
1      002475      立讯精密    85.2   BUY    7
2      300750      宁德时代    82.1   BUY    8
...

推荐买入 (BUY信号):
  002475 立讯精密 (得分=85.2, F=7)
  300750 宁德时代 (得分=82.1, F=8)
```

When the alpha momentum ranks are reported, explain:
- Which factors drove the top rankings (momentum + low-vol + quality weighted 73% combined).
- Whether the top candidates show sector concentration.
- How the Enhanced Momentum variant differs (ETF core overlay + optimized factor weights).

### 5. Portfolio Construction

Use when the user wants to build or review a portfolio.

Steps:
1. Gather parameters: stock codes, capital amount, market, allocation method.
2. Run CLI for standard portfolio:
   `python scripts/run.py portfolio --codes 600519,000858,002475 --capital 1000000 --market A`
3. For the enhanced core-satellite portfolio:
   `python scripts/run.py portfolio-enhanced --capital 1000000`
   (ETF core: 沪深300 17%, 创业板 12%, 科创50 11% + Alpha Momentum Top 3)

Output format:
```
Portfolio: My Portfolio
Capital:   1,000,000
Positions: 3
Allocated: 85.3%
  600519 贵州茅台: 35.0% (450 shares @ 1580.00)
  000858 五粮液:   28.0% (1800 shares @ 155.00)
  002475 立讯精密: 22.3% (5000 shares @ 44.50)
Risk Metrics:
  Sharpe: 1.25
  Sortino: 1.52
  MaxDD: -0.18
  VaR(95%): -0.023
  CVaR(95%): -0.035
```

When the user wants a specific allocation method, use the Python API:
- Equal weight: `from portfolio.allocator import equal_weights`
- Signal-weighted: `from portfolio.allocator import signal_weighted`
- Risk parity: `from portfolio.allocator import risk_parity`
- Min variance: `from portfolio.allocator import min_variance`

For position sizing:
```python
from portfolio.position import compute_position
result = compute_position(code="600519", name="贵州茅台", market="A",
    capital=100000, score=75.0, current_price=100.0,
    method="kelly", max_weight=0.25)
```

### 6. Backtest

Use when the user wants to validate a strategy's historical performance.

Steps:
1. Ensure sufficient historical data exists (requires >= 1500 trading days in cache).
2. Run standard backtest:
   `python scripts/run.py backtest`
3. Run enhanced core-satellite backtest:
   `python scripts/run.py backtest-enhanced`

Output format:
```
Pool: 200 stocks, 8 years
Period: 2018-01 ~ 2026-06
CAGR: 18.50%
Total Return: 285.00%
Sharpe: 1.32
Max Drawdown: -15.80%
Monthly Avg: 1.42%
Result: PASS (CAGR 18.50% > 12% target)
```

When reporting backtest results, explain:
- The CAGR target (12% standard, 18% enhanced).
- Whether the result passed or failed the target.
- The Max Drawdown period context (avoid cherry-picking).
- That past performance does not guarantee future returns.

### 7. Fund/ETF Screening

Use when the user asks about funds or ETFs.

Steps:
1. Run: `python scripts/run.py fetch pool` (includes FUND market).
2. Run scanner: `python scripts/run.py scan FUND --top 20`
3. For fund NAV history, use Python API:
   ```python
   from data_engine import get_fund_nav
   nav = get_fund_nav("510300", days=365)
   ```

For deeper analysis, use the Python API:
```python
from data_engine import get_fund_pool
funds = get_fund_pool()
# Filter by type, sort by scale
etfs = [f for f in funds if f.get("fund_type") == "ETF"]
etfs.sort(key=lambda x: float(x.get("scale", 0)), reverse=True)
```

### 8. Data Operations

Use when cache needs refresh or management.

Refresh commands:
- Full pool refresh: `python scripts/run.py fetch pool`
- Single stock K-line: `python scripts/run.py fetch kline 600519 --market A`
- Single stock fundamentals: `python scripts/run.py fetch fundamentals 600519 --market A`

Cache cleanup (from Python):
```python
from cache import get_cache
cache = get_cache()
removed = cache.cleanup(max_age_days=30, max_size_mb=500)
# Returns {"daily_price": N, "sentiment": N, "factor_snapshot": N}
```

## Analysis frameworks

### Factor system

7 dimensions, each returning a 0-1 percentile score:

| Factor | Weight | Core Metrics |
|--------|:---:|------------|
| Value | 18% | PE_TTM, PB percentile, dividend yield |
| Quality | 22% | ROE (40%), margin stability (25%), debt safety (20%), FCF (15%) |
| Growth | 15% | Revenue YoY, profit YoY, growth acceleration |
| Momentum | 15% | 6-month momentum (excl. 1-month reversal), MA alignment |
| Low Vol | 10% | 12-month volatility, max drawdown penalty |
| Size | 8% | log(market cap) negative scoring |
| F-Score | Bonus | Piotroski 9-point system |

Composite score = weighted sum + F-Score bonus, normalized to 0-100.

### Strategy system

6 strategies with weighted voting:

| Strategy | Weight | Logic |
|----------|:---:|-------|
| Multi-Factor | 30% | 7-factor composite, >=70=BUY, <=30=SELL |
| Deep Value | 25% | PE<25th%, PB<1.5, yield>3%, F-Score>=6 |
| GARP | 20% | PEG<1, ROE>15%, revenue growth>10% |
| MA Trend | 15% | MA5/10/20/60 alignment, golden/death cross |
| Contrarian | 10% | Oversold>15% from 60d high, low valuation |
| Alpha Momentum | 15% | Momentum(30%)+LowVol(28%)+Quality(21%)+Value(14%)+Growth(7%) |

Final signal: weighted vote across strategies. BUY if weighted score >= 65, SELL if <= 35, else HOLD.

### Sentiment adjustment

The sentiment aggregator computes an adjustment factor (0.8-1.2) based on:
- Market breadth (advance-decline ratio, from index data).
- North-bound flow (沪股通/深股通 net buy for A-shares).
- Guba sentiment (East Money 股吧 community sentiment score).

The final adjusted score = strategy base score * sentiment adjustment factor, then clamped to [0, 100].

### Enhanced Momentum variant

When the user mentions "enhanced" or "core-satellite" strategy:
- ETF core: 沪深300 (17%), 创业板 (12%), 科创50 (11%) = 40% total.
- Alpha momentum satellite: Top 3 stocks by enhanced score = 60% total (20% each).
- Enhanced weights: momentum 35%, low-vol 18%, quality 20%, value 17%, growth 10%.

## Output guidelines

Keep the answer concise when the user asks a quick question:

```
600519 贵州茅台:
  评分 82.3/100 | 信号: BUY (F=8)
  核心驱动: 质量(88.7) + 动量(76.5)
  风险: 低
  参考止损/止盈: 1480.50 / 1980.00
```

Provide a full report when the user asks for diagnosis or analysis:
- Start with the decision signal and score.
- List the top-3 driving factors.
- Include the strategy that triggered the signal.
- Note sentiment adjustment if significant (>5% impact).
- State the risk level and key risks.
- End with stop-loss and take-profit reference prices.

Use Chinese for Chinese market content unless the user writes in English. Use English for US/HK market content.

## Error handling

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'config'` | Wrong working directory | Run from project root (where `scripts/` is) or set PYTHONPATH |
| Scan returns 0 results | Cache empty or TTL expired | `python scripts/run.py fetch pool` first |
| "Daily API limit reached" | AKShare rate limit (500/day) | Wait until next day; use cached data |
| `RuntimeError: Daily API limit reached` | API calls exhausted | The system auto-degrades to cache; retry next day |
| `import akshare` fails | Package not installed | `pip install akshare efinance baostock` |
| No BUY signals in alpha scan | Market weakness or data not yet cached | Run `diagnose` on individual stocks first to build factor cache |

Python API error recovery patterns:
```python
from data_engine import get_kline
kline = get_kline("600519", "A", days=365, cached_only=True)  # Skip API if cache exists
```

## Reference files

Load only what is needed:
- [source paths by market](./references/market-source-playbook.md)
- [akshare official docs](./references/akshare_official_docs.md)
- [research partner and learning-mode behavior](./references/serenity-dialogue-protocol.md)
- [plain-language output contract](./references/output-style-and-language.md)
- [source map used by the project](./references/research-sources.md)
- [investment research boundaries](./references/risk-and-compliance.md)

## Python API quick reference

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
```

Data layer:
```python
from data_engine import get_stock_pool, get_kline, get_fundamentals
from data_engine import get_fund_pool, get_fund_nav
pool = get_stock_pool("A")
kline = get_kline("600519", "A", days=365)
fund = get_fundamentals("600519", "A")
nav = get_fund_nav("510300", days=365)
```

Analysis:
```python
from factors.composite import CompositeAnalyzer
result = CompositeAnalyzer("600519", "A").analyze()
# total_score (0-100), factors dict, f_score (0-9)

from strategies.aggregator import StrategyAggregator
signals = StrategyAggregator("600519", "A").analyze_all()
# final_signal, final_score, confidence, signals list

from advisor.diagnosis import StockDiagnosis
report = StockDiagnosis("600519", "A").full_report()
# full diagnosis dict with all sections

from advisor.scanner import MarketScanner
scanner = MarketScanner()
results = scanner.scan_top("A", top_n=20)
```

Portfolio and backtest:
```python
from portfolio.builder import PortfolioBuilder
from portfolio.backtest_engine import AlphaMomentumBacktest

builder = PortfolioBuilder("My Portfolio", capital=1_000_000)
builder.add_from_strategy("600519", "A")
portfolio = builder.build()

engine = AlphaMomentumBacktest(capital=1_000_000, low_vol_min=0.4)
result = engine.run()
```

Sentiment:
```python
from sentiment.aggregator import SentimentAggregator
sentiment = SentimentAggregator("600519", "A").get_sentiment_report()
# adjustment_factor (0.8-1.2), sources, scores
```

## Code structure

```text
scripts/
├── config.py              # Pure-Python config with dot-path access
├── cache.py               # SQLite cache manager with TTL, cleanup
├── data_engine.py         # Data engine with AKShare + fallbacks
├── models.py              # Data classes (StockInfo, KlineData, etc.)
├── utils.py               # Code normalization, market detection
├── run.py                 # CLI entry point
├── factors/               # 7-factor analysis modules
├── strategies/            # 6 quantitative strategies
├── portfolio/             # Portfolio management (builder, allocator, risk)
├── sentiment/             # Market sentiment aggregation
├── advisor/               # Smart advisory (diagnosis, scanner)
└── tools/                 # Utilities
```

## Risk disclaimer

Output is for investment reference only, not investment advice. Data sources are third-party public platforms with 10-15 minute delay. Historical backtest results do not represent future returns.

## Output File Specifications

1. Storage Path: Folder `./reports/`
2. File Naming Rule: `{YYYY-MM-DD-HHMM}_{Short Title}.md`
3. File Format: Standard Markdown with clear hierarchy and unified formatting for direct reuse