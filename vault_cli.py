import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

import frontmatter as fm
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Vault loading
# ---------------------------------------------------------------------------

def load_vault(vault_path=None):
    """Load project entries and obsidiantools vault for graph checks.

    Returns (vault, entries, warnings):
      vault    -- obsidiantools Vault object (for audit graph features)
      entries  -- list of dicts, one per projects/*/bugs|ideas|notes/*.md file
      warnings -- list of filenames that could not be parsed
    """
    import obsidiantools.api as otools

    path = Path(vault_path or os.environ.get("VAULT_PATH", "/mnt/c/Server/obsidian-vault"))
    if not path.exists():
        print(f"Error: vault path not found: {path}", file=sys.stderr)
        sys.exit(1)

    vault = otools.Vault(path).connect()

    entries, warnings = [], []
    projects_dir = path / "projects"

    if projects_dir.exists():
        for proj_dir in sorted(projects_dir.iterdir()):
            if not proj_dir.is_dir():
                continue
            project = proj_dir.name
            for folder in ("bugs", "ideas", "notes"):
                type_dir = proj_dir / folder
                if not type_dir.exists():
                    continue
                for filepath in sorted(type_dir.glob("*.md")):
                    try:
                        post = fm.load(filepath)
                        entry = dict(post.metadata)
                        # Normalise datetime objects from YAML parsing
                        created = entry.get("created")
                        if hasattr(created, "isoformat"):
                            entry["created"] = created.isoformat(timespec="seconds")
                        entry["_note"] = filepath.stem
                        entry["_project"] = project
                        entry["_folder"] = folder
                        entries.append(entry)
                    except Exception:
                        warnings.append(filepath.name)

    return vault, entries, warnings


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def render_table(headers, rows, plain=False, title=None):
    """Print rows as a rich table or plain tab-separated text."""
    if not rows:
        print("Nothing found.")
        return
    if plain:
        print("\t".join(headers))
        for row in rows:
            print("\t".join(str(c) for c in row))
        return
    from rich.table import Table
    from rich.console import Console
    table = Table(*headers, title=title)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    Console().print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _age(created_str):
    if not created_str:
        return "?"
    try:
        created = datetime.fromisoformat(str(created_str))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - created).days
        return f"{days}d"
    except Exception:
        return "?"


def _priority(entry):
    return entry.get("priority") or entry.get("severity") or "-"


# ---------------------------------------------------------------------------
# Commands (stubs — filled in subsequent tasks)
# ---------------------------------------------------------------------------

def projects_cmd(entries, plain):
    from collections import defaultdict

    STATUSES = ["new", "open", "in-progress", "done", "deferred"]
    counts = defaultdict(lambda: defaultdict(int))

    for entry in entries:
        proj = entry.get("_project", "unknown")
        status = entry.get("status", "unknown")
        counts[proj][status] += 1

    if not counts:
        render_table([], [], plain=plain)
        return

    headers = ["Project", "New", "Open", "In-Progress", "Done", "Deferred", "Total"]
    rows = []
    for proj in sorted(counts):
        c = counts[proj]
        row = [proj] + [c.get(s, 0) for s in STATUSES] + [sum(c.values())]
        rows.append(row)

    render_table(headers, rows, plain=plain, title="Projects")


def status_cmd(entries, project_filter, plain):
    ACTIVE = {"open", "in-progress"}
    filtered = [
        e for e in entries
        if e.get("status") in ACTIVE
        and (project_filter is None or e.get("_project") == project_filter)
    ]
    # Sort oldest first (smallest created value first)
    filtered.sort(key=lambda e: str(e.get("created", "")))

    headers = ["Project", "Type", "Title", "Priority", "Age"]
    rows = [
        [e.get("_project", "?"), e.get("type", "?"), e.get("title", "?"),
         _priority(e), _age(e.get("created"))]
        for e in filtered
    ]
    render_table(headers, rows, plain=plain, title="Open Items")


def find_cmd(entries, filters, plain):
    result = entries
    if filters.get("project"):
        result = [e for e in result if e.get("_project") == filters["project"]]
    if filters.get("status"):
        result = [e for e in result if e.get("status") == filters["status"]]
    if filters.get("type"):
        result = [e for e in result if e.get("type") == filters["type"]]
    if filters.get("tag"):
        result = [e for e in result if filters["tag"] in (e.get("tags") or [])]

    result.sort(key=lambda e: str(e.get("created", "")))
    headers = ["Project", "Type", "Title", "Priority", "Age"]
    rows = [
        [e.get("_project", "?"), e.get("type", "?"), e.get("title", "?"),
         _priority(e), _age(e.get("created"))]
        for e in result
    ]
    render_table(headers, rows, plain=plain, title="Results")


def audit_cmd(vault, entries, project_filter, plain):
    REQUIRED_FIELDS = {"type", "status", "project", "title"}
    ACTIVE = {"open", "in-progress"}
    STALE_DAYS = 30

    scoped = entries if project_filter is None else [
        e for e in entries if e.get("_project") == project_filter
    ]
    project_notes = {e["_note"] for e in entries}

    # --- Orphaned project entries (no links in or out) ---
    orphaned = [
        n for n in (vault.isolated_notes or [])
        if n in project_notes
        and (project_filter is None or any(e["_note"] == n and e["_project"] == project_filter for e in entries))
    ]

    # --- Broken wikilink targets ---
    broken_targets = list(vault.nonexistent_notes or [])

    # --- Schema violations ---
    violations = [
        e for e in scoped
        if not REQUIRED_FIELDS.issubset(k for k in e if not k.startswith("_"))
    ]

    # --- Stale open items ---
    stale = []
    for e in scoped:
        if e.get("status") not in ACTIVE:
            continue
        try:
            created = datetime.fromisoformat(str(e.get("created", "")))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - created).days > STALE_DAYS:
                stale.append(e)
        except Exception:
            pass

    printed_something = False

    if orphaned:
        printed_something = True
        render_table(
            ["Note", "Project"],
            [[n, next((e["_project"] for e in entries if e["_note"] == n), "?")]
             for n in sorted(orphaned)],
            plain=plain, title="Orphaned Notes"
        )

    if broken_targets:
        printed_something = True
        render_table(
            ["Broken Wikilink Target"],
            [[t] for t in sorted(broken_targets)],
            plain=plain, title="Broken Wikilinks"
        )

    if violations:
        printed_something = True
        render_table(
            ["Note", "Project", "Missing Fields"],
            [[e["_note"], e.get("_project", "?"),
              ", ".join(REQUIRED_FIELDS - set(k for k in e if not k.startswith("_")))]
             for e in violations],
            plain=plain, title="Schema Violations"
        )

    if stale:
        printed_something = True
        render_table(
            ["Project", "Type", "Title", "Age"],
            [[e.get("_project", "?"), e.get("type", "?"),
              e.get("title", "?"), _age(e.get("created"))]
             for e in stale],
            plain=plain, title="Stale Open Items (>30d)"
        )

    if not printed_something:
        print("Vault looks clean.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="vault_cli", description="Obsidian vault query tool")
    parser.add_argument("--plain", action="store_true", help="Tab-separated output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("projects", help="List projects with status counts")

    p_status = sub.add_parser("status", help="Show open and in-progress items")
    p_status.add_argument("--project", metavar="PROJECT")

    p_find = sub.add_parser("find", help="Filter entries by field values")
    p_find.add_argument("--project", metavar="PROJECT")
    p_find.add_argument("--status", metavar="STATUS")
    p_find.add_argument("--type", dest="type_", metavar="TYPE")
    p_find.add_argument("--tag", metavar="TAG")

    p_audit = sub.add_parser("audit", help="Vault health check")
    p_audit.add_argument("--project", metavar="PROJECT")

    args = parser.parse_args()
    vault, entries, warnings = load_vault()

    if args.command == "projects":
        projects_cmd(entries, args.plain)
    elif args.command == "status":
        status_cmd(entries, getattr(args, "project", None), args.plain)
    elif args.command == "find":
        find_cmd(entries, {"project": args.project, "status": args.status,
                           "type": args.type_, "tag": args.tag}, args.plain)
    elif args.command == "audit":
        audit_cmd(vault, entries, getattr(args, "project", None), args.plain)

    if warnings:
        print(f"\nWarning: skipped {len(warnings)} unparseable file(s): {', '.join(warnings)}")


if __name__ == "__main__":
    main()
