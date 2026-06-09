"""Tests for reflex.infra — infrastructure info lookup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from reflex.infra import (
    format_info_card,
    get_service_info,
)


@pytest.fixture
def ports_yaml_content():
    return """
services:
  risk-hub:
    port: 8090
    container_name: risk_hub_web
    db: risk_hub_db
  travel-beat:
    port: 8001
    container_name: travel_beat_web
    db: travel_beat_db
"""


@pytest.fixture
def mock_ports_yaml(tmp_path, ports_yaml_content):
    """Create a mock ports.yaml file."""
    infra_dir = tmp_path / "platform" / "infra"
    infra_dir.mkdir(parents=True)
    ports_file = infra_dir / "ports.yaml"
    ports_file.write_text(ports_yaml_content)
    return ports_file


class TestGetServiceInfo:
    """Test get_service_info function."""

    def test_should_return_none_for_unknown_repo(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("nonexistent-repo", Path("/repos"))
        assert info is None

    def test_should_return_service_info(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("risk-hub", Path("/repos"))
        assert info is not None
        # Result schema: per-environment ports (port_prod falls back to `port`),
        # container from `container_name`.
        assert info["port_prod"] == 8090
        assert info["container"] == "risk_hub_web"


class TestFormatInfoCard:
    """Test format_info_card output."""

    def test_should_format_service_info(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("risk-hub", Path("/repos"))
        assert info is not None
        card = format_info_card(info)  # single-arg: name is taken from info["name"]
        assert "risk-hub" in card
        assert "8090" in card
