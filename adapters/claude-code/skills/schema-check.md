---
name: schema-check
description: Audit all Obsidian vault entries for tag schema compliance and optionally auto-fix unambiguous violations. Requires VAULT_PATH, IKEOS_URL, and CAPTURE_TOKEN environment variables.
---

Scan all vault entries and report any that don't conform to the tag schema defined in `$VAULT_PATH/meta/vault-schema.md`.

## Step 1: Collect entries

Run this Python script to collect all vault entries into a structured list:

```python
import json, sys, os
from pathlib import Path

_vault = os.environ.get("VAULT_PATH", "")
if not _vault:
    print("Error: VAULT_PATH environment variable is not set.")
    print("Set it to the absolute path of your Obsidian vault root.")
    sys.exit(1)
VAULT = Path(_vault)

PATTERNS = [
    "projects/*/bugs/*.md",
    "projects/*/ideas/*.md",
    "projects/*/notes/*.md",
    "projects/*/housekeeping/*.md",
]

def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    try:
        end = text.index("---", 3)
        fm_raw = text[3:end].strip()
    except ValueError:
        return None
    fm = {}
    current_list_key = None
    for line in fm_raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_list_key:
            fm.setdefault(current_list_key, []).append(stripped[2:].strip())
        elif not line.startswith(" "):
            current_list_key = None
            if ": " in line:
                k, v = line.split(": ", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                fm[k] = v if v else []
                if not v:
                    current_list_key = k
            elif line.rstrip().endswith(":"):
                k = line.rstrip(":").strip()
                fm[k] = []
                current_list_key = k
    return fm

entries = []
unparseable = []

for pattern in PATTERNS:
    for path in sorted(VAULT.glob(pattern)):
        if path.name == "last-run.md":
            continue
        rel = str(path.relative_to(VAULT))
        try:
            fm = parse_frontmatter(path)
            if fm is None:
                unparseable.append(rel)
                continue
            parts = rel.split("/")
            project = parts[1] if len(parts) >= 2 else "unknown"
            tags = fm.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            entries.append({
                "path": rel,
                "project": project,
                "filename": path.stem,
                "tags": tags,
                "type": fm.get("type", ""),
                "status": fm.get("status", ""),
                "severity": fm.get("severity", ""),
                "priority": fm.get("priority", ""),
                "interval": fm.get("interval", ""),
                "enabled": fm.get("enabled", ""),
            })
        except Exception as e:
            unparseable.append(f"{rel} ({e})")

print(f"\nCollected {len(entries)} entries ({len(unparseable)} unparseable)")
if unparseable:
    for p in unparseable:
        print(f"  ! Could not parse: {p}")
print(json.dumps({"entries": entries, "unparseable": unparseable}, indent=2), file=sys.stderr)
```

Capture the JSON from stderr for use in Step 2.

## Step 2: Validate each entry

Check every entry against these rules:

**Required tags (all entries):**
- Exactly one type tag: `bug`, `enhancement`, or `documentation`
- A project tag matching the parent project folder name
- Exactly one `status/*` tag with a valid value

**Type-specific required tags:**
- `bug` → must have one `urgency/*` tag: `critical`, `high`, `medium`, `low`
- `enhancement` → must have one `urgency/*` tag: `high`, `medium`, `low`
- `documentation` → no additional required tags

**Valid status values:**
`new`, `open`, `in-progress`, `done`, `deferred`

**Valid urgency values:**
`critical` (bugs only), `high`, `medium`, `low`

**Approved domain values:**
`auth`, `payments`, `ui`, `api`, `data`, `infra`, `data-visualization`, `game-logic`

**Exempt from standard type/urgency/status tag rules:**
- `type: housekeeping-task` — required fields: title, type, project, interval, enabled, success_definition, last_run, last_error, consecutive_failures. Tags must include `housekeeping-task` and either `status/enabled` or `status/disabled`.
- `type: housekeeping-heartbeat` — required fields: title, type, project, last_run, tasks_run, tasks_failed. Tags must include `housekeeping-heartbeat`.

**Flag as violations:**
- Missing required tag (type, project, status/*, urgency/* where applicable)
- Invalid status value (e.g., `status/closed`, `status/wontfix`)
- Old-style `priority/*` or `severity/*` tags — should be `urgency/*`
- Unrecognised domain tag (e.g., `domain/frontend` — not in approved list)
- Old-style flat tags without `status/*` (e.g., `[bug, bcr-waivers]` with no `status/` tag)
- `application/web` tag on any file (too broad to add graph signal — remove it)
- `application/*` tags on entry files (these belong on overview notes only)
- Mismatched status: `status:` frontmatter field differs from `status/*` tag value

## Step 3: Report findings

Print a summary grouped by issue type:

```
Schema check — N entries scanned

❌ Missing required tags (X):
  - bcr-waivers/bugs/2026-05-27-example.md
    missing: status/*

❌ Invalid tag values (X):
  - bcr-waivers/bugs/2026-05-27-other.md
    invalid: status/closed (valid: new, open, in-progress, done, deferred)

⚠ Status mismatch (X):
  - bcr-waivers/ideas/2026-05-27-idea.md
    frontmatter: status: open  |  tag: status/new

⚠ Unknown domain tags (X):
  - bcr-waivers/ideas/2026-05-27-idea.md
    unknown: domain/frontend

✅ N entries fully compliant
⚠  N entries need attention
```

## Step 4: Offer fixes

Vault files are **read-only** for agents — direct frontmatter edits are permission-denied. Fixes are split into two categories:

### Fixable via PATCH /entries (status violations only)

After the report, ask: **"Apply status fixes automatically?"**

These can be fixed by calling the capture API:

```python
import urllib.request, urllib.parse, os

# Substitute PROJECT_SLUG, ENTRY_TYPE, ENTRY_FILENAME, CORRECTED_STATUS with actual values
token = os.environ.get("CAPTURE_TOKEN", "")
_ikeos_url = os.environ.get("IKEOS_URL", "http://localhost:5009").rstrip("/")
data = urllib.parse.urlencode({
    "project": PROJECT_SLUG,
    "type": ENTRY_TYPE,
    "filename": ENTRY_FILENAME,
    "status": CORRECTED_STATUS,
}).encode()
req = urllib.request.Request(f"{_ikeos_url}/entries", data=data, method="PATCH")
req.add_header("X-Capture-Token", token)
with urllib.request.urlopen(req) as r:
    print(r.status)  # expect 200
```

The endpoint updates `status:`, `updated:`, and the `status/*` tag atomically. Use it for:
- **Missing `status/*` tag** when frontmatter `status:` is valid → PATCH with the existing status value to re-sync the tag
- **Status mismatch** (`status:` frontmatter differs from `status/*` tag) → PATCH with the frontmatter value (frontmatter is authoritative)
- **Invalid status value** (e.g. `status/closed`, `status/wontfix`) → PATCH with the nearest valid value; ask the user which to use if ambiguous: `deferred` or `done`

### Report-only (cannot auto-fix)

These require direct file edits which are permission-denied. List them clearly so the user can action them in Obsidian or via a future settings UI:
- Missing required type tag (`bug`, `enhancement`, `documentation`)
- Missing `urgency/*` tag on a bug or enhancement
- Unknown domain tag (flag it and ask whether to add it to the approved list in `vault-schema.md`)
- `application/*` tags on entry files
- Old-style `priority/*` or `severity/*` tags (suggest the replacement `urgency/*` value)

## Step 5: Summary

After applying fixes, print:
```
Fixed N status violations via PATCH. Y entries still need manual attention (listed above).
```

If unknown domain tags were flagged, ask:
> "Found unknown domain tag `domain/X` — should this be added to the approved list in `vault-schema.md` and `capture.html`?"

## Rules

- Vault files are read-only for agents — all mutations go through `PATCH /entries`; never attempt direct file edits
- Frontmatter `status:` field is the authoritative source — tags follow it, not the other way around
- The PATCH endpoint touches only `status:`, `updated:`, and the `status/*` tag; all other frontmatter is preserved
- If a file can't be parsed, skip it and include it in the report as "unparseable"
