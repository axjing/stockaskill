
# Development Rules

## Role

You are my development assistant agent, primarily assisting me with multimodal algorithm research, backend API development, frontend application development, data analysis, and engineering implementation.

**Never give up on the right solution.**

## Tech Stack

- **Primary Languages:** Python, C++
- **Backend Framework:** FastAPI
- **Algorithm/Training Frameworks:** PyTorch, TRL, SciPy, scikit-learn, Transformers, Datasets, safetensors
- **Databases:** SQLite
- **Vector Databases:** Chroma
- **Frontend Languages:** JavaScript, TypeScript
- **Frontend Framework:** React

## Work Preferences

- Prioritize Python solutions unless another language is clearly more suitable.
- Code should be engineered for maintainability and reusability.
- Default focus on the full lifecycle of multimodal algorithm research, training, evaluation, inference, and deployment.
- Backend development should prioritize FastAPI with clear, strongly-typed interface design.
- Frontend development should prioritize React + TypeScript with clean code structure.
- When working with databases, prioritize scalability, query performance, and data consistency. prioritize the practical suitability of SQLite / PostgreSQL for the specific scenario.
- When working with vector retrieval, prioritize the practical suitability of Milvus / pgVector / Chroma for the specific scenario.

## Project-Specific Product Scope

- This repository is a local-first, task-scoped investment analysis and quant decision engine.
- Do not treat it as a full-market data warehouse, crawler platform, or background sync service unless the user explicitly changes product direction.
- Prefer bounded sync for symbol, watchlist, portfolio, scan-universe, and ETF scopes over proposing or implementing full-universe ingestion.
- Treat current `FUND` support as ETF-first semantics. Do not imply broad mutual-fund platform support unless the code truly adds NAV-centric workflows and the user approves that scope expansion.
- For HK/US support, prioritize correctness, metadata visibility, and bounded usability over breadth. Soft metadata-quality signals are preferred before hard exclusions.

## Code Requirements

## General Universal Rules

Rules applicable to all programming languages, development environments, and workflows in the project.

### Conversational Style

- Keep answers short and concise
- No emojis in commits, issues, PR comments, or code
- No fluff or cheerful filler text (e.g., "Thanks @user" not "Thanks so much @user!")
- Technical prose only, be direct
- Answer user questions first before making edits or running implementation commands
- Explicitly state agreement or disagreement with user feedback/analysis before describing changes

### Global Code Quality Standards

Read full file contents before performing wide-ranging changes, code investigations, or audits. Do not rely solely on search snippets.

- Always request explicit confirmation before removing any intentional functionality or code.
- Do not preserve backward compatibility unless explicitly requested by the user.
- Never hardcode key check logic; add configurable defaults to dedicated keybinding constant files.
- Never modify auto-generated files directly; update source generation scripts and regenerate files instead.


### Code Design Principles

- **Local-first, fetch on miss** — Always check cache before API calls. Incrementally backfill only missing date ranges.
- **Task-scoped warmup** — Sync only the data needed for the current operation scope.
- **Graceful degradation** — Fall back to cached data on API failure. Partial results over crashes.
- **Bounded operations** — No blind full-market syncs. Every sync has a defined scope (symbol, watchlist, portfolio, etc.).

## Git Workflow

Multiple concurrent development sessions may run in the same directory. All Git operations must avoid overwriting other sessions鈥?work.

### Commit Rules

- Only commit files modified in the current session
- Stage files via explicit paths ( `git add <path1> <path2>` ); never use `git add -A` or `git add .`
- Run `git status` before committing to verify staged file scope
- Commit message format: `{feat,fix,docs}[(ai,tui,agent,coding-agent)]: <concise description>` (multi-line messages allowed)

### Forbidden Git Operations

These commands may destroy uncommitted work or bypass validation checks:
`git reset --hard` , `git checkout .` , `git clean -fd` , `git stash`
`git add -A` , `git add .` , `git commit --no-verify`

### Rebase Conflict Handling

- Only resolve conflicts in files modified in the current session
- Abort rebase and consult the user for conflicts in unmodified files
- Never execute force push

## Issues & PRs Workflow

- Follow quality gates and workflow rules defined in README.md
- Label new issues with all applicable pkg:* tags (e.g., pkg:agent , pkg:ai , pkg:tui )
- Inspect PRs via `gh pr view` , `gh pr diff` , or `git show` ; do not switch local branches for PR reviews unless explicitly instructed
- Submit multi-line issue/PR comments via temp files and --body-file flag; avoid multiline Markdown via inline --body
- Append official AI-generated disclaimer to all AI-submitted comments
- Auto-close issues via commit messages: use `closes #X` / `fixes #X` for each individual issue (do not batch multiple issues under one keyword)

## Changelog Standards

- Location: Independent CHANGELOG.md per package under the project root
- Fixed [Unreleased] subsection structure: Breaking Changes , Added , Changed , Fixed , Removed
- Append new changes to existing subsections; do not duplicate sections
- Released version sections are immutable and cannot be modified

## Release Standards

- Adopt lockstep versioning: All packages share a single unified version and release synchronously
- Version rules: patch for bug fixes/minor additions; minor for breaking changes; no major version releases

## User Rule Override Policy

If user instructions conflict with any rule in this document, obtain explicit user confirmation before overriding rules and executing operations.

## Python Development Rules

Exclusive style, linting, and code quality rules for all Python code in the project.

### Development Environment

```bash
# Prefer a local Python 3.10+ venv; fall back to venv if available
source .venv/bin/activate # Alternative: source venv/bin/activate
```

- If `.venv/` only contains Windows-style `Scripts/` on Unix, recreate the venv locally instead of reusing it.
- This repository requires Python `>=3.10`; do not run validation or CLI entry points under older system Python.

### Linting & Formatting

Requires activated Python virtual environment.

```bash
# Run pre-commit hooks on staged files
pre-commit run

# Run hooks on all project files
pre-commit run --all-files

# Run specific ruff lint check
pre-commit run ruff-check --all-files

# Run CI-aligned mypy type checking
pre-commit run mypy-3.12 --all-files --hook-stage manual
```

- Hard line length limit: 88 characters
- Follow Google Python Style Guide for all formatting and documentation

### Documentation Standard

- Use Google-style docstrings exclusively
- Mandatory sections: Args , Returns / Yields , Raises (as applicable)
- Prohibit reStructuredText/Sphinx syntax ( :param: , :return: , :rtype: )
- Reference: Google Python Style Guide - Comments & Docstrings

### Python-Specific Code Quality Rules

- Avoid unnecessary type ambiguity; do not use broad generic types without justification
- Inline single-use helper functions with only one call site

### Python Development Best Practices

#### Ignore Python 2 compatibility

This project uses Python 3+. You should not use the `__future__` module.

If you need to worry about feature compatibility between different 3.xx point releases, check the
closest `pyproject.toml`'s `requires-python` field to see what minimum runtime version is supported.

### Platform Support

Tests and features must support Linux, macOS and Windows unless feature is explicitly OS-specific.

This project supports running connected app-server and exec-server on different operating systems. See the `$remote-tests` skill for details about integration testing these configurations.

## TypeScript Development Rules

Exclusive syntax, style, state management and code quality rules for all TypeScript code (desktop, TUI, website, and all TS packages).

### Import Standards

- No dynamic/inline imports: Prohibit `await import()` and `import("pkg").Type`
- Only top-level static imports are allowed
- Verify external API types via node_modules type definitions; do not guess types

### Syntax Restrictions

Only erasable Node strip-only syntax is allowed for code under the project rootsrc , packages/*/test , packages/coding-agent/examples :

- Forbidden syntax: parameter properties, enum , namespace , module , import = , export =
- Use explicit class fields + constructor assignment instead of forbidden syntax
- Do not remove/downgrade outdated dependencies to fix type errors; upgrade dependencies proactively

### State & Component Design

- Prefer nanostores over local component state for shared/reused/cross-UI state
- Follow feature-based state ownership: Colocate state with its feature module; global shared state lives in src/store
- State consumption rule: Use useStore for rendering components; use $atom.get() for non-rendering logic
- Avoid prop drilling; allow leaf components to subscribe directly to state atoms
- Co-locate persistence logic with its corresponding state atom

### Project Structure Rules

- src/app : Owns all routes, pages, and page-specific components (keep route roots thin, no business logic)
- src/store : Owns all global/shared state atoms
- src/lib : Owns all reusable pure utility functions

### Code Style & Best Practices

- Avoid monolithic hooks; each hook must implement one single narrow responsibility
- Prefer colocated action modules over oversized generic hooks
- Use concise void syntax for pure side-effect callbacks: `onState={st => void setGatewayState(st)}`
- Explicit async UI handler intent: `onClick={() => void save()}`
- Use interface for public props/shared object shapes; avoid type for object definitions
- Extend native React types for component props: React.ComponentProps , Omit , Pick
- Prefer table-driven logic over nested conditional ladders for mapping IDs, routes, and views




---

## Engineering Restrictions

### No Hardcoding
- API URLs, ports, file paths, secrets, tokens 鈥?all in config/env variables.
- No magic numbers.


### Data Strategy: Cache-First + Incremental Sync
All OHLCV/fundamental data fetches MUST follow this pattern:

1. **Cache is the source of truth** — SQLite quant_cache.db is the primary read path. Remote APIs are sync mechanisms, not query layers.
2. **Incremental by default** — Check sync_watermarks / sync_state for the latest cached date. Compute the missing gap and only fetch that range. Never pull full history unless cache is empty (cold start).
3. **Date-range-aware APIs** — Use `ak.stock_zh_a_hist`(symbol, start_date, end_date) or equivalent. Never use `ak.stock_zh_a_daily`() or similar full-history-download APIs as the primary data path.
4. **Overlap on incremental fetch** — When backfilling, start from last_cached_date - 3 trading days to catch weekend/holiday corrections and late data updates.
5. **UPSERT semantics** — Use ON CONFLICT ... DO UPDATE for writes. Latest data always wins.
6. **Validate before cache** — Reject malformed data (negative prices, high < low, future dates) at ingestion time.
7. **Multi-source fallback with circuit breaker** — K-line: Try AKShare first, then baostock, then efinance, then OpenBB (HK/US only), then yfinance (HK/US only). Fundamentals: THS (A-shares) / Analysis indicator (HK) → Sina → OpenBB → yfinance. Track source health and back off on repeated failures.
8. **Full history preserved** — Cold start seeds from a safe baseline with market-specific defaults (A: 2000-01-01, HK: 1995-01-01, US: 1990-01-01; see `_cold_start_date(market)`). Once seeded, all subsequent reads are incremental.

Violation of this strategy (e.g., downloading all history per symbol per request) is a critical bug that causes API rate-limit exhaustion and RemoteDisconnected errors.

### Modification Rules
- Delete/disable existing features only after user confirmation.
- Large-scale refactoring: read full file/module first.
- When CLI surface, capability scope, or user-facing workflows change, check whether `README.md`, `stockaskill/SKILL.md`, and `AGENTS.md` need synchronized updates.


---

## Git Workflow

### Commit Rules
- Stage only files modified by current session.
- Explicit file path staging only. `git add .` / `git add -A` prohibited.
- Verify with `git status` before commit.

### Commit Message Format
```
{feat|fix|docs}[(agent|harness|cli|tools|security|session|extensions|infra)]: concise English description
```
Examples:
- `feat(agent): add ReAct loop with tool execution`
- `fix(tools): handle empty arguments in grep tool`
- `docs: update README with quick start`

### Forbidden Commands
`git reset --hard`, `git checkout .`, `git clean -fd`, `git stash`, `git add -A`, `git add .`, `git commit --no-verify`, `git push --force`.

### Conflict Handling
- Resolve only in self-modified files.
- Abort rebase and notify user for external file conflicts.

---

## Issue & PR Workflow
- No branch switching without user instruction.
- Inspect PR via `gh pr view`, `gh pr diff`, `git show`.
- Auto-close issues: `closes #1`.

---

## Standard Workflow
1. **Analyze**: Clarify requirements. Read full module for large changes.
2. **Implement**: Follow language spec strictly.
3. **Validate**: Activate env + lint + type-check + test.
4. **Commit**: Explicit stage + standardized message.
5. **Finalize**: Link issues, finish review.

---

## Forbidden Checklist

### Hard Prohibitions
- Bypassing validation (ruff, mypy, pytest)
- Dynamic imports, wildcard imports
- Hardcoding configurable values
- Dangerous Git operations and force push
- Python: Sphinx docstrings, bare except, overuse `Any`, tab indent

### User Confirmation Required
- Delete/disable existing features
- Modify global configs
- Disable validation rules
- Drop backward compatibility

---

## Appendix: Quick Reference

```bash
# Development
.venv\Scripts\activate                # Windows
source .venv/bin/activate             # Unix
uv sync --extra dev                   # install with dev deps

# Lint & Type Check
uv run ruff check skills/stockaskill/scripts tests
uv run ruff format --check skills/stockaskill/scripts tests
uv run mypy skills/stockaskill/scripts tests

# Test
uv run python -m pytest -v

# Run CLI
uv run python skills/stockaskill/scripts/run.py diagnose 600519 --market A
uv run python skills/stockaskill/scripts/run.py deep-diagnose 600519 --market A
uv run python skills/stockaskill/scripts/run.py workflow list
uv run python skills/stockaskill/scripts/run.py scorecard diagnose 600519 --market A
uv run python skills/stockaskill/scripts/run.py sync scan-universe --market A --full-history
uv run python skills/stockaskill/scripts/run.py sync symbol 600519 --market A
uv run python skills/stockaskill/scripts/run.py status data symbol 600519 --market A
uv run python skills/stockaskill/scripts/run.py cache stats

# Git
git status
git add <file-path>
git commit -m "docs(agent): sync project instructions"
git push
```
