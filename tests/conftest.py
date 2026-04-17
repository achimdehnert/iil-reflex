"""Test fixtures for iil-reflex."""

import pytest

from reflex.config import ReflexConfig
from reflex.providers import MockDocumentProvider, MockKnowledgeProvider, MockLLMProvider


@pytest.fixture
def config() -> ReflexConfig:
    """Minimal REFLEX config for testing."""
    return ReflexConfig.from_dict({
        "hub_name": "test-hub",
        "vertical": "chemical_safety",
        "domain_keywords": ["SDS", "CAS", "GHS"],
        "quality": {
            "min_acceptance_criteria": 2,
            "max_uc_steps": 7,
        },
        "viewports": [
            {"name": "mobile", "width": 375, "height": 812},
            {"name": "desktop", "width": 1280, "height": 800},
        ],
    })


@pytest.fixture
def knowledge_provider() -> MockKnowledgeProvider:
    """Knowledge provider with sample entries."""
    provider = MockKnowledgeProvider()
    provider.add(
        "SDS Upload Pipeline",
        "Safety Data Sheets must be uploaded in PDF format. "
        "CAS numbers are validated against PubChem.",
        source="outline",
    )
    provider.add(
        "GHS Classification",
        "GHS pictograms are assigned based on hazard category. "
        "Signal words: Danger or Warning.",
        source="outline",
    )
    return provider


@pytest.fixture
def document_provider() -> MockDocumentProvider:
    """Document provider with sample entries."""
    provider = MockDocumentProvider()
    provider.add(
        "REACH Verordnung 2024",
        "Registrierung, Bewertung, Zulassung und Beschränkung chemischer Stoffe",
        source="paperless",
    )
    return provider


@pytest.fixture
def llm_provider() -> MockLLMProvider:
    """LLM provider with pre-configured responses."""
    return MockLLMProvider({
        "reflex.domain-research": '{"facts": ["SDS ist ein Sicherheitsdatenblatt"], '
            '"gaps": ["Welche Felder sind Pflicht?"], '
            '"contradictions": [], "confidence": 0.7}',
        "reflex.domain-interview": '{"questions": [{"question": "Welche SDS-Felder sind Pflicht?", '
            '"category": "data_model", "why_needed": "Pflichtfelder bestimmen DB-Schema", '
            '"expected_format": "list", "priority": "high"}]}',
        "reflex.domain-kb-distill": '{"glossary": {"SDS": "Sicherheitsdatenblatt"}, '
            '"required_fields": ["CAS-Nummer", "Produktname"], '
            '"invariants": ["CAS-Nummer ist einzigartig"], '
            '"scope_boundaries": ["Nicht enthalten: Transportvorschriften"], '
            '"markdown": "# Domain KB: test-hub"}',
        "reflex.uc-quality-check": '{"valid": true, "violations": [], '
            '"warnings": [], "adr_conflicts": []}',
        "reflex.failure-classify": '{"failure_type": "ui_problem", '
            '"confidence": 0.85, "reasoning": "Element fehlt", '
            '"suggested_action": "Wireframe korrigieren"}',
    })
