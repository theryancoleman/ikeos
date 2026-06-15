# Architectural Decisions — Obsidian Capture

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

## 2026-06-15: bundle.css is generated — always edit style.css, never bundle.css

`scripts/bundle_css.py` runs during `docker build` and overwrites `app/static/bundle.css` by inlining all `@import` chains from `app/static/style.css`. Edits made directly to `bundle.css` are silently discarded on the next build. The source of truth for all app CSS is `app/static/style.css` (and `app/static/ikeos/styles.css` for design-system tokens). The committed `bundle.css` in git reflects the last build output but is not the editing target.
