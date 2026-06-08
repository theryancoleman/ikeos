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
    print("projects_cmd: not yet implemented")


def status_cmd(entries, project_filter, plain):
    print("status_cmd: not yet implemented")


def find_cmd(entries, filters, plain):
    print("find_cmd: not yet implemented")


def audit_cmd(vault, entries, project_filter, plain):
    print("audit_cmd: not yet implemented")


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
