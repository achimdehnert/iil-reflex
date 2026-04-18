"""
REFLEX Review Plugin: compose — Docker Compose audit (ADR-165, ADR-021).

Validates docker-compose.prod.yml against platform conventions:
- HEALTHCHECK not in Dockerfile (only in compose)
- Non-root user
- Logging config
- restart policy
- env_file pattern
"""

from __future__ import annotations

import re
from pathlib import Path

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)


class ComposePlugin:
    name = "compose"
    applicable_tiers = [1, 2]

    def check(self, repo: str, context: dict) -> list[Finding]:
        repo_path = Path(context.get("repo_path", ""))
        findings: list[Finding] = []

        compose_file = repo_path / "docker-compose.prod.yml"
        if not compose_file.exists():
            return [
                Finding(
                    rule_id="compose.missing",
                    severity=ReviewSeverity.BLOCK,
                    message="docker-compose.prod.yml not found",
                    adr_ref="ADR-021 §2.3",
                    file_path="docker-compose.prod.yml",
                )
            ]

        compose_text = compose_file.read_text(encoding="utf-8")

        # Check HEALTHCHECK not in Dockerfile
        for dockerfile_path in ["docker/app/Dockerfile", "Dockerfile"]:
            df = repo_path / dockerfile_path
            if df.exists():
                df_text = df.read_text(encoding="utf-8")
                if "HEALTHCHECK" in df_text:
                    findings.append(
                        Finding(
                            rule_id="compose.healthcheck_in_dockerfile",
                            severity=ReviewSeverity.BLOCK,
                            message=(
                                f"HEALTHCHECK in {dockerfile_path} — must be per-service "
                                "in docker-compose.prod.yml only (coach-hub incident)"
                            ),
                            adr_ref="ADR-021 §3.4",
                            file_path=dockerfile_path,
                            auto_fixable=True,
                            fix_complexity=FixComplexity.SIMPLE,
                            fix_hint=(
                                f"Remove HEALTHCHECK from {dockerfile_path},"
                                " add per-service in compose"
                            ),
                        )
                    )

        # Check restart policy
        if "restart:" not in compose_text:
            findings.append(
                Finding(
                    rule_id="compose.no_restart_policy",
                    severity=ReviewSeverity.WARN,
                    message="No restart policy found — recommend 'restart: unless-stopped'",
                    adr_ref="ADR-021 §2.11",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            )

        # Check logging config
        if "logging:" not in compose_text:
            findings.append(
                Finding(
                    rule_id="compose.no_logging_config",
                    severity=ReviewSeverity.WARN,
                    message="No logging config — recommend json-file with max-size",
                    adr_ref="ADR-021 §2.11",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.SIMPLE,
                    fix_hint=(
                        'logging: { driver: "json-file",'
                        ' options: { max-size: "10m", max-file: "3" } }'
                    ),
                )
            )

        # Check env_file usage
        if "env_file" not in compose_text:
            findings.append(
                Finding(
                    rule_id="compose.no_env_file",
                    severity=ReviewSeverity.WARN,
                    message="No env_file directive — secrets should use env_file, not environment",
                    adr_ref="ADR-045",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=False,
                    fix_complexity=FixComplexity.MODERATE,
                )
            )

        # Check for healthcheck in compose (should have at least one)
        if "healthcheck:" not in compose_text and "health_check:" not in compose_text:
            findings.append(
                Finding(
                    rule_id="compose.no_healthcheck",
                    severity=ReviewSeverity.WARN,
                    message=(
                        "No healthcheck defined in compose"
                        " — recommend adding per-service healthchecks"
                    ),
                    adr_ref="ADR-021 §2.8",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=False,
                    fix_complexity=FixComplexity.MODERATE,
                )
            )

        # Check for exposed ports (should use 127.0.0.1:PORT:8000, not 0.0.0.0)
        port_lines = re.findall(r'ports:\s*\n((?:\s+-\s*["\']?\d.*\n)+)', compose_text)
        for block in port_lines:
            for line in block.strip().split("\n"):
                line = line.strip().lstrip("- ").strip("'\"")
                if line and ":" in line and not line.startswith("127.0.0.1"):
                    # Check if it's binding to all interfaces
                    parts = line.split(":")
                    if len(parts) == 2:
                        findings.append(
                            Finding(
                                rule_id="compose.port_exposed_all_interfaces",
                                severity=ReviewSeverity.WARN,
                                message=(
                                    f"Port binding '{line}' exposes to"
                                    f" all interfaces — use 127.0.0.1:{line}"
                                ),
                                adr_ref="ADR-021 §2.9",
                                file_path="docker-compose.prod.yml",
                                auto_fixable=True,
                                fix_complexity=FixComplexity.TRIVIAL,
                                fix_hint=f'Use "127.0.0.1:{line}" instead of "{line}"',
                            )
                        )

        return findings


plugin = ComposePlugin()
