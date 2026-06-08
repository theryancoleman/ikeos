# Vault CLI Design

**Date:** 2026-06-08
**Project:** obsidian-capture
**Status:** Approved

---

## Overview

A read-only CLI tool for querying and auditing the Obsidian vault at `/mnt/c/Server/obsidian-vault`. Lives in the `obsidian-capture` project as a sibling script to the Flask app. Invoked directly from WSL2 — does not require the Docker container to be running.

---

## Commands

```
python vault_cli.py status   [--project PROJECT] [--plain]
python vault_cli.py audit    [--project PROJECT] [--plain]
python vault_cli.py find     [--status STATUS] [--type TYPE] [--project PROJECT] [--tag TAG] [--plain]
python vault_cli.py projects [--plain]
```

### `status`
Lists all entries with `status: open` or `status: in-progress`, sorted by age (oldest first). Grouped by project. Columns: project, type, title, priority/severity, age in days (calculated from `created` frontmatter field).

### `audit`
Vault health check. Reports:
- **Orphaned notes** — notes with no wikilinks in or out (`vault.isolated_notes`)
- **Broken wikilinks** — wikilinks pointing to non-existent notes (`vault.nonexistent_notes`)
- **Schema violations** — entries missing required frontmatter fields (`type`, `status`, `project`, `title`)
- **Stale open items** — entries with `status: open` or `in-progress` and `created` more than 30 days ago

### `find`
Flexible filter over all vault entries. Any combination of `--status`, `--type`, `--project`, `--tag`. All filters are AND'd. `--tag` matches exact tag values (e.g. `--tag status/open`, `--tag domain/infra`). Outputs matching entries with the same columns as `status`.

### `projects`
Lists all projects with entry counts broken down by status (`new`, `open`, `in-progress`, `done`, `deferred`).

### `--plain`
Available on all commands. Switches from rich table output to tab-separated plain text for piping and grepping.

---

## File Structure

Single file at the project root:

```
obsidian-capture/
├── vault_cli.py          ← new
├── app/
│   └── services/
│       └── vault.py      ← existing, not modified
├── requirements.txt      ← add obsidiantools==0.11.0, rich
└── .env                  ← existing VAULT_PATH used as-is
```

### Internal layout of `vault_cli.py`

```
1. Imports & constants
   - VAULT_PATH from env (VAULT_PATH), defaulting to /mnt/c/Server/obsidian-vault
   - Valid status/type sets

2. load_vault()
   - obsidiantools.Vault(Path(VAULT_PATH)).connect()
   - Returns (vault, frontmatter_index)

3. Command functions
   - status_cmd(args)
   - audit_cmd(args)
   - find_cmd(args)
   - projects_cmd(args)

4. Output helpers
   - render_table(headers, rows, plain=False)
   - Uses rich.table.Table when plain=False, plain print when plain=True

5. main()
   - argparse with subparsers
   - Dispatches to command functions
```

---

## Data Flow

```
CLI invocation
  → parse args
  → load_vault()
      → Vault(VAULT_PATH).connect()
      → vault.front_matter_index  (dict: note_name → frontmatter dict)
      → vault.isolated_notes      (audit only)
      → vault.nonexistent_notes   (audit only)
  → filter / group in plain Python
  → render_table(headers, rows, plain=args.plain)
  → exit 0
```

`load_vault()` is called once per invocation. Cold load on this vault is sub-second; no caching needed.

---

## Configuration

`VAULT_PATH` is read from the environment using `python-dotenv`. The existing `.env` sets `VAULT_PATH=/vault` for Docker. For WSL2 direct use, set it in `~/.bashrc` (already the pattern for `PATH` additions):

```bash
export VAULT_PATH=/mnt/c/Server/obsidian-vault
```

`vault_cli.py` loads `.env` first, then environment variables override — so the shell export takes precedence over the Docker-targeted `.env` value with no extra config files needed.

---

## Error Handling

| Condition | Behaviour |
|---|---|
| `VAULT_PATH` directory not found | Print error with attempted path, exit 1 |
| Corrupt frontmatter on a file | Skip file, collect filename, print warning after output |
| No entries match filters | Print "Nothing found." — no empty table |
| obsidiantools not installed | Standard ImportError — user sees clear message to `pip install -r requirements.txt` |

---

## Dependencies Added

| Package | Version | Reason |
|---|---|---|
| `obsidiantools` | `==0.11.0` | Vault graph + frontmatter index (pinned — API churn pending on frontmatter) |
| `rich` | `>=13.0` | Coloured table output |

---

## Out of Scope

- Write operations (status updates, new entries) — those go through the obsidian-capture API
- Web/API exposure of query results — no Flask routes added
- Caching or incremental vault loads
- Wikilink graph visualisation
