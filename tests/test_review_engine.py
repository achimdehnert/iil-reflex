"""Tests for reflex.review.engine — ReviewEngine, plugin discovery, baseline, suppression."""

from __future__ import annotations

from pathlib import Path

from reflex.review.engine import (
    ReviewEngine,
    _discover_plugins,
    _load_baseline,
    _load_suppressions,
    _save_baseline,
    run_review,
)
from reflex.review.types import Finding, ReviewSeverity


class TestPluginDiscovery:
    def test_should_discover_builtin_plugins(self):
        plugins = _discover_plugins()
        assert "repo" in plugins
        assert "compose" in plugins
        assert "adr" in plugins
        assert "port" in plugins

    def test_should_have_at_least_4_plugins(self):
        plugins = _discover_plugins()
        assert len(plugins) >= 4


class TestReviewEngine:
    def test_should_list_available_plugins(self):
        engine = ReviewEngine()
        assert "repo" in engine.available_plugins
        assert "compose" in engine.available_plugins

    def test_should_run_repo_plugin_on_real_repo(self):
        """Run repo plugin on iil-reflex itself."""
        engine = ReviewEngine()
        results = engine.run(repo="iil-reflex", types=["repo"])
        assert len(results) == 1
        assert results[0].review_type == "repo"
        assert results[0].repo == "iil-reflex"
        assert results[0].duration_s >= 0

    def test_should_return_empty_for_unknown_plugin(self):
        engine = ReviewEngine()
        results = engine.run(repo="iil-reflex", types=["nonexistent_plugin"])
        assert results == []

    def test_should_run_all_plugins(self):
        engine = ReviewEngine()
        results = engine.run(repo="iil-reflex")
        assert len(results) >= 4


class TestBaseline:
    def test_should_save_and_load_baseline(self, tmp_path: Path):
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        findings = [
            Finding(rule_id="a.test", severity=ReviewSeverity.WARN, message="msg1"),
            Finding(rule_id="b.test", severity=ReviewSeverity.BLOCK, message="msg2"),
        ]

        baseline_file = _save_baseline(repo_path, findings)
        assert baseline_file.exists()

        baseline_ids = _load_baseline(repo_path)
        assert baseline_ids == {"a.test", "b.test"}

    def test_should_return_empty_when_no_baseline(self, tmp_path: Path):
        assert _load_baseline(tmp_path) == set()


class TestSuppression:
    def test_should_load_suppressions(self, tmp_path: Path):
        repo_path = tmp_path / "test-repo"
        supp_dir = repo_path / ".reflex"
        supp_dir.mkdir(parents=True)
        supp_file = supp_dir / "suppressions.yaml"
        supp_file.write_text(
            "suppressions:\n"
            '  - rule_id: compose.no_logging_config\n'
            '    reason: "Logging via Loki geplant"\n'
            '    permanent: true\n',
            encoding="utf-8",
        )

        entries = _load_suppressions(repo_path)
        assert len(entries) == 1
        assert entries[0].rule_id == "compose.no_logging_config"
        assert entries[0].permanent is True

    def test_should_return_empty_when_no_suppressions(self, tmp_path: Path):
        assert _load_suppressions(tmp_path) == []


class TestEngineFiltering:
    def test_should_filter_suppressed_findings(self, tmp_path: Path):
        """Engine should exclude suppressed rule_ids."""
        # Create a minimal repo structure
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Create suppressions
        supp_dir = repo_path / ".reflex"
        supp_dir.mkdir()
        supp_file = supp_dir / "suppressions.yaml"
        supp_file.write_text(
            "suppressions:\n"
            '  - rule_id: repo.missing_readme\n'
            '    reason: "Intentional"\n'
            '    permanent: true\n',
            encoding="utf-8",
        )

        engine = ReviewEngine(github_dir=tmp_path)
        results = engine.run(repo="test-repo", types=["repo"])

        # repo.missing_readme should be suppressed
        for result in results:
            for f in result.findings:
                assert f.rule_id != "repo.missing_readme"

    def test_should_filter_baseline_findings(self, tmp_path: Path):
        """Engine should exclude baseline rule_ids on subsequent runs."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        # Save baseline with specific rule_ids
        _save_baseline(
            repo_path,
            [
                Finding(rule_id="repo.missing_readme", severity=ReviewSeverity.BLOCK, message="m"),
                Finding(
                    rule_id="repo.missing_gitignore",
                    severity=ReviewSeverity.BLOCK, message="m",
                ),
            ],
        )

        engine = ReviewEngine(github_dir=tmp_path)
        results = engine.run(repo="test-repo", types=["repo"])

        # Baseline findings should be excluded
        for result in results:
            rule_ids = {f.rule_id for f in result.findings}
            assert "repo.missing_readme" not in rule_ids
            assert "repo.missing_gitignore" not in rule_ids

    def test_should_include_baseline_when_requested(self, tmp_path: Path):
        """Engine should include baseline findings when include_baseline=True."""
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        _save_baseline(
            repo_path,
            [Finding(rule_id="repo.missing_readme", severity=ReviewSeverity.BLOCK, message="m")],
        )

        engine = ReviewEngine(github_dir=tmp_path)
        results = engine.run(repo="test-repo", types=["repo"], include_baseline=True)

        # Should include repo.missing_readme this time
        all_rule_ids = {f.rule_id for r in results for f in r.findings}
        assert "repo.missing_readme" in all_rule_ids


class TestRunReview:
    def test_should_work_as_convenience_function(self):
        results = run_review(repo="iil-reflex", types=["repo"])
        assert len(results) == 1
        assert results[0].review_type == "repo"
