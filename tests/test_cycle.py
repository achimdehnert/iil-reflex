"""Tests for reflex.cycle — CycleRunner."""

from __future__ import annotations

import pytest

from reflex.cycle import (
    CycleConfig,
    CyclePhase,
    CycleResult,
    CycleRunner,
    PhaseResult,
    PhaseStatus,
)


SAMPLE_YAML = """\
hub_name: test-hub
vertical: chemical_safety

dev_cycle:
  base_url: http://localhost:8003
  login_url: /accounts/login/
  backend_test_cmd: "echo PASSED"
  lint_cmd: "echo CLEAN"
  max_fix_iterations: 2

permissions_matrix:
  /livez/:
    anonymous: 200
"""


class TestCycleConfig:
    """Test CycleConfig loading."""

    def test_should_load_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        config = CycleConfig.from_yaml(yaml_file)
        assert config.base_url == "http://localhost:8003"
        assert config.login_url == "/accounts/login/"
        assert config.max_fix_iterations == 2
        assert "echo PASSED" in config.backend_test_cmd

    def test_should_use_defaults_without_dev_cycle(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text("hub_name: test\n")

        config = CycleConfig.from_yaml(yaml_file)
        assert config.base_url == "http://localhost:8000"
        assert config.max_fix_iterations == 3

    def test_should_raise_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            CycleConfig.from_yaml("/nonexistent/reflex.yaml")


class TestPhaseResult:
    """Test PhaseResult data class."""

    def test_should_track_passed(self):
        result = PhaseResult(
            phase=CyclePhase.BACKEND_TEST,
            status=PhaseStatus.PASSED,
        )
        assert result.passed is True

    def test_should_track_failed(self):
        result = PhaseResult(
            phase=CyclePhase.BACKEND_TEST,
            status=PhaseStatus.FAILED,
            errors=["FAILED test_something"],
        )
        assert result.passed is False
        assert len(result.errors) == 1


class TestCycleResult:
    """Test CycleResult data class."""

    def test_should_detect_all_passed(self):
        result = CycleResult(
            uc_slug="UC-001",
            phases=[
                PhaseResult(phase=CyclePhase.BACKEND_TEST, status=PhaseStatus.PASSED),
                PhaseResult(phase=CyclePhase.FRONTEND_VERIFY, status=PhaseStatus.PASSED),
            ],
        )
        assert result.all_passed is True

    def test_should_detect_failure(self):
        result = CycleResult(
            uc_slug="UC-001",
            phases=[
                PhaseResult(phase=CyclePhase.BACKEND_TEST, status=PhaseStatus.PASSED),
                PhaseResult(phase=CyclePhase.FRONTEND_VERIFY, status=PhaseStatus.FAILED),
            ],
        )
        assert result.all_passed is False
        assert len(result.failed_phases) == 1

    def test_should_allow_skipped_phases(self):
        result = CycleResult(
            uc_slug="UC-001",
            phases=[
                PhaseResult(phase=CyclePhase.BACKEND_TEST, status=PhaseStatus.PASSED),
                PhaseResult(phase=CyclePhase.FRONTEND_VERIFY, status=PhaseStatus.SKIPPED),
            ],
        )
        assert result.all_passed is True

    def test_should_generate_summary(self):
        result = CycleResult(
            uc_slug="UC-001",
            phases=[
                PhaseResult(phase=CyclePhase.BACKEND_TEST, status=PhaseStatus.PASSED, duration_seconds=2.5),
            ],
        )
        summary = result.phase_summary()
        assert "PASSED" in summary or "passed" in summary


class TestCycleRunnerBackend:
    """Test CycleRunner backend test phase."""

    def test_should_run_backend_with_echo_cmd(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        config = CycleConfig.from_yaml(yaml_file)
        runner = CycleRunner(config)

        result = runner.run_single_phase(CyclePhase.BACKEND_TEST)
        assert result.phase == CyclePhase.BACKEND_TEST
        assert result.status == PhaseStatus.PASSED

    def test_should_handle_missing_command(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text("hub_name: test\ndev_cycle:\n  backend_test_cmd: ''\n")

        config = CycleConfig.from_yaml(yaml_file)
        runner = CycleRunner(config)

        result = runner.run_single_phase(CyclePhase.BACKEND_TEST)
        assert result.status == PhaseStatus.SKIPPED


class TestCycleRunnerHelpers:
    """Test helper methods."""

    def test_should_parse_pytest_output(self):
        output = "====== 15 passed, 2 failed, 1 error in 4.32s ======"
        metrics = CycleRunner._parse_pytest_output(output)
        assert metrics.get("passed") == 15
        assert metrics.get("failed") == 2
        assert metrics.get("errors") == 1
        assert metrics.get("duration") == 4.32

    def test_should_parse_only_passed(self):
        output = "====== 42 passed in 1.23s ======"
        metrics = CycleRunner._parse_pytest_output(output)
        assert metrics.get("passed") == 42
        assert metrics.get("failed") == 0

    def test_should_extract_errors(self):
        output = "FAILED test_one - assert False\nFAILED test_two - timeout\nOK"
        errors = CycleRunner._extract_errors(output)
        assert len(errors) == 2
        assert "test_one" in errors[0]

    def test_should_handle_no_errors(self):
        output = "All tests passed"
        errors = CycleRunner._extract_errors(output)
        assert errors == []


class TestCyclePhaseEnum:
    """Test CyclePhase enum values."""

    def test_should_have_all_phases(self):
        assert CyclePhase.DOMAIN_RESEARCH == "Z0_domain_research"
        assert CyclePhase.BACKEND_TEST == "Z2_backend_test"
        assert CyclePhase.PERMISSION_TEST == "Z4_permission_test"
        assert CyclePhase.COMPLETE == "Z6_complete"
