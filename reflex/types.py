"""
REFLEX Type Definitions — Dataclasses for structured results.

All types are pure Python — no Django, no framework dependency.
Used across agent, quality, classify, and provider modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ── Enums ──────────────────────────────────────────────────────────────────


class UCStatus(str, Enum):
    """Use Case lifecycle status."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    TESTING = "testing"
    PASSED = "passed"
    FAILED = "failed"
    ARCHIVED = "archived"


class FailureType(str, Enum):
    """Root cause classification for test failures."""

    UC_PROBLEM = "uc_problem"
    UI_PROBLEM = "ui_problem"
    INFRA_PROBLEM = "infra_problem"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Finding severity."""

    BLOCKER = "blocker"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ── Knowledge Types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class KnowledgeEntry:
    """Single entry from a knowledge source (Outline, Memory, etc.)."""

    title: str
    content: str
    source: str = ""
    relevance_score: float = 0.0
    url: str = ""


@dataclass(frozen=True)
class DocumentEntry:
    """Single entry from a document source (Paperless, etc.)."""

    title: str
    snippet: str
    source: str = ""
    doc_id: str = ""
    date: str = ""


@dataclass(frozen=True)
class WebPage:
    """Scraped web page content."""

    url: str
    title: str
    text: str
    html: str = ""
    status_code: int = 200
    content_type: str = "text/html"
    scraped_at: str = ""

    @property
    def is_pdf(self) -> bool:
        return "application/pdf" in self.content_type

    @property
    def text_snippet(self) -> str:
        return self.text[:500] + "..." if len(self.text) > 500 else self.text


@dataclass(frozen=True)
class SDSData:
    """Structured SDS (Safety Data Sheet) data extracted from web or PDF."""

    substance_name: str
    cas_number: str = ""
    h_statements: list[str] = field(default_factory=list)
    p_statements: list[str] = field(default_factory=list)
    flash_point: str = ""
    ignition_temperature: str = ""
    explosion_limits: str = ""
    signal_word: str = ""
    ghs_pictograms: list[str] = field(default_factory=list)
    source_url: str = ""
    raw_text: str = ""


# ── Domain Agent Results ───────────────────────────────────────────────────


@dataclass
class DomainResearchResult:
    """Result of autonomous domain research (Zirkel 0, Phase 1-2)."""

    topic: str
    vertical: str
    facts: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def has_gaps(self) -> bool:
        return len(self.gaps) > 0


@dataclass(frozen=True)
class InterviewQuestion:
    """Structured question for domain expert (Zirkel 0, Phase 3)."""

    question: str
    category: str
    why_needed: str
    expected_format: str = "free_text"
    priority: str = "high"


@dataclass
class DomainKBResult:
    """Distilled domain knowledge base (Zirkel 0, Phase 5)."""

    hub_name: str
    vertical: str
    glossary: dict[str, str] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    scope_boundaries: list[str] = field(default_factory=list)
    expert_signoff: str = ""
    signoff_date: str = ""
    markdown: str = ""


# ── UC Quality Results ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class QualityCriterion:
    """Single quality criterion with pass/fail and evidence."""

    name: str
    description: str
    passed: bool
    evidence: str = ""
    suggestion: str = ""


@dataclass
class UCQualityResult:
    """Result of UC quality check (Zirkel 1)."""

    uc_slug: str
    criteria: list[QualityCriterion] = field(default_factory=list)
    overall_score: float = 0.0
    passed: bool = False
    iteration: int = 1

    @property
    def failed_criteria(self) -> list[QualityCriterion]:
        return [c for c in self.criteria if not c.passed]

    @property
    def score_percent(self) -> int:
        if not self.criteria:
            return 0
        return int(sum(1 for c in self.criteria if c.passed) / len(self.criteria) * 100)


@dataclass
class UCValidationResult:
    """Result of UC validation against KB + ADRs."""

    valid: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adr_conflicts: list[str] = field(default_factory=list)


# ── Failure Classification Results ─────────────────────────────────────────


@dataclass(frozen=True)
class ClassifyResult:
    """Result of failure classification (Zirkel 2)."""

    failure_type: FailureType
    confidence: float
    reasoning: str
    suggested_action: str
    affected_criterion: str = ""


# ── Test Run Results ───────────────────────────────────────────────────────


@dataclass
class TestRunResult:
    """Result of a Playwright test run."""

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    failures: list[TestFailureInfo] = field(default_factory=list)
    stdout: str = ""
    report_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped + self.errors

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0


@dataclass(frozen=True)
class TestFailureInfo:
    """Single test failure with classification."""

    test_name: str
    error_message: str
    classification: ClassifyResult | None = None
    screenshot_path: str = ""


# ── UI Audit Types ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HTMXFinding:
    """HTMX validation finding (U-1)."""

    element: str
    pattern: str
    severity: Severity
    message: str
    line: int = 0


@dataclass(frozen=True)
class TestIDCoverage:
    """data-testid coverage metrics (U-3)."""

    total_interactive: int
    with_testid: int
    missing: list[str] = field(default_factory=list)

    @property
    def coverage_percent(self) -> float:
        if self.total_interactive == 0:
            return 100.0
        return self.with_testid / self.total_interactive * 100


@dataclass(frozen=True)
class ViewportResult:
    """Responsive test result for a single viewport (U-4)."""

    name: str
    width: int
    height: int
    has_horizontal_scroll: bool = False
    small_touch_targets: list[str] = field(default_factory=list)
    screenshot_path: str = ""


@dataclass
class PermissionTestResult:
    """Permission matrix test result (U-6)."""

    url: str
    role: str
    expected_status: int
    actual_status: int

    @property
    def passed(self) -> bool:
        return self.expected_status == self.actual_status
