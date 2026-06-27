# IkeOS Platform Audit — Project 'Imi Session 2

_Date: 2026-06-27_
_Evaluated against: PHILOSOPHY.md_

---

## Classification Summary

| # | Area | Classification | One-line rationale |
|---|------|---------------|-------------------|
| 1 | Traefik reverse proxy | Pilot | Adds infrastructure dependency with no HTTPS benefit on a local-network tool |
| 2 | APScheduler 1-worker constraint | Pilot | Functional today but documented fragility; not a durable solution |
| 3 | WSL2 vault bind-mount | Adopt | Acknowledged tradeoff with in-process cache mitigating the known perf penalty |
| 4 | vault.py size (718 lines) | Pilot | Coherent responsibility but above threshold; candidate for decomposition this session |
| 5 | skills_registry.yaml in public repo | Adopt | Intentional adapter contract; personal only in content, not in purpose |
| 6 | umbrella_registry.yaml in public repo | Reject | Personal project topology with no value to contributors; should be gitignored |
| 7 | agent-memory/ committed to git | Reject | Runtime reviewer state in version history; .gitignore already added, stale tracked files remain |
| 8 | Engineering metrics system | Defer | Schema-first decision made; instrumentation is a separate phase |
| 9 | Engineering experiment framework | Defer | Valuable but no lightweight implementation exists; define format before building |
| 10 | Housekeeping scheduler reliability | Pilot | Known open bug (permission-prompt stalls); classify as in-progress, not solved |
| 11 | Evaluation framework | Defer | Nothing exists today; defining what "good" looks like is the next step |
| 12 | Session continuity | Pilot | Skills exist; reliability in scheduled/unattended runs is the gap |
| 13 | .gitignore completeness | Reject | Missing bundle.css, settings.local.json; venv/ tracked in repo root |
| 14 | Naming consistency | Pilot | README still says "Obsidian Capture"; TASK.md template also has stale reference |
| 15 | TASK.md template | Adopt | Solid structure; the scope gate and verification contract are philosophy-aligned |
| 16 | Contributor experience | Reject | Clone-to-running has multiple undocumented prerequisites; not ready for public release |

---

## Infrastructure

### 1. Traefik reverse proxy
**Classification: Pilot**

Traefik routes HTTP by hostname (`Host(\`192.168.1.77\`)`) with no TLS. On a trusted local network with a single-user app this provides no security benefit — it adds an external network dependency (`traefik_network`) that makes `docker compose up` fail out-of-the-box for anyone without the matching Traefik stack. The adapter principle says IkeOS should outlast its toolchain; binding the base compose file to a specific reverse proxy works against portability. The docker-compose split (Task 3) will move Traefik labels to a homelab override, making the base portable. Until then, Traefik remains a necessary but unlabelled constraint.

**Action:** Task 3 (docker-compose split) addresses this directly. After the split, evaluate whether Traefik earns its keep even in the homelab overlay — a direct port mapping may be sufficient given no HTTPS requirement.

---

### 2. APScheduler 1-worker constraint
**Classification: Pilot**

The constraint is documented (DECISIONS.md 2026-06-18) and functional: pinning to `--workers 1` prevents duplicate job fires. However it is a workaround, not a solution. The gunicorn `--workers 1` flag is a global setting that will constrain all routes if request volume ever grows. The Philosophy's "if it cannot be observed, it cannot be trusted" principle applies — there is no runtime check that exactly one scheduler instance is active. If the constraint is accidentally removed during a Dockerfile change, silent duplication resumes.

**Action:** Add a startup assertion that logs `scheduler_workers=1` or raises on misconfiguration. Evaluate whether a dedicated cron service (e.g., a lightweight sidecar or the host cron) would be more durable than threading inside a web worker.

---

### 3. WSL2 vault bind-mount
**Classification: Adopt**

The cross-filesystem I/O penalty is documented in vault.py's cache comment (`~20× vs native Linux`) and mitigated by the in-process cache with a 10-minute TTL and write-invalidation. This is an honest, well-understood tradeoff for a single-user homelab tool where the vault must live on the Windows filesystem for Obsidian access. The cache invalidation pattern (writes call `_invalidate_cache()`) is coherent. For a contributor without a WSL2/Obsidian setup, a different vault path works fine — this is a configuration choice, not a code smell.

**Action:** Document the WSL2 path assumption in the forthcoming public README (Task 4). No code change needed.

---

## Codebase health

### 4. vault.py size (718 lines)
**Classification: Pilot**

At 718 lines, vault.py is above the point where a single responsibility claim requires scrutiny. Reading the file reveals it contains: cache management, project discovery, entry CRUD, status updates, housekeeping task I/O, umbrella resolution calls, and hub page reads. These are related but distinct concerns. The philosophy's "simplicity is a feature" principle flags this as a candidate. However, decomposition carries risk if done without clear interface contracts — splitting prematurely could scatter logic without improving clarity. The single-responsibility claim holds at the "vault I/O" level, but within that there are at least three sub-domains.

**Action:** Pilot a decomposition into `vault_entries.py`, `vault_projects.py`, and `vault_housekeeping.py` as a Session 3 task, once public release artifacts (README, docker-compose split) are stable. Do not decompose during this session.

---

### 5. skills_registry.yaml in public repo
**Classification: Adopt**

This is intentional. The DECISIONS.md entry (2026-06-27) frames `.claude/` as the Claude Code adapter contract. `skills_registry.yaml` is a registry of what capabilities the IkeOS adapter provides — its content is personal in the sense that Ryan wrote the skills, but its purpose is platform documentation, not personal config. A contributor cloning IkeOS would read this to understand what the platform does. The 242 lines are dense but navigable by category.

**Action:** None. Consider adding a brief header comment clarifying this is the adapter capability registry, not user preferences.

---

### 6. umbrella_registry.yaml in public repo
**Classification: Reject**

Unlike `skills_registry.yaml`, `umbrella_registry.yaml` is pure personal project topology: specific project names, Windows paths (`C:\Server\projects\...`), and private sub-project groupings. A contributor cloning IkeOS gains nothing from knowing that `rcade` contains `microgames-dev`. The Windows paths will also fail silently on any non-Windows host. This should be gitignored (a template or example provided instead), or moved to the env-configurable homelab layer.

**Action:** Add `umbrella_registry.yaml` to `.gitignore`, provide `umbrella_registry.yaml.example` with dummy entries and comments, and document the format in the README. This is a Session 2 task.

---

### 7. agent-memory/ committed to git
**Classification: Reject**

`.claude/agent-memory/` contains runtime state written by the code-reviewer agent (MEMORY.md, project_profile.md, recurring_patterns.md). This is session-specific reviewer context, not platform configuration. Committing it means: (a) every review session pollutes git history with reviewer state, (b) a fresh clone gets someone else's reviewer memory, (c) file contents can contain personal notes about codebase decisions that are not appropriate to share publicly. The `.gitignore` already has `.claude/agent-memory/` listed — but the directory is tracked because files were committed before the ignore rule was added. The stale tracked files must be removed with `git rm --cached`.

**Action:** Run `git rm -r --cached .claude/agent-memory/` to untrack the committed files. The `.gitignore` rule already prevents future commits. This is an immediate Session 2 action.

---

## Platform capabilities

### 8. Engineering metrics system
**Classification: Defer**

Decision made in DECISIONS.md (2026-06-27): schema-first, instrumentation deferred. The schema must define: what events are measured (task completion time, verification failures, retry rate, deployment failures, housekeeping success, agent success rate), who emits them (agent hooks, scheduler, vault writes), and where they land (a structured log or lightweight DB). Write paths are a separate phase after schema stabilisation.

**Action:** Schema definition is the next concrete step. Before instrumentation, answer: "What question does this metric answer, and would we act differently if the number changed?" Defer implementation to Session 4+.

---

### 9. Engineering experiment framework
**Classification: Defer**

The Hypothesis/Outcome/Measurement/Decision format is a strong idea — it operationalises the "reflection transforms experience into knowledge" principle. Nothing is implemented today. A lightweight version could be a vault entry type (`experiment`) with structured frontmatter fields. However, before implementing, the format needs to be defined against a real example: "Here is an experiment we ran, here is what the entry would have looked like." Building the format before having a concrete use case risks over-engineering.

**Action:** The next time an architectural decision involves measurable uncertainty, write it up retrospectively as the template experiment. Use that single real example to define the entry format. Defer implementation of vault integration to Session 4+.

---

### 10. Housekeeping scheduler reliability
**Classification: Pilot**

The bug is real, documented, and open (vault bug 2026-06-21, status: in-progress). Subagents dispatched by the scheduler stall on Bash permission prompts in unattended mode because they inherit the session's permission context, which prompts for unapproved Bash commands. The vault entry identifies five potential solutions. The most durable is option 5 (run the Python scanner inline in the parent agent's context rather than delegating to a subagent that lacks permissions). Until this is fixed, the scheduler cannot be trusted for unattended operation — which is its primary value.

**Action:** Prioritise the permission-prompt fix before scheduling additional housekeeping tasks. The bug is the blocker for the scheduler delivering on its promise. Revisit classification after fix.

---

### 11. Evaluation framework
**Classification: Defer**

Nothing exists today. IkeOS has no mechanism to verify its own quality: no metrics, no baseline measurements, no acceptance criteria for "is the platform getting better?" The philosophy says "if it cannot be observed, it cannot be trusted" — this applies to the platform itself. The gap is real but premature to fill without first defining what "better" means. The metrics schema (area 8) and experiment framework (area 9) are prerequisites.

**Action:** After metrics schema is defined (area 8), define three observable signals that would indicate IkeOS is improving: e.g., housekeeping completion rate, session handoff fidelity, vault entry resolution time. These become the seed of the evaluation framework.

---

### 12. Session continuity
**Classification: Pilot**

The `/handoff`, `/resume-session`, `/save-session`, and `/close-session` skills exist and work. The gap is reliability in scheduled and unattended contexts: a session that stalls mid-execution (see area 10) produces no handoff document, leaving the next session with no recovery path. Additionally, context compaction (the model's automatic memory management) can silently discard state that the human assumed was preserved. The skills are well-designed but only tested in attended, interactive sessions.

**Action:** After the housekeeping permission bug is fixed (area 10), add a `POST /sessions/<id>/handoff` endpoint that the scheduler calls on job completion or timeout. A structured JSON summary (tasks run, tasks failed, next scheduled run) is sufficient for Session 3.

---

## Repository

### 13. .gitignore completeness
**Classification: Reject**

The current `.gitignore` is missing several important entries:
- `app/static/bundle.css` — generated by `scripts/bundle_css.py` at build time; committing it pollutes diffs and creates a "last build output" confuse for contributors
- `.claude/settings.local.json` — personal permission overrides; should never be in source control
- `venv/` is listed but the `venv/` directory at project root is tracked (`venv` appears in `ls` output)

The `.gitignore` does correctly cover `.env`, `__pycache__/`, `.pytest_cache/`, and `.claude/agent-memory/`. The gaps are specific and fixable.

**Action:** Add `app/static/bundle.css` and `.claude/settings.local.json` to `.gitignore`. Run `git rm --cached venv/` if it is tracked. This is Task 5.

---

### 14. Naming consistency
**Classification: Pilot**

Multiple naming layers are in conflict. The `CLAUDE.md` header still says "Obsidian Capture — Project CLAUDE.md" (being fixed in Task 2). The `README.md` is titled "Obsidian Capture." The Docker container is named `ikeos` in docker-compose. The `DECISIONS.md` header says "Architectural Decisions — Obsidian Capture." The git repo is `ikeos`. The vault captures against `obsidian-capture` as a project slug. The `umbrella_registry.yaml` maps `ikeos` to components including `obsidian-capture`. A contributor would face three names for the same thing within the first five minutes.

**Action:** The canonical name is **IkeOS**. The `obsidian-capture` vault slug is an internal identifier that may remain for historical continuity. Every human-facing string (README title, CLAUDE.md header, DECISIONS.md header, Docker labels) should say "IkeOS." Tasks 2 and 4 cover the primary surfaces; DECISIONS.md header is Task 5.

---

### 15. TASK.md template
**Classification: Adopt**

The template is well-structured and philosophy-aligned. The scope gate (checkbox list of risk factors) operationalises the "awareness before action" principle. The verification contract section enforces "verification is not a final step." The agent loop status checklist is appropriate for M/L tasks. The template is a genuine contribution to the contributor experience.

**Action:** None structurally. Ensure the `TASK.md` in the public repo is the clean template (not a filled-in task-specific instance). Confirm it says "IkeOS" not "obsidian-capture" in any references.

---

### 16. Contributor experience
**Classification: Reject**

An honest assessment of what a stranger hits when cloning today:

- The `README.md` says "Obsidian Capture" and gives three commands with no explanation of what the app does or what problem it solves.
- `docker compose up` fails immediately with `network traefik_network declared as external, but could not be found` — no workaround documented.
- The `.env.example` exists but requires values (`VAULT_PATH`, `CAPTURE_TOKEN`, etc.) with no guidance on what they should be.
- The vault mount `C:\Server\obsidian-vault:/vault:rw` is a Windows absolute path hardcoded in `docker-compose.yml` — fails on Linux/Mac without editing.
- `umbrella_registry.yaml` refers to personal project paths with no explanation.
- The `venv/` directory may be tracked in git (appears in `ls` output).
- There is no description of the architecture, no screenshots, no "what does this do" section.
- `PHILOSOPHY.md` exists and is excellent but a contributor would not know to read it.

**Action:** Task 4 (public README rewrite) must address all of the above. The docker-compose split (Task 3) addresses the Traefik network failure. The .gitignore fix (Task 5) addresses `venv/` and `bundle.css`.

---

## What would confuse someone who cloned IkeOS today?

- **`docker compose up` fails on first run.** The `traefik_network` external network does not exist on a fresh machine. The error is opaque; there is no documented workaround.
- **The app is named three different things.** README says "Obsidian Capture," docker-compose container is `ikeos`, vault project slug is `obsidian-capture`. No canonical name is declared anywhere a new user would look.
- **The vault mount path is a Windows absolute path.** `C:\Server\obsidian-vault:/vault:rw` in docker-compose.yml breaks on Linux and Mac without editing. There is no comment explaining this or what the vault is.
- **No explanation of what the app does.** The README has a title, three commands, and nothing else. PHILOSOPHY.md explains the "why" beautifully but a contributor wouldn't know it exists.
- **`umbrella_registry.yaml` exposes personal project topology.** A contributor sees `rcade`, `pixitup`, `worldwardle` with Windows paths — none of which they have or need.
- **The `.env.example` doesn't explain its own fields.** `CAPTURE_TOKEN` is listed with no description of what it protects or how to generate a value.
- **agent-memory/ is committed.** A clone includes someone else's code-reviewer session memory — which is both surprising and potentially confusing if the reviewer memory references past decisions.
- **`venv/` may be tracked in git.** If so, a contributor's `git status` after `python -m venv venv` would show no changes, masking their local environment.
- **The skills_registry.yaml and TASK.md template are excellent but unexplained.** A contributor would skip past them as "some config files" without knowing they represent the platform's operating model.
- **There is no `CONTRIBUTING.md` or setup guide.** No instructions for running tests, understanding the vault structure, or adding a new project.

---

## Immediate actions (this session or next)

- **[Task 2]** Rewrite `CLAUDE.md` — remove personal homelab references, rename "Obsidian Capture" to "IkeOS", document the adapter contract.
- **[Task 3]** Split `docker-compose.yml` into portable base (direct port binding) and `docker-compose.homelab.yml` (Traefik labels + external network).
- **[Task 4]** Rewrite `README.md` as a public-facing quickstart: what IkeOS is, what it requires, how to run it in under 10 minutes.
- **[Task 5]** Fix `.gitignore`: add `app/static/bundle.css`, `.claude/settings.local.json`. Run `git rm -r --cached .claude/agent-memory/` to untrack stale committed files.
- **[Immediate]** Gitignore and remove `umbrella_registry.yaml` from tracking; provide `umbrella_registry.yaml.example`.
- **[Immediate]** Fix `DECISIONS.md` header ("Obsidian Capture" → "IkeOS").

---

## Deferred items (Session 3+)

- **vault.py decomposition** — Pilot decomposition into `vault_entries.py`, `vault_projects.py`, `vault_housekeeping.py` after public release artifacts are stable. Do not decompose during Session 2.
- **APScheduler durability** — Evaluate whether a dedicated cron sidecar or host-level cron would be more durable than threading inside a web worker. Prerequisite: housekeeping permission bug fixed first.
- **Housekeeping permission-prompt fix** — Resolve the open bug (vault 2026-06-21) blocking unattended scheduler operation. Most promising approach: run Python scanners inline in the parent agent context.
- **Session continuity for scheduled runs** — Add `POST /sessions/<id>/handoff` so the scheduler emits a structured JSON summary on completion or timeout.
- **Engineering metrics schema** — Define the schema (events, emitters, storage) before any instrumentation. Answer "what question does this metric answer?" for each proposed signal.
- **Experiment framework** — Write one real experiment retrospectively to define the format, then implement the vault entry type.
- **Evaluation framework** — After metrics schema, define three observable signals that indicate IkeOS is improving week-over-week.
- **CONTRIBUTING.md** — After README is solid, add a contributing guide covering: vault structure, running tests, adding a project, adding a skill, the TASK.md workflow.
