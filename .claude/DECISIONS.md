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
