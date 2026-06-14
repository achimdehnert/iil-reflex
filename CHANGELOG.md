# Changelog — iil-reflex

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Fixed
- **`CycleRunner.run_full_cycle` left `final_status = PENDING` on a fully failed
  cycle** instead of `FAILED`: a phase failing on the last iteration `break`s out
  of the loop, so the `for/else` clause that set `FAILED` never fired. Now any
  non-`PASSED` exit is marked `FAILED`. Surfaced while raising cycle test coverage.
- **`CycleRunner.print_result` crashed with `TypeError`** on its trailing
  `logger.info()` call (no message argument). Now `logger.info("")`.

### Removed
- **Dead `reflex/dashboard.py`** (893 LOC): shadowed by the `reflex/dashboard/`
  package since the 2026-04-18 split — Python always imported the package, never
  the flat module. Removing it deletes unreachable code (was at 0% coverage).

### Added
- Test coverage for `reflex.cycle.CycleRunner` raised 50% → 98%: the
  `run_full_cycle` orchestration loop (pass / skip / retry / fail paths), phase
  runners (`_run_backend_tests` timeout & not-found, `_run_frontend_verify`,
  `_run_permission_tests`), `_classify_failure`, `_login_session`, and
  `print_result`.
- Test coverage for `reflex.review.metrics.MetricsWriter` (was 0%): no-URL
  degradation, env-var precedence, row writing, table creation, and graceful
  handling of a missing `psycopg` driver.

### Changed
- Python version metadata unified to **3.12** (matches `requires-python>=3.12`):
  dropped the stale `Python :: 3.11` classifier and bumped `ruff target-version`
  from `py311` to `py312`.

---

## [0.5.0] — 2026-04-23

### Added
- **HTTP Resilience Layer** (`reflex.web`): lazy-init `httpx.Client` with `threading.Lock`,
  `close()` + context-manager support, `_retry_get()` (tenacity, 3 attempts, exponential jitter),
  `_make_rate_limiter()` (pyrate-limiter or `time.sleep` fallback)
- **`reflex review`** command — infrastructure review plugins (ADR-165):
  `repo`, `compose`, `adr`, `port`, `all`, `list`; baseline support; PostgreSQL metrics emit
- **`reflex infra`** command — instant infrastructure lookup per repo; `--live` mode via SSH
  (container, HTTP, disk status)
- **`reflex dashboard`** — local dev dashboard with app tiles + Docker control (port 9000)
- **`reflex init`** — scaffold generator for `reflex.yaml` (ADR-163 Tier 1+2)
- **`reflex platform`** — platform-wide health report across all hubs (ADR-163)
- **`reflex.cycle`** — `CycleRunner` full dev-cycle orchestrator
- **`reflex.uc_dialog`** — `UCDialogEngine` interactive UC creation with feedback loop
- **`reflex.permission_runner`** — automated permission matrix testing
- **`reflex.platform_runner`** — cross-hub health reports (ADR-163)
- **`reflex.scaffold`** — scaffold generator module
- **`reflex.dashboard`** — dashboard server module
- **`reflex.infra`** — infrastructure lookup module
- **`reflex.llm_providers`** — `AifwProvider`, `LiteLLMProvider`, `get_provider()` auto-detection
- `pyproject.toml [web]`: added `tenacity>=9.0`, `hishel>=0.0.33`, `pyrate-limiter>=3.6`
- `pyproject.toml [dev]`: added `respx>=0.21`, `pytest-mock>=3.12`
- `pyproject.toml [metrics]`: `psycopg[binary]>=3.1`
- MIT LICENSE
- `requires-python >= 3.12`

### Changed
- `PubChemAdapter._build_sds()`: `time.sleep(0.25)` → `self._limiter()` (rate limiter)
- `GESTISAdapter`: added `self._limiter = _make_rate_limiter(5.0)`
- `HttpxWebProvider.fetch/search_web`: `except (OSError, ValueError)` → `except Exception`

### Fixed
- `hardcoded-ok` markers for `os.environ` usage (platform review false-positive suppression)
- Infra-plugin retention/size patterns broadened to match `RETENTION_DAYS`, `MAX_BACKUP_BYTES`

---

## [0.2.1] — 2026-04-17

### Added
- `reflex.web`: `HttpxWebProvider`, `PubChemAdapter`, `GESTISAdapter`, `PDFDocumentProvider`
- `reflex.quality`: `UCQualityChecker` — 11 criteria (C-01 to C-11)
- `reflex.classify`: `FailureClassifier` — decision tree + LLM fallback
- `reflex.agent`: `DomainAgent` — LLM-powered domain research (Zirkel 0)
- `reflex.config`: `ReflexConfig.from_yaml()` — hub-specific configuration
- `reflex.providers`: `WebProvider`, `KnowledgeProvider`, `DocumentProvider`, `LLMProvider` protocols
- `reflex.types`: 15+ frozen dataclasses
- CLI commands: `check`, `research`, `scrape`, `sds`, `classify`, `info`
- ADR-162: REFLEX-Methodik als eigenes PyPI Package
- ADR-163: Three-Tier REFLEX Quality Standard
