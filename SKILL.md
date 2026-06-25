---
name: stockaskill
description: >-
  Intelligent stock selection agent for A-share/HK/US markets and funds.
  Compatible with Codex, OpenCode, ClaudeCode, OpenClaw, and other
  SKILL.md-compatible agent frameworks. Uses AKShare as primary data source
  with SQLite full caching. Supports multi-factor analysis
  (value/quality/growth/momentum/low-vol/size), 5 quantitative strategies
  (multi-factor/deep-value/GARP/ma-trend/contrarian), portfolio management
  (Kelly/Risk Parity/backtest), sentiment aggregation, and smart advisory
  (BUY/SELL/HOLD with scoring). Use when the user asks about stock analysis,
  market scanning, portfolio construction, factor screening, quantitative
  strategy signals, fund screening, or investment diagnosis for Chinese
  A-shares, Hong Kong stocks, US stocks, or ETFs/mutual funds.
license: MIT
compatibility: >-
  Designed for Codex, OpenCode, ClaudeCode, OpenClaw, and other
  SKILL.md-compatible agent frameworks. Requires Python 3.10+, pip,
  and network access (AKShare data source).
---

# Smart Stock Selector

Multi-market intelligent stock selection system with AKShare + SQLite caching.
Covers A-shares, HK stocks, US stocks, and funds (ETF/LOF/active).

## Quick Start

```bash
cd path/to/stockaskill

# Analyze a single stock (K-line + valuation + fundamentals)
python scripts/run.py analyze 600519

# Deep diagnosis (strategies + sentiment + risk + technicals)
python scripts/run.py diagnose 601318 --market A

# Alpha momentum scan (CAGR 14.27% optimized strategy)
python scripts/run.py alpha A --top 10

# Scan market top N (supports A/HK/US/FUND)
python scripts/run.py scan A --top 20

# Build portfolio
python scripts/run.py portfolio --codes 601318,000858,600036 --capital 1000000

# Refresh data
python scripts/run.py fetch pool
python scripts/run.py fetch kline 600519
python scripts/run.py fetch fundamentals 002475

# Scheduled watchlist analysis
python scripts/run.py scheduler --run-now
```

## Python API

```python
from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from data_engine import get_stock_pool, get_kline, get_fundamentals
from data_engine import get_fund_pool, get_fund_nav
from advisor.diagnosis import StockDiagnosis
from advisor.scanner import MarketScanner
from strategies.aggregator import StrategyAggregator
from factors.composite import CompositeAnalyzer
from portfolio.builder import PortfolioBuilder
from portfolio.backtest import BacktestEngine
from sentiment.aggregator import SentimentAggregator

# Stock pool (cached, auto-refresh on TTL expiry)
pool = get_stock_pool("A")

# Individual stock analysis
diag = StockDiagnosis("600519", "A").full_report()
# Returns: final_decision, adjusted_score, factors, strategies, risks

# Factor analysis (7 dimensions + F-Score)
factors = CompositeAnalyzer("600519", "A").analyze()

# Strategy aggregation (5 strategies weighted vote)
signals = StrategyAggregator("600519", "A").analyze_all()

# Fund screening
funds = get_fund_pool()  # All cached funds
nav_history = get_fund_nav("510300", days=365)

# Portfolio with backtest
builder = PortfolioBuilder("My Portfolio", capital=1_000_000)
builder.add("600519", "A")
builder.add("000858", "A")
portfolio = builder.build()
print(portfolio.summary())
```

## Architecture

### Data Flow

```text
AKShare ──→ Data Engine ──→ SQLite Cache ──→ Factors/Strategies ──→ Advisor
 (fallback)    (retry)       (TTL/incr)        (0-1 scored)        (decision)
```

### Data Sources

| Level | Source | Purpose |
|-------|--------|---------|
| 1 (Primary) | AKShare | Full market coverage, free, no token |
| 2 (Fallback) | efinance | Market data supplement |
| 3 (Fallback) | baostock | Historical data supplement |

### SQLite Cache (`.cache/quant_cache.db`)

| Table | Content | Refresh |
|-------|---------|---------|
| stock_pool | All tradable stocks (A/HK/US) | TTL 24h |
| daily_price | Daily K-line (adjusted) | Incremental |
| factor_snapshot | Fundamentals (PE/PB/ROE/etc.) | TTL 7d |
| computed_factors | Computed factor values | Local calc |
| fund_info | Fund metadata | TTL 24h |
| fund_nav | Fund NAV history | Incremental |
| market_index | Index K-line (SSE/HSI/SPX) | TTL 24h |
| sentiment | Sentiment scores | TTL 1h |
| kv_store | Generic key-value cache | TTL variable |
| api_usage | Rate limit tracking | Auto |

All data is cached locally. Failed API calls degrade gracefully to cached data.

## Factor System

7 dimensions, each returning a 0-1 percentile score:

| Factor | Default Weight | Core Metrics |
|--------|:---:|------------|
| Value | 18% | PE_TTM percentile, PB percentile, dividend yield |
| Quality | 22% | ROE (40%), margin stability (25%), debt safety (20%), FCF (15%) |
| Growth | 15% | Revenue YoY, profit YoY, growth acceleration |
| Momentum | 15% | 6-month price momentum (excl. 1-month reversal), MA alignment |
| Low Vol | 10% | 12-month daily volatility, max drawdown penalty |
| Size | 8% | log(market cap) negative scoring |
| F-Score | Bonus | Piotroski 9-point system |

Weights configurable via `config.py` _DEFAULTS dict.

## Strategy System

5 strategies with weighted voting → BUY/SELL/HOLD + 0-100 score:

| Strategy | Weight | Logic |
|----------|:---:|-------|
| Multi-Factor | 30% | 7-factor weighted composite, >70=BUY, <30=SELL |
| Deep Value | 25% | PE<industry 25th%, PB<1.5, yield>3%, F-Score≥6 |
| GARP | 20% | PEG<1, ROE>15%, revenue growth>10%, 4Q positive |
| MA Trend | 15% | MA5/10/20/60 alignment, golden/death cross |
| Contrarian | 10% | Oversold>15% from 60d high, low valuation, volume stabilization |
| Alpha Momentum | 15% | Momentum(30%)+LowVol(28%)+Quality(21%)+Value(14%)+Growth(7%), Top6 monthly, CAGR 14.27% (2018-2026 backtest, 75 stocks) |

Final signal = weighted vote. Sentiment adjusts intensity (0.8x~1.15x) without changing direction.

## Portfolio Management

- **Allocation**: Equal weight, Risk Parity, Min Variance, Signal-weighted
- **Position sizing**: Kelly formula, Fixed fraction, per-asset cap
- **Risk metrics**: Max Drawdown, VaR/CVaR (95/99%), Sharpe, Sortino, Beta
- **Backtest**: Daily simulation with commission/stamp tax/slippage
- **Rebalance**: Calendar (weekly/monthly), threshold (>5% deviation), hybrid

## Sentiment

Aggregates from multiple sources into 0-1 score:

- Market breadth (advance/decline ratio)
- North-bound capital flow trend (A-share specific)
- Financial news sentiment (positive/negative keywords)

Output: adjustment multiplier 0.8x (extreme bearish) to 1.15x (extreme bullish).

## Smart Advisor

### Market Scanner

`MarketScanner.scan_top(market, top_n, filters)` returns ranked list with:
- Auto-filter ST/delisted/sub-new/suspended
- Sector/market cap range filtering
- Factor score breakdown per stock

### Stock Diagnosis

`StockDiagnosis(code, market).full_report()` returns:
- `final_decision`: BUY/SELL/HOLD
- `adjusted_score`: 0-100 after sentiment adjustment
- `factors`: 7-dimension factor scores
- `strategies`: individual strategy signals
- `technicals`: MA alignment, support/resistance levels
- `fundamentals`: valuation assessment, financial health
- `risks`: identified risk factors
- `stop_loss` / `take_profit`: reference prices

Decision logic: strategy_signal × sentiment_adjustment × risk_adjustment

## Code Structure

```text
scripts/
├── config.py              # Pure-Python config (no YAML)
├── cache.py               # SQLite cache manager
├── data_engine.py         # Data engine with AKShare + fallback
├── models.py              # Data classes
├── utils.py               # Code normalization utilities
├── run.py                 # CLI entry point
├── factors/               # 7-factor analysis
│   ├── base.py            # Factor base class + normalization
│   ├── value.py           # Valuation factors
│   ├── quality.py         # Quality factors
│   ├── growth.py          # Growth factors
│   ├── momentum.py        # Momentum factors
│   ├── low_vol.py         # Low volatility factors
│   ├── size.py            # Market cap factors
│   └── composite.py       # 7-factor aggregation + F-Score
├── strategies/            # 6 quantitative strategies
│   ├── base.py            # Strategy base class
│   ├── multi_factor.py    # Multi-factor strategy
│   ├── deep_value.py      # Deep value strategy
│   ├── garp.py            # GARP strategy
│   ├── ma_trend.py        # Moving average trend
│   ├── contrarian.py      # Contrarian strategy
│   ├── alpha_momentum.py  # Alpha momentum: momentum+low_vol+quality+value+growth
│   └── aggregator.py      # Weighted vote across strategies
├── portfolio/             # Portfolio management
│   ├── position.py        # Kelly + fixed fraction sizing
│   ├── allocator.py       # Equal/Risk Parity/Min Var/Signal
│   ├── risk.py            # Risk metrics
│   ├── builder.py         # Portfolio construction
│   ├── backtest.py        # Daily simulation backtest
│   └── rebalance.py       # Calendar/threshold rebalancing
├── sentiment/             # Market sentiment
│   ├── dictionary.py      # Financial sentiment lexicon
│   ├── sources.py         # Multi-source sentiment
│   └── aggregator.py      # Sentiment aggregation
└── advisor/               # Smart advisory
    ├── scanner.py         # Market scanner with filters
    └── diagnosis.py       # Individual stock diagnosis
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'config'` | Run from project root; `run.py` auto-fixes sys.path |
| First run is slow | Building local cache; takes ~2-5 minutes |
| API rate limited | System auto-degrades to cached data; retry next day |
| HK/US fundamentals missing | Partial data unavailable for some markets; graceful degradation |
| `ImportError: No module named 'akshare'` | `pip install akshare efinance baostock` |

## Dependencies

`pip install akshare efinance baostock pandas numpy scipy`

No PyYAML or other optional dependencies required.

## Risk Disclaimer

Output is for investment reference only, not investment advice.
Data sources are third-party public platforms with 10-15 minute delay.
Historical backtest results do not represent future returns.
Investment involves risk; proceed with caution.

## Output

将最终的输出结果以规范的markdown格式，写入reports文件夹下方便用户后续使用。
命名方式：`{简短标题}_{输出结果时的时间}.md`

## Bundled resources

**Load only what is needed:**
- [source paths by market.](./references/market-source-playbook.md)
- [akshare offical docs](./references/akshare_official_docs.md)
- [research partner and learning-mode behavior](./references//serenity-dialogue-protocol.md)
- [plain-language output contract](./references/output-style-and-language.md)
- [source map used by the project.](./references/research-sources.md)
- [investment research boundaries](./references/risk-and-compliance.md)
