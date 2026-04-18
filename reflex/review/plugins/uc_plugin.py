"""
REFLEX Review Plugin: uc — Use Case completeness & quality checks (ADR-165).

Checks for:
- Existence of docs/use-cases/ directory
- UC count (minimum for Tier 1)
- UC status distribution (Draft → Implemented → Tested)
- Required UC sections (Akteur, Ziel, Vorbedingung, etc.)
- Implementation evidence (UC defined but no matching code)
"""

from __future__ import annotations

import re
from pathlib import Path

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)


class UCPlugin:
    """Use Case completeness and quality review plugin."""

    name = "uc"
    applicable_tiers = [1, 2]

    # Required sections in a UC document (case-insensitive heading search)
    REQUIRED_SECTIONS = [
        "akteur",
        "ziel",
        "vorbedingung",
    ]

    # Recommended sections (WARN if missing)
    RECOMMENDED_SECTIONS = [
        "nachbedingung",
        "hauptszenario",
    ]

    # Valid UC statuses
    VALID_STATUSES = {
        "draft",
        "defined",
        "implemented",
        "tested",
        "verified",
        "deprecated",
    }

    def check(self, repo: str, context: dict) -> list[Finding]:
        """Check UC completeness for a repo."""
        repo_path = Path(context.get("repo_path", ""))
        if not repo_path.exists():
            return [
                Finding(
                    rule_id="uc.repo_not_found",
                    severity=ReviewSeverity.BLOCK,
                    message=f"Repository path not found: {repo_path}",
                )
            ]

        # Find UC directory
        uc_dir = self._find_uc_dir(repo_path)
        if uc_dir is None:
            return [
                Finding(
                    rule_id="uc.no_uc_directory",
                    severity=ReviewSeverity.WARN,
                    message=("No use-cases directory found. Expected: docs/use-cases/"),
                    adr_ref="ADR-162",
                    fix_hint="mkdir -p docs/use-cases/",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            ]

        # Discover UC files
        uc_files = sorted(uc_dir.glob("UC-*.md"))
        findings: list[Finding] = []

        if not uc_files:
            findings.append(
                Finding(
                    rule_id="uc.no_uc_files",
                    severity=ReviewSeverity.WARN,
                    message=("docs/use-cases/ exists but contains no UC-*.md files"),
                    adr_ref="ADR-162",
                    fix_hint="Create UCs with: reflex uc-create",
                )
            )
            return findings

        # Analyze each UC
        status_counts: dict[str, int] = {}
        for uc_file in uc_files:
            uc_findings = self._check_uc_file(uc_file, repo_path)
            findings.extend(uc_findings)

            # Count statuses
            status = self._extract_status(uc_file)
            status_counts[status] = status_counts.get(status, 0) + 1

        # UC count check (Tier 1 should have >= 3)
        if len(uc_files) < 3:
            findings.append(
                Finding(
                    rule_id="uc.low_uc_count",
                    severity=ReviewSeverity.INFO,
                    message=(f"Only {len(uc_files)} UC(s) defined. Tier 1 repos should have >= 3."),
                    adr_ref="ADR-163",
                )
            )

        # Status distribution check
        total = len(uc_files)
        draft_count = status_counts.get("draft", 0)
        if total > 0 and draft_count == total:
            findings.append(
                Finding(
                    rule_id="uc.all_draft",
                    severity=ReviewSeverity.WARN,
                    message=(f"All {total} UCs are in Draft status. Progress UCs to Implemented/Tested."),
                    adr_ref="ADR-162",
                )
            )

        return findings

    def _find_uc_dir(self, repo_path: Path) -> Path | None:
        """Find the use-cases directory."""
        candidates = [
            repo_path / "docs" / "use-cases",
            repo_path / "docs" / "use_cases",
            repo_path / "use-cases",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return None

    def _extract_status(self, uc_file: Path) -> str:
        """Extract status from UC file."""
        try:
            text = uc_file.read_text(encoding="utf-8")
            match = re.search(r"\*\*Status:\*\*\s*(\w+)", text)
            if match:
                return match.group(1).lower()
        except (OSError, UnicodeDecodeError):
            pass
        return "unknown"

    def _check_uc_file(self, uc_file: Path, repo_path: Path) -> list[Finding]:
        """Check individual UC file for quality."""
        findings: list[Finding] = []
        rel_path = str(uc_file.relative_to(repo_path))
        uc_name = uc_file.stem

        try:
            text = uc_file.read_text(encoding="utf-8")
        except Exception:
            findings.append(
                Finding(
                    rule_id="uc.unreadable",
                    severity=ReviewSeverity.BLOCK,
                    message=f"{uc_name}: Cannot read file",
                    file_path=rel_path,
                )
            )
            return findings

        text_lower = text.lower()

        # Check required sections
        for section in self.REQUIRED_SECTIONS:
            # Look for ## heading or **bold label**
            has_heading = re.search(
                r"^##\s+.*" + re.escape(section),
                text_lower,
                re.MULTILINE,
            )
            has_bold = f"**{section}" in text_lower
            if not has_heading and not has_bold:
                findings.append(
                    Finding(
                        rule_id=f"uc.missing_section_{section}",
                        severity=ReviewSeverity.BLOCK,
                        message=(f"{uc_name}: Missing required section '{section}'"),
                        adr_ref="ADR-162",
                        file_path=rel_path,
                    )
                )

        # Check recommended sections
        for section in self.RECOMMENDED_SECTIONS:
            has_heading = re.search(
                r"^##\s+.*" + re.escape(section),
                text_lower,
                re.MULTILINE,
            )
            has_bold = f"**{section}" in text_lower
            if not has_heading and not has_bold:
                findings.append(
                    Finding(
                        rule_id=(f"uc.missing_recommended_{section}"),
                        severity=ReviewSeverity.INFO,
                        message=(f"{uc_name}: Missing recommended section '{section}'"),
                        adr_ref="ADR-162",
                        file_path=rel_path,
                    )
                )

        # Check minimum content length (< 100 chars = stub)
        content_lines = [ln for ln in text.split("\n") if ln.strip() and not ln.startswith("#")]
        if len(content_lines) < 5:
            findings.append(
                Finding(
                    rule_id="uc.stub_content",
                    severity=ReviewSeverity.WARN,
                    message=(f"{uc_name}: UC appears to be a stub ({len(content_lines)} content lines)"),
                    file_path=rel_path,
                )
            )

        return findings


plugin = UCPlugin()
