"""Tests for DomainAgent — pure Python, no Django."""

from reflex.agent import DomainAgent
from reflex.config import ReflexConfig
from reflex.providers import MockDocumentProvider, MockKnowledgeProvider, MockLLMProvider


class TestDomainAgentResearch:
    """Test autonomous domain research (Zirkel 0, Phase 1-2)."""

    def test_should_research_with_all_providers(
        self, config, knowledge_provider, document_provider, llm_provider
    ):
        agent = DomainAgent(
            config=config,
            llm=llm_provider,
            knowledge=knowledge_provider,
            documents=document_provider,
        )
        result = agent.research("SDS Upload Pipeline")

        assert result.topic == "SDS Upload Pipeline"
        assert result.vertical == "chemical_safety"
        assert len(result.facts) > 0
        assert result.confidence > 0
        assert len(result.sources_used) > 0

    def test_should_research_without_providers(self, config, llm_provider):
        agent = DomainAgent(config=config, llm=llm_provider)
        result = agent.research("SDS Upload")

        assert result.topic == "SDS Upload"
        assert len(result.facts) > 0

    def test_should_include_sources_from_providers(
        self, config, knowledge_provider, llm_provider
    ):
        agent = DomainAgent(
            config=config, llm=llm_provider, knowledge=knowledge_provider
        )
        result = agent.research("SDS")

        assert "outline" in result.sources_used

    def test_should_log_llm_call(self, config, llm_provider):
        agent = DomainAgent(config=config, llm=llm_provider)
        agent.research("test topic")

        assert len(llm_provider.call_log) == 1
        assert llm_provider.call_log[0]["action_code"] == "reflex.domain-research"


class TestDomainAgentInterview:
    """Test expert interview generation (Zirkel 0, Phase 3)."""

    def test_should_generate_questions_for_gaps(
        self, config, llm_provider
    ):
        agent = DomainAgent(config=config, llm=llm_provider)
        research = agent.research("SDS")

        assert research.has_gaps
        questions = agent.generate_interview(research)

        assert len(questions) > 0
        assert questions[0].question
        assert questions[0].category
        assert questions[0].priority in ("high", "medium", "low")

    def test_should_skip_interview_when_no_gaps(self, config, llm_provider):
        llm_provider.set_response(
            "reflex.domain-research",
            '{"facts": ["alles bekannt"], "gaps": [], "contradictions": [], "confidence": 0.95}',
        )
        agent = DomainAgent(config=config, llm=llm_provider)
        research = agent.research("bekanntes Thema")

        assert not research.has_gaps
        questions = agent.generate_interview(research)
        assert len(questions) == 0


class TestDomainAgentKBDistill:
    """Test KB distillation (Zirkel 0, Phase 5)."""

    def test_should_distill_kb_from_research(self, config, llm_provider):
        agent = DomainAgent(config=config, llm=llm_provider)
        research = agent.research("SDS")

        kb = agent.distill_kb(research)

        assert kb.hub_name == "test-hub"
        assert kb.vertical == "chemical_safety"
        assert "SDS" in kb.glossary
        assert len(kb.required_fields) > 0
        assert len(kb.invariants) > 0
        assert kb.markdown

    def test_should_include_expert_answers(self, config, llm_provider):
        agent = DomainAgent(config=config, llm=llm_provider)
        research = agent.research("SDS")

        kb = agent.distill_kb(
            research,
            expert_answers={"Welche Felder?": "CAS, Name, GHS-Kategorie"},
        )

        assert kb.markdown


class TestNormalizeStringList:
    """Test _normalize_string_list helper."""

    def test_should_pass_through_strings(self):
        result = DomainAgent._normalize_string_list(["fact 1", "fact 2"])
        assert result == ["fact 1", "fact 2"]

    def test_should_extract_text_from_dicts(self):
        items = [
            {"id": 1, "text": "Zone 0 ist gefährlich", "source": "ATEX"},
            {"id": 2, "text": "Zone 1 ist gelegentlich", "source": "ATEX"},
        ]
        result = DomainAgent._normalize_string_list(items)
        assert result == ["Zone 0 ist gefährlich", "Zone 1 ist gelegentlich"]

    def test_should_handle_mixed_list(self):
        items = ["plain string", {"text": "dict text"}, 42]
        result = DomainAgent._normalize_string_list(items)
        assert result == ["plain string", "dict text", "42"]

    def test_should_handle_empty_list(self):
        assert DomainAgent._normalize_string_list([]) == []

    def test_should_fallback_to_str_for_unknown_dicts(self):
        items = [{"unknown_key": "value"}]
        result = DomainAgent._normalize_string_list(items)
        assert len(result) == 1
        assert "unknown_key" in result[0]


class TestDomainAgentValidation:
    """Test UC validation (Zirkel 0, Phase 4/6)."""

    def test_should_validate_uc_against_kb(self, config, llm_provider):
        agent = DomainAgent(config=config, llm=llm_provider)
        research = agent.research("SDS")
        kb = agent.distill_kb(research)

        uc_text = """
        Akteur: SDS-Prüfer
        Ziel: Neues Sicherheitsdatenblatt hochladen
        Vorbedingung: Benutzer ist eingeloggt als Prüfer
        1. Prüfer klickt auf "Neues SDS"
        2. Prüfer wählt PDF-Datei aus
        3. System extrahiert CAS-Nummer
        Akzeptanzkriterium 1: PDF wird akzeptiert
        Akzeptanzkriterium 2: CAS-Nummer wird angezeigt
        Fehlerfall: Ungültiges PDF → Fehlermeldung
        Scope: Nicht enthalten: Bulk-Upload
        """

        result = agent.validate_uc(uc_text, kb)
        assert result.valid
        assert len(result.violations) == 0
