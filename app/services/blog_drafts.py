import os
from pathlib import Path


def _posts_dir() -> Path:
    return Path(os.environ.get("AIOS_BLOG_POSTS_DIR", ""))


def latest_draft_paths() -> tuple[Path | None, Path | None]:
    """Return (draft_path, bluesky_path) for the latest weekly draft, or (None, None)."""
    posts = _posts_dir()
    if not posts.exists():
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


def read_draft_bundle() -> dict | None:
    """Return dict with filename, content, bluesky_text, bluesky_filename; or None if no draft."""
    draft, bluesky = latest_draft_paths()
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
    if bluesky and bluesky_text:
        bluesky.write_text(bluesky_text, encoding="utf-8")
    return draft.name
