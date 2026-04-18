"""Tests for reflex.types — dataclasses, enums, and computed properties."""

from __future__ import annotations

import pytest

from reflex.types import (
    ClassifyResult,
    DomainResearchResult,
    FailureType,
    KnowledgeEntry,
    QualityCriterion,
    SDSData,
    Severity,
    TestRunResult,
    UCQualityResult,
    UCStatus,
    WebPage,
)


class TestEnums:
    """Test StrEnum values."""

    def test_should_have_uc_status_values(self):
        assert UCStatus.DRAFT == "draft"
        assert UCStatus.IN_REVIEW == "in_review"
        assert UCStatus.APPROVED == "approved"

    def test_should_have_failure_type_values(self):
        assert FailureType.UI_PROBLEM == "ui_problem"
        assert FailureType.UC_PROBLEM == "uc_problem"

    def test_should_have_severity_values(self):
        assert Severity.CRITICAL == "critical"
        assert Severity.HIGH == "high"
        assert Severity.MEDIUM == "medium"
        assert Severity.LOW == "low"


class TestUCQualityResult:
    """Test UCQualityResult computed properties."""

    def test_should_calculate_score_percent_all_passed(self):
        criteria = [
            QualityCriterion(name=f"C-{i:02d}", description=f"test-{i}", passed=True, evidence="OK")
            for i in range(11)
        ]
        result = UCQualityResult(uc_slug="UC-001", criteria=criteria, overall_score=11, passed=True)
        assert result.score_percent == 100

    def test_should_calculate_score_percent_partial(self):
        criteria = [
            QualityCriterion(name="a", description="d1", passed=True, evidence="OK"),
            QualityCriterion(name="b", description="d2", passed=False, evidence="Fail"),
        ]
        result = UCQualityResult(uc_slug="UC-001", criteria=criteria, overall_score=1, passed=False)
        assert result.score_percent == 50

    def test_should_calculate_score_percent_zero(self):
        result = UCQualityResult(uc_slug="UC-001", criteria=[], overall_score=0, passed=False)
        assert result.score_percent == 0

    def test_should_return_failed_criteria(self):
        criteria = [
            QualityCriterion(name="a", description="d1", passed=True, evidence="OK"),
            QualityCriterion(name="b", description="d2", passed=False, evidence="Fail"),
            QualityCriterion(name="c", description="d3", passed=False, evidence="Fail"),
        ]
        result = UCQualityResult(uc_slug="UC-001", criteria=criteria, overall_score=1, passed=False)
        failed = result.failed_criteria
        assert len(failed) == 2
        assert failed[0].name == "b"
        assert failed[1].name == "c"


class TestTestRunResult:
    """Test TestRunResult computed properties."""

    def test_should_calculate_total(self):
        result = TestRunResult(passed=8, failed=2, errors=1, duration_seconds=1.5)
        assert result.total == 11

    def test_should_detect_all_passed(self):
        result = TestRunResult(passed=10, failed=0, errors=0, duration_seconds=0.5)
        assert result.all_passed is True

    def test_should_detect_not_all_passed(self):
        result = TestRunResult(passed=8, failed=2, errors=0, duration_seconds=0.5)
        assert result.all_passed is False

    def test_should_detect_errors_as_not_passed(self):
        result = TestRunResult(passed=10, failed=0, errors=1, duration_seconds=0.5)
        assert result.all_passed is False


class TestDomainResearchResult:
    """Test DomainResearchResult computed properties."""

    def test_should_detect_gaps(self):
        result = DomainResearchResult(
            topic="ATEX zones",
            vertical="chemistry",
            facts=[],
            gaps=["Missing SDS data"],
            contradictions=[],
            sources_used=[],
            confidence=0.7,
        )
        assert result.has_gaps is True

    def test_should_detect_no_gaps(self):
        result = DomainResearchResult(
            topic="ATEX zones",
            vertical="chemistry",
            facts=[],
            gaps=[],
            contradictions=[],
            sources_used=[],
            confidence=0.95,
        )
        assert result.has_gaps is False


class TestDataclassCreation:
    """Test dataclass instantiation and defaults."""

    def test_should_create_sds_data_minimal(self):
        sds = SDSData(substance_name="Acetone")
        assert sds.substance_name == "Acetone"
        assert sds.cas_number == ""
        assert sds.flash_point == ""

    def test_should_create_web_page(self):
        page = WebPage(url="https://example.com", title="Test", text="content")
        assert page.url == "https://example.com"
        assert page.html == ""
        assert page.status_code == 200

    def test_should_create_knowledge_entry(self):
        entry = KnowledgeEntry(title="ATEX", content="Explosive Atmospheres directive")
        assert entry.title == "ATEX"
        assert entry.source == ""

    def test_should_create_classify_result(self):
        result = ClassifyResult(
            failure_type=FailureType.UI_PROBLEM,
            confidence=0.9,
            reasoning="Element not visible",
            suggested_action="Fix selector",
        )
        assert result.failure_type == FailureType.UI_PROBLEM
        assert result.confidence == 0.9
