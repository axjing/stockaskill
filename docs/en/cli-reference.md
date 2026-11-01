# Complete CLI Reference & Agent Tool Invocation Guide

> **Version**: 2.1.0  
> **CLI Entrypoint**: `python skills/stockaskill/scripts/run.py <command> [options]`

---

## 1. Global Common Options

The following flags can be passed to any sub-command:

| Option | Type | Default | Description |
|:---|:---|:---|:---|
| `--json` | Flag | `False` | **Recommended for Agents**: Streams clean JSON directly to `stdout`. Suppresses banners and colored text. Zero disk I/O. |
| `--output-dir` | String | `reports` | Target directory for generated report files. |
| `--format` | Choice | `both` | Report format: `json`, `md`, `both`, `none`. |

---

## 2. Command Overview

```
+------------------------+-----------------------------------------------------+
| Category               | Commands                                            |
+------------------------+-----------------------------------------------------+
| Screening & Portfolio  | screen, portfolio                                   |
| Single-Stock Diagnosis | diagnose (quick/full/deep), analyze*, deep-diagnose*|
| Thesis Lifecycle       | thesis (capture, list, update, track)               |
| Sync & Maintenance     | sync, cache stats, status                           |
| Market & Sentiment     | sentiment, regime, scan                             |
| Workflows & Evaluation | workflow (list, run), scorecard                     |
+------------------------+-----------------------------------------------------+
* Note: Asterisked commands are permanent aliases for backward compatibility.
```

---

## 3. Command Reference & Usage Examples

### 3.1 Vectorized Cross-Sectional Screening (`screen`)

Performs sub-second multi-factor ranking over 42.44M rows in DuckDB.

#### Options
- `--market`: Target market (`A` default, `HK`, `US`).
- `--preset`: Strategy preset:
  - `momentum_enhanced` (default): Momentum leadership with volume breakout.
  - `low_vol` / `low_volatility`: Low-volatility defensive candidates.
  - `deep_value` / `value`: Deep valuation with high Piotroski F-Scores.
  - `balanced`: Balanced multi-factor score.
- `--top`: Number of candidates, default `10`.
- `--min-mcap`: Minimum total market cap filter in 100M RMB, default `0`.
- `--sector`: Optional industry filter (e.g., `--sector 医药生物`).
- `--to-portfolio`: **Pipeline flag**. Directly passes candidates to the portfolio optimizer.
- `--capital`: Available investment capital, default `1000000`.
- `--track`: **Tracking flag**. Automatically registers positions into the Thesis memory store.

#### Examples
```bash
# Standard screen with pure JSON output
python skills/stockaskill/scripts/run.py screen --market A --preset low_vol --top 5 --json

# One-Shot Pipeline: Screen -> Optimize -> 100-Share Trade Tickets -> Track Thesis
python skills/stockaskill/scripts/run.py screen \
  --market A \
  --preset momentum_enhanced \
  --top 5 \
  --to-portfolio \
  --capital 1000000 \
  --track \
  --json
```

#### Sample `--json` Output
```json
{
  "market": "A",
  "preset": "momentum_enhanced",
  "top_n": 2,
  "count": 2,
  "candidates": [
    {
      "code": "688146",
      "name": "中船特气",
      "score": 346.0,
      "f_score": 0,
      "metrics": {"return_20d": 0.42, "close": 58.2}
    }
  ],
  "portfolio_pipeline": {
    "capital": 1000000.0,
    "weights": {"688146": 0.35},
    "trade_tickets": [
      {
        "code": "688146",
        "weight": 0.35,
        "target_value": 350000.0,
        "shares": 6000,
        "actual_value": 349200.0
      }
    ],
    "unallocated_cash": 650800.0,
    "thesis_ids": ["thesis_688146_20261101"]
  }
}
```

---

### 3.2 Goal-Constrained Portfolio Optimization (`portfolio`)

Uses SLSQP constrained mathematical programming to solve optimal Sharpe ratio weights, rounded down to 100-share board lots.

#### Options
- `--optimize`: Triggers mathematical programming optimization.
- `--codes`: Comma-separated symbol codes (e.g. `600519,000858,601318`).
- `--target-cagr`: Target annualized CAGR (e.g., `0.12` for 12%).
- `--max-drawdown`: Hard constraint on max historical drawdown (e.g., `0.08` for 8%).
- `--capital`: Investment capital, default `1000000`.
- `--market`: Market code, default `A`.

#### Example
```bash
python skills/stockaskill/scripts/run.py portfolio \
  --optimize \
  --codes 600519,000858,601318 \
  --target-cagr 0.10 \
  --max-drawdown 0.06 \
  --capital 500000 \
  --market A \
  --json
```

---

### 3.3 Unified Single-Stock Diagnosis Facade (`diagnose`)

#### Options
- `code`: Symbol code (e.g. `600519`).
- `--market`: Market code (`A`, `HK`, `US`, `FUND`).
- `--level`: Diagnosis depth level:
  - `quick`: Basic technicals, valuation ratios, Piotroski F-score, multi-factor scores.
  - `full` (default): 7-strategy signals, EastMoney sentiment, macro risk budget.
  - `deep`: Research-grade thesis, bull/bear arguments, conflict matrix, invalidation conditions.

#### Examples
```bash
# Agent rapid health check
python skills/stockaskill/scripts/run.py diagnose 600519 --level quick --json

# Complete strategy evaluation
python skills/stockaskill/scripts/run.py diagnose 600519 --level full

# Pre-position deep diagnosis
python skills/stockaskill/scripts/run.py diagnose 600519 --level deep --json
```

---

### 3.4 Dynamic Incremental Synchronization (`sync`)

Maintains DuckDB cache freshness.

#### Sub-actions
- `update <code>`: Incrementally update a single symbol.
- `scan-universe`: Sync market-wide symbol metadata.
- `symbol <code>`: Cold-start seed a symbol from base historical baseline.
- `--market`: Market code (`A`, `HK`, `US`, `FUND`).

#### Examples
```bash
# Incrementally sync Moutai
python skills/stockaskill/scripts/run.py sync update 600519 --market A

# Check symbol data readiness
python skills/stockaskill/scripts/run.py status data symbol 600519 --market A --json

# Check DuckDB database metrics
python skills/stockaskill/scripts/run.py cache stats --json
```

---

### 3.5 Investment Thesis Management (`thesis`)

Tracks the full lifecycle of an investment idea from entry to exit.

#### Sub-actions
- `capture <code>`: Persists a new thesis record with bull/bear arguments and invalidation conditions.
  - Optional: `--notes "..."`, `--status [active|validating|exited]`.
- `list`: Lists active theses.
- `track <code>`: Validates current market prices against invalidation triggers.
- `update <code>`: Modifies thesis notes or status.

#### Examples
```bash
# Capture thesis
python skills/stockaskill/scripts/run.py thesis capture 600519 --market A --notes "MA60 breakout" --json

# View active tracking list
python skills/stockaskill/scripts/run.py thesis list --market A --json

# Run invalidation check
python skills/stockaskill/scripts/run.py thesis track 600519 --market A --json
```

---

### 3.6 Macro Regime & Market Breadth (`regime` & `sentiment`)

Computes real-time market breadth (advance/decline ratio, limit up/down count) directly from DuckDB.

#### Examples
```bash
# Check market regime & risk budget
python skills/stockaskill/scripts/run.py regime --market A --json

# View sentiment aggregate
python skills/stockaskill/scripts/run.py sentiment --market A --json
```

---

## 4. Best Practices for AI Agent Tool Calling

When integrating `stockaskill` into an AI agent (e.g., Claude Code, OpenCode, Codex, OpenClaw, or custom ReAct agent loops):

1. **Always Use `--json`**:
   - Eliminates fragile text regex scraping;
   - Ensures stdout can be directly loaded via `json.loads(result.stdout)`.
2. **Prefer Compound Pipelines (`screen --to-portfolio`)**:
   - Reduces multi-step agent roundtrips from 3 turns down to 1 turn, cutting agent latency and saving tokens.
3. **Use Tiered Diagnosis (`diagnose --level quick`)**:
   - Use `quick` for wide scans and preliminary filtering; reserve `deep` only for shortlisted targets.
