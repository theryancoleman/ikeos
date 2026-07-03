---
name: triage
description: Review and triage new entries (bugs, ideas, notes) from the Obsidian vault for the current project. Requires VAULT_PATH, IKEOS_URL, CAPTURE_TOKEN, and optionally CLAUDE_CONFIG_DIR environment variables.
---

Walk through all `status: new` entries for the current project and triage them.

## Step 0: Reflection health digest

Before listing new entries, print a one-line health summary of the self-improvement system. This runs even if there are no new entries.

Run this Python3 script:

```python
import json, datetime, os

today = datetime.date.today()
cutoff_45 = (today - datetime.timedelta(days=45)).isoformat()

base = os.environ.get("CLAUDE_CONFIG_DIR")
if base and not os.path.isdir(base):
    print(f"Warning: CLAUDE_CONFIG_DIR={base!r} not found — reflection digest skipped")
    base = None

if base is None:
    print('Reflection health: library/ not found — skipping digest')
else:
    try:
        with open(f'{base}/weak-signals.json') as f:
            sig_data = json.load(f)
        signals = sig_data.get('signals', [])
        active_signals = [s for s in signals if s.get('last_seen', '') >= cutoff_45]
        pending_promotion = [s for s in active_signals if s.get('occurrences', 0) >= 3]
    except (FileNotFoundError, json.JSONDecodeError):
        active_signals = []
        pending_promotion = []

    try:
        with open(f'{base}/metrics.json') as f:
            met_data = json.load(f)
        snapshots = met_data.get('snapshots', [])
        latest = snapshots[-1] if snapshots else None
        acc_rate = latest.get('reflection_acceptance_rate') if latest else None
        week = latest.get('week', 'never') if latest else 'never'
    except (FileNotFoundError, json.JSONDecodeError):
        acc_rate = None
        week = 'never'

    abrupt = next((s for s in signals if s.get('pattern') == "Session ended without reflection via /close-session"), None)
    abrupt_count = abrupt['occurrences'] if abrupt else 0

    rate_str = f'{acc_rate:.0%}' if isinstance(acc_rate, (int, float)) else 'n/a'
    promote_str = f' ⚑ {len(pending_promotion)} pending promotion' if pending_promotion else ''
    abrupt_str = f' | {abrupt_count} abrupt endings' if abrupt_count > 0 else ''

    print(f'Reflection health: {len(active_signals)} signals (last 45d){promote_str} | acceptance rate {rate_str} (last snapshot: {week}){abrupt_str}')
```

Then continue to Step 1.

## Step 1: Determine the project

If the current working directory is under a `projects/<name>/` directory, use `<name>` as the project. Otherwise ask: "Which project would you like to triage?"

## Step 2: Find new entries

Scan these folders under `$VAULT_PATH/projects/<project>/`:
- `bugs/*.md`
- `ideas/*.md`
- `notes/*.md`
- `grill-me/*.md`

Read the YAML frontmatter of each file. Collect all entries where `status: new`.

Also scan `$VAULT_PATH/decisions/*.md` for entries with `status: proposed` (agent-drafted ADRs awaiting review — include ones matching this project or with no project). Present these separately in Step 3 as "Proposed decisions"; for each, the user decides `accepted` or `rejected` (PATCH with `type=decision`). Never auto-accept a decision.

If no new entries and no proposed decisions, say "No new entries for `<project>`." and stop.

## Step 3: Present a summary with recommendations

List all new entries together — do not group by type. Sort by urgency score (see Rules), most urgent first:

```
Found N new entries for <project>:
  [urgency] title (type) — created date
  ...
```

Then **analyze the entries together** and share brief recommendations:
- **Group:** entries that are closely related and natural to work on together (same feature area, same system, one unlocks another)
- **Sequence:** entries with a natural order (e.g. "implement X before Y makes sense")
- **Defer candidate:** any entry that seems low-value now, depends on unbuilt work, or conflicts with higher-priority items — flag it with a reason, but do not defer it automatically

Keep the analysis tight — one line per recommendation is enough.

## Step 4: Apply changes

Move every entry to `open` — no per-entry questions. Do all updates before showing output.

For each entry, call the capture API's PATCH endpoint (never edit vault files directly — file writes to the vault are permission-denied):

```bash
IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
curl -s -o /dev/null -w "%{http_code}" -X PATCH "${IKEOS_URL}/entries" \
  -H "X-Capture-Token: $CAPTURE_TOKEN" \
  -d "project=<project>" -d "type=<bug|idea|note|grill-me>" \
  -d "filename=<filename-without-.md>" -d "status=open"
```

The endpoint updates `status:`, `updated:`, and the `status/*` tag together. Expect 200; on 401 the CAPTURE_TOKEN env var is missing from this session — tell the user instead of retrying.

Decision entries (`decisions/` folder, `type=decision`) use the decision lifecycle: `proposed → accepted | rejected | superseded`.

### Why check (ideas only)

For each idea entry being opened, read its vault file and check for a `why:` frontmatter field.

If `why:` is **missing or blank**, ask the user before patching:

> "**[title]** has no 'why'. In one sentence — what problem does this solve or goal does it advance? (Skip to leave blank.)"

If the user provides a response, create a vault **note** for the same project with the why answer captured:

```bash
IKEOS_URL="${IKEOS_URL:-http://localhost:5009}"
curl -s -o /dev/null -X POST "${IKEOS_URL}/capture" \
  -d "type=note" \
  -d "project=<project>" \
  -d "title=Why: <idea title>" \
  -d "body=<why answer>"
```

If the user says "skip" or similar, move on without recording anything.

Do this check only for entries with `type: idea`. Bugs and notes do not need a why.

## Step 5: Check for overrides

After applying, ask once:

> "Opened N entries. Any you'd like to defer or hold as new?"

If the user names entries to defer: PATCH them to `status=deferred` via the same endpoint. If none: done.

## Step 6: Summary

```
Triaged N entries: X opened, Y deferred.
```

## Rules

- Never delete or directly edit vault files — all mutations go through the PATCH endpoint
- The endpoint only touches status/updated/tags; everything else is preserved automatically
- If a file can't be parsed, skip it and mention the filename
- **Urgency score** for ordering: assign a numeric score to each entry and sort descending.
  - Bug critical=40, high=30, medium=20, low=10
  - Idea high=25, medium=15, low=5
  - Note=5
  - Grill-me=5
  - Tiebreak: newer `created` date wins
- Present bugs and ideas together in this unified order — related bugs and ideas that touch the same area naturally surface near each other
- **Grill-me entries:** Label as `(grill-me)` in the summary. When an agent begins work on a grill-me entry, it must invoke `/grill-me` to interview the user and flesh out the idea before implementing anything.
