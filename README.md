# IkeOS

A platform for thoughtful, human-directed AI-assisted software engineering.

> The human remains the architect. The AI accelerates execution.

Read [PHILOSOPHY.md](PHILOSOPHY.md) to understand why IkeOS exists and what it is trying to be.

---

## What This Is

IkeOS is a web app that serves as the operational brain for AI-assisted engineering workflows. It provides:

- **Project tracking** — capture bugs, ideas, notes, and grill-me entries against any project
- **Vault-backed storage** — entries are Markdown files with YAML frontmatter, readable in Obsidian
- **Session management** — view and manage Claude Code agent sessions
- **Housekeeping scheduler** — automated periodic maintenance tasks

IkeOS is designed to run locally on a trusted network. It is not internet-facing software.

---

## Prerequisites

- Docker and Docker Compose
- An Obsidian vault (or any directory organised as `projects/<slug>/bugs|ideas|notes|grill-me/`)
- A Claude Code installation (for session management and housekeeping features)
- tmux (for session management features)
- **Windows users:** WSL2 — IkeOS runs in Docker via WSL2; the vault path in `.env` must be a WSL2-accessible path

---

## Quick Start

**1. Clone and configure**

```bash
git clone <repo-url>
cd ikeos
cp .env.example .env
```

Edit `.env` and set at minimum:
- `VAULT_PATH` — absolute path to your vault on the host. On Windows/WSL2, use the WSL2 mount path (e.g. `/mnt/c/Server/obsidian-vault`), not the Windows path (`C:\...`)
- `CLAUDE_VERSION_PATH` — path to your `.claude/VERSION` file (e.g. `/home/you/.claude/VERSION`)
- `CAPTURE_TOKEN` — any secret string; protects vault mutation endpoints
- `FLASK_SECRET_KEY` — any secret string; protects Flask sessions

The remaining variables in `.env.example` (`SESSION_MANAGER_URL`, `HOUSEKEEPING_PROJECT_DIR`, blog paths) are optional — leave them blank to disable those features.

**2. Start**

```bash
docker compose up -d
```

**3. Verify**

```bash
curl http://localhost:5009/health
# → ok
```

**4. Access**

Open `http://localhost:5009` in your browser.

**5. Umbrella view (optional)**

The Projects page can group related sub-projects under an umbrella. To enable it, copy the example config and edit it to match your setup:

```bash
cp umbrella_registry.yaml.example umbrella_registry.yaml
```

`umbrella_registry.yaml` is gitignored — it contains local paths specific to your machine.

---

## Homelab / Traefik Deployment

If you use Traefik as a reverse proxy, use the homelab overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.homelab.yml up -d
```

Edit `docker-compose.homelab.yml` to set your Traefik router rule before running.

---

## Development

```bash
docker compose up --build    # rebuild after code changes
docker compose logs -f ikeos # stream logs
docker exec ikeos pytest     # run tests
```

---

## Architecture

See [CLAUDE.md](CLAUDE.md) for the full architecture and Claude Code adapter contract.

The wire contract for session drivers is documented in [docs/SESSION_DRIVER_API.md](docs/SESSION_DRIVER_API.md).

See [.claude/DECISIONS.md](.claude/DECISIONS.md) for the history of architectural decisions.
