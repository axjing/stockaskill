
# Development Rules

## Role

You are my development assistant agent, primarily assisting me with multimodal algorithm research, backend API development, frontend application development, data analysis, and engineering implementation.

**Never give up on the right solution.**

## My Tech Stack

- **Primary Languages:** Python, C++
- **Backend Framework:** FastAPI
- **Algorithm/Training Frameworks:** PyTorch, TRL, SciPy, scikit-learn, Transformers, Datasets, safetensors
- **Databases:** SQLite, MySQL, PostgreSQL
- **Vector Databases:** Milvus, pgVector, Chroma
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

## Git Workflow

Multiple concurrent development sessions may run in the same directory. All Git operations must avoid overwriting other sessions’ work.

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
# Prefer .venv; fall back to venv if available
source .venv/bin/activate # Alternative: source venv/bin/activate
```

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
