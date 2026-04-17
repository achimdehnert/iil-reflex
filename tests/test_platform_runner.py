"""Tests for reflex.platform_runner — ADR-163 platform-wide checks."""

from pathlib import Path

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
            name="test", tier=1,
            routes_total=5, routes_ok=3,
            health_ok=True,
        )
        assert hr.status_icon == "⚠️"

    def test_should_show_healthy_icon(self):
        hr = HubReport(name="test", tier=1, health_ok=True)
        assert hr.status_icon == "✅"


class TestPlatformReport:
    """Test PlatformReport aggregations."""

    def test_should_count_tiers(self):
        report = PlatformReport(hubs=[
            HubReport(name="a", tier=1, health_ok=True),
            HubReport(name="b", tier=1, health_ok=True),
            HubReport(name="c", tier=2, health_ok=True),
        ])
        assert len(report.tier1_hubs) == 2
        assert len(report.tier2_hubs) == 1

    def test_should_count_healthy_hubs(self):
        report = PlatformReport(hubs=[
            HubReport(name="a", tier=1, health_ok=True),
            HubReport(name="b", tier=2, health_ok=False, error="down"),
        ])
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
                    name="risk-hub", tier=1,
                    health_ok=True,
                    routes_total=5, routes_ok=5,
                    permissions_total=10, permissions_ok=10,
                    uc_count=4,
                    duration_seconds=1.2,
                ),
                HubReport(
                    name="billing-hub", tier=2,
                    health_ok=True,
                    routes_total=3, routes_ok=3,
                    duration_seconds=0.8,
                ),
                HubReport(
                    name="broken-hub", tier=2,
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
