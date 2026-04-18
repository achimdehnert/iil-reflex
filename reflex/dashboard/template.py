"""
REFLEX Dashboard — HTML/CSS/JS template generation.

This module contains the inline HTML generator for the dashboard.
A future improvement would be to use Jinja2 templates from a file.
"""

from __future__ import annotations

from reflex.dashboard.health import GRAFANA_URL, OUTLINE_URL
from reflex.dashboard.registry import HUBS

# ── HTML Generator ────────────────────────────────────────────────────────────


# Review Score JS — raw string, NOT f-string (avoids brace escaping issues)
_REVIEW_JS = """
<script>
let reviewData = {};

function updateReviewBadges(data) {
    reviewData = data;
    let totalScore = 0, totalFindings = 0, totalBlock = 0;
    let totalUC = 0, ucDraft = 0, ucImpl = 0, ucTested = 0, ucVerified = 0;
    let counted = 0;

    Object.entries(data).forEach(function([slug, review]) {
        var pill = document.getElementById("score-" + slug);
        var fc = document.getElementById("findings-" + slug);
        if (pill) {
            var score = review.score;
            if (score < 0) {
                pill.textContent = "N/A";
                pill.className = "score-pill";
            } else {
                pill.textContent = score + "%";
                pill.className = "score-pill " +
                    (score >= 80 ? "good" : score >= 50 ? "warn" : "bad");
            }
        }
        if (fc && review.findings > 0) {
            fc.textContent = review.block + " block, " + review.warn + " warn";
        }
        if (review.score >= 0) { totalScore += review.score; counted++; }
        totalFindings += review.findings || 0;
        totalBlock += review.block || 0;
        totalUC += review.uc_total || 0;
        var uc = review.uc_status || {};
        ucDraft += uc.draft || 0;
        ucImpl += uc.implemented || 0;
        ucTested += uc.tested || 0;
        ucVerified += uc.verified || 0;
    });

    var avgEl = document.getElementById("q-avg-score");
    if (avgEl && counted > 0) {
        var avg = Math.round(totalScore / counted);
        avgEl.textContent = avg + "%";
        avgEl.style.color = avg >= 80 ? "var(--green)" : avg >= 50 ? "var(--amber)" : "var(--red)";
    }
    var fEl = document.getElementById("q-total-findings");
    if (fEl) { fEl.textContent = totalFindings; fEl.style.color = "var(--amber)"; }
    var bEl = document.getElementById("q-total-block");
    if (bEl) bEl.textContent = totalBlock;
    var ucEl = document.getElementById("q-total-uc");
    if (ucEl) { ucEl.textContent = totalUC; ucEl.style.color = "var(--cyan)"; }

    var bar = document.getElementById("q-uc-bar");
    var legend = document.getElementById("q-uc-legend");
    if (bar && totalUC > 0) {
        var pct = function(n) { return ((n / totalUC) * 100).toFixed(1); };
        bar.innerHTML =
            (ucDraft ? '<div class="draft" style="width:' + pct(ucDraft) + '%"></div>' : "") +
            (ucImpl ? '<div class="implemented" style="width:' + pct(ucImpl) + '%"></div>' : "") +
            (ucTested ? '<div class="tested" style="width:' + pct(ucTested) + '%"></div>' : "") +
            (ucVerified ? '<div class="verified" style="width:' + pct(ucVerified) + '%"></div>' : "");
        if (legend) {
            legend.innerHTML =
                '<span>\u25a0 Draft: ' + ucDraft + '</span>' +
                '<span style="color:var(--accent)">\u25a0 Impl: ' + ucImpl + '</span>' +
                '<span style="color:var(--green)">\u25a0 Tested: ' + ucTested + '</span>' +
                '<span style="color:var(--cyan)">\u25a0 Verified: ' + ucVerified + '</span>';
        }
    }
}

function fetchReviews() {
    fetch("/api/review").then(function(resp) {
        return resp.json();
    }).then(function(data) {
        updateReviewBadges(data);
    }).catch(function(e) {
        console.error("Review fetch failed:", e);
    });
}

function refreshReviews() {
    showToast("Running reviews for all repos...", 10000);
    fetch("/api/review/refresh").then(function(resp) {
        return resp.json();
    }).then(function(data) {
        updateReviewBadges(data);
        showToast("Reviews updated!", 3000);
    }).catch(function(e) {
        showToast("Review refresh failed: " + e, 5000);
    });
}

setTimeout(fetchReviews, 2000);
</script>
"""


def generate_dashboard_html() -> str:
    """Generate the full dashboard HTML with embedded CSS/JS."""
    hub_cards = ""
    for hub in sorted(HUBS, key=lambda h: h.get("sort_order", 100)):
        tags_html = "".join(f'<span class="tag bg-{hub["color"]}">{t}</span>' for t in hub.get("tags", []))
        hub_cards += f"""
        <div class="card" data-slug="{hub["slug"]}" data-port="{hub.get("port", 0)}"
             data-category="{hub.get("category", "product")}"
             data-name="{hub["name"].lower()}"
             data-tags="{",".join(hub.get("tags", [])).lower()}">
            <div class="card-header">
                <div class="icon bg-{hub["color"]}">{hub["icon"]}</div>
                <div class="card-title">
                    <h2>{hub["name"]}</h2>
                    <span class="health-dot" id="dot-{hub["slug"]}" title="Checking..."></span>
                </div>
            </div>
            <p class="desc">{hub["description"]}</p>
            <div class="tags">{tags_html}</div>
            <div class="review-badge" id="review-{hub["slug"]}">
                <span class="score-pill" id="score-{hub["slug"]}">— %</span>
                <span class="finding-count" id="findings-{hub["slug"]}"></span>
            </div>
            <div class="card-links">
                <a href="http://localhost:{hub.get("port", "#")}" class="link-app"
                   target="_blank" id="link-{hub["slug"]}">&#9654; App</a>
                <a href="http://localhost:{hub.get("port", "#")}/admin/"
                   class="link-admin" target="_blank">&#9881; Admin</a>
                <a href="{GRAFANA_URL}/d/reflex-review?var-repo={hub["slug"]}" class="link-grafana" target="_blank">&#128202; Grafana</a>
                <a href="{OUTLINE_URL}/doc/uc-overview-{hub["slug"]}" class="link-outline" target="_blank">&#128218; UCs</a>
                <button class="btn-start" id="btn-{hub["slug"]}"
                        onclick="toggleHub('{hub["slug"]}')"
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
        .review-badge {{
            display: flex; gap: 0.5rem; align-items: center;
            margin-top: 0.25rem;
        }}
        .score-pill {{
            display: inline-flex; align-items: center;
            padding: 0.15em 0.6em; border-radius: 12px;
            font-size: 0.75rem; font-weight: 700;
            background: rgba(148,163,184,0.15); color: var(--muted);
            transition: all 0.3s;
        }}
        .score-pill.good {{ background: rgba(34,197,94,0.15); color: var(--green); }}
        .score-pill.warn {{ background: rgba(245,158,11,0.15); color: var(--amber); }}
        .score-pill.bad {{ background: rgba(239,68,68,0.15); color: var(--red); }}
        .finding-count {{
            font-size: 0.72rem; color: var(--muted);
        }}
        .link-grafana {{ color: var(--purple); background: rgba(168,85,247,0.1); }}
        .link-grafana:hover {{ background: rgba(168,85,247,0.2); }}
        .link-outline {{ color: var(--cyan); background: rgba(6,182,212,0.1); }}
        .link-outline:hover {{ background: rgba(6,182,212,0.2); }}
        .quality-summary {{
            margin-top: 2.5rem; padding: 2rem;
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 12px;
        }}
        .quality-summary h2 {{
            font-size: 1.3rem; font-weight: 700; margin-bottom: 1rem;
            background: linear-gradient(135deg, var(--purple), var(--cyan));
            background-clip: text; -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .quality-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 1rem;
        }}
        .quality-card {{
            background: rgba(15,23,42,0.5); border: 1px solid var(--border);
            border-radius: 8px; padding: 1rem; text-align: center;
        }}
        .quality-card .q-value {{
            font-size: 2rem; font-weight: 800;
        }}
        .quality-card .q-label {{
            font-size: 0.75rem; color: var(--muted);
            text-transform: uppercase; letter-spacing: 0.05em;
        }}
        .uc-bar {{
            display: flex; height: 8px; border-radius: 4px;
            overflow: hidden; margin-top: 0.5rem;
        }}
        .uc-bar .draft {{ background: var(--amber); }}
        .uc-bar .implemented {{ background: var(--accent); }}
        .uc-bar .tested {{ background: var(--green); }}
        .uc-bar .verified {{ background: var(--cyan); }}
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
    <div class="quality-summary" id="quality-summary">
        <h2>&#128202; Quality Controlling</h2>
        <div class="quality-grid">
            <div class="quality-card">
                <div class="q-value" id="q-avg-score" style="color:var(--muted)">&mdash;</div>
                <div class="q-label">Avg Score</div>
            </div>
            <div class="quality-card">
                <div class="q-value" id="q-total-findings" style="color:var(--muted)">&mdash;</div>
                <div class="q-label">Findings</div>
            </div>
            <div class="quality-card">
                <div class="q-value" id="q-total-block" style="color:var(--red)">&mdash;</div>
                <div class="q-label">Blockers</div>
            </div>
            <div class="quality-card">
                <div class="q-value" id="q-total-uc" style="color:var(--cyan)">&mdash;</div>
                <div class="q-label">Use Cases</div>
            </div>
            <div class="quality-card" style="grid-column: span 2;">
                <div class="q-label" style="margin-bottom:0.5rem">UC Status Gesamt</div>
                <div class="uc-bar" id="q-uc-bar"></div>
                <div style="display:flex;gap:1rem;justify-content:center;margin-top:0.5rem;font-size:0.72rem;color:var(--muted)" id="q-uc-legend"></div>
            </div>
        </div>
        <div style="margin-top:1rem;display:flex;gap:0.75rem;justify-content:center">
            <a href="{GRAFANA_URL}/d/reflex-review" class="link-grafana" style="font-size:0.85rem;padding:0.5em 1.2em;border-radius:8px" target="_blank">&#128202; Grafana Dashboard</a>
            <a href="{OUTLINE_URL}/collection/reflex" class="link-outline" style="font-size:0.85rem;padding:0.5em 1.2em;border-radius:8px" target="_blank">&#128218; Outline Docs</a>
            <button onclick="refreshReviews()" class="filter-btn" style="font-size:0.85rem">&#8635; Refresh Reviews</button>
        </div>
    </div>
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
{_REVIEW_JS}
</body>
</html>"""
