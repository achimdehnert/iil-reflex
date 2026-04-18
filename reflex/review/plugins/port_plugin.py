"""
REFLEX Review Plugin: port — Port drift detection (ADR-165, ADR-164).

Compares docker-compose.prod.yml port mappings against the canonical
platform/infra/ports.yaml to detect drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)


class PortPlugin:
    name = "port"
    applicable_tiers = [1, 2]

    def check(self, repo: str, context: dict) -> list[Finding]:
        repo_path = Path(context.get("repo_path", ""))
        github_dir = Path(context.get("github_dir", ""))
        findings: list[Finding] = []

        # Load ports.yaml
        ports_yaml = github_dir / "platform" / "infra" / "ports.yaml"
        if not ports_yaml.exists():
            findings.append(
                Finding(
                    rule_id="port.ports_yaml_missing",
                    severity=ReviewSeverity.INFO,
                    message="platform/infra/ports.yaml not found — cannot check port drift",
                    adr_ref="ADR-164",
                )
            )
            return findings

        try:
            ports_data = yaml.safe_load(ports_yaml.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            findings.append(
                Finding(
                    rule_id="port.ports_yaml_invalid",
                    severity=ReviewSeverity.WARN,
                    message="platform/infra/ports.yaml has invalid YAML",
                    adr_ref="ADR-164",
                    file_path=str(ports_yaml),
                )
            )
            return findings

        # Find this repo in ports.yaml services
        services = ports_data.get("services", {})
        canonical_port = None
        service_name = None

        for svc_name, svc_data in services.items():
            svc_repo = svc_data.get("repo", "")
            # Match by repo name (e.g. "achimdehnert/risk-hub" or just "risk-hub")
            if repo in svc_repo or svc_name == repo or svc_name == repo.replace("-", "_"):
                canonical_port = svc_data.get("prod")
                service_name = svc_name
                break

        if canonical_port is None:
            findings.append(
                Finding(
                    rule_id="port.not_in_ports_yaml",
                    severity=ReviewSeverity.WARN,
                    message=f"Repo '{repo}' not found in ports.yaml services",
                    adr_ref="ADR-164",
                )
            )
            return findings

        # Parse docker-compose.prod.yml for port mappings
        compose_file = repo_path / "docker-compose.prod.yml"
        if not compose_file.exists():
            return findings

        compose_text = compose_file.read_text(encoding="utf-8")

        # Extract port mappings: "8090:8000" or "127.0.0.1:8090:8000"
        port_pattern = re.compile(
            r"""
            (?:127\.0\.0\.1:)?  # optional bind address
            (\d+)               # host port
            :                   # separator
            (\d+)               # container port
            """,
            re.VERBOSE,
        )

        # Find all port lines in compose
        compose_ports: list[tuple[str, str]] = port_pattern.findall(compose_text)

        if not compose_ports:
            findings.append(
                Finding(
                    rule_id="port.no_ports_in_compose",
                    severity=ReviewSeverity.INFO,
                    message="No port mappings found in docker-compose.prod.yml",
                    file_path="docker-compose.prod.yml",
                )
            )
            return findings

        # Check if canonical port is used as host port
        host_ports = [int(hp) for hp, _cp in compose_ports]
        if canonical_port not in host_ports:
            actual_ports = ", ".join(str(p) for p in sorted(set(host_ports)))
            findings.append(
                Finding(
                    rule_id="port.port_drift",
                    severity=ReviewSeverity.BLOCK,
                    message=(
                        f"Port drift: ports.yaml says {service_name}={canonical_port}, "
                        f"but compose uses host port(s) {actual_ports}"
                    ),
                    adr_ref="ADR-164 §5.1",
                    file_path="docker-compose.prod.yml",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                    fix_hint=f"Change host port to {canonical_port} in docker-compose.prod.yml",
                )
            )

        return findings


plugin = PortPlugin()
