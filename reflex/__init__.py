"""
REFLEX — Reflexive Evidence-based Loop for UI Development.

Pure Python package for evidence-based UI quality methodology.
No Django dependency in core — Django integration stays in each hub.

Architecture:
    reflex.agent      → DomainAgent (variable domain, LLM-powered)
    reflex.quality    → UC Quality Checker (11 criteria)
    reflex.classify   → Failure Classifier (UC_PROBLEM vs UI_PROBLEM)
    reflex.config     → ReflexConfig from reflex.yaml
    reflex.providers  → KnowledgeProvider, DocumentProvider (Protocol)
    reflex.types      → Dataclasses (Results, Questions, Entries)
    reflex.templates/ → promptfw .jinja2 templates (package_data)

Usage:
    from reflex.agent import DomainAgent
    from reflex.config import ReflexConfig

    config = ReflexConfig.from_yaml("reflex.yaml")
    agent = DomainAgent(config=config)
    result = agent.research("SDS Upload Pipeline")
"""

__version__ = "0.1.0"
