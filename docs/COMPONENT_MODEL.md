# IkeOS Component Model

> Canonical map of every component in the IkeOS ecosystem — what each one is, where it lives, what it depends on, and what it must never do. See `PHILOSOPHY.md` for the principles this model operationalizes, and `.claude/DECISIONS.md` for why this document exists.
>
> Paths in this document were verified against the repo on 2026-08-19 — treat as potentially stale if read much later.

## 1. Overview

IkeOS is not one repo — it's five components spread across two git repos. This document exists because that split had never been written down in one place, and two of the components had quietly drifted apart as a result (see §7).

| Component | Repo / Path |
|---|---|
| Interface | `ikeos/app/` |
| Vault | Obsidian vault filesystem (not code) |
| Harness | `claude-config/global/` → deployed to `~/.claude` |
| Adapters | `ikeos/adapters/claude-code/` |
| Self-Improvement | `ikeos/app/services/{scheduler,driver,metrics,reflection,research_findings,reviews}.py` + `claude-config/library/{metrics,weak-signals,research-*}.json` + `claude-config/evals/` |

## 2. Interface

- **What it is:** The Flask web app — dashboard, vault browser, capture UI, housekeeping UI. The human-facing surface and "platform brain" per `CLAUDE.md`.
- **Where it lives:** `ikeos/app/` (routes/services/templates/static).
- **Depends on:** Vault (via the `vault*` service modules — `vault.py` is the public facade over `vault_cache.py`/`vault_entries.py`/`vault_projects.py`/`vault_graph.py`/`vault_housekeeping.py`/`vault_council.py`; routes never touch the filesystem directly), Adapters (session driver client, capture API contract), Self-Improvement data (reads `claude-config/library/*.json` read-only via the `CLAUDE_CONFIG_PATH` mount).
- **Must not:** Touch the filesystem outside the `vault*` service modules; embed Claude-Code-specific (harness) logic in the portable contract — the portable contract (`ikeos/adapters/claude-code/`) must stay tool-agnostic and env-var driven. The Interface-side adapter client (`app/services/driver.py`, `app/services/session_client.py`) is the seam that calls into Adapters/Harness and is permitted to be Claude-Code-aware (e.g. it constructs literal slash-command strings).

## 3. Vault

- **What it is:** The Obsidian Markdown store — the storage layer (no database, per `.claude/DECISIONS.md` 2026-05-26).
- **Where it lives:** Host filesystem, mounted read-write into `ikeos` via `VAULT_PATH`.
- **Depends on:** Nothing — it's the ground truth other components read and write against.
- **Must not:** Be written directly by agents — all writes go through the capture API (`POST /capture`, `PATCH /entries`), per the 2026-06-11 decision.

## 4. Harness

- **What it is:** The deployed Claude Code configuration that shapes agent behavior day to day — rules, slash-command skills, permission baseline, hooks wiring.
- **Where it lives:** `claude-config/global/` (commands, rules, settings.json), synced by `scripts/sync.sh apply` to the live `~/.claude` runtime directory. This is the actual analog to an external, static conventions/hooks repo a colleague maintains. `claude-config/library/agents/` (six subagent definitions) is also deployed, via `scripts/sync.sh backfill`, into every project's `.claude/agents/`; `claude-config/library/rules/{stack}/` is likewise deployed into individual projects, via the `/new-project` and `/init-config` scaffolding skills rather than `sync.sh`. `claude-config/library/skills/` is different again — it's a manual staging area (per `claude-config/docs/user-guide.md`): a new skill is drafted there first, then hand-moved to `global/` to go live or hand-copied during `/new-project` scaffolding for a project-local copy; nothing auto-deploys directly out of `library/skills/`.
- **Depends on:** Nothing IkeOS-specific in principle — most of `claude-config/global/commands/` (e.g. blog, deploy-cottage, wire-remote) has nothing to do with IkeOS at all. The subset that *is* IkeOS-specific (triage, housekeeping, promote, schema-check, close-session) is derived from Adapters (see §5).
- **Must not:** Be the only place an IkeOS-specific skill's logic exists — the portable version belongs in Adapters, so IkeOS can be stood up elsewhere without this deployment's hardcoded paths.

## 5. Adapters

- **What it is:** The portable contract/reference-implementation connecting an external AI coding tool (currently Claude Code) to an IkeOS instance — env-var-driven skill definitions, a reference session-manager (Session Driver API), a reference StopHook script. This is what `PHILOSOPHY.md`'s "Adapter Principle" refers to: replaceable, defines the contract, not coupled to one deployment.
- **Where it lives:** `ikeos/adapters/claude-code/` (`skills/`, `session-manager/`, `hooks/`).
- **Depends on:** Documents the Session Driver API (`docs/SESSION_DRIVER_API.md`) that Interface also implements against.
- **Must not:** Contain one specific deployment's hardcoded paths or hostnames — must stay env-var driven (`VAULT_PATH`, `IKEOS_URL`, `CLAUDE_CONFIG_DIR`) so it's usable as a template by anyone else deploying IkeOS.

## 6. Self-Improvement (the "utilities" layer)

- **What it is:** The housekeeping/reflection/metrics instrumentation that lets IkeOS observe and improve its own operation over time — distinct from Harness (which shapes behavior) and Interface (which displays state).
- **Where it lives, split across both repos:**
  - `ikeos` side computes/serves: `app/services/scheduler.py` (APScheduler cron), `app/services/driver.py` (the Claude Code adapter client — maps IkeOS intents onto driver sessions, including spawning scheduled housekeeping sessions, by constructing slash-command strings like `/housekeeping`, `/platform-review`, `/council-discuss`, `/council-action`; blog-related sessions instead send natural-language instructions rather than a `/blog` slash command), `app/services/metrics.py`, `app/services/reflection.py`, `app/services/research_findings.py`, `app/services/reviews.py`.
  - `claude-config` side generates/stores the raw signal: `library/{metrics.json, weak-signals.json, research-*.json}` (mounted read-only into `ikeos` via `CLAUDE_CONFIG_PATH`), `evals/` (runner/judge/baselines — agent quality over time), `scripts/stophook-reflection.sh` (the hook that captures weak signals at session end).
- **Depends on:** Harness (the StopHook is wired via `claude-config` hook config) and Interface (renders the dashboards).
- **Must not:** Have `ikeos` write to `claude-config/library/*.json` directly — it's a read-only mount into `ikeos`. (Writers on the `claude-config` side include the StopHook, the eval runner, several Claude Code skills such as `close-session`, and `session-manager/research_sources.py`.)

## 7. Known duplication / drift points (documented, not resolved)

- **Skills:** `ikeos/adapters/claude-code/skills/*.md` (portable, env-var driven) and `claude-config/global/commands/*.md` (deployed, hardcoded to this deployment's paths) are two independently-maintained copies of the same five skills (`triage`, `housekeeping`, `promote`, `schema-check`, `close-session`). `code-review.md` exists only in the adapter copy — it has no deployed counterpart in `claude-config/global/commands/`, a one-way asymmetry rather than a straight five-way duplication. Confirmed diverged as of 2026-08-19 — all five duplicated files differ between the two copies; `triage.md` is the example cited, where the deployed copy was found missing a `CLAUDE_CONFIG_DIR` fallback present in the adapter copy.
- **Session Manager:** `ikeos/adapters/claude-code/session-manager/` (reference) and `claude-config/services/session-manager/` (deployed) follow the same pattern. One prior sync effort exists (`.claude/DECISIONS.md`, 2026-07-22; `docs/superpowers/plans/2026-07-21-session-manager-adapter-sync.md`) — it documents a single sync event, not a standing process.
- **No tooling watches this boundary.** `claude-config/scripts/check-drift.sh` only diffs `claude-config/global/` against the deployed `~/.claude` — it has no awareness of `ikeos/adapters/` at all.
- Resolution — choosing a sync direction, building drift detection, or physically consolidating — is deferred; no decision has been recorded yet.

## 8. Cross-links

- `README.md` links to this document from its architecture section.
- `CLAUDE.md` links to this document from its header block.
- `.claude/DECISIONS.md` records why this document was created.
