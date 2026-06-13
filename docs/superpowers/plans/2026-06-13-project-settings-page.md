# Project Settings Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/settings` page to obsidian-capture that lists every vault project with its slug, display name, description, and hidden flag — all editable inline — and expose a POST endpoint to persist changes to `project.md`.

**Architecture:** `vault.py` gets a `write_project_meta` function (mirroring `_read_project_meta`) plus a `description` field threaded through `get_projects_with_meta`. `browse.py` gets two new routes: `GET /settings` and `POST /projects/<slug>/settings`. The page renders one form-per-project using the existing ikeOS design system; save is a standard form POST with redirect and flash. No AJAX — consistent with the app's existing patterns.

**Tech Stack:** Python Flask, Jinja2, python-frontmatter, vanilla HTML/CSS, pytest. Docker container at port 5009 has read-write vault mount (`/vault`).

---

## Repos and Key Paths

| File | Role |
|------|------|
| `app/services/vault.py` | All vault I/O — add `write_project_meta`, extend `_read_project_meta` + `get_projects_with_meta` |
| `app/routes/browse.py` | Add `GET /settings` and `POST /projects/<slug>/settings` |
| `app/templates/settings.html` | New settings page template |
| `app/templates/base.html` | Add "Settings" nav link |
| `app/static/style.css` | Add settings page styles |
| `tests/test_vault.py` | Tests for new vault functions |
| `tests/test_browse.py` | Tests for new settings routes |

## How to run tests

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/ -v
```

## Rebuild after changes

```bash
cd /mnt/c/Server/projects/obsidian-capture
docker.exe compose up --build -d
```

---

## Task 1: Extend vault.py — description field + write_project_meta

**Files:**
- Modify: `app/services/vault.py`
- Modify: `tests/test_vault.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_vault.py`:

```python
from app.services.vault import write_project_meta


def test_read_project_meta_returns_description(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text(
        "---\nname: My Project\ndescription: A test project\nhidden: false\n---\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("my-project")
    assert meta["description"] == "A test project"


def test_read_project_meta_description_defaults_to_empty(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text("---\nname: My Project\nhidden: false\n---\n")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("my-project")
    assert meta["description"] == ""


def test_write_project_meta_creates_project_md(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        result = write_project_meta("my-project", "My Project", "A description", False)
    assert result is True
    meta_file = proj / "project.md"
    assert meta_file.exists()
    post = fm.load(meta_file)
    assert post.metadata["name"] == "My Project"
    assert post.metadata["description"] == "A description"
    assert post.metadata["hidden"] is False


def test_write_project_meta_updates_existing(tmp_path):
    proj = tmp_path / "projects" / "my-project"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text("---\nname: Old Name\nhidden: false\n---\n")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        write_project_meta("my-project", "New Name", "Updated desc", True)
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("my-project")
    assert meta["name"] == "New Name"
    assert meta["description"] == "Updated desc"
    assert meta["hidden"] is True


def test_write_project_meta_returns_false_for_missing_slug(tmp_path):
    (tmp_path / "projects").mkdir(parents=True)
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        result = write_project_meta("nonexistent", "Name", "", False)
    assert result is False


def test_get_projects_with_meta_includes_hidden_when_requested(tmp_path):
    for slug, name, hidden in [("visible", "Visible", False), ("hidden-one", "Hidden", True)]:
        d = tmp_path / "projects" / slug
        d.mkdir(parents=True)
        (d / "project.md").write_text(
            f"---\nname: {name}\nhidden: {str(hidden).lower()}\n---\n"
        )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_projects_with_meta
        visible_only = get_projects_with_meta(include_hidden=False)
        all_projects = get_projects_with_meta(include_hidden=True)
    assert len(visible_only) == 1
    assert visible_only[0]["slug"] == "visible"
    assert len(all_projects) == 2
```

- [ ] **Step 2: Run tests — they must fail**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/test_vault.py::test_write_project_meta_creates_project_md -v
```

Expected: `ImportError: cannot import name 'write_project_meta'`

- [ ] **Step 3: Update `_read_project_meta` to include description**

In `app/services/vault.py`, replace the `_read_project_meta` function (lines 38–49):

```python
def _read_project_meta(slug: str) -> dict:
    meta_file = VAULT_PATH / "projects" / slug / "project.md"
    if not meta_file.exists():
        return {"name": slug, "description": "", "hidden": False}
    try:
        post = frontmatter.load(meta_file)
        return {
            "name": post.metadata.get("name", slug),
            "description": post.metadata.get("description", ""),
            "hidden": bool(post.metadata.get("hidden", False)),
        }
    except Exception:
        return {"name": slug, "description": "", "hidden": False}
```

- [ ] **Step 4: Add `include_hidden` parameter to `get_projects_with_meta`**

In `app/services/vault.py`, replace the `get_projects_with_meta` function (lines 59–76):

```python
def get_projects_with_meta(include_hidden: bool = False) -> list[dict]:
    global _projects_cache, _projects_cache_ts
    now = time.monotonic()
    if _projects_cache is not None and (now - _projects_cache_ts) < _TTL:
        cached = _projects_cache
    else:
        projects_dir = VAULT_PATH / "projects"
        if not projects_dir.exists():
            return []
        cached = []
        for d in sorted(projects_dir.iterdir()):
            if not d.is_dir():
                continue
            meta = _read_project_meta(d.name)
            cached.append({
                "slug": d.name,
                "name": meta["name"],
                "description": meta["description"],
                "hidden": meta["hidden"],
            })
        _projects_cache = cached
        _projects_cache_ts = now
    if include_hidden:
        return cached
    return [p for p in cached if not p["hidden"]]
```

- [ ] **Step 5: Add `write_project_meta` function**

In `app/services/vault.py`, add this function after `get_projects_with_meta`:

```python
def write_project_meta(slug: str, name: str, description: str, hidden: bool) -> bool:
    """Write or overwrite project.md for the given slug."""
    proj_dir = VAULT_PATH / "projects" / slug
    if not proj_dir.exists():
        return False
    meta_file = proj_dir / "project.md"
    post = frontmatter.Post("", name=name, description=description, hidden=hidden)
    with open(meta_file, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()
    return True
```

- [ ] **Step 6: Run all vault tests**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/test_vault.py -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
cd /mnt/c/Server/projects/obsidian-capture
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: add description field and write_project_meta to vault service"
```

---

## Task 2: Settings routes in browse.py

**Files:**
- Modify: `app/routes/browse.py`
- Modify: `tests/test_browse.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_browse.py`:

```python
from app.services.vault import write_project_meta


@pytest.fixture
def vault_with_projects(tmp_path):
    for slug, name in [("alpha", "Alpha Project"), ("beta", "Beta Project")]:
        d = tmp_path / "projects" / slug
        d.mkdir(parents=True)
        (d / "project.md").write_text(
            f"---\nname: {name}\ndescription: \nhidden: false\n---\n"
        )
    return tmp_path


@pytest.fixture
def settings_client(vault_with_projects):
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    app = create_app()
    app.config["TESTING"] = True
    with patch("app.services.vault.VAULT_PATH", vault_with_projects):
        with app.test_client() as c:
            yield c, vault_with_projects


def test_settings_page_renders(settings_client):
    client, _ = settings_client
    with patch("app.services.vault.VAULT_PATH", _):
        resp = client.get("/settings")
    assert resp.status_code == 200
    assert b"Alpha Project" in resp.data
    assert b"Beta Project" in resp.data


def test_settings_page_shows_slugs(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        resp = client.get("/settings")
    assert b"alpha" in resp.data
    assert b"beta" in resp.data


def test_update_project_settings_redirects(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        resp = client.post(
            "/projects/alpha/settings",
            data={"name": "Alpha Renamed", "description": "A desc", "hidden": ""},
            follow_redirects=False,
        )
    assert resp.status_code == 302


def test_update_project_settings_persists(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        client.post(
            "/projects/alpha/settings",
            data={"name": "Alpha Renamed", "description": "A new desc", "hidden": ""},
        )
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("alpha")
    assert meta["name"] == "Alpha Renamed"
    assert meta["description"] == "A new desc"
    assert meta["hidden"] is False


def test_update_project_settings_hidden_toggle(settings_client):
    client, vault = settings_client
    with patch("app.services.vault.VAULT_PATH", vault):
        client.post(
            "/projects/alpha/settings",
            data={"name": "Alpha", "description": "", "hidden": "on"},
        )
        from app.services.vault import _read_project_meta
        meta = _read_project_meta("alpha")
    assert meta["hidden"] is True
```

- [ ] **Step 2: Run tests — must fail**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/test_browse.py::test_settings_page_renders -v
```

Expected: 404 (route not defined)

- [ ] **Step 3: Add settings routes to browse.py**

At the top of `app/routes/browse.py`, update the import from vault:

```python
from app.services.vault import (
    get_projects_with_meta, read_entries, read_entry,
    update_entry_status, _read_project_meta, write_project_meta,
)
```

Append the two new routes at the end of `app/routes/browse.py`:

```python
@bp.route("/settings")
def settings():
    projects = get_projects_with_meta(include_hidden=True)
    return render_template("settings.html", projects=projects)


@bp.route("/projects/<slug>/settings", methods=["POST"])
def update_project_settings(slug):
    name = request.form.get("name", "").strip() or slug
    description = request.form.get("description", "").strip()
    hidden = request.form.get("hidden") == "on"
    write_project_meta(slug, name, description, hidden)
    flash(f"'{name}' settings saved.")
    return redirect(url_for("browse.settings"))
```

- [ ] **Step 4: Run browse tests**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/test_browse.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes/browse.py tests/test_browse.py
git commit -m "feat: add GET /settings and POST /projects/<slug>/settings routes"
```

---

## Task 3: Settings template + nav link + CSS

**Files:**
- Create: `app/templates/settings.html`
- Modify: `app/templates/base.html`
- Modify: `app/static/style.css`

- [ ] **Step 1: Create `app/templates/settings.html`**

```html
{% extends "base.html" %}
{% block title %}Settings{% endblock %}

{% block content %}
<div class="settings-page">

  <header class="page-header">
    <span class="ike-eyebrow">Configuration</span>
    <h1>Project Settings</h1>
    <p class="page-subtitle">Manage display names, descriptions, and visibility for each vault project. Slugs are read-only — they match the vault folder name.</p>
  </header>

  <div class="settings-table-wrap">
    <table class="settings-table">
      <thead>
        <tr>
          <th>Slug</th>
          <th>Display Name</th>
          <th>Description</th>
          <th>Hidden</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for p in projects %}
        <tr class="settings-row{% if p.hidden %} settings-row-hidden{% endif %}">
          <form method="POST" action="{{ url_for('browse.update_project_settings', slug=p.slug) }}">
            <td class="st-slug"><code>{{ p.slug }}</code></td>
            <td class="st-name">
              <input type="text" name="name" value="{{ p.name }}"
                     class="settings-input" required autocomplete="off">
            </td>
            <td class="st-desc">
              <input type="text" name="description" value="{{ p.description or '' }}"
                     class="settings-input" placeholder="Optional description…" autocomplete="off">
            </td>
            <td class="st-hidden">
              <label class="settings-toggle" title="Hide from nav and dropdowns">
                <input type="checkbox" name="hidden" {% if p.hidden %}checked{% endif %}>
                <span class="toggle-label">Hidden</span>
              </label>
            </td>
            <td class="st-action">
              <button type="submit" class="pill pill-primary">Save</button>
            </td>
          </form>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Add Settings nav link to `app/templates/base.html`**

Find the line:
```html
      <a href="{{ url_for('agents.status_page') }}" class="nav-link {% if request.endpoint == 'agents.status_page' %}is-active{% endif %}">Status</a>
```

Add after it:
```html
      <a href="{{ url_for('browse.settings') }}" class="nav-link {% if request.endpoint == 'browse.settings' or request.endpoint == 'browse.update_project_settings' %}is-active{% endif %}">Settings</a>
```

- [ ] **Step 3: Add settings CSS to `app/static/style.css`**

Append to `app/static/style.css`:

```css
/* ── Settings page ── */
.settings-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 2.5rem;
}

.settings-page .page-subtitle {
  font-size: 0.85rem;
  color: #999;
  margin-top: 0.4rem;
}

.settings-table-wrap {
  overflow-x: auto;
  margin-top: 1.5rem;
}

.settings-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.settings-table th {
  text-align: left;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #888;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #333;
  white-space: nowrap;
}

.settings-table td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #222;
  vertical-align: middle;
}

.settings-row-hidden .st-slug code,
.settings-row-hidden .st-name input,
.settings-row-hidden .st-desc input {
  opacity: 0.45;
}

.st-slug code {
  font-family: ui-monospace, monospace;
  font-size: 0.78rem;
  color: #aaa;
  background: #1a1a1a;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
}

.settings-input {
  width: 100%;
  background: transparent;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 0.3rem 0.5rem;
  color: inherit;
  font-size: 0.85rem;
  font-family: inherit;
  transition: border-color 0.15s;
}

.settings-input:focus {
  outline: none;
  border-color: #555;
  background: #111;
}

.settings-toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
  font-size: 0.8rem;
  color: #888;
  white-space: nowrap;
}

.settings-toggle input[type="checkbox"] {
  accent-color: #5865f2;
  width: 14px;
  height: 14px;
}

.st-action { white-space: nowrap; }
```

- [ ] **Step 4: Rebuild and verify**

```bash
cd /mnt/c/Server/projects/obsidian-capture
docker.exe compose up --build -d
```

Open `http://192.168.1.77:5009/settings` in a browser. Confirm:
- "Settings" link appears in the top nav (active when on the page)
- All vault projects are listed including hidden ones (greyed out)
- Each row shows the slug (monospace, read-only), an editable name input, a description input, and a Hidden checkbox
- Clicking Save on any row redirects back to /settings with a flash message
- After saving, the updated name appears in the row

- [ ] **Step 5: Run full test suite**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/templates/settings.html app/templates/base.html app/static/style.css
git commit -m "feat: project settings page — edit name, description, and hidden flag per project"
```

---

## Task 4: Post-deploy — create claude-config project.md

The `claude-config` project has no `project.md`, so it shows as the raw slug in all dropdowns. Use the new settings API after deploying to fix this and correct any other outdated names.

- [ ] **Step 1: Set claude-config display name via settings page**

Open `http://192.168.1.77:5009/settings` in a browser. Find the `claude-config` row. Set:
- Name: `Claude Config`
- Description: `Superpowers harness, global settings, session manager`
- Hidden: unchecked

Click Save.

Also review and correct any other stale names visible on the page (e.g. `claude-code` is currently named "Claude Config Mgr" which conflicts with the above).

- [ ] **Step 2: Verify in Capture dropdown**

Open `http://192.168.1.77:5009/capture`. The project dropdown should show "Claude Config" for the `claude-config` slug.

- [ ] **Step 3: Close vault entry**

Mark the "Project Name cleanup" idea as done:

```bash
curl -s -o /dev/null -w "%{http_code}" -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=claude-config" \
  -d "type=idea" \
  -d "filename=2026-06-11-project-name-cleanup" \
  -d "status=done"
```

---

## Deferred: Slug rename

Renaming vault folder slugs (e.g. `frc-dashboard` → `pitradar`) would require moving the directory and rewriting all entry `project:` frontmatter fields — too risky without a migration script. Deferred to a future plan. The display name fix in Task 4 handles the visible impact for now.
