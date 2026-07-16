# Task: Fix scheduler leader-election desync across gunicorn workers

> Replace this file each time you start a new task. Keep it at project root.
> Commit it with your changes so there's a record of what was intended.

---

## Objective

Make `app/services/scheduler.py`'s housekeeping cron job safe under `gunicorn --workers 2` by electing a single leader worker to own the live APScheduler instance, and making `next_run` reporting consistent regardless of which worker answers a request.

---

## Size

M — touches 3 files (`app/services/scheduler.py`, `tests/test_scheduler.py`, `.claude/DECISIONS.md`); introduces a new abstraction (advisory file lock / leader election). Implemented directly per an explicit, fully-specified design brief supplied by the task author, so no separate architect pass was run.

---

## Scope gate

- [x] Touches 3 or more files (scheduler.py, test_scheduler.py, DECISIONS.md)
- [x] Introduces a new abstraction, file, or dependency (leader-election lock file)
- [ ] Changes auth, session, or security logic
- [ ] Touches data persistence or migrations

---

## Agent loop status

- [x] Architect: proposal reviewed and approved (design brief supplied directly by task author; treated as approved)
- [x] Implementer: changes complete
- [ ] Reviewer: signed off (or not required — see scope gate)
- [x] Verification: all steps passed

---

## Verification contract

- [x] `docker compose up --build` completes without error
- [x] `docker ps` shows container status as healthy (or running, if no healthcheck)
- [x] `docker compose logs --tail=50 ikeos` — no ERROR lines related to scheduler/housekeeping (one unrelated pre-existing `/agents/sessions/.../pane` JSONDecodeError observed — confirmed unrelated, not touched by this change)
- [x] `docker.exe exec ikeos pytest tests/ -k scheduler -v` — 20 passed
- [x] `docker.exe exec ikeos pytest tests/test_housekeeping.py -v` — 61 passed

---

## Branch

- [ ] Working on a feature branch (not main) — worked directly on `main` per repo convention observed in recent commit history.

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

- Leader election: non-blocking `fcntl.flock()` on `/tmp/ikeos-scheduler.lock` (container-local, ephemeral) at `start()` time. Only the winning worker creates a live `BackgroundScheduler`; the loser logs and returns without a competing scheduler.
- `next_run` reporting no longer depends on any live scheduler at all — `get_config_with_next_run()` computes it analytically via `apscheduler.triggers.cron.CronTrigger.get_next_fire_time()` straight from `schedule.json`'s cron fields, so any worker (leader or not) answering GET returns the identical value. This is a deliberate simplification vs. the prompt's literal suggestion of "persist the leader's computed value to disk" — pure computation is race-free and needs no persistence/sync at all for the read path.
- Added one thing beyond the prompt's three literal points: a leader-only `housekeeping-sync` APScheduler interval job (every 60s) that re-reads `schedule.json` and reapplies it to the live cron job if changed. This closes a real correctness gap: without it, a PATCH landing on the non-leader worker would update `schedule.json` (and `next_run` reporting, correctly) but the leader's actual firing job would never receive the change until container restart — same functional bug as before, just for firing instead of reporting. Documented in `.claude/DECISIONS.md` (2026-07-16 entry).
- `trigger_now()` required no changes — it was already leader-independent (calls `run_scheduled_housekeeping()` directly in-process).
- Verified live against the running two-worker container: 6 consecutive `GET /housekeeping/schedule` calls (round-robin across both workers) all returned identical `next_run`, confirming the reported symptom is resolved without reverting to `--workers 1`.
