import os
import re
import time
from datetime import datetime
from pathlib import Path

import frontmatter

# ── In-process cache ────────────────────────────────────────────────────────
# The vault lives on a Windows bind mount; cross-filesystem I/O in WSL2 is
# slow (~20× vs native Linux). Cache the two hot reads and invalidate on write.

_TTL = 60.0  # seconds

_projects_cache: list | None = None
_projects_cache_ts: float = 0.0

_entries_cache: list | None = None
_entries_cache_ts: float = 0.0


def _invalidate_cache() -> None:
    global _projects_cache, _projects_cache_ts, _entries_cache, _entries_cache_ts
    _projects_cache = None
    _projects_cache_ts = 0.0
    _entries_cache = None
    _entries_cache_ts = 0.0

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))

VALID_TYPES = {"note", "idea", "bug", "decision"}
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs"}
TYPE_TAGS = {"note": "documentation", "idea": "enhancement", "bug": "bug", "decision": "decision"}


def _read_project_meta(slug: str) -> dict:
    meta_file = VAULT_PATH / "projects" / slug / "project.md"
    if not meta_file.exists():
        return {"name": slug, "hidden": False}
    try:
        post = frontmatter.load(meta_file)
        return {
            "name": post.metadata.get("name", slug),
            "hidden": bool(post.metadata.get("hidden", False)),
        }
    except Exception:
        return {"name": slug, "hidden": False}


def get_projects() -> list[str]:
    projects_dir = VAULT_PATH / "projects"
    if not projects_dir.exists():
        return []
    return sorted(d.name for d in projects_dir.iterdir() if d.is_dir())


def get_projects_with_meta() -> list[dict]:
    global _projects_cache, _projects_cache_ts
    now = time.monotonic()
    if _projects_cache is not None and (now - _projects_cache_ts) < _TTL:
        return _projects_cache
    projects_dir = VAULT_PATH / "projects"
    if not projects_dir.exists():
        return []
    projects = []
    for d in sorted(projects_dir.iterdir()):
        if not d.is_dir():
            continue
        meta = _read_project_meta(d.name)
        if not meta["hidden"]:
            projects.append({"slug": d.name, "name": meta["name"]})
    _projects_cache = projects
    _projects_cache_ts = now
    return projects


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]


def write_entry(data: dict) -> str:
    entry_type = data["type"]
    project = data.get("project", "")
    title = data["title"]
    body = data.get("body", "")

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = f"{date_str}-{_slugify(title)}"

    if entry_type == "decision":
        target_dir = VAULT_PATH / "decisions"
        target_dir.mkdir(parents=True, exist_ok=True)
        tags = ["decision", "status/proposed"]
        if project:
            tags.append(project)
        metadata = {
            "type": "decision",
            "title": title,
            "status": "proposed",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": tags,
        }
        if project:
            metadata["project"] = project
        content = f"## Context\n\n{body}\n\n## Decision\n\n\n## Consequences\n\n"
    else:
        folder = TYPE_FOLDERS[entry_type]
        target_dir = VAULT_PATH / "projects" / project / folder
        target_dir.mkdir(parents=True, exist_ok=True)

        type_tag = TYPE_TAGS[entry_type]
        tags = [type_tag, project, "status/new"]
        if entry_type == "idea":
            tags.append(f"urgency/{data.get('priority', 'medium')}")
        elif entry_type == "bug":
            urgency = "critical" if data.get("severity") == "critical" else data.get("severity", "medium")
            tags.append(f"urgency/{urgency}")
        for domain in data.get("domains", []):
            tags.append(f"domain/{domain}")

        metadata = {
            "type": entry_type,
            "title": title,
            "project": project,
            "status": "new",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": tags,
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

    _invalidate_cache()
    return slug


def _read_all_entries() -> list[dict]:
    """Read and parse every entry file in the vault. Result is cached by callers."""
    entries = []
    for proj in get_projects():
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
    entries.sort(key=lambda e: e.get("created", ""), reverse=True)
    return entries


def read_entries(project: str = None, status_filter: list = None) -> list[dict]:
    global _entries_cache, _entries_cache_ts
    now = time.monotonic()

    if project is None:
        # Hot path: full scan — serve from cache when fresh
        if _entries_cache is None or (now - _entries_cache_ts) >= _TTL:
            _entries_cache = _read_all_entries()
            _entries_cache_ts = now
        entries = _entries_cache
    else:
        # Per-project reads are cheaper; don't cache separately
        proj_dir = VAULT_PATH / "projects" / project
        entries = []
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
        entries.sort(key=lambda e: e.get("created", ""), reverse=True)

    if status_filter:
        entries = [e for e in entries if e.get("status") in status_filter]

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


def update_entry_status(project: str, slug: str, new_status: str) -> bool:
    if new_status not in VALID_STATUSES:
        return False
    proj_dir = VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes"):
        filepath = proj_dir / folder / f"{slug}.md"
        if filepath.exists():
            post = frontmatter.load(filepath)
            post.metadata["status"] = new_status
            post.metadata["updated"] = datetime.now().isoformat(timespec="seconds")
            tags = [t for t in post.metadata.get("tags", []) if not t.startswith("status/")]
            tags.append(f"status/{new_status}")
            post.metadata["tags"] = tags
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
            _invalidate_cache()
            return True
    return False


def update_entry_status_generic(entry_type: str, project: str | None, filename: str, new_status: str) -> bool:
    """Update status for any entry type (task or decision), with byte-identical body preservation."""
    # Validate status based on type
    if entry_type == "decision":
        if new_status not in DECISION_STATUSES:
            return False
        base_path = VAULT_PATH / "decisions"
    else:
        if new_status not in VALID_STATUSES:
            return False
        if not project:
            return False
        if entry_type == "bug":
            base_path = VAULT_PATH / "projects" / project / "bugs"
        elif entry_type == "idea":
            base_path = VAULT_PATH / "projects" / project / "ideas"
        elif entry_type == "note":
            base_path = VAULT_PATH / "projects" / project / "notes"
        else:
            return False

    if filename.endswith(".md"):
        filepath = base_path / filename
    else:
        filepath = base_path / f"{filename}.md"

    if not filepath.exists():
        return False

    try:
        post = frontmatter.load(filepath)
        post.metadata["status"] = new_status
        post.metadata["updated"] = datetime.now().isoformat(timespec="seconds")

        tags = [t for t in post.metadata.get("tags", []) if not t.startswith("status/") and not t.startswith("decision/")]
        tags.append(f"status/{new_status}")
        post.metadata["tags"] = tags

        # Write to temp file first, then rename for atomicity
        temp_filepath = filepath.with_suffix(".md.tmp")
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        temp_filepath.replace(filepath)

        _invalidate_cache()
        return True
    except Exception:
        return False
