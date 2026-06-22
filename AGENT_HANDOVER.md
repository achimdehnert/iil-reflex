# AGENT_HANDOVER — iil-reflex

> Living handover for the next agent/session. Keep this current. `NEXT.md` is an
> auto-generated cache and is **not** the source of truth — this file is.

## Current state (2026-06-22)

- Version: **0.6.0** (`pyproject.toml` + CHANGELOG `[0.6.0]` entry aligned).
- Tests: green — `make test` → **467 passed, 2 skipped** (integration tests
  marked `integration`, skipped by default; need tesseract + poppler).
- Coverage: **~88%** (3553 stmts, 417 missing). No coverage gate configured.
- Lint: `ruff check reflex/ tests/` clean.
- Types: **no `mypy` configured** (later tier).
- CI: `ci.yml` (lint + test) + `publish.yml` (PyPI; `v*` tag push or
  `workflow_dispatch` — gated, not on-merge).

## Recently landed

- Agent-readiness (Tier 1): `__version__` now resolves from package metadata
  (was hardcoded), `__all__` added, `CLAUDE.md` + `AGENT_HANDOVER.md` added.
  No `pyproject`/Makefile config change needed — already aligned (see below).
- SSRF hardening of `HttpxWebProvider.search_web` (routes through `_guarded_get`)
  — currently under CHANGELOG `[Unreleased]`.
- 0.6.0: SSH host-key `accept-new`, aifw-fallback logging, CLI report output via
  `print()`, permission-runner crash fixes.

## Known issues / TODO

- **No `mypy`** and no `[tool.mypy]` config — typing is a deliberate later tier.
- **No `__all__` / metadata-based `__version__` historically** — added in this
  Tier 1 PR; the top-level public surface is intentionally just `__version__`
  (real API is by-submodule).
- **CHANGELOG header sync — already OK at origin/main:** the audit flagged "0.6.0
  changes sitting under `[Unreleased]`", but on `origin/main` there is already a
  proper `## [0.6.0] — 2026-06-14` header, and `[Unreleased]` now holds only the
  genuinely-unreleased SSRF fix. **No edit was made** — nothing to fix.
- No coverage floor configured.

## Next priorities

1. Introduce a `[tool.mypy]` config (start lenient) + a `make types` target,
   then drive type errors down (Tier 2).
2. Add a coverage floor once the ~88% baseline is agreed.
3. Decide whether the `[Unreleased]` SSRF fix warrants a patch release (gated).

## Pointers

- Architecture + commands: `CLAUDE.md`.
- Public API map: `reflex/__init__.py` docstring (by-submodule).
- Changelog: `CHANGELOG.md` (Keep a Changelog).
- Release process: `CLAUDE.md` → Release (gated).
