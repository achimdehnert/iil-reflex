"""
REFLEX Review Engine — Plugin discovery, execution, baseline, suppression (ADR-165 §5.1).

Usage:
    from reflex.review import run_review
    result = run_review(repo="risk-hub", types=["repo", "compose"])
"""

from __future__ import annotations

import importlib
import json
import logging
import pkgutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import yaml

from reflex.review.types import (
    Finding,
    ReviewResult,
    SuppressionEntry,
)

logger = logging.getLogger(__name__)

# ── Plugin Protocol ──────────────────────────────────────────────────────────


@runtime_checkable
class ReviewPlugin(Protocol):
    """Protocol for review plugins (ADR-165 §5.1).

    Every plugin must expose:
        name: str               — e.g. "compose"
        applicable_tiers: list  — e.g. [1, 2]
        check(repo, context)    — returns list[Finding]
    """

    name: str
    applicable_tiers: list[int]

    def check(self, repo: str, context: dict) -> list[Finding]: ...


# ── Suppression + Baseline ───────────────────────────────────────────────────


def _load_suppressions(repo_path: Path) -> list[SuppressionEntry]:
    """Load .reflex/suppressions.yaml if it exists."""
    supp_file = repo_path / ".reflex" / "suppressions.yaml"
    if not supp_file.exists():
        return []
    try:
        raw = yaml.safe_load(supp_file.read_text(encoding="utf-8")) or {}
        entries = []
        for item in raw.get("suppressions", []):
            entries.append(
                SuppressionEntry(
                    rule_id=item.get("rule_id", ""),
                    reason=item.get("reason", ""),
                    until=item.get("until"),
                    permanent=item.get("permanent", False),
                )
            )
        return entries
    except Exception:
        logger.warning("Failed to load suppressions from %s", supp_file)
        return []


def _load_baseline(repo_path: Path) -> set[str]:
    """Load .reflex/baseline.json → set of rule_ids in baseline."""
    baseline_file = repo_path / ".reflex" / "baseline.json"
    if not baseline_file.exists():
        return set()
    try:
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        return {f["rule_id"] for f in data.get("findings", [])}
    except Exception:
        logger.warning("Failed to load baseline from %s", baseline_file)
        return set()


def _save_baseline(repo_path: Path, findings: list[Finding]) -> Path:
    """Save current findings as baseline in .reflex/baseline.json."""
    baseline_dir = repo_path / ".reflex"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = baseline_dir / "baseline.json"
    data = {
        "created_at": datetime.now(UTC).isoformat(),
        "findings": [f.to_dict() for f in findings],
    }
    baseline_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return baseline_file


# ── Plugin Discovery ─────────────────────────────────────────────────────────


def _discover_plugins() -> dict[str, ReviewPlugin]:
    """Auto-discover all plugins in reflex.review.plugins package."""
    import reflex.review.plugins as plugins_pkg

    discovered: dict[str, ReviewPlugin] = {}
    for _importer, modname, _ispkg in pkgutil.iter_modules(plugins_pkg.__path__):
        if modname.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"reflex.review.plugins.{modname}")
            # Convention: each plugin module has a `plugin` attribute
            if hasattr(mod, "plugin"):
                p = mod.plugin
                if isinstance(p, ReviewPlugin):
                    discovered[p.name] = p
                    logger.debug("Discovered review plugin: %s", p.name)
        except Exception:
            logger.warning("Failed to load review plugin: %s", modname, exc_info=True)
    return discovered


# ── Review Engine ────────────────────────────────────────────────────────────


class ReviewEngine:
    """Orchestrates plugin execution with baseline and suppression (ADR-165).

    Usage:
        engine = ReviewEngine()
        results = engine.run(repo="risk-hub", types=["repo", "compose"])
    """

    def __init__(self, github_dir: str | Path | None = None):
        self.github_dir = Path(github_dir) if github_dir else Path.home() / "github"
        self._plugins: dict[str, ReviewPlugin] = _discover_plugins()

    @property
    def available_plugins(self) -> list[str]:
        return sorted(self._plugins.keys())

    def run(
        self,
        repo: str,
        types: list[str] | None = None,
        *,
        triggered_by: str = "manual",
        include_baseline: bool = False,
        init_baseline: bool = False,
        context: dict | None = None,
    ) -> list[ReviewResult]:
        """Run review plugins for a repo.

        Args:
            repo: Repository name (e.g. "risk-hub")
            types: Plugin names to run. None = all available.
            triggered_by: What triggered this review
            include_baseline: Include baseline findings in results
            init_baseline: Save current findings as new baseline
            context: Extra context dict passed to plugins

        Returns:
            List of ReviewResult, one per plugin
        """
        repo_path = self.github_dir / repo
        ctx = {
            "repo_path": str(repo_path),
            "github_dir": str(self.github_dir),
            **(context or {}),
        }

        # Determine which plugins to run
        plugin_names = types or list(self._plugins.keys())
        plugins_to_run = [
            self._plugins[name]
            for name in plugin_names
            if name in self._plugins
        ]

        if not plugins_to_run:
            logger.warning("No matching plugins found for types=%s", types)
            return []

        # Load suppressions and baseline
        suppressions = _load_suppressions(repo_path)
        suppressed_ids = {
            s.rule_id
            for s in suppressions
            if s.permanent or (s.until and not s.is_expired)
        }
        baseline_ids = _load_baseline(repo_path) if not init_baseline else set()

        results: list[ReviewResult] = []
        for plug in plugins_to_run:
            start = time.monotonic()
            try:
                raw_findings = plug.check(repo, ctx)
            except Exception:
                logger.error("Plugin %s failed for %s", plug.name, repo, exc_info=True)
                raw_findings = []
            duration = round(time.monotonic() - start, 3)

            # Filter: suppressions
            findings = [
                f for f in raw_findings if f.rule_id not in suppressed_ids
            ]

            # Filter: baseline (unless include_baseline or init_baseline)
            if not include_baseline and not init_baseline and baseline_ids:
                findings = [f for f in findings if f.rule_id not in baseline_ids]

            # Capture plugin-specific metrics if available
            plugin_meta = getattr(plug, "last_metrics", {})

            result = ReviewResult(
                repo=repo,
                review_type=plug.name,
                findings=findings,
                duration_s=duration,
                triggered_by=triggered_by,
                metadata=plugin_meta if plugin_meta else {},
            )
            results.append(result)

        # Init baseline if requested
        if init_baseline:
            all_findings = [f for r in results for f in r.findings]
            _save_baseline(repo_path, all_findings)

        return results


# ── Convenience function ─────────────────────────────────────────────────────


def run_review(
    repo: str,
    types: list[str] | None = None,
    *,
    github_dir: str | Path | None = None,
    triggered_by: str = "manual",
    include_baseline: bool = False,
    init_baseline: bool = False,
    context: dict | None = None,
) -> list[ReviewResult]:
    """Run a review — convenience wrapper for ReviewEngine (ADR-165 §5.2).

    This is the primary entry point for both CLI and MCP usage:
        from reflex.review import run_review
        results = run_review(repo="risk-hub", types=["repo", "compose"])
    """
    engine = ReviewEngine(github_dir=github_dir)
    return engine.run(
        repo=repo,
        types=types,
        triggered_by=triggered_by,
        include_baseline=include_baseline,
        init_baseline=init_baseline,
        context=context,
    )
