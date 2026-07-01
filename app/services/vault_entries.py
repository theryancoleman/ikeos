import logging
import re
import time
from datetime import datetime

import frontmatter

import app.services.vault_cache as _vc
from app.services.vault_projects import get_projects
from app.services.umbrella import get_umbrella_name

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]


def write_entry(data: dict) -> str:
    entry_type = data["type"]
    project = data.get("project", "").lower().strip()
    title = data["title"]
    body = data.get("body", "")

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = f"{date_str}-{_slugify(title)}"

    if entry_type == "decision":
        target_dir = _vc.VAULT_PATH / "decisions"
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
    elif entry_type == "housekeeping-task":
        target_dir = _vc.VAULT_PATH / "projects" / project / "housekeeping"
        target_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "title": title,
            "type": "housekeeping-task",
            "project": project,
            "interval": data.get("interval", "weekly"),
            "enabled": "true",
            "success_definition": data.get("success_definition", ""),
            "last_run": "null",
            "last_error": "null",
            "consecutive_failures": "0",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": ["housekeeping-task", project, "status/enabled"],
        }
        content = f"## Instructions\n{body}\n"
        post = frontmatter.Post(content, **metadata)
        filepath = target_dir / f"{slug}.md"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        _vc._invalidate_cache()
        return slug
    elif entry_type == "housekeeping-heartbeat":
        target_dir = _vc.VAULT_PATH / "projects" / project / "housekeeping"
        target_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "title": "Housekeeping Last Run",
            "type": "housekeeping-heartbeat",
            "project": project,
            "last_run": "null",
            "tasks_run": "0",
            "tasks_failed": "0",
            "tasks_skipped": "0",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": ["housekeeping-heartbeat", project],
        }
        post = frontmatter.Post("", **metadata)
        filepath = target_dir / "last-run.md"  # singleton — fixed name, no date prefix
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        _vc._invalidate_cache()
        return "last-run"
    else:
        folder = _vc.TYPE_FOLDERS[entry_type]
        target_dir = _vc.VAULT_PATH / "projects" / project / folder
        target_dir.mkdir(parents=True, exist_ok=True)

        type_tag = _vc.TYPE_TAGS[entry_type]
        initial_status = _vc.ENTRY_TYPE_CONFIG[entry_type]["initial_status"]
        tags = [type_tag, project, f"status/{initial_status}"]
        if entry_type == "idea":
            tags.append(f"urgency/{data.get('priority', 'medium')}")
        elif entry_type == "bug":
            urgency = "critical" if data.get("severity") == "critical" else data.get("severity", "medium")
            tags.append(f"urgency/{urgency}")
        for domain in data.get("domains", []):
            tags.append(f"domain/{domain}")
        component = data.get("component", "").strip()
        if component:
            tags.append(f"component/{component}")

        metadata = {
            "type": entry_type,
            "title": title,
            "project": project,
            "status": initial_status,
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": tags,
        }
        if component:
            metadata["component"] = component
        description = data.get("description", "").strip()
        if description:
            metadata["description"] = description

        if entry_type == "idea":
            metadata["priority"] = data.get("priority", "medium")
            metadata["effort"] = data.get("effort", "medium")
            why = data.get("why", "").strip()
            if why:
                metadata["why"] = why
        elif entry_type == "bug":
            metadata["severity"] = data.get("severity", "medium")
        elif entry_type == "experiment":
            metadata["hypothesis"] = data.get("hypothesis", "")
            metadata["expected_outcome"] = data.get("expected_outcome", "")
            metadata["measurement"] = data.get("measurement", "")
            metadata["success_criteria"] = data.get("success_criteria", "")
            metadata["timebox"] = data.get("timebox", "")
            metadata["result"] = ""
            metadata["decision"] = ""

        content = f"## Description\n{body}\n"
        if entry_type == "bug" and data.get("steps"):
            content += f"\n## Steps to reproduce\n{data['steps']}\n"
        if component:
            content += f"\n---\n[[{get_umbrella_name(project)}]]\n"

    post = frontmatter.Post(content, **metadata)

    filepath = target_dir / f"{slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    _vc._invalidate_cache()
    return slug


def _read_all_entries() -> list[dict]:
    """Read and parse every entry file in the vault. Result is cached by callers."""
    entries = []
    for proj in get_projects():
        proj_dir = _vc.VAULT_PATH / "projects" / proj
        for cfg in _vc.ENTRY_TYPE_CONFIG.values():
            type_dir = proj_dir / cfg["folder"]
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


def read_entries(project: str = None, status_filter: list = None, component: str = None) -> list[dict]:
    now = time.monotonic()

    if _vc._entries_cache is None or (now - _vc._entries_cache_ts) >= _vc._TTL:
        _vc._entries_cache = _read_all_entries()
        _vc._entries_cache_ts = now

    entries = _vc._entries_cache
    if project is not None:
        entries = [e for e in entries if e.get("project") == project]
    if component is not None:
        entries = [e for e in entries if e.get("component") == component]
    if status_filter:
        entries = [e for e in entries if e.get("status") in status_filter]

    return entries


def read_entry(project: str, slug: str) -> dict | None:
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for cfg in _vc.ENTRY_TYPE_CONFIG.values():
        filepath = proj_dir / cfg["folder"] / f"{slug}.md"
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
    proj_dir = _vc.VAULT_PATH / "projects" / project
    for cfg in _vc.ENTRY_TYPE_CONFIG.values():
        filepath = proj_dir / cfg["folder"] / f"{slug}.md"
        if filepath.exists():
            if new_status not in cfg["valid_statuses"]:
                return False
            post = frontmatter.load(filepath)
            post.metadata["status"] = new_status
            post.metadata["updated"] = datetime.now().isoformat(timespec="seconds")
            tags = [t for t in post.metadata.get("tags", []) if not t.startswith("status/")]
            tags.append(f"status/{new_status}")
            post.metadata["tags"] = tags
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
            _vc._invalidate_cache()
            return True
    return False


def update_entry_status_generic(entry_type: str, project: str | None, filename: str, new_status: str) -> bool:
    """Update status for any entry type (task or decision), with byte-identical body preservation."""
    # Validate status based on type
    if entry_type == "decision":
        if new_status not in _vc.DECISION_STATUSES:
            return False
        base_path = _vc.VAULT_PATH / "decisions"
    elif entry_type in _vc.ENTRY_TYPE_CONFIG:
        cfg = _vc.ENTRY_TYPE_CONFIG[entry_type]
        if new_status not in cfg["valid_statuses"]:
            return False
        if not project:
            return False
        base_path = _vc.VAULT_PATH / "projects" / project / cfg["folder"]
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

        _vc._invalidate_cache()
        return True
    except Exception:
        return False


# Alias for test compatibility
_invalidate_cache = _vc._invalidate_cache
