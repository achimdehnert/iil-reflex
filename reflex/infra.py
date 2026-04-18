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
import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


__all__ = [
    "get_service_info",
    "get_all_services",
    "format_info_card",
    "format_all_table",
    "get_live_status",
    "format_live_card",
    "format_all_live_table",
    "cmd_infra",
]


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
    for _i, line in enumerate(lines):
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
        lines.append("  Redis:      yes")

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

    lines.append("\n  ⚠️  = compose_drift (port mismatch)")
    lines.append("")
    return "\n".join(lines)


def _run_ssh(ssh_target: str, command: str, timeout: int = 10) -> str | None:
    """Run a command via SSH, return stdout or None on failure."""
    import subprocess

    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no", ssh_target, command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def get_live_status(info: dict) -> dict:
    """Get live status from server via SSH."""
    ssh = info.get("server_ssh", "")
    container = info.get("container", "")
    if not ssh or not container:
        return {"error": "No SSH target or container name"}

    live = {}

    # Container status
    status_out = _run_ssh(ssh, f"docker ps --filter 'name=^{container}$' --format '{{{{.Status}}}}' 2>/dev/null")
    if status_out:
        live["container_status"] = status_out
    else:
        live["container_status"] = "NOT RUNNING"

    # Container resource usage (CPU, MEM)
    stats_out = _run_ssh(
        ssh,
        f"docker stats {container} --no-stream --format "
        f"'{{{{.CPUPerc}}}} {{{{.MemUsage}}}} {{{{.MemPerc}}}}' 2>/dev/null",
    )
    if stats_out:
        parts = stats_out.split()
        if len(parts) >= 3:
            live["cpu"] = parts[0]
            live["memory"] = f"{parts[1]} {parts[2]}"
            live["mem_pct"] = parts[-1] if len(parts) > 3 else parts[2]

    # DB container status (if exists)
    db_container = info.get("db_container")
    if db_container:
        db_status = _run_ssh(ssh, f"docker ps --filter 'name=^{db_container}$' --format '{{{{.Status}}}}' 2>/dev/null")
        live["db_status"] = db_status or "NOT RUNNING"

    # Disk usage
    disk_out = _run_ssh(ssh, "df -h / --output=pcent,avail | tail -1")
    if disk_out:
        live["disk"] = disk_out.strip()

    # HTTP health check
    port = info.get("port_prod")
    if port:
        health_out = _run_ssh(
            ssh,
            f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 3 http://127.0.0.1:{port}/health/ 2>/dev/null"
            f" || curl -s -o /dev/null -w '%{{http_code}}' --max-time 3 http://127.0.0.1:{port}/ 2>/dev/null",
        )
        if health_out:
            live["http_status"] = health_out

    # Recent logs (last error)
    logs_out = _run_ssh(
        ssh, f"docker logs {container} --tail 5 --since 1h 2>&1 | grep -i 'error\\|exception\\|fatal' | tail -1"
    )
    if logs_out:
        live["last_error"] = logs_out[:120]

    return live


def format_live_card(info: dict, live: dict) -> str:
    """Format info card with live data appended."""
    card = format_info_card(info)

    lines = [card.rstrip()]
    lines.append(f"  {'─' * 56}")
    lines.append("  🔴 LIVE STATUS (via SSH)")
    lines.append(f"  {'─' * 56}")

    # Container
    status = live.get("container_status", "?")
    icon = "🟢" if "Up" in status and "healthy" in status else "🟡" if "Up" in status else "🔴"
    lines.append(f"  {icon} Container: {status}")

    # DB
    if live.get("db_status"):
        db_status = live["db_status"]
        db_icon = "🟢" if "healthy" in db_status else "🟡" if "Up" in db_status else "🔴"
        lines.append(f"  {db_icon} Database:  {db_status}")

    # Resources
    if live.get("cpu"):
        lines.append(f"  📊 CPU: {live['cpu']}  |  Memory: {live.get('memory', '?')}")

    # HTTP
    if live.get("http_status"):
        code = live["http_status"]
        http_icon = "🟢" if code.startswith("2") else "🟡" if code.startswith("3") else "🔴"
        lines.append(f"  {http_icon} HTTP:      {code}")

    # Disk
    if live.get("disk"):
        disk_parts = live["disk"].split()
        disk_pct = disk_parts[0] if disk_parts else "?"
        disk_avail = disk_parts[1] if len(disk_parts) > 1 else "?"
        pct_num = int(disk_pct.replace("%", "")) if "%" in disk_pct else 0
        disk_icon = "🟢" if pct_num < 70 else "🟡" if pct_num < 85 else "🔴"
        lines.append(f"  {disk_icon} Disk:      {disk_pct} used, {disk_avail} free")

    # Errors
    if live.get("last_error"):
        lines.append(f"  ⚠️  Last Error: {live['last_error']}")

    if live.get("error"):
        lines.append(f"  ❌ {live['error']}")

    lines.append("")
    return "\n".join(lines)


def format_all_live_table(services: list[dict], github_dir: Path) -> str:
    """Format all services with live status."""
    import concurrent.futures

    lines = []
    lines.append(f"\n{'═' * 90}")
    lines.append(f"  REFLEX Platform — LIVE STATUS ({len(services)} Services)")
    lines.append(f"{'═' * 90}")
    lines.append(f"\n  {'Name':<20} {'Port':<6} {'Status':<28} {'HTTP':<6} {'Domain'}")
    lines.append(f"  {'─' * 20} {'─' * 6} {'─' * 28} {'─' * 6} {'─' * 25}")

    # Parallel SSH calls for speed
    def fetch_live(svc):
        live = get_live_status(svc)
        return svc["name"], svc, live

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_live, svc) for svc in services]
        results = []
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Sort by name
    results.sort(key=lambda x: x[0])

    for name, svc, live in results:
        port = str(svc.get("port_prod", "?"))
        status_raw = live.get("container_status", "?")
        # Shorten status
        if "healthy" in status_raw:
            status = "Up (healthy)"
            icon = "🟢"
        elif "Up" in status_raw:
            status = status_raw[:26]
            icon = "🟡"
        else:
            status = "DOWN"
            icon = "🔴"
        http = live.get("http_status", "?")
        domain = svc.get("domain_prod", "")
        lines.append(f"  {icon} {name:<18} {port:<6} {status:<28} {http:<6} {domain}")

    lines.append("")
    return "\n".join(lines)


def cmd_infra(args) -> int:
    """Execute reflex infra command."""
    github_dir = Path(args.github_dir) if args.github_dir else Path.home() / "github"
    live_mode = getattr(args, "live", False)

    if args.all:
        services = get_all_services(github_dir)
        if not services:
            logger.error("ERROR: Could not load ports.yaml", file=__import__("sys").stderr)
            return 1
        if args.json:
            if live_mode:
                for svc in services:
                    svc["live"] = get_live_status(svc)
            logger.info(json.dumps(services, indent=2, ensure_ascii=False))
        elif live_mode:
            logger.info(format_all_live_table(services, github_dir))
        else:
            logger.info(format_all_table(services))
        return 0

    # Single repo lookup
    repo = args.repo
    if not repo or repo == ".":
        # Try to detect from CWD
        import subprocess

        try:
            toplevel = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            repo = Path(toplevel).name
        except Exception:
            logger.error("ERROR: No repo specified and not in a git repo", file=__import__("sys").stderr)
            return 1

    info = get_service_info(repo, github_dir)
    if not info:
        logger.error(f"ERROR: '{repo}' not found in ports.yaml", file=__import__("sys").stderr)
        return 1

    if args.json:
        data = info
        if live_mode:
            data["live"] = get_live_status(info)
        logger.info(json.dumps(data, indent=2, ensure_ascii=False))
    elif live_mode:
        live = get_live_status(info)
        logger.info(format_live_card(info, live))
    else:
        logger.info(format_info_card(info))

    return 0
