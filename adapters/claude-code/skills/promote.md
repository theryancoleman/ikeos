---
name: promote
description: Promote a memory file or session decision into a draft ADR in the vault's decisions/ folder for human review. Requires IKEOS_URL and CAPTURE_TOKEN environment variables.
---

Promote durable knowledge into the vault as a draft Architecture Decision Record. This is the only bridge from agent memory to the human knowledge layer.

## Input

The argument names what to promote: a memory file (e.g. `/promote project_homelab_infrastructure`), or a description of a decision made this session (e.g. `/promote the capture-API-as-write-surface decision`). If no argument, list this session's candidate decisions and the memory index, and ask which to promote.

## Steps

1. **Gather the substance.** Read the memory file (`~/.claude/memory/<name>.md`) or reconstruct the session decision. A promotable decision has: a context that forced a choice, alternatives that were considered, the choice made, and consequences. If what's being promoted is just a fact or preference (not a decision), say so and suggest it stay in memory.

2. **Draft the ADR body** in three sections matching `templates/adr.md`:
   - `## Context` — the situation and constraints, written to be understandable in two years
   - `## Decision` — what was chosen and the key reason; name the alternatives rejected
   - `## Consequences` — what this commits us to, costs accepted, what would trigger revisiting

3. **Submit via the capture API** (never write vault files directly):

   ```bash
   IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
   curl -s -o /dev/null -w "%{http_code}" -X POST "${IKEOS_URL}/capture" \
     -d "type=decision" \
     -d "title=<decision title>" \
     -d "project=<slug, omit if cross-cutting>" \
     --data-urlencode "body=<the Context section text>"
   ```

   The draft lands in `decisions/` with `status: proposed`. Then PATCH is NOT needed — leave it `proposed`; the user accepts or rejects during `/triage`.

4. **Cross-link.** If a memory file was the source, update it (memory lives in `~/.claude/memory/`, writable) to note: "Promoted to vault ADR: <title> (proposed <date>)". Do not delete the memory — it remains the operational copy until the ADR is accepted.

5. **Report**: title, vault location, and that it awaits review in `/triage`.

## Rules

- One decision per ADR. If the input contains several decisions, propose splitting.
- Never set a decision's status to `accepted` — only the user does that.
- Write for the graph: mention related projects/systems by name so backlinks and domain tags can be added during curation.
