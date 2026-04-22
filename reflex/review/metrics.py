"""
REFLEX Metrics Writer — Persist review results to PostgreSQL (ADR-165 §6).

Writes one row per plugin per run to `reflex_metrics`.
Table is auto-created if missing.

Usage:
    from reflex.review.metrics import MetricsWriter
    writer = MetricsWriter()  # reads DATABASE_URL from env
    writer.write_results(results)
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from reflex.review.types import ReviewResult

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reflex_metrics (
    id              BIGSERIAL PRIMARY KEY,
    run_ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    repo            VARCHAR(128) NOT NULL,
    plugin          VARCHAR(64)  NOT NULL,
    score_pct       REAL         NOT NULL,
    findings_total  INT          NOT NULL DEFAULT 0,
    findings_block  INT          NOT NULL DEFAULT 0,
    findings_warn   INT          NOT NULL DEFAULT 0,
    findings_info   INT          NOT NULL DEFAULT 0,
    auto_fixable    INT          NOT NULL DEFAULT 0,
    duration_s      REAL         NOT NULL DEFAULT 0,
    triggered_by    VARCHAR(64)  NOT NULL DEFAULT 'cli'
);

CREATE INDEX IF NOT EXISTS idx_reflex_metrics_repo_ts
    ON reflex_metrics (repo, run_ts DESC);
"""

INSERT_SQL = """
INSERT INTO reflex_metrics
    (run_ts, repo, plugin, score_pct, findings_total, findings_block,
     findings_warn, findings_info, auto_fixable, duration_s, triggered_by)
VALUES
    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class MetricsWriter:
    """Write REFLEX review results to PostgreSQL."""

    def __init__(self, database_url: str | None = None):
        self._url = database_url or os.environ.get(  # hardcoded-ok: CLI package, decouple not a dependency
            "REFLEX_DATABASE_URL",
            os.environ.get("DATABASE_URL", ""),  # hardcoded-ok: CLI package, decouple not a dependency
        )
        self._conn = None

    def _connect(self):
        if self._conn is not None:
            return
        try:
            import psycopg

            self._conn = psycopg.connect(self._url, autocommit=True)
            self._conn.execute(CREATE_TABLE_SQL)
            logger.debug("MetricsWriter: connected + table ensured")
        except ImportError:
            logger.warning("psycopg not installed — pip install psycopg[binary] for metrics")
            raise
        except Exception:
            logger.error("MetricsWriter: DB connection failed", exc_info=True)
            raise

    def write_results(self, results: list[ReviewResult]) -> int:
        """Write review results to DB. Returns number of rows written."""
        if not self._url:
            logger.warning("No DATABASE_URL — metrics not persisted")
            return 0

        try:
            self._connect()
        except Exception:
            return 0

        now = datetime.now(UTC)
        rows = 0
        for r in results:
            try:
                self._conn.execute(
                    INSERT_SQL,
                    (
                        now,
                        r.repo,
                        r.review_type,
                        r.score_pct,
                        len(r.findings),
                        len(r.findings_block),
                        len(r.findings_warn),
                        len(r.findings_info),
                        len(r.findings_auto_fixable),
                        r.duration_s,
                        r.triggered_by,
                    ),
                )
                rows += 1
            except Exception:
                logger.error(
                    "Failed to write metric for %s/%s",
                    r.repo,
                    r.review_type,
                    exc_info=True,
                )
        if rows:
            logger.info("MetricsWriter: %d rows written for %s", rows, results[0].repo)
        return rows

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
