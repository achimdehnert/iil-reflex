# CLAUDE.md — iil-reflex

Operating guide for an AI agent working in this repo. Repo-specific; the
user-level `~/.claude/CLAUDE.md` still applies and wins on conflicts.

## What this is

`iil-reflex` (dist `iil-reflex`, import `reflex`) is REFLEX — a **Reflexive
Evidence-based Loop for UI Development**. A pure-Python package (no Django in
core) implementing an evidence-based UI quality methodology: an LLM-powered
domain agent, a UC quality checker, a failure classifier (UC vs UI problem), an
interactive UC dialog engine, permission-matrix testing, and a full dev-cycle
orchestrator. Shipped as a PyPI library plus a `reflex` CLI
(`python3 -m reflex …`). Django integration lives in each consuming hub, not here.

## Setup

```bash
make install                     # .venv/bin/pip install -e ".[dev,web]"
# or directly:
python3 -m pip install -e ".[dev,web]"
```

`__version__` is read from installed package metadata (`reflex.__version__`),
falling back to `"0.0.0.dev0"` in an uninstalled source checkout.

## Test / lint / types

```bash
make test              # .venv/bin/python -m pytest --tb=short -q   (unit suite, no system deps)
make test-integration  # pytest -m integration   (needs tesseract + poppler)
make lint              # .venv/bin/ruff check reflex/ tests/
```

- Tests live in `tests/`; ~467 unit tests + a few `integration`-marked tests
  that require real system deps (OCR/PDF) and are skipped by default.
- No `mypy` is configured yet (see Known issues). Type-checking is a later tier.

## Architecture (module map)

| Module | Responsibility |
|---|---|
| `agent.py` | `DomainAgent` — variable-domain, LLM-powered research agent |
| `quality.py` | UC Quality Checker (11 criteria) |
| `classify.py` | Failure Classifier (`UC_PROBLEM` vs `UI_PROBLEM`) |
| `uc_dialog.py` | `UCDialogEngine` — interactive UC creation with feedback loop |
| `permission_runner.py` | `PermissionRunner` — automated permission-matrix testing |
| `cycle.py` | `CycleRunner` — full dev-cycle orchestrator |
| `scaffold.py` | Scaffold generator for `reflex.yaml` (ADR-163 Tier 1+2) |
| `platform_runner.py` | `PlatformRunner` — cross-hub health reports (ADR-163) |
| `infra.py` | infra checks (`reflex infra`, SSH host-key `accept-new`) |
| `dashboard/` | local dev dashboard (app tiles + docker control) |
| `config.py` | `ReflexConfig` loaded from `reflex.yaml` |
| `providers.py` | `KnowledgeProvider` / `DocumentProvider` / `WebProvider` (Protocols) |
| `llm_providers.py` | `AifwProvider`, `LiteLLMProvider` (via iil-aifw / litellm) |
| `web.py` | `HttpxWebProvider`, PubChem/GESTIS adapters, PDF document provider (SSRF-guarded) |
| `review/` | review plugins |
| `types.py` | dataclasses (Results, Questions, Entries, WebPage, SDSData) |
| `templates/` | promptfw `.jinja2` templates (shipped as package data) |
| `__main__.py` | `reflex` CLI entry point |

Public surface is **by submodule** — import directly, e.g.
`from reflex.agent import DomainAgent`. The top-level `reflex` namespace exposes
only `__version__` (see `reflex/__init__.py` docstring for the full map).

## Conventions

- Commits: `[feat|fix|refactor|docs|test|chore](scope): description`.
- Tests: `test_should_<expected_behavior>`.
- Optional-dependency groups are intentionally split (`web` lean vs `web-pdf`
  with OCR/PDF) — keep the common httpx path free of heavy deps.

## Release (GATED)

Versioned in `pyproject.toml` + `reflex/__init__.py` metadata + `CHANGELOG.md`
(Keep a Changelog). Publishing to PyPI is a **deliberate, gated step**: CI
`publish.yml` fires on a `v*` tag push or `workflow_dispatch` — **never**
automatically on merge to `main`. Keep `pyproject.version`, the CHANGELOG top
entry, and the published PyPI version in sync. Tagging/publishing requires an
explicit human go-ahead.

## Known issues / gotchas

- No `[tool.mypy]` config — type-checking is a later tier; do not add it here.
- No coverage gate (current coverage ~88%).
- See `AGENT_HANDOVER.md` for current state and next priorities.
