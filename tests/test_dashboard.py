"""Tests for reflex.dashboard module."""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reflex.dashboard import (
    HUBS,
    DashboardHandler,
    HubStatus,
    check_hub_health,
    generate_dashboard_html,
    get_cached_status,
    refresh_all_health,
    run_dashboard,
    start_hub,
    stop_hub,
)


# ── Hub Registry ──────────────────────────────────────────────────────────────


class TestHubRegistry:
    """Test hub data integrity."""

    def test_should_have_at_least_15_hubs(self):
        assert len(HUBS) >= 15

    def test_should_have_unique_slugs(self):
        slugs = [h["slug"] for h in HUBS]
        assert len(slugs) == len(set(slugs))

    def test_should_have_required_fields(self):
        required = {"name", "slug", "description", "icon", "color", "category", "port"}
        for hub in HUBS:
            missing = required - set(hub.keys())
            assert not missing, f"{hub['slug']} missing: {missing}"

    def test_should_have_valid_categories(self):
        valid = {"product", "internal", "infra"}
        for hub in HUBS:
            assert hub["category"] in valid, f"{hub['slug']}: {hub['category']}"

    def test_should_have_numeric_ports(self):
        for hub in HUBS:
            assert isinstance(hub["port"], int), f"{hub['slug']}: port is {type(hub['port'])}"
            assert hub["port"] > 0, f"{hub['slug']}: port={hub['port']}"


# ── Health Check ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    """Test hub health checking."""

    def test_should_return_unhealthy_for_unreachable_port(self):
        # Port 19999 should not be in use
        st = check_hub_health("test-hub", 19999, timeout=0.5)
        assert not st.healthy
        assert st.slug == "test-hub"

    def test_should_return_hub_status_dataclass(self):
        st = HubStatus(slug="demo")
        assert st.slug == "demo"
        assert not st.healthy
        assert st.response_ms == 0
        assert st.compose_file == ""

    @patch("reflex.dashboard.urlopen")
    def test_should_detect_healthy_hub(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        st = check_hub_health("test-hub", 8000)
        assert st.healthy

    def test_should_cache_status(self):
        # Empty cache initially after module load
        cached = get_cached_status()
        assert isinstance(cached, dict)


# ── Docker Control ────────────────────────────────────────────────────────────


class TestDockerControl:
    """Test docker compose start/stop."""

    def test_should_fail_for_nonexistent_repo(self, tmp_path):
        result = start_hub("nonexistent-hub", str(tmp_path))
        assert not result["ok"]
        assert "not found" in result["error"].lower()

    def test_should_fail_without_compose_file(self, tmp_path):
        (tmp_path / "test-hub").mkdir()
        result = start_hub("test-hub", str(tmp_path))
        assert not result["ok"]
        assert "docker-compose" in result["error"].lower()

    @patch("reflex.dashboard.subprocess.run")
    def test_should_start_with_compose(self, mock_run, tmp_path):
        hub_dir = tmp_path / "test-hub"
        hub_dir.mkdir()
        (hub_dir / "docker-compose.yml").write_text("version: '3'")
        mock_run.return_value = MagicMock(returncode=0)
        result = start_hub("test-hub", str(tmp_path))
        assert result["ok"]
        mock_run.assert_called_once()

    @patch("reflex.dashboard.subprocess.run")
    def test_should_stop_with_compose(self, mock_run, tmp_path):
        hub_dir = tmp_path / "test-hub"
        hub_dir.mkdir()
        (hub_dir / "docker-compose.yml").write_text("version: '3'")
        mock_run.return_value = MagicMock(returncode=0)
        result = stop_hub("test-hub", str(tmp_path))
        assert result["ok"]

    def test_stop_should_fail_for_nonexistent_repo(self, tmp_path):
        result = stop_hub("nonexistent-hub", str(tmp_path))
        assert not result["ok"]


# ── HTML Generation ───────────────────────────────────────────────────────────


class TestHTMLGeneration:
    """Test dashboard HTML output."""

    def test_should_generate_valid_html(self):
        html = generate_dashboard_html()
        assert "<!DOCTYPE html>" in html
        assert "IIL Platform" in html
        assert "Local Development" in html

    def test_should_contain_all_hub_cards(self):
        html = generate_dashboard_html()
        for hub in HUBS:
            assert hub["slug"] in html, f"Missing: {hub['slug']}"

    def test_should_include_search_and_filter(self):
        html = generate_dashboard_html()
        assert 'id="search"' in html
        assert "filter-btn" in html

    def test_should_include_start_buttons(self):
        html = generate_dashboard_html()
        for hub in HUBS:
            assert f'id="btn-{hub["slug"]}"' in html

    def test_should_include_api_endpoints(self):
        html = generate_dashboard_html()
        assert "/api/status" in html
        assert "api/" in html
        assert "toggleHub" in html


# ── Refresh ───────────────────────────────────────────────────────────────────


class TestRefreshHealth:
    """Test background health refresh."""

    def test_should_return_status_dict(self, tmp_path):
        # Create fake repo dirs
        for hub in HUBS[:3]:
            (tmp_path / hub["slug"]).mkdir()
        results = refresh_all_health(str(tmp_path))
        assert isinstance(results, dict)
        assert len(results) >= 1
