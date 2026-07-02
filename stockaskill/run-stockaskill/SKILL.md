---
name: run-stockaskill
description: >-
  Build, install deps, and run the stockaskill CLI tool for stock analysis,
  market scans, backtests, and portfolio construction. Also runs the test suite.
---

# Run stockaskill

Python CLI — multi-market stock analysis (A-share, HK, US, ETF) via AKShare.
Local-first: SQLite cache at `.cache/quant_cache.db`, on-demand API fills.

All paths relative to project root.

## Prerequisites

Python >= 3.10. Create venv and install:

    uv venv .venv
    source .venv/Scripts/activate
    uv pip install akshare efinance baostock pandas numpy scipy pytest

## Run (agent path)

### Smoke test — verify CLI loads

    python stockaskill/scripts/run.py --help

### Core commands

    # Single stock analysis
    python stockaskill/scripts/run.py analyze 600519 --market A

    # Deep diagnosis with BUY/SELL/HOLD signal
    python stockaskill/scripts/run.py diagnose 600519 --market A

    # Long-form diagnosis report
    python stockaskill/scripts/run.py deep-diagnose 600519 --market A --format both

    # Market scan (auto mode: prefers snapshot, falls back to bounded realtime)
    python stockaskill/scripts/run.py scan A --top 20

    # Alpha momentum ranking
    python stockaskill/scripts/run.py alpha A --top 10

    # Portfolio construction
    python stockaskill/scripts/run.py portfolio --codes 600519,000858 --capital 1000000 --market A

    # Backtest
    python stockaskill/scripts/run.py backtest

    # Fetch/refresh pool data
    python stockaskill/scripts/run.py fetch pool

    # Sync bounded data for scope
    python stockaskill/scripts/run.py sync symbol 600519 --market A

    # Cache stats
    python stockaskill/scripts/run.py cache stats

## Direct invocation (Python API)

For PRs that touch internals (import + call, no full CLI):

    python -c "
    import sys
    sys.path.insert(0, 'stockaskill/scripts')
    from data_engine import get_stock_pool
    pool = get_stock_pool('A')
    print(f'A-share pool: {len(pool)} stocks')
    "

    python -c "
    import sys
    sys.path.insert(0, 'stockaskill/scripts')
    from advisor.diagnosis import StockDiagnosis
    report = StockDiagnosis('600519', 'A').full_report()
    print(report['final_decision'])
    "

## Test

    pytest tests/ -v

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `database is locked` on UNC/WSL paths | SQLite file locking over network paths | Delete `.cache/quant_cache.db` and retry; or run from a local Windows path |
| `Daily API limit reached` | Local API budget hit | Commands silently fall back to cached data — results may be stale but still usable |
| `can't open file 'stockaskill/scripts/run.py'` | Wrong working directory | Run from project root (where `stockaskill/` directory lives) |
| `ModuleNotFoundError: No module named 'akshare'` | Dependencies not installed | Run `uv pip install akshare efinance baostock` |
| Scan returns 0 results | Cold cache | Run `fetch pool` once, then retry |
