"""
REFLEX Scaffold — Generate reflex.yaml for new hubs.

Generates Tier 1 (full) or Tier 2 (light) YAML configurations
with sensible defaults. Ports are derived from the --port argument
or fall back to standard 8000.

ADR-163: Adopt Three-Tier REFLEX Quality Standard

Usage:
    python -m reflex init --tier 1 --hub risk-hub --vertical chemical_safety --port 8003
    python -m reflex init --tier 2 --hub billing-hub --port 8006
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ScaffoldOptions", "generate_yaml", "scaffold", "scaffold_force"]


@dataclass
class ScaffoldOptions:
    """Options for generating a reflex.yaml."""

    hub_name: str
    tier: int = 2
    vertical: str = "general"
    port: int = 8000
    output_path: str = "reflex.yaml"


_TIER1_TEMPLATE = textwrap.dedent("""\
    # REFLEX Configuration — {hub_name}
    # ADR-162: Reflexive Evidence-based Loop for UI Development
    # ADR-163: Tier 1 — Full Reflex

    hub_name: {hub_name}
    vertical: {vertical}

    domain_keywords:
      - # TODO: Add domain-specific keywords

    quality:
      min_acceptance_criteria: 2
      max_uc_steps: 7
      require_error_cases: true
      require_specific_actor: true
      forbid_implementation_details: true
      forbid_soft_language: true

    viewports:
      - name: desktop
        width: 1280
        height: 800
      - name: tablet
        width: 768
        height: 1024
      - name: mobile
        width: 375
        height: 812

    htmx_patterns:
      banned:
        - hx-boost
      required_on_forms:
        - hx-indicator
        - hx-disabled-elt

    permissions_matrix:
      /dashboard/:
        admin: 200
        viewer: 200
        anonymous: 302
      # TODO: Add routes and expected status codes per role

    test_users:
      admin:
        username: admin
        password: "<test-password>"
      viewer:
        username: viewer
        password: "<test-password>"
      # TODO: Set actual test credentials

    dev_cycle:
      base_url: http://localhost:{port}
      login_url: /accounts/login/
      backend_test_cmd: "pytest src/ -q --tb=short"
      lint_cmd: "ruff check src/"
      max_fix_iterations: 3
      public_routes:
        - /accounts/login/
        - /livez/
        - /healthz/

    test_routes:
      - url: /livez/
        expect: 200
        auth: false
        label: Liveness
      - url: /healthz/
        expect: 200
        auth: false
        label: Readiness
      - url: /accounts/login/
        expect: 200
        auth: false
        label: Login Page
      # TODO: Add authenticated routes
""")

_TIER2_TEMPLATE = textwrap.dedent("""\
    # REFLEX Configuration — {hub_name}
    # ADR-162: Reflexive Evidence-based Loop for UI Development
    # ADR-163: Tier 2 — Reflex Light (Health + Route Monitoring)

    hub_name: {hub_name}
    vertical: {vertical}

    dev_cycle:
      base_url: http://localhost:{port}
      login_url: /accounts/login/
      backend_test_cmd: "pytest src/ -q --tb=short"
      lint_cmd: "ruff check src/"
      max_fix_iterations: 3
      public_routes:
        - /accounts/login/
        - /livez/
        - /healthz/

    test_routes:
      - url: /livez/
        expect: 200
        auth: false
        label: Liveness
      - url: /healthz/
        expect: 200
        auth: false
        label: Readiness
      - url: /accounts/login/
        expect: 200
        auth: false
        label: Login Page
""")


def generate_yaml(options: ScaffoldOptions) -> str:
    """Generate reflex.yaml content from options.

    Args:
        options: Scaffold configuration

    Returns:
        YAML content as string
    """
    if options.tier == 1:
        template = _TIER1_TEMPLATE
    elif options.tier == 2:
        template = _TIER2_TEMPLATE
    else:
        raise ValueError(f"Invalid tier: {options.tier}. Must be 1 or 2.")

    return template.format(
        hub_name=options.hub_name,
        vertical=options.vertical,
        port=options.port,
    )


def scaffold(options: ScaffoldOptions) -> Path:
    """Generate and write reflex.yaml to disk.

    Args:
        options: Scaffold configuration

    Returns:
        Path to the created file

    Raises:
        FileExistsError: If output_path already exists
    """
    output = Path(options.output_path)
    if output.exists():
        raise FileExistsError(f"reflex.yaml already exists at {output}. Use --force to overwrite.")

    content = generate_yaml(options)
    output.write_text(content, encoding="utf-8")
    return output


def scaffold_force(options: ScaffoldOptions) -> Path:
    """Generate and write reflex.yaml, overwriting if exists.

    Args:
        options: Scaffold configuration

    Returns:
        Path to the created file
    """
    output = Path(options.output_path)
    content = generate_yaml(options)
    output.write_text(content, encoding="utf-8")
    return output
