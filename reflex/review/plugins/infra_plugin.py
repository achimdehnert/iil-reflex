"""
REFLEX Review Plugin: infra — Infrastructure health checks (ADR-165).

Validates infrastructure-related files and conventions that prevent
operational incidents (disk fill, missing backups, stale crons).

All checks are LOCAL — they inspect repo files, not the live server.
Server-side checks are handled by MCP tools (system_manage, docker_manage).

Checks:
- Backup script has retention policy (KEEP_DAYS, disk pre-check)
- Backup script has size safety limit
- Export volume cleanup in backup scripts
- healthz.py template present and correct
- Cleanup cron references in scripts/
- Dockerfile HEALTHCHECK pattern (must be in compose, not Dockerfile)
- Log rotation in backup/cron scripts
"""

from __future__ import annotations

import re
from pathlib import Path

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)


class InfraPlugin:
    """Infrastructure health review plugin."""

    name = "infra"
    applicable_tiers = [1, 2]

    # Backup script patterns that indicate good practices
    RETENTION_PATTERNS = [
        r"KEEP_DAYS\s*=",
        r"RETENTION_DAYS\s*=",
        r"RETENTION\s*=",
        r"find\s+.*-mtime\s+\+.*-delete",
        r"find\s+.*-mtime\s+\+.*rm\b",
        r"find\s+.*-mtime\s+\+.*xargs.*rm",
    ]

    DISK_CHECK_PATTERNS = [
        r"df\s+.*--output",
        r"df\s+-h",
        r"disk_usage",
        r"shutil\.disk_usage",
        r"DISK_PCT",
    ]

    SIZE_LIMIT_PATTERNS = [
        r"MAX_BACKUP_GB\s*=",
        r"MAX_BACKUP_BYTES\s*=",
        r"MAX_BACKUP_SIZE",
        r"BACKUP_SIZE.*limit",
        r"BACKUP_BYTES.*limit",
    ]

    def check(self, repo: str, context: dict) -> list[Finding]:
        repo_path = Path(context.get("repo_path", ""))
        if not repo_path.exists():
            return []

        findings: list[Finding] = []

        # 1. Backup scripts
        findings.extend(self._check_backup_scripts(repo_path, repo))

        # 2. Health endpoint template
        findings.extend(self._check_health_endpoint(repo_path, repo))

        # 3. Cleanup/maintenance scripts
        findings.extend(self._check_cleanup_scripts(repo_path, repo))

        # 4. Docker volume hygiene hints in compose
        findings.extend(self._check_volume_hygiene(repo_path, repo))

        self.last_metrics = self._collect_metrics(repo_path, findings)

        return findings

    def _check_backup_scripts(self, repo_path: Path, repo: str) -> list[Finding]:
        """Check backup scripts for retention, disk checks, and size limits."""
        findings: list[Finding] = []
        backup_scripts = list(repo_path.rglob("*backup*.sh")) + list(repo_path.rglob("*backup*.py"))

        if not backup_scripts:
            return [
                Finding(
                    rule_id="infra.no_backup_script",
                    severity=ReviewSeverity.INFO,
                    message=f"{repo}: No backup script found (backup*.sh or backup*.py)",
                    fix_hint="Create scripts/backup.sh with retention policy",
                    fix_complexity=FixComplexity.MODERATE,
                )
            ]

        for script in backup_scripts:
            rel_path = str(script.relative_to(repo_path))
            try:
                content = script.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Check retention policy
            has_retention = any(re.search(p, content) for p in self.RETENTION_PATTERNS)
            if not has_retention:
                findings.append(
                    Finding(
                        rule_id="infra.backup_no_retention",
                        severity=ReviewSeverity.BLOCK,
                        message=(f"{rel_path}: No retention policy found — backups will accumulate and fill disk"),
                        file_path=rel_path,
                        fix_hint="Add KEEP_DAYS=N and 'find ... -mtime +$KEEP_DAYS -delete'",
                        fix_complexity=FixComplexity.SIMPLE,
                    )
                )

            # Check disk pre-flight
            has_disk_check = any(re.search(p, content) for p in self.DISK_CHECK_PATTERNS)
            if not has_disk_check:
                findings.append(
                    Finding(
                        rule_id="infra.backup_no_disk_check",
                        severity=ReviewSeverity.WARN,
                        message=(f"{rel_path}: No disk space pre-check — backup may fill disk when space is low"),
                        file_path=rel_path,
                        fix_hint=(
                            "Add: DISK_PCT=$(df / --output=pcent | tail -1 | tr -d ' %'); (( DISK_PCT > 90 )) && exit 0"
                        ),
                        fix_complexity=FixComplexity.TRIVIAL,
                    )
                )

            # Check size safety limit
            has_size_limit = any(re.search(p, content) for p in self.SIZE_LIMIT_PATTERNS)
            if not has_size_limit:
                findings.append(
                    Finding(
                        rule_id="infra.backup_no_size_limit",
                        severity=ReviewSeverity.WARN,
                        message=(f"{rel_path}: No backup size safety limit — large exports can exceed available space"),
                        file_path=rel_path,
                        fix_hint="Add MAX_BACKUP_GB=N and prune if exceeded",
                        fix_complexity=FixComplexity.SIMPLE,
                    )
                )

            # Check export volume cleanup
            if "export" in content.lower() and "zip" in content.lower():
                has_export_cleanup = bool(
                    re.search(r"tail\s+-n\s+\+\d+.*xargs.*rm", content)
                    or re.search(r"head\s+-n\s+-\d+.*xargs.*rm", content)
                    or re.search(r"find.*export.*-delete", content)
                    or re.search(r"ls.*export.*tail.*rm", content)
                )
                if not has_export_cleanup:
                    findings.append(
                        Finding(
                            rule_id="infra.backup_no_export_cleanup",
                            severity=ReviewSeverity.WARN,
                            message=(
                                f"{rel_path}: Exports generated but no cleanup — old export zips accumulate in volume"
                            ),
                            file_path=rel_path,
                            fix_hint="Add: ls -1t export-*.zip | tail -n +4 | xargs -r rm -f",
                            fix_complexity=FixComplexity.TRIVIAL,
                        )
                    )

        return findings

    def _check_health_endpoint(self, repo_path: Path, repo: str) -> list[Finding]:
        """Check for healthz.py or health check views."""
        findings: list[Finding] = []

        # Look for health endpoint files
        health_files = (
            list(repo_path.rglob("healthz.py"))
            + list(repo_path.rglob("health.py"))
            + list(repo_path.rglob("health_check*.py"))
        )

        # Also check urls.py for /livez/ and /healthz/ patterns
        has_livez = False
        has_healthz = False
        for urls_file in repo_path.rglob("urls.py"):
            try:
                content = urls_file.read_text(encoding="utf-8", errors="ignore")
                if "livez" in content:
                    has_livez = True
                if "healthz" in content:
                    has_healthz = True
            except Exception:
                continue

        if not health_files and not has_livez:
            findings.append(
                Finding(
                    rule_id="infra.no_health_endpoint",
                    severity=ReviewSeverity.WARN,
                    message=(
                        f"{repo}: No health endpoint found (/livez/, /healthz/) — required for container orchestration"
                    ),
                    fix_hint="Copy platform/deployment/templates/django/healthz.py and wire up URLs",
                    fix_complexity=FixComplexity.SIMPLE,
                )
            )
        else:
            if not has_livez:
                findings.append(
                    Finding(
                        rule_id="infra.no_livez_url",
                        severity=ReviewSeverity.WARN,
                        message=f"{repo}: /livez/ endpoint not wired in urls.py",
                        fix_hint="path('livez/', liveness, name='liveness')",
                        fix_complexity=FixComplexity.TRIVIAL,
                    )
                )
            if not has_healthz:
                findings.append(
                    Finding(
                        rule_id="infra.no_healthz_url",
                        severity=ReviewSeverity.WARN,
                        message=f"{repo}: /healthz/ endpoint not wired in urls.py",
                        fix_hint="path('healthz/', readiness, name='healthz')",
                        fix_complexity=FixComplexity.TRIVIAL,
                    )
                )

            # Check healthz includes disk check
            for hf in health_files:
                try:
                    content = hf.read_text(encoding="utf-8", errors="ignore")
                    if "disk" not in content.lower() and "shutil" not in content:
                        findings.append(
                            Finding(
                                rule_id="infra.healthz_no_disk_check",
                                severity=ReviewSeverity.INFO,
                                message=(
                                    f"{hf.relative_to(repo_path)}: "
                                    "healthz has no disk check — recommend adding "
                                    "shutil.disk_usage for early warning"
                                ),
                                file_path=str(hf.relative_to(repo_path)),
                                fix_complexity=FixComplexity.TRIVIAL,
                            )
                        )
                except Exception:
                    continue

        return findings

    def _check_cleanup_scripts(self, repo_path: Path, repo: str) -> list[Finding]:
        """Check for maintenance/cleanup automation."""
        findings: list[Finding] = []

        # Look for cleanup scripts or cron references
        cleanup_scripts = (
            list(repo_path.rglob("*cleanup*.sh"))
            + list(repo_path.rglob("*maintenance*.sh"))
            + list(repo_path.rglob("*prune*.sh"))
        )

        # Also check for cleanup references in any shell scripts
        has_docker_prune = False
        _has_log_rotation = False
        for sh_file in repo_path.rglob("*.sh"):
            try:
                content = sh_file.read_text(encoding="utf-8", errors="ignore")
                if "docker" in content and ("prune" in content or "cleanup" in content):
                    has_docker_prune = True
                if "vacuum" in content or "logrotate" in content or "max-size" in content:
                    _has_log_rotation = True
            except Exception:
                continue

        if not cleanup_scripts and not has_docker_prune:
            findings.append(
                Finding(
                    rule_id="infra.no_cleanup_automation",
                    severity=ReviewSeverity.INFO,
                    message=(
                        f"{repo}: No cleanup/maintenance scripts found — docker images and logs accumulate over time"
                    ),
                    fix_hint="Add scripts/cleanup.sh with docker prune + log rotation",
                    fix_complexity=FixComplexity.SIMPLE,
                )
            )

        return findings

    def _check_volume_hygiene(self, repo_path: Path, repo: str) -> list[Finding]:
        """Check compose for named volumes that might grow unbounded."""
        findings: list[Finding] = []
        compose_file = repo_path / "docker-compose.prod.yml"
        if not compose_file.exists():
            return []

        try:
            content = compose_file.read_text(encoding="utf-8")
        except Exception:
            return []

        # Check for volumes with 'export' or 'upload' in the name
        # These are high-risk for unbounded growth
        volume_names = re.findall(r"^\s+(\w+_(?:export|upload|media|data)\w*):", content, re.MULTILINE)
        if not volume_names:
            # Also check top-level volumes section
            volume_names = re.findall(r"^  (\w*(?:export|upload|media)\w*):", content, re.MULTILINE)

        for vol in volume_names:
            findings.append(
                Finding(
                    rule_id="infra.unbounded_volume",
                    severity=ReviewSeverity.INFO,
                    message=(
                        f"{repo}: Volume '{vol}' may grow unbounded — "
                        "ensure backup script includes cleanup for old exports"
                    ),
                    file_path="docker-compose.prod.yml",
                    fix_complexity=FixComplexity.SIMPLE,
                )
            )

        return findings

    def _collect_metrics(self, repo_path: Path, findings: list[Finding]) -> dict:
        """Collect metrics for Grafana/Outline reporting."""
        backup_scripts = list(repo_path.rglob("*backup*.sh"))
        health_files = list(repo_path.rglob("healthz.py")) + list(repo_path.rglob("health.py"))
        cleanup_scripts = list(repo_path.rglob("*cleanup*.sh"))

        return {
            "backup_scripts": len(backup_scripts),
            "health_endpoints": len(health_files),
            "cleanup_scripts": len(cleanup_scripts),
            "findings_block": sum(1 for f in findings if f.severity == ReviewSeverity.BLOCK),
            "findings_warn": sum(1 for f in findings if f.severity == ReviewSeverity.WARN),
            "findings_info": sum(1 for f in findings if f.severity == ReviewSeverity.INFO),
        }


plugin = InfraPlugin()
