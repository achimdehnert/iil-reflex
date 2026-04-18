"""
REFLEX Dashboard — Server entry point.
"""

from __future__ import annotations

import threading
import time
from http.server import HTTPServer
from pathlib import Path

from reflex.dashboard.handler import DashboardHandler
from reflex.dashboard.health import refresh_all_health, refresh_all_reviews
from reflex.dashboard.registry import HUBS


def run_dashboard(
    port: int = 9000,
    github_dir: str = "",
) -> None:
    """Start the dashboard web server."""
    if not github_dir:
        github_dir = str(Path.home() / "github")

    DashboardHandler.github_dir = github_dir

    print("\n  REFLEX Dashboard — Local Development")
    print(f"  {'─' * 45}")
    print(f"  GitHub Dir: {github_dir}")
    print(f"  Hubs:       {len(HUBS)}")
    print(f"  URL:        http://localhost:{port}")
    print(f"  {'─' * 45}")
    print("  Press Ctrl+C to stop.\n")

    # Initial health check in background
    threading.Thread(target=refresh_all_health, args=(github_dir,), daemon=True).start()

    # Initial review scores in background (delayed 5s to not slow startup)
    def _delayed_review():
        time.sleep(5)
        refresh_all_reviews(github_dir)

    threading.Thread(target=_delayed_review, daemon=True).start()

    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()
