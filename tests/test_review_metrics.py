"""Tests for reflex.review.metrics — MetricsWriter PostgreSQL persistence (ADR-165 §6).

psycopg is an optional dependency (`pip install iil-reflex[metrics]`); these tests
inject a mock `psycopg` module into sys.modules so they run without a real driver/DB.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from reflex.review.metrics import INSERT_SQL, MetricsWriter
from reflex.review.types import Finding, ReviewResult, ReviewSeverity


def _make_result() -> ReviewResult:
    return ReviewResult(
        repo="demo-hub",
        review_type="compose",
        findings=[
            Finding("compose.port", ReviewSeverity.BLOCK, "port mismatch", auto_fixable=True),
            Finding("compose.img", ReviewSeverity.WARN, "no pinned tag"),
            Finding("compose.note", ReviewSeverity.INFO, "fyi"),
        ],
        duration_s=1.5,
        triggered_by="cli",
    )


@pytest.fixture
def mock_psycopg(monkeypatch):
    """Inject a mock `psycopg` module so `import psycopg` inside _connect resolves."""
    conn = MagicMock(name="connection")
    module = MagicMock(name="psycopg")
    module.connect.return_value = conn
    monkeypatch.setitem(sys.modules, "psycopg", module)
    return module, conn


class TestMetricsWriterNoUrl:
    def test_should_return_zero_when_no_database_url(self, monkeypatch):
        monkeypatch.delenv("REFLEX_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        writer = MetricsWriter()
        assert writer.write_results([_make_result()]) == 0

    def test_should_read_url_from_reflex_database_url_first(self, monkeypatch):
        monkeypatch.setenv("REFLEX_DATABASE_URL", "postgresql://reflex")
        monkeypatch.setenv("DATABASE_URL", "postgresql://fallback")
        assert MetricsWriter()._url == "postgresql://reflex"


class TestMetricsWriterWrite:
    def test_should_write_one_row_per_result_and_return_count(self, mock_psycopg):
        _module, conn = mock_psycopg
        writer = MetricsWriter(database_url="postgresql://x")
        rows = writer.write_results([_make_result(), _make_result()])
        assert rows == 2
        # 1 CREATE TABLE on connect + 2 INSERTs
        insert_calls = [c for c in conn.execute.call_args_list if c.args[0] == INSERT_SQL]
        assert len(insert_calls) == 2

    def test_should_pass_correct_finding_counts_to_insert(self, mock_psycopg):
        _module, conn = mock_psycopg
        writer = MetricsWriter(database_url="postgresql://x")
        writer.write_results([_make_result()])
        insert = next(c for c in conn.execute.call_args_list if c.args[0] == INSERT_SQL)
        params = insert.args[1]
        # (run_ts, repo, plugin, score_pct, total, block, warn, info, auto_fixable, dur, by)
        assert params[1] == "demo-hub"
        assert params[2] == "compose"
        assert params[4] == 3  # findings_total
        assert params[5] == 1  # block
        assert params[6] == 1  # warn
        assert params[7] == 1  # info
        assert params[8] == 1  # auto_fixable
        assert params[10] == "cli"

    def test_should_create_table_on_connect(self, mock_psycopg):
        _module, conn = mock_psycopg
        writer = MetricsWriter(database_url="postgresql://x")
        writer.write_results([_make_result()])
        ddl_calls = [c for c in conn.execute.call_args_list if "CREATE TABLE" in c.args[0]]
        assert ddl_calls, "expected CREATE TABLE IF NOT EXISTS on first connect"


class TestMetricsWriterDegradation:
    def test_should_return_zero_when_psycopg_missing(self, monkeypatch):
        # Simulate psycopg not installed: import raises ImportError.
        monkeypatch.setitem(sys.modules, "psycopg", None)
        writer = MetricsWriter(database_url="postgresql://x")
        assert writer.write_results([_make_result()]) == 0

    def test_should_close_idempotently(self, mock_psycopg):
        _module, conn = mock_psycopg
        writer = MetricsWriter(database_url="postgresql://x")
        writer.write_results([_make_result()])
        writer.close()
        writer.close()  # second call is a no-op, must not raise
        conn.close.assert_called_once()
