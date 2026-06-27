import time

import frontmatter

import app.services.vault_cache as _vc


def _read_project_meta(slug: str) -> dict:
    """Read project metadata from project.md or return defaults."""
    meta_file = _vc.VAULT_PATH / "projects" / slug / "project.md"
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
    """Return sorted list of project slugs (directory names)."""
    projects_dir = _vc.VAULT_PATH / "projects"
    if not projects_dir.exists():
        return []
    return sorted(d.name for d in projects_dir.iterdir() if d.is_dir())


def get_projects_with_meta(include_hidden: bool = False) -> list[dict]:
    """Return list of projects with metadata, optionally including hidden ones.

    Each project dict contains: slug, name, description, hidden.
    Results are cached for 10 minutes.
    """
    now = time.monotonic()
    if _vc._projects_cache is not None and (now - _vc._projects_cache_ts) < _vc._TTL:
        cached = _vc._projects_cache
    else:
        projects_dir = _vc.VAULT_PATH / "projects"
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
        _vc._projects_cache = cached
        _vc._projects_cache_ts = now
    if include_hidden:
        return list(cached)
    return [p for p in cached if not p["hidden"]]


def write_project_meta(slug: str, name: str, description: str, hidden: bool) -> bool:
    """Write or overwrite project.md for the given slug.

    Returns True if successful, False if project directory doesn't exist.
    Invalidates cache on success.
    """
    proj_dir = _vc.VAULT_PATH / "projects" / slug
    if not proj_dir.exists():
        return False
    meta_file = proj_dir / "project.md"
    post = frontmatter.Post("", name=name, description=description, hidden=hidden)
    with open(meta_file, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _vc._invalidate_cache()
    return True
