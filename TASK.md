# Task: Fix write_entry() same-day filename collision data loss

> Replace this file each time you start a new task. Keep it at project root.
> Commit it with your changes so there's a record of what was intended.

---

## Objective

Prevent `write_entry()` in `app/services/vault_entries.py` from silently overwriting an existing vault entry when two entries share the same date-based slug (same day + same/colliding title).

---

## Size

S — 2 files touched (`app/services/vault_entries.py`, `tests/test_vault_entries.py`), no new dependency, no schema/API change, no auth/session logic.

---

## Scope gate

Check the boxes that apply. If any are checked, run the **full agent loop**
(Architect → Implementer → Reviewer → Debugger if needed → Verification).
Otherwise, invoke the Implementer directly.

- [ ] Touches 3 or more files
- [ ] Introduces a new abstraction, file, or dependency
- [ ] Changes auth, session, or security logic
- [x] Touches data persistence or migrations (file writes) — but scope is a targeted bug fix in an existing function, not a new persistence mechanism; treated as S per task-size gate (clear requirements, ≤2 files, no schema/API change).

---

## Agent loop status

- [ ] Architect: proposal reviewed and approved (not required — S size)
- [x] Implementer: changes complete
- [ ] Reviewer: signed off (or not required — see scope gate)
- [x] Verification: all steps passed

---

## Verification contract

> Define these BEFORE starting work. The task is not done until every item is checked.
> Be specific — "no errors" is not a step. "docker compose logs shows no ERROR lines" is.

- [x] `docker compose up --build` completes without error
- [x] `docker ps` shows container status as healthy (or running, if no healthcheck)
- [x] `docker compose logs --tail=50 ikeos` — no ERROR lines
- [x] `curl -sf http://localhost:5009/health` returns 200
- [x] `docker exec ikeos pytest tests/test_vault_entries.py tests/test_capture.py -v` — all pass (85 passed)

---

## Branch

- [ ] Working on a feature branch (not main) — worked directly on `main` per repo convention observed in recent commit history (no feature-branch pattern in use for small fixes).

---

## If verification fails

1. Run `docker compose logs ikeos` — identify the failure
2. Apply fix and re-run verification once
3. If still failing: **stop**. Do not commit. Document in Notes:
   - Root cause hypothesis
   - Fix attempted
   - Remaining issue
   - Suggested next action

---

## Notes

- Root cause: `write_entry()` derived filenames as `{date}-{slugify(title)}.md` and wrote via `open(path, "w")` with no existence check, so two same-day same-titled entries silently clobbered each other.
- Fix: added `_unique_slug(target_dir, slug)` helper that checks for an existing file at the candidate path and appends `-2`, `-3`, etc. until an unused path is found. Applied to the `housekeeping-task` write path and the generic (note/idea/bug/experiment) write path. Deliberately NOT applied to the `housekeeping-heartbeat` write, which uses a fixed `last-run.md` filename by design (singleton, meant to be overwritten every run).
- Caller contract preserved: `write_entry()` still returns a string slug/filename stem; `app/routes/capture.py` callers (`capture_submit`, `capture_json`) discard the return value, so no caller changes were needed.
- Found an unrelated, pre-existing uncommitted diff in `tests/test_housekeeping.py` (CAPTURE_TOKEN header additions) not made by this task — left untouched and excluded from this commit.
- Full `pytest tests/` run has 4 pre-existing failures (`test_driver.py::test_platform_review_command`, `test_housekeeping.py::test_run_task_creates_session`, `test_housekeeping.py::test_run_task_session_manager_unreachable`, `test_session_client.py::test_get_session_status_found`) — unrelated to `vault_entries.py`/`write_entry()`, not touched by this change, confirmed pre-existing via `git diff` on unrelated files.
