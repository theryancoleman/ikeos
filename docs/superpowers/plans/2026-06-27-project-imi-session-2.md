# Project 'Imi Session 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the platform audit (classify all opportunity areas as Adopt/Pilot/Defer/Reject against the philosophy), then execute the first wave of public release cleanup established in Session 1.

**Architecture:** Session 2 has two phases. The audit phase reads the codebase and evaluates each area against `PHILOSOPHY.md` principles — output is `docs/imi-audit.md`. The cleanup phase executes the four structural changes locked in Session 1 decisions: CLAUDE.md split, docker-compose split, README rewrite, and DECISIONS.md header fix.

**Tech Stack:** Python/Flask, Docker Compose, Jinja2, pytest, Markdown

**Philosophy north star:** Before classifying any area, read `PHILOSOPHY.md`. Ask: "Does this make the platform wiser, or just faster?" Faster-only = Defer or Reject.

---

## File Map

| Action | File |
|--------|------|
| Create | `docs/imi-audit.md` |
| Create | `docker-compose.homelab.yml` |
| Modify | `docker-compose.yml` |
| Modify | `CLAUDE.md` |
| Modify | `README.md` |
| Modify | `.claude/DECISIONS.md` (header line only) |
| Modify | `.env.example` (add VAULT_PATH, CLAUDE_VERSION_PATH) |
| Gitignore | `.claude/agent-memory/` |
| Gitignore | `.claude/settings.local.json` |

---

## Task 1: Platform Audit

**Files:**
- Read: `PHILOSOPHY.md`, `docker-compose.yml`, `app/services/vault.py`, `skills_registry.yaml`, `umbrella_registry.yaml`, `.claude/settings.json`, `requirements.txt`
- Create: `docs/imi-audit.md`

**Evaluation criteria (from philosophy):**
- Does it make the platform *wiser* (reflection, awareness, trust, verifiability)?
- Does it reduce complexity without losing capability?
- Does it outlast the current toolchain (adapter principle)?
- Would a new contributor be confused by it?

- [ ] **Step 1: Read core files**

```bash
wc -l app/services/vault.py app/routes/*.py
cat requirements.txt
cat skills_registry.yaml | head -40
cat umbrella_registry.yaml
cat .gitignore 2>/dev/null || echo "no .gitignore"
```

- [ ] **Step 2: Run audit classification**

Evaluate each area below. Classify as **Adopt** (keep as-is), **Pilot** (keep with caveats / experiment), **Defer** (good idea, not now), or **Reject** (not aligned with IkeOS principles or philosophy). Write rationale for each.

Areas to classify:

**Infrastructure**
- Traefik reverse proxy
- APScheduler pinned to 1 gunicorn worker
- WSL2 bind-mount for vault (performance, permissions)

**Codebase health**
- `vault.py` size (check current line count — if >700 lines, flag for decomposition)
- `skills_registry.yaml` in public repo (personal workflow config)
- `umbrella_registry.yaml` in public repo (personal project topology)
- `agent-memory/` in `.claude/` (runtime reviewer state committed to git)

**Platform capabilities**
- Engineering metrics system (schema defined in Session 1 — instrumentation deferred)
- Engineering Experiment framework (Hypothesis/Outcome/Measurement/Decision format)
- Housekeeping scheduler reliability (known bug: stalls on permission prompts)
- Evaluation framework (how does IkeOS verify its own quality?)
- Session continuity (context compaction, handoff documents)

**Repository**
- `.gitignore` completeness (does it exclude `.env`, `venv/`, `__pycache__/`, `agent-memory/`, `settings.local.json`?)
- Naming: repo is named `ikeos` but `CLAUDE.md` says "Obsidian Capture"
- Templates: does the repo provide a `TASK.md` template that contributors can use?
- Contributor experience: is there enough to onboard someone without a call?

- [ ] **Step 3: Write `docs/imi-audit.md`**

```markdown
# IkeOS Platform Audit — Project 'Imi Session 2

_Date: 2026-06-27_
_Evaluated against: PHILOSOPHY.md_

## Summary

| Area | Classification | Rationale |
|------|---------------|-----------|
| Traefik | [Adopt/Pilot/Defer/Reject] | ... |
| APScheduler 1-worker | [Adopt/Pilot/Defer/Reject] | ... |
| WSL2 vault bind-mount | [Adopt/Pilot/Defer/Reject] | ... |
| vault.py size | [Adopt/Pilot/Defer/Reject] | ... |
| skills_registry.yaml in repo | [Adopt/Pilot/Defer/Reject] | ... |
| umbrella_registry.yaml in repo | [Adopt/Pilot/Defer/Reject] | ... |
| agent-memory/ in git | [Adopt/Pilot/Defer/Reject] | ... |
| Engineering metrics | Defer (instrumentation phase) | Schema defined in Session 1 decisions |
| Experiment framework | [Adopt/Pilot/Defer/Reject] | ... |
| Housekeeping reliability | Pilot | Known bug — existing open item |
| Evaluation framework | [Adopt/Pilot/Defer/Reject] | ... |
| Session continuity | [Adopt/Pilot/Defer/Reject] | ... |
| .gitignore completeness | [Adopt/Pilot/Defer/Reject] | ... |
| Naming consistency | Reject (fix now) | Repo is ikeos, not obsidian-capture |
| TASK.md template | [Adopt/Pilot/Defer/Reject] | ... |
| Contributor experience | [Adopt/Pilot/Defer/Reject] | ... |

## Findings requiring immediate action (Session 2)

_List anything classified Reject that is a quick fix._

## Findings for Session 3+

_List Defer items with enough context for a future session to pick them up._

## What would confuse someone who cloned IkeOS today?

_Answer this question honestly. List every assumption, every missing step, every piece of tribal knowledge._
```

- [ ] **Step 4: Commit audit**

```bash
git add docs/imi-audit.md
git commit -m "docs: add 'Imi platform audit — Session 2 classification"
```

---

## Task 2: CLAUDE.md → IkeOS Platform Adapter Contract

**Files:**
- Modify: `CLAUDE.md`

The project `CLAUDE.md` is the Claude Code adapter contract — public, committed, no personal references. Personal config (IPs, credentials, vault paths) lives in the user-level global `~/.claude/CLAUDE.md` only.

- [ ] **Step 1: Rewrite `CLAUDE.md`**

Replace the entire file with the following content. Do not preserve the old "Obsidian Capture" framing — this is now the IkeOS platform adapter contract.

```markdown
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
- `CLAUDE_VERSION_PATH` — host path to `VERSION` file, mounted at `/claude-config/VERSION:ro`
- `CAPTURE_TOKEN` — shared token for mutation endpoints (`POST /capture`, `PATCH /entries`)
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
```

- [ ] **Step 2: Verify no personal references remain**

```bash
grep -n "192\.168\|homeautomation\|ServerAdmin\|C:\\\\Server\|obsidian-capture\|obsidian_capture" CLAUDE.md
```

Expected output: no matches.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: rewrite CLAUDE.md as IkeOS Claude Code adapter contract

Removes personal homelab references (IP, Windows paths, container
name). Establishes CLAUDE.md as the public adapter contract — how
Claude Code must be configured to operate within IkeOS principles.
Personal config lives in the user-level ~/.claude/CLAUDE.md only."
```

---

## Task 3: docker-compose portable base + homelab override

**Files:**
- Modify: `docker-compose.yml`
- Create: `docker-compose.homelab.yml`
- Modify: `.env.example`

The base compose must work on any machine without Traefik. Personal infrastructure goes in the override.

- [ ] **Step 1: Update `.env.example`**

Add the two new path variables:

```
VAULT_PATH=/path/to/your/obsidian-vault
CLAUDE_VERSION_PATH=/path/to/.claude/VERSION
FLASK_SECRET_KEY=change-me
CAPTURE_TOKEN=your-capture-token-here
SESSION_MANAGER_URL=http://host.docker.internal:5010
HOUSEKEEPING_PROJECT_DIR=/path/to/your/project-dir
```

- [ ] **Step 2: Rewrite `docker-compose.yml` as the portable base**

```yaml
services:
  ikeos:
    build: .
    container_name: ikeos
    restart: unless-stopped
    env_file: .env
    ports:
      - "5009:5009"
    volumes:
      - ${VAULT_PATH}:/vault:rw
      - ${CLAUDE_VERSION_PATH}:/claude-config/VERSION:ro
```

- [ ] **Step 3: Create `docker-compose.homelab.yml`**

```yaml
# Homelab overlay — adds Traefik routing for homelab deployments.
# Usage: docker compose -f docker-compose.yml -f docker-compose.homelab.yml up -d
#
# Requires traefik_network to exist:
#   docker network create traefik_network
#
# Note: Traefik is under evaluation (see docs/imi-audit.md). This overlay
# exists so the base compose works without Traefik while homelab deployment
# continues unchanged.

services:
  ikeos:
    networks:
      - traefik_network
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.ikeos.rule=Host(`homeautomation`)"
      - "traefik.http.services.ikeos.loadbalancer.server.port=5009"

networks:
  traefik_network:
    external: true
```

- [ ] **Step 4: Verify portable base works**

```bash
# Test that the base compose can be parsed without traefik_network existing
docker.exe compose config --quiet
```

Expected: exits 0, no error about missing network.

- [ ] **Step 5: Rebuild and verify the container starts**

```bash
docker.exe compose up --build -d ikeos
sleep 3
curl -sf http://localhost:5009/health
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml docker-compose.homelab.yml .env.example
git commit -m "feat: split docker-compose into portable base and homelab overlay

Base compose uses VAULT_PATH and CLAUDE_VERSION_PATH env vars instead
of hardcoded Windows paths. Traefik labels and traefik_network moved
to docker-compose.homelab.yml. Any machine can now run the base
without a Traefik instance."
```

---

## Task 4: README rewrite

**Files:**
- Modify: `README.md`

The README is the first thing a stranger reads. It must explain what IkeOS is, what they need to run it, and how to get started — without assuming any knowledge of the homelab setup.

- [ ] **Step 1: Rewrite `README.md`**

```markdown
# IkeOS

A platform for thoughtful, human-directed AI-assisted software engineering.

> The human remains the architect. The AI accelerates execution.

Read [PHILOSOPHY.md](PHILOSOPHY.md) to understand why IkeOS exists and what it's trying to be.

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

---

## Quick Start

**1. Clone and configure**

```bash
git clone <repo-url>
cd ikeos
cp .env.example .env
```

Edit `.env` and set:
- `VAULT_PATH` — absolute path to your Obsidian vault on the host
- `CLAUDE_VERSION_PATH` — path to your `.claude/VERSION` file (e.g. `~/.claude/VERSION`)
- `CAPTURE_TOKEN` — any secret string; protects mutation endpoints
- `FLASK_SECRET_KEY` — any secret string; protects Flask sessions

**2. Start**

```bash
docker compose up -d
```

**3. Access**

```
http://localhost:5009
```

---

## Homelab / Traefik Deployment

If you use Traefik as a reverse proxy, use the homelab overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.homelab.yml up -d
```

Edit `docker-compose.homelab.yml` to set your Traefik router rule.

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
See [.claude/DECISIONS.md](.claude/DECISIONS.md) for the history of architectural decisions.
```

- [ ] **Step 2: Verify no personal references remain**

```bash
grep -n "192\.168\|homeautomation\|ServerAdmin\|obsidian-capture\|C:\\\\Server" README.md
```

Expected: no matches.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README as public-facing IkeOS quickstart

Removes hardcoded homelab IP and personal paths. Explains what IkeOS
is, its prerequisites, and how to run it against any Obsidian vault.
References PHILOSOPHY.md as the entry point for understanding intent."
```

---

## Task 5: Housekeeping — gitignore and DECISIONS.md header

**Files:**
- Modify or create: `.gitignore`
- Modify: `.claude/DECISIONS.md` (first line only)

Two small fixes surfaced by the audit: agent-memory shouldn't be committed (runtime reviewer state), and the DECISIONS.md header still says "Obsidian Capture".

- [ ] **Step 1: Check current .gitignore**

```bash
cat .gitignore 2>/dev/null || echo "MISSING"
```

- [ ] **Step 2: Update or create `.gitignore`**

Ensure these entries are present:

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/

# App secrets
.env

# Claude Code
.claude/agent-memory/
.claude/settings.local.json

# Build artifacts
app/static/bundle.css
```

Note: `app/static/bundle.css` is generated at build time by `scripts/bundle_css.py` — it should not be edited directly and ideally not committed. However, if the current repo has it tracked, do not force-remove it now; flag it in `docs/imi-audit.md` as a follow-up (removing tracked files mid-project is disruptive).

- [ ] **Step 3: Fix DECISIONS.md header**

```bash
# Verify the current header
head -1 .claude/DECISIONS.md
```

Change the first line from:
```
# Architectural Decisions — Obsidian Capture
```
to:
```
# Architectural Decisions — IkeOS
```

- [ ] **Step 4: Verify agent-memory is now gitignored**

```bash
git status .claude/agent-memory/
```

Expected: the directory is untracked (not staged).

- [ ] **Step 5: Commit**

```bash
git add .gitignore .claude/DECISIONS.md
git commit -m "chore: gitignore agent-memory and fix DECISIONS header

Agent-memory is runtime reviewer state — it accumulates per-session
and is not useful as committed history. DECISIONS.md header renamed
from 'Obsidian Capture' to 'IkeOS' to match the platform name."
```

---

## Task 6: Session 2 'Imi Output

At the conclusion of every 'Imi session, produce the following. Write it as a comment directly below this task in the plan file (or as a separate note to the user — do not commit it as a file).

- [ ] **Step 1: Produce Session 2 output**

Answer each heading in 2–5 bullet points:

**Executive Summary**
What was accomplished this session? What did we learn?

**Files Changed**
List every file modified or created, with one-line description.

**Architectural Decisions**
Any new decisions made during implementation (not already in DECISIONS.md). Add them to DECISIONS.md before closing.

**Public Release Progress**
What percentage of the (B)-level blockers are now resolved? What remains?

**Technical Debt**
What shortcuts were taken? What known-imperfect things were left in place deliberately?

**Lessons Learned**
What was surprising? What would you do differently?

**Platform Health Observations**
What is in good shape? What is fragile?

**Highest ROI Next Task**
One sentence: what should Session 3 start with?

---

## Verification Contract

Session 2 is done when:

- [ ] `docs/imi-audit.md` exists and every row in the classification table is filled
- [ ] `CLAUDE.md` contains no references to `192.168`, `homeautomation`, `C:\Server`, `ServerAdmin`, or `obsidian-capture`
- [ ] `README.md` contains no hardcoded IPs or personal paths
- [ ] `docker compose config --quiet` exits 0 on the base compose file
- [ ] `curl -sf http://localhost:5009/health` returns `ok` after rebuild
- [ ] `.claude/DECISIONS.md` first line reads `# Architectural Decisions — IkeOS`
- [ ] `git status .claude/agent-memory/` shows untracked (not staged)
- [ ] All commits are on `main` with conventional commit messages
