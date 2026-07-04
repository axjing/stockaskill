
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

#### Principle 1: Usability over Performance

* The project’s primary goal is usability
* A secondary goal is to have _reasonable_ performance

We believe the ability to maintain our flexibility to support researchers who are building on top of our abstractions remains critical. We can’t see what the future of workloads will be, but we know we want them to be built first on this platform, and that requires flexibility.

In more concrete terms, we operate in a _usability-first_ manner and try to avoid jumping to _restriction-first_ regimes (for example, static shapes, graph-mode only) without a clear-eyed view of the tradeoffs. Often there is a temptation to impose strict user restrictions upfront because it can simplify implementation, but this comes with risks:

* The performance may not be worth the user friction, either because the performance benefit is not compelling enough or it only applies to a relatively narrow set of subproblems.
* Even if the performance benefit is compelling, the restrictions can fragment the ecosystem into different sets of limitations that can quickly become incomprehensible to users.

We want users to be able to seamlessly move their code built with this framework to different hardware and software platforms, to interoperate with different libraries and frameworks, and to experience the full richness of the framework’s user experience, not a least common denominator subset.

#### Principle 2: Simple Over Easy

Here, we borrow from The Zen of Python:

* _Explicit is better than implicit_
* _Simple is better than complex_

A more concise way of describing these two goals is **Simple Over Easy**. Let’s start with an example because _simple_ and _easy_ are often used interchangeably in everyday English. Consider how one may model computational devices in such a framework:

* **Simple / Explicit (to understand, debug)**
* **Easy / Implicit (to use)**

As a general design philosophy, the project favors exposing simple and explicit building blocks rather than APIs that are easy-to-use by practitioners. The simple version is immediately understandable and debuggable by a new user. The easy solution may let a new user move faster initially, but debugging such a system can be complex: How did the system make its determination? What is the API for plugging into such a system and how are objects represented in its intermediate representation?

Some classic arguments in favor of this sort of design come from foundational literature on distributed computation (**TLDR:** Do not model resources with very different performance characteristics uniformly, the details will leak) and the End-to-End Principle (TLDR: building smarts into the lower layers of the stack can prevent building performant features at higher layers, and often doesn’t work anyway). For example, we could build operator-level or global device movement rules, but the precise choices aren’t obvious and building an extensible mechanism has unavoidable complexity and latency costs.

A caveat here is that this does not mean that higher-level “easy�?APIs are not valuable; certainly there is value in, for example, higher layers in the stack to support efficient tensor computations across heterogeneous compute in a large cluster. Instead, what we mean is that focusing on simple lower-level building blocks helps inform the easy API while still maintaining a good experience when users need to leave the beaten path. It also allows space for innovation and the growth of more opinionated tools at a rate we cannot support in the core library, but ultimately benefit from, as evidenced by our rich ecosystem. In other words, not automating at the start allows us to potentially reach levels of good automation faster.

#### Principle 3: Primary Language First with Best-in-Class Language Interoperability

This principle began as **Primary Language First**:

> The framework is not a binding of its primary language into a monolithic C++ core. It is built to be deeply integrated into that language. You can use it naturally like you would use well-established libraries in that ecosystem. You can write your new neural network layers in the language itself, using your favorite libraries and packages such as performance-oriented extensions. Our goal is to not reinvent the wheel where appropriate.

One thing the project has needed to deal with over the years is language runtime overhead: we first rewrote key components in C++, then the majority of operator definitions, then developed an ahead-of-time compilation flow and a C++ frontend.

Still, working in the primary language provides easily the best experience for our users: it is flexible, familiar, and perhaps most importantly, has a huge ecosystem of scientific computing libraries and extensions available for use. This fact motivates some of our most recent contributions, which attempt to hit a Pareto optimal point close to the language usability end of the curve:

* A dynamic bytecode transformation engine capable of speeding up existing eager-mode programs with minimal user intervention.
* Extension points (such as tensor-level function overrides and operator dispatch customization) that have enabled primary-language-first functionality to be built on top of C++ internals, enabling tools like symbolic tracers and composable function transforms respectively.

These design principles are not hard-and-fast rules, but hard-won choices and anchor how we built this project to be the debuggable, hackable, and flexible framework it is today. As we have more contributors and maintainers, we look forward to applying these core principles with you across our libraries and ecosystem. We are also open to evolving them as we learn new things and the technology space evolves, as we know it will.

## Git Workflow

Multiple concurrent development sessions may run in the same directory. All Git operations must avoid overwriting other sessions�?work.

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

- Follow quality gates and workflow rules defined in CONTRIBUTING.md
- Label new issues with all applicable pkg:* tags (e.g., pkg:agent , pkg:ai , pkg:tui )
- Inspect PRs via `gh pr view` , `gh pr diff` , or `git show` ; do not switch local branches for PR reviews unless explicitly instructed
- Submit multi-line issue/PR comments via temp files and --body-file flag; avoid multiline Markdown via inline --body
- Append official AI-generated disclaimer to all AI-submitted comments
- Auto-close issues via commit messages: use `closes #X` / `fixes #X` for each individual issue (do not batch multiple issues under one keyword)

## Changelog Standards

- Location: Independent CHANGELOG.md per package under packages/*/
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

Only erasable Node strip-only syntax is allowed for code under packages/*/src , packages/*/test , packages/coding-agent/examples :

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
- API URLs, ports, file paths, secrets, tokens �?all in config/env variables.
- No magic numbers.

### Modification Rules
- Delete/disable existing features only after user confirmation.
- Large-scale refactoring: read full file/module first.
- When CLI surface, capability scope, or user-facing workflows change, check whether `README.md`, `stockaskill/SKILL.md`, and `AGENTS.md` need synchronized updates.

### 3rdparty Directory
- `3rdparty/` is read-only. Never modify files inside it.

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
- Modifying files under `3rdparty/`

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

# Git
git status
git add <file-path>
git commit -m "docs(agent): sync project instructions"
git push
```
