# Type-Set Constants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate three overlapping set expressions for vault entry type subsets by promoting them to named constants in `vault_cache.py`, and update `_read_all_entries()` to iterate `ENTRY_TYPE_CONFIG.values()` directly.

**Architecture:** Two new constants join the registry in `vault_cache.py`: `PATCH_VALID_TYPES` (types accepted by `PATCH /entries`) and `CAPTURE_JSON_VALID_TYPES` (types accepted by `POST /capture/json`). Both are derived from `ENTRY_TYPE_CONFIG` plus their respective special-case types. `capture.py` imports and uses these constants instead of computing equivalent sets locally on every request. `_read_all_entries()` replaces `set(TYPE_FOLDERS.values())` with iteration over `ENTRY_TYPE_CONFIG.values()` directly, removing the last site that bypasses the registry. No behaviour changes in any of these refactors — only the location of truth moves.

**Tech Stack:** Python 3.11, Flask, pytest, Docker

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/services/vault_cache.py` | Add `PATCH_VALID_TYPES` and `CAPTURE_JSON_VALID_TYPES` constants |
| Modify | `app/services/vault_entries.py` | `_read_all_entries()`: iterate `ENTRY_TYPE_CONFIG.values()` instead of `TYPE_FOLDERS.values()` |
| Modify | `app/services/vault.py` | Re-export `PATCH_VALID_TYPES` and `CAPTURE_JSON_VALID_TYPES` |
| Modify | `app/routes/capture.py` | Import and use the two new constants; remove local set computations |
| Modify | `.claude/DECISIONS.md` | Document the named type-set constants decision |
| Modify | `tests/test_vault_entries.py` | Add 2 sentinel tests for the new constants |

---

## Critical reading before starting

- `app/services/vault_cache.py` — understand the existing constant layout; new constants go after `VALID_TYPES`
- `app/routes/capture.py` — find lines 116 and 191 where `_patch_valid_types` and `_capture_json_valid_types` are computed; understand what they're replacing
- `app/services/vault_entries.py` — find `_read_all_entries()` line 164 where `set(_vc.TYPE_FOLDERS.values())` appears
- `app/services/vault.py` — understand the re-export block before adding to it
- `tests/test_vault_entries.py` — find the existing ENTRY_TYPE_CONFIG tests at the bottom to place new tests after them

---

## Task 1: Named type-set constants + capture.py + _read_all_entries

**Files:**
- Modify: `app/services/vault_cache.py`
- Modify: `app/services/vault_entries.py`
- Modify: `app/services/vault.py`
- Modify: `app/routes/capture.py`
- Modify: `.claude/DECISIONS.md`
- Modify: `tests/test_vault_entries.py`

- [ ] **Step 1: Write two failing tests**

Add to `tests/test_vault_entries.py` after the last existing test (`test_update_entry_status_generic_uses_entry_type_config`):

```python
def test_patch_valid_types_constant_exists_and_is_correct():
    assert hasattr(_vc, "PATCH_VALID_TYPES"), "PATCH_VALID_TYPES not found in vault_cache"
    assert _vc.PATCH_VALID_TYPES == set(_vc.ENTRY_TYPE_CONFIG.keys()) | {"decision"}


def test_capture_json_valid_types_constant_exists_and_is_correct():
    assert hasattr(_vc, "CAPTURE_JSON_VALID_TYPES"), "CAPTURE_JSON_VALID_TYPES not found in vault_cache"
    assert _vc.CAPTURE_JSON_VALID_TYPES == (
        set(_vc.ENTRY_TYPE_CONFIG.keys()) | {"housekeeping-task", "housekeeping-heartbeat"}
    )
```

- [ ] **Step 2: Run failing tests**

```bash
docker cp tests/test_vault_entries.py ikeos:/app/tests/test_vault_entries.py
docker.exe exec ikeos pytest tests/test_vault_entries.py::test_patch_valid_types_constant_exists_and_is_correct tests/test_vault_entries.py::test_capture_json_valid_types_constant_exists_and_is_correct -v 2>&1 | tail -10
```

Expected: 2 FAILED — `AssertionError: PATCH_VALID_TYPES not found in vault_cache`.

- [ ] **Step 3: Add constants to `vault_cache.py`**

Read `app/services/vault_cache.py`. After the `VALID_TYPES` block (lines 22–24), add:

```python
PATCH_VALID_TYPES: frozenset[str] = frozenset(ENTRY_TYPE_CONFIG.keys()) | {"decision"}
CAPTURE_JSON_VALID_TYPES: frozenset[str] = (
    frozenset(ENTRY_TYPE_CONFIG.keys()) | {"housekeeping-task", "housekeeping-heartbeat"}
)
```

Use `frozenset` (not `set`) — these are immutable constants and `frozenset` communicates that intent. The `in` operator works identically on both.

- [ ] **Step 4: Run new tests — both must pass**

```bash
docker cp app/services/vault_cache.py ikeos:/app/app/services/vault_cache.py
docker.exe exec ikeos pytest tests/test_vault_entries.py::test_patch_valid_types_constant_exists_and_is_correct tests/test_vault_entries.py::test_capture_json_valid_types_constant_exists_and_is_correct -v 2>&1 | tail -10
```

Expected: 2 PASSED.

Note: the tests assert `== set(...) | {...}`. A `frozenset` equals a `set` with the same elements in Python (`frozenset({"a"}) == {"a"}` is `True`), so the test passes with `frozenset`.

- [ ] **Step 5: Update `vault_entries.py` — `_read_all_entries` loop**

Read `app/services/vault_entries.py`. Find the `_read_all_entries` function. Replace the inner loop:

```python
# Old (line 164):
        for folder in set(_vc.TYPE_FOLDERS.values()):
            type_dir = proj_dir / folder

# New:
        for cfg in _vc.ENTRY_TYPE_CONFIG.values():
            type_dir = proj_dir / cfg["folder"]
```

- [ ] **Step 6: Update `vault.py` — add the two new constants to re-exports**

Read `app/services/vault.py`. In the `from app.services.vault_cache import (...)` block, add both new constants after `ENTRY_TYPE_CONFIG`:

```python
from app.services.vault_cache import (  # noqa: F401
    VAULT_PATH,
    VALID_TYPES,
    VALID_STATUSES,
    DECISION_STATUSES,
    EXPERIMENT_STATUSES,
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

- [ ] **Step 7: Update `capture.py` — import and use the constants**

Read `app/routes/capture.py`.

**Change A:** Update the import to include the two new constants:

```python
from app.services.vault import (
    get_projects_with_meta, write_entry, update_entry_status_generic,
    update_housekeeping_fields, ENTRY_TYPE_CONFIG, DECISION_STATUSES,
    PATCH_VALID_TYPES, CAPTURE_JSON_VALID_TYPES,
)
```

**Change B:** In `patch_entries()`, replace the local variable computation:

```python
# Old (lines 115–118):
    # Validate entry_type
    _patch_valid_types = set(ENTRY_TYPE_CONFIG.keys()) | {"decision"}
    if entry_type not in _patch_valid_types:
        return jsonify({"error": "Invalid entry type"}), 400

# New:
    # Validate entry_type
    if entry_type not in PATCH_VALID_TYPES:
        return jsonify({"error": "Invalid entry type"}), 400
```

**Change C:** In `capture_json()`, replace the local variable computation:

```python
# Old (lines 191–194):
    _capture_json_valid_types = set(ENTRY_TYPE_CONFIG.keys()) | {"housekeeping-task", "housekeeping-heartbeat"}
    if entry_type not in _capture_json_valid_types:
        valid_list = ", ".join(sorted(_capture_json_valid_types))
        return jsonify({"error": f"type must be one of: {valid_list}"}), 400

# New:
    if entry_type not in CAPTURE_JSON_VALID_TYPES:
        valid_list = ", ".join(sorted(CAPTURE_JSON_VALID_TYPES))
        return jsonify({"error": f"type must be one of: {valid_list}"}), 400
```

- [ ] **Step 8: Run the full test suite**

```bash
docker cp app/services/vault_cache.py ikeos:/app/app/services/vault_cache.py
docker cp app/services/vault_entries.py ikeos:/app/app/services/vault_entries.py
docker cp app/services/vault.py ikeos:/app/app/services/vault.py
docker cp app/routes/capture.py ikeos:/app/app/routes/capture.py
docker.exe exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: 263 passed, 0 failures (261 existing + 2 new).

- [ ] **Step 9: Append decision to `.claude/DECISIONS.md`**

Read `.claude/DECISIONS.md` to find the end. Append:

```markdown

## 2026-06-27: PATCH_VALID_TYPES and CAPTURE_JSON_VALID_TYPES named in vault_cache

Two named frozenset constants (`PATCH_VALID_TYPES`, `CAPTURE_JSON_VALID_TYPES`) are derived from `ENTRY_TYPE_CONFIG` in `vault_cache.py` and re-exported through `vault.py`. `capture.py` imports them directly rather than computing equivalent sets locally on every request. This eliminates three overlapping set expressions that existed after the ENTRY_TYPE_CONFIG refactor (Session 6) and makes the type-set contract for each endpoint visible in one place. `_read_all_entries()` was also updated to iterate `ENTRY_TYPE_CONFIG.values()` directly rather than going through the `TYPE_FOLDERS` derived dict, completing the registry consolidation.
```

- [ ] **Step 10: Rebuild and verify**

```bash
docker.exe compose up --build -d ikeos 2>&1 | tail -3
```

Wait a few seconds then:

```bash
curl -s http://localhost:5009/health
```

Expected: `ok`

Verify the constants are importable:

```bash
docker.exe exec ikeos python -c "
from app.services.vault import PATCH_VALID_TYPES, CAPTURE_JSON_VALID_TYPES
print('PATCH:', sorted(PATCH_VALID_TYPES))
print('CAPTURE_JSON:', sorted(CAPTURE_JSON_VALID_TYPES))
"
```

Expected output (order may vary within each line):
```
PATCH: ['bug', 'decision', 'experiment', 'grill-me', 'idea', 'note']
CAPTURE_JSON: ['bug', 'experiment', 'grill-me', 'housekeeping-heartbeat', 'housekeeping-task', 'idea', 'note']
```

- [ ] **Step 11: Commit**

```bash
git add app/services/vault_cache.py app/services/vault_entries.py \
        app/services/vault.py app/routes/capture.py \
        .claude/DECISIONS.md tests/test_vault_entries.py
git commit -m "refactor: promote type-set constants to vault_cache; complete registry consolidation

Adds PATCH_VALID_TYPES and CAPTURE_JSON_VALID_TYPES as named frozenset
constants in vault_cache.py (re-exported through vault.py). capture.py
imports them instead of computing equivalent sets on every request.

_read_all_entries() now iterates ENTRY_TYPE_CONFIG.values() directly
rather than going through the TYPE_FOLDERS derived dict, completing
the registry consolidation started in Session 6."
```

---

## Task 2: Session 7 'Imi Output

At the conclusion of every 'Imi session, produce the 8-section output directly to the user (do not commit it as a file).

- [ ] **Step 1: Produce Session 7 output**

Answer each heading:

**Executive Summary** — What was accomplished? What did we learn?

**Files Changed** — Every file modified or created, one-line description.

**Architectural Decisions** — New entries added to DECISIONS.md.

**Public Release Progress** — Which open audit items are now resolved?

**Technical Debt** — What shortcuts were taken deliberately?

**Lessons Learned** — What was surprising or non-obvious?

**Platform Health Observations** — What is in good shape? What is fragile?

**Highest ROI Next Task** — One sentence: what should Session 8 start with?

---

## Verification Contract

Session 7 is done when:

- [ ] `docker exec ikeos pytest tests/ -q` shows 263 passed, 0 failures
- [ ] `python -c "from app.services.vault import PATCH_VALID_TYPES, CAPTURE_JSON_VALID_TYPES; print('ok')"` prints `ok`
- [ ] `PATCH_VALID_TYPES == frozenset({'note','idea','bug','grill-me','experiment','decision'})`
- [ ] `CAPTURE_JSON_VALID_TYPES == frozenset({'note','idea','bug','grill-me','experiment','housekeeping-task','housekeeping-heartbeat'})`
- [ ] No local set computations remain in `capture.py` for type validation
- [ ] `DECISIONS.md` has the new named constants entry
