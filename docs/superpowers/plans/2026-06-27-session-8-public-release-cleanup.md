# Session 8 — Public Release Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining 'Imi audit items and technical-debt cleanups from Sessions 5–7, then produce the Session 8 'Imi output.

**Architecture:** All three tasks are S-size (≤2 files, no schema/API/architecture change). The previous session discovered that Tasks 2–5 from the 'Imi audit and all "Immediate actions" were already completed by the time this session began. What remains: a naming consistency fix in `TASK.md`, dead-code removal and frozenset consistency in `vault_cache.py`/`vault.py`, and the 'Imi output report.

**Tech Stack:** Python 3.11, Flask, pytest, Docker

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `TASK.md` | Replace 3 stale `obsidian-capture` container name references with `ikeos` |
| Modify | `app/services/vault_cache.py` | Remove dead `VALID_TYPES`; convert `VALID_STATUSES`, `DECISION_STATUSES`, `EXPERIMENT_STATUSES` to `frozenset` |
| Modify | `app/services/vault.py` | Remove `VALID_TYPES` from re-export block |
| None | — | Session 8 'Imi output (produced directly to user, not committed) |

---

## Pre-session state confirmed

The following 'Imi audit items were already complete before Session 8 began:
- `docker-compose.yml` portable base (no Traefik network) ✅
- `docker-compose.homelab.yml` Traefik overlay ✅
- `README.md` rewritten for public audience ✅
- `CLAUDE.md` says "IkeOS" throughout ✅
- `DECISIONS.md` header says "Architectural Decisions — IkeOS" ✅
- `.gitignore` covers `bundle.css`, `umbrella_registry.yaml`, `settings.local.json`, `venv/`, `agent-memory/` ✅
- `umbrella_registry.yaml` not tracked; `.example` with dummy entries exists ✅
- `agent-memory/` not tracked in git ✅
- `venv/` not tracked in git ✅
- `.env.example` documents all fields ✅

---

## Task 1: TASK.md naming fix

**Files:**
- Modify: `TASK.md`

- [ ] **Step 1: Replace stale container names in TASK.md**

Read `TASK.md`. Replace every instance of `obsidian-capture` with `ikeos`. There are 3 occurrences (lines 51, 52, 64 approximately):

```
# Old line ~51:
- [ ] `docker compose logs --tail=50 obsidian-capture` — no ERROR lines

# New:
- [ ] `docker compose logs --tail=50 ikeos` — no ERROR lines
```

```
# Old line ~52:
- [ ] <!-- Add any test command, e.g.: `docker exec obsidian-capture pytest` -->

# New:
- [ ] <!-- Add any test command, e.g.: `docker exec ikeos pytest` -->
```

```
# Old line ~64:
1. Run `docker compose logs obsidian-capture` — identify the failure

# New:
1. Run `docker compose logs ikeos` — identify the failure
```

- [ ] **Step 2: Verify no more stale references**

```bash
grep -n "obsidian-capture" TASK.md
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add TASK.md
git commit -m "chore: fix stale obsidian-capture container name in TASK.md template"
```

---

## Task 2: vault_cache.py — dead code removal and frozenset consistency

**Files:**
- Modify: `app/services/vault_cache.py`
- Modify: `app/services/vault.py`

**Context:** `VALID_TYPES` was grep-confirmed to have no consumers in routes, services, or tests — only defined in `vault_cache.py` and re-exported from `vault.py`. The three status sets (`VALID_STATUSES`, `DECISION_STATUSES`, `EXPERIMENT_STATUSES`) remain plain `set` while the new constants added in Session 7 (`PATCH_VALID_TYPES`, `CAPTURE_JSON_VALID_TYPES`) are `frozenset`. Converting them is consistent and communicates immutability intent. There are no behavior changes — `frozenset` supports the same `in` operator.

- [ ] **Step 1: Update vault_cache.py**

Read `app/services/vault_cache.py`. Make two changes:

**Change A** — Convert status sets to `frozenset`:

```python
# Old:
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
EXPERIMENT_STATUSES = {"running", "complete", "abandoned"}

# New:
VALID_STATUSES: frozenset[str] = frozenset({"new", "open", "in-progress", "done", "deferred"})
DECISION_STATUSES: frozenset[str] = frozenset({"proposed", "accepted", "rejected", "superseded"})
EXPERIMENT_STATUSES: frozenset[str] = frozenset({"running", "complete", "abandoned"})
```

**Change B** — Remove `VALID_TYPES` entirely (dead code — no consumers):

```python
# Remove these 3 lines:
VALID_TYPES = set(ENTRY_TYPE_CONFIG.keys()) | {
    "decision", "housekeeping-task", "housekeeping-heartbeat",
}
```

- [ ] **Step 2: Update vault.py — remove VALID_TYPES from re-export**

Read `app/services/vault.py`. Remove `VALID_TYPES,` from the `from app.services.vault_cache import (...)` block.

The block should go from:
```python
from app.services.vault_cache import (  # noqa: F401
    VAULT_PATH,
    VALID_TYPES,
    VALID_STATUSES,
    ...
```

To:
```python
from app.services.vault_cache import (  # noqa: F401
    VAULT_PATH,
    VALID_STATUSES,
    ...
```

- [ ] **Step 3: Copy and run full test suite**

```bash
docker cp app/services/vault_cache.py ikeos:/app/app/services/vault_cache.py
docker cp app/services/vault.py ikeos:/app/app/services/vault.py
docker.exe exec ikeos pytest tests/ -q 2>&1 | tail -5
```

Expected: 263 passed, 0 failures.

- [ ] **Step 4: Rebuild and verify health**

```bash
docker.exe compose up --build -d ikeos 2>&1 | tail -3
curl -s http://localhost:5009/health
```

Expected: `ok`

- [ ] **Step 5: Verify status constants are frozenset and VALID_TYPES is gone**

```bash
docker.exe exec ikeos python -c "
from app.services.vault_cache import VALID_STATUSES, DECISION_STATUSES, EXPERIMENT_STATUSES
print('VALID_STATUSES type:', type(VALID_STATUSES).__name__)
print('DECISION_STATUSES type:', type(DECISION_STATUSES).__name__)
print('EXPERIMENT_STATUSES type:', type(EXPERIMENT_STATUSES).__name__)
try:
    from app.services.vault import VALID_TYPES
    print('ERROR: VALID_TYPES still importable')
except ImportError:
    print('VALID_TYPES correctly removed')
"
```

Expected:
```
VALID_STATUSES type: frozenset
DECISION_STATUSES type: frozenset
EXPERIMENT_STATUSES type: frozenset
VALID_TYPES correctly removed
```

- [ ] **Step 6: Commit**

```bash
git add app/services/vault_cache.py app/services/vault.py
git commit -m "refactor: remove dead VALID_TYPES; convert status sets to frozenset

VALID_TYPES had no consumers (routes and tests use the specialized
PATCH_VALID_TYPES and CAPTURE_JSON_VALID_TYPES constants added in
Session 7). Removing it eliminates silent drift risk.

VALID_STATUSES, DECISION_STATUSES, and EXPERIMENT_STATUSES are now
frozenset for consistency with the Session 7 constants. No behaviour
change — frozenset supports the same 'in' operator."
```

---

## Task 3: Session 8 'Imi Output

At the conclusion of every 'Imi session, produce the 8-section output directly to the user (do not commit it as a file).

- [ ] **Step 1: Produce Session 8 output**

Answer each heading:

**Executive Summary** — What was accomplished? What did we learn?

**Files Changed** — Every file modified or created, one-line description.

**Architectural Decisions** — New entries added to DECISIONS.md.

**Public Release Progress** — Which open audit items are now resolved?

**Technical Debt** — What shortcuts were taken deliberately?

**Lessons Learned** — What was surprising or non-obvious?

**Platform Health Observations** — What is in good shape? What is fragile?

**Highest ROI Next Task** — One sentence: what should Session 9 start with?

---

## Verification Contract

Session 8 is done when:

- [ ] `docker exec ikeos pytest tests/ -q` shows 263 passed, 0 failures
- [ ] `VALID_STATUSES`, `DECISION_STATUSES`, `EXPERIMENT_STATUSES` are `frozenset`
- [ ] `from app.services.vault import VALID_TYPES` raises `ImportError`
- [ ] `TASK.md` has no `obsidian-capture` references
- [ ] `curl -s http://localhost:5009/health` returns `ok`
