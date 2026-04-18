"""
REFLEX Review Plugin: repo — Repository structure checks (ADR-165).

Checks for essential files and directory structure that every
platform repo should have. Pure existence checks only.

Compose content checks → compose_plugin (Single Responsibility).
Security checks (.gitignore secrets) → security_plugin.
"""

from __future__ import annotations

from pathlib import Path

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)


class RepoPlugin:
    name = "repo"
    applicable_tiers = [1, 2, 3]

    # Files that must exist in every repo
    REQUIRED_FILES = [
        ("README.md", "block", "ADR-021 §2"),
        (".gitignore", "block", None),
        ("docker-compose.prod.yml", "block", "ADR-021 §2.3"),
        (".env.prod.example", "warn", "ADR-045"),
    ]

    # Files that should exist for Tier 1+2
    TIER_12_FILES = [
        ("docs/", "warn", "ADR-163"),
        (".github/workflows/", "warn", "ADR-160"),
    ]

    DOCKERFILE_LOCATIONS = [
        "docker/app/Dockerfile",
        "Dockerfile",
    ]

    def check(self, repo: str, context: dict) -> list[Finding]:
        repo_path = Path(context.get("repo_path", ""))
        if not repo_path.exists():
            return [
                Finding(
                    rule_id="repo.not_found",
                    severity=ReviewSeverity.BLOCK,
                    message=f"Repository path not found: {repo_path}",
                )
            ]

        findings: list[Finding] = []

        # Required files
        for file_rel, sev, adr in self.REQUIRED_FILES:
            target = repo_path / file_rel
            if not target.exists():
                findings.append(
                    Finding(
                        rule_id="repo.missing_{}".format(
                            Path(file_rel).stem.lower().replace(".", "_").replace("-", "_")
                        ),
                        severity=ReviewSeverity(sev),
                        message=f"Missing required file: {file_rel}",
                        adr_ref=adr,
                        file_path=file_rel,
                        auto_fixable=file_rel == ".env.prod.example",
                        fix_complexity=FixComplexity.TRIVIAL,
                    )
                )

        # Tier 1+2 files
        for file_rel, sev, adr in self.TIER_12_FILES:
            target = repo_path / file_rel
            if not target.exists():
                findings.append(
                    Finding(
                        rule_id="repo.missing_{}".format(file_rel.rstrip("/").replace("/", "_").replace(".", "_")),
                        severity=ReviewSeverity(sev),
                        message=f"Missing recommended path: {file_rel}",
                        adr_ref=adr,
                        file_path=file_rel,
                    )
                )

        # Dockerfile must exist in one of the known locations
        has_dockerfile = any((repo_path / loc).exists() for loc in self.DOCKERFILE_LOCATIONS)
        if not has_dockerfile:
            findings.append(
                Finding(
                    rule_id="repo.missing_dockerfile",
                    severity=ReviewSeverity.BLOCK,
                    message="No Dockerfile found (checked docker/app/Dockerfile and Dockerfile)",
                    adr_ref="ADR-021 §2.3",
                )
            )

        return findings


plugin = RepoPlugin()
