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
