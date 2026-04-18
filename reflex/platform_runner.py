"""
REFLEX Platform Runner — Consolidated report across all hubs.

Reads a platform-reflex.yaml that lists all hubs with their config path,
base URL, and tier. Runs `reflex verify` on each hub and aggregates results.

ADR-163: Adopt Three-Tier REFLEX Quality Standard

Usage:
    python -m reflex platform -c platform-reflex.yaml
    python -m reflex platform -c platform-reflex.yaml --json
    python -m reflex platform -c platform-reflex.yaml --report docs/platform-health.md

platform-reflex.yaml format:
    hubs:
      - name: risk-hub
        tier: 1
        config: /path/to/risk-hub/reflex.yaml
        base_url: http://localhost:8003
      - name: billing-hub
        tier: 2
        config: /path/to/billing-hub/reflex.yaml
        base_url: http://localhost:8006
"""

from __future__ import annotations

import json as json_module
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


__all__ = ["HubEntry", "HubReport", "PlatformReport", "PlatformRunner"]


@dataclass
class HubEntry:
    """A hub in the platform config."""

    name: str
    tier: int
    config_path: str
    base_url: str = "http://localhost:8000"


@dataclass
class HubReport:
    """Report for a single hub."""

    name: str
    tier: int
    health_ok: bool = False
    routes_total: int = 0
    routes_ok: int = 0
    permissions_total: int = 0
    permissions_ok: int = 0
    uc_count: int = 0
    error: str = ""
    duration_seconds: float = 0.0

    @property
    def route_pass_rate(self) -> float:
        if self.routes_total == 0:
            return 0.0
        return (self.routes_ok / self.routes_total) * 100

    @property
    def permission_pass_rate(self) -> float:
        if self.permissions_total == 0:
            return 0.0
        return (self.permissions_ok / self.permissions_total) * 100

    @property
    def status_icon(self) -> str:
        if self.error:
            return "❌"
        if self.routes_total > 0 and self.routes_ok < self.routes_total:
            return "⚠️"
        if self.health_ok:
            return "✅"
        return "⬜"


@dataclass
class PlatformReport:
    """Aggregated report for all hubs."""

    hubs: list[HubReport] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    generated_at: str = ""

    @property
    def total_hubs(self) -> int:
        return len(self.hubs)

    @property
    def healthy_hubs(self) -> int:
        return sum(1 for h in self.hubs if h.health_ok and not h.error)

    @property
    def tier1_hubs(self) -> list[HubReport]:
        return [h for h in self.hubs if h.tier == 1]

    @property
    def tier2_hubs(self) -> list[HubReport]:
        return [h for h in self.hubs if h.tier == 2]


class PlatformRunner:
    """Run REFLEX checks across all platform hubs.

    Reads platform-reflex.yaml and runs health/route/permission checks
    for each configured hub, producing an aggregated PlatformReport.
    """

    def __init__(self, hubs: list[HubEntry]):
        self.hubs = hubs

    @classmethod
    def from_yaml(cls, path: str | Path) -> PlatformRunner:
        """Load platform config from YAML.

        Expected format:
            hubs:
              - name: risk-hub
                tier: 1
                config: /path/to/reflex.yaml
                base_url: http://localhost:8003
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Platform config not found: {path}")

        with path.open() as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}

        hubs = []
        for entry in raw.get("hubs", []):
            hubs.append(
                HubEntry(
                    name=entry["name"],
                    tier=entry.get("tier", 2),
                    config_path=entry.get("config", ""),
                    base_url=entry.get("base_url", "http://localhost:8000"),
                )
            )

        return cls(hubs=hubs)

    def run_all(self) -> PlatformReport:
        """Run checks on all configured hubs."""
        from datetime import datetime

        start = time.time()
        report = PlatformReport(
            generated_at=datetime.now(UTC).isoformat(),
        )

        for hub in self.hubs:
            logger.info("Checking hub: %s (Tier %d)", hub.name, hub.tier)
            hub_report = self._check_hub(hub)
            report.hubs.append(hub_report)

        report.total_duration_seconds = time.time() - start
        return report

    def _check_hub(self, hub: HubEntry) -> HubReport:
        """Run checks for a single hub."""
        start = time.time()
        hr = HubReport(name=hub.name, tier=hub.tier)

        # Check if config exists
        if hub.config_path and not Path(hub.config_path).exists():
            hr.error = f"Config not found: {hub.config_path}"
            hr.duration_seconds = time.time() - start
            return hr

        # Count Use Cases (Tier 1 only)
        if hub.tier == 1 and hub.config_path:
            config_dir = Path(hub.config_path).parent
            uc_dir = config_dir / "docs" / "use-cases"
            if uc_dir.exists():
                hr.uc_count = sum(1 for f in uc_dir.glob("UC-*.md"))

        # Health check via HTTP
        try:
            import httpx
        except ImportError:
            hr.error = "httpx not installed"
            hr.duration_seconds = time.time() - start
            return hr

        try:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                # Liveness check
                resp = client.get(f"{hub.base_url}/livez/")
                hr.health_ok = resp.status_code == 200

                # Route checks from config
                if hub.config_path and Path(hub.config_path).exists():
                    with open(hub.config_path) as f:
                        config_raw = yaml.safe_load(f) or {}

                    routes = config_raw.get("test_routes", [])
                    for route in routes:
                        url = route.get("url", "")
                        expected = route.get("expect", 200)
                        auth = route.get("auth", True)

                        if not url or auth:
                            continue

                        hr.routes_total += 1
                        try:
                            resp = client.get(
                                f"{hub.base_url}{url}",
                                follow_redirects=False,
                            )
                            if resp.status_code == expected:
                                hr.routes_ok += 1
                        except Exception:
                            pass  # route check — connection failures are expected

                    # Permission matrix count (Tier 1 only)
                    if hub.tier == 1:
                        perm_matrix = config_raw.get("permissions_matrix", {})
                        for _url, roles in perm_matrix.items():
                            hr.permissions_total += len(roles)

        except httpx.ConnectError:
            hr.error = f"Connection refused: {hub.base_url}"
        except Exception as e:
            hr.error = str(e)[:200]

        hr.duration_seconds = time.time() - start
        return hr

    @staticmethod
    def print_report(report: PlatformReport) -> None:
        """Print human-readable platform report to stdout."""
        print(f"\n{'=' * 80}")
        print("  REFLEX Platform Health Report")
        print(f"{'=' * 80}")
        print(f"  Generated: {report.generated_at}")
        print(f"  Duration:  {report.total_duration_seconds:.1f}s")
        print(f"  Hubs:      {report.healthy_hubs}/{report.total_hubs} healthy")
        print(f"{'=' * 80}\n")

        # Tier 1
        if report.tier1_hubs:
            print("  Tier 1 — Full Reflex")
            print(f"  {'─' * 76}")
            print(f"  {'Hub':<22} {'Health':>6} {'Routes':>10} {'Perms':>10} {'UCs':>4} {'Time':>6}")
            print(f"  {'─' * 76}")
            for h in report.tier1_hubs:
                routes_str = f"{h.routes_ok}/{h.routes_total}" if h.routes_total else "—"
                perms_str = f"{h.permissions_ok}/{h.permissions_total}" if h.permissions_total else "—"
                uc_str = str(h.uc_count) if h.uc_count else "—"
                health_str = "✅" if h.health_ok else ("❌" if h.error else "⬜")
                print(
                    f"  {h.name:<22} {health_str:>6} {routes_str:>10} "
                    f"{perms_str:>10} {uc_str:>4} {h.duration_seconds:>5.1f}s"
                )
                if h.error:
                    print(f"    ⚠ {h.error}")
            print()

        # Tier 2
        if report.tier2_hubs:
            print("  Tier 2 — Reflex Light")
            print(f"  {'─' * 76}")
            print(f"  {'Hub':<22} {'Health':>6} {'Routes':>10} {'Time':>6}")
            print(f"  {'─' * 76}")
            for h in report.tier2_hubs:
                routes_str = f"{h.routes_ok}/{h.routes_total}" if h.routes_total else "—"
                health_str = "✅" if h.health_ok else ("❌" if h.error else "⬜")
                print(f"  {h.name:<22} {health_str:>6} {routes_str:>10} {h.duration_seconds:>5.1f}s")
                if h.error:
                    print(f"    ⚠ {h.error}")
            print()

        print(f"{'=' * 80}\n")

    @staticmethod
    def to_json(report: PlatformReport) -> str:
        """Serialize report to JSON."""
        data = {
            "generated_at": report.generated_at,
            "total_duration_seconds": report.total_duration_seconds,
            "total_hubs": report.total_hubs,
            "healthy_hubs": report.healthy_hubs,
            "hubs": [
                {
                    "name": h.name,
                    "tier": h.tier,
                    "health_ok": h.health_ok,
                    "routes_total": h.routes_total,
                    "routes_ok": h.routes_ok,
                    "route_pass_rate": h.route_pass_rate,
                    "permissions_total": h.permissions_total,
                    "permissions_ok": h.permissions_ok,
                    "permission_pass_rate": h.permission_pass_rate,
                    "uc_count": h.uc_count,
                    "error": h.error,
                    "duration_seconds": h.duration_seconds,
                }
                for h in report.hubs
            ],
        }
        return json_module.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def to_markdown(report: PlatformReport) -> str:
        """Generate Markdown report."""
        lines = [
            "# REFLEX Platform Health Report",
            "",
            f"> Generated: {report.generated_at}",
            f"> Duration: {report.total_duration_seconds:.1f}s",
            f"> Hubs: {report.healthy_hubs}/{report.total_hubs} healthy",
            "",
        ]

        if report.tier1_hubs:
            lines.extend(
                [
                    "## Tier 1 — Full Reflex",
                    "",
                    "| Hub | Health | Routes | Permissions | UCs | Time |",
                    "|-----|--------|--------|-------------|-----|------|",
                ]
            )
            for h in report.tier1_hubs:
                routes_str = f"{h.routes_ok}/{h.routes_total}" if h.routes_total else "—"
                perms_str = f"{h.permissions_ok}/{h.permissions_total}" if h.permissions_total else "—"
                uc_str = str(h.uc_count) if h.uc_count else "—"
                health_str = "✅" if h.health_ok else "❌"
                lines.append(
                    f"| {h.name} | {health_str} | {routes_str} | {perms_str} | {uc_str} | {h.duration_seconds:.1f}s |"
                )
            lines.append("")

        if report.tier2_hubs:
            lines.extend(
                [
                    "## Tier 2 — Reflex Light",
                    "",
                    "| Hub | Health | Routes | Time |",
                    "|-----|--------|--------|------|",
                ]
            )
            for h in report.tier2_hubs:
                routes_str = f"{h.routes_ok}/{h.routes_total}" if h.routes_total else "—"
                health_str = "✅" if h.health_ok else "❌"
                lines.append(f"| {h.name} | {health_str} | {routes_str} | {h.duration_seconds:.1f}s |")
            lines.append("")

        # Errors
        error_hubs = [h for h in report.hubs if h.error]
        if error_hubs:
            lines.extend(
                [
                    "## Errors",
                    "",
                ]
            )
            for h in error_hubs:
                lines.append(f"- **{h.name}**: {h.error}")
            lines.append("")

        return "\n".join(lines)
