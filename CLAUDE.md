# Obsidian Capture — Project CLAUDE.md

---

## Project Overview

Web app for capturing notes, ideas, and bugs against homelab projects

---

## Hosting & Deployment

- Docker container on homelab host (192.168.1.77)
- Accessible at `http://homeautomation:5009/` — Traefik routes by port, **not** by path prefix
- Internal port: 5009 (check compose files for conflicts before using)
- **The app must serve from `/` (root). Never use a URL path prefix like `/obsidian-capture/`.**

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
├── routes/
│   ├── capture.py       # GET/POST /capture
│   └── browse.py        # /, /projects/<name>, /projects/<name>/<slug>
├── services/
│   └── vault.py         # All vault file I/O — no Flask imports
├── templates/
│   ├── base.html
│   ├── capture.html
│   ├── dashboard.html
│   ├── project.html
│   └── entry.html
└── static/
    └── style.css
run.py
```

### Key Rules
- Routes are thin: parse request → call service → return response.
- `vault.py` is the sole owner of all file reads/writes. Routes never touch the filesystem.
- Services are pure Python: no `request`, `g`, or `current_app`.
- No database — vault is the storage layer.

---

## Prior Decisions

Before proposing any architectural change, read `.claude/DECISIONS.md`.
If your proposal contradicts an existing decision, flag the conflict explicitly before proceeding.
When you make a non-obvious decision, append an entry to `.claude/DECISIONS.md`.

---

## Environment Variables

See `.env.example` for all required variables. Never commit `.env`.

---

## Docker

- Internal port: 5009
- Traefik routes by port — **no path prefix**. App root is `/`, not `/obsidian-capture/`.
- Vault mounted at `/vault` (read-write): `C:\Server\obsidian-vault:/vault:rw`
- Connect to `traefik_network` (external)
- Non-root user in container
- Health check on `/health`

---

## Debugging

Start with container logs before reading any source code:

```bash
docker compose logs -f obsidian-capture
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

Tag tasks with `Size: S`, `M`, or `L` in TASK.md. Use `/ultrareview` for M and L tasks before committing.

---

## Testing

- Framework: pytest
- Vault tests use a temp directory — never the real vault.
- No DB — no DB test setup needed.
