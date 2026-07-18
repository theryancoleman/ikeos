# Task: Add a weak-signal log viewer page

> Replace this file each time you start a new task. Keep it at project root.
> Commit it with your changes so there's a record of what was intended.

---

## Objective

The claude-config self-improvement system maintains `library/weak-signals.json` (a
candidate pool of observations tracked for recurrence but not yet promoted to a vault
entry). Add a read-only IkeOS page that lists each signal (category, `skill_referenced`,
`pattern`, occurrence count, first/last-seen), shows days remaining until the 45-day
auto-prune window closes, and highlights entries approaching (occurrences == 2) or at
(occurrences >= 3) the promotion threshold. No write operations — agents manage the file
directly.

---

## Size

S — single new service function + single new route/template, following the existing
`get_reflection_health()` / dashboard-widget pattern exactly. No schema/API/architecture
change.

---

## Outcome

Extended the existing reflection surface rather than inventing a new one:

- `app/services/reflection.py`: added `get_weak_signals()`, reusing the same
  `CLAUDE_CONFIG_DIR` env resolution and graceful-`None`-on-unavailable pattern as
  `get_reflection_health()`. Computes `days_until_prune` (45 minus days since
  `last_seen`, can go negative once prune-eligible), `at_threshold`
  (occurrences >= 3), and `approaching_threshold` (occurrences == 2). Sorted by
  occurrences descending, then last_seen descending.
- `app/routes/browse.py`: added `GET /weak-signals` → `weak_signals.html`.
- `app/templates/weak_signals.html`: new standalone page (styled after `skills.html`'s
  table pattern) rather than only extending the compact dashboard widget — the log
  needed a full sortable table (category/skill, pattern, occurrences with threshold
  badges, first/last seen, prune countdown), which didn't fit the widget's
  summary-card format.
- `app/templates/dashboard.html`: added a "View weak-signal log →" link inside the
  existing Reflection Health widget (reuses `.hk-widget-link`).
- `app/templates/base.html`: added "Weak Signals" as a sub-nav item under "Metrics".

Not-configured case handled identically to `get_reflection_health()`: `CLAUDE_CONFIG_DIR`
unset → `get_weak_signals()` returns `None` → template renders an `.empty-state` message
("Not configured. Set `CLAUDE_CONFIG_PATH`...") instead of erroring. Distinguished from
the "configured but zero signals" case ("No weak signals recorded yet").

`CLAUDE_CONFIG_PATH` is **not set** in this environment's `.env` — confirmed via
`docker.exe exec ikeos env | grep CLAUDE_CONFIG` (empty). Manual verification therefore
exercised the not-configured graceful-degradation path only (`curl` → 200, body contains
"Not configured..."). The configured/populated-data path was verified via unit tests
using fixtures mirroring the real `weak-signals.json` schema (confirmed by reading the
actual file on the host at `/mnt/c/Server/claude-config/library/weak-signals.json`).

Tests added:
- `tests/test_reflection.py`: `get_weak_signals()` — not configured, missing file, empty
  list, prune/threshold computation across fresh/approaching/at-threshold/near-prune/
  overdue signals, invalid date handling, malformed JSON.
- `tests/test_browse.py`: `GET /weak-signals` — not-configured empty state, populated
  rows with threshold badges, configured-but-empty state.

---

## Verification contract

1. `docker.exe compose up --build -d ikeos` — rebuilds cleanly, container starts.
2. `docker.exe exec ikeos pytest tests/ -q` — full suite passes, no regressions.
3. `curl -s -o /dev/null -w "%{http_code}" http://localhost:5009/weak-signals` — 200.
4. `curl -s http://localhost:5009/weak-signals` — body contains the graceful
   not-configured message (since `CLAUDE_CONFIG_PATH` is unset here).
5. `curl -s -o /dev/null -w "%{http_code}" http://localhost:5009/tasks` — 200
   (dashboard unaffected).

---

## Agent loop status

- [x] Implementer: changes complete
- [ ] Reviewer: not required (S-size)
- [x] Verification: all contract steps above passed
