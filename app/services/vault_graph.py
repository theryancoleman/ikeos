import logging
import re
import time
from datetime import datetime, timezone

import frontmatter

import app.services.vault_cache as _vc
from app.services.vault_entries import read_entries
from app.services.umbrella import get_umbrella_name

logger = logging.getLogger(__name__)

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
    now = time.monotonic()
    if _vc._hub_pages_cache is not None and (now - _vc._hub_pages_cache_ts) < _vc._TTL:
        return _vc._hub_pages_cache

    pages = []
    projects_dir = _vc.VAULT_PATH / "projects"
    if not projects_dir.exists():
        _vc._hub_pages_cache = pages
        _vc._hub_pages_cache_ts = now
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
    _vc._hub_pages_cache = pages
    _vc._hub_pages_cache_ts = now
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


def write_hub_page(umbrella_slug: str, umbrella_name: str, components: list[str]) -> None:
    """Create or overwrite the hub page for an umbrella project."""
    proj_dir = _vc.VAULT_PATH / "projects" / umbrella_slug
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
    _vc._invalidate_cache()


def write_component_stub(umbrella_slug: str, component_slug: str) -> None:
    """Create or overwrite a component stub page under an umbrella."""
    stubs_dir = _vc.VAULT_PATH / "projects" / umbrella_slug / "components"
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
    _vc._invalidate_cache()
