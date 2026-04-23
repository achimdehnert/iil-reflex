# iil-reflex

**REFLEX — Reflexive Evidence-based Loop for UI Development**

> Version **0.5.0** · Python ≥ 3.12 · Pure Python, no Django dependency · MIT License

Evidence-based UI quality methodology: LLM-powered domain research, UC quality checking,
failure classification, SDS hazardous-substance lookup, infrastructure review, and
full dev-cycle orchestration — as a standalone PyPI package.

[![Tests](https://img.shields.io/badge/tests-~290%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Table of Contents

1. [Installation](#installation)
2. [CLI Commands](#cli-commands)
3. [Quick Start (Python API)](#quick-start-python-api)
4. [Architecture](#architecture)
5. [Hub Configuration](#hub-configuration-reflexyaml)
6. [Provider Pattern](#provider-pattern)
7. [REFLEX Methodology](#reflex-methodology)
8. [Dependencies](#dependencies)
9. [Documentation](#documentation)

---

## Installation

```bash
# Core — UC Quality Check, Failure Classifier, Domain Agent (offline rules, no LLM)
pip install iil-reflex

# Web scraping + SDS lookup (PubChem, GESTIS) + HTTP resilience
pip install iil-reflex[web]

# LLM-powered research (Groq, OpenAI, Anthropic via litellm)
pip install iil-reflex[llm]

# Django-integrated LLM routing
pip install iil-reflex[aifw]

# Playwright browser testing
pip install iil-reflex[playwright]

# PostgreSQL metrics storage
pip install iil-reflex[metrics]

# Everything
pip install iil-reflex[all]
```

---

## CLI Commands

All commands available as `reflex <cmd>` or `python -m reflex <cmd>`.

### `reflex check` — UC Quality Check

```bash
reflex check docs/uc/UC-001-sds-upload.md
reflex check docs/uc/UC-001-sds-upload.md --config reflex.yaml
```

Checks a Use Case against 11 quality criteria. **No LLM, no internet required.**
Exit code `1` if any criterion fails.

### `reflex research` — Domain Research

```bash
reflex research "Zoneneinteilung nach ATEX und BetrSichV" --config reflex.yaml
reflex research "GHS Kennzeichnung" --backend litellm --model groq/llama-3.3-70b-versatile
reflex research "PubChem API" --web --json
```

LLM-powered domain knowledge extraction from internal sources + web.

| Option | Default | Description |
|--------|---------|-------------|
| `--backend`, `-b` | `litellm` | `litellm`, `aifw`, `auto` |
| `--model`, `-m` | `groq/llama-3.3-70b-versatile` | litellm model string |
| `--web`, `-w` | off | Enable DuckDuckGo web search |
| `--json`, `-j` | off | JSON output |

### `reflex sds` — SDS / Hazardous Substance Lookup

```bash
reflex sds "Acetone"                        # PubChem (default)
reflex sds 78-93-3                          # by CAS number
reflex sds Ethanol --source gestis
reflex sds "Methyl Ethyl Ketone" --source all --json
```

Returns CAS number, H-statements, P-statements, signal word, GHS pictograms.
Requires `iil-reflex[web]`. Uses connection pooling, retry, and rate-limiting (≤5 req/s).

### `reflex classify` — Failure Classification

```bash
reflex classify "test_should_show_danger_warning" "AssertionError: heading not found"
reflex classify "test_upload_pdf" "TimeoutError" --uc-file docs/uc/UC-003.md
```

Classifies a test failure as `UC_PROBLEM` / `UI_PROBLEM` / `INFRA_PROBLEM`.

### `reflex scrape` — Web Scrape

```bash
reflex scrape https://example.com/article
reflex scrape https://example.com/report.pdf --json
```

Extracts clean text from HTML pages or PDFs. Requires `iil-reflex[web]`.

### `reflex init` — Scaffold reflex.yaml (ADR-163)

```bash
reflex init --hub risk-hub --tier 1 --vertical hazmat --port 8001
reflex init --hub trading-hub --tier 2 --output config/reflex.yaml --force
```

Generates a hub configuration file for Tier 1 (full REFLEX) or Tier 2 (light).

### `reflex review` — Infrastructure Review (ADR-165)

```bash
reflex review all risk-hub
reflex review repo risk-hub --fail-on block
reflex review compose risk-hub --json
reflex review list                          # list available plugins
reflex review all risk-hub --init-baseline  # save current state as baseline
reflex review all risk-hub --emit-metrics   # write results to PostgreSQL
```

Plugins: `repo`, `compose`, `adr`, `port`, `all`, `list`.

### `reflex infra` — Infrastructure Lookup

```bash
reflex infra risk-hub
reflex infra risk-hub --live               # live status via SSH (container, HTTP, disk)
reflex infra risk-hub --json
```

### `reflex platform` — Platform-wide Health Report (ADR-163)

```bash
reflex platform --config platform.yaml
reflex platform --config platform.yaml --report report.md
```

### `reflex dashboard` — Local Dev Dashboard

```bash
reflex dashboard                           # http://localhost:9000
reflex dashboard --dashboard-port 9001
```

App tiles + Docker control for all local hubs.

### `reflex info` — Show Config

```bash
reflex info --config reflex.yaml
```

---

## Quick Start (Python API)

```python
from reflex.config import ReflexConfig
from reflex.quality import UCQualityChecker

# 1. Load hub config
config = ReflexConfig.from_yaml("reflex.yaml")

# 2. UC Quality Check — no LLM, no internet
checker = UCQualityChecker(config)
result = checker.check(uc_text="...", uc_slug="sds-upload")
print(f"Score: {result.score_percent}%, Passed: {result.passed}")
# → Score: 82%, Passed: False
# → Criteria details in result.criteria (list of QualityCriterion)

# 3. Domain Research — LLM-powered
from reflex.agent import DomainAgent
from reflex.llm_providers import get_provider

llm = get_provider(backend="litellm", model="groq/llama-3.3-70b-versatile")
agent = DomainAgent(config=config, llm=llm)
research = agent.research("SDS Upload Pipeline")
print(f"Facts: {len(research.facts)}, Gaps: {len(research.gaps)}")

# 4. Failure Classification
from reflex.classify import FailureClassifier

clf = FailureClassifier()
result = clf.classify("test_show_warning", "AssertionError: heading not found")
print(f"Type: {result.failure_type}, Action: {result.suggested_action}")

# 5. SDS Lookup — with connection pool + retry + rate-limiting
from reflex.web import HttpxWebProvider, PubChemAdapter

with HttpxWebProvider() as web:         # context manager — reuses TCP connection
    adapter = PubChemAdapter(web=web)
    sds = adapter.lookup_by_name("Acetone")
    print(f"CAS: {sds.cas_number}, Signal: {sds.signal_word}")
    # → CAS: 67-64-1, Signal: Gefahr

# 6. Interactive UC Dialog
from reflex.uc_dialog import UCDialogEngine

engine = UCDialogEngine(config=config, llm=llm)
state = engine.start("SDS hochladen und validieren")

# 7. Infra Review
from reflex.infra import cmd_infra
# or: subprocess.run(["reflex", "infra", "risk-hub", "--live"])
```

---

## Architecture

```
iil-reflex/
├── reflex/
│   ├── agent.py              # DomainAgent — LLM-powered domain research (Zirkel 0)
│   ├── quality.py            # UCQualityChecker — 11 rule-based criteria
│   ├── classify.py           # FailureClassifier — UC/UI/Infra decision tree + LLM
│   ├── uc_dialog.py          # UCDialogEngine — interactive UC creation with feedback loop
│   ├── permission_runner.py  # PermissionRunner — automated HTTP permission matrix testing
│   ├── cycle.py              # CycleRunner — full Backend→Frontend→Test→Fix orchestration
│   ├── web.py                # HttpxWebProvider · PubChemAdapter · GESTISAdapter · PDFProvider
│   │                         #   └─ HTTP Resilience: session reuse, retry (tenacity),
│   │                         #      rate-limiting (pyrate-limiter), context manager
│   ├── llm_providers.py      # AifwProvider (Django) · LiteLLMProvider · get_provider()
│   ├── scaffold.py           # ScaffoldOptions · scaffold() — reflex.yaml generator
│   ├── platform_runner.py    # PlatformRunner — cross-hub health reports (ADR-163)
│   ├── dashboard.py          # Dev dashboard server — app tiles + Docker control
│   ├── infra.py              # Infrastructure lookup — server, port, DB, domain
│   ├── config.py             # ReflexConfig · from_yaml() · Viewport · QualityConfig
│   ├── providers.py          # Protocols: KnowledgeProvider · DocumentProvider
│   │                         #            WebProvider · LLMProvider (+ Mock implementations)
│   ├── types.py              # 15+ frozen dataclasses: SDSData · WebPage · UCQualityResult
│   │                         #   ClassifyResult · DomainResearchResult · TestRunResult · …
│   └── templates/            # 8 Jinja2 prompt templates (promptfw package_data)
├── tests/                    # ~290 tests · ~6s · httpx mocked via respx
├── CHANGELOG.md
├── pyproject.toml
└── README.md
```

---

## Hub Configuration (reflex.yaml)

```yaml
hub_name: risk-hub
vertical: chemical_safety
domain_keywords: ["SDS", "CAS", "GHS", "REACH", "Gefahrstoff"]

quality:
  min_acceptance_criteria: 2
  max_uc_steps: 7
  require_error_cases: true
  forbid_implementation_details: true
  forbid_soft_language: true

viewports:
  - {name: mobile,  width: 375,  height: 812}
  - {name: desktop, width: 1280, height: 800}

htmx_patterns:
  banned: ["hx-boost"]
  required_on_forms: ["hx-indicator"]

# Route → role → expected HTTP status
permissions_matrix:
  /substances/:
    anonymous: 302
    viewer: 200
    admin: 200
  /substances/create/:
    anonymous: 302
    viewer: 403
    admin: 200

test_users:
  admin:   {username: admin,  password: admin123,  is_superuser: true}
  viewer:  {username: viewer, password: viewer123, org_role: member}

dev_cycle:
  base_url: http://localhost:8003
  login_url: /accounts/login/
  backend_test_cmd: "pytest src/ -q --tb=short"
  lint_cmd: "ruff check src/"
  max_fix_iterations: 3
  public_routes: [/accounts/login/, /livez/, /healthz/]
```

---

## Provider Pattern

All external services use `@runtime_checkable` Protocols — swap without code changes:

```python
from reflex.providers import KnowledgeProvider, LLMProvider

class OutlineKnowledgeProvider(KnowledgeProvider):
    def search(self, query: str, limit: int = 5) -> list:
        ...  # call Outline API

class GroqLLMProvider(LLMProvider):
    def complete(self, messages: list, action_code: str = "") -> str:
        ...  # call Groq API
```

Built-in: `AifwProvider` (Django/iil-aifw), `LiteLLMProvider` (CLI).
Testing: `MockKnowledgeProvider`, `MockDocumentProvider`, `MockWebProvider`, `MockLLMProvider`.

---

## REFLEX Methodology

Three quality circles — **no artifact without evidence**:

| Circle | Name | Owner | Gate |
|--------|------|-------|------|
| **Zirkel 0** | Domain KB | DomainAgent + Expert | Signed-off KB file |
| **Zirkel 1** | UC Quality | UCQualityChecker | Score ≥ 80%, all 11 criteria |
| **Zirkel 2** | Test Coverage | PermissionRunner + Playwright | 1 test per acceptance criterion |

**Failure Classification Flow:**

```
Test fails
    ↓
reflex classify "<test_name>" "<error_message>" [--uc-file <path>]
    ↓
UC_PROBLEM   → UC needs revision → restart Zirkel 1
UI_PROBLEM   → Template/View fix → re-run tests
INFRA_PROBLEM → DevOps → check server/network
```

---

## Dependencies

| Extra | Key Packages | Purpose |
|-------|-------------|---------|
| *(core)* | `iil-promptfw>=0.7`, `pyyaml>=6.0` | Prompt templates, config |
| `[web]` | `httpx>=0.27`, `tenacity>=9.0`, `pyrate-limiter>=3.6`, `hishel>=0.0.33`, `beautifulsoup4>=4.12`, `pdfplumber>=0.11` | HTTP client with resilience, SDS APIs, PDF |
| `[llm]` | `litellm>=1.40` | Standalone LLM calls |
| `[aifw]` | `iil-aifw>=0.9` | Django-integrated LLM routing |
| `[playwright]` | `playwright>=1.40` | Browser-based testing |
| `[metrics]` | `psycopg[binary]>=3.1` | PostgreSQL metrics |

---

## Documentation

| Document | Audience | Link |
|----------|----------|------|
| Möglichkeiten & Arbeitsweise | Product Owner, Fachexperten | [→ Outline](https://knowledge.iil.pet/doc/reflex-moglichkeiten-und-arbeitsweise-if47bsKMgP) |
| Funktionsbeschreibung (technisch) | Entwickler | [→ Outline](https://knowledge.iil.pet/doc/iil-reflex-funktionsbeschreibung-rfOPSaQfxO) |
| CLI Referenz | Entwickler, DevOps | [→ Outline](https://knowledge.iil.pet/doc/iil-reflex-cli-referenz-alle-befehle-und-beispiele-t7Eg3h8k7b) |
| HTTP Resilience Layer | Reviewer, Architekten | [→ Outline](https://knowledge.iil.pet/doc/iil-reflex-http-resilience-layer-webpy-optimierungen-apr-2026-A0HzBoxvoV) |
| ADR-162 (Package-Entscheidung) | Architekten | [→ Outline](https://knowledge.iil.pet/doc/reflex-v20-domain-agent-iil-reflex-package-QrJyvkd068) |
| ADR-163 (Three-Tier Standard) | Platform-Team | [→ Outline](https://knowledge.iil.pet/doc/adr-163-three-tier-reflex-quality-standard-implementierung-h1390OhKQm) |
| CHANGELOG | Alle | [CHANGELOG.md](CHANGELOG.md) |

---

## License

MIT — see [LICENSE](LICENSE)
