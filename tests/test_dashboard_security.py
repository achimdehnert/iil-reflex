"""Security regression tests for the dashboard HTTP handler.

Covers the hardening in PR sec/dashboard-and-ssrf-hardening:
  - Host-header allowlist (DNS-rebinding / cross-origin defence)
  - container control is POST-only (GET start/stop is gone → CSRF fix)
  - slug must be a known hub (no arbitrary `docker compose` directory)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from reflex.dashboard.handler import DashboardHandler


def _make_handler(path: str, host: str = "localhost:9000") -> DashboardHandler:
    """Build a handler instance without running BaseHTTPRequestHandler.__init__."""
    h = DashboardHandler.__new__(DashboardHandler)
    h.path = path
    h.headers = {"Host": host}
    h.github_dir = "/repos"
    h.send_error = MagicMock()
    h._json_response = MagicMock()
    h._serve_html = MagicMock()
    h._serve_status = MagicMock()
    return h


class TestHostAllowlist:
    """Requests with a non-loopback Host header are rejected (DNS rebinding)."""

    def test_should_reject_foreign_host_on_get(self):
        h = _make_handler("/", host="attacker.com")
        h.do_GET()
        h.send_error.assert_called_once()
        assert h.send_error.call_args[0][0] == 403

    def test_should_reject_foreign_host_on_post(self):
        h = _make_handler("/api/stop/risk-hub", host="evil.example")
        h.do_POST()
        h.send_error.assert_called_once()
        assert h.send_error.call_args[0][0] == 403

    def test_should_allow_localhost_host(self):
        h = _make_handler("/", host="localhost:9000")
        h.do_GET()
        h.send_error.assert_not_called()
        h._serve_html.assert_called_once()


class TestCsrfHardening:
    """Container control must not be reachable via GET (CSRF via <img>/prefetch)."""

    def test_should_not_handle_start_via_get(self):
        h = _make_handler("/api/start/risk-hub")
        with patch("reflex.dashboard.handler.start_hub") as start:
            h.do_GET()
            start.assert_not_called()
        h.send_error.assert_called_once_with(404)

    def test_should_handle_start_via_post(self):
        h = _make_handler("/api/start/risk-hub")
        with (
            patch("reflex.dashboard.handler.start_hub", return_value={"ok": False}) as start,
            patch("reflex.dashboard.handler.threading"),
        ):
            h.do_POST()
            start.assert_called_once_with("risk-hub", "/repos")


class TestSlugAllowlist:
    """Only known hub slugs may control containers (no path traversal)."""

    def test_should_reject_unknown_slug(self):
        h = _make_handler("/api/start/../../../tmp/evil")
        with patch("reflex.dashboard.handler.start_hub") as start:
            h.do_POST()
            start.assert_not_called()
        # 400 returned via _json_response, start_hub never reached.
        h._json_response.assert_called_once()
        assert h._json_response.call_args.kwargs.get("status") == 400

    def test_should_accept_known_slug(self):
        h = _make_handler("/api/stop/risk-hub")
        with (
            patch("reflex.dashboard.handler.stop_hub", return_value={"ok": False}) as stop,
            patch("reflex.dashboard.handler.threading"),
        ):
            h.do_POST()
            stop.assert_called_once_with("risk-hub", "/repos")
