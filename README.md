# iil-reflex

**REFLEX — Reflexive Evidence-based Loop for UI Development**

Evidence-based UI development methodology with LLM-powered domain agent,
interactive UC dialog, automated permission testing, full development cycle
orchestration, UC quality checker, and failure classifier.
Pure Python — no Django dependency.

## Architecture

```
reflex/
├── agent.py             # DomainAgent (variable domain, LLM-powered)
├── quality.py           # UC Quality Checker (11 criteria, rule-based)
├── classify.py          # Failure Classifier (decision tree + LLM)
├── uc_dialog.py         # UCDialogEngine (interactive UC creation with feedback loop)
├── permission_runner.py # PermissionRunner (automated permission matrix testing)
├── cycle.py             # CycleRunner (full Backend→Frontend→Test→Fix orchestration)
├── config.py            # ReflexConfig from reflex.yaml
├── providers.py         # KnowledgeProvider, DocumentProvider, LLMProvider (Protocol)
├── llm_providers.py     # AifwProvider, LiteLLMProvider (via iil-aifw / litellm)
├── web.py               # HttpxWebProvider, PubChemAdapter, GESTISAdapter, PDFProvider
├── types.py             # 15+ Dataclasses (Results, Questions, Entries, WebPage, SDSData)
└── templates/           # promptfw .jinja2 templates (8 templates)
```

## Installation

```bash
pip install iil-reflex
# Optional extras:
pip install iil-reflex[web]         # httpx, beautifulsoup4, pdfplumber
pip install iil-reflex[llm]         # litellm for standalone LLM calls
pip install iil-reflex[playwright]  # Playwright for Zirkel 2
pip install iil-reflex[all]         # everything
```

## CLI Commands

```bash
# UC Quality Check
python -m reflex check docs/uc/UC-001-sds-upload.md

# Domain Research (LLM-powered)
python -m reflex research "Zoneneinteilung nach ATEX" -c reflex.yaml

# Interactive UC Creation Dialog (NEW in v0.3)
python -m reflex uc-create "SDS hochladen und validieren" -c reflex.yaml

# Permission Matrix Testing (NEW in v0.3)
python -m reflex test-permissions -c reflex.yaml

# Full Development Cycle (NEW in v0.3)
python -m reflex cycle UC-001 -c reflex.yaml

# Quick Route Verification (NEW in v0.3)
python -m reflex verify -c reflex.yaml --base-url http://localhost:8003

# Failure Classification
python -m reflex classify "test_should_show_error" "AssertionError: heading"

# Web Scraping (HTML + PDF)
python -m reflex scrape https://example.com/page

# SDS Data Lookup (PubChem + GESTIS)
python -m reflex sds "Acetone" --source all

# Config Info
python -m reflex info -c reflex.yaml
```

## Quick Start

```python
from reflex.agent import DomainAgent
from reflex.config import ReflexConfig
from reflex.quality import UCQualityChecker
from reflex.uc_dialog import UCDialogEngine

# 1. Load hub config
config = ReflexConfig.from_yaml("reflex.yaml")

# 2. UC Quality Check (rule-based, no LLM needed)
checker = UCQualityChecker(config)
result = checker.check(uc_text="...", uc_slug="sds-upload")
print(f"Score: {result.score_percent}%, Passed: {result.passed}")

# 3. Interactive UC Dialog (LLM-powered)
engine = UCDialogEngine(config=config, llm=your_llm_provider)
state = engine.start("SDS hochladen und validieren")
questions = engine.get_questions(state)  # Targeted follow-ups
state = engine.refine(state, answers={"C-01": "Der Laborleiter"})

# 4. Domain Agent (LLM-powered)
agent = DomainAgent(
    config=config,
    llm=your_llm_provider,
    knowledge=your_knowledge_provider,  # optional
    documents=your_document_provider,   # optional
)
research = agent.research("SDS Upload Pipeline")
questions = agent.generate_interview(research)
kb = agent.distill_kb(research, expert_answers={...})

# 5. Permission Matrix Testing
from reflex.permission_runner import PermissionRunner
runner = PermissionRunner.from_yaml("reflex.yaml")
report = runner.run_all()
print(f"Pass rate: {report.pass_rate}%")

# 6. Full Development Cycle
from reflex.cycle import CycleConfig, CycleRunner
config = CycleConfig.from_yaml("reflex.yaml")
runner = CycleRunner(config)
result = runner.run_full_cycle(uc_slug="UC-001")
```

## Hub Configuration (reflex.yaml)

```yaml
hub_name: risk-hub
vertical: chemical_safety
domain_keywords: ["SDS", "CAS", "GHS", "REACH"]

quality:
  min_acceptance_criteria: 2
  max_uc_steps: 7
  require_error_cases: true

viewports:
  - {name: mobile, width: 375, height: 812}
  - {name: desktop, width: 1280, height: 800}

htmx_patterns:
  banned: ["hx-boost"]
  required_on_forms: ["hx-indicator"]

# Permission matrix: route → role → expected HTTP status
permissions_matrix:
  /substances/:
    anonymous: 302
    viewer: 200
    admin: 200
  /substances/create/:
    anonymous: 302
    viewer: 403
    admin: 200

# Test users for permission + cycle testing
test_users:
  admin:
    username: admin
    password: admin123
    is_superuser: true
  viewer:
    username: viewer
    password: viewer123
    org_role: member

# Development cycle configuration
dev_cycle:
  base_url: http://localhost:8003
  login_url: /accounts/login/
  backend_test_cmd: "pytest src/ -q --tb=short"
  lint_cmd: "ruff check src/"
  max_fix_iterations: 3
  public_routes:
    - /accounts/login/
    - /livez/
    - /healthz/
```

## Provider Pattern

All external dependencies use Protocols (Dependency Inversion):

```python
from reflex.providers import KnowledgeProvider, LLMProvider

class OutlineProvider(KnowledgeProvider):
    def search(self, query, limit=5):
        return mcp3_search_knowledge(query, limit=limit)

class GroqProvider(LLMProvider):
    def complete(self, messages, action_code=""):
        return groq_client.chat(messages=messages)
```

Built-in LLM providers: `AifwProvider` (Django), `LiteLLMProvider` (standalone CLI).
Mock providers for testing: `MockKnowledgeProvider`, `MockDocumentProvider`, `MockLLMProvider`.

## REFLEX Methodology

Three quality circles — no artifact without evidence:

1. **Zirkel 0** — Domain KB (DomainAgent + Expert sign-off)
2. **Zirkel 1** — UC Quality (11 criteria, 100% score required)
3. **Zirkel 2** — Playwright Tests (1 test per acceptance criterion)

Development Cycle (CycleRunner):
- **Z2** Backend Tests → **Z3** Frontend Route Verification → **Z4** Permission Matrix → **Z5** Failure Classification → Retry Loop

Failure Classification:
- **UC_PROBLEM** → UC needs revision (Zirkel 1 restart)
- **UI_PROBLEM** → Wireframe needs fix
- **INFRA_PROBLEM** → Server/browser/network issue

## Dependencies

- `iil-promptfw>=0.7.0` — prompt template rendering
- `pyyaml>=6.0` — config file parsing
- Optional: `httpx`, `beautifulsoup4`, `pdfplumber` — web scraping + SDS lookup
- Optional: `litellm` — standalone LLM calls
- Optional: `playwright` — for Zirkel 2 test execution

## Related

- [ADR-162](https://knowledge.iil.pet/doc/adr-162-reflex) — Full ADR
- [iil-promptfw](https://github.com/achimdehnert/promptfw) — Prompt framework
- Platform: [achimdehnert/platform](https://github.com/achimdehnert/platform)

## License

MIT
