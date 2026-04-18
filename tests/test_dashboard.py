"""Tests for reflex.dashboard module."""

from __future__ import annotations

import json
import threading
import time
from collections import Counter
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reflex.dashboard import (
    COMPOSE_FILES,
    HUBS,
    DashboardHandler,
    HubStatus,
    check_hub_health,
    find_compose_file,
    generate_dashboard_html,
    get_cached_status,
    refresh_all_health,
    run_dashboard,
    start_hub,
    stop_hub,
)


# ── Hub Registry — Data Integrity ─────────────────────────────────────────────


class TestHubRegistry:
    """Test hub data integrity — catches silent config bugs."""

    def test_should_have_at_least_15_hubs(self):
        assert len(HUBS) >= 15

    def test_should_have_unique_slugs(self):
        slugs = [h["slug"] for h in HUBS]
        dupes = [s for s, c in Counter(slugs).items() if c > 1]
        assert not dupes, f"Duplicate slugs: {dupes}"

    def test_should_have_unique_ports(self):
        """Port collisions cause health checks to report wrong hub."""
        ports = [(h["slug"], h["port"]) for h in HUBS]
        seen: dict[int, str] = {}
        collisions = []
        for slug, port in ports:
            if port in seen:
                collisions.append(f"Port {port}: {seen[port]} vs {slug}")
            seen[port] = slug
        assert not collisions, f"Port collisions: {collisions}"

    def test_should_have_required_fields(self):
        required = {"name", "slug", "description", "icon", "color", "category", "port"}
        for hub in HUBS:
            missing = required - set(hub.keys())
            assert not missing, f"{hub['slug']} missing: {missing}"

    def test_should_have_valid_categories(self):
        valid = {"product", "internal", "infra"}
        for hub in HUBS:
            assert hub["category"] in valid, f"{hub['slug']}: {hub['category']}"

    def test_should_have_numeric_ports_above_1024(self):
        for hub in HUBS:
            assert isinstance(hub["port"], int), f"{hub['slug']}: port is {type(hub['port'])}"
            assert hub["port"] > 1024, f"{hub['slug']}: port={hub['port']} (must be >1024)"
            assert hub["port"] < 65536, f"{hub['slug']}: port={hub['port']} out of range"

    def test_should_have_sort_order(self):
        for hub in HUBS:
            assert "sort_order" in hub, f"{hub['slug']} missing sort_order"
            assert isinstance(hub["sort_order"], int), f"{hub['slug']}: sort_order not int"


# ── Compose File Discovery ────────────────────────────────────────────────────


class TestComposeFileDiscovery:
    """Test find_compose_file() and COMPOSE_FILES constant."""

    def test_should_include_prod_yml(self):
        """docker-compose.prod.yml is the only compose file in most repos."""
        assert "docker-compose.prod.yml" in COMPOSE_FILES

    def test_should_prefer_dev_over_prod(self):
        """Dev compose should be found before prod to avoid port conflicts."""
        dev_idx = COMPOSE_FILES.index("docker-compose.yml")
        prod_idx = COMPOSE_FILES.index("docker-compose.prod.yml")
        assert dev_idx < prod_idx, "docker-compose.yml must come before .prod.yml"

    def test_should_find_docker_compose_yml(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text("version: '3'")
        assert find_compose_file(tmp_path) == "docker-compose.yml"

    def test_should_find_prod_yml(self, tmp_path):
        (tmp_path / "docker-compose.prod.yml").write_text("version: '3'")
        assert find_compose_file(tmp_path) == "docker-compose.prod.yml"

    def test_should_find_local_yml(self, tmp_path):
        (tmp_path / "docker-compose.local.yml").write_text("version: '3'")
        assert find_compose_file(tmp_path) == "docker-compose.local.yml"

    def test_should_prefer_dev_compose_over_prod(self, tmp_path):
        """When both exist, prefer dev compose."""
        (tmp_path / "docker-compose.yml").write_text("version: '3'")
        (tmp_path / "docker-compose.prod.yml").write_text("version: '3'")
        assert find_compose_file(tmp_path) == "docker-compose.yml"

    def test_should_return_none_for_empty_dir(self, tmp_path):
        assert find_compose_file(tmp_path) is None


# ── Health Check ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    """Test hub health checking."""

    def test_should_return_unhealthy_for_unreachable_port(self):
        st = check_hub_health("test-hub", 19999, timeout=0.5)
        assert not st.healthy
        assert st.slug == "test-hub"
        assert st.response_ms == 0

    def test_should_return_hub_status_dataclass(self):
        st = HubStatus(slug="demo")
        assert st.slug == "demo"
        assert not st.healthy
        assert st.response_ms == 0
        assert st.compose_file == ""
        assert st.repo_path == ""
        assert not st.starting

    @patch("reflex.dashboard.urlopen")
    def test_should_detect_healthy_hub(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value = mock_resp
        st = check_hub_health("test-hub", 8000)
        assert st.healthy
        assert st.response_ms >= 0

    @patch("reflex.dashboard.urlopen")
    def test_should_try_healthz_if_livez_fails(self, mock_urlopen):
        """Falls back from /livez/ to /healthz/."""
        from urllib.error import URLError

        call_count = 0

        def side_effect(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "/livez/" in url:
                raise URLError("Connection refused")
            resp = MagicMock()
            resp.status = 200
            return resp

        mock_urlopen.side_effect = side_effect
        st = check_hub_health("test-hub", 8000)
        assert st.healthy
        assert call_count == 2  # tried /livez/ then /healthz/

    def test_should_cache_status(self):
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
    def test_should_start_with_compose_yml(self, mock_run, tmp_path):
        hub_dir = tmp_path / "test-hub"
        hub_dir.mkdir()
        (hub_dir / "docker-compose.yml").write_text("version: '3'")
        mock_run.return_value = MagicMock(returncode=0)
        result = start_hub("test-hub", str(tmp_path))
        assert result["ok"]
        cmd = mock_run.call_args[0][0]
        assert "docker-compose.yml" in cmd

    @patch("reflex.dashboard.subprocess.run")
    def test_should_start_with_prod_yml_fallback(self, mock_run, tmp_path):
        """Repos with only docker-compose.prod.yml must still be startable."""
        hub_dir = tmp_path / "test-hub"
        hub_dir.mkdir()
        (hub_dir / "docker-compose.prod.yml").write_text("version: '3'")
        mock_run.return_value = MagicMock(returncode=0)
        result = start_hub("test-hub", str(tmp_path))
        assert result["ok"]
        cmd = mock_run.call_args[0][0]
        assert "docker-compose.prod.yml" in cmd

    @patch("reflex.dashboard.subprocess.run")
    def test_should_stop_with_compose(self, mock_run, tmp_path):
        hub_dir = tmp_path / "test-hub"
        hub_dir.mkdir()
        (hub_dir / "docker-compose.yml").write_text("version: '3'")
        mock_run.return_value = MagicMock(returncode=0)
        result = stop_hub("test-hub", str(tmp_path))
        assert result["ok"]

    @patch("reflex.dashboard.subprocess.run")
    def test_should_report_docker_errors(self, mock_run, tmp_path):
        hub_dir = tmp_path / "test-hub"
        hub_dir.mkdir()
        (hub_dir / "docker-compose.yml").write_text("version: '3'")
        mock_run.return_value = MagicMock(returncode=1, stderr="image not found")
        result = start_hub("test-hub", str(tmp_path))
        assert not result["ok"]
        assert "image not found" in result["error"]

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
            assert f'data-slug="{hub["slug"]}"' in html, f"Missing card: {hub['slug']}"

    def test_should_embed_correct_ports_in_cards(self):
        """Each card must have its hub's port as data-port."""
        html = generate_dashboard_html()
        for hub in HUBS:
            expected = f'data-slug="{hub["slug"]}" data-port="{hub["port"]}"'
            assert expected in html, f"{hub['slug']}: port mismatch in HTML"

    def test_should_include_search_and_filter(self):
        html = generate_dashboard_html()
        assert 'id="search"' in html
        assert "filter-btn" in html
        assert '"Running"' in html or "Running" in html

    def test_should_include_start_buttons(self):
        html = generate_dashboard_html()
        for hub in HUBS:
            assert f'id="btn-{hub["slug"]}"' in html

    def test_should_include_health_dots(self):
        html = generate_dashboard_html()
        for hub in HUBS:
            assert f'id="dot-{hub["slug"]}"' in html

    def test_should_include_api_endpoints_in_js(self):
        html = generate_dashboard_html()
        assert "/api/status" in html
        assert "toggleHub" in html


# ── Refresh ───────────────────────────────────────────────────────────────────


class TestRefreshHealth:
    """Test background health refresh."""

    def test_should_return_status_for_all_hubs(self, tmp_path):
        for hub in HUBS:
            (tmp_path / hub["slug"]).mkdir()
        with patch("reflex.dashboard.check_hub_health") as mock_check:
            mock_check.return_value = HubStatus(slug="x", healthy=False)
            results = refresh_all_health(str(tmp_path))
        assert len(results) == len(HUBS)

    def test_should_detect_compose_file_in_refresh(self, tmp_path):
        hub_dir = tmp_path / "risk-hub"
        hub_dir.mkdir()
        (hub_dir / "docker-compose.prod.yml").write_text("version: '3'")
        with patch("reflex.dashboard.check_hub_health") as mock_check:
            mock_check.return_value = HubStatus(slug="risk-hub")
            results = refresh_all_health(str(tmp_path))
        assert results["risk-hub"].compose_file == "docker-compose.prod.yml"

    def test_should_set_repo_path(self, tmp_path):
        hub_dir = tmp_path / "bfagent"
        hub_dir.mkdir()
        with patch("reflex.dashboard.check_hub_health") as mock_check:
            mock_check.return_value = HubStatus(slug="bfagent")
            results = refresh_all_health(str(tmp_path))
        assert results["bfagent"].repo_path == str(hub_dir)

    def test_should_update_cache(self, tmp_path):
        with patch("reflex.dashboard.check_hub_health") as mock_check:
            mock_check.return_value = HubStatus(slug="x", healthy=False)
            refresh_all_health(str(tmp_path))
        cached = get_cached_status()
        assert len(cached) >= 1
