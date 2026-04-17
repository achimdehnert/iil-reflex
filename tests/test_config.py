"""Tests for ReflexConfig — YAML loading and defaults."""


import pytest

from reflex.config import ReflexConfig


class TestConfigFromDict:
    def test_should_create_with_minimal_dict(self):
        config = ReflexConfig.from_dict({"hub_name": "test", "vertical": "general"})

        assert config.hub_name == "test"
        assert config.vertical == "general"
        assert len(config.viewports) == 3
        assert config.quality.max_uc_steps == 7

    def test_should_apply_custom_quality(self):
        config = ReflexConfig.from_dict({
            "hub_name": "risk-hub",
            "vertical": "chemical_safety",
            "quality": {"max_uc_steps": 5, "min_acceptance_criteria": 3},
        })

        assert config.quality.max_uc_steps == 5
        assert config.quality.min_acceptance_criteria == 3

    def test_should_parse_viewports(self):
        config = ReflexConfig.from_dict({
            "hub_name": "test",
            "vertical": "general",
            "viewports": [
                {"name": "mobile", "width": 375, "height": 812},
            ],
        })

        assert len(config.viewports) == 1
        assert config.viewports[0].name == "mobile"
        assert config.viewports[0].width == 375

    def test_should_parse_htmx_rules(self):
        config = ReflexConfig.from_dict({
            "hub_name": "test",
            "vertical": "general",
            "htmx_patterns": {
                "banned": ["hx-boost", "hx-push-url"],
                "required_on_forms": ["hx-indicator"],
            },
        })

        assert "hx-boost" in config.htmx_patterns.banned
        assert "hx-push-url" in config.htmx_patterns.banned

    def test_should_parse_permissions_matrix(self):
        config = ReflexConfig.from_dict({
            "hub_name": "test",
            "vertical": "general",
            "permissions_matrix": {
                "/substances/": {"anonymous": 302, "viewer": 200},
            },
        })

        assert config.permissions_matrix["/substances/"]["anonymous"] == 302


class TestConfigFromYAML:
    def test_should_load_from_file(self, tmp_path):
        yaml_content = """
hub_name: risk-hub
vertical: chemical_safety
domain_keywords:
  - SDS
  - CAS
quality:
  min_acceptance_criteria: 2
  max_uc_steps: 7
viewports:
  - name: mobile
    width: 375
    height: 812
  - name: desktop
    width: 1280
    height: 800
"""
        config_file = tmp_path / "reflex.yaml"
        config_file.write_text(yaml_content)

        config = ReflexConfig.from_yaml(config_file)

        assert config.hub_name == "risk-hub"
        assert config.vertical == "chemical_safety"
        assert "SDS" in config.domain_keywords
        assert len(config.viewports) == 2

    def test_should_raise_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            ReflexConfig.from_yaml("/nonexistent/reflex.yaml")

    def test_should_use_defaults_for_empty_yaml(self, tmp_path):
        config_file = tmp_path / "reflex.yaml"
        config_file.write_text("hub_name: minimal\nvertical: test\n")

        config = ReflexConfig.from_yaml(config_file)

        assert config.hub_name == "minimal"
        assert config.quality.max_uc_steps == 7
        assert len(config.viewports) == 3
