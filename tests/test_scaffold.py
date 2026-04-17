"""Tests for reflex.scaffold — ADR-163 scaffold generator."""

from pathlib import Path

import pytest
import yaml

from reflex.config import ReflexConfig
from reflex.scaffold import ScaffoldOptions, generate_yaml, scaffold, scaffold_force


class TestGenerateYaml:
    """Test YAML generation for Tier 1 and Tier 2."""

    def test_should_generate_tier1_yaml(self):
        options = ScaffoldOptions(
            hub_name="test-hub",
            tier=1,
            vertical="chemical_safety",
            port=8003,
        )
        result = generate_yaml(options)
        assert "hub_name: test-hub" in result
        assert "vertical: chemical_safety" in result
        assert "Tier 1" in result
        assert "permissions_matrix:" in result
        assert "test_users:" in result
        assert "8003" in result

    def test_should_generate_tier2_yaml(self):
        options = ScaffoldOptions(
            hub_name="billing-hub",
            tier=2,
            vertical="general",
            port=8006,
        )
        result = generate_yaml(options)
        assert "hub_name: billing-hub" in result
        assert "Tier 2" in result
        assert "/livez/" in result
        assert "/healthz/" in result
        assert "permissions_matrix:" not in result
        assert "8006" in result

    def test_should_reject_invalid_tier(self):
        options = ScaffoldOptions(hub_name="test", tier=3)
        with pytest.raises(ValueError, match="Invalid tier"):
            generate_yaml(options)

    def test_should_produce_valid_yaml(self):
        for tier in (1, 2):
            options = ScaffoldOptions(
                hub_name="yaml-test",
                tier=tier,
                vertical="test",
                port=9000,
            )
            content = generate_yaml(options)
            parsed = yaml.safe_load(content)
            assert parsed["hub_name"] == "yaml-test"

    def test_should_include_health_routes_in_both_tiers(self):
        for tier in (1, 2):
            options = ScaffoldOptions(hub_name="test", tier=tier, port=8000)
            content = generate_yaml(options)
            assert "/livez/" in content
            assert "/healthz/" in content

    def test_tier1_should_be_loadable_by_reflex_config(self, tmp_path: Path):
        options = ScaffoldOptions(
            hub_name="loadtest-hub",
            tier=1,
            vertical="test_vertical",
            port=8042,
            output_path=str(tmp_path / "reflex.yaml"),
        )
        scaffold_force(options)
        config = ReflexConfig.from_yaml(tmp_path / "reflex.yaml")
        assert config.hub_name == "loadtest-hub"
        assert config.vertical == "test_vertical"


class TestScaffoldWrite:
    """Test file writing behavior."""

    def test_should_create_file(self, tmp_path: Path):
        out = tmp_path / "reflex.yaml"
        options = ScaffoldOptions(
            hub_name="new-hub", tier=2, output_path=str(out),
        )
        result = scaffold(options)
        assert result.exists()
        assert "hub_name: new-hub" in result.read_text()

    def test_should_refuse_overwrite_without_force(self, tmp_path: Path):
        out = tmp_path / "reflex.yaml"
        out.write_text("existing content")
        options = ScaffoldOptions(
            hub_name="new-hub", tier=2, output_path=str(out),
        )
        with pytest.raises(FileExistsError):
            scaffold(options)

    def test_should_overwrite_with_force(self, tmp_path: Path):
        out = tmp_path / "reflex.yaml"
        out.write_text("old content")
        options = ScaffoldOptions(
            hub_name="force-hub", tier=1, output_path=str(out),
        )
        result = scaffold_force(options)
        assert "hub_name: force-hub" in result.read_text()

    def test_should_not_include_test_passwords_in_cleartext(self):
        options = ScaffoldOptions(hub_name="sec-test", tier=1)
        content = generate_yaml(options)
        assert "admin123" not in content
        assert "<test-password>" in content
