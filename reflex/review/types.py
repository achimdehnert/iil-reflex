"""
REFLEX Review Types — Dataclasses for review findings and results (ADR-165 §5.1).

Pure Python — no Django, no framework dependency.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ReviewSeverity(StrEnum):
    """Finding severity level."""

    BLOCK = "block"
    WARN = "warn"
    INFO = "info"


class FixComplexity(StrEnum):
    """Estimated complexity for auto-fix (ADR-165 §5.3)."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass(frozen=True)
class Finding:
    """Single review finding from a plugin (ADR-165 §5.1).

    Attributes:
        rule_id: Dot-separated rule identifier, e.g. "compose.port_matches_yaml"
        severity: "block", "warn", or "info"
        message: Human-readable description
        adr_ref: Optional ADR reference, e.g. "ADR-164 §3.3"
        fix_hint: Optional code snippet or command to fix
        file_path: Optional affected file path (relative to repo root)
        auto_fixable: Whether this can be auto-fixed
        fix_complexity: Estimated fix complexity for model-tier routing
    """

    rule_id: str
    severity: ReviewSeverity
    message: str
    adr_ref: str | None = None
    fix_hint: str | None = None
    file_path: str | None = None
    auto_fixable: bool = False
    fix_complexity: FixComplexity = FixComplexity.MODERATE

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["fix_complexity"] = self.fix_complexity.value
        return d


@dataclass
class ReviewResult:
    """Aggregated result of one review run (ADR-165 §5.1).

    Attributes:
        repo: Repository name
        review_type: Plugin name that generated this result
        findings: List of findings
        duration_s: How long the review took
        triggered_by: What triggered the review
        timestamp: When the review was run
    """

    repo: str
    review_type: str
    findings: list[Finding] = field(default_factory=list)
    duration_s: float = 0.0
    triggered_by: str = "manual"
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    metadata: dict = field(default_factory=dict)

    @property
    def findings_block(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ReviewSeverity.BLOCK]

    @property
    def findings_warn(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ReviewSeverity.WARN]

    @property
    def findings_info(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ReviewSeverity.INFO]

    @property
    def findings_auto_fixable(self) -> list[Finding]:
        return [f for f in self.findings if f.auto_fixable]

    @property
    def score_pct(self) -> float:
        """Score 0-100. 100 = no findings, 0 = all block."""
        if not self.findings:
            return 100.0
        block_count = len(self.findings_block)
        warn_count = len(self.findings_warn)
        total = len(self.findings)
        # block = 3 points, warn = 1 point, info = 0
        penalty = (block_count * 3 + warn_count * 1)
        max_penalty = total * 3
        return max(0.0, round(100.0 * (1 - penalty / max_penalty), 2))

    @property
    def has_blockers(self) -> bool:
        return len(self.findings_block) > 0

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "review_type": self.review_type,
            "findings": [f.to_dict() for f in self.findings],
            "summary": {
                "total": len(self.findings),
                "block": len(self.findings_block),
                "warn": len(self.findings_warn),
                "info": len(self.findings_info),
                "auto_fixable": len(self.findings_auto_fixable),
                "score_pct": self.score_pct,
            },
            "duration_s": self.duration_s,
            "triggered_by": self.triggered_by,
            "timestamp": self.timestamp,
            **({"metadata": self.metadata} if self.metadata else {}),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class SuppressionEntry:
    """Single suppression rule from .reflex/suppressions.yaml (ADR-165 §5.8)."""

    rule_id: str
    reason: str
    until: str | None = None
    permanent: bool = False

    @property
    def is_expired(self) -> bool:
        if self.permanent or not self.until:
            return False
        try:
            expiry = datetime.fromisoformat(self.until)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            return datetime.now(UTC) > expiry
        except ValueError:
            return False
