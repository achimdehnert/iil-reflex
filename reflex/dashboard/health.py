"""
REFLEX Dashboard — Health checks, Docker control, and review caching.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from reflex.dashboard.registry import HUBS, find_compose_file

logger = logging.getLogger(__name__)


@dataclass
class HubStatus:
    """Runtime status of a hub."""

    slug: str
    healthy: bool = False
    response_ms: int = 0
    compose_file: str = ""
    repo_path: str = ""
    starting: bool = False


# ── Health Check Engine ───────────────────────────────────────────────────────

_status_cache: dict[str, HubStatus] = {}
_cache_lock = threading.Lock()


def check_hub_health(slug: str, port: int, timeout: float = 2.0) -> HubStatus:
    """Check if a hub is running on localhost."""
    status = HubStatus(slug=slug)
    for path in ("/livez/", "/healthz/"):
        url = f"http://localhost:{port}{path}"
        try:
            t0 = time.monotonic()
            resp = urlopen(url, timeout=timeout)  # noqa: S310
            elapsed = int((time.monotonic() - t0) * 1000)
            if resp.status == 200:
                status.healthy = True
                status.response_ms = elapsed
                return status
        except (URLError, OSError, TimeoutError):
            continue
    return status


def refresh_all_health(github_dir: str) -> dict[str, HubStatus]:
    """Refresh health for all registered hubs."""
    results: dict[str, HubStatus] = {}
    for hub in HUBS:
        slug = hub["slug"]
        port = hub.get("port", 0)
        if not port:
            continue
        st = check_hub_health(slug, port)
        # Find compose file
        repo_path = Path(github_dir) / slug
        if repo_path.is_dir():
            st.repo_path = str(repo_path)
            cf = find_compose_file(repo_path)
            if cf:
                st.compose_file = cf
        results[slug] = st
    with _cache_lock:
        _status_cache.clear()
        _status_cache.update(results)
    return results


def get_cached_status() -> dict[str, HubStatus]:
    """Return cached hub status."""
    with _cache_lock:
        return dict(_status_cache)


# ── Docker Compose Control ────────────────────────────────────────────────────


def start_hub(slug: str, github_dir: str) -> dict[str, Any]:
    """Start a hub via docker compose up -d."""
    repo_path = Path(github_dir) / slug
    if not repo_path.is_dir():
        return {"ok": False, "error": f"Repo not found: {repo_path}"}

    compose_file = find_compose_file(repo_path)
    if not compose_file:
        return {"ok": False, "error": f"No docker-compose file in {repo_path}"}

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", compose_file, "up", "-d"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return {"ok": True, "message": f"Started {slug} via {compose_file}"}
        return {"ok": False, "error": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout after 120s"}
    except FileNotFoundError:
        return {"ok": False, "error": "docker not found"}


def stop_hub(slug: str, github_dir: str) -> dict[str, Any]:
    """Stop a hub via docker compose down."""
    repo_path = Path(github_dir) / slug
    if not repo_path.is_dir():
        return {"ok": False, "error": f"Repo not found: {repo_path}"}

    compose_file = find_compose_file(repo_path)
    if not compose_file:
        return {"ok": False, "error": f"No docker-compose file in {repo_path}"}

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", compose_file, "down"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return {"ok": True, "message": f"Stopped {slug}"}
        return {"ok": False, "error": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout after 60s"}
    except FileNotFoundError:
        return {"ok": False, "error": "docker not found"}


# ── HTTP Handler ──────────────────────────────────────────────────────────────


# ── Review Score Cache ────────────────────────────────────────────────────────

_review_cache: dict[str, dict] = {}
_review_lock = threading.Lock()
GRAFANA_URL = os.environ.get("REFLEX_GRAFANA_URL", "http://localhost:3000")  # hardcoded-ok: CLI package, decouple not a dependency
OUTLINE_URL = os.environ.get("REFLEX_OUTLINE_URL", "https://knowledge.iil.pet")  # hardcoded-ok: CLI package, decouple not a dependency


def refresh_all_reviews(github_dir: str) -> dict[str, dict]:
    """Run reflex review for all repos and cache results."""
    from reflex.review import run_review

    results: dict[str, dict] = {}
    for hub in HUBS:
        slug = hub["slug"]
        repo_path = Path(github_dir) / slug
        if not repo_path.is_dir():
            continue
        try:
            review_results = run_review(
                repo=slug,
                github_dir=github_dir,
                triggered_by="dashboard",
            )
            total_findings = sum(len(r.findings) for r in review_results)
            total_block = sum(len(r.findings_block) for r in review_results)
            total_warn = sum(len(r.findings_warn) for r in review_results)
            avg_score = (
                round(sum(r.score_pct for r in review_results) / len(review_results), 1) if review_results else 0
            )
            # Extract UC metadata if available
            uc_meta = {}
            for r in review_results:
                if r.review_type == "uc" and r.metadata:
                    uc_meta = r.metadata

            results[slug] = {
                "score": avg_score,
                "findings": total_findings,
                "block": total_block,
                "warn": total_warn,
                "plugins": len(review_results),
                "uc_total": uc_meta.get("uc_total", 0),
                "uc_status": uc_meta.get("status_counts", {}),
            }
        except Exception as exc:
            logger.warning("Review failed for %s: %s", slug, exc)
            results[slug] = {
                "score": -1,
                "findings": 0,
                "block": 0,
                "warn": 0,
                "plugins": 0,
                "uc_total": 0,
                "uc_status": {},
            }

    with _review_lock:
        _review_cache.clear()
        _review_cache.update(results)
    return results


def get_cached_reviews() -> dict[str, dict]:
    """Return cached review scores."""
    with _review_lock:
        return dict(_review_cache)
