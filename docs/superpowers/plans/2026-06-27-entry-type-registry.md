# Entry Type Registry Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `ENTRY_TYPE_CONFIG` as a single registry in `vault_cache.py` so that adding a new project-scoped vault entry type requires touching exactly one place — no more hardcoded tuples in `vault_entries.py` or ternary chains in `capture.py`.

**Architecture:** `ENTRY_TYPE_CONFIG` maps each project-scoped type (`note`, `idea`, `bug`, `grill-me`, `experiment`) to its folder, tag, initial status, and valid statuses. `TYPE_FOLDERS` and `TYPE_TAGS` become derived from this registry (backward-compatible). `vault_entries.py` loops over `ENTRY_TYPE_CONFIG.values()` for folder scans and index lookups. `capture.py` derives valid_statuses and the PATCH type set from the registry. Decision and housekeeping types keep their existing special-case paths (they have different storage layouts that don't fit the standard pattern). No new user-visible features.

**Tech Stack:** Python 3.11, Flask, python-frontmatter, pytest, Docker

---

## Scope Note

The three tasks are sequential. Task 1 must be complete and passing before Task 2 starts — capture.py depends on the re-export added in Task 2, and vault.py re-exports from vault_entries which is changed in Task 1.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/services/vault_cache.py` | Add `ENTRY_TYPE_CONFIG`; derive `TYPE_FOLDERS` and `TYPE_TAGS` from it |
| Modify | `app/services/vault_entries.py` | Use registry in `write_entry`, `read_entry`, `update_entry_status`, `update_entry_status_generic` |
| Modify | `app/services/vault.py` | Add `ENTRY_TYPE_CONFIG` to re-exports |
| Modify | `app/routes/capture.py` | Derive valid_statuses and PATCH type set from `ENTRY_TYPE_CONFIG`; derive `capture_json` type set |
| Modify | `.claude/DECISIONS.md` | Document the registry consolidation decision |
| Modify | `tests/test_vault_entries.py` | Add 3 tests proving registry drives behaviour |
| Modify | `tests/test_capture.py` | No new tests needed — existing patch_entries coverage is sufficient |

---

## Critical reading before starting

- `app/services/vault_cache.py` — understand all existing constants before adding the registry
- `app/services/vault_entries.py` — read `write_entry()`, `read_entry()`, `update_entry_status()`, `update_entry_status_generic()` in full; the else-branch in `update_entry_status_generic` is being collapsed
- `app/routes/capture.py` — understand `patch_entries()` valid_statuses ternary and `capture_json()` type list
- `app/services/vault.py` — understand what is already re-exported before adding to it
- `tests/test_vault_entries.py` — understand the `reset_cache` autouse fixture and import patterns

---

## Task 1: Add `ENTRY_TYPE_CONFIG` and update `vault_entries.py`

**Files:**
- Modify: `app/services/vault_cache.py`
- Modify: `app/services/vault_entries.py`
- Modify: `tests/test_vault_entries.py`

### Step 1: Write three failing tests

Add these tests to `tests/test_vault_entries.py` after the last existing test:

```python
def test_entry_type_config_defines_type_folders_and_tags():
    """TYPE_FOLDERS and TYPE_TAGS must be derived from ENTRY_TYPE_CONFIG — not independent dicts."""
    assert hasattr(_vc, "ENTRY_TYPE_CONFIG"), "ENTRY_TYPE_CONFIG not found in vault_cache"
    assert _vc.TYPE_FOLDERS == {k: v["folder"] for k, v in _vc.ENTRY_TYPE_CONFIG.items()}
    assert _vc.TYPE_TAGS == {k: v["tag"] for k, v in _vc.ENTRY_TYPE_CONFIG.items()}


def test_read_entry_uses_entry_type_config(tmp_path):
    """read_entry must find an entry whose type/folder comes only from ENTRY_TYPE_CONFIG."""
    fake_config = {
        **_vc.ENTRY_TYPE_CONFIG,
        "widget": {
            "folder": "widgets",
            "tag": "widget",
            "initial_status": "new",
            "valid_statuses": _vc.VALID_STATUSES,
        },
    }
    widget_dir = tmp_path / "projects" / "myproj" / "widgets"
    widget_dir.mkdir(parents=True)
    post = fm.Post(
        "body",
        type="widget", title="Widget", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["widget", "myproj", "status/new"],
    )
    (widget_dir / "2026-01-01-widget.md").write_text(fm.dumps(post))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.services.vault_cache.ENTRY_TYPE_CONFIG", fake_config):
        from app.services.vault_entries import read_entry
        result = read_entry("myproj", "2026-01-01-widget")
    assert result is not None
    assert result["title"] == "Widget"


def test_update_entry_status_generic_uses_entry_type_config(tmp_path):
    """update_entry_status_generic must route to a folder defined only in ENTRY_TYPE_CONFIG."""
    fake_config = {
        **_vc.ENTRY_TYPE_CONFIG,
        "widget": {
            "folder": "widgets",
            "tag": "widget",
            "initial_status": "new",
            "valid_statuses": _vc.VALID_STATUSES,
        },
    }
    widget_dir = tmp_path / "projects" / "myproj" / "widgets"
    widget_dir.mkdir(parents=True)
    post = fm.Post(
        "body",
        type="widget", title="W", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["widget", "myproj", "status/new"],
    )
    (widget_dir / "2026-01-01-w.md").write_text(fm.dumps(post))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path), \
         patch("app.services.vault_cache.ENTRY_TYPE_CONFIG", fake_config):
        from app.services.vault_entries import update_entry_status_generic
        result = update_entry_status_generic("widget", "myproj", "2026-01-01-w", "done")
    assert result is True
    post = fm.load(widget_dir / "2026-01-01-w.md")
    assert post.metadata["status"] == "done"
    assert "status/done" in post.metadata["tags"]
```

- [ ] **Step 2: Run failing tests**

```bash
docker.exe exec ikeos pytest tests/test_vault_entries.py::test_entry_type_config_defines_type_folders_and_tags tests/test_vault_entries.py::test_read_entry_uses_entry_type_config tests/test_vault_entries.py::test_update_entry_status_generic_uses_entry_type_config -v 2>&1 | tail -15
```

Expected: 3 FAILED — `AttributeError: module 'app.services.vault_cache' has no attribute 'ENTRY_TYPE_CONFIG'` for the first; the latter two fail because `read_entry` and `update_entry_status_generic` use hardcoded paths.

- [ ] **Step 3: Update `vault_cache.py` — add registry and derive dependent constants**

Replace the current block:

```python
VALID_TYPES = {
    "note", "idea", "bug", "decision",
    "grill-me", "housekeeping-task", "housekeeping-heartbeat", "experiment",
}
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
EXPERIMENT_STATUSES = {"running", "complete", "abandoned"}
TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs", "grill-me": "grill-me", "experiment": "experiments"}
TYPE_TAGS = {
    "note": "documentation",
    "idea": "enhancement",
    "bug": "bug",
    "decision": "decision",
    "grill-me": "grill-me",
    "experiment": "experiment",
}
```

With:

```python
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
EXPERIMENT_STATUSES = {"running", "complete", "abandoned"}

ENTRY_TYPE_CONFIG: dict[str, dict] = {
    "note":       {"folder": "notes",       "tag": "documentation", "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "idea":       {"folder": "ideas",       "tag": "enhancement",   "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "bug":        {"folder": "bugs",        "tag": "bug",           "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "grill-me":   {"folder": "grill-me",    "tag": "grill-me",      "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "experiment": {"folder": "experiments", "tag": "experiment",    "initial_status": "running", "valid_statuses": EXPERIMENT_STATUSES},
}

TYPE_FOLDERS = {k: v["folder"] for k, v in ENTRY_TYPE_CONFIG.items()}
TYPE_TAGS = {k: v["tag"] for k, v in ENTRY_TYPE_CONFIG.items()}

VALID_TYPES = set(ENTRY_TYPE_CONFIG.keys()) | {
    "decision", "housekeeping-task", "housekeeping-heartbeat",
}
```

- [ ] **Step 4: Run tests — all existing tests must still pass**

```bash
docker cp app/services/vault_cache.py ikeos:/app/app/services/vault_cache.py
docker.exe exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: 258 passed (including the 3 new ones still failing — that's ok at this step; this confirms vault_cache changes don't break anything). Actually the 3 new tests may still fail since vault_entries hasn't changed yet. Verify only that no previously-passing test now fails.

- [ ] **Step 5: Update `vault_entries.py` — four changes**

Read `app/services/vault_entries.py` in full before editing. Then apply these four changes.

**Change A:** In `write_entry()`, in the `else:` branch, replace the initial_status line:

```python
# Old:
initial_status = "running" if entry_type == "experiment" else "new"

# New:
initial_status = _vc.ENTRY_TYPE_CONFIG[entry_type]["initial_status"]
```

**Change B:** In `read_entry()`, replace the hardcoded folder tuple:

```python
# Old:
def read_entry(project: str, slug: str) -> dict | None:
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes", "grill-me", "experiments"):
        filepath = proj_dir / folder / f"{slug}.md"

# New:
def read_entry(project: str, slug: str) -> dict | None:
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for cfg in _vc.ENTRY_TYPE_CONFIG.values():
        filepath = proj_dir / cfg["folder"] / f"{slug}.md"
```

**Change C:** In `update_entry_status()`, replace the hardcoded folder tuple:

```python
# Old:
    for folder in ("bugs", "ideas", "notes", "grill-me", "experiments"):
        filepath = proj_dir / folder / f"{slug}.md"

# New:
    for cfg in _vc.ENTRY_TYPE_CONFIG.values():
        filepath = proj_dir / cfg["folder"] / f"{slug}.md"
```

**Change D:** In `update_entry_status_generic()`, collapse the `elif entry_type == "experiment":` branch and the `else:` branch's `folder_map` into a single `elif`:

```python
# Old (lines 243–261):
    elif entry_type == "experiment":
        if new_status not in _vc.EXPERIMENT_STATUSES:
            return False
        if not project:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / "experiments"
    else:
        if new_status not in _vc.VALID_STATUSES:
            return False
        if not project:
            return False
        folder_map = {
            "bug": "bugs", "idea": "ideas", "note": "notes",
            "grill-me": "grill-me",
        }
        folder = folder_map.get(entry_type)
        if folder is None:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / folder

# New:
    elif entry_type in _vc.ENTRY_TYPE_CONFIG:
        cfg = _vc.ENTRY_TYPE_CONFIG[entry_type]
        if new_status not in cfg["valid_statuses"]:
            return False
        if not project:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / cfg["folder"]
    else:
        return False
```

- [ ] **Step 6: Run all vault_entries tests — all must pass including the 3 new ones**

```bash
docker cp app/services/vault_cache.py ikeos:/app/app/services/vault_cache.py
docker cp app/services/vault_entries.py ikeos:/app/app/services/vault_entries.py
docker cp tests/test_vault_entries.py ikeos:/app/tests/test_vault_entries.py
docker.exe exec ikeos pytest tests/test_vault_entries.py -v 2>&1 | tail -25
```

Expected: all PASSED (existing 9 + 3 new = 12 tests).

- [ ] **Step 7: Run the full test suite**

```bash
docker.exe exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: 261 passed, 0 failures.

- [ ] **Step 8: Commit**

```bash
git add app/services/vault_cache.py app/services/vault_entries.py \
        tests/test_vault_entries.py
git commit -m "refactor: introduce ENTRY_TYPE_CONFIG as single registry for vault entry types

Replaces independently maintained TYPE_FOLDERS and TYPE_TAGS dicts with
a unified ENTRY_TYPE_CONFIG that also carries initial_status and
valid_statuses per type. TYPE_FOLDERS and TYPE_TAGS are now derived
from the registry to preserve backward compatibility.

vault_entries.py no longer has hardcoded folder tuples in read_entry()
or update_entry_status(); both derive folders from ENTRY_TYPE_CONFIG.
update_entry_status_generic() collapses the separate experiment and
folder_map branches into a single generic ENTRY_TYPE_CONFIG lookup.

Adding a new project-scoped entry type now requires one ENTRY_TYPE_CONFIG
entry plus type-specific write_entry() metadata — no more scattered tuple updates."
```

---

## Task 2: Update `vault.py` re-export and `capture.py`; document decision

**Files:**
- Modify: `app/services/vault.py`
- Modify: `app/routes/capture.py`
- Modify: `.claude/DECISIONS.md`

- [ ] **Step 1: Add `ENTRY_TYPE_CONFIG` to `vault.py` re-exports**

Read `app/services/vault.py` first. In the `vault_cache` import block, add `ENTRY_TYPE_CONFIG`:

```python
from app.services.vault_cache import (  # noqa: F401
    VAULT_PATH,
    VALID_TYPES,
    VALID_STATUSES,
    DECISION_STATUSES,
    EXPERIMENT_STATUSES,
    ENTRY_TYPE_CONFIG,
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

Note: `EXPERIMENT_STATUSES` is also not currently re-exported — add it at the same time so it's accessible from the facade.

- [ ] **Step 2: Run tests — must still pass**

```bash
docker cp app/services/vault.py ikeos:/app/app/services/vault.py
docker.exe exec ikeos pytest tests/ -q 2>&1 | tail -3
```

Expected: 261 passed.

- [ ] **Step 3: Update `capture.py` — two changes**

Read `app/routes/capture.py` in full before editing.

**Change A:** Add `ENTRY_TYPE_CONFIG` and `DECISION_STATUSES` to the import from `app.services.vault`:

```python
from app.services.vault import (
    get_projects_with_meta, write_entry, update_entry_status_generic,
    update_housekeeping_fields, ENTRY_TYPE_CONFIG, DECISION_STATUSES,
)
```

**Change B:** In `patch_entries()`, replace the type check and valid_statuses ternary. Find this block:

```python
    # Validate entry_type
    if entry_type not in ("bug", "idea", "note", "decision", "grill-me", "experiment"):
        return jsonify({"error": "Invalid entry type"}), 400

    # Validate status against the lifecycle for this entry type
    valid_statuses = (
        ("proposed", "accepted", "rejected", "superseded") if entry_type == "decision"
        else ("running", "complete", "abandoned") if entry_type == "experiment"
        else ("new", "open", "in-progress", "done", "deferred")
    )
    if status not in valid_statuses:
        return jsonify({"error": f"Invalid status for {entry_type}"}), 400
```

Replace with:

```python
    # Validate entry_type
    _patch_valid_types = set(ENTRY_TYPE_CONFIG.keys()) | {"decision"}
    if entry_type not in _patch_valid_types:
        return jsonify({"error": "Invalid entry type"}), 400

    # Validate status against the lifecycle for this entry type
    if entry_type == "decision":
        valid_statuses = DECISION_STATUSES
    else:
        valid_statuses = ENTRY_TYPE_CONFIG[entry_type]["valid_statuses"]
    if status not in valid_statuses:
        return jsonify({"error": f"Invalid status for {entry_type}"}), 400
```

**Change C:** In `capture_json()`, replace the type check:

```python
    # Old:
    if entry_type not in ("note", "idea", "bug", "grill-me", "housekeeping-task", "housekeeping-heartbeat", "experiment"):
        return jsonify({"error": "type must be note, idea, bug, grill-me, housekeeping-task, housekeeping-heartbeat, or experiment"}), 400

    # New:
    _capture_json_valid_types = set(ENTRY_TYPE_CONFIG.keys()) | {"housekeeping-task", "housekeeping-heartbeat"}
    if entry_type not in _capture_json_valid_types:
        valid_list = ", ".join(sorted(_capture_json_valid_types))
        return jsonify({"error": f"type must be one of: {valid_list}"}), 400
```

- [ ] **Step 4: Run the full test suite**

```bash
docker cp app/services/vault.py ikeos:/app/app/services/vault.py
docker cp app/routes/capture.py ikeos:/app/app/routes/capture.py
docker.exe exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: 261 passed, 0 failures.

- [ ] **Step 5: Append decision to `.claude/DECISIONS.md`**

Read `.claude/DECISIONS.md` first to confirm the last entry, then append:

```markdown

## 2026-06-27: ENTRY_TYPE_CONFIG is the single registry for project-scoped vault types

`vault_cache.py` now contains `ENTRY_TYPE_CONFIG`, a dict mapping each project-scoped entry type (`note`, `idea`, `bug`, `grill-me`, `experiment`) to its folder, tag, initial status, and valid statuses. `TYPE_FOLDERS` and `TYPE_TAGS` are derived from it. `vault_entries.py` uses `ENTRY_TYPE_CONFIG.values()` for folder scans in `read_entry()` and `update_entry_status()`; `update_entry_status_generic()` uses a single `elif entry_type in ENTRY_TYPE_CONFIG:` branch. `capture.py` derives the PATCH endpoint's valid-type set and per-type valid statuses from the registry. Decisions and housekeeping types retain separate code paths (different storage layouts). Adding a new project-scoped type now requires: one entry in `ENTRY_TYPE_CONFIG`, one `elif` block in `write_entry()` for type-specific metadata fields, and UI changes (form radio + capture_json type list).
```

- [ ] **Step 6: Rebuild and verify**

```bash
docker.exe compose up --build -d ikeos 2>&1 | tail -3
```

Wait a few seconds then:

```bash
curl -s http://localhost:5009/health
```

Expected: `ok`

Verify experiment PATCH still works end-to-end:

```bash
# Create an experiment entry
curl -s -X POST http://localhost:5009/capture/json \
  -H "Content-Type: application/json" \
  -d '{"type":"experiment","project":"ikeos","title":"Registry Test","body":"","hypothesis":"H","expected_outcome":"O","measurement":"M","success_criteria":"S","timebox":"1 session"}' \
  | python3 -m json.tool
```

Expected: `{"ok": true}`

Then patch it to complete (replace FILENAME with the slug shown in the experiments folder):

```bash
ls /mnt/c/Server/obsidian-vault/projects/ikeos/experiments/ | tail -1
```

```bash
curl -s -X PATCH http://localhost:5009/entries \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=ikeos" -d "type=experiment" \
  -d "filename=<slug-from-above>" -d "status=complete"
```

Expected: `{"message": "Status updated"}`

- [ ] **Step 7: Commit**

```bash
git add app/services/vault.py app/routes/capture.py .claude/DECISIONS.md
git commit -m "refactor: derive capture.py type sets and valid_statuses from ENTRY_TYPE_CONFIG

patch_entries() type check now uses set(ENTRY_TYPE_CONFIG.keys()) | {'decision'};
valid_statuses comes from ENTRY_TYPE_CONFIG[entry_type]['valid_statuses'] instead
of a hardcoded ternary. capture_json() type check similarly derives from
ENTRY_TYPE_CONFIG.keys() plus the housekeeping special types.
vault.py re-exports ENTRY_TYPE_CONFIG and EXPERIMENT_STATUSES."
```

---

## Task 3: Session 6 'Imi Output

At the conclusion of every 'Imi session, produce the 8-section output directly to the user (do not commit it as a file).

- [ ] **Step 1: Produce Session 6 output**

Answer each heading:

**Executive Summary** — What was accomplished? What did we learn?

**Files Changed** — Every file modified or created, one-line description.

**Architectural Decisions** — New entries added to DECISIONS.md.

**Public Release Progress** — Which open audit items are now resolved?

**Technical Debt** — What shortcuts were taken deliberately?

**Lessons Learned** — What was surprising or non-obvious?

**Platform Health Observations** — What is in good shape? What is fragile?

**Highest ROI Next Task** — One sentence: what should Session 7 start with?

---

## Verification Contract

Session 6 is done when:

- [ ] `docker exec ikeos pytest tests/ -q` shows 261 passed, 0 failures
- [ ] `python3 -c "from app.services.vault_cache import ENTRY_TYPE_CONFIG, TYPE_FOLDERS, TYPE_TAGS; assert TYPE_FOLDERS == {k:v['folder'] for k,v in ENTRY_TYPE_CONFIG.items()}; assert TYPE_TAGS == {k:v['tag'] for k,v in ENTRY_TYPE_CONFIG.items()}; print('ok')"` prints `ok`
- [ ] A new experiment entry can be created via `POST /capture/json` and patched to `complete` via `PATCH /entries` after the rebuild
- [ ] `ENTRY_TYPE_CONFIG` and `DECISION_STATUSES` are importable via `from app.services.vault import ENTRY_TYPE_CONFIG, DECISION_STATUSES`
- [ ] `DECISIONS.md` has the new registry consolidation entry
