# Architectural Decisions — Obsidian Capture

> Append-only. Add an entry when a non-obvious decision is made.
> Format: `## YYYY-MM-DD: Title` followed by a brief explanation of *why*.
> Never delete entries. Mark superseded ones with `~~strikethrough~~`.

## 2026-05-26: Direct vault file writes (no REST API dependency)

The homelab PC is not always in active use. Writing directly to the vault filesystem (via Docker volume mount) means the app works regardless of whether Obsidian is running. The Local REST API would require Obsidian to be open.

## 2026-05-26: No database — vault is the storage layer

Entries are Markdown files with YAML frontmatter. This keeps them readable in Obsidian and eliminates a DB dependency. Status updates are done by Claude agents editing frontmatter directly.

## 2026-05-26: Status field with "new" distinct from "open"

Added "new" status (distinct from "open") so Claude agents can identify unchecked entries at session start without relying on creation dates. Lifecycle: new → open → in-progress → done | deferred.
