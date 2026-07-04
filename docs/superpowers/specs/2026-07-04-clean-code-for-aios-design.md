# Clean Code for AIOS — Design Spec

**Date:** 2026-07-04  
**Source:** Vault idea `ikeos/ideas/2026-07-02-clean-code-as-foundational-influence...md` (priority: high)  
**Author:** Derived autonomously from vault requirements + codebase survey

---

## Problem

IkeOS has per-project rules files (`.claude/rules/`) covering Python best practices, error handling, and project structure. These are agent-instruction files — they tell Claude how to write code for IkeOS. They are not:
- A comprehensive engineering standard applicable across all AIOS projects
- Adapted for AI-native development (prompt quality, agent boundaries, context management)
- Available as a reusable skill any agent can invoke to review code
- The foundation for automated code review enforcement

The result: quality depends on which rules the active agent happens to load, and there is no persistent, reviewable standard.

---

## Scope (IkeOS session)

Three deliverables, scoped to what ships in this repo:

| # | Deliverable | File | Task size |
|---|---|---|---|
| 1 | AIOS Engineering Standard | `docs/engineering/CLEAN_CODE_FOR_AIOS.md` | M (writing task, do directly) |
| 2 | Code-review skill | `adapters/claude-code/skills/code-review.md` | M (coding, use writing-plans) |
| 3 | Cross-project work | vault entries → claude-config session | S (capture entries) |

What does NOT ship in this session:
- Updates to global `~/.claude/CLAUDE.md` → needs a claude-config session
- Agent system prompt updates for architect/reviewer/debugger → vault entry
- Automated metrics / repository health scoring → future phase

---

## Approach Decision: B — standard document + code-review skill

**Rejected A** (standard only) — delivers no enforcement.  
**Rejected C** (full multi-repo) — too large for one session; claude-config work requires a separate session with different project context.

---

## Design

### Deliverable 1: AIOS Engineering Standard

**Location:** `docs/engineering/CLEAN_CODE_FOR_AIOS.md`

Sections (each short and opinionated, not encyclopedic):

1. **Naming** — intention-revealing, consistent, no abbreviations
2. **Function design** — ~20 lines max, single responsibility, keyword args for 3+ params
3. **File & module organization** — one responsibility per file, flat > nested
4. **Comments** — WHY only; never WHAT; omit if obvious
5. **Error handling** — typed exceptions, logging.exception() at boundaries, never bare except
6. **Testing** — small fixtures, no DB (vault tests use tmp_path), one assertion cluster per test
7. **Observability** — structured logging, events.jsonl for metrics, /health endpoint
8. **Configuration** — all config from env vars, never hardcoded; .env gitignored
9. **Security** — validate at boundary, sanitize before render, no secrets in logs
10. **Refactoring** — Boy Scout Rule, behavior-preserving, incremental
11. **AI-native engineering** — prompt quality, agent responsibility boundaries, context management, tool contracts, memory usage, safety gates
12. **Code review** — what to flag (correctness, security, simplicity); how to report (file:line, impact, fix)

Each section: 100-200 words, grounded in this codebase's actual patterns.

### Deliverable 2: Code-review skill

**Location:** `adapters/claude-code/skills/code-review.md`

**Interface:**
- Invoked as: `/code-review` (optionally with path argument)
- Reads: `docs/engineering/CLEAN_CODE_FOR_AIOS.md` as the evaluation standard
- Reviews: changed files (default) or a specified path
- Output: structured report with Executive Summary, Strengths, Findings (severity + fix), and First 3 Tasks

**Findings format:**
```
## Finding: <title>
- File: path/to/file.py:L<line>
- Why it matters: ...
- Suggested fix: ...
- Effort: S/M/L
```

**Skill structure:** 4 phases
1. Load the engineering standard
2. Identify files to review (git diff --name-only HEAD vs specified path)
3. Review each file against the standard (findings list)
4. Synthesize: Executive Summary, Strengths, Findings sorted by severity, First 3 Tasks

### Deliverable 3: Cross-project vault entries

After completing 1 and 2, create vault entries in affected projects:
- `claude-config/ideas/`: update global CLAUDE.md + agent instruction files
- `ikeos/notes/`: link to the new standard in CLAUDE.md

---

## Assumptions (autonomous mode — not verified with user)

1. The engineering standard lives in IkeOS and is referenced from other projects, not duplicated. This is the authoritative source.
2. The code-review skill uses the markdown file as its evaluation rubric, not a hardcoded ruleset. This lets the standard evolve without updating the skill.
3. The skill targets Claude Code (adapters/claude-code/). Other drivers would need their own adapter.
4. "AI-native engineering" section covers the novel territory — prompt quality, agent boundaries — not covered by Clean Code 2008. This is the most differentiated part.

---

## Self-review

- No placeholders
- Scope is consistent throughout
- All deliverables are achievable in one session
- No contradictions with DECISIONS.md (this is additive documentation + a new skill)
