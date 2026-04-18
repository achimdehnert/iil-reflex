"""
REFLEX Infra Lookup — Single-command infrastructure info for any repo.

Usage:
    reflex infra dev-hub         # Full info card
    reflex infra dev-hub --json  # Machine-readable
    reflex infra --all           # All services at a glance
    reflex infra --all --json    # Export all as JSON

Reads from platform/infra/ports.yaml (Single Source of Truth).
Enriches with local docker-compose.prod.yml for DB, volumes, healthcheck info.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


def _find_ports_yaml(github_dir: Path) -> Path | None:
    """Locate platform/infra/ports.yaml."""
    candidates = [
        github_dir / "platform" / "infra" / "ports.yaml",
        github_dir / "platform" / "ports.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _load_ports_data(github_dir: Path) -> dict:
    """Load and parse ports.yaml."""
    path = _find_ports_yaml(github_dir)
    if not path:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _extract_db_info(compose_path: Path) -> dict:
    """Extract database info from docker-compose.prod.yml."""
    if not compose_path.exists():
        return {}

    content = compose_path.read_text(encoding="utf-8", errors="ignore")

    db_info = {}

    # Find DB image
    db_match = re.search(r"image:\s*(postgres|pgvector|timescale)\S*", content)
    if db_match:
        db_info["db_image"] = db_match.group(0).replace("image:", "").strip()

    # Find DB container name
    # Look for -db or _db service
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"container_name:.*(_db|[-_]db)", line):
            db_info["db_container"] = line.split(":")[-1].strip()

    # Find DB environment vars
    db_name_match = re.search(r"POSTGRES_DB[=:]\s*(\S+)", content)
    if db_name_match:
        db_info["db_name"] = db_name_match.group(1).strip("\"'")

    db_user_match = re.search(r"POSTGRES_USER[=:]\s*(\S+)", content)
    if db_user_match:
        db_info["db_user"] = db_user_match.group(1).strip("\"'")

    # Find volumes
    volumes = re.findall(r"(\w+_pg\w+|\w+_postgres\w+):/var/lib/postgresql", content)
    if volumes:
        db_info["db_volume"] = volumes[0]

    # Find Redis
    redis_match = re.search(r"image:\s*(redis|valkey)\S*", content)
    if redis_match:
        db_info["redis"] = True

    return db_info


def _extract_healthcheck(compose_path: Path) -> str | None:
    """Extract web service healthcheck from compose file."""
    if not compose_path.exists():
        return None

    content = compose_path.read_text(encoding="utf-8", errors="ignore")
    # Look for curl-based healthcheck
    match = re.search(r"curl.*?http://\S+", content)
    if match:
        return match.group(0)
    return None


def get_service_info(repo_name: str, github_dir: Path) -> dict | None:
    """Get complete infrastructure info for a repo."""
    ports_data = _load_ports_data(github_dir)
    if not ports_data:
        return None

    # Search in services
    services = ports_data.get("services", {})
    infra = ports_data.get("infra", {})
    servers = ports_data.get("servers", {})

    # Find matching service
    service_data = None
    service_key = None

    # Direct match
    if repo_name in services:
        service_data = services[repo_name]
        service_key = repo_name
    elif repo_name in infra:
        service_data = infra[repo_name]
        service_key = repo_name
    else:
        # Search by repo field
        for key, svc in services.items():
            if svc.get("repo", "").endswith(f"/{repo_name}"):
                service_data = svc
                service_key = key
                break

    if not service_data:
        return None

    result = {
        "name": service_key,
        "port_prod": service_data.get("prod", service_data.get("port")),
        "port_staging": service_data.get("staging", service_data.get("port")),
        "port_dev": service_data.get("dev", service_data.get("port")),
        "container": service_data.get("container_name", ""),
        "domain_prod": service_data.get("domain_prod", ""),
        "domain_staging": service_data.get("domain_staging", ""),
        "domain_aliases": service_data.get("domain_aliases", []),
        "repo": service_data.get("repo", ""),
        "server": service_data.get("server", "prod"),
        "compose_drift": service_data.get("compose_drift"),
        "note": service_data.get("note"),
    }

    # Resolve server info
    server_key = result["server"]
    if server_key in servers:
        result["server_ip"] = servers[server_key].get("ip", "")
        result["server_ssh"] = servers[server_key].get("ssh", "")
        result["server_name"] = servers[server_key].get("name", "")

    # Enrich with compose info
    repo_path = github_dir / repo_name
    compose = repo_path / "docker-compose.prod.yml"
    if compose.exists():
        db_info = _extract_db_info(compose)
        result.update(db_info)
        healthcheck = _extract_healthcheck(compose)
        if healthcheck:
            result["healthcheck"] = healthcheck

    return result


def get_all_services(github_dir: Path) -> list[dict]:
    """Get info for all services."""
    ports_data = _load_ports_data(github_dir)
    if not ports_data:
        return []

    services = ports_data.get("services", {})
    result = []
    for key in sorted(services.keys()):
        info = get_service_info(key, github_dir)
        if info:
            result.append(info)
    return result


def format_info_card(info: dict) -> str:
    """Format a service info card for terminal display."""
    lines = []
    lines.append(f"\n{'═' * 60}")
    lines.append(f"  📦 {info['name']}")
    lines.append(f"{'═' * 60}")

    # Server
    lines.append(f"\n  Server:     {info.get('server_name', '?')} ({info.get('server_ip', '?')})")
    lines.append(f"  SSH:        {info.get('server_ssh', '?')}")

    # Ports
    lines.append(f"\n  Port Prod:  {info.get('port_prod', '?')}")
    lines.append(f"  Port Stage: {info.get('port_staging', '?')}")
    lines.append(f"  Port Dev:   {info.get('port_dev', '?')}")

    # Container
    lines.append(f"\n  Container:  {info.get('container', '?')}")

    # Domains
    lines.append(f"\n  Domain:     https://{info.get('domain_prod', '?')}")
    if info.get("domain_staging"):
        lines.append(f"  Staging:    https://{info.get('domain_staging')}")
    if info.get("domain_aliases"):
        lines.append(f"  Aliases:    {', '.join(info['domain_aliases'])}")

    # Database
    if info.get("db_container") or info.get("db_image"):
        lines.append(f"\n  DB Image:   {info.get('db_image', '?')}")
        lines.append(f"  DB Name:    {info.get('db_name', '?')}")
        lines.append(f"  DB User:    {info.get('db_user', '?')}")
        lines.append(f"  DB Cont:    {info.get('db_container', '?')}")
        if info.get("db_volume"):
            lines.append(f"  DB Volume:  {info['db_volume']}")

    # Redis
    if info.get("redis"):
        lines.append(f"  Redis:      yes")

    # Health
    if info.get("healthcheck"):
        lines.append(f"\n  Health:     {info['healthcheck']}")

    # Repo
    if info.get("repo"):
        lines.append(f"\n  GitHub:     https://github.com/{info['repo']}")

    # Warnings
    if info.get("compose_drift"):
        lines.append(f"\n  ⚠️  DRIFT:  {info['compose_drift']}")

    if info.get("note"):
        lines.append(f"  Note:       {info['note']}")

    lines.append("")
    return "\n".join(lines)


def format_all_table(services: list[dict]) -> str:
    """Format all services as a compact table."""
    lines = []
    lines.append(f"\n{'═' * 80}")
    lines.append(f"  REFLEX Platform Infrastructure — {len(services)} Services")
    lines.append(f"{'═' * 80}")
    lines.append(f"\n  {'Name':<20} {'Port':<6} {'Container':<25} {'Domain'}")
    lines.append(f"  {'─' * 20} {'─' * 6} {'─' * 25} {'─' * 25}")

    for svc in services:
        port = str(svc.get("port_prod", "?"))
        container = svc.get("container", "?")[:24]
        domain = svc.get("domain_prod", "")
        drift = " ⚠️" if svc.get("compose_drift") else ""
        lines.append(f"  {svc['name']:<20} {port:<6} {container:<25} {domain}{drift}")

    lines.append(f"\n  ⚠️  = compose_drift (port mismatch)")
    lines.append("")
    return "\n".join(lines)


def cmd_infra(args) -> int:
    """Execute reflex infra command."""
    github_dir = Path(args.github_dir) if args.github_dir else Path.home() / "github"

    if args.all:
        services = get_all_services(github_dir)
        if not services:
            print("ERROR: Could not load ports.yaml", file=__import__("sys").stderr)
            return 1
        if args.json:
            print(json.dumps(services, indent=2, ensure_ascii=False))
        else:
            print(format_all_table(services))
        return 0

    # Single repo lookup
    repo = args.repo
    if not repo or repo == ".":
        # Try to detect from CWD
        import subprocess

        try:
            toplevel = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            repo = Path(toplevel).name
        except Exception:
            print("ERROR: No repo specified and not in a git repo", file=__import__("sys").stderr)
            return 1

    info = get_service_info(repo, github_dir)
    if not info:
        print(f"ERROR: '{repo}' not found in ports.yaml", file=__import__("sys").stderr)
        return 1

    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print(format_info_card(info))

    return 0
