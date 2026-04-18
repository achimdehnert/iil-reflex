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

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)

# ── Hub Registry ──────────────────────────────────────────────────────────────

HUBS: list[dict[str, Any]] = [
    {
        "name": "Coach Hub",
        "slug": "coach-hub",
        "description": "Coaching platform — Assessments, QuickCheck, Maturity-Scoring.",
        "icon": "🎯",
        "color": "accent",
        "category": "product",
        "tags": ["Coaching", "SaaS"],
        "port": 8007,
        "container_name": "coach_hub_web",
        "prod_url": "https://kiohnerisiko.de",
        "sort_order": 5,
    },
    {
        "name": "Schutztat Risk Hub",
        "slug": "risk-hub",
        "description": "Gefährdungsbeurteilungen, Hazard-Analyse, Maßnahmen-Tracking.",
        "icon": "⚠️",
        "color": "red",
        "category": "product",
        "tags": ["Django Ninja", "SaaS"],
        "port": 8090,
        "container_name": "risk_hub_web",
        "prod_url": "https://schutztat.de",
        "sort_order": 10,
    },
    {
        "name": "BF Agent",
        "slug": "bfagent",
        "description": "Book Factory Agent — AI-powered creative writing and publishing.",
        "icon": "📚",
        "color": "purple",
        "category": "product",
        "tags": ["AI Agent"],
        "port": 8000,
        "container_name": "bfagent_web",
        "prod_url": "https://bfagent.iil.pet",
        "sort_order": 20,
    },
    {
        "name": "Writing Hub",
        "slug": "writing-hub",
        "description": "Buchreihen, Kapitel, Charaktere — Romane mit KI schreiben.",
        "icon": "✍️",
        "color": "amber",
        "category": "product",
        "tags": ["Writing", "AI"],
        "port": 8095,
        "container_name": "writing_hub_web",
        "prod_url": "https://writing.iil.pet",
        "sort_order": 25,
    },
    {
        "name": "DriftTales",
        "slug": "travel-beat",
        "description": "AI-generated travel stories with smart location enrichment.",
        "icon": "✈️",
        "color": "cyan",
        "category": "product",
        "tags": ["Travel"],
        "port": 8089,
        "container_name": "travel_beat_web",
        "prod_url": "https://drifttales.app",
        "sort_order": 30,
    },
    {
        "name": "Weltenforger",
        "slug": "weltenhub",
        "description": "Story universe platform — world-building and narrative design.",
        "icon": "🌐",
        "color": "pink",
        "category": "product",
        "tags": ["Creative"],
        "port": 8081,
        "container_name": "weltenhub_web",
        "prod_url": "https://weltenforger.com",
        "sort_order": 35,
    },
    {
        "name": "137herz",
        "slug": "137-hub",
        "description": "Das Erwachen — Community Hub, Newsletter und Supersystem Chatbot.",
        "icon": "🔮",
        "color": "purple",
        "category": "product",
        "tags": ["Community", "AI"],
        "port": 8137,
        "prod_url": "https://137herz.de",
        "sort_order": 40,
    },
    {
        "name": "Wedding Hub",
        "slug": "wedding-hub",
        "description": "Hochzeitsplanung — Events, Gäste, Budget, Timeline.",
        "icon": "💍",
        "color": "pink",
        "category": "product",
        "tags": ["Events"],
        "port": 8093,
        "container_name": "wedding_hub_web",
        "prod_url": "https://wedding-hub.iil.pet",
        "sort_order": 45,
    },
    {
        "name": "NL2CAD",
        "slug": "cad-hub",
        "description": "CAD Hub — IFC/DXF, Brandschutz, DIN 277, GAEB-Export.",
        "icon": "📐",
        "color": "green",
        "category": "product",
        "tags": ["CAD", "AI"],
        "port": 8094,
        "container_name": "cad_hub_web",
        "prod_url": "https://nl2cad.de",
        "sort_order": 50,
    },
    {
        "name": "Prezimo",
        "slug": "pptx-hub",
        "description": "AI-assisted PPTX generation with templates.",
        "icon": "📊",
        "color": "amber",
        "category": "product",
        "tags": ["PPTX"],
        "port": 8020,
        "container_name": "pptx_hub_web",
        "prod_url": "https://prezimo.de",
        "sort_order": 55,
    },
    {
        "name": "Trading Hub",
        "slug": "trading-hub",
        "description": "Algorithmic trading signals and portfolio analysis.",
        "icon": "📈",
        "color": "green",
        "category": "product",
        "tags": ["Finance"],
        "port": 8088,
        "container_name": "trading_hub_web",
        "prod_url": "https://ai-trades.de",
        "sort_order": 60,
    },
    {
        "name": "Bieterpilot",
        "slug": "ausschreibungs-hub",
        "description": "Ausschreibungsmanagement — Vergabe, Angebote, Dokumente.",
        "icon": "📋",
        "color": "cyan",
        "category": "product",
        "tags": ["Vergabe", "SaaS"],
        "port": 8101,
        "container_name": "ausschreibungs_hub_web",
        "prod_url": "https://bieterpilot.de",
        "sort_order": 65,
    },
    {
        "name": "Tax Hub",
        "slug": "tax-hub",
        "description": "Steuerberatung SaaS — Mandanten, Bescheide, Fristen, DMS.",
        "icon": "🧾",
        "color": "green",
        "category": "product",
        "tags": ["Tax", "SaaS"],
        "port": 8104,
        "container_name": "tax_hub_web",
        "prod_url": "https://tax.iil.pet",
        "sort_order": 72,
    },
    {
        "name": "Illustration Hub",
        "slug": "illustration-hub",
        "description": "KI-gestützte Illustration — Buchcover, Szenen, Character Art.",
        "icon": "🎨",
        "color": "pink",
        "category": "product",
        "tags": ["AI", "Illustration"],
        "port": 8096,
        "container_name": "illustration_hub_web",
        "prod_url": "https://illustration.iil.pet",
        "sort_order": 73,
    },
    {
        "name": "Learn Hub",
        "slug": "learn-hub",
        "description": "Lernplattform — Kurse, Quizze, Zertifikate, SCORM, Gamification.",
        "icon": "🎓",
        "color": "accent",
        "category": "product",
        "tags": ["Learning", "LMS"],
        "port": 8100,
        "container_name": "learn_hub_web",
        "prod_url": "https://learn.iil.pet",
        "sort_order": 74,
    },
    {
        "name": "Research Hub",
        "slug": "research-hub",
        "description": "KI-Recherche — Quellen, Zusammenfassungen, RAG-Pipelines.",
        "icon": "🔬",
        "color": "cyan",
        "category": "product",
        "tags": ["Research", "AI"],
        "port": 8098,
        "container_name": "research_hub_web",
        "prod_url": "https://research.iil.pet",
        "sort_order": 75,
    },
    {
        "name": "DMS Hub",
        "slug": "dms-hub",
        "description": "Dokumentenmanagement — Upload, OCR, d.velop-Archivierung.",
        "icon": "📁",
        "color": "amber",
        "category": "internal",
        "tags": ["DMS", "d.velop"],
        "port": 8107,
        "container_name": "dms_hub_web",
        "prod_url": "https://dms.iil.pet",
        "sort_order": 76,
    },
    {
        "name": "dev-hub",
        "slug": "dev-hub",
        "description": "Developer Portal — Service Catalog, ADRs, Health Checks.",
        "icon": "🛠️",
        "color": "accent",
        "category": "internal",
        "tags": ["DevOps", "Portal"],
        "port": 8085,
        "container_name": "devhub_web",
        "prod_url": "https://devhub.iil.pet",
        "sort_order": 80,
    },
    {
        "name": "Billing Hub",
        "slug": "billing-hub",
        "description": "Central billing service — Subscriptions, Invoices, Stripe.",
        "icon": "💰",
        "color": "green",
        "category": "internal",
        "tags": ["Billing"],
        "port": 8092,
        "container_name": "billing-hub-web",
        "prod_url": "https://billing.iil.pet",
        "sort_order": 85,
    },
    {
        "name": "Recruiting Hub",
        "slug": "recruiting-hub",
        "description": "Recruiting & Bewerbermanagement — Stellen, Bewerber, Pipeline.",
        "icon": "👤",
        "color": "accent",
        "category": "internal",
        "tags": ["HR", "Recruiting"],
        "port": 8103,
        "container_name": "recruiting_hub_web",
        "sort_order": 86,
    },
]


# Compose file search order — local dev first, prod as fallback
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.local.yml",
    "docker-compose.dev.yml",
    "docker-compose.prod.yml",
)


def find_compose_file(repo_path: Path) -> str | None:
    """Find the best compose file in a repo directory."""
    for cf in COMPOSE_FILES:
        if (repo_path / cf).exists():
            return cf
    return None


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
            threading.Thread(
                target=refresh_all_health, args=(self.github_dir,), daemon=True
            ).start()
        self._json_response(result)

    def _handle_stop(self, slug: str):
        result = stop_hub(slug, self.github_dir)
        if result.get("ok"):
            threading.Thread(
                target=refresh_all_health, args=(self.github_dir,), daemon=True
            ).start()
        self._json_response(result)

    def _handle_refresh(self):
        statuses = refresh_all_health(self.github_dir)
        data = {slug: asdict(st) for slug, st in statuses.items()}
        self._json_response(data)

    def _serve_html(self):
        html = generate_dashboard_html()
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── HTML Generator ────────────────────────────────────────────────────────────

def generate_dashboard_html() -> str:
    """Generate the full dashboard HTML with embedded CSS/JS."""
    hub_cards = ""
    for hub in sorted(HUBS, key=lambda h: h.get("sort_order", 100)):
        tags_html = "".join(
            f'<span class="tag bg-{hub["color"]}">{t}</span>' for t in hub.get("tags", [])
        )
        hub_cards += f"""
        <div class="card" data-slug="{hub['slug']}" data-port="{hub.get('port', 0)}"
             data-category="{hub.get('category', 'product')}"
             data-name="{hub['name'].lower()}"
             data-tags="{','.join(hub.get('tags', [])).lower()}">
            <div class="card-header">
                <div class="icon bg-{hub['color']}">{hub['icon']}</div>
                <div class="card-title">
                    <h2>{hub['name']}</h2>
                    <span class="health-dot" id="dot-{hub['slug']}" title="Checking..."></span>
                </div>
            </div>
            <p class="desc">{hub['description']}</p>
            <div class="tags">{tags_html}</div>
            <div class="card-links">
                <a href="http://localhost:{hub.get('port', '#')}" class="link-app"
                   target="_blank" id="link-{hub['slug']}">&#9654; App</a>
                <a href="http://localhost:{hub.get('port', '#')}/admin/"
                   class="link-admin" target="_blank">&#9881; Admin</a>
                <button class="btn-start" id="btn-{hub['slug']}"
                        onclick="toggleHub('{hub['slug']}')"
                        title="Start/Stop via Docker Compose">&#9654; Start</button>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IIL Platform — Local Dev</title>
    <style>
        :root {{
            --bg: #0f172a; --surface: #1e293b; --border: #334155;
            --text: #e2e8f0; --muted: #94a3b8; --accent: #3b82f6;
            --green: #22c55e; --amber: #f59e0b; --red: #ef4444;
            --purple: #a855f7; --cyan: #06b6d4; --pink: #ec4899;
            --orange: #f97316;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: var(--bg); color: var(--text); min-height: 100vh;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 2.5rem 1.5rem; }}
        header {{ text-align: center; margin-bottom: 2rem; }}
        header h1 {{
            font-size: 2.5rem; font-weight: 800; letter-spacing: -0.03em;
            background: linear-gradient(135deg, var(--accent), var(--cyan));
            background-clip: text; -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        header p {{ color: var(--muted); font-size: 1.1rem; margin-top: 0.5rem; }}
        .env-badge {{
            display: inline-block; background: rgba(34,197,94,0.15); color: var(--green);
            padding: 0.3em 1em; border-radius: 20px; font-size: 0.85rem; font-weight: 600;
            margin-top: 0.5rem;
        }}
        .stats {{
            display: flex; gap: 1.5rem; justify-content: center;
            margin-bottom: 2rem; flex-wrap: wrap;
        }}
        .stat {{ text-align: center; }}
        .stat-value {{ font-size: 1.8rem; font-weight: 800; color: var(--accent); }}
        .stat-label {{
            font-size: 0.75rem; color: var(--muted);
            text-transform: uppercase; letter-spacing: 0.05em;
        }}
        .toolbar {{
            display: flex; gap: 0.75rem; margin-bottom: 2rem;
            flex-wrap: wrap; align-items: center;
        }}
        .search-input {{
            flex: 1; min-width: 200px; background: var(--surface);
            border: 1px solid var(--border); border-radius: 8px;
            color: var(--text); padding: 0.6rem 1rem; font-size: 0.9rem; outline: none;
        }}
        .search-input:focus {{ border-color: var(--accent); }}
        .search-input::placeholder {{ color: var(--muted); }}
        .filter-btn {{
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 8px; color: var(--muted); padding: 0.6rem 1rem;
            font-size: 0.8rem; font-weight: 600; cursor: pointer;
        }}
        .filter-btn:hover, .filter-btn.active {{
            border-color: var(--accent); color: var(--accent);
            background: rgba(59,130,246,0.08);
        }}
        .grid {{
            display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 1.25rem;
        }}
        .card {{
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 12px; padding: 1.5rem;
            display: flex; flex-direction: column; gap: 0.5rem;
            transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
        }}
        .card:hover {{
            transform: translateY(-3px); border-color: var(--accent);
            box-shadow: 0 8px 30px rgba(59,130,246,0.12);
        }}
        .card.inactive {{ opacity: 0.55; }}
        .card.inactive:hover {{ opacity: 0.85; }}
        .card.hidden {{ display: none; }}
        .card-header {{ display: flex; align-items: center; gap: 0.75rem; }}
        .icon {{
            width: 44px; height: 44px; border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 1.4rem; flex-shrink: 0;
        }}
        .card-title {{ display: flex; align-items: center; gap: 0.5rem; flex: 1; }}
        .card-title h2 {{ font-size: 1.15rem; font-weight: 700; }}
        .health-dot {{
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--muted); flex-shrink: 0; transition: background 0.3s;
        }}
        .health-dot.healthy {{ background: var(--green); box-shadow: 0 0 6px rgba(34,197,94,0.5); }}
        .health-dot.unhealthy {{ background: var(--red); box-shadow: 0 0 6px rgba(239,68,68,0.4); }}
        .health-dot.starting {{ background: var(--amber); animation: pulse 1s infinite; }}
        @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
        p.desc {{ color: var(--muted); font-size: 0.88rem; line-height: 1.5; flex-grow: 1; }}
        .tags {{ display: flex; gap: 0.4rem; flex-wrap: wrap; }}
        .tag {{
            display: inline-block; font-size: 0.7rem; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.05em;
            padding: 0.2em 0.6em; border-radius: 4px;
        }}
        .card-links {{
            display: flex; gap: 0.5rem; margin-top: 0.5rem;
            padding-top: 0.5rem; border-top: 1px solid var(--border); flex-wrap: wrap;
        }}
        .card-links a, .btn-start {{
            font-size: 0.78rem; font-weight: 600; text-decoration: none;
            padding: 0.3em 0.7em; border-radius: 6px; transition: background 0.15s;
            cursor: pointer; border: none;
        }}
        .link-app {{ color: var(--accent); background: rgba(59,130,246,0.1); }}
        .link-app:hover {{ background: rgba(59,130,246,0.2); }}
        .link-admin {{ color: var(--amber); background: rgba(245,158,11,0.1); }}
        .link-admin:hover {{ background: rgba(245,158,11,0.2); }}
        .btn-start {{
            color: var(--green); background: rgba(34,197,94,0.1);
            margin-left: auto;
        }}
        .btn-start:hover {{ background: rgba(34,197,94,0.2); }}
        .btn-start.running {{
            color: var(--red); background: rgba(239,68,68,0.1);
        }}
        .btn-start.running:hover {{ background: rgba(239,68,68,0.2); }}
        .btn-start.busy {{
            color: var(--amber); background: rgba(245,158,11,0.1);
            pointer-events: none;
        }}
        .bg-accent {{ background: rgba(59,130,246,0.15); color: var(--accent); }}
        .bg-red {{ background: rgba(239,68,68,0.15); color: var(--red); }}
        .bg-green {{ background: rgba(34,197,94,0.15); color: var(--green); }}
        .bg-amber {{ background: rgba(245,158,11,0.15); color: var(--amber); }}
        .bg-purple {{ background: rgba(168,85,247,0.15); color: var(--purple); }}
        .bg-cyan {{ background: rgba(6,182,212,0.15); color: var(--cyan); }}
        .bg-pink {{ background: rgba(236,72,153,0.15); color: var(--pink); }}
        .bg-orange {{ background: rgba(249,115,22,0.15); color: var(--orange); }}
        .bg-muted {{ background: rgba(148,163,184,0.15); color: var(--muted); }}
        .toast {{
            position: fixed; bottom: 2rem; right: 2rem;
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 10px; padding: 1rem 1.5rem; color: var(--text);
            font-size: 0.9rem; box-shadow: 0 8px 30px rgba(0,0,0,0.3);
            transform: translateY(100px); opacity: 0;
            transition: all 0.3s ease;
        }}
        .toast.show {{ transform: translateY(0); opacity: 1; }}
        footer {{
            text-align: center; margin-top: 3rem; padding-top: 1.5rem;
            border-top: 1px solid var(--border); color: var(--muted); font-size: 0.85rem;
        }}
        footer a {{ color: var(--accent); text-decoration: none; }}
        .no-results {{
            text-align: center; color: var(--muted); padding: 3rem; display: none;
        }}
        @media (max-width: 700px) {{
            .grid {{ grid-template-columns: 1fr; }}
            header h1 {{ font-size: 1.8rem; }}
            .toolbar {{ flex-direction: column; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>IIL Platform</h1>
        <p>Integrated Intelligence Layer &mdash; App Ecosystem</p>
        <div class="env-badge">&#127968; Local Development</div>
    </header>
    <div class="stats">
        <div class="stat">
            <div class="stat-value">{len(HUBS)}</div>
            <div class="stat-label">Platform Hubs</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="healthy-count">&mdash;</div>
            <div class="stat-label">Running</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="stopped-count">&mdash;</div>
            <div class="stat-label">Stopped</div>
        </div>
    </div>
    <div class="toolbar">
        <input type="text" class="search-input" id="search" placeholder="Search hubs..." autocomplete="off">
        <button class="filter-btn active" data-filter="all">All</button>
        <button class="filter-btn" data-filter="running">Running</button>
        <button class="filter-btn" data-filter="stopped">Stopped</button>
        <button class="filter-btn" data-filter="product">Products</button>
        <button class="filter-btn" data-filter="internal">Internal</button>
    </div>
    <div class="grid" id="hub-grid">
        {hub_cards}
    </div>
    <div class="no-results" id="no-results">No hubs match your search.</div>
    <div class="toast" id="toast"></div>
    <footer>
        <p>IIL Platform &bull; REFLEX Dashboard &bull;
           <a href="https://iil.pet" target="_blank">Production</a></p>
    </footer>
</div>
<script>
const cards = document.querySelectorAll('.card');
const searchInput = document.getElementById('search');
const filterBtns = document.querySelectorAll('.filter-btn');
const noResults = document.getElementById('no-results');
let activeFilter = 'all';
let hubStates = {{}};

function applyFilters() {{
    const q = searchInput.value.toLowerCase().trim();
    let visible = 0;
    cards.forEach(card => {{
        const name = card.dataset.name || '';
        const tags = card.dataset.tags || '';
        const cat = card.dataset.category || '';
        const slug = card.dataset.slug;
        const isRunning = hubStates[slug] && hubStates[slug].healthy;
        const matchSearch = !q || name.includes(q) || tags.includes(q);
        let matchFilter = true;
        if (activeFilter === 'running') matchFilter = isRunning;
        else if (activeFilter === 'stopped') matchFilter = !isRunning;
        else if (activeFilter !== 'all') matchFilter = cat === activeFilter;
        const show = matchSearch && matchFilter;
        card.classList.toggle('hidden', !show);
        if (show) visible++;
    }});
    noResults.style.display = visible === 0 ? 'block' : 'none';
}}

searchInput.addEventListener('input', applyFilters);
filterBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        applyFilters();
    }});
}});

function showToast(msg, duration) {{
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), duration || 3000);
}}

function updateUI(statuses) {{
    hubStates = statuses;
    let running = 0, stopped = 0;
    cards.forEach(card => {{
        const slug = card.dataset.slug;
        const st = statuses[slug];
        const dot = document.getElementById('dot-' + slug);
        const btn = document.getElementById('btn-' + slug);
        if (st && st.healthy) {{
            running++;
            card.classList.remove('inactive');
            if (dot) {{ dot.className = 'health-dot healthy'; dot.title = st.response_ms + 'ms'; }}
            if (btn) {{ btn.className = 'btn-start running'; btn.innerHTML = '&#9724; Stop'; }}
        }} else {{
            stopped++;
            card.classList.add('inactive');
            if (dot) {{ dot.className = 'health-dot unhealthy'; dot.title = 'Not running'; }}
            if (btn) {{ btn.className = 'btn-start'; btn.innerHTML = '&#9654; Start'; }}
        }}
    }});
    document.getElementById('healthy-count').textContent = running;
    document.getElementById('stopped-count').textContent = stopped;
    applyFilters();
}}

async function fetchStatus() {{
    try {{
        const resp = await fetch('/api/status');
        const data = await resp.json();
        updateUI(data);
    }} catch (e) {{ console.error('Status fetch failed:', e); }}
}}

async function toggleHub(slug) {{
    const btn = document.getElementById('btn-' + slug);
    const dot = document.getElementById('dot-' + slug);
    const isRunning = hubStates[slug] && hubStates[slug].healthy;
    const action = isRunning ? 'stop' : 'start';

    if (btn) {{ btn.className = 'btn-start busy'; btn.innerHTML = '&#8987; ...'; }}
    if (dot) dot.className = 'health-dot starting';
    showToast((isRunning ? 'Stopping' : 'Starting') + ' ' + slug + '...', 5000);

    try {{
        const resp = await fetch('/api/' + action + '/' + slug);
        const data = await resp.json();
        if (data.ok) {{
            showToast(data.message || (slug + ' ' + action + 'ed'), 3000);
            setTimeout(fetchStatus, isRunning ? 2000 : 8000);
        }} else {{
            showToast('Error: ' + (data.error || 'unknown'), 5000);
            fetchStatus();
        }}
    }} catch (e) {{
        showToast('Network error: ' + e, 5000);
        fetchStatus();
    }}
}}

// Card click → open app if running, otherwise start
cards.forEach(card => {{
    card.addEventListener('click', (e) => {{
        if (e.target.closest('.card-links')) return;
        const slug = card.dataset.slug;
        const port = card.dataset.port;
        if (hubStates[slug] && hubStates[slug].healthy) {{
            window.open('http://localhost:' + port, '_blank');
        }} else {{
            toggleHub(slug);
        }}
    }});
    card.style.cursor = 'pointer';
}});

// Initial fetch + auto-refresh every 30s
fetchStatus();
setInterval(fetchStatus, 30000);
</script>
</body>
</html>"""


# ── Server Entry Point ────────────────────────────────────────────────────────

def run_dashboard(
    port: int = 9000,
    github_dir: str = "",
) -> None:
    """Start the dashboard web server."""
    if not github_dir:
        github_dir = str(Path.home() / "github")

    DashboardHandler.github_dir = github_dir

    print(f"\n  REFLEX Dashboard — Local Development")
    print(f"  {'─' * 45}")
    print(f"  GitHub Dir: {github_dir}")
    print(f"  Hubs:       {len(HUBS)}")
    print(f"  URL:        http://localhost:{port}")
    print(f"  {'─' * 45}")
    print(f"  Press Ctrl+C to stop.\n")

    # Initial health check in background
    threading.Thread(
        target=refresh_all_health, args=(github_dir,), daemon=True
    ).start()

    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.")
        server.server_close()
