"""
REFLEX Review Plugin: adr — ADR compliance checks (ADR-165, ADR-138).

Validates ADR files against MADR 4.0 structure and ADR-138 tracking requirements.
Works on a repo's docs/adr/ directory.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)


class ADRPlugin:
    name = "adr"
    applicable_tiers = [1, 2]

    REQUIRED_FRONTMATTER = ["title", "status", "date"]
    RECOMMENDED_FRONTMATTER = ["deciders", "implementation_status"]
    VALID_STATUSES = {"proposed", "accepted", "deprecated", "superseded", "archived"}
    VALID_IMPL_STATUSES = {"none", "partial", "implemented", "verified"}

    REQUIRED_SECTIONS = [
        "context",
        "decision drivers",
        "considered options",
        "decision outcome",
    ]

    def check(self, repo: str, context: dict) -> list[Finding]:
        repo_path = Path(context.get("repo_path", ""))
        findings: list[Finding] = []

        # Find ADR directory
        adr_dirs = [
            repo_path / "docs" / "adr",
            repo_path / "docs" / "adrs",
        ]
        adr_dir = next((d for d in adr_dirs if d.exists()), None)

        if adr_dir is None:
            findings.append(
                Finding(
                    rule_id="adr.no_adr_directory",
                    severity=ReviewSeverity.INFO,
                    message="No docs/adr/ directory found — ADR tracking not set up",
                    adr_ref="ADR-138",
                )
            )
            return findings

        adr_files = sorted(adr_dir.glob("ADR-*.md"))
        if not adr_files:
            findings.append(
                Finding(
                    rule_id="adr.no_adr_files",
                    severity=ReviewSeverity.INFO,
                    message="ADR directory exists but contains no ADR-*.md files",
                )
            )
            return findings

        for adr_file in adr_files:
            findings.extend(self._check_adr(adr_file, repo_path))

        return findings

    def _check_adr(self, adr_file: Path, repo_path: Path) -> list[Finding]:
        findings: list[Finding] = []
        rel_path = str(adr_file.relative_to(repo_path))
        text = adr_file.read_text(encoding="utf-8")
        adr_name = adr_file.stem

        # Parse frontmatter
        frontmatter = self._parse_frontmatter(text)

        # Check required frontmatter
        for key in self.REQUIRED_FRONTMATTER:
            if key not in frontmatter:
                findings.append(
                    Finding(
                        rule_id=f"adr.missing_frontmatter_{key}",
                        severity=ReviewSeverity.BLOCK,
                        message=f"{adr_name}: Missing required frontmatter field '{key}'",
                        adr_ref="MADR 4.0",
                        file_path=rel_path,
                        auto_fixable=False,
                        fix_complexity=FixComplexity.SIMPLE,
                    )
                )

        # Check status is valid
        status = frontmatter.get("status", "").lower()
        if status and status not in self.VALID_STATUSES:
            findings.append(
                Finding(
                    rule_id="adr.invalid_status",
                    severity=ReviewSeverity.WARN,
                    message=(
                        f"{adr_name}: Invalid status '{status}'"
                        f" — must be one of {self.VALID_STATUSES}"
                    ),
                    file_path=rel_path,
                )
            )

        # ADR-138: implementation_status required for Accepted ADRs
        if status == "accepted":
            impl_status = frontmatter.get("implementation_status", "")
            if not impl_status:
                findings.append(
                    Finding(
                        rule_id="adr.missing_implementation_status",
                        severity=ReviewSeverity.BLOCK,
                        message=(
                            f"{adr_name}: Accepted ADR missing"
                            " 'implementation_status' (ADR-138)"
                        ),
                        adr_ref="ADR-138",
                        file_path=rel_path,
                        auto_fixable=True,
                        fix_complexity=FixComplexity.TRIVIAL,
                        fix_hint="Add 'implementation_status: none' to frontmatter",
                    )
                )
            elif impl_status not in self.VALID_IMPL_STATUSES:
                findings.append(
                    Finding(
                        rule_id="adr.invalid_implementation_status",
                        severity=ReviewSeverity.WARN,
                        message=f"{adr_name}: Invalid implementation_status '{impl_status}'",
                        adr_ref="ADR-138",
                        file_path=rel_path,
                    )
                )

            # If partial/implemented/verified, must have evidence
            if impl_status in ("partial", "implemented", "verified"):
                evidence = frontmatter.get("implementation_evidence", [])
                if not evidence:
                    findings.append(
                        Finding(
                            rule_id="adr.missing_implementation_evidence",
                            severity=ReviewSeverity.WARN,
                            message=(
                                f"{adr_name}: implementation_status="
                                f"'{impl_status}' but no"
                                " implementation_evidence"
                            ),
                            adr_ref="ADR-138",
                            file_path=rel_path,
                        )
                    )

        # Check for required sections (lower-cased heading search)
        text_lower = text.lower()
        for section in self.REQUIRED_SECTIONS:
            # Look for ## heading containing the section name
            pattern = r"^##\s+.*" + re.escape(section)
            if not re.search(pattern, text_lower, re.MULTILINE):
                findings.append(
                    Finding(
                        rule_id=f"adr.missing_section_{section.replace(' ', '_')}",
                        severity=ReviewSeverity.WARN,
                        message=f"{adr_name}: Missing recommended section containing '{section}'",
                        adr_ref="MADR 4.0",
                        file_path=rel_path,
                    )
                )

        return findings

    @staticmethod
    def _parse_frontmatter(text: str) -> dict:
        """Parse YAML frontmatter from markdown text."""
        if not text.startswith("---"):
            return {}
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}
        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}


plugin = ADRPlugin()
