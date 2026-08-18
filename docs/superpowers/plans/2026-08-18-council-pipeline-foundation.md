# Council Pipeline Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give IkeOS a first-class, stateful `council-item` vault entry type plus the pure backend routes and session-dispatch needed for a Discuss/Approve/Decline workflow — the API surface both a future UI and the claude-config narrative-review pipeline will be built against.

**Architecture:** `council-item` is a new entry type in the existing `ENTRY_TYPE_CONFIG` registry (same mechanism as `idea`/`bug`/`experiment`), with its own status lifecycle (`pending-review → in-discussion → approved/declined → actioned`) and a small set of extra runtime fields (`match_slug`, `weeks_open`, `source_review`, `discussion_session_id`, `decision_ref`) updated through a new `PATCH /entries/council` endpoint that mirrors the existing `PATCH /entries/housekeeping` pattern exactly. A new `app/routes/council.py` blueprint exposes `Discuss` (spawns a moderator session), `Approve` (flips status to `approved` and immediately dispatches an implementation session in a worktree — no separate Action click, no scope-based gating), and `Decline` (status flip only). This plan is API/service-layer only — no template or JS changes. Every task is verifiable with `pytest` and `curl` alone.

**Tech Stack:** Flask (routes/services), python-frontmatter (vault I/O), pytest (tests). No database — vault is the storage layer, per project convention.

**Spec:** `/mnt/c/Server/obsidian-vault/projects/ikeos/ideas/2026-08-18-unified-weekly-review-pipeline-decision-council-di.md` — the grilled design. This plan implements the IkeOS-side data model, routes, and session dispatch only (spec items 2, 3 partial, 4 partial, 5). Two things are deliberately deferred to separate follow-on plans, written after this one lands and is verified:
1. **UI** — the `/housekeeping` dashboard Council widget (pending count, weeks-open badges, Discuss/Approve/Decline buttons). Building this against a real, tested backend (rather than bundled into the same batch) means the UI plan can be written against the actual API shape instead of an assumed one, and this plan stays independently reviewable/mergeable without dragging template/JS changes along.
2. **claude-config side** — narrative task rewiring to create `council-item` entries with slug-matching/aging, the `/council-discuss` and `/council-action` moderator/implementer skills, `/platform-review` unification, push notification, and `type=decision` record creation. This is markdown-instruction-file work with no test framework — a different engineering modality from this plan's pytest-TDD tasks.

## Global Constraints

- Routes stay thin: parse request → call service → return response. Services never import Flask (`request`, `g`, `current_app`).
- `app/services/vault_cache.py`, `vault_entries.py`, `vault_council.py` are the only files that touch vault frontmatter directly — routes never do.
- All new vault-mutating routes that aren't simple reads require `@require_capture_token` (`app/routes/auth.py`), matching every existing mutation route (`/entries`, `/entries/housekeeping`, `/housekeeping/weekly-review/run`).
- Entry bodies are immutable once created — only `status` and the allowlisted runtime fields may be updated via PATCH. Never write code that rewrites a council-item's `## Description` body after creation.
- Push to the remote repo always requires a separate explicit human approval — nothing in this plan or its follow-on may add code that runs `git push` unattended. (Enforced in the follow-on claude-config plan, not here, but no IkeOS route in this plan should either.)
- Follow `app/services/vault_housekeeping.py`'s exact shape (`_ALLOWED_FIELDS` dict, temp-file-then-replace atomic write, `_vc._invalidate_cache()` on success) for the new `vault_council.py` — this repo already has one correct implementation of "allowlisted extra fields on a typed vault entry," don't reinvent it.

---

## File Structure

```
app/services/vault_cache.py       # MODIFY — add COUNCIL_STATUSES, "council-item" entry in ENTRY_TYPE_CONFIG
app/services/vault_entries.py     # MODIFY — write_entry() council-item fields; read_entries() entry_type filter
app/services/vault_council.py     # CREATE — update_council_fields(), mirrors vault_housekeeping.py
app/services/vault.py             # MODIFY — re-export new names
app/services/capabilities.py      # MODIFY — add "council_pipeline" capability
app/services/driver.py            # MODIFY — run_council_discuss(), run_council_action()
app/routes/capture.py             # MODIFY — PATCH /entries/council route
app/routes/council.py             # CREATE — POST /council/<slug>/discuss, /approve, /decline
app/__init__.py                   # MODIFY — register council_bp
tests/test_vault_entries.py       # MODIFY — council-item write/read tests
tests/test_vault_council.py       # CREATE — update_council_fields() tests
tests/test_capture.py             # MODIFY — PATCH /entries/council tests
tests/test_council_routes.py      # CREATE — discuss/approve/decline route tests
tests/test_capabilities.py        # MODIFY — council_pipeline capability test (if file exists; else add to test_housekeeping.py)
```

---

### Task 1: `council-item` entry type in the registry

**Files:**
- Modify: `app/services/vault_cache.py`
- Test: `tests/test_vault_entries.py`

**Interfaces:**
- Produces: `COUNCIL_STATUSES: tuple[str, ...]` = `("pending-review", "in-discussion", "approved", "declined", "actioned")`; `ENTRY_TYPE_CONFIG["council-item"]` = `{"folder": "council", "tag": "council", "initial_status": "pending-review", "valid_statuses": COUNCIL_STATUSES}`. `TYPE_FOLDERS`, `TYPE_TAGS`, `PATCH_VALID_TYPES`, `CAPTURE_JSON_VALID_TYPES` all pick this up automatically since they're derived from `ENTRY_TYPE_CONFIG.keys()`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_vault_entries.py`:

```python
def test_write_entry_creates_council_item_in_council_folder(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({
            "type": "council-item", "project": "myproj",
            "title": "Recover missing weak-signals entries", "body": "Recover the ~18 missing signals.",
        })
    files = list((tmp_path / "projects" / "myproj" / "council").glob("*.md"))
    assert len(files) == 1


def test_write_entry_council_item_initial_status_pending_review(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({
            "type": "council-item", "project": "myproj",
            "title": "Test recommendation", "body": "Body",
        })
    files = list((tmp_path / "projects" / "myproj" / "council").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["status"] == "pending-review"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_vault_entries.py -k council_item -v`
Expected: FAIL — `KeyError: 'council-item'` from `TYPE_FOLDERS[entry_type]` in `write_entry()`'s generic branch, since the type isn't registered yet.

- [ ] **Step 3: Add the entry type**

In `app/services/vault_cache.py`, add below `EXPERIMENT_STATUSES`:

```python
COUNCIL_STATUSES: tuple[str, ...] = ("pending-review", "in-discussion", "approved", "declined", "actioned")
```

Add to `ENTRY_TYPE_CONFIG`, keeping the existing rows unchanged:

```python
    "council-item": {"folder": "council", "tag": "council", "initial_status": "pending-review", "valid_statuses": COUNCIL_STATUSES},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_vault_entries.py -k council_item -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/vault_cache.py tests/test_vault_entries.py
git commit -m "feat: add council-item vault entry type"
```

---

### Task 2: `write_entry()` council-item metadata + `read_entries()` type filter

**Files:**
- Modify: `app/services/vault_entries.py`
- Test: `tests/test_vault_entries.py`

**Interfaces:**
- Consumes: `ENTRY_TYPE_CONFIG["council-item"]` from Task 1.
- Produces: `write_entry(data)` accepts `match_slug`, `source`, `source_review` in `data` for `type="council-item"` and persists them plus `weeks_open="1"`, `discussion_session_id=""`, `decision_ref=""` in frontmatter. `read_entries(project=None, status_filter=None, component=None, entry_type=None)` — new optional `entry_type` param filters the returned list to that type; every existing caller (which omits it) is unaffected.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_vault_entries.py`:

```python
def test_write_entry_council_item_persists_match_slug_and_source(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({
            "type": "council-item", "project": "myproj",
            "title": "Recover weak-signals entries", "body": "Body",
            "match_slug": "weak-signals-integrity",
            "source": "narrative-review",
            "source_review": "2026-08-15-review.md",
        })
    files = list((tmp_path / "projects" / "myproj" / "council").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["match_slug"] == "weak-signals-integrity"
    assert post.metadata["source"] == "narrative-review"
    assert post.metadata["source_review"] == "2026-08-15-review.md"
    assert post.metadata["weeks_open"] == "1"
    assert post.metadata["discussion_session_id"] == ""
    assert post.metadata["decision_ref"] == ""


def test_read_entries_filters_by_entry_type(tmp_path):
    for folder, etype in [("bugs", "bug"), ("council", "council-item")]:
        d = tmp_path / "projects" / "myproj" / folder
        d.mkdir(parents=True)
        (d / "2026-01-01-entry.md").write_text(
            f"---\ntype: {etype}\ntitle: T\nproject: myproj\n"
            "status: new\ncreated: 2026-01-01T00:00:00\ntags: []\n---\n## Description\n"
        )
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import read_entries, _invalidate_cache
        _invalidate_cache()
        result = read_entries(project="myproj", entry_type="council-item")
    assert len(result) == 1
    assert result[0]["type"] == "council-item"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_vault_entries.py -k "match_slug or filters_by_entry_type" -v`
Expected: FAIL — `match_slug`/`source`/`source_review`/`weeks_open` keys missing from metadata (generic branch doesn't set them); `read_entries()` raises `TypeError: unexpected keyword argument 'entry_type'`.

- [ ] **Step 3: Implement**

In `app/services/vault_entries.py`, inside `write_entry()`'s generic `else` branch (the one handling `note`/`idea`/`bug`/`experiment`/`grill-me`), add a `council-item` branch alongside the existing `if entry_type == "idea": ... elif entry_type == "bug": ...` chain:

```python
        elif entry_type == "council-item":
            metadata["match_slug"] = data.get("match_slug", "")
            metadata["source"] = data.get("source", "")
            metadata["source_review"] = data.get("source_review", "")
            metadata["weeks_open"] = "1"
            metadata["discussion_session_id"] = ""
            metadata["decision_ref"] = ""
```

(Place this as another `elif` in the same chain that already has `idea`/`bug`/`experiment` branches — it runs after the shared `metadata = {...}` dict is built, same as those.)

Update `read_entries()`'s signature and body:

```python
def read_entries(project: str = None, status_filter: list = None, component: str = None, entry_type: str = None) -> list[dict]:
    now = time.monotonic()

    if _vc._entries_cache is None or (now - _vc._entries_cache_ts) >= _vc._TTL:
        _vc._entries_cache = _read_all_entries()
        _vc._entries_cache_ts = now

    entries = _vc._entries_cache
    if project is not None:
        entries = [e for e in entries if e.get("project") == project]
    if component is not None:
        entries = [e for e in entries if e.get("component") == component]
    if status_filter:
        entries = [e for e in entries if e.get("status") in status_filter]
    if entry_type is not None:
        entries = [e for e in entries if e.get("type") == entry_type]

    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_vault_entries.py -v`
Expected: PASS, including all pre-existing tests in the file (confirms the new `entry_type` param didn't break any caller relying on positional args — check none of the existing call sites in the codebase pass `read_entries` positionally past `component`; grep confirms all current callers use keyword args).

- [ ] **Step 5: Commit**

```bash
git add app/services/vault_entries.py tests/test_vault_entries.py
git commit -m "feat: council-item metadata fields and entry_type filter on read_entries"
```

---

### Task 3: `update_council_fields()` service

**Files:**
- Create: `app/services/vault_council.py`
- Test: `tests/test_vault_council.py`

**Interfaces:**
- Consumes: `app.services.vault_cache as _vc` (for `VAULT_PATH`, `_invalidate_cache`).
- Produces: `update_council_fields(project: str, filename: str, fields: dict) -> bool` — allowlisted fields: `match_slug`, `weeks_open`, `discussion_session_id`, `decision_ref`. Returns `False` on path traversal, missing file, or an empty allowlisted intersection.

- [ ] **Step 1: Write the failing test**

Create `tests/test_vault_council.py`:

```python
import pytest
from unittest.mock import patch
import frontmatter as fm
import app.services.vault_cache as _vc


@pytest.fixture(autouse=True)
def reset_cache():
    _vc._invalidate_cache()
    yield
    _vc._invalidate_cache()


def _write_council_item(tmp_path, project="myproj", slug="2026-08-18-test-item"):
    d = tmp_path / "projects" / project / "council"
    d.mkdir(parents=True)
    entry = fm.Post(
        "## Description\nbody\n",
        type="council-item", title="Test item", project=project,
        status="pending-review", created="2026-08-18T00:00:00",
        tags=["council", project, "status/pending-review"],
        match_slug="test-item", source="narrative-review", source_review="",
        weeks_open="1", discussion_session_id="", decision_ref="",
    )
    (d / f"{slug}.md").write_text(fm.dumps(entry))
    return d / f"{slug}.md"


def test_update_council_fields_bumps_weeks_open(tmp_path):
    filepath = _write_council_item(tmp_path)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "2026-08-18-test-item", {"weeks_open": "2"})
    assert result is True
    post = fm.load(filepath)
    assert post.metadata["weeks_open"] == "2"


def test_update_council_fields_sets_decision_ref(tmp_path):
    filepath = _write_council_item(tmp_path)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "2026-08-18-test-item", {"decision_ref": "2026-08-25-recover-weak-signals-decision"})
    assert result is True
    post = fm.load(filepath)
    assert post.metadata["decision_ref"] == "2026-08-25-recover-weak-signals-decision"


def test_update_council_fields_rejects_disallowed_field(tmp_path):
    _write_council_item(tmp_path)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "2026-08-18-test-item", {"title": "Hijacked"})
    assert result is False


def test_update_council_fields_missing_entry_returns_false(tmp_path):
    (tmp_path / "projects" / "myproj" / "council").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "does-not-exist", {"weeks_open": "2"})
    assert result is False


def test_update_council_fields_rejects_path_traversal(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "../../etc/passwd", {"weeks_open": "2"})
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_vault_council.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.vault_council'`

- [ ] **Step 3: Implement**

Create `app/services/vault_council.py`:

```python
"""Council vault functions — read/write council-item runtime fields."""

import logging

import frontmatter

import app.services.vault_cache as _vc

logger = logging.getLogger(__name__)

_COUNCIL_ALLOWED_FIELDS: set[str] = {"match_slug", "weeks_open", "discussion_session_id", "decision_ref"}


def update_council_fields(project: str, filename: str, fields: dict) -> bool:
    """Overwrite allowed runtime fields on a council-item vault entry."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    if ".." in project or "/" in project or "\\" in project:
        return False

    updates = {k: v for k, v in fields.items() if k in _COUNCIL_ALLOWED_FIELDS}
    if not updates:
        return False

    fname = filename if filename.endswith(".md") else f"{filename}.md"
    filepath = _vc.VAULT_PATH / "projects" / project / "council" / fname
    if not filepath.exists():
        return False

    temp_filepath = filepath.with_suffix(".tmp")
    try:
        post = frontmatter.load(filepath)
        for k, v in updates.items():
            post.metadata[k] = v
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        temp_filepath.replace(filepath)
        _vc._invalidate_cache()
        return True
    except Exception:
        logger.exception("Failed to update council fields for %s/%s", project, filename)
        temp_filepath.unlink(missing_ok=True)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_vault_council.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/vault_council.py tests/test_vault_council.py
git commit -m "feat: update_council_fields service for council-item runtime fields"
```

---

### Task 4: Re-export from `app/services/vault.py`

**Files:**
- Modify: `app/services/vault.py`
- Test: `tests/test_vault.py`

**Interfaces:**
- Consumes: `COUNCIL_STATUSES` (Task 1), `update_council_fields` (Task 3).
- Produces: `from app.services.vault import COUNCIL_STATUSES, update_council_fields` works for route code, matching how `update_housekeeping_fields` is already re-exported.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_vault.py`:

```python
def test_vault_reexports_council_statuses_and_update_fn():
    from app.services.vault import COUNCIL_STATUSES, update_council_fields
    assert "pending-review" in COUNCIL_STATUSES
    assert callable(update_council_fields)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker exec ikeos pytest tests/test_vault.py -k council -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Add the re-exports**

In `app/services/vault.py`, add `COUNCIL_STATUSES` to the existing `from app.services.vault_cache import (...)` block:

```python
from app.services.vault_cache import (  # noqa: F401
    VAULT_PATH,
    VALID_STATUSES,
    DECISION_STATUSES,
    EXPERIMENT_STATUSES,
    COUNCIL_STATUSES,
    ENTRY_TYPE_CONFIG,
    PATCH_VALID_TYPES,
    CAPTURE_JSON_VALID_TYPES,
    TYPE_FOLDERS,
    TYPE_TAGS,
    _TTL,
    _invalidate_cache,
    _projects_cache,
    _projects_cache_ts,
    _entries_cache,
    _entries_cache_ts,
    _hub_pages_cache,
    _hub_pages_cache_ts,
)
```

Find wherever `update_housekeeping_fields` is currently re-exported (the `from app.services.vault_housekeeping import (...)` block) and add a matching block immediately after it:

```python
from app.services.vault_council import (  # noqa: F401
    update_council_fields,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker exec ikeos pytest tests/test_vault.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: re-export council vault functions from vault.py"
```

---

### Task 5: `PATCH /entries/council` route

**Files:**
- Modify: `app/routes/capture.py`
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: `update_council_fields` (Task 3/4), `require_capture_token` decorator pattern already used by `patch_housekeeping()` in the same file.
- Produces: `PATCH /entries/council` — JSON body `{"project": str, "filename": str, "fields": dict}`, header `X-Capture-Token`. 200 on success, 401/503 on auth failure, 400 on malformed body, 404 on missing entry or no valid fields.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_capture.py`:

```python
def test_patch_council_requires_token(client, tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        resp = client.patch("/entries/council", json={
            "project": "myproj", "filename": "test", "fields": {"weeks_open": "2"},
        })
    assert resp.status_code == 401


def test_patch_council_updates_weeks_open(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "myproj").mkdir(parents=True)
        from app.services.vault import write_entry
        slug = write_entry({
            "type": "council-item", "project": "myproj",
            "title": "Test item", "body": "Body",
            "match_slug": "test-item", "source": "narrative-review",
        })
        resp = client.patch(
            "/entries/council",
            json={"project": "myproj", "filename": slug, "fields": {"weeks_open": "2"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 200
    assert "Updated" in resp.get_json().get("message", "")


def test_patch_council_missing_entry_returns_404(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / "myproj" / "council").mkdir(parents=True)
        resp = client.patch(
            "/entries/council",
            json={"project": "myproj", "filename": "nope", "fields": {"weeks_open": "2"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 404


def test_patch_council_rejects_path_traversal(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        resp = client.patch(
            "/entries/council",
            json={"project": "myproj", "filename": "../../etc/passwd", "fields": {"weeks_open": "2"}},
            headers={"X-Capture-Token": "test-token-secret"},
        )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_capture.py -k patch_council -v`
Expected: FAIL — 404 (route doesn't exist)

- [ ] **Step 3: Implement**

In `app/routes/capture.py`, add `update_council_fields` to the existing `from app.services.vault import (...)` block, then add the route below `patch_housekeeping()`:

```python
@bp.route("/entries/council", methods=["PATCH"])
def patch_council():
    """Update council-item runtime fields (weeks_open, discussion_session_id, decision_ref, match_slug)."""
    token = request.headers.get("X-Capture-Token", "")
    is_valid, status_code = _validate_token(token)
    if not is_valid:
        return jsonify({"error": "Unauthorized" if status_code == 401 else "Service unavailable"}), status_code

    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    req_data = request.get_json(silent=True)
    if req_data is None:
        return jsonify({"error": "Invalid or empty JSON body"}), 400
    project = req_data.get("project", "").strip().lower()
    filename = req_data.get("filename", "").strip()
    fields = req_data.get("fields")

    if not isinstance(fields, dict) or not fields:
        return jsonify({"error": "fields must be a non-empty object"}), 400

    if not _reject_path_traversal(filename):
        return jsonify({"error": "Invalid filename"}), 400

    if not project:
        return jsonify({"error": "project is required"}), 400

    success = update_council_fields(project, filename, fields)
    if not success:
        return jsonify({"error": "Entry not found or no valid fields provided"}), 404

    return jsonify({"message": "Updated"}), 200
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_capture.py -v`
Expected: PASS, all tests including pre-existing ones in the file.

- [ ] **Step 5: Commit**

```bash
git add app/routes/capture.py tests/test_capture.py
git commit -m "feat: PATCH /entries/council route for council-item runtime fields"
```

---

### Task 6: `council_pipeline` capability flag

**Files:**
- Modify: `app/services/capabilities.py`
- Test: existing capability tests (find the file testing `capabilities.py` — grep `tests/` for `DEFAULT_CAPABILITIES` to locate it; add alongside).

**Interfaces:**
- Produces: `DEFAULT_CAPABILITIES["council_pipeline"]` = `{"enabled": False, "enabled_by": None, "enabled_at": None, "description": "Council discuss/approve pipeline for weekly review recommendations"}`. `is_enabled("council_pipeline")` and `update_capability("council_pipeline", ...)` work exactly as they do for `weekly_platform_review`.

- [ ] **Step 1: Locate the existing capability test file and write the failing test**

```bash
grep -rl "DEFAULT_CAPABILITIES\|weekly_platform_review" tests/
```

Add to that file (or `tests/test_capabilities.py` if none exists yet):

```python
def test_council_pipeline_capability_defaults_disabled():
    from app.services.capabilities import get_capabilities
    caps = get_capabilities()
    assert caps["council_pipeline"]["enabled"] is False


def test_council_pipeline_capability_can_be_enabled(tmp_path, monkeypatch):
    from unittest.mock import patch as _patch
    with _patch("app.services.capabilities._capabilities_path", return_value=tmp_path / "capabilities.json"):
        from app.services.capabilities import update_capability, is_enabled
        update_capability("council_pipeline", True, actor="ryan")
        assert is_enabled("council_pipeline") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest -k council_pipeline_capability -v`
Expected: FAIL — `KeyError: 'council_pipeline'`

- [ ] **Step 3: Implement**

In `app/services/capabilities.py`, add to `DEFAULT_CAPABILITIES`:

```python
    "council_pipeline": {
        "enabled": False,
        "enabled_by": None,
        "enabled_at": None,
        "description": "Council discuss/approve pipeline for weekly review recommendations",
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest -k council_pipeline_capability -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/capabilities.py tests/
git commit -m "feat: add council_pipeline capability flag"
```

---

### Task 7: `driver.py` session dispatch

**Files:**
- Modify: `app/services/driver.py`
- Test: `tests/test_driver.py` (check it exists via `find tests -iname "*driver*"`; create if not)

**Interfaces:**
- Consumes: `create_session`, `SessionResult` from `app.services.session_client`; `project_slug()` from `app.services.platform`; `_housekeeping_project_dir()` (existing private helper in the same file).
- Produces: `run_council_discuss(item_slug: str, model: str | None = None) -> SessionResult`, `run_council_action(item_slug: str, model: str | None = None) -> SessionResult`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_driver.py` (create the file with this content if it doesn't exist — check first with `find tests -iname "*driver*"` and match its existing fixture/mocking style if it does):

```python
from unittest.mock import patch, MagicMock

from app.services.session_client import SessionResult


def test_run_council_discuss_uses_item_slug_in_command():
    fake_result = SessionResult(session_id="abc123")
    with patch("app.services.driver.create_session", return_value=fake_result) as mock_create:
        from app.services.driver import run_council_discuss
        result = run_council_discuss("2026-08-18-recover-weak-signals-entries")
    assert result.session_id == "abc123"
    _, kwargs = mock_create.call_args
    assert kwargs["initial_command"] == "/council-discuss 2026-08-18-recover-weak-signals-entries"


def test_run_council_action_uses_item_slug_in_command():
    fake_result = SessionResult(session_id="def456")
    with patch("app.services.driver.create_session", return_value=fake_result) as mock_create:
        from app.services.driver import run_council_action
        result = run_council_action("2026-08-18-recover-weak-signals-entries")
    assert result.session_id == "def456"
    _, kwargs = mock_create.call_args
    assert kwargs["initial_command"] == "/council-action 2026-08-18-recover-weak-signals-entries"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_driver.py -k council -v`
Expected: FAIL — `ImportError: cannot import name 'run_council_discuss'`

- [ ] **Step 3: Implement**

In `app/services/driver.py`, add below `run_platform_review()`:

```python
def run_council_discuss(item_slug: str, model: str | None = None) -> SessionResult:
    return create_session(
        name=f"council-discuss-{item_slug[:40]}",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command=f"/council-discuss {item_slug}",
        model=model,
    )


def run_council_action(item_slug: str, model: str | None = None) -> SessionResult:
    return create_session(
        name=f"council-action-{item_slug[:40]}",
        project=project_slug(),
        project_dir=_housekeeping_project_dir(),
        initial_command=f"/council-action {item_slug}",
        model=model,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_driver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/driver.py tests/test_driver.py
git commit -m "feat: council discuss/action session dispatch in driver.py"
```

---

### Task 8: `app/routes/council.py` — Discuss/Approve/Decline routes

**Files:**
- Create: `app/routes/council.py`
- Modify: `app/__init__.py`
- Test: `tests/test_council_routes.py`

**Interfaces:**
- Consumes: `run_council_discuss`, `run_council_action` (Task 7); `update_entry_status_generic` (existing, from `app.services.vault`); `is_enabled` (Task 6); `require_capture_token` (existing, `app.routes.auth`); `project_slug` (existing, `app.services.platform`).
- Produces: Blueprint `council_bp` with routes `POST /council/<slug>/discuss`, `POST /council/<slug>/approve`, `POST /council/<slug>/decline`. All three require `X-Capture-Token` and `council_pipeline` capability enabled (403 if disabled, matching `weekly_review_run()`'s existing pattern in `housekeeping.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_council_routes.py`:

```python
from unittest.mock import patch

import pytest

from app.services.session_client import SessionResult


@pytest.fixture(autouse=True)
def enable_council_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "test-token-secret")
    with patch("app.services.capabilities._capabilities_path", return_value=tmp_path / "capabilities.json"):
        from app.services.capabilities import update_capability
        update_capability("council_pipeline", True, actor="test")
        yield


def _write_item(tmp_path, project="claude-config", slug="2026-08-18-test-item"):
    from app.services.vault import write_entry
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        (tmp_path / "projects" / project).mkdir(parents=True, exist_ok=True)
        return write_entry({
            "type": "council-item", "project": project,
            "title": "Test item", "body": "Body", "match_slug": "test-item",
        })


def test_discuss_requires_token(client, tmp_path):
    resp = client.post("/council/some-slug/discuss")
    assert resp.status_code == 401


def test_discuss_spawns_session_and_sets_in_discussion(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.council.project_slug", lambda: "claude-config")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        slug = _write_item(tmp_path)
        with patch("app.services.driver.run_council_discuss", return_value=SessionResult(session_id="s1")) as mock_run:
            resp = client.post(f"/council/{slug}/discuss", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 200
    assert resp.get_json()["session_id"] == "s1"
    mock_run.assert_called_once_with(slug)


def test_approve_spawns_action_session(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.council.project_slug", lambda: "claude-config")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        slug = _write_item(tmp_path)
        with patch("app.services.driver.run_council_action", return_value=SessionResult(session_id="s2")) as mock_run:
            resp = client.post(f"/council/{slug}/approve", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 200
    assert resp.get_json()["session_id"] == "s2"
    mock_run.assert_called_once_with(slug)


def test_decline_flips_status_without_spawning_session(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes.council.project_slug", lambda: "claude-config")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        slug = _write_item(tmp_path)
        resp = client.post(f"/council/{slug}/decline", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 200


def test_approve_returns_403_when_capability_disabled(client, tmp_path):
    from app.services.capabilities import update_capability
    with patch("app.services.capabilities._capabilities_path", return_value=tmp_path / "caps.json"):
        update_capability("council_pipeline", False, actor="test")
        resp = client.post("/council/some-slug/approve", headers={"X-Capture-Token": "test-token-secret"})
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec ikeos pytest tests/test_council_routes.py -v`
Expected: FAIL — 404 (blueprint not registered, module doesn't exist)

- [ ] **Step 3: Implement**

Create `app/routes/council.py`:

```python
from flask import Blueprint, jsonify

from app.routes.auth import require_capture_token
from app.services.capabilities import is_enabled
from app.services.driver import run_council_action, run_council_discuss
from app.services.platform import project_slug
from app.services.vault import update_entry_status_generic

bp = Blueprint("council", __name__)


@bp.route("/council/<slug>/discuss", methods=["POST"])
@require_capture_token
def discuss(slug):
    if not is_enabled("council_pipeline"):
        return jsonify({"error": "council_pipeline capability is disabled"}), 403
    update_entry_status_generic("council-item", project_slug(), slug, "in-discussion")
    result = run_council_discuss(slug)
    if not result.ok:
        return jsonify({"error": result.error or "Failed to create discuss session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/council/<slug>/approve", methods=["POST"])
@require_capture_token
def approve(slug):
    if not is_enabled("council_pipeline"):
        return jsonify({"error": "council_pipeline capability is disabled"}), 403
    update_entry_status_generic("council-item", project_slug(), slug, "approved")
    result = run_council_action(slug)
    if not result.ok:
        return jsonify({"error": result.error or "Failed to create action session"}), 502
    return jsonify({"ok": True, "session_id": result.session_id}), 200


@bp.route("/council/<slug>/decline", methods=["POST"])
@require_capture_token
def decline(slug):
    if not is_enabled("council_pipeline"):
        return jsonify({"error": "council_pipeline capability is disabled"}), 403
    success = update_entry_status_generic("council-item", project_slug(), slug, "declined")
    if not success:
        return jsonify({"error": "Entry not found"}), 404
    return jsonify({"ok": True}), 200
```

Note: `test_approve_returns_403_when_capability_disabled` deliberately doesn't create a vault entry first — the capability check must short-circuit before any vault lookup, so route order matters (capability check first, as written above).

In `app/__init__.py`, add the import alongside the existing blueprint imports and register it alongside the existing `app.register_blueprint(...)` calls:

```python
from app.routes.council import bp as council_bp
```

```python
    app.register_blueprint(council_bp)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec ikeos pytest tests/test_council_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes/council.py app/__init__.py tests/test_council_routes.py
git commit -m "feat: council discuss/approve/decline routes"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Spec coverage:** This plan covers spec items — data model (Task 1-4), decision-record linkage field (`decision_ref`, Task 2-3, populated by the claude-config follow-on plan), Discuss/Approve/Decline dispatch (Task 7-8). NOT covered here: the `/housekeeping` dashboard widget (its own follow-on UI plan, written once this API is live and tested) and everything on the claude-config side — narrative-task recommendation generation and slug-matching/aging logic (the *producer* of council-items — this plan only builds the *consumer* API), the `/council-discuss` and `/council-action` moderator/implementer skills themselves, `/platform-review` unification, push notification on new-item creation, and the `type=decision` record creation on Discuss conclusion. Push-gate enforcement (local worktree work never auto-pushes) lives entirely in `/council-action`'s prompt instructions in that follow-on plan — there is no IkeOS route in this plan that could push regardless.
- **Push notification:** intentionally not an IkeOS route/service in this plan — it's a `PushNotification` tool call from within the narrative-review Claude Code session itself (claude-config follow-on plan), since that session already runs as a Claude agent with that tool available. No new IkeOS notification infrastructure needed.
- **Type consistency:** `run_council_discuss`/`run_council_action` (driver.py, Task 7) both take `item_slug: str` positionally and are called positionally in `council.py` (Task 8) — verified consistent. `update_council_fields(project, filename, fields)` (Task 3) matches its call convention in the PATCH route (Task 5).
- **Manual API verification (in place of Task 9's browser check):** after Task 8, this plan has no template/JS, so there's nothing to click in a browser — verify end-to-end via curl instead: enable `council_pipeline` (`update_capability`), `POST /capture/json` a `type=council-item` entry, then `curl -X POST http://localhost:5009/council/<slug>/approve -H "X-Capture-Token: $CAPTURE_TOKEN"` and confirm a session appears in the session-manager's session list with `initial_command` starting `/council-action` (the skill itself doesn't exist yet until the claude-config plan lands, so the spawned session will fail its slash command — that's expected and fine, this step only verifies dispatch, not the skill's behavior).
