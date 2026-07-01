# Findings & Decisions

## Requirements
- Assess whether "incremental full retrieval" for HK stocks, US stocks, ETFs, and funds is reasonable.
- Assess whether that scope matches the current purpose of the stock selection / investing / quant skill.
- Base the conclusion on the repository's current architecture and behavior.

## Research Findings
- The repository is local-first and task-scoped: cache is warmed on demand for analysis, scans, backtests, and fund screening.
- `get_kline()` performs incremental history fetch for a single symbol by reusing cached rows and requesting only a trailing window from the latest cached date.
- `refresh_snapshot()` is a market scan workflow that opportunistically backfills missing history and fundamentals while building a ranking snapshot; it is not a dedicated market-wide sync pipeline.
- A-share pool metadata has explicit backfill logic for listing date and related fields; HK and US do not have equivalent metadata enrichment.
- The "fund" implementation is ETF-oriented today: fund pool comes from `fund_etf_spot_em()`, `fund_type` is fixed to `ETF`, and `get_fund_nav()` reads exchange-traded history rather than broad mutual-fund NAV sources.
- The cache schema stores several core entities by `code` rather than `(market, code)`, which is a structural risk if the project expands toward fuller cross-market coverage.
- The skill description and implemented workflows emphasize stock analysis, market scanning, diagnosis, portfolio construction, and backtesting, all with local-first cache warming rather than background warehouse-style synchronization.
- Full incremental sync for HK, US, ETF, and especially broad funds would turn the project toward data-platform concerns: source reliability, pagination/crawling control, schema normalization, freshness SLAs, recovery jobs, and multi-market identity management.
- For an investing and quant skill, the highest-value data is usually the subset needed for current decisions: watchlists, candidate pools, benchmark indices, ETFs under consideration, and historical series required by active strategies.
- Broad mutual-fund support has a different product shape from stock/ETF support because it depends on NAV-oriented data and fund master metadata rather than exchange-traded quote history alone.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Judge the request on product fit first, then implementation fit | A feature can be technically possible yet still be the wrong scope for the product |
| Treat ETF and broad mutual-fund support as separate concerns | The current code already shows they have different source and data-model needs |
| Recommend against full-universe incremental sync as the default roadmap | It adds large ingestion and data-governance burden without matching the repository's current user-facing workflows |
| Recommend expanding selective incremental sync for user-scoped universes | This preserves the local-first, task-scoped design and directly serves scan/analyze/backtest workflows |

## Recommendation Summary
- Full incremental retrieval of all HK stocks, all US stocks, all ETFs, and all funds is not the most reasonable next step for this repository.
- It only partially aligns with the skill's purpose. It aligns at the margin for broader market coverage, but it does not align with the current product center of gravity, which is decision support and bounded quant workflows rather than operating a general-purpose market data platform.
- Expanding from A-share-centric support to better HK/US/ETF support is reasonable if the scope is bounded: user watchlists, scan candidate pools, selected benchmarks, and explicitly requested funds.
- Broad mutual-fund full sync should be treated as a separate product decision, not bundled into the same roadmap item as HK/US/ETF incremental sync.

## Recommended Scope Boundary
- Keep: incremental per-symbol history fetch, market-scan backfill, bounded warmup for backtests, ETF-specific history caching.
- Add next: stable HK/US symbol metadata enrichment, selective universe sync commands, per-market sync state, `(market, code)` cache identity, better ETF/fund separation.
- Defer: full-universe mutual-fund ingestion, warehouse-style daily sync for all markets, background freshness SLAs across all supported assets.

## Optimization Direction
- The right optimization target is not "more markets first"; it is "more predictable readiness, better cache correctness, and clearer task-scoped orchestration."
- The biggest near-term gains come from improving data identity, freshness accounting, selective sync ergonomics, and observability of readiness gaps.
- The architecture should evolve toward explicit sync scopes: symbol scope, candidate scope, portfolio scope, benchmark scope, ETF scope.
- Cross-market expansion should be correctness-first: fix cache keys and sync state before adding more source breadth.
- The current `FUND` path remains ETF-oriented in practice, so the least risky next step is to expose ETF-specific sync/readiness/status explicitly instead of pretending broad fund support already exists.

## Proposed Optimization Plan

### 1. Correctness Foundation
- Introduce market-aware cache identity for core entities:
  - `stock_pool`: primary identity should be `(market, code)`.
  - `daily_price`: primary identity should include `market`.
  - `factor_snapshot`: primary identity should include `market`.
- Add explicit per-scope sync metadata:
  - last history date
  - last fundamentals date
  - last pool refresh time
  - last sync status / error
- Split ETF and broad fund concepts in the data model instead of treating them as one feature.

### 2. Task-Scoped Sync API
- Keep current implicit warmup paths, but add explicit sync entry points for predictable usage:
  - `sync symbol <code> --market <M>`
  - `sync watchlist --market <M>`
  - `sync scan-universe <M> --top-candidates N`
  - `sync portfolio --codes ...`
  - `sync etf --codes ...`
- Make each sync command bounded and report:
  - requested symbols
  - cache hits
  - fetched history/fundamentals
  - still-missing items
  - last covered date

### 3. Metadata Enrichment
- Extend non-A-share metadata support:
  - HK: listing date, market cap if available, sector/industry where source quality is acceptable
  - US: normalized ticker identity, sector/industry, market cap, delisting/inactive handling
- Treat metadata completeness as best-effort but visible, not silent.

### 4. Readiness and Observability
- Standardize readiness checks around reusable scopes:
  - analysis-ready
  - scan-ready
  - backtest-ready
  - portfolio-ready
  - fund-ready
- Add concise readiness summaries and failure reasons in CLI outputs and reports.
- Persist sync errors and expose them in a diagnostics command rather than hiding them behind silent fallbacks.

### 5. Asset-Scope Strategy
- A-shares: remain the deepest-supported market.
- HK / US: support bounded watchlist and candidate-based incremental sync first.
- ETF: treat as a first-class supported asset because it fits portfolio and allocation workflows.
- Broad mutual funds: keep out of the core roadmap until a separate NAV-centric product need is confirmed.

## Suggested Milestones
- Milestone 1: cache identity and schema hardening
- Milestone 2: explicit sync commands and per-scope sync metadata
- Milestone 3: HK/US metadata enrichment and better readiness reporting
- Milestone 4: ETF-first portfolio/fund workflow cleanup
- Milestone 5: optional deferred decision on broad mutual-fund support

## Repository Impact Map
- `stockaskill/scripts/cache.py`
  - schema migration
  - new sync-state storage
  - market-aware keys
- `stockaskill/scripts/data_engine.py`
  - explicit sync orchestration
  - source selection normalization
  - ETF/fund separation
- `stockaskill/scripts/data_readiness.py`
  - scope-oriented readiness contracts
  - reusable readiness summaries
- `stockaskill/scripts/run.py`
  - new `sync` commands
  - better user-visible readiness output
- `stockaskill/scripts/advisor/scanner.py`
  - consume explicit candidate sync status rather than mixing sync and ranking logic as tightly

## Executable Development Plan

### MVP Batch 1: Cache Identity and Sync State

#### Goal
Fix the most important correctness risks without changing product scope.

#### Changes
- In `cache.py`:
  - introduce market-aware tables or v2 tables for:
    - `stock_pool`
    - `daily_price`
    - `factor_snapshot`
  - add a new `sync_state` table with fields similar to:
    - `scope_type` (`symbol`, `pool`, `watchlist`, `portfolio`, `etf`)
    - `scope_key`
    - `market`
    - `code`
    - `data_kind` (`history`, `fundamentals`, `pool`, `nav`)
    - `last_success_at`
    - `last_covered_date`
    - `last_error`
    - `status`
- Keep migration additive first if possible, to reduce break risk:
  - read old tables
  - write new tables
  - switch reads once coverage is verified

#### Why first
- It unlocks safe HK/US/ETF expansion.
- It reduces hidden cache corruption risk from cross-market identity ambiguity.

### MVP Batch 2: Explicit Sync Service Layer

#### Goal
Turn implicit warmup behavior into explicit reusable sync primitives.

#### Changes
- In `data_engine.py`:
  - add service-style functions:
    - `sync_symbol_data(...)`
    - `sync_symbols_data(...)`
    - `sync_market_pool(...)`
    - `sync_etf_data(...)`
  - each function should return a structured result:
    - requested count
    - cache hit count
    - fetched history count
    - fetched fundamentals count
    - missing count
    - covered-through date
    - errors
- Keep `get_kline()` and `get_fundamentals()` as read-oriented APIs.
- Move orchestration logic out of scan-specific paths where practical.

#### Why second
- This is the reuse layer needed by CLI commands, readiness checks, scanner warmups, and future diagnostics.

### MVP Batch 3: Readiness Contracts

#### Goal
Make "data ready" a first-class concept rather than ad hoc checks.

#### Changes
- In `data_readiness.py`:
  - standardize return schemas for:
    - `ensure_symbol_analysis_ready`
    - `ensure_market_scan_ready`
    - `ensure_backtest_ready`
    - `ensure_fund_screen_ready`
  - add explicit readiness summaries:
    - `ready`
    - `missing_history_symbols`
    - `missing_fundamental_symbols`
    - `stale_symbols`
    - `covered_through`
- Add reusable scope-level helpers:
  - `ensure_watchlist_ready`
  - `ensure_portfolio_ready`
  - `ensure_etf_ready`

#### Why third
- It improves UX immediately and simplifies reasoning in CLI/reporting layers.

### MVP Batch 4: CLI and Diagnostics

#### Goal
Expose bounded sync intentionally, not indirectly.

#### Changes
- In `run.py` add commands like:
  - `sync symbol 600519 --market A`
  - `sync watchlist --market US`
  - `sync scan-universe HK --limit 200`
  - `sync portfolio --codes 0700,9988 --market HK`
  - `sync etf --codes 510300,159915`
- Add a diagnostics command:
  - `status data --market A`
  - or `diagnose-cache`
- Output should show:
  - cache reuse
  - fetched rows
  - missing symbols
  - freshness / last covered date

#### Why fourth
- The internal architecture becomes user-visible and testable.

### MVP Batch 5: HK / US / ETF Tightening

#### Goal
Improve bounded cross-market support after the base is safe.

#### Changes
- In `data_engine.py`:
  - improve HK/US metadata enrichment
  - normalize inactive/delisted handling where possible
  - separate ETF from general fund fetch paths more explicitly
- In `scanner.py`:
  - consume explicit sync results
  - reduce hidden remote fetches during ranking

#### Why fifth
- This is where feature breadth expands, so it should come after identity and orchestration are sound.

## First PR Scope Recommendation
- Restrict the first implementation batch to:
  - `cache.py`
  - `data_engine.py`
  - `data_readiness.py`
  - minimal `run.py` additions for one `sync symbol` command
- Do not include:
  - full HK/US metadata overhaul
  - broad fund support
  - scanner redesign
- This keeps the first change set reviewable and reversible.

## Suggested Function-Level Work Breakdown

### `cache.py`
- Add new schema definitions and migration helpers.

## Batch 4 Findings
- `scan FUND` was still user-visible as generic "fund" behavior even though it only sourced exchange-traded ETF instruments.
- Adding an explicit ETF sync scope is a better fit than expanding general-fund semantics because it reuses existing ETF-oriented sources and keeps readiness/status reporting consistent with the earlier sync-state work.
- The cleanest compatibility path is to keep `market="FUND"` internally for now while adding ETF-specific CLI/readiness/sync entry points on top.

## Batch 5 Findings
- The next leverage point after ETF scope exposure is semantic cleanup, not a large schema rename: adding `get_etf_pool()` and market helpers reduces continued spread of raw `FUND` conditionals.
- HK/US pool fetches can safely extract more useful metadata now using best-effort field normalization across heterogeneous upstream columns rather than waiting for a full dedicated metadata pipeline.
- Marking obviously inactive HK/US names as `is_active=0` and skipping them in scanner candidate preparation is a low-risk way to reduce bad candidates before deeper cross-market support work.

## Batch 6 Findings
- The next missing piece for bounded HK/US support was not more fields but visibility into field quality. Adding `metadata_source`, `metadata_status`, and `metadata_completeness` to cached pool rows makes upstream quality visible without changing product scope.
- Additive metadata columns on `stock_pool_v2` are sufficient for this stage; a heavier schema split is not yet necessary.
- Scanner/operator visibility improves when candidate metadata summaries include complete/partial/inactive counts rather than only A-share list-date backfill counters.

## Batch 7 Findings
- Metadata quality is now useful enough to feed lightly into scan decisions: a small HK/US-only ranking penalty is a safer first step than turning low completeness into a hard exclusion.
- `status data` becomes more actionable once it reports scope-level metadata health, not just sync freshness/error counts.
- Snapshot/realtime scan output can carry metadata quality without another schema migration by exposing it in result payloads and CLI output.

## Documentation Findings
- `SKILL.md` needed explicit clarification that the skill is local-first and bounded-sync oriented, not a full-market sync platform.
- `README.md` needed command-level documentation for `sync` / `status data` plus the new metadata-quality concepts, otherwise the implemented behavior remained discoverable only from code.
- `AGENTS.md` benefits from explicit product-scope guardrails so future agents do not regress toward full-universe ingestion proposals by default.

## Skill Definition Findings
- The skill definition itself still over-triggered on broad fund language even after product docs were updated; the trigger surface needed to be narrowed to ETF-first requests explicitly.
- Reducing `SKILL.md` frontmatter to the minimal `name` + `description` form lowers compatibility risk across skill hosts and matches the skill-creator guidance better.
- Reference routing needed task-based guidance, not a flat file list, to make progressive disclosure actually work in practice.
- Add methods for:
  - upserting market-aware pool rows
  - upserting market-aware price rows
  - upserting market-aware factor snapshots
  - reading/writing sync state

### `data_engine.py`
- Add sync result models or dict contracts.
- Refactor shared fetch/update logic into reusable internal helpers.
- Keep the external read path stable where possible.

### `data_readiness.py`
- Replace loosely structured readiness returns with standardized payloads.
- Route existing `ensure_*_ready` functions through the new sync layer.

### `run.py`
- Add `sync` subcommands.
- Print concise sync summaries.
- Keep existing commands working.

## Migration and Risk Notes
- Highest risk: schema changes around cache identity.
- Mitigation:
  - additive migration first
  - dual-read or compatibility read path during transition
  - focused regression tests for A-share existing workflows
- Second risk: hidden coupling between scanner warmup and data fetch paths.
- Mitigation:
  - preserve current behavior first
  - introduce explicit sync layer under existing calls before removing old logic

## Verification Plan
- Unit tests:
  - market-aware cache read/write
  - sync state persistence
  - readiness summary correctness
  - CLI sync output for symbol scope
- Regression tests:
  - existing `analyze`
  - existing `scan A`
  - existing `scan FUND`
  - existing `backtest` warmup behavior
- Manual smoke checks:
  - cold cache single symbol sync
  - mixed-market watchlist sync
  - ETF sync and readiness report

## Implemented Batch 1
- Added market-aware additive cache tables:
  - `stock_pool_v2`
  - `daily_price_v2`
  - `factor_snapshot_v2`
- Added `sync_state` table for bounded sync bookkeeping.
- Updated cache upsert/read paths so market-aware reads prefer v2 tables and retain fallback compatibility with legacy tables.
- Added symbol-scoped sync orchestration in `data_engine.py`:
  - `sync_symbol_data()`
  - `sync_symbols_data()`
- Updated readiness helpers to use the new sync layer.
- Added minimal CLI support for:
  - `python stockaskill/scripts/run.py sync symbol <code> --market <M>`

## Batch 1 Validation
- Targeted tests passed:
  - `tests/test_cache.py`
  - `tests/test_data_readiness.py`
  - `tests/test_run.py`
- Result:
  - `41 passed`
  - `ruff check` passed for touched files

## Next Recommended Batch
- Add watchlist / portfolio / scan-universe sync scopes.
- Expand readiness summaries and diagnostics output.
- Then tighten scanner integration so ranking consumes explicit sync results more consistently.

## Implemented Batch 2
- Added bounded sync scopes in `data_engine.py`:
  - `sync_watchlist_data()`
  - `sync_portfolio_data()`
  - `sync_scan_universe_data()`
- Added scope-level summary sync-state rows so non-symbol scopes can be inspected through diagnostics.
- Added readiness wrappers in `data_readiness.py`:
  - `ensure_watchlist_ready()`
  - `ensure_portfolio_ready()`
  - `ensure_scan_universe_ready()`
- Expanded CLI in `run.py`:
  - `sync watchlist`
  - `sync portfolio`
  - `sync scan-universe`
  - `status data symbol`
  - `status data watchlist`
  - `status data portfolio`
  - `status data scan-universe`

## Batch 2 Validation
- Targeted tests passed:
  - `tests/test_cache.py`
  - `tests/test_data_readiness.py`
  - `tests/test_run.py`
- Result:
  - `45 passed`
  - `ruff check` passed for touched files

## Updated Next Recommended Batch
- Tighten scanner integration so `scan` and `refresh-scan` reuse explicit scope sync summaries more directly.
- Add richer `status data` output:
  - stale vs fresh
  - aggregated error counts
  - top missing symbols
- Add ETF-specific scope sync and ETF/fund reporting cleanup.

## Implemented Batch 3
- Updated `advisor/scanner.py` so realtime scan paths print readiness/sync summaries from explicit scope warmup results before scoring.
- Enriched `status data` in `run.py`:
  - aggregate `fresh / stale / missing`
  - error counts
  - symbols with issues
  - top problem symbols
- Added symbol-row aggregation for:
  - watchlist
  - portfolio
  - scan-universe
- Adjusted scan-universe scope identity to include the limit in scope tracking.

## Batch 3 Validation
- Targeted tests passed:
  - `tests/test_cache.py`
  - `tests/test_data_readiness.py`
  - `tests/test_run.py`
  - `tests/test_advisor.py`
- Result:
  - `65 passed`
  - `ruff check` passed for touched files

## New Next Recommended Batch
- ETF-specific sync scope and ETF/fund workflow cleanup.
- Broader readiness standardization:
  - explicit stale symbol lists
  - richer `status data` summaries in saved reports
- HK/US metadata enrichment after observability is strong enough to debug source quality issues.

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| No planning artifacts existed yet | Created root-level planning files as required by the skill |

## Resources
- `/home/ji/stockaskill/stockaskill/SKILL.md`
- `/home/ji/stockaskill/stockaskill/scripts/data_engine.py`
- `/home/ji/stockaskill/stockaskill/scripts/advisor/scanner.py`
- `/home/ji/stockaskill/stockaskill/scripts/cache.py`
- `/home/ji/stockaskill/stockaskill/scripts/data_readiness.py`

## Visual/Browser Findings
- None. This assessment used local repository inspection only.
