# Task: Build a research-sources management page

> Replace this file each time you start a new task. Keep it at project root.
> Commit it with your changes so there's a record of what was intended.

---

## Objective

`claude-config`'s `library/research-sources.json` lists trusted external URLs the
weekly research agent consults. IkeOS needs a page to display and manage this list:
show all sources with status, add a new source, block/unblock a source, show
last-fetched date and how many vault entries it's generated. IkeOS is the write
interface only — the claude-config file is the source of truth.

---

## Size

M — new route module, template, client functions, nav change, and a new test file;
no schema change but a new user-facing feature surface with real design choices
(field-naming mismatch, error-state handling).

---

## API contract (session-manager, port 5010 — already live)

- `GET /research-sources` → `200 {"sources": [{...}]}`. Fields: `url`, `label`,
  `status` (always `"active"`, not the real block signal), `blacklisted` (bool —
  **the actual block/unblock switch**), `last_fetched` (nullable), `entries_generated`
  (int), `added` (ISO date), `id` (base64url of the url, derived not persisted).
- `POST /research-sources` `{"url", "label"}` → `201` created source. `400` if
  missing fields, `409` if URL already exists.
- `PATCH /research-sources/<id>` (no body) → toggles `blacklisted`. `404` if
  unresolvable.
- No auth on this service.

---

## Fix / Implementation

- `app/services/session_client.py`: added `list_research_sources()`,
  `add_research_source(*, url, label)`, `toggle_research_source(source_id)` plus
  `ResearchSourcesResult` / `ResearchSourceResult` frozen dataclasses, following the
  existing `SessionResult` / `session_manager_url()` pattern in the same file.
- `app/routes/research_sources.py` (new blueprint): `GET /research-sources` (page),
  `POST /research-sources` (add), `POST /research-sources/<id>/toggle` (calls PATCH
  downstream — mirrors `housekeeping.toggle_task`'s POST-that-PATCHes convention).
  Registered in `app/__init__.py`.
- `app/templates/research_sources.html` (new): reuses existing `hk-table`,
  `hk-pill--ok` / `hk-pill--disabled`, `hk-add-section/form`, `pill` CSS classes —
  no new shared CSS added, only a small scoped `<style>` block for source-specific
  column widths (same pattern as `skills.html`). UI shows **Active/Blocked** derived
  from `blacklisted`, not the no-op `status` field. Unreachable-service state renders
  a clear message instead of a 500.
- `app/templates/base.html`: added a "Research Sources" sub-link under a new
  Housekeeping `nav-item`/`nav-subnav` (matching the existing Tasks pattern).
- `tests/test_research_sources.py` (new): service-level tests for the three client
  functions (success/unreachable/error-status) and route-level tests (page render
  with mocked list, blocked-status rendering, service-unreachable rendering, add-form
  POST, toggle POST, 400/404/502 paths).

---

## Verification contract

1. `docker.exe exec ikeos pytest tests/test_research_sources.py -q` — all pass.
2. `docker.exe exec ikeos pytest tests/ -q` — full suite passes, no regressions.
3. `docker.exe compose up -d --build ikeos` — container rebuilds and reports healthy.
4. `curl http://localhost:5009/research-sources` — renders real live data from the
   session-manager (if `SESSION_MANAGER_URL` configured and reachable), or the
   graceful degradation message otherwise.

---

## Agent loop status

- [x] Implementer: changes complete
- [ ] Reviewer: not run in this dispatch — orchestrator invoked implementer directly
      for a self-contained task and instructed committing on completion; flagged as
      an open question given M size.
- [x] Verification: all contract steps passed (see below)

---

## Follow-up (outside this task)

- `adapters/claude-code/session-manager/app.py` (this repo's reference copy of the
  session-manager) does not yet contain the `/research-sources` endpoints that are
  live on the deployed port-5010 instance — worth syncing back so the reference
  implementation matches production, but out of scope for this task.
