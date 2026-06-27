# Project 'Imi Session 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining public release housekeeping from Session 2, then write the three definition documents that Session 4 will implement — metrics schema, experiment framework format, and contributor guide.

**Architecture:** Session 3 is definition-first. Tasks 1–2 are small S-size file changes (untrack artifacts, fix CLAUDE.md). Tasks 3–5 produce specification documents — no code. This keeps the working system stable while establishing the vocabulary Session 4 will build against.

**Tech Stack:** Python/Flask, Docker, Markdown, YAML, JSON-lines

**Philosophy north star:** Read `PHILOSOPHY.md` before writing any document. "Reflection transforms experience into knowledge" — the schema and framework documents must answer real questions IkeOS has faced, not hypothetical ones.

---

## File Map

| Action | File |
|--------|------|
| Untrack (git rm --cached) | `app/static/bundle.css` |
| Untrack (git rm --cached) | `umbrella_registry.yaml` |
| Add to .gitignore | `umbrella_registry.yaml` |
| Create | `umbrella_registry.yaml.example` |
| Modify | `CLAUDE.md` — services/ tree only |
| Create | `docs/metrics-schema.md` |
| Create | `docs/experiment-framework.md` |
| Create | `CONTRIBUTING.md` |

---

## Task 1: Untrack committed artifacts and provide examples

**Files:**
- Modify: `.gitignore`
- Delete from tracking: `app/static/bundle.css`, `umbrella_registry.yaml`
- Create: `umbrella_registry.yaml.example`

Both files are committed but should not be. `app/static/bundle.css` is a generated build artifact — it was added to `.gitignore` in Session 2 but never untracked. `umbrella_registry.yaml` contains personal project topology with Windows paths — it must be replaced by an example file contributors can copy and adapt.

- [ ] **Step 1: Verify both files are currently tracked**

```bash
git ls-files app/static/bundle.css umbrella_registry.yaml
```

Expected output (both lines present):
```
app/static/bundle.css
umbrella_registry.yaml
```

- [ ] **Step 2: Add `umbrella_registry.yaml` to .gitignore**

Read the current `.gitignore` and append this line in the "Build artifacts" or a new "Project config" section:

```
# Personal project config — copy from umbrella_registry.yaml.example
umbrella_registry.yaml
```

The `.gitignore` already has these relevant entries from Session 2:
```
app/static/bundle.css
.claude/settings.local.json
.claude/agent-memory/
```

Append `umbrella_registry.yaml` after `app/static/bundle.css`.

- [ ] **Step 3: Create `umbrella_registry.yaml.example`**

Write this content exactly:

```yaml
# umbrella_registry.yaml
# Maps project slugs to their component sub-projects.
#
# Copy this file to umbrella_registry.yaml and configure for your projects.
# umbrella_registry.yaml is gitignored — your project config stays private.
#
# Umbrella projects: set components to a non-empty list.
#   Components will be hidden from the top-level project picker and
#   captured into the umbrella's vault folder.
#
# Flat projects: set components to an empty list [].
#   These appear as normal projects with no component picker.
#
# codebases: absolute paths to the relevant source directories on disk.
#   Used by housekeeping and session management to locate project files.

# Example umbrella project with two components
my-platform:
  name: My Platform
  codebases:
    - /path/to/my-platform
    - /path/to/my-platform-worker
  components:
    - web-app
    - background-worker

# Example flat project (no components)
my-tool:
  name: My Tool
  codebases:
    - /path/to/my-tool
  components: []
```

- [ ] **Step 4: Untrack both files**

```bash
git rm --cached app/static/bundle.css
git rm --cached umbrella_registry.yaml
```

Expected output:
```
rm 'app/static/bundle.css'
rm 'umbrella_registry.yaml'
```

- [ ] **Step 5: Verify the files are now untracked**

```bash
git status app/static/bundle.css umbrella_registry.yaml
```

Expected: both show as untracked (not staged).

```bash
ls app/static/bundle.css umbrella_registry.yaml
```

Expected: both files still exist on disk (untracking does not delete them).

- [ ] **Step 6: Commit**

```bash
git add .gitignore umbrella_registry.yaml.example
git commit -m "chore: untrack generated and personal config files

Untrack app/static/bundle.css (generated at build time by
scripts/bundle_css.py — should not be in source control).
Untrack umbrella_registry.yaml (personal project topology with
Windows paths). Provide umbrella_registry.yaml.example with
documented format for contributors to copy and adapt."
```

---

## Task 2: Fix CLAUDE.md services/ architecture tree

**Files:**
- Modify: `CLAUDE.md` — lines 42–43 (the services/ section in the architecture tree)

The services/ tree currently shows only `vault.py`. There are three other services: `scheduler.py`, `skills.py`, and `umbrella.py`. A contributor reading CLAUDE.md would not know these exist.

- [ ] **Step 1: Read the current architecture section**

```bash
grep -n "services/" /mnt/c/Server/projects/ikeos/CLAUDE.md
ls /mnt/c/Server/projects/ikeos/app/services/
```

- [ ] **Step 2: Update the services/ tree**

Find this section in `CLAUDE.md`:

```
├── services/
│   └── vault.py         # All vault file I/O — no Flask imports
```

Replace with:

```
├── services/
│   ├── vault.py         # All vault file I/O — no Flask imports
│   ├── scheduler.py     # APScheduler housekeeping job setup and management
│   ├── skills.py        # Reads skills_registry.yaml, groups skills by category
│   └── umbrella.py      # Reads umbrella_registry.yaml, resolves project component trees
```

- [ ] **Step 3: Verify no personal references introduced**

```bash
grep -n "192\.168\|homeautomation\|ServerAdmin\|C:\\\\Server" /mnt/c/Server/projects/ikeos/CLAUDE.md
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: expand services/ tree in CLAUDE.md adapter contract

Add scheduler.py, skills.py, and umbrella.py to the architecture
tree. A contributor reading CLAUDE.md now sees the full services
layer, not just vault.py."
```

---

## Task 3: Engineering metrics schema

**Files:**
- Create: `docs/metrics-schema.md`

Define what IkeOS measures, why each signal matters, and what format stores it. No instrumentation — just the schema. Answer "what question does this metric answer?" for every event type before defining its fields.

The storage format is JSON-lines (`.jsonl`): one JSON object per line, append-only, readable with any tool, no database required.

- [ ] **Step 1: Write `docs/metrics-schema.md`**

Write this exact content:

```markdown
# IkeOS Engineering Metrics Schema

_Status: Defined — not yet instrumented_
_Instrumentation phase: Session 4+_

---

## Why This Exists

"If it cannot be observed, it cannot be trusted." — IkeOS Philosophy

IkeOS has no current mechanism to verify its own quality. This schema defines what to measure and why. Instrumentation (write paths from agents, hooks, and the scheduler) follows in a later phase, once the schema is stable and validated against real questions.

Before implementing any metric, answer: **"What question does this answer, and would we act differently if the number changed?"** If the answer is no, the metric does not belong here.

---

## Storage Format

**Location:** `~/.claude/metrics/events.jsonl`

**Format:** JSON-lines — one JSON object per line, append-only.

```jsonl
{"timestamp": "2026-06-27T14:00:00Z", "event": "task.complete", "session_id": "...", "project": "ikeos", "task_size": "S", "duration_ms": 45000, "outcome": "success", "commit_sha": "abc1234"}
{"timestamp": "2026-06-27T14:05:00Z", "event": "verification.failure", "session_id": "...", "project": "ikeos", "stage": "health_check", "retry_count": 1, "error_summary": "container not healthy after rebuild"}
```

**Why JSON-lines:**
- Append-only (no locking, no transactions needed)
- Readable with `grep`, `jq`, Python — no tooling required
- Each line is self-contained (partial reads are safe)
- Works as a flat file forever; can be imported into SQLite when analysis needs grow

---

## Common Fields (all events)

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 string | When the event occurred (UTC) |
| `event` | string | Event type (see below) |
| `session_id` | string | Unique ID for the Claude Code session |
| `project` | string | Project slug (matches vault project slug) |

---

## Event Types

### `task.complete`

**Question answered:** Are tasks getting done, and how long do they take?

| Field | Type | Description |
|-------|------|-------------|
| `task_size` | `"S"` \| `"M"` \| `"L"` | Size classification from TASK.md |
| `duration_ms` | integer | Wall time from task start to commit |
| `outcome` | `"success"` \| `"abandoned"` | Whether the task produced a commit |
| `commit_sha` | string \| null | Git SHA if committed |
| `files_changed` | integer | Number of files in the commit |

---

### `verification.failure`

**Question answered:** Where do we fail most often, and are we improving?

| Field | Type | Description |
|-------|------|-------------|
| `stage` | string | `"build"`, `"health_check"`, `"tests"`, `"lint"` |
| `error_summary` | string | One-line description of the failure |
| `retry_count` | integer | How many times this verification was retried |
| `resolved` | boolean | Whether the failure was resolved in the same session |

---

### `deployment.attempt`

**Question answered:** How reliable is our deployment process?

| Field | Type | Description |
|-------|------|-------------|
| `service` | string | Docker service name |
| `outcome` | `"success"` \| `"failure"` | Result of `docker compose up --build` |
| `duration_ms` | integer | Time to deploy |
| `error_summary` | string \| null | Failure reason if outcome is failure |

---

### `housekeeping.run`

**Question answered:** Is the housekeeping scheduler actually working?

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | `"scheduled"` \| `"manual"` | How the run was initiated |
| `tasks_run` | integer | Number of housekeeping tasks attempted |
| `tasks_succeeded` | integer | Tasks that completed without error |
| `tasks_failed` | integer | Tasks that failed or stalled |
| `duration_ms` | integer | Total run time |
| `stalled_on_permission` | boolean | Whether the run stalled on a Bash permission prompt |

---

### `session.end`

**Question answered:** How long do sessions run, and are they being closed cleanly?

| Field | Type | Description |
|-------|------|-------------|
| `duration_ms` | integer | Session wall time |
| `context_compacted` | boolean | Whether auto-compaction fired during the session |
| `closed_via_skill` | boolean | Whether `/close-session` was run (vs abrupt end) |
| `tasks_completed` | integer | Number of tasks marked done in this session |

---

### `agent.dispatch`

**Question answered:** Are subagents succeeding, and which task types fail most?

| Field | Type | Description |
|-------|------|-------------|
| `agent_type` | string | `"implementer"`, `"reviewer"`, `"debugger"`, etc. |
| `task_label` | string | Short description of what the agent was given |
| `outcome` | `"done"` \| `"done_with_concerns"` \| `"blocked"` \| `"needs_context"` | Agent's reported status |
| `duration_ms` | integer | Agent run time |
| `model` | string | Model used (e.g. `claude-sonnet-4-6`) |

---

### `manual.intervention`

**Question answered:** Where is the agent failing to work autonomously?

| Field | Type | Description |
|-------|------|-------------|
| `reason` | string | Why the human had to intervene |
| `context` | string | What the agent was doing when it needed help |
| `blocker_type` | string | `"permission"`, `"ambiguity"`, `"error"`, `"design_decision"` |

---

## Derived Signals

These are computed from raw events — not stored as events themselves.

| Signal | Derived from | Indicates |
|--------|-------------|-----------|
| Task completion rate | `task.complete` outcome | Are we shipping? |
| Verification failure rate | `verification.failure` per `task.complete` | Are we breaking things? |
| Housekeeping reliability | `tasks_succeeded / tasks_run` in `housekeeping.run` | Is the scheduler trustworthy? |
| Session clean-close rate | `closed_via_skill` in `session.end` | Are we reflecting? |
| Agent success rate | `done` / total in `agent.dispatch` | Are subagents effective? |
| Autonomous operation rate | `manual.intervention` per session | Is the platform getting more self-sufficient? |

---

## What Is Not Measured (and Why)

| Candidate | Decision | Reason |
|-----------|----------|--------|
| Lines of code added/removed | Rejected | Incentivises wrong behaviour; not correlated with quality |
| Number of commits | Rejected | Noisy; a sign of activity, not progress |
| Test coverage % | Deferred | Requires a consistent test runner; add when tests are more complete |
| Token usage per session | Deferred | Claude Code does not currently expose this directly |
```

- [ ] **Step 2: Commit**

```bash
git add docs/metrics-schema.md
git commit -m "docs: define IkeOS engineering metrics schema

Establishes what to measure (7 event types), why each signal matters,
JSON-lines storage format, derived signals, and what is explicitly
not measured. Instrumentation follows in a later phase."
```

---

## Task 4: Experiment framework format

**Files:**
- Create: `docs/experiment-framework.md`

Define the format for engineering experiments. The key insight from the audit: "before implementing, define the format against a real example." This task defines the format AND includes one retrospective real experiment so the format is validated against something that actually happened.

- [ ] **Step 1: Write `docs/experiment-framework.md`**

Write this exact content:

```markdown
# IkeOS Engineering Experiment Framework

_Status: Format defined — vault entry type pending_

---

## Why This Exists

"Reflection transforms experience into knowledge." — IkeOS Philosophy

Not every decision IkeOS makes is obvious. Some are bets: we hypothesise that X will work, we try it, and we find out. Without a format to capture the hypothesis, measurement, and outcome, the lesson dissolves. We make the same bet again, or we never revisit a decision that deserved reconsideration.

The experiment framework makes bets explicit, measurements honest, and decisions durable.

---

## When to Use an Experiment

An experiment is appropriate when:
- The right answer is genuinely uncertain before trying
- There is a measurable signal that would distinguish success from failure
- The outcome would change future decisions if it went the other way

An experiment is NOT appropriate for:
- Decisions with an obvious correct answer
- Pure preference choices (style, naming) with no measurable outcome
- Decisions that cannot be reversed — commit to those as decisions, not experiments

---

## Format

Experiments live as vault entries with `type: experiment`. Frontmatter holds the structured fields; the body holds narrative context.

### Frontmatter schema

```yaml
---
type: experiment
title: "One sentence describing the bet"
hypothesis: "If we do X, then Y will happen"
expected_outcome: "Specific, measurable result if the hypothesis is correct"
measurement: "How we will know — what we will observe or measure"
success_criteria: "The threshold that counts as success"
timebox: "How long we will run before deciding"
status: running   # running | complete | abandoned
result: ""        # fill in when complete
decision: ""      # adopt | reject | pivot — fill in when complete
project: project-slug
created: 'YYYY-MM-DDTHH:MM:SS'
---
```

### Body template

```markdown
## Context

Why this experiment was started. What problem or uncertainty prompted it.

## What we tried

Brief description of the implementation or change made.

## What we observed

Actual measurements, log excerpts, or user feedback. Specific, not vague.

## Decision rationale

Why we chose to adopt, reject, or pivot — based on what we observed.
```

---

## Example: In-Memory Cache for Vault Reads

_Retrospective — this experiment was run and decided in June 2026._

```yaml
---
type: experiment
title: "Global in-memory cache for vault reads on WSL2"
hypothesis: "If we cache all vault entries in-process with a 10-minute TTL, page load times will drop below 200ms on WSL2"
expected_outcome: "Per-project page loads under 200ms after first cache warm-up"
measurement: "Browser DevTools network timing for /projects/<slug> — cold vs warm cache"
success_criteria: "Warm-cache response under 200ms; cold-cache miss under 2000ms"
timebox: "One session — measure during implementation"
status: complete
result: "Cold-cache miss: ~1.1s (scans all entries). Warm-cache hit: <50ms. Both within criteria."
decision: adopt
project: ikeos
created: '2026-06-13T00:00:00'
---
```

**Context**

WSL2 bind-mounts incur a ~20× I/O penalty vs native Linux. With 174+ vault entries, per-project reads were taking ~1.1s on cold load — noticeable on every navigation.

**What we tried**

Changed `read_entries()` to always populate a global `_entries_cache` on miss, then filter in-memory for per-project requests. Cache TTL: 10 minutes. Writes call `_invalidate_cache()`.

**What we observed**

Cold-cache miss (first request after invalidation): ~1.1s — acceptable for the vault size and miss frequency. Warm-cache hit: <50ms. The tradeoff: a cold miss now scans all entries instead of just one project's files. In practice, cache warm-up happens on first page load and persists for the session.

**Decision rationale**

Adopted. The tradeoff is well-understood, documented in DECISIONS.md, and the warm-cache performance justifies it. Cache invalidation on writes prevents stale reads. The constraint (WSL2 bind-mount penalty) is environmental, not architectural — this is the right mitigation given the constraint.

---

## Vault Integration (Deferred)

Adding `experiment` as a first-class vault entry type requires:
1. Adding `"experiment"` to `VALID_TYPES` and `TYPE_FOLDERS` in `vault.py`
2. Creating an `experiments/` folder in the project vault directory
3. Adding an experiment capture form or API endpoint

This is deferred to Session 4+. Until then, experiments can be written as `notes/` entries with `type: experiment` in the body, or as Markdown files in `docs/`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/experiment-framework.md
git commit -m "docs: define IkeOS experiment framework format

Format for capturing engineering bets: hypothesis, measurement,
success criteria, decision. Includes a retrospective real example
(vault read cache) to validate the format against something that
actually happened. Vault entry type integration deferred to Session 4."
```

---

## Task 5: CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

A contributor who clones IkeOS today has no guide for: how the vault is structured, how to run tests, how to add a project, what the TASK.md workflow is, or what `.claude/` means. This gap was the final "Reject" item in the Session 2 audit.

- [ ] **Step 1: Write `CONTRIBUTING.md`**

Write this exact content:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add CONTRIBUTING.md — vault structure, dev loop, task sizing

Covers vault structure, running locally, dev loop, testing, adding
projects and skills, TASK.md workflow, commit style, and the .claude/
adapter contract. Addresses the final Reject item from the 'Imi audit."
```

---

## Task 6: Session 3 'Imi Output

At the conclusion of every 'Imi session, produce the 8-section output. Report it directly to the user (do not commit it as a file).

- [ ] **Step 1: Produce Session 3 output**

Answer each heading:

**Executive Summary** — What was accomplished? What did we learn?

**Files Changed** — Every file modified or created, one-line description.

**Architectural Decisions** — Any new decisions. Add to DECISIONS.md before closing.

**Public Release Progress** — Which Level B blockers remain?

**Technical Debt** — What shortcuts were taken deliberately?

**Lessons Learned** — What was surprising?

**Platform Health Observations** — What is in good shape? What is fragile?

**Highest ROI Next Task** — One sentence: what should Session 4 start with?

---

## Verification Contract

Session 3 is done when:

- [ ] `git ls-files app/static/bundle.css umbrella_registry.yaml` returns empty (both untracked)
- [ ] `umbrella_registry.yaml.example` exists with documented format
- [ ] `CLAUDE.md` services/ tree shows all four services (vault.py, scheduler.py, skills.py, umbrella.py)
- [ ] `docs/metrics-schema.md` exists with 7 event types defined
- [ ] `docs/experiment-framework.md` exists with format and real retrospective example
- [ ] `CONTRIBUTING.md` exists covering vault structure, dev loop, tests, task sizing, commit style
- [ ] All commits on `main` with conventional commit messages
