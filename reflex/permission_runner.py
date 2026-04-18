"""
REFLEX Permission Runner — Automated permission matrix testing.

Reads test_users and permissions_matrix from reflex.yaml and executes
HTTP requests to verify access control for each route × role combination.

Supports:
    - Anonymous access testing (no login)
    - Authenticated access testing (CSRF-aware login)
    - Expected status code validation (200, 302, 403)
    - JSON and human-readable output

Architecture:
    - Pure Python with httpx (async-capable, sync default)
    - Reads config from ReflexConfig + raw YAML (test_users, permissions_matrix)
    - Returns structured PermissionTestResult objects

Usage:
    from reflex.permission_runner import PermissionRunner

    runner = PermissionRunner.from_yaml("reflex.yaml", base_url="http://localhost:8003")
    report = runner.run_all()
    runner.print_report(report)

CLI:
    python -m reflex test-permissions --config reflex.yaml --base-url http://localhost:8003
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from reflex.types import PermissionTestResult

logger = logging.getLogger(__name__)


__all__ = ["ReflexTestUser", "PermissionReport", "PermissionRunner"]


@dataclass
class ReflexTestUser:
    """Test user definition from reflex.yaml."""

    username: str
    password: str
    org_role: str = ""
    module_role: str = ""
    is_staff: bool = False
    is_superuser: bool = False


@dataclass
class PermissionReport:
    """Complete permission test report."""

    results: list[PermissionTestResult] = field(default_factory=list)
    base_url: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total * 100 if self.total > 0 else 0.0

    def failures_only(self) -> list[PermissionTestResult]:
        return [r for r in self.results if not r.passed]


class PermissionRunner:
    """Automated permission matrix tester.

    Reads test_users + permissions_matrix from reflex.yaml and
    tests each route × role combination against expected status codes.
    """

    def __init__(
        self,
        base_url: str,
        test_users: dict[str, ReflexTestUser],
        permissions_matrix: dict[str, dict[str, int]],
        login_url: str = "/accounts/login/",
        timeout: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self.test_users = test_users
        self.permissions_matrix = permissions_matrix
        self.login_url = login_url
        self.timeout = timeout

    @classmethod
    def from_yaml(
        cls,
        yaml_path: str | Path,
        base_url: str = "http://localhost:8000",
        login_url: str = "/accounts/login/",
    ) -> PermissionRunner:
        """Create PermissionRunner from reflex.yaml."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")

        with path.open() as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}

        # Parse test_users
        test_users: dict[str, ReflexTestUser] = {}
        for name, user_data in raw.get("test_users", {}).items():
            test_users[name] = ReflexTestUser(
                username=user_data.get("username", name),
                password=user_data.get("password", ""),
                org_role=user_data.get("org_role", ""),
                module_role=user_data.get("module_role", ""),
                is_staff=user_data.get("is_staff", False),
                is_superuser=user_data.get("is_superuser", False),
            )

        # Parse permissions_matrix — strip comments from values
        permissions_matrix: dict[str, dict[str, int]] = {}
        for url, roles in raw.get("permissions_matrix", {}).items():
            if isinstance(roles, dict):
                clean_roles: dict[str, int] = {}
                for role, status in roles.items():
                    if isinstance(status, int):
                        clean_roles[role] = status
                    elif isinstance(status, str):
                        # Handle "200  # comment" format
                        match = re.match(r"(\d+)", str(status))
                        if match:
                            clean_roles[role] = int(match.group(1))
                permissions_matrix[url] = clean_roles

        # Extract dev_cycle config if present (YAML defaults, caller overrides)
        dev_cycle = raw.get("dev_cycle", {})
        configured_login_url = login_url or dev_cycle.get("login_url", "/accounts/login/")
        configured_base_url = base_url or dev_cycle.get("base_url", "http://localhost:8000")

        return cls(
            base_url=configured_base_url,
            test_users=test_users,
            permissions_matrix=permissions_matrix,
            login_url=configured_login_url,
        )

    def run_all(self) -> PermissionReport:
        """Execute all permission tests and return report.

        Tests each URL × role combination from the permissions_matrix.
        """
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required for permission testing. Install: pip install httpx") from None

        report = PermissionReport(base_url=self.base_url)
        sessions: dict[str, httpx.Client] = {}

        try:
            for url, roles in sorted(self.permissions_matrix.items()):
                for role, expected_status in sorted(roles.items()):
                    if role == "anonymous":
                        actual = self._test_anonymous(url, httpx)
                    else:
                        if role not in sessions:
                            sessions[role] = self._create_authenticated_session(role, httpx)
                        session = sessions.get(role)
                        if session is None:
                            logger.warning("Could not create session for role %s — skipping", role)
                            continue
                        actual = self._test_authenticated(url, session)

                    result = PermissionTestResult(
                        url=url,
                        role=role,
                        expected_status=expected_status,
                        actual_status=actual,
                    )
                    report.results.append(result)
                    report.total += 1
                    if result.passed:
                        report.passed += 1
                    else:
                        report.failed += 1

                    icon = "✅" if result.passed else "❌"
                    logger.info(
                        "%s %s %s: expected=%d actual=%d",
                        icon,
                        role,
                        url,
                        expected_status,
                        actual,
                    )

        finally:
            for session in sessions.values():
                session.close()

        return report

    def _test_anonymous(self, url: str, httpx_mod: Any) -> int:
        """Test a URL without authentication."""
        try:
            with httpx_mod.Client(follow_redirects=False, timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}{url}")
                return resp.status_code
        except Exception as e:
            logger.error("Anonymous test failed for %s: %s", url, e)
            return 0

    def _test_authenticated(self, url: str, session: Any) -> int:
        """Test a URL with an authenticated session."""
        try:
            resp = session.get(f"{self.base_url}{url}", follow_redirects=False)
            return resp.status_code
        except Exception as e:
            logger.error("Authenticated test failed for %s: %s", url, e)
            return 0

    def _create_authenticated_session(self, role: str, httpx_mod: Any) -> Any | None:
        """Create an authenticated httpx session for a test user."""
        user = self.test_users.get(role)
        if not user:
            logger.warning("No test_user defined for role: %s", role)
            return None

        try:
            session = httpx_mod.Client(follow_redirects=False, timeout=self.timeout)

            # GET login page to obtain CSRF token
            login_resp = session.get(f"{self.base_url}{self.login_url}")
            csrf_token = self._extract_csrf_token(login_resp)

            if not csrf_token:
                logger.warning("Could not extract CSRF token for %s", role)
                session.close()
                return None

            # POST login
            login_data = {
                "username": user.username,
                "password": user.password,
                "csrfmiddlewaretoken": csrf_token,
            }
            resp = session.post(
                f"{self.base_url}{self.login_url}",
                data=login_data,
                headers={"Referer": f"{self.base_url}{self.login_url}"},
            )

            if resp.status_code in (200, 302):
                logger.info("Logged in as %s (role: %s)", user.username, role)
                return session
            else:
                logger.warning("Login failed for %s: status=%d", role, resp.status_code)
                session.close()
                return None

        except Exception as e:
            logger.error("Session creation failed for %s: %s", role, e)
            return None

    @staticmethod
    def _extract_csrf_token(response: Any) -> str:
        """Extract CSRF token from response cookies or HTML."""
        # Try cookie first
        csrf = response.cookies.get("csrftoken", "")
        if csrf:
            return csrf

        # Try HTML form
        match = re.search(
            r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)',
            response.text,
        )
        return match.group(1) if match else ""

    @staticmethod
    def print_report(report: PermissionReport) -> None:
        """Print human-readable permission test report."""
        logger.info(f"\n{'=' * 70}")
        logger.info("  REFLEX Permission Matrix Test Report")
        logger.info(f"{'=' * 70}")
        logger.info(f"  Base URL: {report.base_url}")
        logger.info(f"  Total:    {report.total}")
        logger.info(f"  Passed:   {report.passed}")
        logger.info(f"  Failed:   {report.failed}")
        logger.info(f"  Rate:     {report.pass_rate:.0f}%")
        logger.info(f"{'=' * 70}\n")

        # Group by URL
        by_url: dict[str, list[PermissionTestResult]] = {}
        for r in report.results:
            by_url.setdefault(r.url, []).append(r)

        for url, results in sorted(by_url.items()):
            roles_str = "  ".join(
                f"{'✅' if r.passed else '❌'}{r.role}:{r.actual_status}" for r in sorted(results, key=lambda x: x.role)
            )
            logger.info(f"  {url}")
            logger.info(f"    {roles_str}")

        if report.failed > 0:
            logger.error(f"\n  ❌ FAILURES ({report.failed}):")
            for r in report.failures_only():
                logger.info(f"    {r.url} [{r.role}]: expected {r.expected_status}, got {r.actual_status}")

        logger.info()

    @staticmethod
    def to_json(report: PermissionReport) -> str:
        """Export report as JSON."""
        import json

        data = {
            "base_url": report.base_url,
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "pass_rate": report.pass_rate,
            "results": [
                {
                    "url": r.url,
                    "role": r.role,
                    "expected": r.expected_status,
                    "actual": r.actual_status,
                    "passed": r.passed,
                }
                for r in report.results
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
