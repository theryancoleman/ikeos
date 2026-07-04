# Project 'Imi Session 4 — vault.py Decomposition

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `app/services/vault.py` (718 lines) into four focused sub-modules plus a shared cache module, with a thin re-export facade maintaining full backward compatibility.

**Architecture:** A new `vault_cache.py` owns `VAULT_PATH`, shared constants, and cache state. Four sub-modules (`vault_projects.py`, `vault_entries.py`, `vault_graph.py`, `vault_housekeeping.py`) import cache state via module reference (`import app.services.vault_cache as _vc`) so that test patches on `vault_cache.VAULT_PATH` propagate correctly. `vault.py` becomes a thin facade that re-exports everything — zero changes required in routes. Existing tests are updated in Task 7 to patch `vault_cache.VAULT_PATH` instead of `vault.VAULT_PATH`.

**Tech Stack:** Python 3.11, Flask, python-frontmatter, pytest, Docker

---

## Critical reading before starting

Before any task, read:
- `app/services/vault.py` (718 lines — full source of truth for all functions)
- `tests/test_vault.py` (understand what's tested and how VAULT_PATH is patched)
- `app/routes/browse.py`, `app/routes/capture.py`, `app/routes/housekeeping.py` (import sites)

Key invariant: **all existing `from app.services.vault import X` imports must continue to work unchanged after this refactoring.** The routes and tests import from `vault` — the facade preserves this.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/services/vault_cache.py` | VAULT_PATH, constants, cache state, `_invalidate_cache()` |
| Create | `app/services/vault_projects.py` | `_read_project_meta`, `get_projects`, `get_projects_with_meta`, `write_project_meta` |
| Create | `app/services/vault_entries.py` | `_slugify`, `write_entry`, `_read_all_entries`, `read_entries`, `read_entry`, `update_entry_status`, `update_entry_status_generic` |
| Create | `app/services/vault_graph.py` | `_get_urgency`, `_read_hub_pages`, `get_vault_graph`, `write_hub_page`, `write_component_stub` |
| Create | `app/services/vault_housekeeping.py` | `update_housekeeping_fields`, `_compute_task_status`, `_compute_next_run`, `read_housekeeping_tasks`, `read_housekeeping_heartbeat`, `delete_housekeeping_task` |
| Replace | `app/services/vault.py` | Thin re-export facade — no functions, only imports |
| Create | `tests/test_vault_projects.py` | Isolated tests for vault_projects using `vault_cache.VAULT_PATH` patch |
| Create | `tests/test_vault_housekeeping.py` | Isolated tests for vault_housekeeping using `vault_cache.VAULT_PATH` patch |
| Modify | `tests/test_vault.py` | Update all `vault.VAULT_PATH` patches → `vault_cache.VAULT_PATH`; update cache references |
| Modify | `tests/test_browse.py` | Same patch update |
| Modify | `tests/test_capture.py` | Same patch update |
| Modify | `tests/test_housekeeping.py` | Same patch update |

---

## Why the cache lives in vault_cache.py

Sub-modules access `VAULT_PATH` via `import app.services.vault_cache as _vc` and then `_vc.VAULT_PATH`. This module-attribute access means patching `app.services.vault_cache.VAULT_PATH` in tests IS effective (Python resolves the attribute at call time, not at import time). If sub-modules used `from app.services.vault_cache import VAULT_PATH`, they'd get a local copy that patch couldn't affect.

---

## Task 1: Create vault_cache.py

**Files:**
- Create: `app/services/vault_cache.py`

This module owns all shared state. No other vault sub-module should define `VAULT_PATH` or cache globals.

- [x] **Step 1: Confirm baseline tests pass**

```bash
docker exec ikeos pytest tests/test_vault.py -q 2>&1 | tail -5
```

Expected: All tests pass (no failures). If any fail, stop and fix before proceeding.

- [x] **Step 2: Create `app/services/vault_cache.py`**

```python
import os
import time
from pathlib import Path

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))

VALID_TYPES = {
    "note", "idea", "bug", "decision",
    "grill-me", "housekeeping-task", "housekeeping-heartbeat",
}
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs", "grill-me": "grill-me"}
TYPE_TAGS = {
    "note": "documentation",
    "idea": "enhancement",
    "bug": "bug",
    "decision": "decision",
    "grill-me": "grill-me",
}

_TTL = 600.0  # 10 minutes

_projects_cache: list | None = None
_projects_cache_ts: float = 0.0

_entries_cache: list | None = None
_entries_cache_ts: float = 0.0

_hub_pages_cache: list | None = None
_hub_pages_cache_ts: float = 0.0


def _invalidate_cache() -> None:
    global _projects_cache, _projects_cache_ts
    global _entries_cache, _entries_cache_ts
    global _hub_pages_cache, _hub_pages_cache_ts
    _projects_cache = None
    _projects_cache_ts = 0.0
    _entries_cache = None
    _entries_cache_ts = 0.0
    _hub_pages_cache = None
    _hub_pages_cache_ts = 0.0
```

- [x] **Step 3: Verify vault_cache imports correctly**

```bash
docker exec ikeos python -c "from app.services.vault_cache import VAULT_PATH, _invalidate_cache, TYPE_FOLDERS; print('OK', VAULT_PATH)"
```

Expected: `OK /vault`

- [x] **Step 4: Confirm existing tests still pass (vault.py unchanged)**

```bash
docker exec ikeos pytest tests/test_vault.py -q 2>&1 | tail -5
```

Expected: all still pass.

- [x] **Step 5: Commit**

```bash
git add app/services/vault_cache.py
git commit -m "refactor: extract shared vault constants and cache state to vault_cache.py

Moves VAULT_PATH, type/status constants, and in-process cache globals
out of vault.py into a standalone vault_cache module. Sub-modules will
import via module reference to preserve test-patch semantics."
```

---

## Task 2: Create vault_projects.py

**Files:**
- Create: `app/services/vault_projects.py`
- Create: `tests/test_vault_projects.py`

Moves `_read_project_meta`, `get_projects`, `get_projects_with_meta`, `write_project_meta` from vault.py into a dedicated module. vault.py is NOT changed in this task.

- [x] **Step 1: Write failing tests for vault_projects**

Create `tests/test_vault_projects.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import patch
import frontmatter as fm
import app.services.vault_cache as _vc


@pytest.fixture(autouse=True)
def reset_cache():
    _vc._invalidate_cache()
    yield
    _vc._invalidate_cache()


def test_get_projects_returns_sorted_list(tmp_path):
    (tmp_path / "projects" / "alpha").mkdir(parents=True)
    (tmp_path / "projects" / "beta").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects
        result = get_projects()
    assert result == ["alpha", "beta"]


def test_get_projects_empty_when_no_dir(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects
        result = get_projects()
    assert result == []


def test_get_projects_with_meta_returns_name_from_project_md(tmp_path):
    proj_dir = tmp_path / "projects" / "myproj"
    proj_dir.mkdir(parents=True)
    meta = fm.Post("", name="My Project", description="desc", hidden=False)
    (proj_dir / "project.md").write_text(fm.dumps(meta))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects_with_meta
        result = get_projects_with_meta()
    assert len(result) == 1
    assert result[0]["name"] == "My Project"
    assert result[0]["slug"] == "myproj"


def test_get_projects_with_meta_excludes_hidden_by_default(tmp_path):
    proj_dir = tmp_path / "projects" / "hidden-proj"
    proj_dir.mkdir(parents=True)
    meta = fm.Post("", name="Hidden", description="", hidden=True)
    (proj_dir / "project.md").write_text(fm.dumps(meta))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects_with_meta
        result = get_projects_with_meta()
    assert result == []


def test_write_project_meta_creates_project_md(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import write_project_meta
        result = write_project_meta("myproj", "My Project", "A description", False)
    assert result is True
    post = fm.load(tmp_path / "projects" / "myproj" / "project.md")
    assert post.metadata["name"] == "My Project"
    assert post.metadata["description"] == "A description"
```

- [x] **Step 2: Run tests to confirm they fail**

```bash
docker exec ikeos pytest tests/test_vault_projects.py -v 2>&1 | tail -15
```

Expected: `ModuleNotFoundError: No module named 'app.services.vault_projects'`

- [x] **Step 3: Create `app/services/vault_projects.py`**

```python
import time

import frontmatter

import app.services.vault_cache as _vc


def _read_project_meta(slug: str) -> dict:
    meta_file = _vc.VAULT_PATH / "projects" / slug / "project.md"
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


def get_projects() -> list[str]:
    projects_dir = _vc.VAULT_PATH / "projects"
    if not projects_dir.exists():
        return []
    return sorted(d.name for d in projects_dir.iterdir() if d.is_dir())


def get_projects_with_meta(include_hidden: bool = False) -> list[dict]:
    now = time.monotonic()
    if _vc._projects_cache is not None and (now - _vc._projects_cache_ts) < _vc._TTL:
        cached = _vc._projects_cache
    else:
        projects_dir = _vc.VAULT_PATH / "projects"
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
        _vc._projects_cache = cached
        _vc._projects_cache_ts = now
    if include_hidden:
        return list(cached)
    return [p for p in cached if not p["hidden"]]


def write_project_meta(slug: str, name: str, description: str, hidden: bool) -> bool:
    proj_dir = _vc.VAULT_PATH / "projects" / slug
    if not proj_dir.exists():
        return False
    meta_file = proj_dir / "project.md"
    post = frontmatter.Post("", name=name, description=description, hidden=hidden)
    with open(meta_file, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _vc._invalidate_cache()
    return True
```

- [x] **Step 4: Run tests — must pass**

```bash
docker exec ikeos pytest tests/test_vault_projects.py -v 2>&1 | tail -15
```

Expected: 5 PASSED

- [x] **Step 5: Confirm existing vault tests unchanged**

```bash
docker exec ikeos pytest tests/test_vault.py -q 2>&1 | tail -5
```

Expected: all pass (vault.py not yet modified).

- [x] **Step 6: Commit**

```bash
git add app/services/vault_projects.py tests/test_vault_projects.py
git commit -m "refactor: extract project vault functions into vault_projects.py

get_projects, get_projects_with_meta, write_project_meta, _read_project_meta
moved from vault.py (source still intact — facade update follows in Task 6).
Tests use vault_cache.VAULT_PATH patch directly."
```

---

## Task 3: Create vault_entries.py

**Files:**
- Create: `app/services/vault_entries.py`
- Create: `tests/test_vault_entries.py`

Moves `_slugify`, `write_entry`, `_read_all_entries`, `read_entries`, `read_entry`, `update_entry_status`, `update_entry_status_generic` from vault.py.

- [x] **Step 1: Write failing tests for vault_entries**

Create `tests/test_vault_entries.py`:

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


def test_write_entry_creates_note_in_notes_folder(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({"type": "note", "project": "myproj", "title": "Test note", "body": "Body"})
    files = list((tmp_path / "projects" / "myproj" / "notes").glob("*.md"))
    assert len(files) == 1


def test_write_entry_sets_status_new(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({"type": "note", "project": "myproj", "title": "Test", "body": ""})
    files = list((tmp_path / "projects" / "myproj" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["status"] == "new"


def test_write_entry_bug_includes_severity(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import write_entry
        write_entry({
            "type": "bug", "project": "myproj",
            "title": "Crash", "body": "It crashes", "severity": "high",
        })
    files = list((tmp_path / "projects" / "myproj" / "bugs").glob("*.md"))
    post = fm.load(files[0])
    assert post.metadata["severity"] == "high"


def test_read_entries_returns_all_types(tmp_path):
    for folder in ("bugs", "notes", "ideas"):
        d = tmp_path / "projects" / "myproj" / folder
        d.mkdir(parents=True)
        (d / "2026-01-01-entry.md").write_text(
            f"---\ntype: {folder[:-1]}\ntitle: T\nproject: myproj\n"
            "status: new\ncreated: 2026-01-01T00:00:00\ntags: []\n---\n## Description\n"
        )
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import read_entries, _invalidate_cache
        _invalidate_cache()
        result = read_entries(project="myproj")
    assert len(result) == 3


def test_update_entry_status_generic_changes_status(tmp_path):
    notes_dir = tmp_path / "projects" / "myproj" / "notes"
    notes_dir.mkdir(parents=True)
    entry = fm.Post(
        "## Description\nbody\n",
        type="note", title="T", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["documentation", "myproj", "status/new"],
    )
    (notes_dir / "2026-01-01-t.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status_generic
        result = update_entry_status_generic("note", "myproj", "2026-01-01-t", "open")
    assert result is True
    post = fm.load(notes_dir / "2026-01-01-t.md")
    assert post.metadata["status"] == "open"
    assert "status/open" in post.metadata["tags"]
```

- [x] **Step 2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_vault_entries.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'app.services.vault_entries'`

- [x] **Step 3: Create `app/services/vault_entries.py`**

Copy the following functions verbatim from `app/services/vault.py` with ONE change: replace all bare `VAULT_PATH` references with `_vc.VAULT_PATH`, all `_invalidate_cache()` with `_vc._invalidate_cache()`, and all `VALID_TYPES/VALID_STATUSES/DECISION_STATUSES/TYPE_FOLDERS/TYPE_TAGS` with `_vc.` prefix. Also replace `get_projects()` with a call imported from `vault_projects`.

```python
import logging
import re
import time
from datetime import datetime

import frontmatter

import app.services.vault_cache as _vc
from app.services.vault_projects import get_projects
from app.services.umbrella import get_umbrella_name

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]


def write_entry(data: dict) -> str:
    entry_type = data["type"]
    project = data.get("project", "")
    title = data["title"]
    body = data.get("body", "")

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = f"{date_str}-{_slugify(title)}"

    if entry_type == "decision":
        target_dir = _vc.VAULT_PATH / "decisions"
        target_dir.mkdir(parents=True, exist_ok=True)
        tags = ["decision", "status/proposed"]
        if project:
            tags.append(project)
        metadata = {
            "type": "decision",
            "title": title,
            "status": "proposed",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": tags,
        }
        if project:
            metadata["project"] = project
        content = f"## Context\n\n{body}\n\n## Decision\n\n\n## Consequences\n\n"
    elif entry_type == "housekeeping-task":
        project = data.get("project", "")
        target_dir = _vc.VAULT_PATH / "projects" / project / "housekeeping"
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
        _vc._invalidate_cache()
        return slug
    elif entry_type == "housekeeping-heartbeat":
        project = data.get("project", "")
        target_dir = _vc.VAULT_PATH / "projects" / project / "housekeeping"
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
        filepath = target_dir / "last-run.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        _vc._invalidate_cache()
        return "last-run"
    else:
        folder = _vc.TYPE_FOLDERS[entry_type]
        target_dir = _vc.VAULT_PATH / "projects" / project / folder
        target_dir.mkdir(parents=True, exist_ok=True)

        type_tag = _vc.TYPE_TAGS[entry_type]
        tags = [type_tag, project, "status/new"]
        if entry_type == "idea":
            tags.append(f"urgency/{data.get('priority', 'medium')}")
        elif entry_type == "bug":
            urgency = "critical" if data.get("severity") == "critical" else data.get("severity", "medium")
            tags.append(f"urgency/{urgency}")
        for domain in data.get("domains", []):
            tags.append(f"domain/{domain}")
        component = data.get("component", "").strip()
        if component:
            tags.append(f"component/{component}")

        metadata = {
            "type": entry_type,
            "title": title,
            "project": project,
            "status": "new",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": tags,
        }
        if component:
            metadata["component"] = component
        description = data.get("description", "").strip()
        if description:
            metadata["description"] = description

        if entry_type == "idea":
            metadata["priority"] = data.get("priority", "medium")
            metadata["effort"] = data.get("effort", "medium")
            why = data.get("why", "").strip()
            if why:
                metadata["why"] = why
        elif entry_type == "bug":
            metadata["severity"] = data.get("severity", "medium")

        content = f"## Description\n{body}\n"
        if entry_type == "bug" and data.get("steps"):
            content += f"\n## Steps to reproduce\n{data['steps']}\n"
        if component:
            content += f"\n---\n[[{get_umbrella_name(project)}]]\n"

    post = frontmatter.Post(content, **metadata)
    filepath = target_dir / f"{slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _vc._invalidate_cache()
    return slug


def _read_all_entries() -> list[dict]:
    entries = []
    for proj in get_projects():
        proj_dir = _vc.VAULT_PATH / "projects" / proj
        for folder in set(_vc.TYPE_FOLDERS.values()):
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


def read_entries(project: str = None, status_filter: list = None, component: str = None) -> list[dict]:
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
    return entries


def read_entry(project: str, slug: str) -> dict | None:
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes", "grill-me"):
        filepath = proj_dir / folder / f"{slug}.md"
        if filepath.exists():
            post = frontmatter.load(filepath)
            entry = dict(post.metadata)
            if hasattr(entry.get("created"), "isoformat"):
                entry["created"] = entry["created"].isoformat(timespec="seconds")
            entry["body"] = post.content
            entry["slug"] = slug
            return entry
    return None


def update_entry_status(project: str, slug: str, new_status: str) -> bool:
    if new_status not in _vc.VALID_STATUSES:
        return False
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes", "grill-me"):
        filepath = proj_dir / folder / f"{slug}.md"
        if filepath.exists():
            post = frontmatter.load(filepath)
            post.metadata["status"] = new_status
            post.metadata["updated"] = datetime.now().isoformat(timespec="seconds")
            tags = [t for t in post.metadata.get("tags", []) if not t.startswith("status/")]
            tags.append(f"status/{new_status}")
            post.metadata["tags"] = tags
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
            _vc._invalidate_cache()
            return True
    return False


def update_entry_status_generic(entry_type: str, project: str | None, filename: str, new_status: str) -> bool:
    if entry_type == "decision":
        if new_status not in _vc.DECISION_STATUSES:
            return False
        base_path = _vc.VAULT_PATH / "decisions"
    else:
        if new_status not in _vc.VALID_STATUSES:
            return False
        if not project:
            return False
        folder_map = {"bug": "bugs", "idea": "ideas", "note": "notes", "grill-me": "grill-me"}
        folder = folder_map.get(entry_type)
        if folder is None:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / folder

    filepath = base_path / (filename if filename.endswith(".md") else f"{filename}.md")
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
        _vc._invalidate_cache()
        return True
    except Exception:
        return False
```

- [x] **Step 4: Run vault_entries tests — must pass**

```bash
docker exec ikeos pytest tests/test_vault_entries.py -v 2>&1 | tail -15
```

Expected: 5 PASSED

- [x] **Step 5: Confirm existing test_vault.py still passes**

```bash
docker exec ikeos pytest tests/test_vault.py -q 2>&1 | tail -5
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add app/services/vault_entries.py tests/test_vault_entries.py
git commit -m "refactor: extract entry vault functions into vault_entries.py

write_entry, read_entries, read_entry, update_entry_status,
update_entry_status_generic, _slugify moved from vault.py.
All cache/VAULT_PATH access via vault_cache module reference."
```

---

## Task 4: Create vault_graph.py

**Files:**
- Create: `app/services/vault_graph.py`
- Create: `tests/test_vault_graph.py`

Moves `_WIKILINK_RE`, `_STALE_DAYS`, `_get_urgency`, `_read_hub_pages`, `get_vault_graph`, `write_hub_page`, `write_component_stub` from vault.py.

- [x] **Step 1: Write failing tests for vault_graph**

Create `tests/test_vault_graph.py`:

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


def test_get_vault_graph_returns_expected_structure(tmp_path):
    (tmp_path / "projects" / "myproj" / "notes").mkdir(parents=True)
    (tmp_path / "projects" / "myproj" / "notes" / "2026-01-01-note.md").write_text(
        "---\ntype: note\ntitle: My Note\nproject: myproj\n"
        "status: new\ncreated: 2026-01-01T00:00:00\ntags: []\n---\n## Description\nHello\n"
    )
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_graph import get_vault_graph
        result = get_vault_graph()
    assert "nodes" in result
    assert "links" in result
    assert "health" in result
    assert any(n["id"] == "2026-01-01-note" for n in result["nodes"])


def test_write_hub_page_creates_hub_file(tmp_path):
    (tmp_path / "projects" / "myplatform").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_graph import write_hub_page
        write_hub_page("myplatform", "My Platform", ["api", "worker"])
    files = list((tmp_path / "projects" / "myplatform").glob("*.md"))
    assert any(f.name == "My Platform.md" for f in files)
    post = fm.load(tmp_path / "projects" / "myplatform" / "My Platform.md")
    assert post.metadata["type"] == "hub"


def test_write_component_stub_creates_stub(tmp_path):
    (tmp_path / "projects" / "myplatform").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_graph import write_component_stub
        write_component_stub("myplatform", "api")
    stubs_dir = tmp_path / "projects" / "myplatform" / "components"
    assert (stubs_dir / "api.md").exists()
```

- [x] **Step 2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_vault_graph.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'app.services.vault_graph'`

- [x] **Step 3: Create `app/services/vault_graph.py`**

```python
import logging
import re
import time
from datetime import datetime, timezone

import frontmatter

import app.services.vault_cache as _vc
from app.services.vault_entries import read_entries
from app.services.umbrella import get_umbrella_name

logger = logging.getLogger(__name__)

_WIKILINK_RE = re.compile(r'\[\[([^\]|]+)')
_STALE_DAYS = 30


def _get_urgency(entry: dict) -> str:
    for tag in entry.get("tags", []):
        if tag.startswith("urgency/"):
            return tag.split("/", 1)[1]
    sev = entry.get("severity") or entry.get("priority")
    if sev in ("critical", "high", "medium", "low"):
        return sev
    return "medium"


def _read_hub_pages() -> list[dict]:
    now = time.monotonic()
    if _vc._hub_pages_cache is not None and (now - _vc._hub_pages_cache_ts) < _vc._TTL:
        return _vc._hub_pages_cache

    pages = []
    projects_dir = _vc.VAULT_PATH / "projects"
    if not projects_dir.exists():
        _vc._hub_pages_cache = pages
        _vc._hub_pages_cache_ts = now
        return pages
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
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
            except Exception as e:
                logger.warning("Failed to parse hub page %s: %s", candidate, e)
        stubs_dir = proj_dir / "components"
        if stubs_dir.exists():
            for stub_file in stubs_dir.glob("*.md"):
                try:
                    post = frontmatter.load(stub_file)
                    entry = dict(post.metadata)
                    entry["body"] = post.content
                    entry["slug"] = stub_file.stem
                    pages.append(entry)
                except Exception as e:
                    logger.warning("Failed to parse component stub %s: %s", stub_file, e)
    _vc._hub_pages_cache = pages
    _vc._hub_pages_cache_ts = now
    return pages


def get_vault_graph() -> dict:
    entries = read_entries()
    hub_pages = _read_hub_pages()
    all_items = entries + hub_pages
    slug_set = {e["slug"] for e in all_items}

    nodes = []
    links = []
    untriaged = []
    stale = []
    broken_links = []

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for entry in all_items:
        slug = entry["slug"]
        nodes.append({
            "id": slug,
            "title": entry.get("title", slug),
            "type": entry.get("type", "note"),
            "status": entry.get("status", ""),
            "project": entry.get("project", ""),
            "urgency": _get_urgency(entry),
        })
        if entry.get("type") not in ("hub", "component"):
            if entry.get("status") == "new":
                untriaged.append({
                    "slug": slug,
                    "title": entry.get("title", slug),
                    "project": entry.get("project", ""),
                    "type": entry.get("type", "note"),
                })
            if entry.get("status") in ("open", "in-progress"):
                ref_date_raw = entry.get("updated") or entry.get("created", "")
                try:
                    if isinstance(ref_date_raw, datetime):
                        ref_date = ref_date_raw
                    else:
                        ref_date = datetime.fromisoformat(ref_date_raw)
                    ref_date = ref_date.replace(tzinfo=None) if ref_date.tzinfo else ref_date
                    days_stale = (now - ref_date).days
                    if days_stale >= _STALE_DAYS:
                        stale.append({
                            "slug": slug,
                            "title": entry.get("title", slug),
                            "project": entry.get("project", ""),
                            "type": entry.get("type", "note"),
                            "status": entry.get("status", ""),
                            "days_stale": days_stale,
                        })
                except (ValueError, TypeError):
                    pass
        body = entry.get("body", "")
        for ref in _WIKILINK_RE.findall(body):
            ref = ref.strip()
            if not ref or ref == slug:
                continue
            if ref in slug_set:
                links.append({"source": slug, "target": ref})
            else:
                broken_links.append({
                    "source_slug": slug,
                    "source_title": entry.get("title", slug),
                    "source_project": entry.get("project", ""),
                    "broken_ref": ref,
                })

    return {
        "nodes": nodes,
        "links": links,
        "health": {
            "untriaged": untriaged,
            "stale": stale,
            "broken_links": broken_links,
        },
    }


def write_hub_page(umbrella_slug: str, umbrella_name: str, components: list[str]) -> None:
    proj_dir = _vc.VAULT_PATH / "projects" / umbrella_slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    component_links = " · ".join(f"[[{c}]]" for c in components) if components else ""
    content = f"# {umbrella_name}\n\n"
    if component_links:
        content += f"**Components:** {component_links}\n\n"
    metadata = {
        "type": "hub",
        "title": umbrella_name,
        "project": umbrella_slug,
        "tags": ["hub", f"project/{umbrella_slug}"],
    }
    post = frontmatter.Post(content, **metadata)
    filepath = proj_dir / f"{umbrella_name}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _vc._invalidate_cache()


def write_component_stub(umbrella_slug: str, component_slug: str) -> None:
    stubs_dir = _vc.VAULT_PATH / "projects" / umbrella_slug / "components"
    stubs_dir.mkdir(parents=True, exist_ok=True)
    content = f"# {component_slug}\n\n[[{get_umbrella_name(umbrella_slug)}]]\n"
    metadata = {
        "type": "component",
        "title": component_slug,
        "project": umbrella_slug,
        "tags": ["component", f"umbrella/{umbrella_slug}"],
    }
    post = frontmatter.Post(content, **metadata)
    filepath = stubs_dir / f"{component_slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _vc._invalidate_cache()
```

- [x] **Step 4: Run tests — must pass**

```bash
docker exec ikeos pytest tests/test_vault_graph.py -v 2>&1 | tail -10
```

Expected: 3 PASSED

- [x] **Step 5: Confirm existing tests still pass**

```bash
docker exec ikeos pytest tests/test_vault.py -q 2>&1 | tail -5
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add app/services/vault_graph.py tests/test_vault_graph.py
git commit -m "refactor: extract graph and hub-page vault functions into vault_graph.py

_read_hub_pages, get_vault_graph, write_hub_page, write_component_stub
moved from vault.py. _get_urgency helper included."
```

---

## Task 5: Create vault_housekeeping.py

**Files:**
- Create: `app/services/vault_housekeeping.py`
- Create: `tests/test_vault_housekeeping.py`

Moves all housekeeping vault functions (lines 512–718 of vault.py) into a dedicated module.

- [x] **Step 1: Write failing tests for vault_housekeeping**

Create `tests/test_vault_housekeeping.py`:

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


def _write_task(path, filename, enabled="true", last_run="null", failures="0", interval="weekly"):
    task = fm.Post(
        "## Instructions\nDo the thing.\n",
        title="Test Task",
        type="housekeeping-task",
        project="myproj",
        interval=interval,
        enabled=enabled,
        success_definition="",
        last_run=last_run,
        last_error="null",
        consecutive_failures=failures,
        created="2026-01-01T00:00:00",
        tags=["housekeeping-task", "myproj", "status/enabled"],
    )
    path.mkdir(parents=True, exist_ok=True)
    (path / filename).write_text(fm.dumps(task))


def test_read_housekeeping_tasks_returns_list(tmp_path):
    hk_dir = tmp_path / "projects" / "myproj" / "housekeeping"
    _write_task(hk_dir, "2026-01-01-test.md")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import read_housekeeping_tasks
        result = read_housekeeping_tasks("myproj")
    assert len(result) == 1
    assert result[0]["title"] == "Test Task"


def test_compute_task_status_due_when_never_run(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import _compute_task_status
        status = _compute_task_status({"enabled": "true", "last_run": "null", "interval": "weekly"})
    assert status == "due"


def test_compute_task_status_disabled(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import _compute_task_status
        status = _compute_task_status({"enabled": "false", "last_run": "null", "interval": "weekly"})
    assert status == "disabled"


def test_update_housekeeping_fields_updates_last_run(tmp_path):
    hk_dir = tmp_path / "projects" / "myproj" / "housekeeping"
    _write_task(hk_dir, "2026-01-01-test.md")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import update_housekeeping_fields
        result = update_housekeeping_fields(
            "housekeeping-task", "myproj", "2026-01-01-test",
            {"last_run": "2026-06-27T10:00:00"},
        )
    assert result is True
    post = fm.load(hk_dir / "2026-01-01-test.md")
    assert post.metadata["last_run"] == "2026-06-27T10:00:00"


def test_delete_housekeeping_task_removes_file(tmp_path):
    hk_dir = tmp_path / "projects" / "myproj" / "housekeeping"
    _write_task(hk_dir, "2026-01-01-test.md")
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_housekeeping import delete_housekeeping_task
        result = delete_housekeeping_task("myproj", "2026-01-01-test")
    assert result is True
    assert not (hk_dir / "2026-01-01-test.md").exists()
```

- [x] **Step 2: Run to confirm failure**

```bash
docker exec ikeos pytest tests/test_vault_housekeeping.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'app.services.vault_housekeeping'`

- [x] **Step 3: Create `app/services/vault_housekeeping.py`**

```python
import logging
from datetime import datetime, timedelta

import frontmatter

import app.services.vault_cache as _vc

logger = logging.getLogger(__name__)

_HOUSEKEEPING_ALLOWED_FIELDS: dict[str, set[str]] = {
    "housekeeping-task": {"enabled", "last_run", "last_error", "consecutive_failures", "success_definition"},
    "housekeeping-heartbeat": {"last_run", "tasks_run", "tasks_failed", "tasks_skipped"},
}

_INTERVAL_THRESHOLDS: dict[str, int] = {
    "weekly": 6,
    "monthly": 27,
    "quarterly": 83,
    "annually": 364,
}


def _compute_task_status(task: dict) -> str:
    if task.get("enabled") != "true":
        return "disabled"
    if task.get("consecutive_failures", "0") != "0":
        return "error"
    last_run = task.get("last_run", "null")
    if last_run == "null" or last_run is None:
        return "due" if task.get("interval") == "weekly" else "uninitialized"
    threshold = _INTERVAL_THRESHOLDS.get(task.get("interval", "weekly"), 6)
    try:
        last_run_dt = datetime.fromisoformat(last_run) if isinstance(last_run, str) else last_run
        days_since = (datetime.now() - last_run_dt.replace(tzinfo=None)).days
        if days_since >= threshold + 3:
            return "overdue"
        if days_since >= threshold:
            return "due"
        return "ok"
    except (ValueError, TypeError):
        return "unknown"


def _compute_next_run(task: dict) -> str | None:
    last_run = task.get("last_run", "null")
    if last_run == "null" or last_run is None:
        return None
    threshold = _INTERVAL_THRESHOLDS.get(task.get("interval", "weekly"), 6)
    try:
        last_run_dt = datetime.fromisoformat(last_run) if isinstance(last_run, str) else last_run
        return (last_run_dt.replace(tzinfo=None) + timedelta(days=threshold)).date().isoformat()
    except (ValueError, TypeError):
        return None


def read_housekeeping_tasks(project: str) -> list[dict]:
    folder = _vc.VAULT_PATH / "projects" / project / "housekeeping"
    if not folder.exists():
        return []
    tasks = []
    for filepath in sorted(folder.glob("*.md")):
        if filepath.name == "last-run.md":
            continue
        try:
            post = frontmatter.load(filepath)
            if post.metadata.get("type") != "housekeeping-task":
                continue
            task = dict(post.metadata)
            task["filename"] = filepath.stem
            task["status"] = _compute_task_status(task)
            task["next_run"] = _compute_next_run(task)
            tasks.append(task)
        except Exception as e:
            logger.warning("Failed to parse housekeeping task %s: %s", filepath, e)
            continue
    return tasks


def read_housekeeping_heartbeat(project: str) -> dict:
    _safe: dict = {
        "last_run": None,
        "tasks_run": "0",
        "tasks_failed": "0",
        "tasks_skipped": "0",
    }
    filepath = _vc.VAULT_PATH / "projects" / project / "housekeeping" / "last-run.md"
    if not filepath.exists():
        return _safe.copy()
    try:
        post = frontmatter.load(filepath)
        data = dict(post.metadata)
        if data.get("last_run") in ("null", None, ""):
            data["last_run"] = None
        return {**_safe, **data}
    except Exception:
        return _safe.copy()


def update_housekeeping_fields(
    entry_type: str,
    project: str,
    filename: str,
    fields: dict,
) -> bool:
    allowed = _HOUSEKEEPING_ALLOWED_FIELDS.get(entry_type)
    if allowed is None:
        return False
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    if ".." in project or "/" in project or "\\" in project:
        return False
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    fname = filename if filename.endswith(".md") else f"{filename}.md"
    filepath = _vc.VAULT_PATH / "projects" / project / "housekeeping" / fname
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
        logger.exception(
            "Failed to update housekeeping fields for %s/%s/%s",
            entry_type, project, filename,
        )
        temp_filepath.unlink(missing_ok=True)
        return False


def delete_housekeeping_task(project: str, filename: str) -> bool:
    folder = _vc.VAULT_PATH / "projects" / project / "housekeeping"
    filepath = folder / f"{filename}.md"
    if not filepath.exists():
        return False
    if filepath.name == "last-run.md":
        return False
    try:
        post = frontmatter.load(filepath)
        if post.metadata.get("type") != "housekeeping-task":
            return False
    except Exception:
        return False
    filepath.unlink()
    return True
```

- [x] **Step 4: Run tests — must pass**

```bash
docker exec ikeos pytest tests/test_vault_housekeeping.py -v 2>&1 | tail -10
```

Expected: 5 PASSED

- [x] **Step 5: Confirm existing tests still pass**

```bash
docker exec ikeos pytest tests/test_vault.py tests/test_housekeeping.py -q 2>&1 | tail -5
```

Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add app/services/vault_housekeeping.py tests/test_vault_housekeeping.py
git commit -m "refactor: extract housekeeping vault functions into vault_housekeeping.py

update_housekeeping_fields, read_housekeeping_tasks, read_housekeeping_heartbeat,
delete_housekeeping_task, _compute_task_status, _compute_next_run moved from vault.py."
```

---

## Task 6: Replace vault.py with thin re-export facade

**Files:**
- Replace: `app/services/vault.py` (entire file)

vault.py becomes a pure re-export module. All existing `from app.services.vault import X` imports continue to work. No routes or route tests are changed here.

**Important:** After this task, the cache and VAULT_PATH live in `vault_cache.py`. Existing tests that patch `app.services.vault.VAULT_PATH` will begin to FAIL because sub-modules now reference `_vc.VAULT_PATH` (vault_cache.VAULT_PATH). This is expected — Task 7 fixes the tests.

- [x] **Step 1: Read current vault.py to confirm scope**

```bash
grep -c "^def " /mnt/c/Server/projects/ikeos/app/services/vault.py
```

Expected: 21 (confirm all 21 functions are accounted for in the sub-modules).

- [x] **Step 2: List all functions in each sub-module**

```bash
grep "^def " \
  app/services/vault_cache.py \
  app/services/vault_projects.py \
  app/services/vault_entries.py \
  app/services/vault_graph.py \
  app/services/vault_housekeeping.py
```

Verify these 21 names appear: `_invalidate_cache`, `_read_project_meta`, `get_projects`, `get_projects_with_meta`, `write_project_meta`, `_slugify`, `write_entry`, `_read_all_entries`, `read_entries`, `read_entry`, `update_entry_status`, `update_entry_status_generic`, `_get_urgency`, `_read_hub_pages`, `get_vault_graph`, `write_hub_page`, `write_component_stub`, `_compute_task_status`, `_compute_next_run`, `read_housekeeping_tasks`, `read_housekeeping_heartbeat`, `update_housekeeping_fields`, `delete_housekeeping_task`.

If any are missing, add them to the appropriate sub-module before proceeding.

- [x] **Step 3: Replace app/services/vault.py with facade**

Overwrite the file with exactly this content:

```python
# Public API — re-exports from vault sub-modules.
# All existing callers of `from app.services.vault import X` continue to work.
# To add new functions, implement them in the appropriate sub-module and re-export here.

from app.services.vault_cache import (  # noqa: F401
    VAULT_PATH,
    VALID_TYPES,
    VALID_STATUSES,
    DECISION_STATUSES,
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

from app.services.vault_projects import (  # noqa: F401
    _read_project_meta,
    get_projects,
    get_projects_with_meta,
    write_project_meta,
)

from app.services.vault_entries import (  # noqa: F401
    _slugify,
    write_entry,
    _read_all_entries,
    read_entries,
    read_entry,
    update_entry_status,
    update_entry_status_generic,
)

from app.services.vault_graph import (  # noqa: F401
    _WIKILINK_RE,
    _STALE_DAYS,
    _get_urgency,
    _read_hub_pages,
    get_vault_graph,
    write_hub_page,
    write_component_stub,
)

from app.services.vault_housekeeping import (  # noqa: F401
    _HOUSEKEEPING_ALLOWED_FIELDS,
    _INTERVAL_THRESHOLDS,
    _compute_task_status,
    _compute_next_run,
    read_housekeeping_tasks,
    read_housekeeping_heartbeat,
    update_housekeeping_fields,
    delete_housekeeping_task,
)
```

- [x] **Step 4: Verify imports work**

```bash
docker exec ikeos python -c "
from app.services.vault import (
    write_entry, read_entries, get_projects_with_meta,
    get_vault_graph, read_housekeeping_tasks, VAULT_PATH,
    _invalidate_cache, _compute_task_status,
)
print('All imports OK')
"
```

Expected: `All imports OK`

- [x] **Step 5: Run sub-module tests (should still pass)**

```bash
docker exec ikeos pytest tests/test_vault_projects.py tests/test_vault_entries.py tests/test_vault_graph.py tests/test_vault_housekeeping.py -q 2>&1 | tail -5
```

Expected: all pass.

- [x] **Step 6: Run original tests (expect failures — VAULT_PATH patch mismatch)**

```bash
docker exec ikeos pytest tests/test_vault.py -q 2>&1 | tail -20
```

Expected: some failures related to VAULT_PATH patching and cache attribute access. Note which tests fail — Task 7 will fix them.

- [x] **Step 7: Commit (with known test failures noted in message)**

```bash
git add app/services/vault.py
git commit -m "refactor: replace vault.py with thin re-export facade

vault.py now re-exports from vault_cache, vault_projects, vault_entries,
vault_graph, and vault_housekeeping. All public symbols preserved.
Existing tests that patch app.services.vault.VAULT_PATH will fail until
Task 7 updates them to patch app.services.vault_cache.VAULT_PATH."
```

---

## Task 7: Update existing tests to patch vault_cache.VAULT_PATH

**Files:**
- Modify: `tests/test_vault.py`
- Modify: `tests/test_browse.py`
- Modify: `tests/test_capture.py`
- Modify: `tests/test_housekeeping.py`
- Modify: `tests/conftest.py`

After this task, all tests must pass.

- [x] **Step 1: Find all VAULT_PATH patch locations**

```bash
grep -n "vault\.VAULT_PATH\|patch.*vault.*VAULT_PATH\|vault_mod\._\|patch\.object.*vault_mod" \
  tests/test_vault.py tests/test_browse.py tests/test_capture.py tests/test_housekeeping.py tests/conftest.py
```

Note every line number. Each occurrence needs the patch target updated.

- [x] **Step 2: Update test_vault.py — VAULT_PATH patches**

In `tests/test_vault.py`, replace ALL occurrences of:
- `patch("app.services.vault.VAULT_PATH"` → `patch("app.services.vault_cache.VAULT_PATH"`

Run this to verify the count before and after:
```bash
grep -c 'patch("app.services.vault.VAULT_PATH"' tests/test_vault.py
# note count
sed -i 's/patch("app\.services\.vault\.VAULT_PATH"/patch("app.services.vault_cache.VAULT_PATH"/g' tests/test_vault.py
grep -c 'patch("app.services.vault_cache.VAULT_PATH"' tests/test_vault.py
# counts must match
```

- [x] **Step 3: Update test_vault.py — vault_mod cache attribute access**

Find the test around line 362 that uses `patch.object(vault_mod, "VAULT_PATH", ...)` and accesses `vault_mod._hub_pages_cache` / `vault_mod._hub_pages_cache_ts`. This test tests hub-page caching behavior.

Read the test, then replace its vault_mod references with vault_cache references:

```python
# BEFORE (approximate — read the actual test first):
from app.services import vault as vault_mod
vault_mod._invalidate_cache()
with patch.object(vault_mod, "VAULT_PATH", tmp_path):
    result1 = vault_mod._read_hub_pages()
    ts_after_first = vault_mod._hub_pages_cache_ts
    ...
assert vault_mod._hub_pages_cache is not None

# AFTER:
import app.services.vault_cache as vault_cache_mod
from app.services.vault_graph import _read_hub_pages
vault_cache_mod._invalidate_cache()
with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
    result1 = _read_hub_pages()
    ts_after_first = vault_cache_mod._hub_pages_cache_ts
    result2 = _read_hub_pages()
    ts_after_second = vault_cache_mod._hub_pages_cache_ts
assert vault_cache_mod._hub_pages_cache is not None
```

Read the actual test before editing to ensure the replacement is exact.

- [x] **Step 4: Update test_browse.py**

```bash
grep -n "vault\.VAULT_PATH\|vault_cache" tests/test_browse.py
```

Replace all `patch("app.services.vault.VAULT_PATH"` with `patch("app.services.vault_cache.VAULT_PATH"` in test_browse.py:

```bash
sed -i 's/patch("app\.services\.vault\.VAULT_PATH"/patch("app.services.vault_cache.VAULT_PATH"/g' tests/test_browse.py
```

Also update the top-level import in test_browse.py:
```python
# BEFORE:
from app.services.vault import write_entry, read_entry, write_project_meta, _read_project_meta, _invalidate_cache

# AFTER (add vault_cache import):
from app.services.vault import write_entry, read_entry, write_project_meta, _read_project_meta, _invalidate_cache
import app.services.vault_cache  # noqa: F401 — needed for patch("app.services.vault_cache.VAULT_PATH")
```

(The existing `_invalidate_cache` import from vault still works because vault.py re-exports it.)

- [x] **Step 5: Update test_capture.py**

```bash
sed -i 's/patch("app\.services\.vault\.VAULT_PATH"/patch("app.services.vault_cache.VAULT_PATH"/g' tests/test_capture.py
```

- [x] **Step 6: Update test_housekeeping.py**

```bash
sed -i 's/patch("app\.services\.vault\.VAULT_PATH"/patch("app.services.vault_cache.VAULT_PATH"/g' tests/test_housekeeping.py
```

Also update any direct `_compute_task_status` or `_compute_next_run` imports in test_housekeeping.py — they currently import from `app.services.vault`. After the facade, these still work (vault.py re-exports them), so no change needed here. Verify:

```bash
grep "_compute_task_status\|_compute_next_run" tests/test_housekeeping.py
```

Expected: imports from `app.services.vault` — these still work via the facade.

- [x] **Step 7: Update tests/conftest.py if it patches VAULT_PATH**

```bash
grep -n "VAULT_PATH" tests/conftest.py
```

If any patch uses `vault.VAULT_PATH`, apply the same sed replacement.

- [x] **Step 8: Run ALL tests — must all pass**

```bash
docker exec ikeos pytest tests/ -q 2>&1 | tail -20
```

Expected: all tests pass, 0 failures. If any fail, read the error and fix the specific test before proceeding.

- [x] **Step 9: Commit**

```bash
git add tests/test_vault.py tests/test_browse.py tests/test_capture.py tests/test_housekeeping.py tests/conftest.py
git commit -m "refactor: update test patches from vault.VAULT_PATH to vault_cache.VAULT_PATH

After vault.py became a re-export facade, sub-modules reference VAULT_PATH
via vault_cache (module-attribute access for test-patch compatibility).
All tests updated to patch the canonical location."
```

---

## Task 8: Final verification and deploy

**Files:** None (verification only)

- [x] **Step 1: Run the full test suite one final time**

```bash
docker exec ikeos pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests pass.

- [x] **Step 2: Confirm vault.py has no function definitions**

```bash
grep "^def " /mnt/c/Server/projects/ikeos/app/services/vault.py
```

Expected: no output (vault.py is now a pure re-export file).

- [x] **Step 3: Confirm sub-module line counts are reasonable**

```bash
wc -l app/services/vault_cache.py app/services/vault_projects.py app/services/vault_entries.py app/services/vault_graph.py app/services/vault_housekeeping.py app/services/vault.py
```

Expected (approximate): cache ~50, projects ~70, entries ~200, graph ~130, housekeeping ~120, vault facade ~60. Total should be ~630 lines across 6 files vs 718 in the original single file.

- [x] **Step 4: Confirm app import works cleanly**

```bash
docker exec ikeos python -c "from app import create_app; app = create_app(); print('App factory OK')"
```

Expected: `App factory OK`

- [x] **Step 5: Rebuild container and smoke test**

```bash
docker.exe compose up --build -d ikeos 2>&1 | tail -10
sleep 5
curl -s http://localhost:5009/health
```

Expected: `{"status": "ok"}` or similar health response.

- [x] **Step 6: Commit the verification result (if any minor fixes were needed)**

If steps 1–5 required any fixes, commit them:

```bash
git add -p
git commit -m "fix: correct vault decomposition issues found during final verification"
```

If no fixes needed, no commit required.

---

## Verification Contract

Session 4 is done when:

- [x] `grep "^def " app/services/vault.py` returns empty (vault.py is a pure facade)
- [x] All 5 sub-module files exist: vault_cache.py, vault_projects.py, vault_entries.py, vault_graph.py, vault_housekeeping.py
- [x] `docker exec ikeos pytest tests/ -q` shows 0 failures
- [x] `curl -s http://localhost:5009/health` returns HTTP 200
- [x] `from app.services.vault import write_entry, read_entries, VAULT_PATH` works (backward compat preserved)

---

## Scope note

This plan covers vault.py decomposition only. The following are NOT in scope for Session 4 and belong in Session 5:
- `experiment` as a first-class vault entry type (add to VALID_TYPES, TYPE_FOLDERS, create experiments/ folder)
- Metrics instrumentation write paths (events.jsonl)
- Housekeeping permission-prompt bug fix
