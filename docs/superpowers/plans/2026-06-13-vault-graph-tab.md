# Vault Graph Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/graph` page to ikeOS (obsidian-capture) that renders an interactive D3.js force-directed graph of all vault entries and a health sidebar surfacing untriaged, stale, and broken-link entries.

**Architecture:** A new `get_vault_graph()` function in `vault.py` scans all entries (via the existing cache), extracts nodes, wikilink edges (`[[slug]]` references), and three health categories. A Flask route renders the page; `/api/graph` returns JSON. The browser loads D3.js v7 (vendored in `static/vendor/`) and a `graph.js` file that drives the force simulation, tooltips, drag, zoom, and type-filter checkboxes. A health sidebar is rendered from the same JSON response.

**Tech Stack:** Python/Flask, D3.js v7 (vendored), vanilla JS, CSS Grid

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/services/vault.py` | Modify | Add `_get_urgency()` helper and `get_vault_graph()` function |
| `app/routes/browse.py` | Modify | Add `GET /graph` and `GET /api/graph` routes |
| `app/templates/graph.html` | Create | Graph page (canvas + health sidebar layout) |
| `app/static/graph.js` | Create | D3.js force graph, tooltip, drag, zoom, filter logic |
| `app/static/vendor/d3.v7.min.js` | Create | Vendored D3 v7 (downloaded during Task 3) |
| `app/static/style.css` | Modify | Graph page and health panel CSS |
| `app/templates/base.html` | Modify | Add Graph nav link |
| `tests/test_vault.py` | Modify | Tests for `get_vault_graph()` |
| `tests/test_browse.py` | Modify | Tests for `/graph` and `/api/graph` |

---

## Task 1: `get_vault_graph()` service function

**Files:**
- Modify: `app/services/vault.py`
- Modify: `tests/test_vault.py`

### Context

`vault.py` already imports `re`, `datetime`, and has `read_entries()` (uses cache). Add two new functions after `write_project_meta()` (around line 97).

- [ ] **Step 1: Write five failing tests**

Append to `tests/test_vault.py`:

```python
# ── get_vault_graph ──────────────────────────────────────────────────────────

def _make_entry(path, slug, type_, status, project, body="", urgency=None):
    """Helper: write a minimal vault entry file."""
    tags = [type_, project, f"status/{status}"]
    if urgency:
        tags.append(f"urgency/{urgency}")
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{slug}.md").write_text(
        f"---\ntype: {type_}\ntitle: {slug}\nproject: {project}\n"
        f"status: {status}\ncreated: 2026-01-01T10:00:00\n"
        f"updated: 2026-01-01T10:00:00\ntags: {tags}\n---\n"
        f"## Description\n{body}\n"
    )


def test_get_vault_graph_returns_structure(tmp_path):
    bugs = tmp_path / "projects" / "proj-a" / "bugs"
    _make_entry(bugs, "2026-01-01-bug-one", "bug", "open", "proj-a")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    assert set(result.keys()) == {"nodes", "links", "health"}
    assert set(result["health"].keys()) == {"untriaged", "stale", "broken_links"}
    assert len(result["nodes"]) == 1
    node = result["nodes"][0]
    assert node["id"] == "2026-01-01-bug-one"
    assert node["type"] == "bug"
    assert node["project"] == "proj-a"


def test_get_vault_graph_detects_wikilinks(tmp_path):
    bugs = tmp_path / "projects" / "proj-a" / "bugs"
    notes = tmp_path / "projects" / "proj-a" / "notes"
    _make_entry(bugs, "2026-01-01-bug-a", "bug", "open", "proj-a",
                body="See [[2026-01-01-note-b]]")
    _make_entry(notes, "2026-01-01-note-b", "note", "open", "proj-a")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    assert len(result["links"]) == 1
    assert result["links"][0]["source"] == "2026-01-01-bug-a"
    assert result["links"][0]["target"] == "2026-01-01-note-b"


def test_get_vault_graph_detects_broken_links(tmp_path):
    notes = tmp_path / "projects" / "proj-a" / "notes"
    _make_entry(notes, "2026-01-01-note-x", "note", "open", "proj-a",
                body="See [[nonexistent-slug]]")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    broken = result["health"]["broken_links"]
    assert len(broken) == 1
    assert broken[0]["broken_ref"] == "nonexistent-slug"
    assert broken[0]["source_slug"] == "2026-01-01-note-x"
    assert len(result["links"]) == 0


def test_get_vault_graph_detects_untriaged(tmp_path):
    notes = tmp_path / "projects" / "proj-a" / "notes"
    _make_entry(notes, "2026-01-01-untriaged", "note", "new", "proj-a")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    untriaged = result["health"]["untriaged"]
    assert len(untriaged) == 1
    assert untriaged[0]["slug"] == "2026-01-01-untriaged"


def test_get_vault_graph_detects_stale(tmp_path):
    notes = tmp_path / "projects" / "proj-a" / "notes"
    (notes).mkdir(parents=True, exist_ok=True)
    # updated 500 days ago — definitely stale
    (notes / "2026-01-01-old.md").write_text(
        "---\ntype: note\ntitle: Old Note\nproject: proj-a\n"
        "status: open\ncreated: 2024-08-15T10:00:00\n"
        "updated: 2024-08-15T10:00:00\ntags: [documentation]\n---\n"
        "## Description\nContent\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    stale = result["health"]["stale"]
    assert len(stale) == 1
    assert stale[0]["days_stale"] >= 30
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/test_vault.py::test_get_vault_graph_returns_structure tests/test_vault.py::test_get_vault_graph_detects_wikilinks tests/test_vault.py::test_get_vault_graph_detects_broken_links tests/test_vault.py::test_get_vault_graph_detects_untriaged tests/test_vault.py::test_get_vault_graph_detects_stale -v
```

Expected: 5 failures with `ImportError: cannot import name 'get_vault_graph'` or similar.

- [ ] **Step 3: Implement `_get_urgency()` and `get_vault_graph()` in `vault.py`**

Insert after `write_project_meta()` (after line 97), before the `_slugify()` function:

```python
def _get_urgency(entry: dict) -> str:
    """Extract urgency level from tags, falling back to severity/priority fields."""
    for tag in entry.get("tags", []):
        if tag.startswith("urgency/"):
            return tag.split("/", 1)[1]
    sev = entry.get("severity") or entry.get("priority")
    if sev in ("critical", "high", "medium", "low"):
        return sev
    return "medium"


def get_vault_graph() -> dict:
    """Build graph nodes, link edges (wikilinks), and health data from all vault entries."""
    entries = read_entries()  # uses global cache

    wikilink_re = re.compile(r'\[\[([^\]|]+)')
    known_slugs = {e["slug"] for e in entries}
    now = datetime.now()
    stale_days = 30

    nodes = [
        {
            "id": e["slug"],
            "title": e.get("title", e["slug"]),
            "type": e.get("type", "note"),
            "status": e.get("status", "new"),
            "project": e.get("project", ""),
            "urgency": _get_urgency(e),
        }
        for e in entries
    ]

    links: list[dict] = []
    broken_links: list[dict] = []
    untriaged: list[dict] = []
    stale: list[dict] = []

    for e in entries:
        # Wikilinks → graph edges
        for ref in wikilink_re.findall(e.get("body", "")):
            ref = ref.strip()
            if not ref:
                continue
            if ref in known_slugs and ref != e["slug"]:
                links.append({"source": e["slug"], "target": ref})
            else:
                broken_links.append({
                    "source_slug": e["slug"],
                    "source_title": e.get("title", e["slug"]),
                    "source_project": e.get("project", ""),
                    "broken_ref": ref,
                })

        # Health checks
        status = e.get("status", "")
        if status == "new":
            untriaged.append({
                "slug": e["slug"],
                "title": e.get("title", e["slug"]),
                "project": e.get("project", ""),
                "type": e.get("type", ""),
            })
        elif status in ("open", "in-progress"):
            updated_str = e.get("updated") or e.get("created", "")
            try:
                updated = datetime.fromisoformat(updated_str)
                days = (now - updated).days
                if days >= stale_days:
                    stale.append({
                        "slug": e["slug"],
                        "title": e.get("title", e["slug"]),
                        "project": e.get("project", ""),
                        "type": e.get("type", ""),
                        "status": status,
                        "days_stale": days,
                    })
            except (ValueError, TypeError):
                pass

    return {
        "nodes": nodes,
        "links": links,
        "health": {
            "untriaged": untriaged,
            "stale": stale,
            "broken_links": broken_links,
        },
    }
```

- [ ] **Step 4: Run tests — expect all 5 to pass**

```bash
python -m pytest tests/test_vault.py::test_get_vault_graph_returns_structure tests/test_vault.py::test_get_vault_graph_detects_wikilinks tests/test_vault.py::test_get_vault_graph_detects_broken_links tests/test_vault.py::test_get_vault_graph_detects_untriaged tests/test_vault.py::test_get_vault_graph_detects_stale -v
```

Expected: 5 PASSED

- [ ] **Step 5: Run full suite — expect no regressions**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: same pass/fail ratio as before this task (2 pre-existing failures in `test_agents.py` are acceptable).

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Server/projects/obsidian-capture
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: add get_vault_graph() — nodes, wikilink edges, health metrics"
```

---

## Task 2: Graph routes

**Files:**
- Modify: `app/routes/browse.py`
- Modify: `tests/test_browse.py`

### Context

`browse.py` currently imports from `vault.py` and registers routes on `bp = Blueprint("browse", __name__)`. Add two routes at the bottom. The `/api/graph` route returns JSON; the `/graph` route renders a template.

- [ ] **Step 1: Write two failing tests**

Append to `tests/test_browse.py`:

```python
# ── Graph routes ──────────────────────────────────────────────────────────────

@pytest.fixture
def graph_vault(tmp_path):
    notes_dir = tmp_path / "projects" / "proj-a" / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "2026-01-01-test-note.md").write_text(
        "---\ntype: note\ntitle: Test Note\nproject: proj-a\n"
        "status: open\ncreated: 2026-01-01T10:00:00\n"
        "updated: 2026-01-01T10:00:00\ntags: [documentation]\n---\n"
        "## Description\nContent\n"
    )
    return tmp_path


@pytest.fixture
def graph_client(graph_vault):
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", graph_vault):
        with app.test_client() as client:
            yield client


def test_graph_page_renders(graph_client):
    response = graph_client.get("/graph")
    assert response.status_code == 200


def test_api_graph_returns_json(graph_client):
    from app.services.vault import _invalidate_cache
    with patch("app.services.vault.VAULT_PATH", graph_client.application.extensions.get("vault_path",
               __import__("pathlib").Path("/vault"))):
        pass  # vault path is already patched by the fixture context
    response = graph_client.get("/api/graph")
    assert response.status_code == 200
    data = response.get_json()
    assert "nodes" in data
    assert "links" in data
    assert "health" in data
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "2026-01-01-test-note"
    assert data["nodes"][0]["project"] == "proj-a"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/test_browse.py::test_graph_page_renders tests/test_browse.py::test_api_graph_returns_json -v
```

Expected: both FAIL (404 or template not found).

- [ ] **Step 3: Add routes to `browse.py`**

Add this import at the top of `browse.py` (with the existing Flask imports):

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
```

Add these two routes at the bottom of `browse.py`:

```python
@bp.route("/graph")
def graph():
    return render_template("graph.html")


@bp.route("/api/graph")
def api_graph():
    from app.services.vault import get_vault_graph
    return jsonify(get_vault_graph())
```

- [ ] **Step 4: Create a minimal `graph.html` stub so the page renders**

Create `app/templates/graph.html`:

```html
{% extends "base.html" %}
{% block title %}Graph{% endblock %}
{% block content %}
<p>Graph coming soon.</p>
{% endblock %}
```

- [ ] **Step 5: Run tests — expect both to pass**

```bash
python -m pytest tests/test_browse.py::test_graph_page_renders tests/test_browse.py::test_api_graph_returns_json -v
```

Expected: 2 PASSED. If `test_api_graph_returns_json` fails because vault cache leaks between tests, add `_invalidate_cache()` at the top of the `graph_client` fixture:

```python
@pytest.fixture
def graph_client(graph_vault):
    from app.services.vault import _invalidate_cache
    _invalidate_cache()
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", graph_vault):
        with app.test_client() as client:
            yield client
```

- [ ] **Step 6: Run full suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add app/routes/browse.py app/templates/graph.html tests/test_browse.py
git commit -m "feat: add /graph and /api/graph routes"
```

---

## Task 3: Graph page UI

**Files:**
- Create: `app/static/vendor/d3.v7.min.js`
- Modify: `app/templates/graph.html` (replace stub)
- Create: `app/static/graph.js`
- Modify: `app/static/style.css`
- Modify: `app/templates/base.html`

### Context

This task builds the interactive graph UI. D3.js v7 is vendored (downloaded to `static/vendor/`). The page uses a two-column CSS Grid: graph canvas on the left, health sidebar on the right. `graph.js` fetches `/api/graph`, runs a force simulation, and populates the health sidebar.

- [ ] **Step 1: Download D3 v7 to vendor/**

```bash
curl -L -o /mnt/c/Server/projects/obsidian-capture/app/static/vendor/d3.v7.min.js \
  https://d3js.org/d3.v7.min.js
```

Verify the file exists and is non-empty:

```bash
ls -lh /mnt/c/Server/projects/obsidian-capture/app/static/vendor/d3.v7.min.js
```

Expected: file ~262KB.

- [ ] **Step 2: Replace `graph.html` with the full template**

Overwrite `app/templates/graph.html`:

```html
{% extends "base.html" %}
{% block title %}Graph{% endblock %}
{% block content %}
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">

<div class="graph-page">
  <header class="page-header">
    <span class="ike-eyebrow">Vault</span>
    <h1>Graph</h1>
    <p class="page-subtitle">{{ "{" }}{{ "{" }} node_count {{ "}}" }}{{ "}}" }} entries across {{ "{" }}{{ "{" }} project_count {{ "}}" }}{{ "}}" }} projects — connections show wikilinks.</p>
  </header>

  <div class="graph-layout">

    <!-- ── Canvas ── -->
    <div class="graph-canvas-wrap">
      <div class="graph-controls">
        <label class="graph-filter-label">
          <input type="checkbox" id="filter-bugs" checked>
          <span class="graph-dot graph-dot-bug"></span>Bugs
        </label>
        <label class="graph-filter-label">
          <input type="checkbox" id="filter-ideas" checked>
          <span class="graph-dot graph-dot-idea"></span>Ideas
        </label>
        <label class="graph-filter-label">
          <input type="checkbox" id="filter-notes" checked>
          <span class="graph-dot graph-dot-note"></span>Notes
        </label>
        <span class="graph-hint">Drag to move · Scroll to zoom · Click to open</span>
      </div>
      <svg id="graph-svg"></svg>
      <div id="graph-tooltip" class="graph-tooltip"></div>
      <div class="graph-loading" id="graph-loading">
        <div class="ike-loading-orbit" aria-hidden="true"></div>
        <span>Mapping the vault…</span>
      </div>
    </div>

    <!-- ── Health sidebar ── -->
    <aside class="graph-health">

      <div class="health-section">
        <div class="health-heading">
          <span class="health-badge" id="badge-untriaged">—</span>
          Untriaged
        </div>
        <ul class="health-list" id="list-untriaged">
          <li class="health-empty">Loading…</li>
        </ul>
      </div>

      <div class="health-section">
        <div class="health-heading">
          <span class="health-badge" id="badge-stale">—</span>
          Stale (&gt;30 days)
        </div>
        <ul class="health-list" id="list-stale">
          <li class="health-empty">Loading…</li>
        </ul>
      </div>

      <div class="health-section">
        <div class="health-heading">
          <span class="health-badge" id="badge-broken">—</span>
          Broken Links
        </div>
        <ul class="health-list" id="list-broken">
          <li class="health-empty">Loading…</li>
        </ul>
      </div>

    </aside>
  </div>
</div>

<script src="{{ url_for('static', filename='vendor/d3.v7.min.js') }}"></script>
<script src="{{ url_for('static', filename='graph.js') }}"></script>
{% endblock %}
```

**Note:** The `{{ "{" }}{{ "{" }} node_count {{ "}}" }}{{ "}}" }}` placeholders above are illustrative — the actual template should use literal Jinja variables `{{ node_count }}` and `{{ project_count }}` passed from the route. Update `browse.py`'s `graph()` route to pass these:

```python
@bp.route("/graph")
def graph():
    from app.services.vault import get_vault_graph
    data = get_vault_graph()
    return render_template(
        "graph.html",
        node_count=len(data["nodes"]),
        project_count=len({n["project"] for n in data["nodes"]}),
    )
```

The **actual** `graph.html` template content (copy this verbatim — no `{{ "{" }}` escaping needed, just write normal Jinja syntax):

```html
{% extends "base.html" %}
{% block title %}Graph{% endblock %}
{% block content %}

<div class="graph-page">
  <header class="page-header">
    <span class="ike-eyebrow">Vault</span>
    <h1>Graph</h1>
    <p class="page-subtitle">{{ node_count }} entries across {{ project_count }} projects — connections show wikilinks.</p>
  </header>

  <div class="graph-layout">

    <!-- ── Canvas ── -->
    <div class="graph-canvas-wrap">
      <div class="graph-controls">
        <label class="graph-filter-label">
          <input type="checkbox" id="filter-bugs" checked>
          <span class="graph-dot graph-dot-bug"></span>Bugs
        </label>
        <label class="graph-filter-label">
          <input type="checkbox" id="filter-ideas" checked>
          <span class="graph-dot graph-dot-idea"></span>Ideas
        </label>
        <label class="graph-filter-label">
          <input type="checkbox" id="filter-notes" checked>
          <span class="graph-dot graph-dot-note"></span>Notes
        </label>
        <span class="graph-hint">Drag · Scroll to zoom · Click to open</span>
      </div>
      <svg id="graph-svg"></svg>
      <div id="graph-tooltip" class="graph-tooltip"></div>
      <div class="graph-loading" id="graph-loading">
        <div class="ike-loading-orbit" aria-hidden="true"></div>
        <span>Mapping the vault…</span>
      </div>
    </div>

    <!-- ── Health sidebar ── -->
    <aside class="graph-health">

      <div class="health-section">
        <div class="health-heading">
          <span class="health-badge" id="badge-untriaged">—</span>
          Untriaged
        </div>
        <ul class="health-list" id="list-untriaged">
          <li class="health-empty">Loading…</li>
        </ul>
      </div>

      <div class="health-section">
        <div class="health-heading">
          <span class="health-badge" id="badge-stale">—</span>
          Stale (&gt;30 days)
        </div>
        <ul class="health-list" id="list-stale">
          <li class="health-empty">Loading…</li>
        </ul>
      </div>

      <div class="health-section">
        <div class="health-heading">
          <span class="health-badge" id="badge-broken">—</span>
          Broken Links
        </div>
        <ul class="health-list" id="list-broken">
          <li class="health-empty">Loading…</li>
        </ul>
      </div>

    </aside>
  </div>
</div>

<script src="{{ url_for('static', filename='vendor/d3.v7.min.js') }}"></script>
<script src="{{ url_for('static', filename='graph.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Create `app/static/graph.js`**

```javascript
(function () {
  'use strict';

  const TYPE_COLOR = { bug: '#ef4444', idea: '#a855f7', note: '#3b82f6' };
  const STATUS_OPACITY = { done: 0.25, deferred: 0.2 };
  const URGENCY_RADIUS = { critical: 12, high: 10, medium: 8, low: 6 };

  let allNodes = [];
  let allLinks = [];
  let simulation = null;

  function nodeRadius(d) { return URGENCY_RADIUS[d.urgency] || 7; }
  function nodeOpacity(d) { return STATUS_OPACITY[d.status] || 1; }
  function entryUrl(d) { return '/projects/' + d.project + '/' + d.id; }

  // ── Health sidebar ──────────────────────────────────────────────────────────

  function renderHealth(health) {
    var untriaged = health.untriaged;
    var stale = health.stale;
    var broken = health.broken_links;

    document.getElementById('badge-untriaged').textContent = untriaged.length;
    document.getElementById('badge-stale').textContent = stale.length;
    document.getElementById('badge-broken').textContent = broken.length;

    function entryItem(e, sub) {
      return '<li class="health-item"><a href="' + entryUrl(e) + '">' +
        escHtml(e.title) + '</a>' +
        (sub ? '<span class="health-sub">' + escHtml(sub) + '</span>' : '') +
        '</li>';
    }

    document.getElementById('list-untriaged').innerHTML =
      untriaged.length
        ? untriaged.slice(0, 25).map(function (e) { return entryItem(e, e.project); }).join('')
        : '<li class="health-empty">All clear</li>';

    document.getElementById('list-stale').innerHTML =
      stale.length
        ? stale.slice(0, 25).map(function (e) {
            return entryItem(e, e.days_stale + 'd stale · ' + e.project);
          }).join('')
        : '<li class="health-empty">All clear</li>';

    document.getElementById('list-broken').innerHTML =
      broken.length
        ? broken.slice(0, 25).map(function (b) {
            return '<li class="health-item health-item-broken">[[' + escHtml(b.broken_ref) + ']]' +
              '<span class="health-sub">in ' + escHtml(b.source_project) + '</span></li>';
          }).join('')
        : '<li class="health-empty">All clear</li>';
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Force graph ─────────────────────────────────────────────────────────────

  function filteredData() {
    var showBugs   = document.getElementById('filter-bugs').checked;
    var showIdeas  = document.getElementById('filter-ideas').checked;
    var showNotes  = document.getElementById('filter-notes').checked;

    var visibleIds = new Set(
      allNodes
        .filter(function (n) {
          return (n.type === 'bug'  && showBugs)  ||
                 (n.type === 'idea' && showIdeas) ||
                 (n.type === 'note' && showNotes);
        })
        .map(function (n) { return n.id; })
    );

    return {
      nodes: allNodes.filter(function (n) { return visibleIds.has(n.id); }),
      links: allLinks.filter(function (l) {
        var src = l.source.id !== undefined ? l.source.id : l.source;
        var tgt = l.target.id !== undefined ? l.target.id : l.target;
        return visibleIds.has(src) && visibleIds.has(tgt);
      }),
    };
  }

  function renderGraph() {
    var wrap = document.querySelector('.graph-canvas-wrap');
    var W = wrap.clientWidth;
    var H = Math.max(520, window.innerHeight - 220);

    var svg = d3.select('#graph-svg').attr('width', W).attr('height', H);
    svg.selectAll('*').remove();

    if (simulation) { simulation.stop(); simulation = null; }

    var fd = filteredData();
    if (fd.nodes.length === 0) return;

    // Clone so D3 can mutate x/y without touching allNodes
    var nodeData = fd.nodes.map(function (n) { return Object.assign({}, n); });
    var byId = new Map(nodeData.map(function (n) { return [n.id, n]; }));
    var linkData = fd.links
      .map(function (l) {
        var src = l.source.id !== undefined ? l.source.id : l.source;
        var tgt = l.target.id !== undefined ? l.target.id : l.target;
        return { source: byId.get(src), target: byId.get(tgt) };
      })
      .filter(function (l) { return l.source && l.target; });

    // Project cluster centres (grid layout)
    var projects = Array.from(new Set(nodeData.map(function (n) { return n.project; })));
    var cols = Math.ceil(Math.sqrt(projects.length));
    var rows = Math.ceil(projects.length / cols);
    var clusterX = {}, clusterY = {};
    projects.forEach(function (p, i) {
      var col = i % cols;
      var row = Math.floor(i / cols);
      clusterX[p] = W * (0.1 + 0.8 * ((col + 0.5) / cols));
      clusterY[p] = H * (0.1 + 0.8 * ((row + 0.5) / rows));
    });

    simulation = d3.forceSimulation(nodeData)
      .force('link', d3.forceLink(linkData).id(function (d) { return d.id; }).distance(70))
      .force('charge', d3.forceManyBody().strength(-90))
      .force('collide', d3.forceCollide().radius(function (d) { return nodeRadius(d) + 4; }))
      .force('x', d3.forceX(function (d) { return clusterX[d.project] || W / 2; }).strength(0.07))
      .force('y', d3.forceY(function (d) { return clusterY[d.project] || H / 2; }).strength(0.07));

    var g = svg.append('g');

    // Pan + zoom
    svg.call(
      d3.zoom()
        .scaleExtent([0.15, 5])
        .on('zoom', function (event) { g.attr('transform', event.transform); })
    );

    // Edges
    var link = g.append('g')
      .selectAll('line')
      .data(linkData)
      .join('line')
      .attr('stroke', '#2a2a2a')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.7);

    // Tooltip
    var tooltip = document.getElementById('graph-tooltip');

    // Nodes
    var node = g.append('g')
      .selectAll('circle')
      .data(nodeData)
      .join('circle')
      .attr('r', nodeRadius)
      .attr('fill', function (d) { return TYPE_COLOR[d.type] || '#888'; })
      .attr('fill-opacity', nodeOpacity)
      .attr('stroke', '#111')
      .attr('stroke-width', 1)
      .style('cursor', 'pointer')
      .on('mouseover', function (event, d) {
        tooltip.style.display = 'block';
        tooltip.innerHTML =
          '<strong>' + escHtml(d.title) + '</strong><br>' +
          escHtml(d.project) + ' · ' + d.type + ' · ' + d.status;
      })
      .on('mousemove', function (event) {
        var rect = wrap.getBoundingClientRect();
        tooltip.style.left = (event.clientX - rect.left + 14) + 'px';
        tooltip.style.top  = (event.clientY - rect.top  + 14) + 'px';
      })
      .on('mouseout', function () { tooltip.style.display = 'none'; })
      .on('click', function (event, d) { window.location.href = entryUrl(d); })
      .call(
        d3.drag()
          .on('start', function (event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on('drag', function (event, d) { d.fx = event.x; d.fy = event.y; })
          .on('end', function (event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
      );

    simulation.on('tick', function () {
      link
        .attr('x1', function (d) { return d.source.x; })
        .attr('y1', function (d) { return d.source.y; })
        .attr('x2', function (d) { return d.target.x; })
        .attr('y2', function (d) { return d.target.y; });
      node
        .attr('cx', function (d) { return d.x; })
        .attr('cy', function (d) { return d.y; });
    });
  }

  // ── Init ────────────────────────────────────────────────────────────────────

  async function init() {
    var loadingEl = document.getElementById('graph-loading');
    try {
      var res = await fetch('/api/graph');
      var data = await res.json();
      allNodes = data.nodes;
      allLinks = data.links;

      if (loadingEl) loadingEl.style.display = 'none';

      renderHealth(data.health);
      renderGraph();

      ['filter-bugs', 'filter-ideas', 'filter-notes'].forEach(function (id) {
        document.getElementById(id).addEventListener('change', renderGraph);
      });

      window.addEventListener('resize', renderGraph);
    } catch (err) {
      if (loadingEl) loadingEl.textContent = 'Failed to load graph data.';
      console.error(err);
    }
  }

  init();
})();
```

- [ ] **Step 4: Add graph CSS to `app/static/style.css`**

Append to the end of `app/static/style.css`:

```css
/* ── Graph page ────────────────────────────────────────────────────────────── */
.graph-page { padding: 1.5rem; }

.graph-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 1rem;
  align-items: start;
  margin-top: 1rem;
}

.graph-canvas-wrap {
  position: relative;
  background: #090909;
  border: 1px solid var(--border-subtle, #222);
  border-radius: 8px;
  overflow: hidden;
  min-height: 520px;
}

#graph-svg { display: block; width: 100%; }

.graph-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid var(--border-subtle, #1e1e1e);
  background: #0e0e0e;
  flex-wrap: wrap;
}

.graph-filter-label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
  color: #aaa;
  cursor: pointer;
  user-select: none;
}

.graph-filter-label input[type="checkbox"] { accent-color: #555; }

.graph-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.graph-dot-bug  { background: #ef4444; }
.graph-dot-idea { background: #a855f7; }
.graph-dot-note { background: #3b82f6; }

.graph-hint { margin-left: auto; font-size: 0.7rem; color: #555; }

.graph-tooltip {
  position: absolute;
  display: none;
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.45rem 0.65rem;
  font-size: 0.76rem;
  color: #ddd;
  pointer-events: none;
  max-width: 240px;
  line-height: 1.4;
  z-index: 20;
}

.graph-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  font-size: 0.82rem;
  color: #666;
}

/* ── Health sidebar ─────────────────────────────────────────────────────────── */
.graph-health { display: flex; flex-direction: column; gap: 0.75rem; }

.health-section {
  border: 1px solid var(--border-subtle, #222);
  border-radius: 8px;
  overflow: hidden;
}

.health-heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.75rem;
  background: #0e0e0e;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #777;
  border-bottom: 1px solid var(--border-subtle, #1e1e1e);
}

.health-badge {
  background: #222;
  color: #bbb;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  min-width: 22px;
  text-align: center;
}

.health-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
}

.health-item {
  display: flex;
  flex-direction: column;
  padding: 0.35rem 0.75rem;
  border-bottom: 1px solid #161616;
  font-size: 0.76rem;
}

.health-item:last-child { border-bottom: none; }

.health-item a { color: #ccc; text-decoration: none; }
.health-item a:hover { color: #fff; }

.health-item-broken { color: #777; font-family: monospace; font-size: 0.7rem; }

.health-sub { color: #555; font-size: 0.68rem; margin-top: 1px; }

.health-empty { padding: 0.5rem 0.75rem; color: #444; font-size: 0.76rem; }
```

- [ ] **Step 5: Add Graph nav link to `base.html`**

In `app/templates/base.html`, after the Settings link, add:

```html
      <a href="{{ url_for('browse.graph') }}" class="nav-link {% if request.endpoint == 'browse.graph' %}is-active{% endif %}">Graph</a>
```

The full nav-links section should look like:

```html
    <div class="nav-links" id="nav-links-menu">
      <a href="{{ url_for('agents.dashboard') }}" class="nav-link {% if request.endpoint == 'agents.dashboard' %}is-active{% endif %}">Dashboard</a>
      <a href="{{ url_for('browse.tasks') }}"     class="nav-link {% if request.endpoint == 'browse.tasks' %}is-active{% endif %}">Tasks</a>
      <a href="{{ url_for('agents.agents') }}"    class="nav-link {% if request.endpoint == 'agents.agents' %}is-active{% endif %}">Sessions</a>
      <a href="{{ url_for('capture.capture_form') }}" class="nav-link {% if request.endpoint == 'capture.capture_form' %}is-active{% endif %}">Capture</a>
      <a href="{{ url_for('agents.status_page') }}" class="nav-link {% if request.endpoint == 'agents.status_page' %}is-active{% endif %}">Status</a>
      <a href="{{ url_for('browse.settings') }}" class="nav-link {% if request.endpoint == 'browse.settings' or request.endpoint == 'browse.update_project_settings' %}is-active{% endif %}">Settings</a>
      <a href="{{ url_for('browse.graph') }}" class="nav-link {% if request.endpoint == 'browse.graph' %}is-active{% endif %}">Graph</a>
      {% if config_version %}<span class="nav-version">{{ config_version }}</span>{% endif %}
    </div>
```

- [ ] **Step 6: Run full test suite**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/ -v --tb=short 2>&1 | tail -25
```

Expected: no new failures vs. before Task 3.

- [ ] **Step 7: Rebuild Docker and verify**

```bash
cd /mnt/c/Server/projects/obsidian-capture
docker.exe compose up --build -d
```

Wait ~10 seconds, then verify the Graph page loads:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5009/graph
```

Expected: `200`

```bash
curl -s http://localhost:5009/api/graph | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'nodes={len(d[\"nodes\"])}, links={len(d[\"links\"])}, health keys={list(d[\"health\"].keys())}')"
```

Expected: `nodes=N, links=M, health keys=['untriaged', 'stale', 'broken_links']` (N > 0)

- [ ] **Step 8: Commit**

```bash
git add app/static/vendor/d3.v7.min.js app/templates/graph.html app/static/graph.js \
        app/static/style.css app/templates/base.html app/routes/browse.py
git commit -m "feat: vault graph page — force-directed D3 graph + health sidebar"
```
