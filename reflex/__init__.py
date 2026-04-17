"""
REFLEX — Reflexive Evidence-based Loop for UI Development.

Pure Python package for evidence-based UI quality methodology.
No Django dependency in core — Django integration stays in each hub.

Architecture:
    reflex.agent             → DomainAgent (variable domain, LLM-powered)
    reflex.quality           → UC Quality Checker (11 criteria)
    reflex.classify          → Failure Classifier (UC_PROBLEM vs UI_PROBLEM)
    reflex.uc_dialog         → UCDialogEngine (interactive UC creation with feedback loop)
    reflex.permission_runner → PermissionRunner (automated permission matrix testing)
    reflex.cycle             → CycleRunner (full dev cycle orchestrator)
    reflex.scaffold          → Scaffold generator for reflex.yaml (ADR-163 Tier 1+2)
    reflex.platform_runner   → PlatformRunner for cross-hub health reports (ADR-163)
    reflex.config            → ReflexConfig from reflex.yaml
    reflex.providers         → KnowledgeProvider, DocumentProvider, WebProvider (Protocol)
    reflex.llm_providers     → AifwProvider, LiteLLMProvider (via iil-aifw / litellm)
    reflex.web               → HttpxWebProvider, PubChemAdapter, GESTISAdapter, PDFDocumentProvider
    reflex.types             → Dataclasses (Results, Questions, Entries, WebPage, SDSData)
    reflex.templates/        → promptfw .jinja2 templates (package_data)
    reflex.__main__          → CLI: python -m reflex check/research/scrape/sds/classify/
                                    uc-create/test-permissions/cycle/verify/init/platform/info

Usage:
    from reflex.agent import DomainAgent
    from reflex.config import ReflexConfig
    from reflex.uc_dialog import UCDialogEngine

    config = ReflexConfig.from_yaml("reflex.yaml")
    agent = DomainAgent(config=config)
    result = agent.research("SDS Upload Pipeline")

    engine = UCDialogEngine(config=config, llm=llm)
    state = engine.start("SDS hochladen und validieren")
"""

__version__ = "0.4.0"
