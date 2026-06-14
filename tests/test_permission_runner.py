"""Tests for reflex.permission_runner — PermissionRunner."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from reflex.permission_runner import PermissionReport, PermissionRunner, ReflexTestUser
from reflex.types import PermissionTestResult

SAMPLE_YAML = """\
hub_name: test-hub
vertical: chemical_safety

test_users:
  admin:
    username: admin
    password: admin123
    org_role: owner
    is_staff: true
    is_superuser: true
  viewer:
    username: viewer
    password: viewer123
    org_role: member
    is_staff: false

permissions_matrix:
  /livez/:
    anonymous: 200
    admin: 200
    viewer: 200
  /dashboard/:
    anonymous: 302
    admin: 200
    viewer: 200
  /admin/:
    anonymous: 302
    admin: 200
    viewer: 403

dev_cycle:
  base_url: http://localhost:8000
  login_url: /accounts/login/
"""


class TestPermissionRunnerInit:
    """Test PermissionRunner initialization."""

    def test_should_create_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        runner = PermissionRunner.from_yaml(yaml_file)
        assert runner.base_url == "http://localhost:8000"
        assert "admin" in runner.test_users
        assert "viewer" in runner.test_users
        assert len(runner.permissions_matrix) == 3

    def test_should_parse_test_users(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        runner = PermissionRunner.from_yaml(yaml_file)
        admin = runner.test_users["admin"]
        assert admin.username == "admin"
        assert admin.password == "admin123"
        assert admin.is_superuser is True

    def test_should_parse_permissions_matrix(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        runner = PermissionRunner.from_yaml(yaml_file)
        assert runner.permissions_matrix["/livez/"]["anonymous"] == 200
        assert runner.permissions_matrix["/dashboard/"]["anonymous"] == 302
        assert runner.permissions_matrix["/admin/"]["viewer"] == 403

    def test_should_raise_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            PermissionRunner.from_yaml("/nonexistent/reflex.yaml")

    def test_should_override_base_url(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text(SAMPLE_YAML)

        runner = PermissionRunner.from_yaml(yaml_file, base_url="http://custom:9000")
        assert runner.base_url == "http://custom:9000"


class TestPermissionReport:
    """Test PermissionReport data class."""

    def test_should_calculate_pass_rate(self):
        report = PermissionReport(
            results=[
                PermissionTestResult(url="/a", role="admin", expected_status=200, actual_status=200),
                PermissionTestResult(url="/b", role="admin", expected_status=200, actual_status=403),
            ],
            total=2,
            passed=1,
            failed=1,
        )
        assert report.pass_rate == 50.0
        assert not report.all_passed

    def test_should_filter_failures(self):
        report = PermissionReport(
            results=[
                PermissionTestResult(url="/a", role="admin", expected_status=200, actual_status=200),
                PermissionTestResult(url="/b", role="admin", expected_status=200, actual_status=403),
                PermissionTestResult(url="/c", role="viewer", expected_status=302, actual_status=200),
            ],
            total=3,
            passed=1,
            failed=2,
        )
        failures = report.failures_only()
        assert len(failures) == 2
        assert failures[0].url == "/b"
        assert failures[1].url == "/c"

    def test_should_report_all_passed(self):
        report = PermissionReport(total=3, passed=3, failed=0)
        assert report.all_passed

    def test_should_handle_empty_report(self):
        report = PermissionReport()
        assert report.all_passed
        assert report.pass_rate == 0.0


class TestReflexTestUser:
    """Test ReflexTestUser data class."""

    def test_should_create_with_defaults(self):
        user = ReflexTestUser(username="test", password="test123")
        assert user.org_role == ""
        assert user.is_staff is False
        assert user.is_superuser is False


class TestPermissionRunnerHelpers:
    """Test helper methods."""

    def test_should_extract_csrf_from_html(self):
        class FakeResponse:
            cookies = {}
            text = '<input name="csrfmiddlewaretoken" value="abc123token">'

        token = PermissionRunner._extract_csrf_token(FakeResponse())
        assert token == "abc123token"

    def test_should_extract_csrf_from_cookie(self):
        class FakeResponse:
            cookies = {"csrftoken": "cookie_token"}
            text = ""

        token = PermissionRunner._extract_csrf_token(FakeResponse())
        assert token == "cookie_token"

    def test_should_return_empty_when_no_csrf(self):
        class FakeResponse:
            cookies = {}
            text = "<html>no token here</html>"

        token = PermissionRunner._extract_csrf_token(FakeResponse())
        assert token == ""


class TestPermissionRunnerOutput:
    """Test report output methods."""

    def test_should_generate_json(self):
        import json

        report = PermissionReport(
            base_url="http://localhost:8000",
            results=[
                PermissionTestResult(url="/a", role="admin", expected_status=200, actual_status=200),
            ],
            total=1,
            passed=1,
            failed=0,
        )
        output = PermissionRunner.to_json(report)
        data = json.loads(output)
        assert data["total"] == 1
        assert data["passed"] == 1
        assert data["results"][0]["url"] == "/a"

    def test_print_report_should_not_raise(self):
        # Regression: trailing logger.info() with no args raised TypeError.
        report = PermissionReport(
            base_url="http://x",
            results=[PermissionTestResult(url="/a", role="admin", expected_status=200, actual_status=403)],
            total=1,
            passed=0,
            failed=1,
        )
        PermissionRunner.print_report(report)


def _user(name: str = "admin") -> ReflexTestUser:
    return ReflexTestUser(username=name, password=f"{name}123")


class TestFromYamlStatusParsing:
    def test_should_parse_string_status_with_comment(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text('permissions_matrix:\n  /x/:\n    anonymous: "200  # ok"\n')
        runner = PermissionRunner.from_yaml(yaml_file)
        assert runner.permissions_matrix["/x/"]["anonymous"] == 200

    def test_should_drop_non_numeric_string_status(self, tmp_path):
        yaml_file = tmp_path / "reflex.yaml"
        yaml_file.write_text('permissions_matrix:\n  /x/:\n    anonymous: "n/a"\n')
        runner = PermissionRunner.from_yaml(yaml_file)
        assert "anonymous" not in runner.permissions_matrix["/x/"]


class TestRunAll:
    def test_should_aggregate_anonymous_and_authenticated(self):
        runner = PermissionRunner(
            base_url="http://x",
            test_users={"admin": _user()},
            permissions_matrix={"/a": {"anonymous": 200, "admin": 200}},
        )
        with (
            patch.object(runner, "_test_anonymous", return_value=200),
            patch.object(runner, "_create_authenticated_session", return_value=MagicMock()),
            patch.object(runner, "_test_authenticated", return_value=200),
        ):
            report = runner.run_all()
        assert report.total == 2
        assert report.passed == 2
        assert report.all_passed

    def test_should_reuse_session_across_urls(self):
        runner = PermissionRunner(
            base_url="http://x",
            test_users={"admin": _user()},
            permissions_matrix={"/a": {"admin": 200}, "/b": {"admin": 200}},
        )
        with (
            patch.object(runner, "_create_authenticated_session", return_value=MagicMock()) as mk_sess,
            patch.object(runner, "_test_authenticated", return_value=200),
        ):
            runner.run_all()
        mk_sess.assert_called_once()

    def test_should_skip_role_when_session_creation_fails(self):
        runner = PermissionRunner(
            base_url="http://x",
            test_users={},
            permissions_matrix={"/a": {"admin": 200}},
        )
        with patch.object(runner, "_create_authenticated_session", return_value=None):
            report = runner.run_all()
        assert report.total == 0

    def test_should_count_failures(self):
        runner = PermissionRunner(
            base_url="http://x",
            test_users={},
            permissions_matrix={"/a": {"anonymous": 200}},
        )
        with patch.object(runner, "_test_anonymous", return_value=403):
            report = runner.run_all()
        assert report.failed == 1
        assert not report.all_passed

    def test_should_raise_when_httpx_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "httpx", None)
        runner = PermissionRunner(base_url="http://x", test_users={}, permissions_matrix={"/a": {"anonymous": 200}})
        with pytest.raises(ImportError):
            runner.run_all()


class TestAnonymousAndAuthenticatedRequests:
    def test_should_return_status_for_anonymous(self):
        runner = PermissionRunner("http://x", {}, {})
        httpx_mod = MagicMock()
        client = MagicMock()
        client.get.return_value = MagicMock(status_code=200)
        httpx_mod.Client.return_value.__enter__.return_value = client
        assert runner._test_anonymous("/a", httpx_mod) == 200

    def test_should_return_zero_on_anonymous_error(self):
        runner = PermissionRunner("http://x", {}, {})
        httpx_mod = MagicMock()
        httpx_mod.Client.side_effect = RuntimeError("boom")
        assert runner._test_anonymous("/a", httpx_mod) == 0

    def test_should_return_status_for_authenticated(self):
        runner = PermissionRunner("http://x", {}, {})
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=403)
        assert runner._test_authenticated("/a", session) == 403

    def test_should_return_zero_on_authenticated_error(self):
        runner = PermissionRunner("http://x", {}, {})
        session = MagicMock()
        session.get.side_effect = RuntimeError("boom")
        assert runner._test_authenticated("/a", session) == 0


class TestCreateAuthenticatedSession:
    def _httpx_with_session(self, csrf="tok", login_status=302):
        httpx_mod = MagicMock()
        session = MagicMock()
        httpx_mod.Client.return_value = session
        login_resp = MagicMock(text="")
        login_resp.cookies.get.return_value = csrf
        session.get.return_value = login_resp
        session.post.return_value = MagicMock(status_code=login_status)
        return httpx_mod, session

    def test_should_return_none_without_user(self):
        runner = PermissionRunner("http://x", {}, {})
        assert runner._create_authenticated_session("ghost", MagicMock()) is None

    def test_should_create_session_on_successful_login(self):
        runner = PermissionRunner("http://x", {"admin": _user()}, {})
        httpx_mod, session = self._httpx_with_session()
        assert runner._create_authenticated_session("admin", httpx_mod) is session
        session.post.assert_called_once()

    def test_should_return_none_when_no_csrf(self):
        runner = PermissionRunner("http://x", {"admin": _user()}, {})
        httpx_mod, session = self._httpx_with_session(csrf="")
        assert runner._create_authenticated_session("admin", httpx_mod) is None
        session.close.assert_called_once()

    def test_should_return_none_on_login_failure_status(self):
        runner = PermissionRunner("http://x", {"admin": _user()}, {})
        httpx_mod, session = self._httpx_with_session(login_status=401)
        assert runner._create_authenticated_session("admin", httpx_mod) is None
        session.close.assert_called_once()

    def test_should_return_none_on_exception(self):
        runner = PermissionRunner("http://x", {"admin": _user()}, {})
        httpx_mod = MagicMock()
        httpx_mod.Client.side_effect = RuntimeError("boom")
        assert runner._create_authenticated_session("admin", httpx_mod) is None
