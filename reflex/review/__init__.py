"""
REFLEX Review Engine — Plugin-based infrastructure review (ADR-165).

Entry point for both CLI and MCP usage:

    from reflex.review import run_review
    result = run_review(repo="risk-hub", types=["repo", "compose"])

    # CLI:
    python -m reflex review repo risk-hub --json
"""

from __future__ import annotations

from reflex.review.engine import ReviewEngine, run_review
from reflex.review.types import Finding, ReviewResult, ReviewSeverity

__all__ = [
    "Finding",
    "ReviewEngine",
    "ReviewResult",
    "ReviewSeverity",
    "run_review",
]
