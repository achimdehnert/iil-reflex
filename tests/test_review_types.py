"""Tests for reflex.review.types — Finding, ReviewResult, SuppressionEntry."""

from __future__ import annotations

import json

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewResult,
    ReviewSeverity,
    SuppressionEntry,
)


class TestFinding:
    def test_should_create_finding_with_defaults(self):
        f = Finding(rule_id="repo.test", severity=ReviewSeverity.BLOCK, message="test")
        assert f.rule_id == "repo.test"
        assert f.severity == ReviewSeverity.BLOCK
        assert f.auto_fixable is False
        assert f.fix_complexity == FixComplexity.MODERATE

    def test_should_serialize_to_dict(self):
        f = Finding(
            rule_id="compose.port_drift",
            severity=ReviewSeverity.BLOCK,
            message="Port mismatch",
            adr_ref="ADR-164",
            auto_fixable=True,
            fix_complexity=FixComplexity.TRIVIAL,
        )
        d = f.to_dict()
        assert d["rule_id"] == "compose.port_drift"
        assert d["severity"] == "block"
        assert d["fix_complexity"] == "trivial"
        assert d["auto_fixable"] is True

    def test_should_support_all_severity_levels(self):
        for sev in ReviewSeverity:
            f = Finding(rule_id="x", severity=sev, message="m")
            assert f.severity == sev


class TestReviewResult:
    def test_should_create_empty_result(self):
        r = ReviewResult(repo="risk-hub", review_type="repo")
        assert r.score_pct == 100.0
        assert r.has_blockers is False
        assert r.findings == []

    def test_should_count_findings_by_severity(self):
        r = ReviewResult(
            repo="risk-hub",
            review_type="repo",
            findings=[
                Finding(rule_id="a", severity=ReviewSeverity.BLOCK, message="m1"),
                Finding(rule_id="b", severity=ReviewSeverity.WARN, message="m2"),
                Finding(rule_id="c", severity=ReviewSeverity.WARN, message="m3"),
                Finding(rule_id="d", severity=ReviewSeverity.INFO, message="m4"),
            ],
        )
        assert len(r.findings_block) == 1
        assert len(r.findings_warn) == 2
        assert len(r.findings_info) == 1
        assert r.has_blockers is True

    def test_should_calculate_score(self):
        r = ReviewResult(
            repo="risk-hub",
            review_type="repo",
            findings=[
                Finding(rule_id="a", severity=ReviewSeverity.BLOCK, message="m1"),
            ],
        )
        assert r.score_pct == 0.0

        r2 = ReviewResult(
            repo="risk-hub",
            review_type="repo",
            findings=[
                Finding(rule_id="a", severity=ReviewSeverity.INFO, message="m1"),
            ],
        )
        assert r2.score_pct == 100.0

    def test_should_count_auto_fixable(self):
        r = ReviewResult(
            repo="risk-hub",
            review_type="repo",
            findings=[
                Finding(
                    rule_id="a", severity=ReviewSeverity.WARN,
                    message="m1", auto_fixable=True,
                ),
                Finding(
                    rule_id="b", severity=ReviewSeverity.WARN,
                    message="m2", auto_fixable=False,
                ),
            ],
        )
        assert len(r.findings_auto_fixable) == 1

    def test_should_serialize_to_json(self):
        r = ReviewResult(
            repo="risk-hub",
            review_type="repo",
            findings=[
                Finding(rule_id="a", severity=ReviewSeverity.BLOCK, message="m1"),
            ],
        )
        j = r.to_json()
        parsed = json.loads(j)
        assert parsed["repo"] == "risk-hub"
        assert parsed["summary"]["block"] == 1


class TestSuppressionEntry:
    def test_should_not_expire_permanent(self):
        s = SuppressionEntry(rule_id="a", reason="reason", permanent=True)
        assert s.is_expired is False

    def test_should_not_expire_without_until(self):
        s = SuppressionEntry(rule_id="a", reason="reason")
        assert s.is_expired is False

    def test_should_expire_past_date(self):
        s = SuppressionEntry(rule_id="a", reason="reason", until="2020-01-01")
        assert s.is_expired is True

    def test_should_not_expire_future_date(self):
        s = SuppressionEntry(rule_id="a", reason="reason", until="2099-01-01")
        assert s.is_expired is False

    def test_should_handle_invalid_date(self):
        s = SuppressionEntry(rule_id="a", reason="reason", until="not-a-date")
        assert s.is_expired is False
