"""
REFLEX Cycle Runner — Orchestrates the full development cycle.

Manages the complete loop: UC → Backend → Frontend → Test → Fix → Verify.
Each phase produces structured results that feed into the next phase.
Failed phases trigger automatic retry with classification-based routing.

Architecture:
    - Pure Python orchestrator
    - Delegates to UCDialogEngine, UCQualityChecker, PermissionRunner, FailureClassifier
    - Configurable via dev_cycle section in reflex.yaml
    - Max retry iterations per phase (configurable)

Phases:
    Z0: Domain Research      → DomainAgent.research()
    Z1: UC Dialog + Quality  → UCDialogEngine.start() / refine()
    Z2: Backend Verify       → pytest (via subprocess)
    Z3: Frontend Verify      → HTTP status checks on all routes
    Z4: Permission Test      → PermissionRunner.run_all()
    Z5: Fix Classification   → FailureClassifier.classify()
    Z6: Retry Loop           → Back to failed phase

Usage:
    from reflex.cycle import CycleRunner, CycleConfig

    config = CycleConfig.from_yaml("reflex.yaml")
    runner = CycleRunner(config)
    result = runner.run_full_cycle(uc_slug="UC-001")

CLI:
    python -m reflex cycle UC-001 --config reflex.yaml
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


__all__ = ["CyclePhase", "PhaseStatus", "CycleConfig", "PhaseResult", "CycleResult", "CycleRunner"]


class CyclePhase(StrEnum):
    """Development cycle phases."""

    DOMAIN_RESEARCH = "Z0_domain_research"
    UC_QUALITY = "Z1_uc_quality"
    BACKEND_TEST = "Z2_backend_test"
    FRONTEND_VERIFY = "Z3_frontend_verify"
    PERMISSION_TEST = "Z4_permission_test"
    FIX_CLASSIFY = "Z5_fix_classify"
    COMPLETE = "Z6_complete"


class PhaseStatus(StrEnum):
    """Phase execution status."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CycleConfig:
    """Configuration for the development cycle from reflex.yaml."""

    base_url: str = "http://localhost:8000"
    login_url: str = "/accounts/login/"
    backend_test_cmd: str = "pytest src/ -q --tb=short"
    frontend_test_cmd: str = ""
    lint_cmd: str = "ruff check src/"
    max_fix_iterations: int = 3
    project_root: str = "."
    routes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> CycleConfig:
        """Load cycle config from reflex.yaml dev_cycle section."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")

        with path.open() as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}

        dev_cycle = raw.get("dev_cycle", {})
        return cls(
            base_url=dev_cycle.get("base_url", "http://localhost:8000"),
            login_url=dev_cycle.get("login_url", "/accounts/login/"),
            backend_test_cmd=dev_cycle.get("backend_test_cmd", "pytest src/ -q --tb=short"),
            frontend_test_cmd=dev_cycle.get("frontend_test_cmd", ""),
            lint_cmd=dev_cycle.get("lint_cmd", "ruff check src/"),
            max_fix_iterations=dev_cycle.get("max_fix_iterations", 3),
            project_root=str(path.parent),
            routes=raw.get("routes", []),
        )


@dataclass
class PhaseResult:
    """Result of a single cycle phase."""

    phase: CyclePhase
    status: PhaseStatus
    duration_seconds: float = 0.0
    output: str = ""
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == PhaseStatus.PASSED


@dataclass
class CycleResult:
    """Complete development cycle result."""

    uc_slug: str
    phases: list[PhaseResult] = field(default_factory=list)
    iteration: int = 1
    total_duration_seconds: float = 0.0
    final_status: PhaseStatus = PhaseStatus.PENDING

    @property
    def all_passed(self) -> bool:
        return all(p.passed or p.status == PhaseStatus.SKIPPED for p in self.phases)

    @property
    def failed_phases(self) -> list[PhaseResult]:
        return [p for p in self.phases if p.status == PhaseStatus.FAILED]

    def phase_summary(self) -> str:
        lines = []
        for p in self.phases:
            icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}.get(p.status.value, "⏳")
            lines.append(f"  {icon} {p.phase.value}: {p.status.value} ({p.duration_seconds:.1f}s)")
        return "\n".join(lines)


class CycleRunner:
    """Orchestrates the full development cycle.

    Runs phases sequentially, classifies failures, and retries
    up to max_fix_iterations times.
    """

    def __init__(self, config: CycleConfig):
        self.config = config

    def run_full_cycle(
        self,
        uc_slug: str = "",
        skip_phases: list[CyclePhase] | None = None,
    ) -> CycleResult:
        """Execute the full development cycle.

        Args:
            uc_slug: Use case identifier (e.g. "UC-001")
            skip_phases: Phases to skip (e.g. [CyclePhase.DOMAIN_RESEARCH])

        Returns:
            CycleResult with all phase results
        """
        skip = set(skip_phases or [])
        result = CycleResult(uc_slug=uc_slug)
        start_time = time.time()

        for iteration in range(1, self.config.max_fix_iterations + 1):
            result.iteration = iteration
            logger.info("=== Cycle iteration %d for %s ===", iteration, uc_slug)

            # Z2: Backend Tests
            if CyclePhase.BACKEND_TEST not in skip:
                phase = self._run_backend_tests()
                result.phases.append(phase)
                if not phase.passed:
                    classification = self._classify_failure(phase)
                    result.phases.append(classification)
                    if iteration < self.config.max_fix_iterations:
                        logger.info("Backend test failed — will retry")
                        continue
                    break

            # Z3: Frontend Verify (route checks)
            if CyclePhase.FRONTEND_VERIFY not in skip:
                phase = self._run_frontend_verify()
                result.phases.append(phase)
                if not phase.passed:
                    if iteration < self.config.max_fix_iterations:
                        logger.info("Frontend verify failed — will retry")
                        continue
                    break

            # Z4: Permission Tests
            if CyclePhase.PERMISSION_TEST not in skip:
                phase = self._run_permission_tests()
                result.phases.append(phase)
                if not phase.passed:
                    if iteration < self.config.max_fix_iterations:
                        logger.info("Permission test failed — will retry")
                        continue
                    break

            # All passed
            result.final_status = PhaseStatus.PASSED
            break
        else:
            result.final_status = PhaseStatus.FAILED

        result.total_duration_seconds = time.time() - start_time
        return result

    def run_single_phase(self, phase: CyclePhase) -> PhaseResult:
        """Run a single phase (useful for targeted re-runs)."""
        runners = {
            CyclePhase.BACKEND_TEST: self._run_backend_tests,
            CyclePhase.FRONTEND_VERIFY: self._run_frontend_verify,
            CyclePhase.PERMISSION_TEST: self._run_permission_tests,
        }
        runner = runners.get(phase)
        if not runner:
            return PhaseResult(
                phase=phase,
                status=PhaseStatus.SKIPPED,
                output=f"No runner for phase {phase.value}",
            )
        return runner()

    # ── Phase Runners ───────────────────────────────────────────────────────

    def _run_backend_tests(self) -> PhaseResult:
        """Z2: Run backend tests via subprocess."""
        start = time.time()
        cmd = self.config.backend_test_cmd

        if not cmd:
            return PhaseResult(
                phase=CyclePhase.BACKEND_TEST,
                status=PhaseStatus.SKIPPED,
                output="No backend_test_cmd configured",
            )

        try:
            proc = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.config.project_root,
            )
            passed = proc.returncode == 0
            output = proc.stdout + proc.stderr

            # Extract test counts from pytest output
            metrics = self._parse_pytest_output(output)

            return PhaseResult(
                phase=CyclePhase.BACKEND_TEST,
                status=PhaseStatus.PASSED if passed else PhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                output=output[-2000:],  # Last 2000 chars
                errors=self._extract_errors(output) if not passed else [],
                metrics=metrics,
            )
        except subprocess.TimeoutExpired:
            return PhaseResult(
                phase=CyclePhase.BACKEND_TEST,
                status=PhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                errors=["Backend test timed out after 300s"],
            )
        except FileNotFoundError as e:
            return PhaseResult(
                phase=CyclePhase.BACKEND_TEST,
                status=PhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                errors=[f"Command not found: {e}"],
            )

    def _run_frontend_verify(self) -> PhaseResult:
        """Z3: Verify frontend routes are accessible."""
        start = time.time()

        try:
            import httpx
        except ImportError:
            return PhaseResult(
                phase=CyclePhase.FRONTEND_VERIFY,
                status=PhaseStatus.SKIPPED,
                output="httpx not installed — skip frontend verify",
            )

        errors = []
        routes_checked = 0
        routes_ok = 0

        # Test authenticated routes
        try:
            with httpx.Client(follow_redirects=False, timeout=10) as client:
                # Login first
                session = self._login_session(client)

                for route_def in self.config.routes:
                    url = route_def.get("url", "")
                    expected = route_def.get("expect", 200)
                    auth_required = route_def.get("auth", True)
                    label = route_def.get("label", url)

                    if not url:
                        continue

                    routes_checked += 1
                    full_url = f"{self.config.base_url}{url}"

                    if auth_required and session:
                        resp = session.get(full_url, follow_redirects=False)
                    else:
                        resp = client.get(full_url, follow_redirects=False)

                    if resp.status_code == expected:
                        routes_ok += 1
                    else:
                        errors.append(f"{label} ({url}): expected {expected}, got {resp.status_code}")

        except Exception as e:
            errors.append(f"Frontend verify error: {e}")

        return PhaseResult(
            phase=CyclePhase.FRONTEND_VERIFY,
            status=PhaseStatus.PASSED if not errors else PhaseStatus.FAILED,
            duration_seconds=time.time() - start,
            output=f"Routes: {routes_ok}/{routes_checked} OK",
            errors=errors,
            metrics={"routes_checked": routes_checked, "routes_ok": routes_ok},
        )

    def _run_permission_tests(self) -> PhaseResult:
        """Z4: Run permission matrix tests via PermissionRunner."""
        start = time.time()

        try:
            from reflex.permission_runner import PermissionRunner

            runner = PermissionRunner.from_yaml(
                Path(self.config.project_root) / "reflex.yaml",
                base_url=self.config.base_url,
                login_url=self.config.login_url,
            )
            report = runner.run_all()

            return PhaseResult(
                phase=CyclePhase.PERMISSION_TEST,
                status=PhaseStatus.PASSED if report.all_passed else PhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                output=f"Permissions: {report.passed}/{report.total} passed",
                errors=[
                    f"{r.url} [{r.role}]: expected {r.expected_status}, got {r.actual_status}"
                    for r in report.failures_only()
                ],
                metrics={
                    "total": report.total,
                    "passed": report.passed,
                    "failed": report.failed,
                    "pass_rate": report.pass_rate,
                },
            )

        except ImportError:
            return PhaseResult(
                phase=CyclePhase.PERMISSION_TEST,
                status=PhaseStatus.SKIPPED,
                output="PermissionRunner not available",
            )
        except Exception as e:
            return PhaseResult(
                phase=CyclePhase.PERMISSION_TEST,
                status=PhaseStatus.FAILED,
                duration_seconds=time.time() - start,
                errors=[f"Permission test error: {e}"],
            )

    def _classify_failure(self, phase_result: PhaseResult) -> PhaseResult:
        """Z5: Classify failures using FailureClassifier."""
        start = time.time()
        from reflex.classify import FailureClassifier

        classifier = FailureClassifier()
        classifications = []

        for error in phase_result.errors[:5]:  # Max 5 errors
            result = classifier.classify(
                test_name=phase_result.phase.value,
                error_message=error,
            )
            classifications.append(f"{result.failure_type.value}: {result.reasoning} → {result.suggested_action}")

        return PhaseResult(
            phase=CyclePhase.FIX_CLASSIFY,
            status=PhaseStatus.PASSED,
            duration_seconds=time.time() - start,
            output="\n".join(classifications),
            metrics={"classifications": len(classifications)},
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _login_session(self, client: Any) -> Any | None:
        """Login using first admin test user from config routes."""
        import re

        try:
            resp = client.get(f"{self.config.base_url}{self.config.login_url}")
            csrf = resp.cookies.get("csrftoken", "")
            if not csrf:
                match = re.search(
                    r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)',
                    resp.text,
                )
                csrf = match.group(1) if match else ""

            if not csrf:
                return None

            # Use admin credentials (hardcoded fallback, should come from config)
            client.post(
                f"{self.config.base_url}{self.config.login_url}",
                data={
                    "username": "admin",
                    "password": "admin123",
                    "csrfmiddlewaretoken": csrf,
                },
                headers={"Referer": f"{self.config.base_url}{self.config.login_url}"},
            )
            return client
        except Exception:
            return None

    @staticmethod
    def _parse_pytest_output(output: str) -> dict[str, Any]:
        """Extract test metrics from pytest output."""
        import re

        metrics: dict[str, Any] = {}
        # "5 passed, 2 failed, 1 error in 3.45s"
        match = re.search(
            r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?.*?in ([\d.]+)s",
            output,
        )
        if match:
            metrics["passed"] = int(match.group(1))
            metrics["failed"] = int(match.group(2) or 0)
            metrics["errors"] = int(match.group(3) or 0)
            metrics["duration"] = float(match.group(4))
        return metrics

    @staticmethod
    def _extract_errors(output: str) -> list[str]:
        """Extract error lines from test output."""
        errors = []
        for line in output.split("\n"):
            stripped = line.strip()
            if stripped.startswith("FAILED") or stripped.startswith("ERROR"):
                errors.append(stripped[:200])
        return errors[:10]  # Max 10 errors

    @staticmethod
    def print_result(result: CycleResult) -> None:
        """Print human-readable cycle result."""
        logger.info(f"\n{'=' * 70}")
        logger.info(f"  REFLEX Development Cycle Report — {result.uc_slug}")
        logger.info(f"{'=' * 70}")
        logger.info(f"  Iteration:  {result.iteration}")
        logger.info(f"  Duration:   {result.total_duration_seconds:.1f}s")
        logger.info(f"  Status:     {result.final_status.value}")
        logger.info(f"{'=' * 70}\n")
        logger.info(result.phase_summary())

        if result.failed_phases:
            logger.info("\n  ❌ Failed Phases:")
            for p in result.failed_phases:
                logger.info(f"    {p.phase.value}:")
                for e in p.errors[:3]:
                    logger.info(f"      - {e}")

        logger.info()
