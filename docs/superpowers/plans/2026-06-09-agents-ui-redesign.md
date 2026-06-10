# Agents UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the clunky table-based session manager with a card grid + slide-in detail panel that is reactive, polished, and higher-contrast.

**Architecture:** Four files change. Two backend: a new pane endpoint on the session manager and a proxy route in obsidian-capture. Two frontend: a full CSS rewrite and a full HTML/JS rewrite. JS polling replaces all `window.location.reload()` calls.

**Tech Stack:** Flask, Jinja2, vanilla JS (fetch + setInterval), vanilla CSS. No new dependencies. Session manager runs in WSL2 at `http://host.docker.internal:5010`.

**Note on frontend tasks:** Use the **Fable** model (`claude-fable-5`) for Tasks 3 and 4 — these are creative design tasks.

---

## File Map

| File | Change |
|---|---|
| `services/session-manager/app.py` | Add `GET /sessions/<id>/pane` endpoint |
| `services/session-manager/tests/test_app.py` | Add 3 tests for pane endpoint |
| `app/routes/agents.py` | Add `GET /agents/sessions/<id>/pane` proxy route |
| `app/static/agents.css` | Full rewrite — new colour system, cards, panel, modal |
| `app/templates/agents.html` | Full rewrite — card grid, panel, modal, polling JS |

---

## Task 1: session-manager pane endpoint

**Context:** The session manager is a standalone Flask app at `C:\Server\claude-config\services\session-manager\`. It manages Claude Code tmux sessions. Tests use pytest-mock's `mocker` fixture. Read `tests/test_app.py` to understand the test fixture and patch patterns before writing tests.

**Files:**
- Modify: `services/session-manager/app.py` (after line 120, before `if __name__`)
- Modify: `services/session-manager/tests/test_app.py` (append to end of file)

- [ ] **Step 1: Write the failing tests**

Append to `services/session-manager/tests/test_app.py`:

```python
def test_get_pane_not_found(client):
    resp = client.get("/sessions/nonexistent-id/pane")
    assert resp.status_code == 404


def test_get_pane_stopped_session(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=True)
    mocker.patch("app.capture_pane", return_value="")
    create_resp = client.post("/sessions", json={
        "name": "pane-stopped", "project": "proj",
        "project_dir": "/dir", "remote_control": False,
    })
    sid = create_resp.get_json()["id"]
    mocker.patch("app.has_session", return_value=False)
    resp = client.get(f"/sessions/{sid}/pane")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is False
    assert data["lines"] == []


def test_get_pane_active_session(client, mocker):
    mocker.patch("app.launch_session")
    mocker.patch("app.has_session", return_value=True)
    mocker.patch("app.capture_pane", return_value="alpha\nbeta\ngamma")
    create_resp = client.post("/sessions", json={
        "name": "pane-active", "project": "proj",
        "project_dir": "/dir", "remote_control": False,
    })
    sid = create_resp.get_json()["id"]
    resp = client.get(f"/sessions/{sid}/pane")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is True
    assert data["lines"] == ["alpha", "beta", "gamma"]
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd C:\Server\claude-config\services\session-manager
python -m pytest tests/test_app.py::test_get_pane_not_found tests/test_app.py::test_get_pane_stopped_session tests/test_app.py::test_get_pane_active_session -v
```

Expected: 3 FAILED with `404 != 200` or similar (route not found).

- [ ] **Step 3: Add the endpoint to app.py**

Add after the `send_slash_command` route and before `if __name__ == "__main__":`:

```python
@app.route("/sessions/<session_id>/pane")
def get_pane(session_id):
    session = get_session(session_id)
    if not session:
        abort(404)
    if not has_session(session["tmux_session"]):
        return jsonify({"lines": [], "active": False})
    try:
        output = capture_pane(session["tmux_session"])
        lines = output.splitlines()[-40:]
        return jsonify({"lines": lines, "active": True})
    except Exception:
        return jsonify({"lines": [], "active": False})
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd C:\Server\claude-config\services\session-manager
python -m pytest tests/test_app.py::test_get_pane_not_found tests/test_app.py::test_get_pane_stopped_session tests/test_app.py::test_get_pane_active_session -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Run full test suite to check for regressions**

```
cd C:\Server\claude-config\services\session-manager
python -m pytest tests/ -v
```

Expected: all tests pass (was 57 before this task; now 60).

- [ ] **Step 6: Restart the session manager to pick up the new route**

```
wsl -e bash -c "tmux send-keys -t session-manager C-c '' && sleep 1 && tmux send-keys -t session-manager 'python3 app.py' Enter"
```

Wait 3 seconds, then verify:
```
curl -s http://192.168.1.77:5010/sessions | python3 -m json.tool | head -5
```

Expected: JSON array (even if empty).

- [ ] **Step 7: Commit**

```
cd C:\Server\claude-config
git add services/session-manager/app.py services/session-manager/tests/test_app.py
git commit -m "feat: add pane content endpoint to session manager"
```

---

## Task 2: agents.py proxy route

**Context:** `app/routes/agents.py` in the obsidian-capture project is a thin proxy layer — all routes call `_proxy()` and return the result. This task adds one more route following the exact same pattern.

**Files:**
- Modify: `app/routes/agents.py` (append one route after `send_command`)

- [ ] **Step 1: Add the proxy route**

Append to `app/routes/agents.py` after the `send_command` route:

```python
@bp.route("/agents/sessions/<session_id>/pane")
def session_pane(session_id):
    data, status = _proxy("GET", f"/sessions/{session_id}/pane")
    return jsonify(data), status
```

- [ ] **Step 2: Verify the route is reachable**

With obsidian-capture running (`docker compose up` in `C:\Server\projects\obsidian-capture`), fetch a pane for any session ID visible in the UI:

```
curl -s http://192.168.1.77:5009/agents/sessions/<any-id>/pane
```

Expected: `{"active": false, "lines": []}` or `{"active": true, "lines": [...]}` — not a 404 or 500.

- [ ] **Step 3: Commit**

```
cd C:\Server\projects\obsidian-capture
git add app/routes/agents.py
git commit -m "feat: add pane proxy route to agents blueprint"
```

---

## Task 3: agents.css full rewrite

**Context:** `app/static/agents.css` is loaded in the agents page. Rewrite it completely with the new colour token system. The base template at `app/templates/base.html` may define some globals — read it first to avoid conflicts with existing variables.

**Model note:** Use **Fable** (`claude-fable-5`) for this task.

**Files:**
- Overwrite: `app/static/agents.css`

- [ ] **Step 1: Read base.html to understand existing CSS variables**

Read `app/templates/base.html` and note any CSS custom properties (e.g. `--color-*`) already defined. The new agents.css uses its own scoped token names — check there are no conflicts.

- [ ] **Step 2: Write the new agents.css**

Replace the entire contents of `app/static/agents.css` with:

```css
/* ── Tokens ───────────────────────────────────────────────────────────────── */
.agents-page {
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

/* ── Layout ───────────────────────────────────────────────────────────────── */
.agents-page {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.agents-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.agents-header h1 {
  margin: 0;
  font-size: 1.25rem;
  color: var(--text);
}

.agents-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* ── Card grid ────────────────────────────────────────────────────────────── */
.card-grid {
  flex: 1;
  padding: 1.5rem;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
  align-content: start;
  overflow-y: auto;
}

/* ── Session card ─────────────────────────────────────────────────────────── */
.session-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-top: 3px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.session-card:hover           { border-color: #444; }
.session-card.selected        { box-shadow: 0 0 0 2px var(--accent); border-color: var(--accent); }

.session-card.health-fresh { border-top-color: var(--success); }
.session-card.health-aging  { border-top-color: var(--warn); }
.session-card.health-heavy  { border-top-color: var(--danger); }

.card-body {
  padding: 1rem;
}

.card-name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text);
  margin: 0 0 0.2rem;
}

.card-project {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0 0 0.75rem;
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
}

.status-active  { color: var(--success); }
.status-stopped { color: var(--text-muted); }

.activity-pill {
  font-size: 0.68rem;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  border: 1px solid currentColor;
  line-height: 1.4;
}
.activity-thinking { color: var(--thinking); }
.activity-working  { color: var(--working); }

.card-age {
  font-size: 0.75rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.card-footer {
  padding: 0.5rem 0.75rem;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 0.4rem;
  align-items: center;
  flex-wrap: wrap;
}

/* ── Pill buttons ─────────────────────────────────────────────────────────── */
.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.2rem 0.65rem;
  border-radius: 999px;
  border: 1px solid currentColor;
  background: transparent;
  cursor: pointer;
  font-size: 0.75rem;
  color: var(--text-muted);
  transition: opacity 0.1s;
  white-space: nowrap;
  line-height: 1.4;
}
.pill:hover { opacity: 0.72; }

.pill-primary        { color: var(--accent); }
.pill-primary-filled { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.pill-danger         { color: var(--danger); }
.pill-ghost          { border: none; }
.pill-on             { color: var(--success); border-color: var(--success); }

/* ── Detail panel ─────────────────────────────────────────────────────────── */
.detail-panel {
  width: 0;
  overflow: hidden;
  transition: width 0.2s ease;
  border-left: 1px solid transparent;
  background: var(--bg-panel);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.detail-panel.open {
  width: 380px;
  border-left-color: var(--border);
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  background: var(--bg-panel);
  z-index: 1;
}

.panel-title    { font-size: 1rem; font-weight: 600; color: var(--text); margin: 0 0 0.15rem; }
.panel-subtitle { font-size: 0.75rem; color: var(--text-muted); }

.panel-close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 1.25rem;
  padding: 0 0.25rem;
  line-height: 1;
  flex-shrink: 0;
}
.panel-close:hover { color: var(--text); }

.panel-body {
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* ── Pane output ──────────────────────────────────────────────────────────── */
.pane-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.5rem;
}

.pane-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  animation: blink 1.6s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.25; }
}

.pane-output {
  background: var(--bg-pane);
  border: 1px solid #1e1e1e;
  border-radius: 4px;
  padding: 0.75rem;
  font-family: 'Consolas', 'Monaco', 'Lucida Console', monospace;
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--success);
  min-height: 160px;
  max-height: 42vh;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.pane-output.pane-stopped {
  color: var(--text-muted);
  font-style: italic;
}

/* ── Panel actions ────────────────────────────────────────────────────────── */
.panel-section-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 0.4rem;
}

.panel-actions {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.panel-actions .pill {
  width: 100%;
  padding: 0.4rem 1rem;
  font-size: 0.8rem;
  border-radius: 6px;
}

/* ── Command row ──────────────────────────────────────────────────────────── */
.cmd-row {
  display: flex;
  gap: 0.5rem;
}

.cmd-row input {
  flex: 1;
  background: #111;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
  min-width: 0;
}
.cmd-row input:focus         { outline: none; border-color: var(--accent); }
.cmd-row input::placeholder  { color: #4a4a4a; }

/* ── New session modal ────────────────────────────────────────────────────── */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.72);
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

.modal h2 { margin: 0 0 1.25rem; font-size: 1rem; color: var(--text); }

.modal .field          { display: flex; flex-direction: column; gap: 0.3rem; margin-bottom: 0.75rem; }
.modal label           { font-size: 0.75rem; color: var(--text-muted); }
.modal input,
.modal select          {
  background: #111;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 0.45rem 0.75rem;
  font-size: 0.85rem;
}
.modal input:focus,
.modal select:focus    { outline: none; border-color: var(--accent); }
.modal select option   { background: #1a1a1a; }

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.25rem;
}

/* ── Empty state ──────────────────────────────────────────────────────────── */
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--text-muted);
  padding: 3rem;
  font-size: 0.9rem;
}

/* ── Narrow viewport: panel overlays ─────────────────────────────────────── */
@media (max-width: 800px) {
  .detail-panel.open {
    position: fixed;
    right: 0; top: 0; bottom: 0;
    width: 100% !important;
    max-width: 380px;
    z-index: 50;
  }
}
```

- [ ] **Step 3: Verify the page still loads**

Open `http://192.168.1.77:5009/agents` in a browser (rebuild obsidian-capture first if needed: `docker compose up --build -d` in `C:\Server\projects\obsidian-capture`). The page must load without broken styling. Since agents.html hasn't changed yet, it may look odd — that's fine. Confirm no 500 error and no missing file error in the browser console.

- [ ] **Step 4: Commit**

```
cd C:\Server\projects\obsidian-capture
git add app/static/agents.css
git commit -m "feat: rewrite agents.css with high-contrast card/panel design tokens"
```

---

## Task 4: agents.html full rewrite

**Context:** This is the main UI work. Replace the table-based template with a card grid + side panel + modal. The page uses vanilla JS — no bundler, no framework. All state is in module-level JS variables. The Jinja template receives `sessions` (list) and `projects` (list of `{slug, name}` dicts) from `agents.py`.

Read `app/templates/base.html` before starting so you know what wrapper elements and CSS variables already exist.

**Model note:** Use **Fable** (`claude-fable-5`) for this task.

**Files:**
- Overwrite: `app/templates/agents.html`

- [ ] **Step 1: Write the new agents.html**

Replace the entire contents of `app/templates/agents.html` with:

```html
{% extends "base.html" %}
{% block title %}Agents{% endblock %}

{% block content %}
<link rel="stylesheet" href="{{ url_for('static', filename='agents.css') }}">

<div class="agents-page">

  <!-- ── Header ── -->
  <div class="agents-header">
    <h1>Agents</h1>
    <button class="pill pill-primary" onclick="openModal()">+ New Session</button>
  </div>

  <!-- ── Body: grid + panel ── -->
  <div class="agents-body">

    <div class="card-grid" id="card-grid">
      <div class="empty-state">Loading…</div>
    </div>

    <div class="detail-panel" id="detail-panel">
      <div class="panel-header">
        <div>
          <div class="panel-title" id="panel-title"></div>
          <div class="panel-subtitle" id="panel-subtitle"></div>
        </div>
        <button class="panel-close" onclick="closePanel()">×</button>
      </div>
      <div class="panel-body">

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

        <div>
          <div class="panel-section-label">Command</div>
          <div class="cmd-row">
            <input type="text" id="panel-cmd" placeholder="Type a /command…"
                   onkeydown="if(event.key==='Enter') sendPanelCmd()">
            <button class="pill pill-primary" onclick="sendPanelCmd()">Send</button>
          </div>
        </div>

      </div>
    </div>

  </div><!-- .agents-body -->
</div><!-- .agents-page -->

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

<script>
// ── State ──────────────────────────────────────────────────────────────────
let sessions = {{ sessions | tojson }};
let selectedId = null;
let gridTimer  = null;
let paneTimer  = null;

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

// ── Card rendering ──────────────────────────────────────────────────────────
function activityPill(s) {
  if (s.status !== 'active' || !s.activity || s.activity === 'idle') return '';
  const cls = s.activity === 'thinking' ? 'activity-thinking' : 'activity-working';
  return `<span class="activity-pill ${cls}">${s.activity}</span>`;
}

function cardFooter(s) {
  if (s.status === 'active') {
    return `
      <button class="pill pill-danger" onclick="event.stopPropagation();stopSession('${s.id}')">Stop</button>
      <button class="pill ${s.remote_control ? 'pill-on' : ''}"
              onclick="event.stopPropagation();toggleRc('${s.id}')">RC: ${s.remote_control ? 'on' : 'off'}</button>
      <button class="pill ${s.autonomous_mode ? 'pill-on' : ''}"
              onclick="event.stopPropagation();toggleAuto('${s.id}')">Auto: ${s.autonomous_mode ? 'on' : 'off'}</button>
    `;
  }
  return `
    <button class="pill pill-primary-filled"
            onclick="event.stopPropagation();resetSession('${s.id}')">Start</button>
    <button class="pill pill-danger pill-ghost"
            onclick="event.stopPropagation();removeSession('${s.id}')">Remove</button>
  `;
}

function renderCard(s) {
  const health   = s.health || 'fresh';
  const selected = s.id === selectedId ? ' selected' : '';
  const statusHtml = s.status === 'active'
    ? `<span class="status-badge"><span class="status-active">● active</span>${activityPill(s)}</span>`
    : `<span class="status-badge status-stopped">○ stopped</span>`;
  return `
    <div class="session-card health-${health}${selected}"
         data-id="${s.id}" onclick="openPanel('${s.id}')">
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

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function updateGrid(newSessions) {
  sessions = newSessions;
  const grid = document.getElementById('card-grid');
  if (!sessions.length) {
    grid.innerHTML = '<div class="empty-state">No sessions yet. Click + New Session to start one.</div>';
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
  } catch (_) {}
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
  } catch (_) {}
}

function startPanePolling() { pollPane(); paneTimer = setInterval(pollPane, 2000); }
function stopPanePolling()  { clearInterval(paneTimer); paneTimer = null; }

// ── Panel ───────────────────────────────────────────────────────────────────
function renderPanelActions(s) {
  const el = document.getElementById('panel-actions');
  if (s.status === 'active') {
    el.innerHTML = `
      <button class="pill ${s.remote_control  ? 'pill-on' : ''}"
              onclick="toggleRc('${s.id}')">Toggle RC  (${s.remote_control  ? 'on' : 'off'})</button>
      <button class="pill ${s.autonomous_mode ? 'pill-on' : ''}"
              onclick="toggleAuto('${s.id}')">Toggle Auto (${s.autonomous_mode ? 'on' : 'off'})</button>
      <button class="pill" onclick="sendCmd('${s.id}','/clear')">Clear context</button>
      <button class="pill" onclick="sendCmd('${s.id}','/compact')">Compact</button>
      <button class="pill" onclick="resetSession('${s.id}')">Reset session</button>
      <button class="pill pill-danger" onclick="stopSession('${s.id}')">Stop session</button>
      <button class="pill pill-danger pill-ghost" style="font-size:0.72rem"
              onclick="removeSession('${s.id}')">Remove</button>
    `;
  } else {
    el.innerHTML = `
      <button class="pill pill-primary-filled" onclick="resetSession('${s.id}')">Start session</button>
      <button class="pill pill-danger pill-ghost" style="font-size:0.72rem"
              onclick="removeSession('${s.id}')">Remove</button>
    `;
  }
}

function openPanel(id) {
  const s = sessions.find(x => x.id === id);
  if (!s) return;
  selectedId = id;
  document.getElementById('panel-title').textContent   = s.name;
  document.getElementById('panel-subtitle').textContent = s.project;
  renderPanelActions(s);
  document.getElementById('pane-output').textContent = '…';
  document.getElementById('pane-output').classList.remove('pane-stopped');
  document.getElementById('detail-panel').classList.add('open');
  document.querySelectorAll('.session-card')
    .forEach(el => el.classList.toggle('selected', el.dataset.id === id));
  stopPanePolling();
  startPanePolling();
}

function closePanel() {
  selectedId = null;
  stopPanePolling();
  document.getElementById('detail-panel').classList.remove('open');
  document.querySelectorAll('.session-card').forEach(el => el.classList.remove('selected'));
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
    name:        fd.get('name'),
    project:     fd.get('project'),
    project_dir: fd.get('project_dir'),
    remote_control: false,
  });
  closeModal();
  await pollSessions();
}

// ── Init ─────────────────────────────────────────────────────────────────────
updateGrid(sessions);
gridTimer = setInterval(pollSessions, 4000);
</script>
{% endblock %}
```

- [ ] **Step 2: Rebuild and open the page**

```
cd C:\Server\projects\obsidian-capture
docker compose up --build -d
```

Wait ~15 seconds, then open `http://192.168.1.77:5009/agents`.

Verify:
- Cards render for all existing sessions (stopped sessions are expected)
- Each card shows name, project, health border, status badge, age
- No JS errors in browser console (`F12 → Console`)

- [ ] **Step 3: Verify card actions**

For a **stopped** session card:
- Click **Start** — card updates to active without page reload
- Click the card body — detail panel slides in from the right

For an **active** session card (start one if needed):
- Click **Stop** — card updates to stopped
- Click **RC: off** — toggles RC state on the card
- Click **Auto: off** — toggles auto state on the card

- [ ] **Step 4: Verify the detail panel**

Click any card body to open the panel. Verify:
- Panel slides in, header shows session name and project
- Pane output area shows terminal content (green text on black) or "session stopped"
- All action buttons render (Toggle RC, Toggle Auto, Clear context, Compact, Reset, Stop, Remove)
- Pulsing dot visible when session is active
- Command input: type `/clear` and press Enter — command is sent, input clears
- Click `×` — panel closes, selected ring disappears from card

- [ ] **Step 5: Verify the new session modal**

Click **+ New Session** in the header. Verify:
- Modal opens over a dark overlay
- Project dropdown auto-fills the dir field
- Click **Cancel** — modal closes
- Fill form and click **Start Session** — session appears in the card grid, modal closes

- [ ] **Step 6: Verify polling**

Open a session in another tab. Wait 4–5 seconds. The card grid on the agents page should update without a page reload.

- [ ] **Step 7: Commit**

```
cd C:\Server\projects\obsidian-capture
git add app/templates/agents.html
git commit -m "feat: redesign agents UI — card grid, slide-in panel, modal, live polling"
```

---

## Self-review checklist (for the plan author — do not skip)

- [x] Spec: pane endpoint → Task 1 ✓
- [x] Spec: proxy route → Task 2 ✓
- [x] Spec: CSS tokens (high-contrast, all named tokens) → Task 3 ✓
- [x] Spec: card grid with health border, status badge, activity pill, age → Task 4 ✓
- [x] Spec: panel with live pane output + actions + command input → Task 4 ✓
- [x] Spec: new session modal → Task 4 ✓
- [x] Spec: polling (4s grid, 2s pane) → Task 4 ✓
- [x] Spec: no `reload()` anywhere → Task 4 ✓
- [x] Spec: panel hidden on load, opens on card click → Task 4 ✓
- [x] Spec: RC/Auto duplication noted in panel → Task 4 ✓
- [x] Function names consistent: `resetSession` used in card footer (Start) and panel (Reset) ✓
- [x] `esc()` helper used for all user-provided strings in card HTML ✓
- [x] `pane-dot` visibility toggled correctly (style.visibility not display to avoid layout shift) ✓
