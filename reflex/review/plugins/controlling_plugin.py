"""
REFLEX Review Plugin: controlling — Quality metrics and optimization insights (ADR-165 §6).

Analyzes review history, baseline freshness, suppression expiry,
and cross-repo coverage to surface optimization opportunities.

Requires: REFLEX_DATABASE_URL env var for trend analysis.
Works without DB — baseline/suppression checks are file-based.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)

logger = logging.getLogger(__name__)


class ControllingPlugin:
    name = "controlling"
    applicable_tiers = [1, 2, 3]

    def check(self, repo: str, context: dict) -> list[Finding]:
        repo_path = Path(context.get("repo_path", ""))
        github_dir = Path(context.get("github_dir", ""))
        if not repo_path.exists():
            return []

        findings: list[Finding] = []

        # 1. Baseline freshness
        findings.extend(self._check_baseline_freshness(repo_path, repo))

        # 2. Suppression expiry
        findings.extend(self._check_suppression_expiry(repo_path, repo))

        # 3. reflex.yaml completeness (TODOs remaining)
        findings.extend(self._check_config_completeness(repo_path, repo))

        # 4. Metrics trend (DB-dependent, graceful fallback)
        findings.extend(self._check_metrics_trend(repo))

        # 5. Cross-repo coverage (only if github_dir available)
        if github_dir.exists():
            findings.extend(self._check_platform_coverage(github_dir, repo))

        return findings

    def _check_baseline_freshness(self, repo_path: Path, repo: str) -> list[Finding]:
        """Stale baselines hide accumulated tech debt."""
        baseline_file = repo_path / ".reflex" / "baseline.json"
        if not baseline_file.exists():
            return [
                Finding(
                    rule_id="controlling.no_baseline",
                    severity=ReviewSeverity.WARN,
                    message=f"{repo}: No baseline set — run 'reflex review all {repo} --init-baseline'",
                    fix_hint=f"reflex review all {repo} --init-baseline",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            ]

        try:
            data = json.loads(baseline_file.read_text(encoding="utf-8"))
            created = data.get("created_at", "")
            if created:
                baseline_dt = datetime.fromisoformat(created)
                if baseline_dt.tzinfo is None:
                    baseline_dt = baseline_dt.replace(tzinfo=UTC)
                age_days = (datetime.now(UTC) - baseline_dt).days
                finding_count = len(data.get("findings", []))

                if age_days > 90 and finding_count > 0:
                    return [
                        Finding(
                            rule_id="controlling.stale_baseline",
                            severity=ReviewSeverity.WARN,
                            message=(
                                f"{repo}: Baseline is {age_days} days old with "
                                f"{finding_count} suppressed findings — review and update"
                            ),
                            fix_hint=f"reflex review all {repo} --include-baseline  # then fix or re-baseline",
                            fix_complexity=FixComplexity.MODERATE,
                        )
                    ]
                elif age_days > 30 and finding_count > 20:
                    return [
                        Finding(
                            rule_id="controlling.baseline_high_debt",
                            severity=ReviewSeverity.INFO,
                            message=(
                                f"{repo}: {finding_count} findings in baseline (age: {age_days}d) "
                                f"— consider scheduling a cleanup sprint"
                            ),
                        )
                    ]
        except Exception:
            pass
        return []

    def _check_suppression_expiry(self, repo_path: Path, repo: str) -> list[Finding]:
        """Expired suppressions should be re-evaluated."""
        supp_file = repo_path / ".reflex" / "suppressions.yaml"
        if not supp_file.exists():
            return []

        findings = []
        try:
            raw = yaml.safe_load(supp_file.read_text(encoding="utf-8")) or {}
            for item in raw.get("suppressions", []):
                until = item.get("until")
                if not until:
                    continue
                try:
                    expiry = datetime.fromisoformat(str(until))
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=UTC)
                    if datetime.now(UTC) > expiry:
                        findings.append(
                            Finding(
                                rule_id="controlling.suppression_expired",
                                severity=ReviewSeverity.BLOCK,
                                message=(
                                    f"{repo}: Suppression for '{item.get('rule_id')}' "
                                    f"expired on {until} — re-evaluate or make permanent"
                                ),
                                file_path=".reflex/suppressions.yaml",
                                fix_complexity=FixComplexity.TRIVIAL,
                            )
                        )
                    elif (expiry - datetime.now(UTC)).days < 7:
                        findings.append(
                            Finding(
                                rule_id="controlling.suppression_expiring_soon",
                                severity=ReviewSeverity.WARN,
                                message=(
                                    f"{repo}: Suppression for '{item.get('rule_id')}' "
                                    f"expires in {(expiry - datetime.now(UTC)).days} days"
                                ),
                                file_path=".reflex/suppressions.yaml",
                                fix_complexity=FixComplexity.TRIVIAL,
                            )
                        )
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass
        return findings

    def _check_config_completeness(self, repo_path: Path, repo: str) -> list[Finding]:
        """Unfinished TODOs in reflex.yaml indicate incomplete setup."""
        config_file = repo_path / "reflex.yaml"
        if not config_file.exists():
            return []

        content = config_file.read_text(encoding="utf-8", errors="ignore")
        todo_count = content.count("TODO")
        if todo_count >= 3:
            return [
                Finding(
                    rule_id="controlling.config_incomplete",
                    severity=ReviewSeverity.WARN,
                    message=(
                        f"{repo}: reflex.yaml has {todo_count} TODO markers "
                        f"— complete configuration for accurate reviews"
                    ),
                    file_path="reflex.yaml",
                    fix_complexity=FixComplexity.SIMPLE,
                )
            ]
        return []

    def _check_metrics_trend(self, repo: str) -> list[Finding]:
        """Check if review metrics show a worsening trend."""
        db_url = os.environ.get("REFLEX_DATABASE_URL", "")
        if not db_url:
            return [
                Finding(
                    rule_id="controlling.no_metrics_db",
                    severity=ReviewSeverity.INFO,
                    message=(
                        "REFLEX_DATABASE_URL not set — trend analysis unavailable. "
                        "Use --emit-metrics to enable Controlling."
                    ),
                )
            ]

        try:
            import psycopg

            conn = psycopg.connect(db_url, autocommit=True)

            # Check: any metrics at all for this repo?
            cur = conn.execute(
                "SELECT COUNT(*), MAX(run_ts), MIN(run_ts) "
                "FROM reflex_metrics WHERE repo = %s",
                (repo,),
            )
            row = cur.fetchone()
            total_runs, last_run, first_run = row[0], row[1], row[2]

            findings = []

            if total_runs == 0:
                findings.append(
                    Finding(
                        rule_id="controlling.no_metrics_data",
                        severity=ReviewSeverity.WARN,
                        message=(
                            f"{repo}: No metrics recorded — "
                            f"run 'reflex review all {repo} --emit-metrics' to start tracking"
                        ),
                        fix_hint=f"reflex review all {repo} --emit-metrics",
                        auto_fixable=True,
                        fix_complexity=FixComplexity.TRIVIAL,
                    )
                )
            elif last_run:
                days_since = (datetime.now(UTC) - last_run).days
                if days_since > 14:
                    findings.append(
                        Finding(
                            rule_id="controlling.metrics_stale",
                            severity=ReviewSeverity.WARN,
                            message=(
                                f"{repo}: Last metrics {days_since} days ago — "
                                f"reviews should run at least weekly"
                            ),
                        )
                    )

            # Check: score trend (compare last 2 runs)
            if total_runs >= 2:
                cur = conn.execute(
                    """
                    SELECT run_ts, SUM(findings_block) as blocks,
                           AVG(score_pct) as avg_score
                    FROM reflex_metrics
                    WHERE repo = %s
                    GROUP BY run_ts
                    ORDER BY run_ts DESC
                    LIMIT 2
                    """,
                    (repo,),
                )
                runs = cur.fetchall()
                if len(runs) == 2:
                    latest_blocks = runs[0][1]
                    prev_blocks = runs[1][1]
                    if latest_blocks > prev_blocks:
                        findings.append(
                            Finding(
                                rule_id="controlling.regression_detected",
                                severity=ReviewSeverity.BLOCK,
                                message=(
                                    f"{repo}: BLOCKs increased from {prev_blocks} to "
                                    f"{latest_blocks} — regression detected"
                                ),
                                fix_complexity=FixComplexity.MODERATE,
                            )
                        )

            conn.close()
            return findings

        except ImportError:
            return []
        except Exception as e:
            logger.debug("Controlling metrics check failed: %s", e)
            return []

    def _check_platform_coverage(self, github_dir: Path, current_repo: str) -> list[Finding]:
        """Check how many repos in the platform have reflex.yaml."""
        # Only run this check for the 'platform' scope, not per-repo
        # to avoid noisy output on every review
        if current_repo != "platform":
            return []

        total = 0
        covered = 0
        uncovered = []
        for repo_dir in sorted(github_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            compose = repo_dir / "docker-compose.prod.yml"
            if not compose.exists():
                continue
            total += 1
            if (repo_dir / "reflex.yaml").exists():
                covered += 1
            else:
                uncovered.append(repo_dir.name)

        if uncovered:
            return [
                Finding(
                    rule_id="controlling.platform_coverage",
                    severity=ReviewSeverity.INFO,
                    message=(
                        f"REFLEX coverage: {covered}/{total} repos "
                        f"({100*covered//total}%). Missing: {', '.join(uncovered[:5])}"
                        f"{'...' if len(uncovered) > 5 else ''}"
                    ),
                )
            ]
        return []


plugin = ControllingPlugin()
