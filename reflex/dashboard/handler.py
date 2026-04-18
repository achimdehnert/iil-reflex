"""
REFLEX Dashboard — HTTP request handler.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler
from typing import Any

from reflex.dashboard.health import (
    get_cached_reviews,
    get_cached_status,
    refresh_all_health,
    refresh_all_reviews,
    start_hub,
    stop_hub,
)
from reflex.dashboard.template import generate_dashboard_html

logger = logging.getLogger(__name__)


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local dashboard."""

    github_dir: str = ""

    def log_message(self, format, *args):
        logger.debug(format, *args)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_html()
        elif self.path == "/api/status":
            self._serve_status()
        elif self.path.startswith("/api/start/"):
            slug = self.path.split("/api/start/")[1].rstrip("/")
            self._handle_start(slug)
        elif self.path.startswith("/api/stop/"):
            slug = self.path.split("/api/stop/")[1].rstrip("/")
            self._handle_stop(slug)
        elif self.path == "/api/review":
            self._serve_review()
        elif self.path == "/api/review/refresh":
            self._handle_review_refresh()
        elif self.path == "/api/refresh":
            self._handle_refresh()
        else:
            self.send_error(404)

    def _json_response(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_status(self):
        statuses = get_cached_status()
        data = {slug: asdict(st) for slug, st in statuses.items()}
        self._json_response(data)

    def _handle_start(self, slug: str):
        result = start_hub(slug, self.github_dir)
        # Refresh health after start
        if result.get("ok"):
            threading.Thread(target=refresh_all_health, args=(self.github_dir,), daemon=True).start()
        self._json_response(result)

    def _handle_stop(self, slug: str):
        result = stop_hub(slug, self.github_dir)
        if result.get("ok"):
            threading.Thread(target=refresh_all_health, args=(self.github_dir,), daemon=True).start()
        self._json_response(result)

    def _handle_refresh(self):
        statuses = refresh_all_health(self.github_dir)
        data = {slug: asdict(st) for slug, st in statuses.items()}
        self._json_response(data)

    def _serve_review(self):
        reviews = get_cached_reviews()
        self._json_response(reviews)

    def _handle_review_refresh(self):
        reviews = refresh_all_reviews(self.github_dir)
        self._json_response(reviews)

    def _serve_html(self):
        html = generate_dashboard_html()
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
