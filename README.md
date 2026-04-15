# iil-reflex

**REFLEX — Reflexive Evidence-based Loop for UI Development**

Evidence-based UI development methodology with LLM-powered domain agent,
UC quality checker, and failure classifier. Pure Python — no Django dependency.

## Architecture

```
reflex/
├── agent.py       # DomainAgent (variable domain, LLM-powered)
├── quality.py     # UC Quality Checker (11 criteria, rule-based)
├── classify.py    # Failure Classifier (decision tree + LLM)
├── config.py      # ReflexConfig from reflex.yaml
├── providers.py   # KnowledgeProvider, DocumentProvider (Protocol)
├── types.py       # Dataclasses (Results, Questions, Entries)
└── templates/     # promptfw .jinja2 templates (6 templates)
```

## Installation

```bash
pip install iil-reflex
# Optional: Playwright for Zirkel 2
pip install iil-reflex[playwright]
```

## Quick Start

```python
from reflex.agent import DomainAgent
from reflex.config import ReflexConfig
from reflex.quality import UCQualityChecker

# 1. Load hub config
config = ReflexConfig.from_yaml("reflex.yaml")

# 2. UC Quality Check (rule-based, no LLM needed)
checker = UCQualityChecker(config)
result = checker.check(uc_text="...", uc_slug="sds-upload")
print(f"Score: {result.score_percent}%, Passed: {result.passed}")

# 3. Domain Agent (LLM-powered)
agent = DomainAgent(
    config=config,
    llm=your_llm_provider,
    knowledge=your_knowledge_provider,  # optional
    documents=your_document_provider,   # optional
)
research = agent.research("SDS Upload Pipeline")
questions = agent.generate_interview(research)
kb = agent.distill_kb(research, expert_answers={...})
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
permissions_matrix:
  /substances/: {anonymous: 302, viewer: 200, admin: 200}
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

Mock providers included for testing:
`MockKnowledgeProvider`, `MockDocumentProvider`, `MockLLMProvider`

## REFLEX Methodology

Three quality circles — no artifact without evidence:

1. **Zirkel 0** — Domain KB (DomainAgent + Expert sign-off)
2. **Zirkel 1** — UC Quality (11 criteria, 100% score required)
3. **Zirkel 2** — Playwright Tests (1 test per acceptance criterion)

Failure Classification:
- **UC_PROBLEM** → UC needs revision (Zirkel 1 restart)
- **UI_PROBLEM** → Wireframe needs fix
- **INFRA_PROBLEM** → Server/browser/network issue

## Dependencies

- `iil-promptfw>=0.7.0` — prompt template rendering
- `pyyaml>=6.0` — config file parsing
- Optional: `playwright` — for Zirkel 2 test execution

## Related

- [ADR-162](https://knowledge.iil.pet/doc/adr-162-reflex) — Full ADR
- [iil-promptfw](https://github.com/achimdehnert/promptfw) — Prompt framework
- Platform: [achimdehnert/platform](https://github.com/achimdehnert/platform)

## License

MIT
