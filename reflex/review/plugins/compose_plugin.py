"""
REFLEX Review Plugin: compose — Docker Compose audit (ADR-165, ADR-021).

Validates docker-compose.prod.yml against platform conventions:
- HEALTHCHECK not in Dockerfile (only in compose)
- restart policy
- Logging config (json-file with max-size)
- env_file usage (not environment:${VAR})
- Memory limits
- Healthcheck in compose

Port binding checks → security_plugin (Single Responsibility).
"""

from __future__ import annotations

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
                            fix_hint=(f"Remove HEALTHCHECK from {dockerfile_path}, add per-service in compose"),
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
                    fix_hint=('logging: { driver: "json-file", options: { max-size: "10m", max-file: "3" } }'),
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
                    message=("No healthcheck defined in compose — recommend adding per-service healthchecks"),
                    adr_ref="ADR-021 §2.8",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=False,
                    fix_complexity=FixComplexity.MODERATE,
                )
            )

        # Check memory limits
        if "mem_limit" not in compose_text and "memory" not in compose_text:
            findings.append(
                Finding(
                    rule_id="compose.no_memory_limit",
                    severity=ReviewSeverity.WARN,
                    message="docker-compose.prod.yml has no memory limits",
                    adr_ref="ADR-021 §2.11",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.SIMPLE,
                    fix_hint="Add deploy.resources.limits.memory under each service",
                )
            )

        # Check env interpolation anti-pattern (ADR-045)
        if "environment:" in compose_text and "${" in compose_text:
            findings.append(
                Finding(
                    rule_id="compose.env_interpolation",
                    severity=ReviewSeverity.BLOCK,
                    message=("docker-compose.prod.yml uses ${VAR} interpolation — use env_file instead"),
                    adr_ref="ADR-045",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=False,
                    fix_complexity=FixComplexity.MODERATE,
                )
            )

        return findings


plugin = ComposePlugin()
