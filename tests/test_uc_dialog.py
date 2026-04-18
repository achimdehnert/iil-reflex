"""Tests for reflex.uc_dialog — UCDialogEngine."""

from __future__ import annotations

import pytest

from reflex.config import ReflexConfig
from reflex.providers import MockLLMProvider
from reflex.uc_dialog import UCDialogEngine, UCDialogState


@pytest.fixture
def config() -> ReflexConfig:
    return ReflexConfig.from_dict({
        "hub_name": "test-hub",
        "vertical": "chemical_safety",
        "domain_keywords": ["SDS", "CAS", "GHS"],
        "quality": {
            "min_acceptance_criteria": 2,
            "max_uc_steps": 7,
        },
    })


@pytest.fixture
def llm() -> MockLLMProvider:
    return MockLLMProvider({
        "reflex.uc-dialog-generate": (
            "## Akteur\n\n"
            "Der Sicherheitsingenieur\n\n"
            "## Ziel\n\n"
            "Der Sicherheitsingenieur möchte ein SDS hochladen, damit die Gefahrstoffe "
            "korrekt erfasst werden.\n\n"
            "## Vorbedingung\n\n"
            "- Der Benutzer ist eingeloggt\n"
            "- Der Benutzer hat die Rolle Sicherheitsingenieur\n\n"
            "## Scope\n\n"
            "Nur SDS-Upload und Validierung. Nicht Teil: GHS-Einstufung, Export.\n\n"
            "## Schritte\n\n"
            "1. Der Sicherheitsingenieur navigiert zum SDS-Upload\n"
            "2. Der Sicherheitsingenieur wählt eine PDF-Datei aus\n"
            "3. Das System validiert das SDS-Format\n"
            "4. Das System extrahiert CAS-Nummer und H-Sätze\n"
            "5. Das System zeigt die extrahierten Daten an\n\n"
            "## Fehlerfälle\n\n"
            "- Falls die Datei kein PDF ist, erscheint die Meldung 'Nur PDF-Dateien erlaubt'\n"
            "- Falls die CAS-Nummer ungültig ist, wird eine Warnung angezeigt\n\n"
            "## Akzeptanzkriterien\n\n"
            "GIVEN ein eingeloggter Sicherheitsingenieur\n"
            "WHEN er ein gültiges SDS-PDF hochlädt\n"
            "THEN werden CAS-Nummer und H-Sätze extrahiert und angezeigt\n\n"
            "GIVEN ein ungültiges Dateiformat\n"
            "WHEN der Upload gestartet wird\n"
            "THEN erscheint eine Fehlermeldung\n"
        ),
        "reflex.uc-dialog-refine": (
            "## Akteur\n\n"
            "Der Sicherheitsingenieur\n\n"
            "## Ziel\n\n"
            "Der Sicherheitsingenieur möchte ein SDS hochladen, damit die Gefahrstoffe "
            "korrekt erfasst werden.\n\n"
            "## Vorbedingung\n\n"
            "- Der Benutzer ist eingeloggt\n"
            "- Der Benutzer hat die Rolle Sicherheitsingenieur\n\n"
            "## Scope\n\n"
            "Nur SDS-Upload und Validierung. Nicht Teil: GHS-Einstufung, Export.\n\n"
            "## Schritte\n\n"
            "1. Der Sicherheitsingenieur navigiert zum SDS-Upload\n"
            "2. Der Sicherheitsingenieur wählt eine PDF-Datei aus\n"
            "3. Das System validiert das SDS-Format\n"
            "4. Das System extrahiert CAS-Nummer und H-Sätze\n"
            "5. Das System zeigt die extrahierten Daten an\n\n"
            "## Fehlerfälle\n\n"
            "- Falls die Datei kein PDF ist, erscheint die Meldung 'Nur PDF-Dateien erlaubt'\n"
            "- Falls die CAS-Nummer ungültig ist, wird eine Warnung angezeigt\n\n"
            "## Akzeptanzkriterien\n\n"
            "GIVEN ein eingeloggter Sicherheitsingenieur\n"
            "WHEN er ein gültiges SDS-PDF hochlädt\n"
            "THEN werden CAS-Nummer und H-Sätze extrahiert und angezeigt\n\n"
            "GIVEN ein ungültiges Dateiformat\n"
            "WHEN der Upload gestartet wird\n"
            "THEN erscheint eine Fehlermeldung\n"
        ),
    })


class TestUCDialogEngineInit:
    """Test UCDialogEngine initialization."""

    def test_should_create_engine_without_llm(self, config):
        engine = UCDialogEngine(config=config)
        assert engine.llm is None
        assert engine.max_iterations == 5

    def test_should_create_engine_with_llm(self, config, llm):
        engine = UCDialogEngine(config=config, llm=llm)
        assert engine.llm is not None


class TestUCDialogStart:
    """Test UCDialogEngine.start() — initial skeleton generation."""

    def test_should_generate_template_without_llm(self, config):
        engine = UCDialogEngine(config=config)
        state = engine.start("SDS hochladen")

        assert state.topic == "SDS hochladen"
        assert state.iteration == 1
        assert "## Akteur" in state.uc_text
        assert "## Ziel" in state.uc_text
        assert "## Schritte" in state.uc_text
        assert state.quality_result is not None

    def test_should_generate_via_llm(self, config, llm):
        engine = UCDialogEngine(config=config, llm=llm)
        state = engine.start("SDS hochladen")

        assert "Sicherheitsingenieur" in state.uc_text
        assert state.quality_result is not None
        assert len(llm.call_log) == 1
        assert llm.call_log[0]["action_code"] == "reflex.uc-dialog-generate"

    def test_should_run_quality_check_on_start(self, config, llm):
        engine = UCDialogEngine(config=config, llm=llm)
        state = engine.start("SDS hochladen")

        assert state.quality_result is not None
        assert len(state.quality_result.criteria) > 0
        assert state.quality_result.score_percent >= 0


class TestUCDialogQuestions:
    """Test get_questions() — targeted follow-ups."""

    def test_should_return_questions_for_failed_criteria(self, config):
        engine = UCDialogEngine(config=config)
        state = engine.start("SDS hochladen")

        questions = engine.get_questions(state)
        assert isinstance(questions, list)
        # Template mode should have some failed criteria
        if state.failed_criteria:
            assert len(questions) > 0
            assert "criterion" in questions[0]
            assert "question" in questions[0]

    def test_should_return_empty_when_complete(self, config, llm):
        engine = UCDialogEngine(config=config, llm=llm)
        state = engine.start("SDS hochladen")

        # Force complete
        state.quality_result._replace_passed = True  # noqa
        # Create a new quality result that's "passed"
        from reflex.types import UCQualityResult
        state.quality_result = UCQualityResult(
            uc_slug="test", passed=True, criteria=[], overall_score=1.0
        )

        questions = engine.get_questions(state)
        assert questions == []


class TestUCDialogRefine:
    """Test refine() — UC improvement with answers."""

    def test_should_refine_with_llm(self, config, llm):
        engine = UCDialogEngine(config=config, llm=llm)
        state = engine.start("SDS hochladen")

        if state.is_complete:
            # Template already passed — force a failed state for testing
            from reflex.types import QualityCriterion, UCQualityResult
            state.quality_result = UCQualityResult(
                uc_slug="test", passed=False, criteria=[
                    QualityCriterion(name="C-01: Spezifischer Akteur",
                                     description="test", passed=False),
                ]
            )

        initial_iteration = state.iteration
        state = engine.refine(state, {"C-01": "Der Laborleiter"})

        assert state.iteration == initial_iteration + 1
        assert state.quality_result is not None

    def test_should_refine_manually_without_llm(self, config):
        engine = UCDialogEngine(config=config)
        state = engine.start("SDS hochladen")

        if state.is_complete:
            from reflex.types import QualityCriterion, UCQualityResult
            state.quality_result = UCQualityResult(
                uc_slug="test", passed=False, criteria=[
                    QualityCriterion(name="C-01: Spezifischer Akteur",
                                     description="test", passed=False),
                ]
            )

        state = engine.refine(state, {"C-01": "Der Gefahrstoffbeauftragte"})
        assert state.iteration == 2

    def test_should_stop_at_max_iterations(self, config):
        engine = UCDialogEngine(config=config, max_iterations=2)
        state = engine.start("SDS hochladen")

        if state.is_complete:
            from reflex.types import QualityCriterion, UCQualityResult
            state.quality_result = UCQualityResult(
                uc_slug="test", passed=False, criteria=[
                    QualityCriterion(name="C-01: Spezifischer Akteur",
                                     description="test", passed=False),
                ]
            )

        state = engine.refine(state, {"C-01": "Test"})
        assert state.iteration == 2
        assert not state.can_iterate  # Max reached


class TestUCDialogState:
    """Test UCDialogState properties."""

    def test_should_track_completion(self):
        from reflex.types import UCQualityResult
        state = UCDialogState(topic="test")
        assert not state.is_complete

        state.quality_result = UCQualityResult(
            uc_slug="test", passed=True, criteria=[]
        )
        assert state.is_complete

    def test_should_track_iteration_limit(self):
        state = UCDialogState(topic="test", max_iterations=3)
        assert state.can_iterate

        state.iteration = 3
        assert not state.can_iterate


class TestUCDialogHelpers:
    """Test helper methods."""

    def test_should_generate_slug(self):
        slug = UCDialogEngine._topic_to_slug("SDS hochladen und validieren")
        assert slug == "uc-sds-hochladen-und-validieren"

    def test_should_clean_llm_response(self):
        text = "```markdown\n## Akteur\nDer Admin\n```"
        cleaned = UCDialogEngine._clean_llm_response(text)
        assert cleaned == "## Akteur\nDer Admin"

    def test_should_handle_plain_response(self):
        text = "## Akteur\nDer Admin"
        cleaned = UCDialogEngine._clean_llm_response(text)
        assert cleaned == text
