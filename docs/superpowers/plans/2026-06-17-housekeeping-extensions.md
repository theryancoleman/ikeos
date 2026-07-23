# Obsidian-Capture Housekeeping Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend obsidian-capture to support `housekeeping-task` and `housekeeping-heartbeat` vault entry types, and add a `PATCH /entries/housekeeping` endpoint for writing runtime state fields.

**Architecture:** Two vault service functions handle the new types in `write_entry()` and a new `update_housekeeping_fields()` updates runtime state. A new route mirrors the existing `PATCH /entries` pattern but accepts a `fields` dict instead of a status string. The `housekeeping-heartbeat` type is a singleton: always written to `last-run.md` (no date prefix), overwriting in-place.

**Tech Stack:** Python 3.11, Flask, python-frontmatter, pytest

**Spec:** `docs/superpowers/specs/2026-06-17-housekeeping-design.md` (in ikeos repo)

---

## Files

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/services/vault.py` | Add `write_entry` support for new types; add `update_housekeeping_fields()` |
| Modify | `app/routes/capture.py` | Extend `capture_json()` for `housekeeping-task`; add `PATCH /entries/housekeeping` |
| Modify | `tests/test_vault.py` | Tests for new vault functions |
| Modify | `tests/test_capture.py` | Tests for new route and extended capture_json |

---

### Task 1: vault — write_entry for housekeeping-task

**Files:**
- Modify: `tests/test_vault.py`
- Modify: `app/services/vault.py`

- [ ] **Step 1.1: Write the failing tests**

Append to `tests/test_vault.py`:

```python
# ============= housekeeping-task write tests =============

def test_write_entry_housekeeping_task_creates_file_in_housekeeping_folder(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Prune stale entries",
            "body": "Run the pruner.",
            "interval": "weekly",
            "success_definition": "No entries older than 90 days remain.",
        })
    files = list((vault / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    assert len(files) == 1
    assert slug in files[0].name


def test_write_entry_housekeeping_task_frontmatter(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Prune vault",
            "body": "",
            "interval": "monthly",
            "success_definition": "Done.",
        })
    files = list((vault / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["type"] == "housekeeping-task"
    assert post.metadata["interval"] == "monthly"
    assert post.metadata["enabled"] == "true"
    assert post.metadata["last_run"] == "null"
    assert post.metadata["last_error"] == "null"
    assert post.metadata["consecutive_failures"] == "0"
    assert "housekeeping-task" in post.metadata["tags"]
    assert "status/enabled" in post.metadata["tags"]
    assert "claude-config" in post.metadata["tags"]
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /mnt/c/Server/projects/obsidian-capture
docker.exe compose exec obsidian-capture pytest tests/test_vault.py::test_write_entry_housekeeping_task_creates_file_in_housekeeping_folder tests/test_vault.py::test_write_entry_housekeeping_task_frontmatter -v
```

Expected: FAIL with `KeyError` or similar (type not handled)

- [ ] **Step 1.3: Add `write_entry` support for housekeeping-task in `app/services/vault.py`**

In `write_entry()`, add a new branch after the `decision` branch (before the final `else`/default handling). Also add `"housekeeping-task"` to `VALID_TYPES`:

```python
VALID_TYPES = {"note", "idea", "bug", "decision", "housekeeping-task", "housekeeping-heartbeat"}
```

Add this branch in `write_entry()` after the `decision` block:

```python
elif entry_type == "housekeeping-task":
    project = data.get("project", "")
    target_dir = VAULT_PATH / "projects" / project / "housekeeping"
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "title": title,
        "type": "housekeeping-task",
        "project": project,
        "interval": data.get("interval", "weekly"),
        "enabled": "true",
        "success_definition": data.get("success_definition", ""),
        "last_run": "null",
        "last_error": "null",
        "consecutive_failures": "0",
        "created": datetime.now().isoformat(timespec="seconds"),
        "tags": ["housekeeping-task", project, "status/enabled"],
    }
    content = f"## Instructions\n{body}\n"
    post = frontmatter.Post(content, **metadata)
    filepath = target_dir / f"{slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()
    return slug
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_vault.py::test_write_entry_housekeeping_task_creates_file_in_housekeeping_folder tests/test_vault.py::test_write_entry_housekeeping_task_frontmatter -v
```

Expected: PASS

- [ ] **Step 1.5: Commit**

```bash
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: add housekeeping-task write support to vault"
```

---

### Task 2: vault — write_entry for housekeeping-heartbeat (singleton)

**Files:**
- Modify: `tests/test_vault.py`
- Modify: `app/services/vault.py`

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/test_vault.py`:

```python
# ============= housekeeping-heartbeat write tests =============

def test_write_entry_housekeeping_heartbeat_creates_last_run_md(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "housekeeping-heartbeat",
            "project": "claude-config",
            "title": "Housekeeping Last Run",
        })
    heartbeat = vault / "projects" / "claude-config" / "housekeeping" / "last-run.md"
    assert heartbeat.exists()
    assert slug == "last-run"


def test_write_entry_housekeeping_heartbeat_frontmatter(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({
            "type": "housekeeping-heartbeat",
            "project": "claude-config",
            "title": "Housekeeping Last Run",
        })
    post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / "last-run.md")
    assert post.metadata["type"] == "housekeeping-heartbeat"
    assert post.metadata["last_run"] == "null"
    assert post.metadata["tasks_run"] == "0"
    assert post.metadata["tasks_failed"] == "0"
    assert post.metadata["tasks_skipped"] == "0"


def test_write_entry_housekeeping_heartbeat_is_singleton(vault):
    """Writing heartbeat twice overwrites, never duplicates."""
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
    files = list((vault / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    assert len(files) == 1
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_vault.py::test_write_entry_housekeeping_heartbeat_creates_last_run_md tests/test_vault.py::test_write_entry_housekeeping_heartbeat_frontmatter tests/test_vault.py::test_write_entry_housekeeping_heartbeat_is_singleton -v
```

Expected: FAIL

- [ ] **Step 2.3: Add `write_entry` support for housekeeping-heartbeat in `app/services/vault.py`**

Add this branch in `write_entry()` after the `housekeeping-task` branch:

```python
elif entry_type == "housekeeping-heartbeat":
    project = data.get("project", "")
    target_dir = VAULT_PATH / "projects" / project / "housekeeping"
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "title": "Housekeeping Last Run",
        "type": "housekeeping-heartbeat",
        "project": project,
        "last_run": "null",
        "tasks_run": "0",
        "tasks_failed": "0",
        "tasks_skipped": "0",
        "created": datetime.now().isoformat(timespec="seconds"),
        "tags": ["housekeeping-heartbeat", project],
    }
    post = frontmatter.Post("", **metadata)
    filepath = target_dir / "last-run.md"  # singleton — fixed name, no date prefix
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()
    return "last-run"
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_vault.py::test_write_entry_housekeeping_heartbeat_creates_last_run_md tests/test_vault.py::test_write_entry_housekeeping_heartbeat_frontmatter tests/test_vault.py::test_write_entry_housekeeping_heartbeat_is_singleton -v
```

Expected: PASS

- [ ] **Step 2.5: Commit**

```bash
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: add housekeeping-heartbeat singleton write support to vault"
```

---

### Task 3: vault — update_housekeeping_fields

**Files:**
- Modify: `tests/test_vault.py`
- Modify: `app/services/vault.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_vault.py`:

```python
# ============= update_housekeeping_fields tests =============

def test_update_housekeeping_fields_task_enabled_toggle(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry, update_housekeeping_fields
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Test task",
            "body": "",
            "interval": "weekly",
            "success_definition": "Done.",
        })
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", slug, {"enabled": "false"}
        )
        assert result is True
        post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / f"{slug}.md")
        assert post.metadata["enabled"] == "false"


def test_update_housekeeping_fields_heartbeat(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry, update_housekeeping_fields
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        result = update_housekeeping_fields(
            "housekeeping-heartbeat", "claude-config", "last-run",
            {"last_run": "2026-06-17T12:00:00", "tasks_run": "3",
             "tasks_failed": "0", "tasks_skipped": "1"},
        )
        assert result is True
        post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / "last-run.md")
        assert post.metadata["last_run"] == "2026-06-17T12:00:00"
        assert post.metadata["tasks_run"] == "3"
        assert post.metadata["tasks_skipped"] == "1"


def test_update_housekeeping_fields_ignores_disallowed_fields(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry, update_housekeeping_fields
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Original",
            "body": "",
            "interval": "weekly",
            "success_definition": "Done.",
        })
        # title is not in the allowed set — should be silently ignored
        update_housekeeping_fields(
            "housekeeping-task", "claude-config", slug,
            {"title": "HACKED", "enabled": "false"},
        )
        post = fm.load(vault / "projects" / "claude-config" / "housekeeping" / f"{slug}.md")
        assert post.metadata["title"] == "Original"
        assert post.metadata["enabled"] == "false"


def test_update_housekeeping_fields_invalid_type_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_housekeeping_fields
        result = update_housekeeping_fields("bug", "claude-config", "any", {"last_run": "2026-06-17"})
        assert result is False


def test_update_housekeeping_fields_missing_file_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        (vault / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import update_housekeeping_fields
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", "nonexistent", {"enabled": "false"}
        )
        assert result is False


def test_update_housekeeping_fields_path_traversal_returns_false(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import update_housekeeping_fields
        result = update_housekeeping_fields(
            "housekeeping-task", "claude-config", "../../etc/passwd", {"enabled": "false"}
        )
        assert result is False
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_vault.py -k "update_housekeeping" -v
```

Expected: FAIL with `ImportError` (function not defined yet)

- [ ] **Step 3.3: Implement `update_housekeeping_fields` in `app/services/vault.py`**

Add this function after `update_entry_status_generic`:

```python
_HOUSEKEEPING_ALLOWED_FIELDS: dict[str, set[str]] = {
    "housekeeping-task": {"enabled", "last_run", "last_error", "consecutive_failures"},
    "housekeeping-heartbeat": {"last_run", "tasks_run", "tasks_failed", "tasks_skipped"},
}


def update_housekeeping_fields(
    entry_type: str,
    project: str,
    filename: str,
    fields: dict,
) -> bool:
    """Overwrite allowed runtime fields on a housekeeping vault entry."""
    allowed = _HOUSEKEEPING_ALLOWED_FIELDS.get(entry_type)
    if allowed is None:
        return False

    if ".." in filename or "/" in filename or "\\" in filename:
        return False

    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    fname = filename if filename.endswith(".md") else f"{filename}.md"
    filepath = VAULT_PATH / "projects" / project / "housekeeping" / fname
    if not filepath.exists():
        return False

    try:
        post = frontmatter.load(filepath)
        for k, v in updates.items():
            post.metadata[k] = v
        temp_filepath = filepath.with_suffix(".md.tmp")
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        temp_filepath.replace(filepath)
        _invalidate_cache()
        return True
    except Exception:
        return False
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_vault.py -k "update_housekeeping" -v
```

Expected: PASS

- [ ] **Step 3.5: Commit**

```bash
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: add update_housekeeping_fields to vault service"
```

---

### Task 4: capture — extend capture_json for housekeeping-task

**Files:**
- Modify: `tests/test_capture.py`
- Modify: `app/routes/capture.py`

- [ ] **Step 4.1: Write the failing tests**

Append to `tests/test_capture.py`:

```python
# ============= housekeeping-task capture_json tests =============

def test_capture_json_housekeeping_task(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "project": "claude-config",
        "title": "Prune vault",
        "interval": "weekly",
        "success_definition": "Old entries pruned.",
    })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    files = list((tmp_path / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    assert len(files) == 1


def test_capture_json_housekeeping_task_missing_title(client):
    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "project": "claude-config",
        "interval": "weekly",
        "success_definition": "Done.",
    })
    assert resp.status_code == 400


def test_capture_json_housekeeping_task_missing_project(client):
    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "title": "Test",
        "interval": "weekly",
        "success_definition": "Done.",
    })
    assert resp.status_code == 400


def test_capture_json_housekeeping_task_defaults_interval_to_weekly(client, tmp_path, monkeypatch):
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()
    (tmp_path / "projects" / "claude-config").mkdir(parents=True)

    resp = client.post("/capture/json", json={
        "type": "housekeeping-task",
        "project": "claude-config",
        "title": "Prune vault",
        "success_definition": "Done.",
        # interval omitted — should default to weekly
    })
    assert resp.status_code == 200
    files = list((tmp_path / "projects" / "claude-config" / "housekeeping").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["interval"] == "weekly"
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_capture.py -k "housekeeping_task" -v
```

Expected: FAIL (type rejected as invalid)

- [ ] **Step 4.3: Extend `capture_json` in `app/routes/capture.py`**

Replace the type validation and data extraction in `capture_json()`:

```python
@bp.route("/capture/json", methods=["POST"])
def capture_json():
    req = request.get_json(silent=True) or {}
    entry_type = req.get("type", "")
    project = req.get("project", "")
    title = req.get("title", "")

    if not title:
        return jsonify({"error": "title is required"}), 400
    if entry_type not in ("note", "idea", "bug", "housekeeping-task"):
        return jsonify({"error": "type must be note, idea, bug, or housekeeping-task"}), 400
    if not project:
        return jsonify({"error": "project is required"}), 400

    data = {
        "type": entry_type,
        "project": project,
        "title": title,
        "body": req.get("body", ""),
        "domains": [],
    }
    component = req.get("component", "").strip() or None
    if component:
        data["component"] = component
    if entry_type == "idea":
        data["priority"] = req.get("priority", "medium")
        data["effort"] = req.get("effort", "medium")
    elif entry_type == "bug":
        data["severity"] = req.get("severity", "medium")
        data["steps"] = req.get("steps", "")
    elif entry_type == "housekeeping-task":
        data["interval"] = req.get("interval", "weekly")
        data["success_definition"] = req.get("success_definition", "")

    write_entry(data)
    return jsonify({"ok": True}), 200
```

- [ ] **Step 4.4: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_capture.py -k "housekeeping_task" -v
```

Expected: PASS

- [ ] **Step 4.5: Commit**

```bash
git add app/routes/capture.py tests/test_capture.py
git commit -m "feat: extend capture_json to support housekeeping-task type"
```

---

### Task 5: capture — PATCH /entries/housekeeping route

**Files:**
- Modify: `tests/test_capture.py`
- Modify: `app/routes/capture.py`

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/test_capture.py`:

```python
# ============= PATCH /entries/housekeeping tests =============

def test_patch_housekeeping_requires_token(client, tmp_path):
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch("/entries/housekeeping", json={
            "project": "claude-config",
            "type": "housekeeping-task",
            "filename": "test",
            "fields": {"enabled": "false"},
        })
    assert resp.status_code == 401


def test_patch_housekeeping_task_enabled(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "housekeeping-task",
            "project": "claude-config",
            "title": "Test task",
            "body": "",
            "interval": "weekly",
            "success_definition": "Done.",
        })
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": slug, "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 200
    assert "Updated" in resp.get_json().get("message", "")


def test_patch_housekeeping_heartbeat(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        from app.services.vault import write_entry
        write_entry({"type": "housekeeping-heartbeat", "project": "claude-config", "title": "HB"})
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-heartbeat",
                  "filename": "last-run",
                  "fields": {"last_run": "2026-06-17T12:00:00", "tasks_run": "5",
                              "tasks_failed": "1", "tasks_skipped": "2"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 200


def test_patch_housekeeping_invalid_type_returns_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "bug",
                  "filename": "test", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400


def test_patch_housekeeping_missing_entry_returns_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "claude-config").mkdir(parents=True)
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "nonexistent", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 404


def test_patch_housekeeping_path_traversal_returns_400(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "../../etc/passwd", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400


def test_patch_housekeeping_requires_json_body(client, tmp_path, monkeypatch):
    """PATCH /entries/housekeeping rejects form data — JSON body only."""
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            data={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "test", "enabled": "false"},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400


def test_patch_housekeeping_wrong_token_returns_401(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/housekeeping",
            json={"project": "claude-config", "type": "housekeeping-task",
                  "filename": "test", "fields": {"enabled": "false"}},
            headers={"X-Capture-Token": "wrong-token"},
        )
    assert resp.status_code == 401
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_capture.py -k "patch_housekeeping" -v
```

Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 5.3: Add `PATCH /entries/housekeeping` to `app/routes/capture.py`**

Add this import at the top of `capture.py`:

```python
from app.services.vault import get_projects_with_meta, write_entry, update_entry_status_generic, update_housekeeping_fields
```

Add this route after `patch_entries`:

```python
@bp.route("/entries/housekeeping", methods=["PATCH"])
def patch_housekeeping():
    """Update housekeeping runtime fields. JSON body only."""
    token = request.headers.get("X-Capture-Token", "")
    is_valid, status_code = _validate_token(token)
    if not is_valid:
        return jsonify({"error": "Unauthorized" if status_code == 401 else "Service unavailable"}), status_code

    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    req_data = request.get_json()
    project = req_data.get("project", "").strip()
    entry_type = req_data.get("type", "").strip()
    filename = req_data.get("filename", "").strip()
    fields = req_data.get("fields")

    if not isinstance(fields, dict) or not fields:
        return jsonify({"error": "fields must be a non-empty object"}), 400

    if not _reject_path_traversal(filename):
        return jsonify({"error": "Invalid filename"}), 400

    if entry_type not in ("housekeeping-task", "housekeeping-heartbeat"):
        return jsonify({"error": "type must be housekeeping-task or housekeeping-heartbeat"}), 400

    if not project:
        return jsonify({"error": "project is required"}), 400

    success = update_housekeeping_fields(entry_type, project, filename, fields)
    if not success:
        return jsonify({"error": "Entry not found or no valid fields provided"}), 404

    return jsonify({"message": "Updated"}), 200
```

- [ ] **Step 5.4: Run tests to verify they pass**

```bash
docker.exe compose exec obsidian-capture pytest tests/test_capture.py -k "patch_housekeeping" -v
```

Expected: PASS

- [ ] **Step 5.5: Run full test suite to check for regressions**

```bash
docker.exe compose exec obsidian-capture pytest tests/ -v
```

Expected: All pass

- [ ] **Step 5.6: Commit**

```bash
git add app/routes/capture.py tests/test_capture.py
git commit -m "feat: add PATCH /entries/housekeeping for runtime field updates"
```

---

### Task 6: rebuild and smoke test

**Files:** None (container operations only)

- [ ] **Step 6.1: Rebuild and restart the obsidian-capture container**

```bash
cd /mnt/c/Server/projects/obsidian-capture
docker.exe compose up --build -d obsidian-capture
```

Wait ~10 seconds for startup.

- [ ] **Step 6.2: Check container is healthy**

```bash
docker.exe compose ps obsidian-capture
curl -s http://localhost:5009/health
```

Expected: `up`, response `ok`

- [ ] **Step 6.3: Smoke test — create a housekeeping-task via API**

```bash
CAPTURE_TOKEN=$(grep CAPTURE_TOKEN /mnt/c/Server/projects/obsidian-capture/.env | cut -d= -f2 | tr -d '\r')

curl -s -X POST http://localhost:5009/capture/json \
  -H "Content-Type: application/json" \
  -d '{"type":"housekeeping-task","project":"claude-config","title":"Smoke test task","interval":"weekly","success_definition":"Completes without error."}'
```

Expected: `{"ok": true}`

- [ ] **Step 6.4: Smoke test — create heartbeat singleton**

```bash
curl -s -X POST http://localhost:5009/capture/json \
  -H "Content-Type: application/json" \
  -d '{"type":"housekeeping-heartbeat","project":"claude-config","title":"Housekeeping Last Run"}'
```

Expected: `{"ok": true}`
Verify: `last-run.md` exists at `C:\Server\obsidian-vault\projects\claude-config\housekeeping\last-run.md`

- [ ] **Step 6.5: Smoke test — PATCH housekeeping fields**

```bash
curl -s -X PATCH http://localhost:5009/entries/housekeeping \
  -H "Content-Type: application/json" \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d '{"project":"claude-config","type":"housekeeping-heartbeat","filename":"last-run","fields":{"last_run":"2026-06-17T12:00:00","tasks_run":"3","tasks_failed":"0","tasks_skipped":"1"}}'
```

Expected: `{"message": "Updated"}`

- [ ] **Step 6.6: Clean up smoke test entries**

Delete the smoke test task file created in Step 6.3 (check the filename in the housekeeping folder and delete it). The `last-run.md` singleton can stay.

```bash
# Find and delete the smoke test task file
ls /mnt/c/Server/obsidian-vault/projects/claude-config/housekeeping/
# Delete the smoke test entry (not last-run.md)
# rm /mnt/c/Server/obsidian-vault/projects/claude-config/housekeeping/<smoke-test-file>.md
```
