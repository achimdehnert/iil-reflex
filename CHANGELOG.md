# Changelog — iil-reflex

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
