import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)

from app.services.umbrella import get_umbrella_name

# ── In-process cache ────────────────────────────────────────────────────────
# The vault lives on a Windows bind mount; cross-filesystem I/O in WSL2 is
# slow (~20× vs native Linux). Cache the two hot reads and invalidate on write.

_TTL = 600.0  # 10 minutes; vault changes are rare and writes invalidate immediately

_projects_cache: list | None = None
_projects_cache_ts: float = 0.0

_entries_cache: list | None = None
_entries_cache_ts: float = 0.0

_hub_pages_cache: list | None = None
_hub_pages_cache_ts: float = 0.0


def _invalidate_cache() -> None:
    global _projects_cache, _projects_cache_ts, _entries_cache, _entries_cache_ts
    global _hub_pages_cache, _hub_pages_cache_ts
    _projects_cache = None
    _projects_cache_ts = 0.0
    _entries_cache = None
    _entries_cache_ts = 0.0
    _hub_pages_cache = None
    _hub_pages_cache_ts = 0.0

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))

VALID_TYPES = {"note", "idea", "bug", "decision", "grill-me", "housekeeping-task", "housekeeping-heartbeat"}
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs", "grill-me": "grill-me"}
TYPE_TAGS = {"note": "documentation", "idea": "enhancement", "bug": "bug", "decision": "decision", "grill-me": "grill-me"}


def _read_project_meta(slug: str) -> dict:
    meta_file = VAULT_PATH / "projects" / slug / "project.md"
    if not meta_file.exists():
        return {"name": slug, "description": "", "hidden": False}
    try:
        post = frontmatter.load(meta_file)
        return {
            "name": post.metadata.get("name", slug),
            "description": post.metadata.get("description", ""),
            "hidden": bool(post.metadata.get("hidden", False)),
        }
    except Exception:
        return {"name": slug, "description": "", "hidden": False}


def get_projects() -> list[str]:
    projects_dir = VAULT_PATH / "projects"
    if not projects_dir.exists():
        return []
    return sorted(d.name for d in projects_dir.iterdir() if d.is_dir())


def get_projects_with_meta(include_hidden: bool = False) -> list[dict]:
    global _projects_cache, _projects_cache_ts
    now = time.monotonic()
    if _projects_cache is not None and (now - _projects_cache_ts) < _TTL:
        cached = _projects_cache
    else:
        projects_dir = VAULT_PATH / "projects"
        if not projects_dir.exists():
            return []
        cached = []
        for d in sorted(projects_dir.iterdir()):
            if not d.is_dir():
                continue
            meta = _read_project_meta(d.name)
            cached.append({
                "slug": d.name,
                "name": meta["name"],
                "description": meta["description"],
                "hidden": meta["hidden"],
            })
        _projects_cache = cached
        _projects_cache_ts = now
    if include_hidden:
        return list(cached)
    return [p for p in cached if not p["hidden"]]


def write_project_meta(slug: str, name: str, description: str, hidden: bool) -> bool:
    """Write or overwrite project.md for the given slug."""
    proj_dir = VAULT_PATH / "projects" / slug
    if not proj_dir.exists():
        return False
    meta_file = proj_dir / "project.md"
    post = frontmatter.Post("", name=name, description=description, hidden=hidden)
    with open(meta_file, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()
    return True


_WIKILINK_RE = re.compile(r'\[\[([^\]|]+)')
_STALE_DAYS = 30


def _get_urgency(entry: dict) -> str:
    """Extract urgency level from tags, falling back to severity/priority fields."""
    for tag in entry.get("tags", []):
        if tag.startswith("urgency/"):
            return tag.split("/", 1)[1]
    sev = entry.get("severity") or entry.get("priority")
    if sev in ("critical", "high", "medium", "low"):
        return sev
    return "medium"


def _read_hub_pages() -> list[dict]:
    """Read hub pages and component stubs (<proj>/components/*.md).
    Hub pages are discovered by type:hub frontmatter (filename = display name)."""
    global _hub_pages_cache, _hub_pages_cache_ts
    now = time.monotonic()
    if _hub_pages_cache is not None and (now - _hub_pages_cache_ts) < _TTL:
        return _hub_pages_cache

    pages = []
    projects_dir = VAULT_PATH / "projects"
    if not projects_dir.exists():
        _hub_pages_cache = pages
        _hub_pages_cache_ts = now
        return pages
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        # Hub page — scan top-level .md files for type:hub (file is named after display name)
        for candidate in proj_dir.glob("*.md"):
            if candidate.name == "project.md":
                continue
            try:
                post = frontmatter.load(candidate)
                if post.metadata.get("type") == "hub":
                    entry = dict(post.metadata)
                    entry["body"] = post.content
                    entry["slug"] = candidate.stem  # e.g. "IkeOS", "Music Tools"
                    pages.append(entry)
                    break
            except Exception as e:
                logger.warning("Failed to parse hub page %s: %s", candidate, e)
        # Component stubs
        stubs_dir = proj_dir / "components"
        if stubs_dir.exists():
            for stub_file in stubs_dir.glob("*.md"):
                try:
                    post = frontmatter.load(stub_file)
                    entry = dict(post.metadata)
                    entry["body"] = post.content
                    entry["slug"] = stub_file.stem
                    pages.append(entry)
                except Exception as e:
                    logger.warning("Failed to parse component stub %s: %s", stub_file, e)
    _hub_pages_cache = pages
    _hub_pages_cache_ts = now
    return pages


def get_vault_graph() -> dict:
    """Return nodes, wikilink edges, and health metrics for all project entries (bugs, ideas, notes) plus hub/component pages."""
    entries = read_entries()
    hub_pages = _read_hub_pages()
    all_items = entries + hub_pages
    slug_set = {e["slug"] for e in all_items}

    nodes = []
    links = []
    untriaged = []
    stale = []
    broken_links = []

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for entry in all_items:
        slug = entry["slug"]

        nodes.append({
            "id": slug,
            "title": entry.get("title", slug),
            "type": entry.get("type", "note"),
            "status": entry.get("status", ""),
            "project": entry.get("project", ""),
            "urgency": _get_urgency(entry),
        })

        # Health checks apply only to non-hub entries
        if entry.get("type") not in ("hub", "component"):
            if entry.get("status") == "new":
                untriaged.append({
                    "slug": slug,
                    "title": entry.get("title", slug),
                    "project": entry.get("project", ""),
                    "type": entry.get("type", "note"),
                })
            if entry.get("status") in ("open", "in-progress"):
                ref_date_raw = entry.get("updated") or entry.get("created", "")
                try:
                    if isinstance(ref_date_raw, datetime):
                        ref_date = ref_date_raw
                    else:
                        ref_date = datetime.fromisoformat(ref_date_raw)
                    ref_date = ref_date.replace(tzinfo=None) if ref_date.tzinfo else ref_date
                    days_stale = (now - ref_date).days
                    if days_stale >= _STALE_DAYS:
                        stale.append({
                            "slug": slug,
                            "title": entry.get("title", slug),
                            "project": entry.get("project", ""),
                            "type": entry.get("type", "note"),
                            "status": entry.get("status", ""),
                            "days_stale": days_stale,
                        })
                except (ValueError, TypeError):
                    pass

        body = entry.get("body", "")
        for ref in _WIKILINK_RE.findall(body):
            ref = ref.strip()
            if not ref or ref == slug:
                continue
            if ref in slug_set:
                links.append({"source": slug, "target": ref})
            else:
                broken_links.append({
                    "source_slug": slug,
                    "source_title": entry.get("title", slug),
                    "source_project": entry.get("project", ""),
                    "broken_ref": ref,
                })

    return {
        "nodes": nodes,
        "links": links,
        "health": {
            "untriaged": untriaged,
            "stale": stale,
            "broken_links": broken_links,
        },
    }


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50]


def write_hub_page(umbrella_slug: str, umbrella_name: str, components: list[str]) -> None:
    """Create or overwrite the hub page for an umbrella project."""
    proj_dir = VAULT_PATH / "projects" / umbrella_slug
    proj_dir.mkdir(parents=True, exist_ok=True)

    component_links = " · ".join(f"[[{c}]]" for c in components) if components else ""
    content = f"# {umbrella_name}\n\n"
    if component_links:
        content += f"**Components:** {component_links}\n\n"

    metadata = {
        "type": "hub",
        "title": umbrella_name,
        "project": umbrella_slug,
        "tags": ["hub", f"project/{umbrella_slug}"],
    }
    post = frontmatter.Post(content, **metadata)
    filepath = proj_dir / f"{umbrella_name}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()


def write_component_stub(umbrella_slug: str, component_slug: str) -> None:
    """Create or overwrite a component stub page under an umbrella."""
    stubs_dir = VAULT_PATH / "projects" / umbrella_slug / "components"
    stubs_dir.mkdir(parents=True, exist_ok=True)

    content = f"# {component_slug}\n\n[[{get_umbrella_name(umbrella_slug)}]]\n"
    metadata = {
        "type": "component",
        "title": component_slug,
        "project": umbrella_slug,
        "tags": ["component", f"umbrella/{umbrella_slug}"],
    }
    post = frontmatter.Post(content, **metadata)
    filepath = stubs_dir / f"{component_slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()


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
    elif entry_type == "housekeeping-task":
        project = data.get("project", "")
        target_dir = VAULT_PATH / "projects" / project / "housekeeping"
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
        _invalidate_cache()
        return slug
    elif entry_type == "housekeeping-heartbeat":
        project = data.get("project", "")
        target_dir = VAULT_PATH / "projects" / project / "housekeeping"
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
        _invalidate_cache()
        return "last-run"
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
        component = data.get("component", "").strip()
        if component:
            tags.append(f"component/{component}")

        metadata = {
            "type": entry_type,
            "title": title,
            "project": project,
            "status": "new",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": tags,
        }
        if component:
            metadata["component"] = component

        if entry_type == "idea":
            metadata["priority"] = data.get("priority", "medium")
            metadata["effort"] = data.get("effort", "medium")
        elif entry_type == "bug":
            metadata["severity"] = data.get("severity", "medium")

        content = f"## Description\n{body}\n"
        if entry_type == "bug" and data.get("steps"):
            content += f"\n## Steps to reproduce\n{data['steps']}\n"
        if component:
            content += f"\n---\n[[{get_umbrella_name(project)}]]\n"

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
        for folder in set(TYPE_FOLDERS.values()):
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


def read_entries(project: str = None, status_filter: list = None, component: str = None) -> list[dict]:
    global _entries_cache, _entries_cache_ts
    now = time.monotonic()

    if _entries_cache is None or (now - _entries_cache_ts) >= _TTL:
        _entries_cache = _read_all_entries()
        _entries_cache_ts = now

    entries = _entries_cache
    if project is not None:
        entries = [e for e in entries if e.get("project") == project]
    if component is not None:
        entries = [e for e in entries if e.get("component") == component]
    if status_filter:
        entries = [e for e in entries if e.get("status") in status_filter]

    return entries


def read_entry(project: str, slug: str) -> dict | None:
    proj_dir = VAULT_PATH / "projects" / project
    for folder in ("bugs", "ideas", "notes", "grill-me"):
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
    for folder in ("bugs", "ideas", "notes", "grill-me"):
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


_HOUSEKEEPING_ALLOWED_FIELDS: dict[str, set[str]] = {
    "housekeeping-task": {"enabled", "last_run", "last_error", "consecutive_failures"},
    "housekeeping-heartbeat": {"last_run", "tasks_run", "tasks_failed", "tasks_skipped"},
}


def update_housekeeping_fields(
    entry_type: str,
    project: str,
    filename: str,
    fields: dict,
) -> bool:
    """Overwrite allowed runtime fields on a housekeeping vault entry."""
    allowed = _HOUSEKEEPING_ALLOWED_FIELDS.get(entry_type)
    if allowed is None:
        return False

    if ".." in filename or "/" in filename or "\\" in filename:
        return False

    if ".." in project or "/" in project or "\\" in project:
        return False

    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    fname = filename if filename.endswith(".md") else f"{filename}.md"
    filepath = VAULT_PATH / "projects" / project / "housekeeping" / fname
    if not filepath.exists():
        return False

    temp_filepath = filepath.with_suffix(".tmp")
    try:
        post = frontmatter.load(filepath)
        for k, v in updates.items():
            post.metadata[k] = v
        with open(temp_filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        temp_filepath.replace(filepath)
        _invalidate_cache()
        return True
    except Exception:
        logger.exception(
            "Failed to update housekeeping fields for %s/%s/%s",
            entry_type, project, filename,
        )
        temp_filepath.unlink(missing_ok=True)
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
        elif entry_type == "grill-me":
            base_path = VAULT_PATH / "projects" / project / "grill-me"
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


# ── Housekeeping read ─────────────────────────────────────────────────────────

_INTERVAL_THRESHOLDS: dict[str, int] = {
    "weekly": 6,
    "monthly": 27,
    "quarterly": 83,
    "annually": 364,
}


def _compute_task_status(task: dict) -> str:
    if task.get("enabled") != "true":
        return "disabled"
    if task.get("consecutive_failures", "0") != "0":
        return "error"
    last_run = task.get("last_run", "null")
    if last_run == "null" or last_run is None:
        return "due" if task.get("interval") == "weekly" else "uninitialized"
    threshold = _INTERVAL_THRESHOLDS.get(task.get("interval", "weekly"), 6)
    try:
        last_run_dt = datetime.fromisoformat(last_run) if isinstance(last_run, str) else last_run
        days_since = (datetime.now() - last_run_dt.replace(tzinfo=None)).days
        if days_since >= threshold + 3:
            return "overdue"
        if days_since >= threshold:
            return "due"
        return "ok"
    except (ValueError, TypeError):
        return "unknown"


def _compute_next_run(task: dict) -> str | None:
    last_run = task.get("last_run", "null")
    if last_run == "null" or last_run is None:
        return None
    threshold = _INTERVAL_THRESHOLDS.get(task.get("interval", "weekly"), 6)
    try:
        last_run_dt = datetime.fromisoformat(last_run) if isinstance(last_run, str) else last_run
        return (last_run_dt.replace(tzinfo=None) + timedelta(days=threshold)).date().isoformat()
    except (ValueError, TypeError):
        return None


def read_housekeeping_tasks(project: str) -> list[dict]:
    """Read all housekeeping-task entries. Uncached — state changes frequently."""
    folder = VAULT_PATH / "projects" / project / "housekeeping"
    if not folder.exists():
        return []
    tasks = []
    for filepath in sorted(folder.glob("*.md")):
        if filepath.name == "last-run.md":
            continue
        try:
            post = frontmatter.load(filepath)
            if post.metadata.get("type") != "housekeeping-task":
                continue
            task = dict(post.metadata)
            task["filename"] = filepath.stem
            task["status"] = _compute_task_status(task)
            task["next_run"] = _compute_next_run(task)
            tasks.append(task)
        except Exception:
            continue
    return tasks


def read_housekeeping_heartbeat(project: str) -> dict:
    """Read the housekeeping heartbeat singleton. Returns safe defaults if missing."""
    _safe: dict = {
        "last_run": None,
        "tasks_run": "0",
        "tasks_failed": "0",
        "tasks_skipped": "0",
    }
    filepath = VAULT_PATH / "projects" / project / "housekeeping" / "last-run.md"
    if not filepath.exists():
        return _safe.copy()
    try:
        post = frontmatter.load(filepath)
        data = dict(post.metadata)
        if data.get("last_run") in ("null", None, ""):
            data["last_run"] = None
        return {**_safe, **data}
    except Exception:
        return _safe.copy()
