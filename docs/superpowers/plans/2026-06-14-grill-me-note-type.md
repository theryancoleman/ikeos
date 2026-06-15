# Grill Me Note Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Grill Me" capture type to Obsidian Capture — a new vault folder for capturing half-formed ideas that need further exploration, with full UI, API, and triage support.

**Architecture:** `grill-me` is a first-class entry type stored in a dedicated `grill-me/` folder alongside `bugs/`, `ideas/`, `notes/`. The vault service, PATCH endpoint, JSON API, and capture form are each updated independently. A capture API ticket is filed to claude-config at the end, requesting /triage be updated to surface grill-me items.

**Tech Stack:** Python 3.11, Flask, python-frontmatter, Jinja2, pytest

---

## File Map

| File | Change |
|---|---|
| `app/services/vault.py` | Add `grill-me` to `VALID_TYPES`, `TYPE_FOLDERS`, `TYPE_TAGS`; scan `grill-me/` in `_read_all_entries()`; handle `grill-me` path in `update_entry_status_generic()` |
| `app/routes/capture.py` | Accept `grill-me` in `patch_entries()` type validation and `capture_json()` type check |
| `app/templates/capture.html` | Add "Grill Me" radio button option |
| `tests/test_vault.py` | Add 2 tests for grill-me write and read |
| `tests/test_capture.py` | Add 2 tests for grill-me PATCH and JSON API |

---

### Task 1: vault.py — register grill-me type and folder

**Files:**
- Modify: `app/services/vault.py:42-46`
- Modify: `app/services/vault.py:383-403` (`_read_all_entries`)
- Modify: `app/services/vault.py:461-486` (`update_entry_status_generic`)
- Test: `tests/test_vault.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_vault.py`:

```python
def test_write_entry_creates_grill_me_in_correct_folder(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({"type": "grill-me", "project": "bcr-waivers", "title": "Half baked idea", "body": "Not sure yet"})

    files = list((vault / "projects" / "bcr-waivers" / "grill-me").glob("*.md"))
    assert len(files) == 1
    import frontmatter as fm
    post = fm.load(files[0])
    assert post.metadata["type"] == "grill-me"
    assert post.metadata["status"] == "new"


def test_read_entries_includes_grill_me_folder(vault):
    grill_dir = vault / "projects" / "bcr-waivers" / "grill-me"
    grill_dir.mkdir(parents=True)
    (grill_dir / "2026-06-14-half-formed.md").write_text(
        "---\ntype: grill-me\ntitle: Half formed\nproject: bcr-waivers\nstatus: new\n"
        "created: 2026-06-14T10:00:00\ntags: [grill-me]\n---\n## Description\nNeeds work\n"
    )
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entries, _invalidate_cache
        _invalidate_cache()
        entries = read_entries(project="bcr-waivers")
    assert any(e["type"] == "grill-me" for e in entries)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_vault.py::test_write_entry_creates_grill_me_in_correct_folder tests/test_vault.py::test_read_entries_includes_grill_me_folder -v
```

Expected: FAIL — `KeyError: 'grill-me'` on TYPE_FOLDERS lookup.

- [ ] **Step 3: Update the constants in vault.py**

In `app/services/vault.py`, update lines 42–46:

```python
VALID_TYPES = {"note", "idea", "bug", "decision", "grill-me"}
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs", "grill-me": "grill-me"}
TYPE_TAGS = {"note": "documentation", "idea": "enhancement", "bug": "bug", "decision": "decision", "grill-me": "grill-me"}
```

- [ ] **Step 4: Update `_read_all_entries` to scan the grill-me folder**

In `app/services/vault.py`, find `_read_all_entries` (currently scans `("bugs", "ideas", "notes")`). Change the tuple:

```python
def _read_all_entries() -> list[dict]:
    """Read and parse every entry file in the vault. Result is cached by callers."""
    entries = []
    for proj in get_projects():
        proj_dir = VAULT_PATH / "projects" / proj
        for folder in ("bugs", "ideas", "notes", "grill-me"):
            type_dir = proj_dir / folder
            if not type_dir.exists():
                continue
            for filepath in type_dir.glob("*.md"):
                try:
                    post = frontmatter.load(filepath)
                    entry = dict(post.metadata)
                    if hasattr(entry.get("created"), "isoformat"):
                        entry["created"] = entry["created"].isoformat(timespec="seconds")
                    entry["body"] = post.content
                    entry["slug"] = filepath.stem
                    entries.append(entry)
                except Exception:
                    continue
    entries.sort(key=lambda e: e.get("created", ""), reverse=True)
    return entries
```

- [ ] **Step 5: Update `update_entry_status_generic` to handle grill-me path**

In `app/services/vault.py`, find `update_entry_status_generic`. Add the `grill-me` branch alongside `bug`, `idea`, `note`:

```python
def update_entry_status_generic(entry_type: str, project: str | None, filename: str, new_status: str) -> bool:
    """Update status for any entry type (task or decision), with byte-identical body preservation."""
    if entry_type == "decision":
        if new_status not in DECISION_STATUSES:
            return False
        base_path = VAULT_PATH / "decisions"
    else:
        if new_status not in VALID_STATUSES:
            return False
        if not project:
            return False
        if entry_type == "bug":
            base_path = VAULT_PATH / "projects" / project / "bugs"
        elif entry_type == "idea":
            base_path = VAULT_PATH / "projects" / project / "ideas"
        elif entry_type == "note":
            base_path = VAULT_PATH / "projects" / project / "notes"
        elif entry_type == "grill-me":
            base_path = VAULT_PATH / "projects" / project / "grill-me"
        else:
            return False

    if filename.endswith(".md"):
        filepath = base_path / filename
    else:
        filepath = base_path / f"{filename}.md"

    if not filepath.exists():
        return False

    try:
        post = frontmatter.load(filepath)
        post.metadata["status"] = new_status
        post.metadata["updated"] = datetime.now().isoformat(timespec="seconds")

        tags = [t for t in post.metadata.get("tags", []) if not t.startswith("status/") and not t.startswith("decision/")]
        tags.append(f"status/{new_status}")
        post.metadata["tags"] = tags

        temp_filepath = filepath.with_suffix(".md.tmp")
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        temp_filepath.replace(filepath)

        _invalidate_cache()
        return True
    except Exception:
        return False
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_vault.py::test_write_entry_creates_grill_me_in_correct_folder tests/test_vault.py::test_read_entries_includes_grill_me_folder -v
```

Expected: PASS

- [ ] **Step 7: Run the full test suite to check for regressions**

```bash
python3 -m pytest tests/test_vault.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: register grill-me type in vault — folder, constants, read/update support"
```

---

### Task 2: capture.py — accept grill-me in PATCH and JSON endpoints

**Files:**
- Modify: `app/routes/capture.py:105` (PATCH endpoint type validation)
- Modify: `app/routes/capture.py:142` (capture_json type validation)
- Test: `tests/test_capture.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/test_capture.py`. Add these two tests (place them near the existing PATCH and JSON tests respectively):

```python
def test_patch_entries_accepts_grill_me_type(client, tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("CAPTURE_TOKEN", "testtoken")
    grill_dir = tmp_path / "projects" / "bcr-waivers" / "grill-me"
    grill_dir.mkdir(parents=True)
    (grill_dir / "2026-06-14-test-grill.md").write_text(
        "---\ntype: grill-me\ntitle: Test Grill\nproject: bcr-waivers\nstatus: new\n"
        "created: 2026-06-14T10:00:00\ntags: [grill-me, status/new]\n---\n## Description\ntest\n"
    )
    import urllib.request as _ur
    import app.services.vault as vault_mod
    monkeypatch.setattr(vault_mod, "VAULT_PATH", tmp_path)
    resp = client.patch(
        "/entries",
        data={"project": "bcr-waivers", "type": "grill-me", "filename": "2026-06-14-test-grill", "status": "open"},
        headers={"X-Capture-Token": "testtoken"},
    )
    assert resp.status_code == 200


def test_capture_json_accepts_grill_me_type(client, tmp_path, monkeypatch):
    import app.services.vault as vault_mod
    monkeypatch.setattr(vault_mod, "VAULT_PATH", tmp_path)
    (tmp_path / "projects" / "bcr-waivers").mkdir(parents=True)
    resp = client.post(
        "/capture/json",
        json={"type": "grill-me", "project": "bcr-waivers", "title": "Half baked"},
    )
    assert resp.status_code == 200
    files = list((tmp_path / "projects" / "bcr-waivers" / "grill-me").glob("*.md"))
    assert len(files) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_capture.py::test_patch_entries_accepts_grill_me_type tests/test_capture.py::test_capture_json_accepts_grill_me_type -v
```

Expected: FAIL — `400 Invalid entry type` for PATCH; `400 type must be note, idea, or bug` for JSON.

- [ ] **Step 3: Update PATCH endpoint type validation in capture.py**

In `app/routes/capture.py`, find line ~105 inside `patch_entries()`:

```python
    # Validate entry_type
    if entry_type not in ("bug", "idea", "note", "decision", "grill-me"):
        return jsonify({"error": "Invalid entry type"}), 400
```

- [ ] **Step 4: Update capture_json type validation in capture.py**

In `app/routes/capture.py`, find line ~142 inside `capture_json()`:

```python
    if entry_type not in ("note", "idea", "bug", "grill-me"):
        return jsonify({"error": "type must be note, idea, bug, or grill-me"}), 400
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_capture.py::test_patch_entries_accepts_grill_me_type tests/test_capture.py::test_capture_json_accepts_grill_me_type -v
```

Expected: PASS

- [ ] **Step 6: Run the full capture test suite**

```bash
python3 -m pytest tests/test_capture.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add app/routes/capture.py tests/test_capture.py
git commit -m "feat: accept grill-me type in PATCH /entries and POST /capture/json"
```

---

### Task 3: capture.html — add Grill Me radio button

**Files:**
- Modify: `app/templates/capture.html:37-41`

No new tests for template rendering — the form is exercised by the existing submit tests.

- [ ] **Step 1: Add the radio button**

In `app/templates/capture.html`, find the `type-radios` div (currently has Note, Feature Request, Bug). Add "Grill Me" after Bug:

```html
  <div class="field">
    <label class="ike-eyebrow" id="type-group-label">Type</label>
    <div class="type-radios" role="radiogroup" aria-labelledby="type-group-label">
      <label class="type-radio-label"><input type="radio" name="type" id="type-note" value="note"> Note</label>
      <label class="type-radio-label"><input type="radio" name="type" id="type-idea" value="idea" checked> Feature Request</label>
      <label class="type-radio-label"><input type="radio" name="type" id="type-bug" value="bug"> Bug</label>
      <label class="type-radio-label"><input type="radio" name="type" id="type-grill-me" value="grill-me"> Grill Me</label>
    </div>
  </div>
```

Grill Me has no conditional extra fields (no priority/effort/severity). The existing `updateFields` JS already handles this — it only shows `idea-fields` for `idea` and `bug-fields` for `bug`; any other type hides both, which is correct.

- [ ] **Step 2: Verify in browser**

Open `http://homeautomation:5009/capture`. You should see four radio options: Note, Feature Request, Bug, Grill Me. Selecting "Grill Me" shows no extra fields (title + description only). Submit a test entry and confirm the file lands in the vault at `/mnt/c/Server/obsidian-vault/projects/<project>/grill-me/`.

```bash
ls /mnt/c/Server/obsidian-vault/projects/ikeos/grill-me/ 2>/dev/null || echo "folder does not exist yet (will be created on first write)"
```

- [ ] **Step 3: Commit**

```bash
git add app/templates/capture.html
git commit -m "feat: add Grill Me radio button to capture form"
```

---

### Task 4: Rebuild bundle.css and redeploy

Static files are baked into the Docker image at build time. Template changes go into the image via `COPY . .`. The CSS bundle must also be rebuilt.

- [ ] **Step 1: Rebuild bundle.css**

```bash
python3 scripts/bundle_css.py
```

Expected output: `bundle.css written (NNN bytes, 9 files inlined)`

- [ ] **Step 2: Rebuild and restart the container**

```bash
docker.exe compose up --build -d
```

Expected: container recreated and started.

- [ ] **Step 3: Smoke-test the live app**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5009/capture
```

Expected: `200`

- [ ] **Step 4: Commit**

```bash
git add app/static/bundle.css
git commit -m "chore: rebuild bundle.css after grill-me feature"
```

---

### Task 5: File a ticket to claude-config to update /triage

The `/triage` skill instruction currently mentions `bugs/*.md`, `ideas/*.md`, and `notes/*.md`. It needs to also scan `grill-me/*.md` and, when an agent starts work on a grill-me entry, invoke `/grill-me` to interview the user for more detail.

- [ ] **Step 1: File the ticket via the capture API**

```bash
TOKEN=$(grep CAPTURE_TOKEN /mnt/c/Server/projects/ikeos/.env | cut -d= -f2 | tr -d '\r\n')
python3 -c "
import urllib.request, urllib.parse
token = '$TOKEN'
title = 'Update /triage to scan grill-me folder and invoke /grill-me skill'
body = '''The triage instruction currently scans bugs/, ideas/, notes/ for status:new entries.

Requested changes:
1. Also scan projects/<project>/grill-me/*.md for status:new entries.
2. In the triage summary, label these entries as type \"grill-me\" and urgency score them like notes (score 5).
3. Add a note in the per-task guidance: when an agent starts working on a grill-me entry, it must invoke the /grill-me skill to interview the user and flesh out the idea before implementing anything.'''
data = urllib.parse.urlencode({
    'type': 'idea',
    'project': 'claude-config',
    'title': title,
    'body': body,
    'priority': 'medium',
    'effort': 'small',
}).encode()
req = urllib.request.Request('http://localhost:5009/capture', data=data, method='POST')
resp = urllib.request.urlopen(req)
print('OK', resp.status)
"
```

Expected: `OK 200` (or redirect 302 — both mean the entry was written).

- [ ] **Step 2: Verify the ticket was created**

```bash
ls /mnt/c/Server/obsidian-vault/projects/claude-config/ideas/ | grep triage
```

Expected: a file like `2026-06-14-update-triage-to-scan-grill-me-folder*.md` is present.
