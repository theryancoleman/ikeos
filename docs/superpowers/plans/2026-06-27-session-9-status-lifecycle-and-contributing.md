# Session 9 — Status Lifecycle Fix + CONTRIBUTING.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a correctness bug in `update_entry_status()` (the web-UI status update path) that permits invalid statuses for experiment entries, then produce `CONTRIBUTING.md` to complete Level B public release readiness.

**Architecture:** `update_entry_status()` currently validates `new_status` against `VALID_STATUSES` (the standard set) before finding the file. This means: (a) `"done"` succeeds on experiment entries (invalid — experiments use `running/complete/abandoned`), and (b) `"complete"` fails on experiments (valid experiment status rejected because it's not in `VALID_STATUSES`). The fix moves validation to after finding the file, using the `cfg["valid_statuses"]` from `ENTRY_TYPE_CONFIG` for each type. No new abstractions needed — `cfg` is already available in the loop. `CONTRIBUTING.md` is a new file at the repo root covering prerequisites, running tests, vault structure, adding a project, and the TASK.md workflow.

**Tech Stack:** Python 3.11, Flask, pytest, Docker

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/services/vault_entries.py` | Fix `update_entry_status()` — per-type lifecycle validation |
| Modify | `tests/test_vault_entries.py` | Add 3 sentinel tests for the lifecycle fix |
| Create | `CONTRIBUTING.md` | Contributor guide: setup, vault structure, tests, adding types |
| Modify | `.claude/DECISIONS.md` | Document the lifecycle fix decision |

---

## Critical reading before starting

- `app/services/vault_entries.py` — understand `update_entry_status()` (lines 216–233): the upfront `if new_status not in _vc.VALID_STATUSES: return False` is what must change
- `app/services/vault_cache.py` — understand `ENTRY_TYPE_CONFIG`: each type has a `valid_statuses` key (either `VALID_STATUSES` or `EXPERIMENT_STATUSES`)
- `tests/test_vault_entries.py` — understand the existing test patterns (lines 141–157 show the experiment test structure to follow for new tests)
- `README.md` — read before writing CONTRIBUTING.md to avoid duplication; CONTRIBUTING.md supplements, not replaces

---

## Task 1: Fix `update_entry_status()` per-type lifecycle enforcement

**Files:**
- Modify: `app/services/vault_entries.py`
- Modify: `tests/test_vault_entries.py`
- Modify: `.claude/DECISIONS.md`

### The bug

```python
# Current (buggy) — validates against VALID_STATUSES before finding the file:
def update_entry_status(project: str, slug: str, new_status: str) -> bool:
    if new_status not in _vc.VALID_STATUSES:   # "running" rejected, "done" accepted for ALL types
        return False
    ...
```

The caller is `browse.py:100` — the web UI status dropdown at `POST /projects/<name>/<slug>/status`. Experiments created with `status: running` cannot be advanced to `complete` via the UI (rejected). Standard entries can be accidentally set to experiment-only statuses if they somehow appear in the form.

### The fix

Move validation to after finding the file, using the per-type `cfg["valid_statuses"]`:

```python
def update_entry_status(project: str, slug: str, new_status: str) -> bool:
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for cfg in _vc.ENTRY_TYPE_CONFIG.values():
        filepath = proj_dir / cfg["folder"] / f"{slug}.md"
        if filepath.exists():
            if new_status not in cfg["valid_statuses"]:
                return False
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
```

- [x] **Step 1: Write three failing tests**

Add to `tests/test_vault_entries.py` after `test_capture_json_valid_types_constant_exists_and_is_correct` (the last existing test):

```python
def test_update_entry_status_rejects_standard_status_for_experiment(tmp_path):
    """'done' is a valid VALID_STATUS but not a valid experiment status."""
    exp_dir = tmp_path / "projects" / "myproj" / "experiments"
    exp_dir.mkdir(parents=True)
    entry = fm.Post(
        "body",
        type="experiment", title="E", project="myproj",
        status="running", created="2026-01-01T00:00:00",
        tags=["experiment", "myproj", "status/running"],
    )
    (exp_dir / "2026-01-01-e.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status
        result = update_entry_status("myproj", "2026-01-01-e", "done")
    assert result is False, "update_entry_status must reject 'done' for experiments"


def test_update_entry_status_accepts_experiment_status_for_experiment(tmp_path):
    """'complete' is a valid experiment status and must be accepted."""
    exp_dir = tmp_path / "projects" / "myproj" / "experiments"
    exp_dir.mkdir(parents=True)
    entry = fm.Post(
        "body",
        type="experiment", title="E", project="myproj",
        status="running", created="2026-01-01T00:00:00",
        tags=["experiment", "myproj", "status/running"],
    )
    (exp_dir / "2026-01-01-e.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status
        result = update_entry_status("myproj", "2026-01-01-e", "complete")
    assert result is True
    post = fm.load(exp_dir / "2026-01-01-e.md")
    assert post.metadata["status"] == "complete"
    assert "status/complete" in post.metadata["tags"]


def test_update_entry_status_rejects_experiment_status_for_note(tmp_path):
    """'running' is a valid experiment status but not valid for a note."""
    note_dir = tmp_path / "projects" / "myproj" / "notes"
    note_dir.mkdir(parents=True)
    entry = fm.Post(
        "body",
        type="note", title="N", project="myproj",
        status="new", created="2026-01-01T00:00:00",
        tags=["documentation", "myproj", "status/new"],
    )
    (note_dir / "2026-01-01-n.md").write_text(fm.dumps(entry))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_entries import update_entry_status
        result = update_entry_status("myproj", "2026-01-01-n", "running")
    assert result is False, "update_entry_status must reject 'running' for notes"
```

- [x] **Step 2: Run failing tests**

```bash
docker cp tests/test_vault_entries.py ikeos:/app/tests/test_vault_entries.py
docker.exe exec ikeos pytest tests/test_vault_entries.py::test_update_entry_status_rejects_standard_status_for_experiment tests/test_vault_entries.py::test_update_entry_status_accepts_experiment_status_for_experiment tests/test_vault_entries.py::test_update_entry_status_rejects_experiment_status_for_note -v 2>&1 | tail -15
```

Expected:
- `test_update_entry_status_rejects_standard_status_for_experiment` — FAILED (currently passes `"done"` incorrectly)
- `test_update_entry_status_accepts_experiment_status_for_experiment` — FAILED (`"complete"` is incorrectly rejected)
- `test_update_entry_status_rejects_experiment_status_for_note` — FAILED (`"running"` is incorrectly accepted since it's not in `VALID_STATUSES`... actually wait — `"running"` IS not in `VALID_STATUSES`, so this test may PASS already)

Note: The third test (`_rejects_experiment_status_for_note`) may already pass because `"running"` is not in `VALID_STATUSES`. That's fine — it documents the intended behaviour. The first two are the meaningful regressions.

- [x] **Step 3: Fix `update_entry_status()` in `vault_entries.py`**

Read `app/services/vault_entries.py`. Replace `update_entry_status()` (lines 216–233):

```python
def update_entry_status(project: str, slug: str, new_status: str) -> bool:
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for cfg in _vc.ENTRY_TYPE_CONFIG.values():
        filepath = proj_dir / cfg["folder"] / f"{slug}.md"
        if filepath.exists():
            if new_status not in cfg["valid_statuses"]:
                return False
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
```

- [x] **Step 4: Run all three new tests — all must pass**

```bash
docker cp app/services/vault_entries.py ikeos:/app/app/services/vault_entries.py
docker.exe exec ikeos pytest tests/test_vault_entries.py::test_update_entry_status_rejects_standard_status_for_experiment tests/test_vault_entries.py::test_update_entry_status_accepts_experiment_status_for_experiment tests/test_vault_entries.py::test_update_entry_status_rejects_experiment_status_for_note -v 2>&1 | tail -15
```

Expected: 3 PASSED.

- [x] **Step 5: Run full test suite**

```bash
docker.exe exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: 266 passed, 0 failures (263 existing + 3 new).

- [x] **Step 6: Append decision to `.claude/DECISIONS.md`**

Read `.claude/DECISIONS.md` to find the end. Append:

```markdown

## 2026-06-27: update_entry_status() validates against per-type lifecycle

`update_entry_status()` (the web-UI status path, called by `POST /projects/<name>/<slug>/status`) previously validated `new_status` against `VALID_STATUSES` before finding the file. This meant experiments could be set to `done` (invalid) and could not be set to `complete` (valid for experiments). Fix: remove the upfront check; after finding the file by type folder, validate against `cfg["valid_statuses"]` from `ENTRY_TYPE_CONFIG`. This is the same pattern `update_entry_status_generic()` uses. The web UI status dropdown now correctly enforces per-type lifecycle rules without needing to know the entry type upfront.
```

- [x] **Step 7: Rebuild and verify health**

```bash
docker.exe compose up --build -d ikeos 2>&1 | tail -3
curl -s http://localhost:5009/health
```

Expected: `ok`

- [x] **Step 8: Commit**

```bash
git add app/services/vault_entries.py tests/test_vault_entries.py .claude/DECISIONS.md
git commit -m "fix: update_entry_status validates per-type lifecycle not global VALID_STATUSES

The web-UI status update path (POST /projects/<name>/<slug>/status)
was validating against VALID_STATUSES before finding the file, which
meant experiments could be set to 'done' (invalid) and could not be
set to 'complete' (valid experiment status).

Fix: validate against cfg[\"valid_statuses\"] from ENTRY_TYPE_CONFIG
after finding the entry file, same pattern as update_entry_status_generic."
```

---

## Task 2: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

CONTRIBUTING.md supplements README.md — README explains what IkeOS is and how to run it; CONTRIBUTING.md explains how to develop it, how the vault is structured, and how to extend it. Keep it practical and concrete. No marketing language. No duplication of README content.

- [x] **Step 1: Write CONTRIBUTING.md**

Create `CONTRIBUTING.md` at the repo root:

```markdown
# Contributing to IkeOS

IkeOS is a personal platform, not a general-purpose tool. Contributions are welcome if they align with [PHILOSOPHY.md](PHILOSOPHY.md) — read it first.

---

## Prerequisites

- Docker and Docker Compose (required)
- Claude Code CLI (optional — needed for the Sessions tab and housekeeping scheduler)
- An Obsidian vault, or any directory structured as `projects/<slug>/bugs|ideas|notes|grill-me|experiments/` (required for vault features)

---

## Setup

```bash
git clone <repo-url>
cd ikeos
cp .env.example .env
# Edit .env — see field comments for what each variable does
docker compose up --build
```

Open `http://localhost:5009`. The `/health` endpoint returns `ok` when the app is running.

---

## Running tests

Tests run inside the container against a temporary vault directory — they never touch your real vault.

```bash
docker exec ikeos pytest          # all tests
docker exec ikeos pytest -v       # verbose
docker exec ikeos pytest tests/test_vault_entries.py  # one file
```

The test suite has no database setup — it patches `vault_cache.VAULT_PATH` to a `tmp_path` fixture.

---

## Vault structure

IkeOS reads and writes Markdown files with YAML frontmatter. The vault root (set via `VAULT_PATH` in `.env`) must follow this layout:

```
vault-root/
  projects/
    <project-slug>/
      bugs/         ← bug entries
      ideas/        ← idea entries
      notes/        ← note entries
      grill-me/     ← grill-me entries
      experiments/  ← experiment entries
      housekeeping/ ← housekeeping tasks and heartbeat
  decisions/        ← cross-project decision records (ADRs)
```

Each entry is a `.md` file with frontmatter fields `type`, `title`, `project`, `status`, `created`, `tags`, and type-specific fields.

---

## Entry types

Entry types and their lifecycle are defined in `app/services/vault_cache.py` — `ENTRY_TYPE_CONFIG`:

| Type | Folder | Initial status | Valid statuses |
|------|--------|---------------|----------------|
| `note` | `notes/` | `new` | new, open, in-progress, done, deferred |
| `idea` | `ideas/` | `new` | new, open, in-progress, done, deferred |
| `bug` | `bugs/` | `new` | new, open, in-progress, done, deferred |
| `grill-me` | `grill-me/` | `new` | new, open, in-progress, done, deferred |
| `experiment` | `experiments/` | `running` | running, complete, abandoned |

`decision` and `housekeeping-*` types have separate storage layouts and are not in `ENTRY_TYPE_CONFIG`.

### Adding a new entry type

1. Add an entry to `ENTRY_TYPE_CONFIG` in `app/services/vault_cache.py`
2. Add an `elif entry_type == "<your-type>":` block in `write_entry()` in `vault_entries.py` (for type-specific metadata fields)
3. Add a radio button to `app/templates/capture.html`
4. Add the type to `capture_json()` in `app/routes/capture.py` if it should be capturable via API

See `DECISIONS.md` entry "ENTRY_TYPE_CONFIG is the single registry" for the architectural rationale.

---

## Adding a project to track

IkeOS discovers projects from `vault-root/projects/<slug>/`. To add a project:

1. Create `vault-root/projects/<slug>/` (the app will pick it up on the next cache miss)
2. Optionally add an entry to `umbrella_registry.yaml` (copy from `umbrella_registry.yaml.example`) if the project has sub-components

---

## Project configuration — umbrella_registry.yaml

`umbrella_registry.yaml` maps project slugs to their component sub-projects. It is gitignored (personal project topology stays private). Copy `umbrella_registry.yaml.example` to get started.

---

## CSS and static files

`app/static/bundle.css` is generated at Docker build time by `scripts/bundle_css.py`. Never edit `bundle.css` directly — edits are overwritten on the next build. Edit `app/static/style.css` (and imported files like `app/static/ikeos/styles.css`).

---

## The TASK.md workflow

`TASK.md` is a template for structured implementation tasks. Before starting any non-trivial change:

1. Copy the template and fill in the Objective, Size, and Verification contract
2. Work through the agent loop status checklist
3. Verify every item in the contract before committing

The scope gate determines whether an architect review is needed — check any box that applies to trigger the full loop.

---

## Architecture

Routes → Services → Vault (filesystem). Routes are thin; all file I/O is in `app/services/vault*.py`. Services have no Flask imports. There is no database.

See [CLAUDE.md](CLAUDE.md) for the full adapter contract.  
See [.claude/DECISIONS.md](.claude/DECISIONS.md) for the history of architectural decisions.
```

- [x] **Step 2: Verify no broken links**

```bash
# Check that all referenced files exist
ls PHILOSOPHY.md .env.example umbrella_registry.yaml.example CLAUDE.md .claude/DECISIONS.md
```

Expected: all six files listed without error.

- [x] **Step 3: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add CONTRIBUTING.md — vault structure, tests, adding types

Covers prerequisites, dev setup, vault directory layout, entry type
registry (ENTRY_TYPE_CONFIG), adding a new project, umbrella config,
CSS bundle, TASK.md workflow, and architecture overview.

Completes Level B public release readiness."
```

---

## Task 3: Session 9 'Imi Output

- [x] **Step 1: Produce Session 9 output**

Answer each heading:

**Executive Summary** — What was accomplished? What did we learn?

**Files Changed** — Every file modified or created, one-line description.

**Architectural Decisions** — New entries added to DECISIONS.md.

**Public Release Progress** — Which open audit items are now resolved?

**Technical Debt** — What shortcuts were taken deliberately?

**Lessons Learned** — What was surprising or non-obvious?

**Platform Health Observations** — What is in good shape? What is fragile?

**Highest ROI Next Task** — One sentence: what should Session 10 start with?

---

## Verification Contract

Session 9 is done when:

- [x] `docker exec ikeos pytest tests/ -q` shows 266 passed, 0 failures
- [x] `update_entry_status("myproj", "experiment-slug", "done")` returns `False`
- [x] `update_entry_status("myproj", "experiment-slug", "complete")` returns `True`
- [x] `CONTRIBUTING.md` exists at repo root with no broken file references
- [x] `curl -s http://localhost:5009/health` returns `ok`
- [x] `DECISIONS.md` has the lifecycle fix entry
