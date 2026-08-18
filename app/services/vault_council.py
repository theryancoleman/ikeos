"""Council vault functions — read/write council-item runtime fields."""

import logging

import frontmatter

import app.services.vault_cache as _vc

logger = logging.getLogger(__name__)

_COUNCIL_ALLOWED_FIELDS: set[str] = {
    "match_slug", "weeks_open", "discussion_session_id", "decision_ref", "source", "source_review",
}


def update_council_fields(project: str, filename: str, fields: dict) -> bool:
    """Overwrite allowed runtime fields on a council-item vault entry."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    if ".." in project or "/" in project or "\\" in project:
        return False

    updates = {k: v for k, v in fields.items() if k in _COUNCIL_ALLOWED_FIELDS}
    if not updates:
        return False

    fname = filename if filename.endswith(".md") else f"{filename}.md"
    filepath = _vc.VAULT_PATH / "projects" / project / "council" / fname
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
        _vc._invalidate_cache()
        return True
    except Exception:
        logger.exception("Failed to update council fields for %s/%s", project, filename)
        temp_filepath.unlink(missing_ok=True)
        return False
