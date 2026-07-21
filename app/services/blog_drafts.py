import os
from pathlib import Path


def _posts_dir() -> Path | None:
    d = os.environ.get("AIOS_BLOG_POSTS_DIR", "")
    return Path(d) if d else None


def latest_draft_paths() -> tuple[Path | None, Path | None]:
    """Return (draft_path, bluesky_path) for the latest weekly draft, or (None, None)."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return None, None
    drafts = sorted(posts.glob("*-weekly-draft.md"), reverse=True)
    if not drafts:
        return None, None
    draft = drafts[0]
    bluesky = draft.with_name(draft.stem.replace("-weekly-draft", "-weekly-bluesky") + ".txt")
    return draft, bluesky if bluesky.exists() else None


def latest_draft_name() -> str | None:
    draft, _ = latest_draft_paths()
    return draft.name if draft else None


def draft_paths(filename: str) -> tuple[Path | None, Path | None]:
    """Return (draft_path, bluesky_path) for a specific draft filename."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return None, None
    if "/" in filename or "\\" in filename or ".." in filename:
        return None, None
    draft = posts / filename
    if not draft.exists() or not draft.name.endswith("-weekly-draft.md"):
        return None, None
    bluesky = draft.with_name(draft.stem.replace("-weekly-draft", "-weekly-bluesky") + ".txt")
    return draft, bluesky if bluesky.exists() else None


def read_draft_bundle(filename: str | None = None) -> dict | None:
    """Return dict with filename, content, bluesky_text, bluesky_filename for the given
    draft filename, or the latest draft if filename is omitted; None if not found."""
    draft, bluesky = draft_paths(filename) if filename else latest_draft_paths()
    if not draft:
        return None
    return {
        "filename": draft.name,
        "content": draft.read_text(encoding="utf-8"),
        "bluesky_text": bluesky.read_text(encoding="utf-8") if bluesky else "",
        "bluesky_filename": bluesky.name if bluesky else "",
    }


def save_draft(content: str, bluesky_text: str) -> str:
    """Write content and bluesky_text to the latest draft files. Returns filename.

    Raises FileNotFoundError if no draft exists.
    """
    draft, bluesky = latest_draft_paths()
    if not draft:
        raise FileNotFoundError("No draft file found")
    draft.write_text(content, encoding="utf-8")
    if bluesky:
        bluesky.write_text(bluesky_text, encoding="utf-8")
    return draft.name


def list_drafts() -> list[dict]:
    """All weekly drafts, newest first, each flagged with whether it's the current latest."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return []
    drafts = sorted(posts.glob("*-weekly-draft.md"), reverse=True)
    return [
        {"filename": draft.name, "generated_at": draft.name[:10], "is_latest": i == 0}
        for i, draft in enumerate(drafts)
    ]


def delete_draft(filename: str) -> bool:
    """Delete a draft (and its companion bluesky file, if present). Returns True if deleted."""
    posts = _posts_dir()
    if not posts or not posts.exists():
        return False
    if "/" in filename or "\\" in filename or ".." in filename:
        return False
    if not filename.endswith("-weekly-draft.md"):
        return False
    draft = posts / filename
    if not draft.exists():
        return False
    draft.unlink()
    bluesky = draft.with_name(draft.stem.replace("-weekly-draft", "-weekly-bluesky") + ".txt")
    if bluesky.exists():
        bluesky.unlink()
    return True
