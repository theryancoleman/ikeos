# Three-Column Home Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the obsidian-capture home page at `/` with a three-column workspace (Sessions | Session Detail | Capture), keeping `/agents`, `/capture`, and a new `/tasks` (current dashboard) as standalone pages.

**Architecture:** Single `workspace.html` template rendered by both `/` (three_col=True) and `/agents` (three_col=False), driven by extracted `agents.js`. Routes: `browse.py` owns `/tasks`, `agents.py` owns `/` and `/agents`. A new `POST /capture/json` endpoint enables AJAX capture from the inline form.

**Tech Stack:** Flask/Jinja2, vanilla JS, CSS Grid, `history.replaceState` for URL state.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/routes/browse.py` | Modify | `/` → temp redirect; `/tasks` owns dashboard view |
| `app/routes/agents.py` | Modify | `/` → 3-col home; `/agents` → 2-col sessions |
| `app/routes/capture.py` | Modify | Add `POST /capture/json` JSON endpoint |
| `app/templates/base.html` | Modify | Nav: Home / Tasks / Sessions / Capture |
| `app/templates/workspace.html` | Create | Three-column workspace (replaces agents.html) |
| `app/templates/agents.html` | Delete | Replaced by workspace.html |
| `app/static/workspace.css` | Create | Grid layout + all workspace component styles |
| `app/static/agents.js` | Create | Session management JS, URL state, capture sync |
| `app/static/agents.css` | Delete | Replaced by workspace.css |
| `tests/test_browse.py` | Modify | Update `/` tests → `/tasks`; add `/tasks` test |
| `tests/test_agents.py` | Modify | Add `/` home tests; update for workspace.html |
| `tests/test_capture.py` | Modify | Add `/capture/json` tests |

---

## Task 1: Move dashboard to /tasks

**Files:**
- Modify: `app/routes/browse.py`
- Modify: `app/routes/capture.py`
- Modify: `app/templates/base.html`
- Modify: `tests/test_browse.py`

- [ ] **Step 1: Write failing test for /tasks**

Add to `tests/test_browse.py`:

```python
def test_tasks_page_renders(client):
    response = client.get("/tasks")
    assert response.status_code == 200

def test_tasks_page_shows_entry_title(client):
    response = client.get("/tasks")
    assert b"Test note" in response.data
```

Run: `docker exec obsidian-capture python -m pytest tests/test_browse.py::test_tasks_page_renders -v`
Expected: FAIL with `404`

- [ ] **Step 2: Rename dashboard route to /tasks in browse.py**

In `app/routes/browse.py`, change the route decorator and function name:

```python
@bp.route("/tasks")
def tasks():
    projects = get_projects_with_meta()
    all_entries = read_entries()

    project_stats = {}
    for p in projects:
        slug = p["slug"]
        p_entries = [e for e in all_entries if e.get("project") == slug]
        active = [e for e in p_entries if e.get("status") in ACTIVE_STATUSES]
        project_stats[slug] = {
            "bugs": len([e for e in active if e.get("type") == "bug"]),
            "ideas": len([e for e in active if e.get("type") == "idea"]),
            "notes": len([e for e in active if e.get("type") == "note"]),
            "new": len([e for e in p_entries if e.get("status") == "new"]),
        }

    in_flight = [e for e in all_entries if e.get("status") == "in-progress"]
    needs_triage = [e for e in all_entries if e.get("status") == "new"]

    return render_template(
        "dashboard.html",
        projects=projects,
        project_stats=project_stats,
        in_flight=in_flight,
        needs_triage=needs_triage,
    )
```

Add a temporary `/` redirect below it (agents.py will replace this in Task 5):

```python
@bp.route("/")
def home_redirect():
    return redirect(url_for("browse.tasks"))
```

Add `redirect` to the imports at the top of `browse.py`:

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
```

- [ ] **Step 3: Update url_for references from browse.dashboard → browse.tasks**

In `app/routes/capture.py`, find both occurrences of `url_for("browse.dashboard")` and change to `url_for("browse.tasks")`:

```python
# In capture_submit(), two places:
return redirect(url_for("browse.tasks"))
```

Run: `grep -n "browse.dashboard" app/routes/capture.py app/templates/base.html app/templates/dashboard.html app/templates/project.html app/templates/entry.html`

For any match found, replace `browse.dashboard` with `browse.tasks`.

In `app/templates/base.html`, the nav brand link:
```html
<a href="{{ url_for('browse.tasks') }}" class="nav-brand">Capture</a>
```

- [ ] **Step 4: Update existing dashboard tests**

In `tests/test_browse.py`, change the two existing tests that hit `/`:

```python
def test_dashboard_returns_200(client):
    response = client.get("/tasks")
    assert response.status_code == 200


def test_dashboard_shows_entry_title(client):
    response = client.get("/tasks")
    assert b"Test note" in response.data
```

- [ ] **Step 5: Run tests**

```bash
docker exec obsidian-capture python -m pytest tests/test_browse.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git -C /mnt/c/Server/projects/obsidian-capture add \
  app/routes/browse.py app/routes/capture.py \
  app/templates/base.html tests/test_browse.py
git -C /mnt/c/Server/projects/obsidian-capture \
  commit -m "feat: move dashboard to /tasks, add temp / redirect"
```

---

## Task 2: Add /capture/json endpoint

**Files:**
- Modify: `app/routes/capture.py`
- Modify: `tests/test_capture.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_capture.py`:

```python
def test_capture_json_note(client, mocker):
    mock_write = mocker.patch("app.routes.capture.write_entry")
    resp = client.post(
        "/capture/json",
        json={"type": "note", "project": "bcr-waivers", "title": "Test note"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    call_data = mock_write.call_args[0][0]
    assert call_data["type"] == "note"
    assert call_data["project"] == "bcr-waivers"
    assert call_data["title"] == "Test note"


def test_capture_json_missing_title_returns_400(client):
    resp = client.post(
        "/capture/json",
        json={"type": "note", "project": "bcr-waivers"},
    )
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_capture_json_missing_project_returns_400(client):
    resp = client.post(
        "/capture/json",
        json={"type": "note", "title": "Test"},
    )
    assert resp.status_code == 400


def test_capture_json_invalid_type_returns_400(client):
    resp = client.post(
        "/capture/json",
        json={"type": "decision", "project": "bcr-waivers", "title": "Test"},
    )
    assert resp.status_code == 400


def test_capture_json_idea_includes_priority_effort(client, mocker):
    mock_write = mocker.patch("app.routes.capture.write_entry")
    resp = client.post(
        "/capture/json",
        json={
            "type": "idea",
            "project": "bcr-waivers",
            "title": "Test idea",
            "priority": "high",
            "effort": "low",
        },
    )
    assert resp.status_code == 200
    call_data = mock_write.call_args[0][0]
    assert call_data["priority"] == "high"
    assert call_data["effort"] == "low"
```

Run: `docker exec obsidian-capture python -m pytest tests/test_capture.py::test_capture_json_note -v`
Expected: FAIL with `404`

- [ ] **Step 2: Add the endpoint to capture.py**

Append to `app/routes/capture.py` (before the final blank line):

```python
@bp.route("/capture/json", methods=["POST"])
def capture_json():
    req = request.get_json(silent=True) or {}
    entry_type = req.get("type", "")
    project = req.get("project", "")
    title = req.get("title", "")

    if not title:
        return jsonify({"error": "title is required"}), 400
    if entry_type not in ("note", "idea", "bug"):
        return jsonify({"error": "type must be note, idea, or bug"}), 400
    if not project:
        return jsonify({"error": "project is required"}), 400

    data = {
        "type": entry_type,
        "project": project,
        "title": title,
        "body": req.get("body", ""),
        "domains": [],
    }
    if entry_type == "idea":
        data["priority"] = req.get("priority", "medium")
        data["effort"] = req.get("effort", "medium")
    elif entry_type == "bug":
        data["severity"] = req.get("severity", "medium")
        data["steps"] = req.get("steps", "")

    write_entry(data)
    return jsonify({"ok": True}), 200
```

- [ ] **Step 3: Run tests**

```bash
docker exec obsidian-capture python -m pytest tests/test_capture.py -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git -C /mnt/c/Server/projects/obsidian-capture add \
  app/routes/capture.py tests/test_capture.py
git -C /mnt/c/Server/projects/obsidian-capture \
  commit -m "feat: add POST /capture/json for inline AJAX capture"
```

---

## Task 3: Create workspace.css

**Files:**
- Create: `app/static/workspace.css`

No tests for CSS. The file is verified visually in Task 5 after the template exists.

- [ ] **Step 1: Create app/static/workspace.css**

```css
/* ── Tokens ─────────────────────────────────────────────────────────────── */
.workspace-page {
  --bg-card:    #1a1a1a;
  --bg-panel:   #141414;
  --bg-pane:    #000;
  --text:       #f0f0f0;
  --text-muted: #aaaaaa;
  --border:     #2e2e2e;
  --accent:     #7c6af7;
  --success:    #4ade80;
  --warn:       #fb923c;
  --danger:     #f87171;
  --thinking:   #a78bfa;
  --working:    #38bdf8;
}

/* ── Full-bleed body override ────────────────────────────────────────────── */
body:has(.workspace-page) {
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
body:has(.workspace-page) main {
  max-width: none;
  margin: 0;
  padding: 0;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── Grid layout ─────────────────────────────────────────────────────────── */
.workspace-page {
  display: grid;
  grid-template-columns: 260px 1fr;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.workspace-page.workspace-3col {
  grid-template-columns: 260px 1fr 280px;
}

/* ── Column base ─────────────────────────────────────────────────────────── */
.sessions-col,
.detail-col,
.capture-col {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-right: 1px solid var(--border);
}
.detail-col  { border-right: none; background: var(--bg-panel); }
.capture-col { border-right: none; border-left: 1px solid var(--border); background: var(--bg-panel); }

/* ── Column headers ──────────────────────────────────────────────────────── */
.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1.25rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.col-header h2 {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

/* ── Card grid ───────────────────────────────────────────────────────────── */
.card-grid {
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  overflow-y: auto;
  flex: 1;
}

/* ── Session card ────────────────────────────────────────────────────────── */
.session-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-top: 3px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.session-card:hover          { border-color: #444; }
.session-card.selected       { box-shadow: 0 0 0 2px var(--accent); border-color: var(--accent); }
.session-card.session-active { border-top-color: var(--success); }

.card-body    { padding: 0.75rem; }
.card-name    { font-size: 0.9rem; font-weight: 600; color: var(--text); margin: 0 0 0.15rem; }
.card-project { font-size: 0.7rem; color: var(--text-muted); margin: 0 0 0.5rem; }
.card-meta    { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }

.status-badge   { display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; }
.status-active  { color: var(--success); }
.status-stopped { color: var(--text-muted); }

.activity-pill          { font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 999px; border: 1px solid currentColor; line-height: 1.4; }
.activity-thinking      { color: var(--thinking); }
.activity-working       { color: var(--working); }

.card-age { font-size: 0.7rem; color: var(--text-muted); white-space: nowrap; }

.card-footer {
  padding: 0.4rem 0.6rem;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 0.35rem;
  align-items: center;
  flex-wrap: wrap;
}

/* ── Pill buttons ────────────────────────────────────────────────────────── */
.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  border: 1px solid currentColor;
  background: transparent;
  cursor: pointer;
  font-size: 0.72rem;
  color: var(--text-muted);
  transition: opacity 0.1s;
  white-space: nowrap;
  line-height: 1.4;
}
.pill:hover             { opacity: 0.72; }
.pill-primary           { color: var(--accent); }
.pill-primary-filled    { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.pill-danger            { color: var(--danger); }
.pill-ghost             { border: none; }
.pill-on                { color: var(--success); border-color: var(--success); }

/* ── Detail column internals ─────────────────────────────────────────────── */
.panel-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 0.85rem;
  padding: 2rem;
  text-align: center;
}

.detail-col .panel-header,
.detail-col .panel-body      { display: none; }
.detail-col.open .panel-placeholder { display: none; }
.detail-col.open .panel-header      { display: flex; }
.detail-col.open .panel-body        { display: flex; }

.panel-header {
  align-items: flex-start;
  justify-content: space-between;
  padding: 0.875rem 1.25rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  background: var(--bg-panel);
  z-index: 1;
}
.panel-title    { font-size: 0.95rem; font-weight: 600; color: var(--text); margin: 0 0 0.15rem; }
.panel-subtitle { font-size: 0.72rem; color: var(--text-muted); }
.panel-close    { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.25rem; padding: 0 0.25rem; line-height: 1; flex-shrink: 0; }
.panel-close:hover { color: var(--text); }

.panel-body {
  padding: 1rem 1.25rem;
  flex-direction: column;
  gap: 1rem;
  overflow-y: auto;
  flex: 1;
}

/* ── Pane output ─────────────────────────────────────────────────────────── */
.pane-label {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
}
.pane-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--success);
  animation: blink 1.6s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }

.pane-output {
  background: var(--bg-pane);
  border: 1px solid #1e1e1e;
  border-radius: 4px;
  padding: 0.6rem;
  font-family: 'Consolas', 'Monaco', 'Lucida Console', monospace;
  font-size: 0.7rem;
  line-height: 1.5;
  color: var(--success);
  min-height: 120px;
  max-height: 38vh;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.pane-output.pane-stopped { color: var(--text-muted); font-style: italic; }

/* ── Panel sections ──────────────────────────────────────────────────────── */
.panel-section-label {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
}
.panel-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.3rem;
}
.panel-actions .pill {
  width: 100%;
  padding: 0.3rem 0.4rem;
  font-size: 0.72rem;
  border-radius: 6px;
  text-align: center;
}

/* ── Command row ─────────────────────────────────────────────────────────── */
.cmd-row { display: flex; gap: 0.5rem; }
.cmd-row input {
  flex: 1;
  background: #111;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 0.4rem 0.65rem;
  font-size: 0.8rem;
  min-width: 0;
}
.cmd-row input:focus        { outline: none; border-color: var(--accent); }
.cmd-row input::placeholder { color: #4a4a4a; }

/* ── Capture column internals ────────────────────────────────────────────── */
.capture-form-body {
  padding: 0.875rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  overflow-y: auto;
  flex: 1;
}
.capture-form-body .field { display: flex; flex-direction: column; gap: 0.25rem; }
.capture-form-body label  {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.capture-form-body select,
.capture-form-body input,
.capture-form-body textarea {
  background: #111;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 0.35rem 0.6rem;
  font-size: 0.8rem;
  font-family: inherit;
  resize: vertical;
}
.capture-form-body select:focus,
.capture-form-body input:focus,
.capture-form-body textarea:focus { outline: none; border-color: var(--accent); }
.capture-form-body select option  { background: #1a1a1a; }

.capture-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding-top: 0.25rem;
}
.capture-msg       { font-size: 0.75rem; color: var(--success); flex: 1; min-width: 0; }
.capture-msg.error { color: var(--danger); }

/* ── New session modal ───────────────────────────────────────────────────── */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.72);
  z-index: 100;
  align-items: center;
  justify-content: center;
}
.modal-overlay.open { display: flex; }
.modal {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.5rem;
  width: 420px;
  max-width: 90vw;
}
.modal h2              { margin: 0 0 1.25rem; font-size: 1rem; color: var(--text); }
.modal .field          { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.75rem; }
.modal label           { font-size: 0.75rem; color: var(--text-muted); }
.modal input,
.modal select          { background: #111; border: 1px solid var(--border); border-radius: 6px; color: var(--text); padding: 0.45rem 0.75rem; font-size: 0.85rem; }
.modal input:focus,
.modal select:focus    { outline: none; border-color: var(--accent); }
.modal select option   { background: #1a1a1a; }
.modal-footer          { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1.25rem; }

/* ── Empty state ─────────────────────────────────────────────────────────── */
.empty-state { text-align: center; color: var(--text-muted); padding: 3rem 1rem; font-size: 0.85rem; }
```

- [ ] **Step 2: Commit**

```bash
git -C /mnt/c/Server/projects/obsidian-capture add app/static/workspace.css
git -C /mnt/c/Server/projects/obsidian-capture commit -m "feat: add workspace.css for three-column grid layout"
```

---

## Task 4: Create agents.js

**Files:**
- Create: `app/static/agents.js`

This extracts all inline JS from `agents.html` into a static file, adds URL state persistence, and adds capture column project sync.

- [ ] **Step 1: Create app/static/agents.js**

```javascript
// ── State ──────────────────────────────────────────────────────────────────
let sessions   = [];
let selectedId = null;
let gridTimer  = null;
let paneTimer  = null;

// ── URL state ──────────────────────────────────────────────────────────────
function pushSessionToUrl(id) {
  const url = id
    ? location.pathname + '?session=' + encodeURIComponent(id)
    : location.pathname;
  history.replaceState(null, '', url);
}

function readSessionFromUrl() {
  return new URLSearchParams(location.search).get('session');
}

// ── API helper ─────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  return fetch('/agents' + path, opts);
}

// ── Formatting ─────────────────────────────────────────────────────────────
function fmtAge(startedAt) {
  if (!startedAt) return '—';
  const secs = Math.floor((Date.now() - new Date(startedAt)) / 1000);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Card rendering ──────────────────────────────────────────────────────────
function activityPill(s) {
  if (s.status !== 'active' || !s.activity || s.activity === 'idle') return '';
  const cls = s.activity === 'thinking' ? 'activity-thinking' : 'activity-working';
  return `<span class="activity-pill ${cls}">${s.activity}</span>`;
}

function cardFooter(s) {
  if (s.status === 'active') {
    return `
      <button class="pill pill-danger"
              onclick="event.stopPropagation();stopSession('${esc(s.id)}')">Stop</button>
      <button class="pill ${s.remote_control ? 'pill-on' : ''}"
              onclick="event.stopPropagation();toggleRc('${esc(s.id)}')">RC: ${s.remote_control ? 'on' : 'off'}</button>
      <button class="pill ${s.autonomous_mode ? 'pill-on' : ''}"
              onclick="event.stopPropagation();toggleAuto('${esc(s.id)}')">Auto: ${s.autonomous_mode ? 'on' : 'off'}</button>
    `;
  }
  return `
    <button class="pill pill-primary-filled"
            onclick="event.stopPropagation();resetSession('${esc(s.id)}')">Start</button>
    <button class="pill pill-danger pill-ghost"
            onclick="event.stopPropagation();removeSession('${esc(s.id)}')">Remove</button>
  `;
}

function renderCard(s) {
  const activeClass = s.status === 'active' ? ' session-active' : '';
  const selected    = s.id === selectedId ? ' selected' : '';
  const statusHtml  = s.status === 'active'
    ? `<span class="status-badge"><span class="status-active">● active</span>${activityPill(s)}</span>`
    : `<span class="status-badge status-stopped">○ stopped</span>`;
  return `
    <div class="session-card${activeClass}${selected}"
         data-id="${esc(s.id)}" onclick="openPanel('${esc(s.id)}')">
      <div class="card-body">
        <div class="card-name">${esc(s.name)}</div>
        <div class="card-project">${esc(s.project)}</div>
        <div class="card-meta">
          ${statusHtml}
          <span class="card-age">${fmtAge(s.started_at)}</span>
        </div>
      </div>
      <div class="card-footer">${cardFooter(s)}</div>
    </div>
  `;
}

function updateGrid(newSessions) {
  sessions = [...newSessions].sort((a, b) => (b.status === 'active') - (a.status === 'active'));
  const grid = document.getElementById('card-grid');
  if (!sessions.length) {
    grid.innerHTML = '<div class="empty-state">No sessions yet. Click + New to start one.</div>';
    return;
  }
  grid.innerHTML = sessions.map(renderCard).join('');
}

// ── Session polling ─────────────────────────────────────────────────────────
async function pollSessions() {
  try {
    const resp = await fetch('/agents/sessions');
    if (!resp.ok) return;
    const data = await resp.json();
    updateGrid(data);
    if (selectedId) {
      const sel = data.find(s => s.id === selectedId);
      if (sel) renderPanelActions(sel);
    }
  } catch (e) { console.error('pollSessions failed:', e); }
}

// ── Pane polling ────────────────────────────────────────────────────────────
async function pollPane() {
  if (!selectedId) return;
  try {
    const resp = await fetch(`/agents/sessions/${selectedId}/pane`);
    if (!resp.ok) return;
    const data = await resp.json();
    const out = document.getElementById('pane-output');
    const dot = document.getElementById('pane-dot');
    if (!data.active || !data.lines || !data.lines.length) {
      out.textContent = '— session stopped —';
      out.classList.add('pane-stopped');
      dot.style.visibility = 'hidden';
    } else {
      const atBottom = out.scrollHeight - out.scrollTop <= out.clientHeight + 24;
      out.classList.remove('pane-stopped');
      dot.style.visibility = '';
      out.textContent = data.lines.join('\n');
      if (atBottom) out.scrollTop = out.scrollHeight;
    }
  } catch (e) { console.error('pollPane failed:', e); }
}

function startPanePolling() { pollPane(); paneTimer = setInterval(pollPane, 2000); }
function stopPanePolling()  { clearInterval(paneTimer); paneTimer = null; }

// ── Panel ───────────────────────────────────────────────────────────────────
function renderPanelActions(s) {
  const el = document.getElementById('panel-actions');
  if (s.status === 'active') {
    el.innerHTML = `
      <button class="pill ${s.remote_control  ? 'pill-on' : ''}"
              onclick="toggleRc('${esc(s.id)}')">Toggle RC (${s.remote_control  ? 'on' : 'off'})</button>
      <button class="pill ${s.autonomous_mode ? 'pill-on' : ''}"
              onclick="toggleAuto('${esc(s.id)}')">Toggle Auto (${s.autonomous_mode ? 'on' : 'off'})</button>
      <button class="pill" onclick="sendCmd('${esc(s.id)}','/clear')">Clear context</button>
      <button class="pill" onclick="sendCmd('${esc(s.id)}','/compact')">Compact</button>
      <button class="pill" onclick="resetSession('${esc(s.id)}')">Reset session</button>
      <button class="pill pill-danger" onclick="stopSession('${esc(s.id)}')">Stop session</button>
      <button class="pill pill-danger pill-ghost" style="font-size:0.68rem"
              onclick="removeSession('${esc(s.id)}')">Remove</button>
    `;
  } else {
    el.innerHTML = `
      <button class="pill pill-primary-filled" onclick="resetSession('${esc(s.id)}')">Start session</button>
      <button class="pill pill-danger pill-ghost" style="font-size:0.68rem"
              onclick="removeSession('${esc(s.id)}')">Remove</button>
    `;
  }
}

function syncCaptureProject(slug) {
  const sel = document.getElementById('cap-project');
  if (!sel) return;
  const opt = [...sel.options].find(o => o.value === slug);
  if (opt) sel.value = slug;
}

function openPanel(id) {
  const s = sessions.find(x => x.id === id);
  if (!s) return;
  selectedId = id;
  document.getElementById('panel-title').textContent    = s.name;
  document.getElementById('panel-subtitle').textContent = s.project;
  renderPanelActions(s);
  document.getElementById('pane-output').textContent = '…';
  document.getElementById('pane-output').classList.remove('pane-stopped');
  document.getElementById('detail-col').classList.add('open');
  document.querySelectorAll('.session-card')
    .forEach(el => el.classList.toggle('selected', el.dataset.id === id));
  stopPanePolling();
  startPanePolling();
  pushSessionToUrl(id);
  syncCaptureProject(s.project);
}

function closePanel() {
  selectedId = null;
  stopPanePolling();
  document.getElementById('detail-col').classList.remove('open');
  document.querySelectorAll('.session-card').forEach(el => el.classList.remove('selected'));
  pushSessionToUrl(null);
  const sel = document.getElementById('cap-project');
  if (sel && sel.options.length) sel.selectedIndex = 0;
}

// ── Actions ─────────────────────────────────────────────────────────────────
async function stopSession(id) {
  await api('DELETE', '/sessions/' + id);
  await pollSessions();
  if (selectedId === id) closePanel();
}

async function resetSession(id) {
  await api('POST', '/sessions/' + id + '/reset');
  await pollSessions();
}

async function removeSession(id) {
  await api('DELETE', '/sessions/' + id + '/remove');
  await pollSessions();
  if (selectedId === id) closePanel();
}

async function toggleRc(id) {
  await api('PATCH', '/sessions/' + id + '/remote_control');
  await pollSessions();
}

async function toggleAuto(id) {
  await api('PATCH', '/sessions/' + id + '/autonomous_mode');
  await pollSessions();
}

async function sendCmd(id, cmd) {
  await api('POST', '/sessions/' + id + '/command', { command: cmd });
  await pollSessions();
}

async function sendPanelCmd() {
  const input = document.getElementById('panel-cmd');
  const cmd   = input.value.trim();
  if (!cmd || !selectedId) return;
  input.value = '';
  await api('POST', '/sessions/' + selectedId + '/command', { command: cmd });
}

// ── Capture column ──────────────────────────────────────────────────────────
async function submitCapture() {
  const project = document.getElementById('cap-project')?.value;
  const type    = document.getElementById('cap-type')?.value;
  const title   = document.getElementById('cap-title')?.value?.trim();
  const body    = document.getElementById('cap-body')?.value?.trim();
  const msgEl   = document.getElementById('capture-msg');

  if (!title) { showCaptureMsg('Title is required', true); return; }

  const payload = { type, project, title, body: body || '' };
  if (type === 'idea') { payload.priority = 'medium'; payload.effort = 'medium'; }

  try {
    const resp = await fetch('/capture/json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (resp.ok) {
      document.getElementById('cap-title').value = '';
      document.getElementById('cap-body').value  = '';
      showCaptureMsg('Saved ✓', false);
      setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 3000);
    } else {
      showCaptureMsg(data.error || 'Error saving', true);
    }
  } catch (e) {
    showCaptureMsg('Network error', true);
  }
}

function showCaptureMsg(text, isError) {
  const el = document.getElementById('capture-msg');
  if (!el) return;
  el.textContent = text;
  el.className = 'capture-msg' + (isError ? ' error' : '');
}

// ── Modal ────────────────────────────────────────────────────────────────────
function openModal()  { document.getElementById('modal-overlay').classList.add('open'); }
function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  document.getElementById('new-session-form').reset();
  updateModalDir(document.getElementById('m-project').value);
}

function updateModalDir(slug) {
  document.getElementById('m-dir').value = '/mnt/c/Server/projects/' + slug;
}

async function submitNewSession(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api('POST', '/sessions', {
    name:           fd.get('name'),
    project:        fd.get('project'),
    project_dir:    fd.get('project_dir'),
    remote_control: false,
  });
  closeModal();
  await pollSessions();
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateGrid(window.INITIAL_SESSIONS || []);
  gridTimer = setInterval(pollSessions, 4000);

  const urlSession = readSessionFromUrl();
  if (urlSession) {
    const found = (window.INITIAL_SESSIONS || []).find(s => s.id === urlSession);
    if (found) openPanel(urlSession);
  }
});
```

- [ ] **Step 2: Commit**

```bash
git -C /mnt/c/Server/projects/obsidian-capture add app/static/agents.js
git -C /mnt/c/Server/projects/obsidian-capture commit -m "feat: add agents.js with URL state and capture sync"
```

---

## Task 5: Create workspace.html, update agents.py, delete agents.html

**Files:**
- Create: `app/templates/workspace.html`
- Modify: `app/routes/agents.py`
- Delete: `app/templates/agents.html`
- Delete: `app/static/agents.css`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Write failing tests for new routes**

Add to `tests/test_agents.py`:

```python
def test_home_page_renders(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Sessions" in resp.data


def test_home_page_has_capture_column(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/")
    assert b"cap-project" in resp.data


def test_agents_page_no_capture_column(client, mocker):
    mocker.patch("app.routes.agents.requests.request",
                 return_value=_mock_response([MOCK_SESSION]))
    resp = client.get("/agents")
    assert resp.status_code == 200
    assert b"cap-project" not in resp.data
```

Run: `docker exec obsidian-capture python -m pytest tests/test_agents.py::test_home_page_renders -v`
Expected: FAIL (browse.py's temp redirect sends to /tasks, or / doesn't render workspace.html yet)

- [ ] **Step 2: Create app/templates/workspace.html**

```html
{% extends "base.html" %}
{% block title %}{% if three_col %}Home{% else %}Sessions{% endif %}{% endblock %}

{% block content %}
<link rel="stylesheet" href="{{ url_for('static', filename='workspace.css') }}">

<div class="workspace-page{% if three_col %} workspace-3col{% endif %}">

  <!-- ── Col 1: Sessions ── -->
  <div class="sessions-col">
    <div class="col-header">
      <h2>Sessions</h2>
      <button class="pill pill-primary" onclick="openModal()">+ New</button>
    </div>
    <div class="card-grid" id="card-grid">
      <div class="empty-state">Loading…</div>
    </div>
  </div>

  <!-- ── Col 2: Session Detail ── -->
  <div class="detail-col" id="detail-col">
    <div class="panel-placeholder" id="panel-placeholder">Select a session to view details</div>

    <div class="panel-header" id="panel-header">
      <div>
        <div class="panel-title" id="panel-title"></div>
        <div class="panel-subtitle" id="panel-subtitle"></div>
      </div>
      <button class="panel-close" onclick="closePanel()">×</button>
    </div>

    <div class="panel-body" id="panel-body">
      <!-- Command input is first -->
      <div>
        <div class="panel-section-label">Command</div>
        <div class="cmd-row">
          <input type="text" id="panel-cmd" placeholder="Type a /command…"
                 onkeydown="if(event.key==='Enter') sendPanelCmd()">
          <button class="pill pill-primary" onclick="sendPanelCmd()">Send</button>
        </div>
      </div>

      <div>
        <div class="pane-label">
          <span class="pane-dot" id="pane-dot"></span>
          Live output
        </div>
        <div class="pane-output" id="pane-output"></div>
      </div>

      <div>
        <div class="panel-section-label">Actions</div>
        <div class="panel-actions" id="panel-actions"></div>
      </div>
    </div>
  </div>

  {% if three_col %}
  <!-- ── Col 3: Capture ── -->
  <div class="capture-col">
    <div class="col-header">
      <h2>Capture</h2>
    </div>
    <div class="capture-form-body">
      <div class="field">
        <label for="cap-project">Project</label>
        <select id="cap-project">
          {% for p in projects %}
            <option value="{{ p.slug }}">{{ p.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="field">
        <label for="cap-type">Type</label>
        <select id="cap-type">
          <option value="note">Note</option>
          <option value="idea">Idea</option>
          <option value="bug">Bug</option>
        </select>
      </div>
      <div class="field">
        <label for="cap-title">Title</label>
        <input type="text" id="cap-title" placeholder="Entry title…" autocomplete="off">
      </div>
      <div class="field">
        <label for="cap-body">Description</label>
        <textarea id="cap-body" rows="5" placeholder="Optional description…"></textarea>
      </div>
      <div class="capture-footer">
        <span class="capture-msg" id="capture-msg"></span>
        <button class="pill pill-primary-filled" onclick="submitCapture()">Capture</button>
      </div>
    </div>
  </div>
  {% endif %}

</div><!-- .workspace-page -->

<!-- ── New session modal ── -->
<div class="modal-overlay" id="modal-overlay"
     onclick="if(event.target===this) closeModal()">
  <div class="modal">
    <h2>New Session</h2>
    <form id="new-session-form" onsubmit="submitNewSession(event)">
      <div class="field">
        <label for="m-name">Name</label>
        <input id="m-name" name="name" type="text"
               placeholder="e.g. zone-builder-dev" required autocomplete="off">
      </div>
      <div class="field">
        <label for="m-project">Project</label>
        <select id="m-project" name="project" onchange="updateModalDir(this.value)">
          {% for p in projects %}
            <option value="{{ p.slug }}">{{ p.name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="field">
        <label for="m-dir">Project dir</label>
        <input id="m-dir" name="project_dir" type="text"
               value="/mnt/c/Server/projects/{{ projects[0].slug if projects else '' }}">
      </div>
      <div class="modal-footer">
        <button type="button" class="pill" onclick="closeModal()">Cancel</button>
        <button type="submit" class="pill pill-primary-filled">Start Session</button>
      </div>
    </form>
  </div>
</div>

<script>window.INITIAL_SESSIONS = {{ sessions | tojson }};</script>
<script src="{{ url_for('static', filename='agents.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Update agents.py routes**

Replace the `agents()` function and add a `home()` function in `app/routes/agents.py`:

```python
@bp.route("/")
def home():
    try:
        sessions, _ = _proxy("GET", "/sessions")
        for s in sessions:
            s["age_str"] = _age_str(s.get("started_at"))
    except Exception:
        sessions = []

    from app.services.vault import get_projects_with_meta
    projects = get_projects_with_meta()
    return render_template("workspace.html", sessions=sessions,
                           projects=projects, three_col=True)


@bp.route("/agents")
def agents():
    try:
        sessions, _ = _proxy("GET", "/sessions")
        for s in sessions:
            s["age_str"] = _age_str(s.get("started_at"))
    except Exception:
        sessions = []

    from app.services.vault import get_projects_with_meta
    projects = get_projects_with_meta()
    return render_template("workspace.html", sessions=sessions,
                           projects=projects, three_col=False)
```

- [ ] **Step 4: Remove temp redirect and agents.html**

In `app/routes/browse.py`, delete the `home_redirect()` function and its route:

```python
# DELETE these lines:
@bp.route("/")
def home_redirect():
    return redirect(url_for("browse.tasks"))
```

Also remove `redirect` from the browse.py imports if it's no longer used anywhere in that file:
```python
# Check: grep -n "redirect" app/routes/browse.py
# If only home_redirect used it, change the import line to:
from flask import Blueprint, render_template, request, url_for, flash, abort
```

Delete `app/templates/agents.html` and `app/static/agents.css`:

```bash
git -C /mnt/c/Server/projects/obsidian-capture rm app/templates/agents.html app/static/agents.css
```

- [ ] **Step 5: Update test_agents.py — fix existing test**

The existing test `test_agents_page_renders` checks for `b"test-session"` in the response. This will still pass since workspace.html renders session names. Verify it still works after the template rename.

Also update any test that referenced the old `agents.html`-specific markup. Run all tests to identify failures.

- [ ] **Step 6: Run all tests**

```bash
docker exec obsidian-capture python -m pytest tests/ -v
```

Expected: all PASS including the three new home page tests

- [ ] **Step 7: Commit**

```bash
git -C /mnt/c/Server/projects/obsidian-capture add \
  app/templates/workspace.html app/routes/agents.py app/routes/browse.py \
  tests/test_agents.py
git -C /mnt/c/Server/projects/obsidian-capture \
  commit -m "feat: add workspace.html + home route, replace agents.html"
```

---

## Task 6: Update base.html navigation

**Files:**
- Modify: `app/templates/base.html`

- [ ] **Step 1: Update nav in base.html**

Replace the entire `<nav>` block in `app/templates/base.html`:

```html
<nav>
  <a href="/" class="nav-brand">Obsidian Capture</a>
  <a href="{{ url_for('agents.home') }}"   class="nav-link">Home</a>
  <a href="{{ url_for('browse.tasks') }}"  class="nav-link">Tasks</a>
  <a href="{{ url_for('agents.agents') }}" class="nav-link">Sessions</a>
  <a href="{{ url_for('capture.capture_form') }}" class="nav-link">Capture</a>
</nav>
```

- [ ] **Step 2: Rebuild and smoke-test**

```bash
docker.exe compose -f C:\Server\docker\compose-prod.yml --env-file C:\Server\docker\.env.prod \
  up -d --build obsidian-capture
```

Visit `http://192.168.1.77:5009/` — should show the three-column workspace.
Visit `http://192.168.1.77:5009/agents` — should show the two-column sessions view (no capture column).
Visit `http://192.168.1.77:5009/tasks` — should show the project grid dashboard.

Select a session, note the URL (`?session=<id>`), refresh — should reopen the same session.
Select a session, check that the Capture column's Project dropdown updates to match the session project.
Submit a capture entry from the inline form — should show "Saved ✓" without navigating away.

- [ ] **Step 3: Run full test suite one more time**

```bash
docker exec obsidian-capture python -m pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git -C /mnt/c/Server/projects/obsidian-capture add app/templates/base.html
git -C /mnt/c/Server/projects/obsidian-capture \
  commit -m "feat: update nav — Home/Tasks/Sessions/Capture"
```
