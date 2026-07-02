# Architectural Decisions — IkeOS

> Append-only. Add an entry when a non-obvious decision is made.
> Format: `## YYYY-MM-DD: Title` followed by a brief explanation of *why*.
> Never delete entries. Mark superseded ones with `~~strikethrough~~`.

## 2026-05-26: Direct vault file writes (no REST API dependency)

The homelab PC is not always in active use. Writing directly to the vault filesystem (via Docker volume mount) means the app works regardless of whether Obsidian is running. The Local REST API would require Obsidian to be open.

## 2026-05-26: No database — vault is the storage layer

Entries are Markdown files with YAML frontmatter. This keeps them readable in Obsidian and eliminates a DB dependency. ~~Status updates are done by Claude agents editing frontmatter directly.~~ (superseded 2026-06-11 — see below)

## 2026-05-26: Status field with "new" distinct from "open"

Added "new" status (distinct from "open") so Claude agents can identify unchecked entries at session start without relying on creation dates. Lifecycle: new → open → in-progress → done | deferred.

## 2026-06-11: Vault is read-only for agents — all writes via capture API

NTFS ownership means WSL2/Linux agent processes cannot write vault files. All new entries go via `POST /capture`; all status changes go via `PATCH /entries` with `X-Capture-Token`. There is no third door.

## 2026-06-11: Single workspace.html template for 2-col and 3-col layouts

Replaced `agents.html` with `workspace.html` rendered by both `/` (three_col=True) and `/agents` (three_col=False). CSS grid modifier class `.workspace-3col` controls column count. Avoids template duplication.

## 2026-06-11: URL state for selected session via ?session= query param

Selected session ID persisted in `?session=<id>` so a page refresh returns to the same panel. `history.replaceState` on open/close; parsed via `URLSearchParams` on load.

## 2026-06-11: POST /capture/json for inline AJAX capture

Added a JSON endpoint so the capture column in the workspace can submit without a page redirect. Internally calls the same `write_entry()` used by the form POST. No auth required (same policy as the form).

## 2026-06-11: Claude config version mounted read-only into container

`~/.claude/VERSION` mounted at `/claude-config/VERSION:ro`. Flask context processor reads it at request time and exposes `config_version` to all templates. No app rebuild needed when config version changes.

## 2026-06-11: Loading screen at `/` — one-per-session splash

`/` renders `loading.html` (standalone, no base.html). A `sessionStorage` guard in `<head>` fires before body paint — repeat visitors are instantly redirected to `/dashboard`. rAF-based 6.5s animation, 5 brand captions, orbital dots, aurora bloom. On complete: 280ms delay → Welcome overlay → 1200ms → fade out → redirect to `/dashboard`. A hidden `<iframe src="/dashboard">` preloads the destination during the animation.

## 2026-06-11: Nav structure — Dashboard / Tasks / Sessions / Capture

`/dashboard` is a new route (`agents.dashboard`) serving `workspace.html` with `three_col=True`. This separates "Dashboard" (three-col: Sessions + Detail + Capture) from "Sessions" (`/agents`, two-col). Each nav item has a distinct endpoint so `request.endpoint` highlights exactly one item per page. Loading screen redirects to `/dashboard`, not `/tasks`. Brand logo also links to `/dashboard`.

## 2026-06-13: Per-project vault reads use global in-memory cache

`read_entries(project=name)` previously bypassed the cache and did fresh file I/O on every project page load (slow on WSL2 Windows bind-mount). Changed to always populate the global `_entries_cache` on miss and filter in-memory for per-project requests. Trade-off: a cold-cache miss now scans all 174+ entries (~1.1s) instead of just one project's files, but the cache is shared across all reads so subsequent requests within the 10-minute TTL are instant. Writes still call `_invalidate_cache()`. Project page also consolidated from two cache lookups (`_read_project_meta` + `get_projects_with_meta`) to a single `get_projects_with_meta(include_hidden=True)` call.

## 2026-06-13: Settings page uses CSS grid div layout, not table

The project list on `/settings` is rendered as a `.settings-list` div with a `.settings-row` per project (each row is its own `<form>`). A table was considered but `<form>` elements inside `<tr>` are invalid HTML — form tags are not permitted as children of table rows. The CSS grid approach (`grid-template-columns: 180px 1fr 1fr 90px 60px`) gives the same columnar alignment without the invalidity.

## 2026-06-13: Graph tab uses client-side D3.js, not Neo4j

The vault graph (`/graph`) uses a D3 v7 force-directed graph rendered entirely in the browser, fed by the `/api/graph` JSON endpoint. Neo4j was considered but the existing `music-graph` Neo4j instance is dedicated to a separate project; adding a second instance for 174 vault entries would be disproportionate. D3 client-side requires no additional infrastructure and performs adequately at this scale. The `/api/graph` endpoint piggybacks on the existing `read_entries()` cache.

## 2026-06-13: /graph route is thin — counts computed in JS, not server-side

The `/graph` route calls no service functions; it simply renders the template. The subtitle ("N entries across M projects") is populated by `graph.js` after it receives the `/api/graph` response. This avoids calling `get_vault_graph()` twice per page load (once server-side for counts, once client-side for data).

## 2026-06-13: Hub nodes always visible in graph filteredData()

Hub nodes represent projects in the wikilink graph and are the anchor points for all edges. Excluding them from `filteredData()` (e.g. when the user unchecks "bugs") dropped every edge, leaving isolated dots. Hub nodes are not filterable content — they are structural connectors. `n.type === 'hub'` is always included in the visibleIds set regardless of filter checkboxes.

## 2026-06-13: D3 convex hull overlays chosen over hub-to-entry dandelion edges

When wikilinks between entries exist, the graph uses actual edges. For the common case where older/closed entries lack explicit wikilinks back to their hub, the graph shows D3 `polygonHull` overlays — one coloured region per project — rather than synthesising fake hub→entry edges for every entry. Synthetic edges would create meaningless radial "dandelion" patterns and obscure real wikilink structure. Hulls provide project grouping without polluting the link data.

## 2026-06-13: Native HTML radio buttons replace CSS-hidden chip pattern on capture form

The original capture form used hidden `<input type="radio">` elements styled with `.type-chips` — clicking the `<label>` toggled a chip appearance. On iOS Safari, `pointer-events: none` on hidden inputs breaks the tap target, making type selection unreliable on mobile. Replaced with standard wrapped-label radios (`.type-radio-label`) using `accent-color` for brand tinting. Accessible: `role="radiogroup"` + `aria-labelledby`.

## 2026-06-14: Nav subnav uses ::before bridge pseudo-element to fix hover gap

The subnav is positioned with `top: calc(100% + 10px)`, creating a 10px visual gap between the nav link and the dropdown. Moving the mouse across this gap exits the `.nav-item` hover zone, collapsing the dropdown before the user reaches it. A transparent `::before` pseudo-element on `.nav-subnav` fills the gap, keeping the hover zone continuous without affecting appearance.

## 2026-06-14: grill-me is a first-class entry type with its own vault folder

Rather than storing grill-me entries in `notes/` with a distinguishing type field, `grill-me` gets its own `grill-me/` folder alongside `bugs/`, `ideas/`, `notes/`. This keeps the folder-per-type pattern consistent across the vault and makes the folder structure self-documenting. `TYPE_FOLDERS` drives both `write_entry()` and the scan loop, so the folder name is defined in one place.

## 2026-06-14: _read_all_entries driven from TYPE_FOLDERS.values(), not a hardcoded tuple

Previously `_read_all_entries` iterated a hardcoded `("bugs", "ideas", "notes")` tuple. When `grill-me` was added to `TYPE_FOLDERS`, two other functions (`read_entry`, `update_entry_status`) were found to have the same hardcoded tuple and were missed in the initial commit. Changed `_read_all_entries` to `set(TYPE_FOLDERS.values())` so any future type added to `TYPE_FOLDERS` is automatically scanned. `read_entry` and `update_entry_status` were also patched to include `"grill-me"` explicitly.

## 2026-06-17: workspace.css is now imported into style.css (part of the bundle)

Previously workspace.css was linked only from workspace.html, so `.pill`, `.session-card`, `.card-footer` and other shared UI classes were unavailable on other pages (Status, Skills, etc.). Adding `@import url("workspace.css")` to style.css makes these classes available everywhere via bundle.css. workspace.html still links workspace.css directly, which is harmless (CSS is idempotent).

## 2026-06-17: Container protection stored in ~/.claude-protected-containers.json

The session manager persists protected container names to `~/.claude-protected-containers.json` (alongside `~/.claude-sessions.json`). Protected containers cannot be restarted or stopped via the API (403). The `PROTECTED_CONTAINERS` env var provides defaults without requiring a pre-existing file. Protection state flows through `GET /infrastructure` as `"protected": bool` per container.

## 2026-06-18: Housekeeping scheduler uses APScheduler BackgroundScheduler pinned to 1 gunicorn worker

APScheduler's BackgroundScheduler starts a thread per process. With gunicorn's default multi-worker model, each worker would launch its own scheduler instance, causing the cron job to fire N times per trigger window and spawn N simultaneous Claude sessions. Fix: gunicorn pinned to `--workers 1` in Dockerfile CMD. If workers are ever scaled, a process-safe solution (e.g., a dedicated cron service or APScheduler's SQLAlchemyJobStore for leader election) would be required.

## 2026-06-18: Vault files owned by uid 999 — deletion must go through a container

The obsidian-capture container writes vault files as uid 999. Direct deletion from WSL2/host shell fails. Vault file deletion must go through a container that has the vault mounted R/W (ikeos at `/vault` or obsidian-capture). IkeOS exposes this as `DELETE /housekeeping/tasks/<filename>/delete` backed by `vault.delete_housekeeping_task()` which calls `filepath.unlink()` inside the container context.

## 2026-06-18: Browser JS mutation endpoints require token injected via Jinja2

Flask routes gated by `X-Capture-Token` cannot receive the token from browser JS unless it is injected into the page at render time. Pattern: pass the token from the route handler to the template, inject as `const _captureToken = {{ capture_token | tojson }};` in a `<script>` block, then include `'X-Capture-Token': _captureToken` in `fetch()` headers. Applied on `PATCH /housekeeping/schedule` (saveSchedule) and `POST /housekeeping/tasks/<f>/delete` (deleteTask).

## 2026-06-15: bundle.css is generated — always edit style.css, never bundle.css

`scripts/bundle_css.py` runs during `docker build` and overwrites `app/static/bundle.css` by inlining all `@import` chains from `app/static/style.css`. Edits made directly to `bundle.css` are silently discarded on the next build. The source of truth for all app CSS is `app/static/style.css` (and `app/static/ikeos/styles.css` for design-system tokens). The committed `bundle.css` in git reflects the last build output but is not the editing target.

## 2026-06-27: Project 'Imi — public release target is Level B

IkeOS will be released at Level B: someone can clone the repo, configure their own Obsidian vault path and token, and run `docker compose up -d` to get a working instance. Level C (general-purpose, tool-agnostic platform with no personal assumptions) is the acknowledged future horizon. All 'Imi decisions are evaluated against B while keeping C achievable.

## 2026-06-27: Project 'Imi — IkeOS web app is the brain for v1

The IkeOS Flask app is the platform brain in v1, not an adapter. Clean internal boundaries (named interfaces between the app and its dependencies) will be established during 'Imi. Actual repo restructuring — extracting components into separate repos — is deferred to a subsequent phase. Rationale: premature extraction stalls the public release without delivering value.

## 2026-06-27: Project 'Imi — engineering metrics are schema-first

The engineering metrics system (task completion time, verification failures, retry rate, deployment failures, housekeeping success, agent success rate, etc.) will have its schema and measurement intent defined during 'Imi. Write paths (instrumentation from agent sessions and hooks) are a separate phase. Rationale: reliable metric emission across sessions that can fail mid-run is an L-size distributed-observability problem — solving it before the schema is stable would produce an empty database nobody trusts.

## 2026-06-27: Project 'Imi — docker-compose split into portable base + homelab override

`docker-compose.yml` becomes a portable base with no external network dependencies (direct port binding only). `docker-compose.homelab.yml` is a gitignored or clearly-marked override that adds Traefik labels and the `traefik_network` external network. Traefik itself is flagged for evaluation in the platform audit (Adopt/Pilot/Defer/Reject) — port-based routing without HTTPS may not justify the infrastructure dependency.

## 2026-06-27: Project 'Imi — .claude/ is the Claude Code adapter contract

The `.claude/` directory is intentionally committed and public. It represents IkeOS's adapter configuration for Claude Code: how an AI coding engine must be configured to operate within IkeOS principles. `CLAUDE.md` is split into two layers: the project-level file (committed, public IkeOS platform instructions) and the user-level global `~/.claude/CLAUDE.md` (personal homelab config, never committed to any repo). Personal references (IPs, credentials, vault paths) must not appear in the project-level file.

## 2026-06-27: Project 'Imi — X-Capture-Token auth model is a deliberate single-user choice

The shared token protecting `POST /capture` and `PATCH /entries` is appropriate for IkeOS v1: single-user, trusted local network, not internet-facing. This is a documented architectural choice, not an oversight. Multi-user session-based auth is the natural next step if IkeOS becomes internet-facing or multi-tenant. Until then, the token model is correct for its threat surface.

## 2026-06-27: Project 'Imi — Session 1 scope is philosophy + decisions only

Session 1 produces PHILOSOPHY.md (the foundational document) and the above DECISIONS.md entries. No structural file changes. Session 2 begins the platform audit and cleanup using the philosophy as its north star, then determines subsequent phases.

## 2026-06-27: Experiment entry type uses separate status lifecycle

Experiments use `running → complete | abandoned` rather than the standard `new → open → in-progress → done | deferred`. Added `EXPERIMENT_STATUSES` constant to `vault_cache.py` and branched `update_entry_status_generic()` to validate against the right set per type. The PATCH /entries endpoint mirrors this branch. Standard status fields (`new`, `open`, etc.) were not extended — experiment statuses are isolated to prevent contaminating the triage flow (which looks for `status: new`).

## 2026-06-27: Housekeeping permission bug fix deferred to claude-config

The root cause of vault bug 2026-06-21 (subagents stalling on Bash permission prompts in unattended housekeeping sessions) is not fixable from the IkeOS app layer. IkeOS dispatches a Claude Code session; permission grants are governed by `claude-config/global/settings.json`. The chosen fix: add `Bash(python3 *)` and `Bash(python *)` to the allowlist in `claude-config/global/settings.json`, scoped to the claude-config project context. An idea entry has been created in the claude-config vault project tracking this work. IkeOS side: the `housekeeping.trigger` metrics event (Task 2, Session 5) provides the observability needed to detect failed or stalled runs.

## 2026-06-27: ENTRY_TYPE_CONFIG is the single registry for project-scoped vault types

`vault_cache.py` now contains `ENTRY_TYPE_CONFIG`, a dict mapping each project-scoped entry type (`note`, `idea`, `bug`, `grill-me`, `experiment`) to its folder, tag, initial status, and valid statuses. `TYPE_FOLDERS` and `TYPE_TAGS` are derived from it. `vault_entries.py` uses `ENTRY_TYPE_CONFIG.values()` for folder scans in `read_entry()` and `update_entry_status()`; `update_entry_status_generic()` uses a single `elif entry_type in ENTRY_TYPE_CONFIG:` branch. `capture.py` derives the PATCH endpoint's valid-type set and per-type valid statuses from the registry. Decisions and housekeeping types retain separate code paths (different storage layouts). Adding a new project-scoped type now requires: one entry in `ENTRY_TYPE_CONFIG`, one `elif` block in `write_entry()` for type-specific metadata fields, and UI changes (form radio + capture_json type list).

## 2026-06-27: PATCH_VALID_TYPES and CAPTURE_JSON_VALID_TYPES named in vault_cache

Two named frozenset constants (`PATCH_VALID_TYPES`, `CAPTURE_JSON_VALID_TYPES`) are derived from `ENTRY_TYPE_CONFIG` in `vault_cache.py` and re-exported through `vault.py`. `capture.py` imports them directly rather than computing equivalent sets locally on every request. This eliminates three overlapping set expressions that existed after the ENTRY_TYPE_CONFIG refactor (Session 6) and makes the type-set contract for each endpoint visible in one place. `_read_all_entries()` was also updated to iterate `ENTRY_TYPE_CONFIG.values()` directly rather than going through the `TYPE_FOLDERS` derived dict, completing the registry consolidation.

## 2026-06-30: Phase 0 metrics — append-only JSONL, read at call-time

`events.jsonl` at `METRICS_PATH` is append-only. `append_event()` opens in `"a"` mode per call. `read_events(limit)` reads the file at call-time (not import-time) so tests can patch `METRICS_PATH` without module-level binding issues. Returns newest-first by reversing the last N lines before parsing. Per-line `JSONDecodeError` is logged and skipped — a single bad line never drops all events.

## 2026-06-30: /metrics/event requires X-Capture-Token — same pattern as /capture

`POST /metrics/event` is gated by `_check_auth()` in `agents.py`. The session manager posts with `X-Capture-Token: $IKEOS_CAPTURE_TOKEN` from its `.env`. The public `GET /metrics` page does not require auth (read-only, same policy as `/projects`).

## 2026-06-30: Ephemeral sessions get --dangerously-skip-permissions

When a session is created with `initial_command` (ephemeral), Claude is launched with `--dangerously-skip-permissions`. Interactive sessions (no `initial_command`) receive normal permission flow. Rationale: unattended scheduled sessions (housekeeping, auto-tasks) stall indefinitely when subagents prompt for Bash approval — there is no user at the terminal. The `ephemeral` flag on the session record carries this state so `reset()` can restore it.

## 2026-06-30: Metrics wiring is fire-and-forget, 2s timeout

`_post_metric()` in session-manager `app.py` suppresses all exceptions and uses a 2s `urllib.request` timeout. It never blocks session create/remove/cleanup operations. This is correct for the current architecture: if IkeOS is down, metrics are silently dropped — the session operation proceeds. A persistent queue or retry mechanism would be needed only if metrics loss is unacceptable.

## 2026-06-30: send_prompt sleeps 2s after keystroke delivery before returning

After `send_command(name, command)` in `send_prompt()`, a `time.sleep(2.0)` fires before returning `True`. Without it, `parse_activity()` returns `"idle"` in the ~2s gap between tmux keystroke delivery and Claude's first visual pane update (✻ indicator), causing the next `send_prompt` call to fire before the previous command is handled. The sleep is the minimal fix; a smarter detector (watching for the pane to go non-idle then idle again) is a future improvement.

## 2026-07-01: Phase 1 — capability gate is additive pre-condition over schedule.json enabled flag

`capabilities.json` in the vault provides a safe-off gate checked in `scheduler._job()` before `trigger_now()` fires. The `schedule.json` `enabled` flag is preserved and continues to control APScheduler job state. The capability gate is an additional layer, not a replacement. Rationale: additive design avoids migration risk — existing schedule config is untouched, and the gate can be extended to future autonomous capabilities without changing the scheduler layer.

## 2026-07-01: Phase 2 — session_client.create_session() is the single session-creation path

All IkeOS→session-manager `POST /sessions` calls are centralised in `app/services/session_client.py`. `create_session()` returns a `SessionResult` frozen dataclass with `session_id`, `already_running`, `error`, and `ok` property. Callers check `result.ok` / `result.already_running` instead of raw HTTP status codes. Automatic `session.created` metric emission on success is fire-and-forget (wrapped in try/except, never raises). The `requests` import was removed from `scheduler.py` — no other function there uses it. The `requests` import stays in `housekeeping.py` — still needed by command-send, toggle/reset, and proxy routes. The blog-rewrite 409 branch (send command to running session) stays in the route because it is not session creation.

## 2026-06-27: update_entry_status() validates against per-type lifecycle

`update_entry_status()` (the web-UI status path, called by `POST /projects/<name>/<slug>/status`) previously validated `new_status` against `VALID_STATUSES` before finding the file. This meant experiments could be set to `done` (invalid) and could not be set to `complete` (valid). Fix: remove the upfront check; after finding the file by type folder, validate against `cfg["valid_statuses"]` from `ENTRY_TYPE_CONFIG`. This is the same pattern `update_entry_status_generic()` uses. The web UI status dropdown now correctly enforces per-type lifecycle rules without needing to know the entry type upfront.

## 2026-07-02: v0.1.0 released as Claude Code-specific; driver abstraction deferred

IkeOS v0.1.0 ships with Claude Code as the sole AI agent driver. `session_client.py` is a thin HTTP client for the session-manager, which hardcodes `--model sonnet` in `CLAUDE_CMD`. The driver interface is implicit, not abstracted. Decision rationale: YAGNI — abstracting before a second driver exists is speculative, and a `DriverBase` protocol before the interface is stress-tested by real use risks calcifying the wrong contract. The adapter principle (IkeOS should outlast its toolchain) is honoured by keeping all Claude Code-specific code in `session_client.py` and the session-manager — none of it leaks into `app/routes/` or `app/services/vault*.py`. A pluggable driver model is planned for v0.2, to be designed in a dedicated architecture session.

## 2026-07-02: Skill implementations stay in claude-config; IkeOS owns the API contract

IkeOS-specific Claude Code skills (`/housekeeping`, `/platform-review`) live in claude-config (private), not in IkeOS. IkeOS owns the API surface those skills call (capture endpoint, session trigger, weekly-review viewer). The integration story is documented in IkeOS (`docs/` and `CLAUDE.md`) as the canonical contract; actual skill implementations are user-supplied. A `docs/skills/` reference directory is planned for v0.2 to give contributors a starting point. This preserves the adapter principle: IkeOS is AI-tool-agnostic at the web layer; the driver (skill) layer is swappable.
