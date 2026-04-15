"""
REFLEX Configuration — Declarative hub config from reflex.yaml.

Each hub defines its REFLEX rules in a reflex.yaml file:
    hub_name, vertical, viewports, htmx_patterns, permissions_matrix, etc.

Usage:
    from reflex.config import ReflexConfig

    config = ReflexConfig.from_yaml("reflex.yaml")
    agent = DomainAgent(config=config)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Viewport:
    """Viewport definition for responsive testing (U-4)."""

    name: str
    width: int
    height: int


@dataclass(frozen=True)
class HTMXRules:
    """HTMX validation rules (U-1, ADR-048)."""

    banned: list[str] = field(default_factory=lambda: ["hx-boost"])
    required_on_forms: list[str] = field(
        default_factory=lambda: ["hx-indicator", "hx-disabled-elt"]
    )


@dataclass(frozen=True)
class QualityConfig:
    """UC quality check configuration (Zirkel 1)."""

    min_acceptance_criteria: int = 2
    max_uc_steps: int = 7
    require_error_cases: bool = True
    require_specific_actor: bool = True
    forbid_implementation_details: bool = True
    forbid_soft_language: bool = True


@dataclass
class ReflexConfig:
    """Complete REFLEX configuration for a hub.

    Loaded from reflex.yaml in the hub root directory.
    """

    hub_name: str
    vertical: str
    domain_keywords: list[str] = field(default_factory=list)
    quality: QualityConfig = field(default_factory=QualityConfig)
    viewports: list[Viewport] = field(
        default_factory=lambda: [
            Viewport("mobile", 375, 812),
            Viewport("tablet", 768, 1024),
            Viewport("desktop", 1280, 800),
        ]
    )
    htmx_patterns: HTMXRules = field(default_factory=HTMXRules)
    permissions_matrix: dict[str, dict[str, int]] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ReflexConfig:
        """Load config from a reflex.yaml file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"REFLEX config not found: {path}")

        with path.open() as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}

        return cls._from_dict(raw)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflexConfig:
        """Create config from a dictionary (for testing)."""
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> ReflexConfig:
        quality_raw = raw.get("quality", {})
        quality = QualityConfig(
            min_acceptance_criteria=quality_raw.get("min_acceptance_criteria", 2),
            max_uc_steps=quality_raw.get("max_uc_steps", 7),
            require_error_cases=quality_raw.get("require_error_cases", True),
            require_specific_actor=quality_raw.get("require_specific_actor", True),
            forbid_implementation_details=quality_raw.get(
                "forbid_implementation_details", True
            ),
            forbid_soft_language=quality_raw.get("forbid_soft_language", True),
        )

        viewports = [
            Viewport(v["name"], v["width"], v["height"])
            for v in raw.get("viewports", [])
        ]

        htmx_raw = raw.get("htmx_patterns", {})
        htmx = HTMXRules(
            banned=htmx_raw.get("banned", ["hx-boost"]),
            required_on_forms=htmx_raw.get(
                "required_on_forms", ["hx-indicator", "hx-disabled-elt"]
            ),
        )

        return cls(
            hub_name=raw.get("hub_name", "unknown"),
            vertical=raw.get("vertical", "general"),
            domain_keywords=raw.get("domain_keywords", []),
            quality=quality,
            viewports=viewports or [
                Viewport("mobile", 375, 812),
                Viewport("tablet", 768, 1024),
                Viewport("desktop", 1280, 800),
            ],
            htmx_patterns=htmx,
            permissions_matrix=raw.get("permissions_matrix", {}),
        )
