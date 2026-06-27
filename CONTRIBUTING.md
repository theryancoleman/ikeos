# Contributing to IkeOS

IkeOS is a platform for thoughtful, human-directed AI-assisted software engineering. Before contributing, read [PHILOSOPHY.md](PHILOSOPHY.md) — it explains what IkeOS is trying to be and will help you make good decisions.

---

## Vault Structure

IkeOS reads and writes entries to a vault directory. The expected structure is:

```
vault/
└── projects/
    └── <project-slug>/
        ├── bugs/
        │   └── YYYY-MM-DD-<title-slug>.md
        ├── ideas/
        ├── notes/
        ├── grill-me/
        └── experiments/   (planned)
```

Each entry is a Markdown file with YAML frontmatter. Required frontmatter fields:

```yaml
---
title: "Entry title"
type: bug          # bug | idea | note | grill-me
status: new        # new | open | in-progress | done | deferred
project: my-project
created: '2026-06-27T14:00:00'
---
```

IkeOS does not create the vault directory — you provide one via `VAULT_PATH` in `.env`.

---

## Running Locally

**Prerequisites:** Docker and Docker Compose. See [README.md](README.md) for full quickstart.

```bash
cp .env.example .env
# Edit .env — set VAULT_PATH and CAPTURE_TOKEN at minimum
docker compose up -d
```

Access at `http://localhost:5009`.

---

## Development Loop

```bash
# After any code change
docker compose up --build -d

# Stream logs
docker compose logs -f ikeos

# Run tests
docker exec ikeos pytest

# Run a specific test
docker exec ikeos pytest tests/test_vault.py -v
```

**Never test by running code on the host.** Always run inside the container — the container has the vault mount and environment variables the app depends on.

---

## Running Tests

Tests use pytest. The vault tests create a temporary directory — never the real vault.

```bash
docker exec ikeos pytest                    # all tests
docker exec ikeos pytest tests/ -v          # verbose
docker exec ikeos pytest tests/test_vault.py::test_name -v  # single test
```

Tests are in `tests/`. They mirror the source structure: `tests/test_vault.py` tests `app/services/vault.py`.

---

## Adding a Project

Projects are created by capturing the first entry against a new project slug. Either:

1. Via the web UI at `/capture` — select or type a new project name
2. Via the API:

```bash
curl -X POST http://localhost:5009/capture \
  -d "type=note" \
  -d "project=my-new-project" \
  -d "title=First entry" \
  -d "body=Project created."
```

The vault directory for the project is created automatically on first write.

---

## Adding a Skill

Skills are defined in `skills_registry.yaml`. Each skill has a name, category, description, and usage examples.

```yaml
my-skill:
  name: My Skill
  category: workflow
  description: "What this skill does in one sentence."
  usage: "/my-skill"
  examples:
    - "When to invoke this skill"
```

Skills are displayed on the `/skills` page. The `skills.py` service reads `skills_registry.yaml` and groups entries by `category`.

---

## Task Sizing and TASK.md

IkeOS uses a three-size system to determine how much process a task needs:

| Size | When | Process |
|------|------|---------|
| **S** | 1–3 files, clear scope, no schema/API/architecture change | Read → Implement → Verify |
| **M** | Multi-file, some design needed | Plan → Implement → Review → Verify |
| **L** | Cross-cutting or architectural | Architect → Approve → Implement → Review → Verify → Commit |

Before starting any M or L task, fill in `TASK.md` at the project root. The scope gate checkboxes help you identify the right size. The verification contract must be defined before starting work — the task is not done until every item is checked.

---

## Commit Style

IkeOS uses conventional commits:

```
feat: add grill-me entry type to vault
fix: resolve cache invalidation on concurrent writes
docs: update CONTRIBUTING.md with vault structure
chore: untrack generated bundle.css
refactor: extract housekeeping I/O into vault_housekeeping.py
```

The message explains **why**, not what. The diff shows what.

---

## The `.claude/` Directory

`.claude/` is the IkeOS adapter contract for Claude Code — how the AI coding engine is configured to operate within IkeOS principles.

- `CLAUDE.md` — platform instructions for Claude Code agents working on IkeOS
- `DECISIONS.md` — append-only record of non-obvious architectural decisions
- `rules/` — portable engineering standards (Python best practices, error handling, etc.)
- `agents/` — custom agent definitions (implementer, reviewer, debugger, etc.)
- `settings.json` — permission allowlist for automated commands

If you are using a different AI coding engine, `.claude/` is the reference for what an IkeOS adapter must configure. Adapt it for your engine.

---

## Architectural Decisions

Before proposing a change that affects the architecture, read `.claude/DECISIONS.md`. If your proposal contradicts an existing decision, flag the conflict explicitly before proceeding. When you make a non-obvious decision, append an entry.

Format:
```markdown
## YYYY-MM-DD: Title

Brief explanation of *why* the decision was made. One paragraph maximum.
```
