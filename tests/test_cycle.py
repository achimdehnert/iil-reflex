"""Tests for reflex.cycle — CycleRunner."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

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


def _passed(phase: CyclePhase) -> PhaseResult:
    return PhaseResult(phase=phase, status=PhaseStatus.PASSED)


def _failed(phase: CyclePhase, *errors: str) -> PhaseResult:
    return PhaseResult(phase=phase, status=PhaseStatus.FAILED, errors=list(errors))


class TestRunFullCycle:
    """Test the orchestration loop run_full_cycle."""

    def test_should_complete_when_all_phases_pass(self):
        runner = CycleRunner(CycleConfig(max_fix_iterations=2))
        with (
            patch.object(runner, "_run_backend_tests", return_value=_passed(CyclePhase.BACKEND_TEST)),
            patch.object(runner, "_run_frontend_verify", return_value=_passed(CyclePhase.FRONTEND_VERIFY)),
            patch.object(runner, "_run_permission_tests", return_value=_passed(CyclePhase.PERMISSION_TEST)),
        ):
            result = runner.run_full_cycle(uc_slug="UC-001")
        assert result.final_status == PhaseStatus.PASSED
        assert result.iteration == 1
        assert result.total_duration_seconds >= 0.0

    def test_should_not_run_skipped_phases(self):
        runner = CycleRunner(CycleConfig(max_fix_iterations=1))
        with (
            patch.object(runner, "_run_backend_tests") as backend,
            patch.object(runner, "_run_frontend_verify", return_value=_passed(CyclePhase.FRONTEND_VERIFY)),
            patch.object(runner, "_run_permission_tests", return_value=_passed(CyclePhase.PERMISSION_TEST)),
        ):
            result = runner.run_full_cycle(skip_phases=[CyclePhase.BACKEND_TEST])
            backend.assert_not_called()
        assert result.final_status == PhaseStatus.PASSED

    def test_should_classify_and_retry_then_fail_after_max_iterations(self):
        runner = CycleRunner(CycleConfig(max_fix_iterations=2))
        with patch.object(
            runner, "_run_backend_tests", return_value=_failed(CyclePhase.BACKEND_TEST, "FAILED test_x")
        ):
            result = runner.run_full_cycle(uc_slug="UC-001")
        # Regression: a fully failed cycle must end FAILED, not PENDING.
        assert result.final_status == PhaseStatus.FAILED
        assert result.iteration == 2
        assert any(p.phase == CyclePhase.FIX_CLASSIFY for p in result.phases)

    def test_should_retry_frontend_then_pass(self):
        runner = CycleRunner(CycleConfig(max_fix_iterations=2))
        with (
            patch.object(runner, "_run_backend_tests", return_value=_passed(CyclePhase.BACKEND_TEST)),
            patch.object(
                runner,
                "_run_frontend_verify",
                side_effect=[_failed(CyclePhase.FRONTEND_VERIFY, "x"), _passed(CyclePhase.FRONTEND_VERIFY)],
            ),
            patch.object(runner, "_run_permission_tests", return_value=_passed(CyclePhase.PERMISSION_TEST)),
        ):
            result = runner.run_full_cycle()
        assert result.final_status == PhaseStatus.PASSED
        assert result.iteration == 2

    def test_should_retry_permission_then_pass(self):
        runner = CycleRunner(CycleConfig(max_fix_iterations=2))
        with (
            patch.object(runner, "_run_backend_tests", return_value=_passed(CyclePhase.BACKEND_TEST)),
            patch.object(runner, "_run_frontend_verify", return_value=_passed(CyclePhase.FRONTEND_VERIFY)),
            patch.object(
                runner,
                "_run_permission_tests",
                side_effect=[_failed(CyclePhase.PERMISSION_TEST, "x"), _passed(CyclePhase.PERMISSION_TEST)],
            ),
        ):
            result = runner.run_full_cycle()
        assert result.final_status == PhaseStatus.PASSED
        assert result.iteration == 2

    def test_should_fail_on_frontend_failure_at_last_iteration(self):
        runner = CycleRunner(CycleConfig(max_fix_iterations=1))
        with (
            patch.object(runner, "_run_backend_tests", return_value=_passed(CyclePhase.BACKEND_TEST)),
            patch.object(
                runner, "_run_frontend_verify", return_value=_failed(CyclePhase.FRONTEND_VERIFY, "/x 500")
            ),
        ):
            result = runner.run_full_cycle()
        assert result.final_status == PhaseStatus.FAILED


class TestRunSinglePhase:
    def test_should_skip_phase_without_runner(self):
        runner = CycleRunner(CycleConfig())
        result = runner.run_single_phase(CyclePhase.DOMAIN_RESEARCH)
        assert result.status == PhaseStatus.SKIPPED
        assert "No runner" in result.output


class TestBackendTestErrors:
    def test_should_fail_on_timeout(self):
        runner = CycleRunner(CycleConfig(backend_test_cmd="sleep 999"))
        with patch("reflex.cycle.subprocess.run", side_effect=subprocess.TimeoutExpired("sleep", 300)):
            result = runner._run_backend_tests()
        assert result.status == PhaseStatus.FAILED
        assert "timed out" in result.errors[0]

    def test_should_fail_on_command_not_found(self):
        runner = CycleRunner(CycleConfig(backend_test_cmd="nonexistent-xyz"))
        with patch("reflex.cycle.subprocess.run", side_effect=FileNotFoundError("nonexistent-xyz")):
            result = runner._run_backend_tests()
        assert result.status == PhaseStatus.FAILED
        assert "not found" in result.errors[0].lower()


class TestFrontendVerify:
    def test_should_skip_when_httpx_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "httpx", None)
        runner = CycleRunner(CycleConfig())
        result = runner._run_frontend_verify()
        assert result.status == PhaseStatus.SKIPPED

    def _client_cm(self, status_code: int):
        client = MagicMock()
        client.get.return_value = MagicMock(status_code=status_code)
        cm = MagicMock()
        cm.__enter__.return_value = client
        return cm, client

    def test_should_pass_when_routes_return_expected(self):
        config = CycleConfig(routes=[{"url": "/health", "expect": 200, "auth": False}])
        runner = CycleRunner(config)
        cm, _client = self._client_cm(200)
        with patch("httpx.Client", return_value=cm), patch.object(runner, "_login_session", return_value=None):
            result = runner._run_frontend_verify()
        assert result.status == PhaseStatus.PASSED
        assert result.metrics["routes_ok"] == 1

    def test_should_fail_on_status_mismatch(self):
        config = CycleConfig(routes=[{"url": "/admin", "expect": 200, "auth": False, "label": "Admin"}])
        runner = CycleRunner(config)
        cm, _client = self._client_cm(403)
        with patch("httpx.Client", return_value=cm), patch.object(runner, "_login_session", return_value=None):
            result = runner._run_frontend_verify()
        assert result.status == PhaseStatus.FAILED
        assert "Admin" in result.errors[0]

    def test_should_skip_routes_with_empty_url(self):
        config = CycleConfig(routes=[{"url": "", "expect": 200}])
        runner = CycleRunner(config)
        cm, _client = self._client_cm(200)
        with patch("httpx.Client", return_value=cm), patch.object(runner, "_login_session", return_value=None):
            result = runner._run_frontend_verify()
        assert result.metrics["routes_checked"] == 0

    def test_should_use_session_for_auth_routes(self):
        config = CycleConfig(routes=[{"url": "/dash", "expect": 200, "auth": True}])
        runner = CycleRunner(config)
        cm, _client = self._client_cm(200)
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=200)
        with patch("httpx.Client", return_value=cm), patch.object(runner, "_login_session", return_value=session):
            result = runner._run_frontend_verify()
        session.get.assert_called_once()
        assert result.status == PhaseStatus.PASSED


class TestPermissionTests:
    def _runner_with_report(self, report):
        runner = CycleRunner(CycleConfig())
        mock_runner = MagicMock()
        mock_runner.run_all.return_value = report
        return runner, mock_runner

    def test_should_pass_when_all_permissions_pass(self):
        report = MagicMock(all_passed=True, passed=5, total=5, failed=0, pass_rate=1.0)
        report.failures_only.return_value = []
        runner, mock_runner = self._runner_with_report(report)
        with patch("reflex.permission_runner.PermissionRunner.from_yaml", return_value=mock_runner):
            result = runner._run_permission_tests()
        assert result.status == PhaseStatus.PASSED
        assert result.metrics["passed"] == 5

    def test_should_fail_and_collect_failures(self):
        failure = MagicMock(url="/admin", role="user", expected_status=403, actual_status=200)
        report = MagicMock(all_passed=False, passed=4, total=5, failed=1, pass_rate=0.8)
        report.failures_only.return_value = [failure]
        runner, mock_runner = self._runner_with_report(report)
        with patch("reflex.permission_runner.PermissionRunner.from_yaml", return_value=mock_runner):
            result = runner._run_permission_tests()
        assert result.status == PhaseStatus.FAILED
        assert "/admin" in result.errors[0]

    def test_should_fail_on_runner_exception(self):
        runner = CycleRunner(CycleConfig())
        with patch("reflex.permission_runner.PermissionRunner.from_yaml", side_effect=RuntimeError("boom")):
            result = runner._run_permission_tests()
        assert result.status == PhaseStatus.FAILED
        assert "boom" in result.errors[0]


class TestClassifyFailure:
    def test_should_classify_phase_errors(self):
        runner = CycleRunner(CycleConfig())
        phase = _failed(CyclePhase.BACKEND_TEST, "FAILED test_x - AssertionError")
        result = runner._classify_failure(phase)
        assert result.phase == CyclePhase.FIX_CLASSIFY
        assert result.status == PhaseStatus.PASSED
        assert result.metrics["classifications"] == 1


class TestLoginSession:
    def test_should_return_client_with_csrf_cookie(self):
        runner = CycleRunner(CycleConfig())
        client = MagicMock()
        resp = MagicMock()
        resp.cookies.get.return_value = "tok123"
        client.get.return_value = resp
        assert runner._login_session(client) is client
        client.post.assert_called_once()

    def test_should_return_none_without_csrf(self):
        runner = CycleRunner(CycleConfig())
        client = MagicMock()
        resp = MagicMock(text="<html>no token here</html>")
        resp.cookies.get.return_value = ""
        client.get.return_value = resp
        assert runner._login_session(client) is None

    def test_should_extract_csrf_from_html_when_no_cookie(self):
        runner = CycleRunner(CycleConfig())
        client = MagicMock()
        resp = MagicMock(text='<input name="csrfmiddlewaretoken" value="htmltok">')
        resp.cookies.get.return_value = ""
        client.get.return_value = resp
        assert runner._login_session(client) is client

    def test_should_return_none_on_exception(self):
        runner = CycleRunner(CycleConfig())
        client = MagicMock()
        client.get.side_effect = RuntimeError("network down")
        assert runner._login_session(client) is None


class TestPrintResult:
    def test_should_not_raise_on_failed_phases(self):
        # Regression: the trailing logger.info() with no args raised TypeError.
        result = CycleResult(
            uc_slug="UC-001",
            phases=[_failed(CyclePhase.BACKEND_TEST, "FAILED test_x")],
            final_status=PhaseStatus.FAILED,
        )
        CycleRunner.print_result(result)

    def test_should_write_report_to_stdout(self, capsys):
        # Regression: report used logger.info, which is silent without a handler.
        result = CycleResult(
            uc_slug="UC-001",
            phases=[_passed(CyclePhase.BACKEND_TEST)],
            final_status=PhaseStatus.PASSED,
        )
        CycleRunner.print_result(result)
        out = capsys.readouterr().out
        assert "REFLEX Development Cycle Report" in out
        assert "UC-001" in out
