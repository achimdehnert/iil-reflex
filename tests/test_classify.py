"""Tests for Failure Classifier — decision tree + LLM augmentation."""

import pytest

from reflex.classify import FailureClassifier
from reflex.types import FailureType


@pytest.fixture
def classifier() -> FailureClassifier:
    return FailureClassifier()


@pytest.fixture
def classifier_with_llm(llm_provider) -> FailureClassifier:
    return FailureClassifier(llm=llm_provider)


UC_TEXT = """
Akteur: SDS-Prüfer
1. Prüfer klickt auf "Neues SDS hochladen"
2. System zeigt Upload-Formular
3. Prüfer wählt PDF aus
Fehlerfall: Ungültiges PDF → Fehlermeldung sichtbar
Akzeptanzkriterium: CAS-Nummer wird angezeigt
"""


class TestInfraClassification:
    def test_should_classify_timeout(self, classifier):
        result = classifier.classify(
            test_name="test_should_show_upload_form",
            error_message="TimeoutError: page.goto timed out after 30000ms",
        )
        assert result.failure_type == FailureType.INFRA_PROBLEM

    def test_should_classify_connection_refused(self, classifier):
        result = classifier.classify(
            test_name="test_should_load_page",
            error_message="net::ERR_CONNECTION_REFUSED at http://localhost:8000",
        )
        assert result.failure_type == FailureType.INFRA_PROBLEM

    def test_should_classify_browser_closed(self, classifier):
        result = classifier.classify(
            test_name="test_any",
            error_message="Browser has been closed",
        )
        assert result.failure_type == FailureType.INFRA_PROBLEM


class TestUCProblemClassification:
    def test_should_classify_missing_criterion(self, classifier):
        result = classifier.classify(
            test_name="test_should_export_to_csv",
            error_message="AssertionError: Export button not found",
            uc_text=UC_TEXT,
        )
        assert result.failure_type == FailureType.UC_PROBLEM
        assert "nicht als AK" in result.reasoning or "nicht" in result.reasoning

    def test_should_classify_permission_error(self, classifier):
        result = classifier.classify(
            test_name="test_should_show_upload_form",
            error_message="permission denied: 403 Forbidden",
            uc_text=UC_TEXT,
        )
        assert result.failure_type == FailureType.UC_PROBLEM


class TestUIProblemClassification:
    def test_should_classify_missing_element(self, classifier):
        result = classifier.classify(
            test_name="test_should_show_upload_form",
            error_message="AssertionError: heading 'Upload' not visible",
            uc_text=UC_TEXT,
        )
        assert result.failure_type == FailureType.UI_PROBLEM

    def test_should_classify_aria_missing(self, classifier):
        result = classifier.classify(
            test_name="test_should_show_cas_nummer",
            error_message="locator role='heading' resolved to 0 elements",
            uc_text=UC_TEXT,
        )
        assert result.failure_type == FailureType.UI_PROBLEM


class TestLLMFallback:
    def test_should_use_llm_for_unknown(self, classifier_with_llm):
        # Provide UC that covers keywords so criterion_in_uc=True,
        # but error doesn't match any rule-based pattern → falls to LLM
        result = classifier_with_llm.classify(
            test_name="test_something_ambiguous",
            error_message="Some weird error nobody expected",
            uc_text="Der Admin tut something ambiguous im System",
        )
        # LLM mock returns ui_problem
        assert result.failure_type == FailureType.UI_PROBLEM

    def test_should_return_unknown_without_llm(self, classifier):
        # No UC text → UNKNOWN (can't classify without UC)
        result = classifier.classify(
            test_name="test_something_ambiguous",
            error_message="Some weird error nobody expected",
            uc_text="",
        )
        assert result.failure_type == FailureType.UNKNOWN
        assert result.confidence < 0.5


class TestConfidence:
    def test_should_have_high_confidence_for_infra(self, classifier):
        result = classifier.classify(
            test_name="test_any",
            error_message="TimeoutError",
        )
        assert result.confidence >= 0.8

    def test_should_have_medium_confidence_for_uc(self, classifier):
        result = classifier.classify(
            test_name="test_should_export_to_csv",
            error_message="Button not found",
            uc_text=UC_TEXT,
        )
        assert result.confidence >= 0.5
