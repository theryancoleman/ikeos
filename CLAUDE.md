# IkeOS — Claude Code Adapter Contract

> This file is the IkeOS adapter configuration for Claude Code.
> It tells Claude Code how to operate within IkeOS principles.
> Read `PHILOSOPHY.md` before making architectural decisions.
> Before proposing changes, read `.claude/DECISIONS.md`.

---

## What IkeOS Is

IkeOS is a platform for thoughtful, human-directed AI-assisted software engineering. The human remains the architect. The AI accelerates execution.

This repository is the IkeOS web app — the platform brain in v1. It provides project tracking, vault-backed knowledge capture, session management, and a housekeeping scheduler.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Web framework | Flask |
| Config | python-dotenv, `.env` file |
| Container | Docker + Docker Compose |
| Templates | Jinja2 |
| Frontend | Vanilla HTML/CSS/JS — no build pipeline |
| Vault I/O | python-frontmatter, direct file writes |

---

## Architecture

```
app/
├── __init__.py          # App factory (create_app())
├── routes/              # Thin handlers — parse request, call service, return response
│   ├── agents.py        # /dashboard, /agents, /infrastructure
│   ├── browse.py        # /tasks, /projects/<name>, /projects/<name>/<slug>
│   ├── capture.py       # /capture, /capture/json, /entries (PATCH)
│   └── housekeeping.py  # /housekeeping
├── services/
│   └── vault.py         # All vault file I/O — no Flask imports
├── templates/           # Jinja2 templates
└── static/              # CSS, JS — no build pipeline
run.py
```

### Key Rules
- Routes are thin: parse request → call service → return response.
- `vault.py` is the sole owner of all file reads/writes. Routes never touch the filesystem.
- Services are pure Python: no `request`, `g`, or `current_app`.
- No database — vault is the storage layer.
- The app must serve from `/` (root). Never use a URL path prefix.

---

## Prior Decisions

Before proposing any architectural change, read `.claude/DECISIONS.md`.
If your proposal contradicts an existing decision, flag the conflict explicitly before proceeding.
When you make a non-obvious decision, append an entry to `.claude/DECISIONS.md`.

---

## Environment Variables

See `.env.example` for all required variables. Never commit `.env`.

Key variables:
- `VAULT_PATH` — host path to mount as `/vault` inside the container
- `CLAUDE_VERSION_PATH` — host path to the Claude config `VERSION` file, mounted at `/claude-config/VERSION:ro`
- `CAPTURE_TOKEN` — shared token protecting mutation endpoints (`POST /capture`, `PATCH /entries`)
- `SESSION_MANAGER_URL` — URL of the Claude Code session manager service
- `HOUSEKEEPING_PROJECT_DIR` — host path to the project directory housekeeping runs against

---

## Docker

- Internal port: 5009
- App root is `/`. Never configure a path prefix.
- Vault mounted at `/vault` (read-write) via `VAULT_PATH` env var
- Claude config version mounted at `/claude-config/VERSION` (read-only) via `CLAUDE_VERSION_PATH`
- Non-root user in container
- Health check on `/health`

For homelab deployment with Traefik, use `docker-compose.homelab.yml` as an override.

---

## Debugging

Start with container logs before reading any source code:

```bash
docker compose logs -f ikeos
```

Diagnose from evidence. Only read source files after confirming what the container reported.

---

## Workflow

Task size determines the execution loop:

| Size | When | Flow |
|---|---|---|
| **S** — Small | 1–3 files, clear scope | Read → Implement → Verify |
| **M** — Medium | Multi-file, some design needed | Plan → Implement → Review → Verify |
| **L** — Large | Cross-cutting or architectural | Architect → Approve → Implement → Review → Verify → Commit |

---

## Testing

- Framework: pytest
- Vault tests use a temp directory — never the real vault.
- No DB — no DB test setup needed.
- Run tests: `docker exec ikeos pytest`
