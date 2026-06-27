# Task: [Task name]

> Replace this file each time you start a new task. Keep it at project root.
> Commit it with your changes so there's a record of what was intended.

---

## Objective

<!-- One sentence: what does this task accomplish? -->

---

## Size

<!-- S / M / L — determined by scope gate below.
     S: Implementer only. M: Implementer → Reviewer. L: Architect → Implementer → Reviewer. -->

---

## Scope gate

Check the boxes that apply. If any are checked, run the **full agent loop**
(Architect → Implementer → Reviewer → Debugger if needed → Verification).
Otherwise, invoke the Implementer directly.

- [ ] Touches 3 or more files
- [ ] Introduces a new abstraction, file, or dependency
- [ ] Changes auth, session, or security logic
- [ ] Touches data persistence or migrations

---

## Agent loop status

- [ ] Architect: proposal reviewed and approved
- [ ] Implementer: changes complete
- [ ] Reviewer: signed off (or not required — see scope gate)
- [ ] Verification: all steps passed

---

## Verification contract

> Define these BEFORE starting work. The task is not done until every item is checked.
> Be specific — "no errors" is not a step. "docker compose logs shows no ERROR lines" is.

- [ ] `docker compose up --build` completes without error
- [ ] `docker ps` shows container status as healthy (or running, if no healthcheck)
- [ ] `docker compose logs --tail=50 ikeos` — no ERROR lines
- [ ] <!-- Add endpoint / behaviour check, e.g.: `curl -sf http://localhost:5009/health` returns 200 -->
- [ ] <!-- Add any test command, e.g.: `docker exec ikeos pytest` -->

---

## Branch

- [ ] Working on a feature branch (not main)

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

<!-- Anything that came up during implementation worth remembering -->
