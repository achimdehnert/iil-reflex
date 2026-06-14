"""Tests for reflex.platform_runner — ADR-163 platform-wide checks."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from reflex.platform_runner import (
    HubEntry,
    HubReport,
    PlatformReport,
    PlatformRunner,
)


class TestHubReport:
    """Test HubReport dataclass properties."""

    def test_should_calculate_route_pass_rate(self):
        hr = HubReport(name="test", tier=1, routes_total=10, routes_ok=8)
        assert hr.route_pass_rate == 80.0

    def test_should_handle_zero_routes(self):
        hr = HubReport(name="test", tier=2, routes_total=0, routes_ok=0)
        assert hr.route_pass_rate == 0.0

    def test_should_show_error_icon(self):
        hr = HubReport(name="test", tier=1, error="connection refused")
        assert hr.status_icon == "❌"

    def test_should_show_warning_icon_for_partial_routes(self):
        hr = HubReport(
            name="test",
            tier=1,
            routes_total=5,
            routes_ok=3,
            health_ok=True,
        )
        assert hr.status_icon == "⚠️"

    def test_should_show_healthy_icon(self):
        hr = HubReport(name="test", tier=1, health_ok=True)
        assert hr.status_icon == "✅"


class TestPlatformReport:
    """Test PlatformReport aggregations."""

    def test_should_count_tiers(self):
        report = PlatformReport(
            hubs=[
                HubReport(name="a", tier=1, health_ok=True),
                HubReport(name="b", tier=1, health_ok=True),
                HubReport(name="c", tier=2, health_ok=True),
            ]
        )
        assert len(report.tier1_hubs) == 2
        assert len(report.tier2_hubs) == 1

    def test_should_count_healthy_hubs(self):
        report = PlatformReport(
            hubs=[
                HubReport(name="a", tier=1, health_ok=True),
                HubReport(name="b", tier=2, health_ok=False, error="down"),
            ]
        )
        assert report.healthy_hubs == 1
        assert report.total_hubs == 2


class TestPlatformRunnerFromYaml:
    """Test YAML loading."""

    def test_should_load_platform_config(self, tmp_path: Path):
        config = {
            "hubs": [
                {
                    "name": "risk-hub",
                    "tier": 1,
                    "config": "/path/to/reflex.yaml",
                    "base_url": "http://localhost:8003",
                },
                {
                    "name": "billing-hub",
                    "tier": 2,
                    "config": "/path/to/reflex.yaml",
                    "base_url": "http://localhost:8006",
                },
            ]
        }
        cfg_path = tmp_path / "platform-reflex.yaml"
        cfg_path.write_text(yaml.dump(config))

        runner = PlatformRunner.from_yaml(cfg_path)
        assert len(runner.hubs) == 2
        assert runner.hubs[0].name == "risk-hub"
        assert runner.hubs[0].tier == 1
        assert runner.hubs[1].name == "billing-hub"
        assert runner.hubs[1].tier == 2

    def test_should_raise_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            PlatformRunner.from_yaml("/nonexistent/platform.yaml")


class TestPlatformRunnerOutput:
    """Test output formatters."""

    @pytest.fixture
    def sample_report(self) -> PlatformReport:
        return PlatformReport(
            generated_at="2026-04-17T23:00:00Z",
            total_duration_seconds=5.2,
            hubs=[
                HubReport(
                    name="risk-hub",
                    tier=1,
                    health_ok=True,
                    routes_total=5,
                    routes_ok=5,
                    permissions_total=10,
                    permissions_ok=10,
                    uc_count=4,
                    duration_seconds=1.2,
                ),
                HubReport(
                    name="billing-hub",
                    tier=2,
                    health_ok=True,
                    routes_total=3,
                    routes_ok=3,
                    duration_seconds=0.8,
                ),
                HubReport(
                    name="broken-hub",
                    tier=2,
                    health_ok=False,
                    error="Connection refused",
                    duration_seconds=0.1,
                ),
            ],
        )

    def test_should_produce_json(self, sample_report: PlatformReport):
        import json

        output = PlatformRunner.to_json(sample_report)
        data = json.loads(output)
        assert data["total_hubs"] == 3
        assert data["healthy_hubs"] == 2
        assert len(data["hubs"]) == 3

    def test_should_produce_markdown(self, sample_report: PlatformReport):
        md = PlatformRunner.to_markdown(sample_report)
        assert "# REFLEX Platform Health Report" in md
        assert "risk-hub" in md
        assert "billing-hub" in md
        assert "Connection refused" in md
        assert "## Tier 1" in md
        assert "## Tier 2" in md

    def test_should_print_report(self, sample_report: PlatformReport, capsys):
        PlatformRunner.print_report(sample_report)
        captured = capsys.readouterr()
        assert "risk-hub" in captured.out
        assert "REFLEX Platform Health Report" in captured.out


class TestStatusIconDefault:
    def test_should_show_blank_icon_when_down_without_error(self):
        # no error, no routes, health_ok False → ⬜
        assert HubReport(name="x", tier=2).status_icon == "⬜"


class TestRunAll:
    def test_should_aggregate_hub_reports(self):
        hubs = [
            HubEntry(name="a", tier=1, config_path="", base_url="http://a"),
            HubEntry(name="b", tier=2, config_path="", base_url="http://b"),
        ]
        runner = PlatformRunner(hubs)
        with patch.object(
            runner,
            "_check_hub",
            side_effect=lambda h: HubReport(name=h.name, tier=h.tier, health_ok=True),
        ):
            report = runner.run_all()
        assert report.total_hubs == 2
        assert report.healthy_hubs == 2
        assert report.generated_at
        assert report.total_duration_seconds >= 0.0


def _mock_client(get_return=None, get_side_effect=None):
    client = MagicMock()
    if get_side_effect is not None:
        client.get.side_effect = get_side_effect
    else:
        client.get.return_value = get_return or MagicMock(status_code=200)
    cm = MagicMock()
    cm.__enter__.return_value = client
    return cm, client


class TestCheckHub:
    def test_should_error_when_config_missing(self):
        hub = HubEntry(name="x", tier=1, config_path="/nonexistent/reflex.yaml", base_url="http://h")
        hr = PlatformRunner([hub])._check_hub(hub)
        assert "Config not found" in hr.error

    def test_should_error_when_httpx_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "httpx", None)
        hub = HubEntry(name="x", tier=2, config_path="", base_url="http://h")
        hr = PlatformRunner([hub])._check_hub(hub)
        assert "httpx not installed" in hr.error

    def test_should_check_health_routes_perms_and_ucs(self, tmp_path):
        cfg = tmp_path / "reflex.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "test_routes": [
                        {"url": "/pub/", "expect": 200, "auth": False},
                        {"url": "/secret/", "expect": 200, "auth": True},  # skipped (auth)
                    ],
                    "permissions_matrix": {"/a/": {"anon": 200, "admin": 200}},
                }
            )
        )
        uc_dir = tmp_path / "docs" / "use-cases"
        uc_dir.mkdir(parents=True)
        (uc_dir / "UC-001-x.md").write_text("x")
        (uc_dir / "UC-002-y.md").write_text("y")

        hub = HubEntry(name="risk-hub", tier=1, config_path=str(cfg), base_url="http://h")
        runner = PlatformRunner([hub])
        cm, _client = _mock_client(get_return=MagicMock(status_code=200))
        with patch("httpx.Client", return_value=cm):
            hr = runner._check_hub(hub)
        assert hr.health_ok is True
        assert hr.uc_count == 2
        assert hr.routes_total == 1  # only the auth=False route
        assert hr.routes_ok == 1
        assert hr.permissions_total == 2

    def test_should_tolerate_route_request_errors(self, tmp_path):
        cfg = tmp_path / "reflex.yaml"
        cfg.write_text(yaml.dump({"test_routes": [{"url": "/pub/", "expect": 200, "auth": False}]}))
        hub = HubEntry(name="h", tier=2, config_path=str(cfg), base_url="http://h")
        runner = PlatformRunner([hub])

        def get(url, **kw):
            if url.endswith("/livez/"):
                return MagicMock(status_code=200)
            raise RuntimeError("route down")

        cm, _client = _mock_client(get_side_effect=get)
        with patch("httpx.Client", return_value=cm):
            hr = runner._check_hub(hub)
        assert hr.health_ok is True
        assert hr.routes_total == 1
        assert hr.routes_ok == 0  # the route raised, swallowed

    def test_should_record_connection_refused(self):
        import httpx

        hub = HubEntry(name="x", tier=2, config_path="", base_url="http://h")
        runner = PlatformRunner([hub])
        cm, _client = _mock_client(get_side_effect=httpx.ConnectError("refused"))
        with patch("httpx.Client", return_value=cm):
            hr = runner._check_hub(hub)
        assert "Connection refused" in hr.error

    def test_should_record_generic_error(self):
        hub = HubEntry(name="x", tier=2, config_path="", base_url="http://h")
        runner = PlatformRunner([hub])
        cm, _client = _mock_client(get_side_effect=RuntimeError("boom"))
        with patch("httpx.Client", return_value=cm):
            hr = runner._check_hub(hub)
        assert "boom" in hr.error
