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
    container: risk_hub_web
    db: risk_hub_db
    description: Gefahrstoffmanagement
  travel-beat:
    port: 8001
    container: travel_beat_web
    db: travel_beat_db
    description: Reiseplanung
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
            info = get_service_info("nonexistent-repo")
        assert info is None

    def test_should_return_service_info(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("risk-hub")
        assert info is not None
        assert info["port"] == 8090
        assert info["container"] == "risk_hub_web"

    def test_should_include_description(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("travel-beat")
        assert info is not None
        assert info["description"] == "Reiseplanung"


class TestFormatInfoCard:
    """Test format_info_card output."""

    def test_should_format_service_info(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("risk-hub")
        assert info is not None
        card = format_info_card("risk-hub", info)
        assert "risk-hub" in card
        assert "8090" in card

    def test_should_handle_none_info(self):
        card = format_info_card("unknown", None)
        assert "unknown" in card or card == ""
