# IkeOS Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 open vault entries: revert CSS checkboxes to native HTML, add "+ New Item" button to the tasks page, cache `_read_hub_pages` in the vault graph, and fix 404 when clicking hub/component graph nodes.

**Architecture:** All changes are isolated to existing files. No new files needed. Tasks 1–2 and 4 are pure frontend (CSS/HTML/JS); Task 3 adds a server-side cache in `vault.py` matching the existing `_entries_cache` pattern.

**Tech Stack:** Flask, Jinja2, vanilla JS, pytest

**Assumptions:**
- "CSS version checkboxes" refers to the `type-chips` radio buttons in `capture.html` — they are hidden with `position: absolute; opacity: 0; pointer-events: none;` and replaced by styled labels, which is broken on mobile iOS.
- Hub nodes in graph.js should route to `/projects/<project>` on click; component nodes should be suppressed (no routable page exists).
- Tests run via: `./venv/bin/pytest tests/ -v` from project root.
- Container rebuild: `docker.exe compose build obsidian-capture && docker.exe compose up -d obsidian-capture`

---

### Task 1: Revert type-selector to native radio buttons

**Files:**
- Modify: `app/static/style.css` (lines 290–308, the `.type-chips` block)
- Modify: `app/templates/capture.html` (lines 37–45, the type field)

This removes the CSS-hidden radio + styled-label pattern and replaces it with visible native radio buttons.

- [ ] **Step 1: Remove the type-chips CSS block from style.css**

In `app/static/style.css`, replace lines 290–308:

```css
/* ── Type chip group (Phase 2) ───────────────────────────────────────────── */
.type-chips { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.type-chips input[type="radio"] { position: absolute; opacity: 0; pointer-events: none; }
.type-chip {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  border: 1px solid currentColor;
  font-size: var(--fs-body-sm);
  cursor: pointer;
  background: transparent;
  user-select: none;
  transition: background var(--dur-quick) var(--ease-out);
  display: inline-block;
}
.type-chip-note { color: var(--sem-knowledge); }
.type-chip-idea { color: var(--ike-soft-lavender); }
.type-chip-bug  { color: var(--sem-insight); }
.type-chips input:checked + .type-chip { background: color-mix(in srgb, currentColor 14%, transparent); }
.type-chips input:focus-visible + .type-chip { box-shadow: var(--ring-focus); }
```

with:

```css
/* ── Type radio group ────────────────────────────────────────────────────── */
.type-radios { display: flex; gap: var(--space-5); flex-wrap: wrap; }
.type-radio-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--fs-body-sm);
  cursor: pointer;
  color: var(--text-secondary);
}
.type-radio-label input[type="radio"] { accent-color: var(--brand-primary); width: 15px; height: 15px; cursor: pointer; }
```

- [ ] **Step 2: Update capture.html type field to use plain radio buttons**

In `app/templates/capture.html`, replace the type field block (lines 36–45):

```html
  <div class="field">
    <label class="ike-eyebrow" for="type-note">Type</label>
    <div class="type-chips" role="radiogroup">
      <input type="radio" name="type" id="type-note" value="note">
      <label class="type-chip type-chip-note" for="type-note">Note</label>
      <input type="radio" name="type" id="type-idea" value="idea" checked>
      <label class="type-chip type-chip-idea" for="type-idea">Feature Request</label>
      <input type="radio" name="type" id="type-bug" value="bug">
      <label class="type-chip type-chip-bug" for="type-bug">Bug</label>
    </div>
  </div>
```

with:

```html
  <div class="field">
    <label class="ike-eyebrow">Type</label>
    <div class="type-radios" role="radiogroup">
      <label class="type-radio-label"><input type="radio" name="type" id="type-note" value="note"> Note</label>
      <label class="type-radio-label"><input type="radio" name="type" id="type-idea" value="idea" checked> Feature Request</label>
      <label class="type-radio-label"><input type="radio" name="type" id="type-bug" value="bug"> Bug</label>
    </div>
  </div>
```

- [ ] **Step 3: Verify no other `.type-chip*` references remain**

```bash
grep -rn "type-chip" /mnt/c/Server/projects/ikeos/app/
```

Expected: no output (all references cleaned up).

- [ ] **Step 4: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/static/style.css app/templates/capture.html
git commit -m "fix: revert type selector to native radio buttons — CSS chips were unresponsive on mobile"
```

---

### Task 2: Add "+ New Item" button to tasks page header

**Files:**
- Modify: `app/templates/dashboard.html` (lines 8–16, the `<header>` block)

The tasks page (`/tasks`) shows the dashboard but has no quick-capture button. The project page already has this pattern. Mirror it in the dashboard header.

- [ ] **Step 1: Add the button to the page header in dashboard.html**

In `app/templates/dashboard.html`, replace the `<header>` block (lines 9–16):

```html
    <header class="page-header">
      <span class="ike-eyebrow">Tasks</span>
      <h1>Dashboard</h1>
      <p class="page-subtitle">
        {{ projects | length }} project{{ 's' if projects | length != 1 }} · {{ in_flight | length }} in flight · {{ needs_triage | length }} awaiting triage
      </p>
    </header>
```

with:

```html
    <header class="page-header">
      <span class="ike-eyebrow">Tasks</span>
      <div class="page-header-actions">
        <h1>Dashboard</h1>
        <a href="{{ url_for('capture.capture_form') }}" class="btn">+ New Item</a>
      </div>
      <p class="page-subtitle">
        {{ projects | length }} project{{ 's' if projects | length != 1 }} · {{ in_flight | length }} in flight · {{ needs_triage | length }} awaiting triage
      </p>
    </header>
```

- [ ] **Step 2: Verify the existing `.page-header-actions` CSS already styles this correctly**

```bash
grep -n "page-header-actions" /mnt/c/Server/projects/ikeos/app/static/style.css
```

Expected: shows `display: flex` or similar (it's already used in `project.html` which works).

- [ ] **Step 3: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/templates/dashboard.html
git commit -m "feat: add '+ New Item' button to tasks page header"
```

---

### Task 3: Cache `_read_hub_pages` in vault.py

**Files:**
- Modify: `app/services/vault.py` (globals block ~lines 12–29, `_invalidate_cache` ~line 24, `_read_hub_pages` ~line 117)
- Modify: `tests/test_vault.py` (add cache test)

`_read_hub_pages()` currently runs a full `iterdir` + `frontmatter.load` on every `/api/graph` call. WSL2 cross-filesystem I/O is ~20× slower than native Linux. Add a 600s TTL cache identical to the existing `_entries_cache` pattern.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_vault.py`:

```python
def test_read_hub_pages_uses_cache_on_second_call(tmp_path):
    proj_dir = tmp_path / "projects" / "myproject"
    proj_dir.mkdir(parents=True)
    hub_file = proj_dir / "MyProject.md"
    hub_file.write_text(
        "---\ntype: hub\ntitle: My Project\nproject: myproject\n---\n"
    )

    import time
    from unittest.mock import patch
    from app.services import vault as vault_mod

    vault_mod._hub_pages_cache = None
    vault_mod._hub_pages_cache_ts = 0.0

    with patch.object(vault_mod, "VAULT_PATH", tmp_path):
        call_count = 0
        original = vault_mod._read_hub_pages.__wrapped__ if hasattr(vault_mod._read_hub_pages, '__wrapped__') else None

        # Call twice; the filesystem should only be read once (cache hit on second)
        result1 = vault_mod._read_hub_pages()
        ts_after_first = vault_mod._hub_pages_cache_ts
        result2 = vault_mod._read_hub_pages()
        ts_after_second = vault_mod._hub_pages_cache_ts

    assert len(result1) == 1
    assert result1[0]["title"] == "My Project"
    assert result1 == result2
    assert ts_after_first == ts_after_second  # timestamp unchanged → cache was hit
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/c/Server/projects/ikeos && ./venv/bin/pytest tests/test_vault.py::test_read_hub_pages_uses_cache_on_second_call -v
```

Expected: FAIL with `AttributeError: module 'app.services.vault' has no attribute '_hub_pages_cache'`

- [ ] **Step 3: Add the cache globals to vault.py**

In `app/services/vault.py`, after the existing cache globals (after line 20 `_entries_cache_ts: float = 0.0`), add:

```python
_hub_pages_cache: list | None = None
_hub_pages_cache_ts: float = 0.0
```

- [ ] **Step 4: Update `_invalidate_cache` to clear the new cache**

In `app/services/vault.py`, replace `_invalidate_cache`:

```python
def _invalidate_cache() -> None:
    global _projects_cache, _projects_cache_ts, _entries_cache, _entries_cache_ts
    global _hub_pages_cache, _hub_pages_cache_ts
    _projects_cache = None
    _projects_cache_ts = 0.0
    _entries_cache = None
    _entries_cache_ts = 0.0
    _hub_pages_cache = None
    _hub_pages_cache_ts = 0.0
```

- [ ] **Step 5: Update `_read_hub_pages` to use the cache**

In `app/services/vault.py`, replace `_read_hub_pages`:

```python
def _read_hub_pages() -> list[dict]:
    """Read hub pages and component stubs (<proj>/components/*.md).
    Hub pages are discovered by type:hub frontmatter (filename = display name)."""
    global _hub_pages_cache, _hub_pages_cache_ts
    now = time.monotonic()
    if _hub_pages_cache is not None and (now - _hub_pages_cache_ts) < _TTL:
        return _hub_pages_cache

    pages = []
    projects_dir = VAULT_PATH / "projects"
    if not projects_dir.exists():
        _hub_pages_cache = pages
        _hub_pages_cache_ts = now
        return pages
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        # Hub page — scan top-level .md files for type:hub
        for candidate in proj_dir.glob("*.md"):
            if candidate.name == "project.md":
                continue
            try:
                post = frontmatter.load(candidate)
                if post.metadata.get("type") == "hub":
                    entry = dict(post.metadata)
                    entry["body"] = post.content
                    entry["slug"] = candidate.stem
                    pages.append(entry)
                    break
            except Exception:
                pass
        # Component stubs
        stubs_dir = proj_dir / "components"
        if stubs_dir.exists():
            for stub_file in stubs_dir.glob("*.md"):
                try:
                    post = frontmatter.load(stub_file)
                    entry = dict(post.metadata)
                    entry["body"] = post.content
                    entry["slug"] = stub_file.stem
                    pages.append(entry)
                except Exception:
                    pass
    _hub_pages_cache = pages
    _hub_pages_cache_ts = now
    return pages
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /mnt/c/Server/projects/ikeos && ./venv/bin/pytest tests/test_vault.py -v
```

Expected: all tests pass including the new cache test.

- [ ] **Step 7: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/services/vault.py tests/test_vault.py
git commit -m "perf: cache _read_hub_pages with 600s TTL — matches entries_cache pattern, fixes WSL2 graph slowness"
```

---

### Task 4: Fix graph 404 for hub and component node clicks

**Files:**
- Modify: `app/static/graph.js` (lines 14, `entryUrl` function; line 174, click handler)

When a hub or component node is clicked, `entryUrl(d)` returns `/projects/<project>/<slug>` which calls `read_entry()` — that only searches bugs/ideas/notes, so hub/component slugs return 404.

Fix: hub nodes route to `/projects/<project>`; component nodes suppress click (no routable page).

- [ ] **Step 1: Update `entryUrl` and the click handler in graph.js**

In `app/static/graph.js`, replace `entryUrl` (line 14):

```javascript
function entryUrl(d) { return '/projects/' + d.project + '/' + d.id; }
```

with:

```javascript
function entryUrl(d) {
    if (d.type === 'hub') return '/projects/' + d.project;
    if (d.type === 'component') return null;
    return '/projects/' + d.project + '/' + d.id;
}
```

Then update the click handler (line 174). Replace:

```javascript
      .on('click', function (event, d) { window.location.href = entryUrl(d); })
```

with:

```javascript
      .on('click', function (event, d) { var url = entryUrl(d); if (url) window.location.href = url; })
```

- [ ] **Step 2: Verify the change is correct**

```bash
grep -n "entryUrl\|on('click'" /mnt/c/Server/projects/ikeos/app/static/graph.js
```

Expected output shows the updated `entryUrl` function with the hub/component branches and the null-guarded click handler.

- [ ] **Step 3: Commit**

```bash
cd /mnt/c/Server/projects/ikeos
git add app/static/graph.js
git commit -m "fix: hub nodes route to /projects/<project>, component node clicks suppressed"
```

---

### Task 5: Rebuild container and verify

- [ ] **Step 1: Run the full test suite**

```bash
cd /mnt/c/Server/projects/ikeos && ./venv/bin/pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Rebuild and restart the container**

```bash
cd /mnt/c/Server/projects/ikeos && docker.exe compose build obsidian-capture && docker.exe compose up -d obsidian-capture
```

- [ ] **Step 3: Confirm container is healthy**

```bash
docker.exe compose logs obsidian-capture --tail=20
```

Expected: no errors, `Listening on port 5009`.

- [ ] **Step 4: Smoke-check each change**

- Visit `http://homeautomation:5009/capture` — confirm Type field shows native radio buttons (Note, Feature Request, Bug) instead of chip buttons.
- Visit `http://homeautomation:5009/tasks` — confirm "+ New Item" link appears in header.
- Visit `http://homeautomation:5009/graph` — click a hub node (e.g. "IkeOS"), confirm it routes to `/projects/ikeos` (no 404). Click a component node, confirm no navigation.
- Reload `/graph` twice quickly — should be noticeably fast on second load (cache hit).

- [ ] **Step 5: Close vault entries**

Mark all 4 vault entries as done via PATCH:

```bash
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=bug" \
  -d "filename=2026-06-13-checkboxes-still-are-broken-in-ikeos" -d "status=done"

curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=idea" \
  -d "filename=2026-06-13-add-new-item-button-at-top-of-tasks-page" -d "status=done"

curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=idea" \
  -d "filename=2026-06-13-cache-read-hub-pages-in-vault-graph-currently-unca" -d "status=done"

curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=bug" \
  -d "filename=2026-06-13-hub-and-component-nodes-in-graph-view-404-on-click" -d "status=done"
```
