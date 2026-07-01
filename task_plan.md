# Task Plan: Assess Full Incremental Multi-Market Data Sync Scope

## Goal
Determine whether building incremental full-universe sync for HK stocks, US stocks, ETFs, and funds is reasonable for this repository, whether it aligns with the purpose of the current stock-investing and quant-trading skill, and define an optimization roadmap for the confirmed local-first, task-scoped data engine direction.

## Current Phase
Phase 19

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints and requirements
- [x] Document findings in findings.md
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Define assessment criteria
- [x] Separate product-fit questions from implementation questions
- [x] Document decisions with rationale
- **Status:** complete

### Phase 3: Assessment
- [x] Evaluate current market coverage and sync behavior
- [x] Evaluate operational cost, data quality, and maintenance burden
- [x] Evaluate alignment with the skill's target workflows
- **Status:** complete

### Phase 4: Recommendation
- [x] Produce a recommendation with alternatives
- [x] Identify what should be supported now vs deferred
- [x] State risks and assumptions clearly
- **Status:** complete

### Phase 5: Delivery
- [x] Review planning files
- [x] Deliver concise conclusion to user
- **Status:** complete

### Phase 6: Optimization Framing
- [x] Confirm target product positioning
- [x] Define optimization principles for local-first task-scoped data workflows
- [x] Separate immediate fixes from strategic enhancements
- **Status:** complete

### Phase 7: Optimization Roadmap
- [x] Define architecture improvements
- [x] Define staged implementation milestones
- [x] Map milestones to repository modules
- **Status:** complete

### Phase 8: Roadmap Delivery
- [x] Deliver optimization proposal to user
- [x] Call out priorities, risks, and sequencing
- **Status:** complete

### Phase 9: Executable Development Plan
- [x] Translate roadmap into concrete code changes
- [x] Define first-batch schema and API changes
- [x] Define implementation and verification order
- **Status:** complete

### Phase 10: Plan Delivery
- [x] Deliver executable development plan to user
- [x] Highlight MVP scope vs later milestones
- **Status:** complete

### Phase 11: MVP Batch 1 Implementation
- [x] Add market-aware cache v2 tables and sync_state
- [x] Add bounded symbol sync service
- [x] Add minimal sync CLI entry point
- [x] Update targeted tests and verification
- **Status:** complete

### Phase 12: MVP Batch 2 Implementation
- [x] Add watchlist / portfolio / scan-universe sync scopes
- [x] Add minimal `status data` diagnostics
- [x] Extend targeted tests and verification
- **Status:** complete

### Phase 13: MVP Batch 3 Implementation
- [x] Make scanner consume readiness/sync summary more directly
- [x] Enrich `status data` with aggregate freshness/error reporting
- [x] Extend targeted tests and verification
- **Status:** complete

### Phase 14: MVP Batch 4 Implementation
- [x] Add ETF-specific sync/readiness scope
- [x] Tighten FUND workflow wording toward ETF-first semantics
- [x] Extend targeted tests and verification
- **Status:** complete

### Phase 15: MVP Batch 5 Implementation
- [x] Add clearer ETF asset semantics in the data layer
- [x] Improve HK/US pool metadata extraction and inactive-symbol handling
- [x] Extend targeted tests and verification
- **Status:** complete

### Phase 16: MVP Batch 6 Implementation
- [x] Add visible HK/US metadata source/completeness/status fields
- [x] Surface metadata completeness in candidate readiness summaries
- [x] Extend targeted tests and verification
- **Status:** complete

### Phase 17: MVP Batch 7 Implementation
- [x] Make scan/realtime ranking consume metadata quality signals
- [x] Add market-level metadata health summaries to `status data`
- [x] Extend targeted tests and verification
- **Status:** complete

### Phase 18: Documentation Alignment
- [x] Update `SKILL.md` to reflect local-first bounded sync and ETF-first scope
- [x] Update `README.md` with new sync/status/metadata-quality behavior
- [x] Update `AGENTS.md` with product-scope guardrails for future agents
- **Status:** complete

### Phase 19: Skill Definition Tightening
- [x] Narrow trigger wording from broad fund claims to ETF-first semantics
- [x] Reduce `SKILL.md` frontmatter to `name` + `description`
- [x] Improve progressive-disclosure navigation and examples
- [x] Align `agents/openai.yaml` with the tightened scope
- **Status:** complete

## Key Questions
1. Does this repository currently behave like a task-scoped analysis engine or a full market data platform?
2. Would full incremental sync of HK, US, ETF, and funds materially improve the core workflows already implemented?
3. Which asset classes are essential to the stated product purpose, and which add disproportionate complexity?
4. Given the confirmed local-first positioning, which optimizations produce the highest leverage without turning the project into a data platform?
5. What is the smallest implementation batch that materially improves correctness and user experience without destabilizing current workflows?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use file-based planning for this request | The user explicitly invoked the planning-with-files skill and the task is multi-step research/assessment rather than a one-line answer |
| Do not recommend full-universe sync as the primary product direction | The repository is built as a task-scoped analysis/cache engine, not a data-platform foundation |
| Recommend bounded incremental support for ETFs and selected cross-market watchlists instead | That aligns with actual scan, diagnose, portfolio, and backtest workflows while containing source and maintenance complexity |
| Optimize around task-scoped readiness and cache identity first | These changes improve correctness and user experience without expanding the product into a warehouse or crawler platform |
| Use staged milestones instead of a single large refactor | The project already works for core A-share workflows, so improvements should preserve momentum and reduce regression risk |
| Start with an MVP batch that does not require broad feature deletion | The repository should improve incrementally around existing workflows rather than pausing progress for a large rewrite |
| Use additive v2 cache tables in the first implementation batch | This reduces migration risk and allows compatibility fallback while introducing market-aware identity |
| Add scope sync before deeper scanner refactors | Explicit sync scopes make later scanner and diagnostics cleanup much safer and easier to reason about |
| Improve observability before broadening market coverage further | Better freshness/error visibility reduces blind spots and makes later market expansion safer |
| Treat current FUND workflows as ETF-first rather than broad mutual-fund support | The upstream data sources and cached behavior are exchange-traded ETF oriented, so explicit ETF scope is less misleading and easier to extend safely |
| Use ETF aliasing and inactive-pool filtering before broader HK/US expansion | This improves semantics and reduces noisy candidate universes without forcing a large schema rewrite |
| Add metadata visibility before deeper HK/US enrichment | Source/status/completeness visibility helps reason about cross-market quality without overcommitting to brittle upstream assumptions |
| Use metadata quality as a light ranking/status signal before hard filters | Soft consumption of metadata quality improves decision support without aggressively discarding bounded HK/US universes |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| No existing planning files in repo root | 1 | Create fresh task_plan.md, findings.md, and progress.md for this assessment |

## Notes
- Keep product-scope reasoning separate from code-level feasibility.
- Focus on whether the feature matches the skill's purpose, not just whether it can be engineered.
