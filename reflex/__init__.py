"""
REFLEX — Reflexive Evidence-based Loop for UI Development.

Pure Python package for evidence-based UI quality methodology.
No Django dependency in core — Django integration stays in each hub.

Architecture:
    reflex.agent         → DomainAgent (variable domain, LLM-powered)
    reflex.quality       → UC Quality Checker (11 criteria)
    reflex.classify      → Failure Classifier (UC_PROBLEM vs UI_PROBLEM)
    reflex.config        → ReflexConfig from reflex.yaml
    reflex.providers     → KnowledgeProvider, DocumentProvider, WebProvider (Protocol)
    reflex.llm_providers → AifwProvider, LiteLLMProvider (via iil-aifw / litellm)
    reflex.web           → HttpxWebProvider, PubChemAdapter, GESTISAdapter, PDFDocumentProvider
    reflex.types         → Dataclasses (Results, Questions, Entries, WebPage, SDSData)
    reflex.templates/    → promptfw .jinja2 templates (package_data)
    reflex.__main__      → CLI: python -m reflex check/research/scrape/sds/classify/info

Usage:
    from reflex.agent import DomainAgent
    from reflex.config import ReflexConfig

    config = ReflexConfig.from_yaml("reflex.yaml")
    agent = DomainAgent(config=config)
    result = agent.research("SDS Upload Pipeline")
"""

__version__ = "0.2.0"
