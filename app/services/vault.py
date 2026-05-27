import os
import re
from datetime import datetime
from pathlib import Path

import frontmatter

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))

VALID_TYPES = {"note", "idea", "bug"}
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs"}


def get_projects() -> list[str]:
    projects_dir = VAULT_PATH / "projects"
    if not projects_dir.exists():
        return []
    return sorted(d.name for d in projects_dir.iterdir() if d.is_dir())


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]


def write_entry(data: dict) -> str:
    entry_type = data["type"]
    project = data["project"]
    title = data["title"]
    body = data.get("body", "")

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = f"{date_str}-{_slugify(title)}"

    folder = TYPE_FOLDERS[entry_type]
    target_dir = VAULT_PATH / "projects" / project / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "type": entry_type,
        "title": title,
        "project": project,
        "status": "new",
        "created": datetime.now().isoformat(timespec="seconds"),
        "tags": [entry_type, project],
    }

    if entry_type == "idea":
        metadata["priority"] = data.get("priority", "medium")
        metadata["effort"] = data.get("effort", "medium")
    elif entry_type == "bug":
        metadata["severity"] = data.get("severity", "medium")

    content = f"## Description\n{body}\n"
    if entry_type == "bug" and data.get("steps"):
        content += f"\n## Steps to reproduce\n{data['steps']}\n"

    post = frontmatter.Post(content, **metadata)

    filepath = target_dir / f"{slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    return slug


def read_entries(project: str = None, status_filter: list = None) -> list[dict]:
    projects = [project] if project else get_projects()
    entries = []

    for proj in projects:
        proj_dir = VAULT_PATH / "projects" / proj
        for folder in ("bugs", "ideas", "notes"):
            type_dir = proj_dir / folder
            if not type_dir.exists():
                continue
            for filepath in type_dir.glob("*.md"):
                try:
                    post = frontmatter.load(filepath)
                    entry = dict(post.metadata)
                    if hasattr(entry.get("created"), "isoformat"):
                        entry["created"] = entry["created"].isoformat(timespec="seconds")
                    entry["body"] = post.content
                    entry["slug"] = filepath.stem
                    entries.append(entry)
                except Exception:
                    continue

    if status_filter:
        entries = [e for e in entries if e.get("status") in status_filter]

    entries.sort(key=lambda e: e.get("created", ""), reverse=True)
    return entries


def read_entry(project: str, slug: str) -> dict | None:
    proj_dir = VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes"):
        filepath = proj_dir / folder / f"{slug}.md"
        if filepath.exists():
            post = frontmatter.load(filepath)
            entry = dict(post.metadata)
            if hasattr(entry.get("created"), "isoformat"):
                entry["created"] = entry["created"].isoformat(timespec="seconds")
            entry["body"] = post.content
            entry["slug"] = slug
            return entry
    return None
