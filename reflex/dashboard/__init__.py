"""
REFLEX Dashboard — Local development landing page with app tiles.

Mirrors iil.pet but for localhost:
- Shows all platform hubs as cards with health status
- Click on inactive app → starts docker compose
- Auto-refresh health every 30s
- Zero dependencies (stdlib http.server + inline HTML)

Usage:
    python -m reflex dashboard [--port 9000] [--github-dir ~/github]
"""

from reflex.dashboard.handler import DashboardHandler
from reflex.dashboard.health import (
    HubStatus,
    check_hub_health,
    get_cached_reviews,
    get_cached_status,
    refresh_all_health,
    refresh_all_reviews,
    start_hub,
    stop_hub,
)
from reflex.dashboard.registry import COMPOSE_FILES, HUBS, find_compose_file
from reflex.dashboard.server import run_dashboard
from reflex.dashboard.template import generate_dashboard_html

__all__ = [
    "COMPOSE_FILES",
    "DashboardHandler",
    "HUBS",
    "HubStatus",
    "check_hub_health",
    "find_compose_file",
    "generate_dashboard_html",
    "get_cached_reviews",
    "get_cached_status",
    "refresh_all_health",
    "refresh_all_reviews",
    "run_dashboard",
    "start_hub",
    "stop_hub",
]
