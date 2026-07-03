import os
from pathlib import Path


def _review_dir() -> Path | None:
    d = os.environ.get("WEEKLY_REVIEW_OUTPUT_DIR", "")
    return Path(d) if d else None


def latest_review_name() -> str | None:
    review_dir = _review_dir()
    if not review_dir or not review_dir.exists():
        return None
    reviews = sorted(review_dir.glob("*-weekly-review.md"), reverse=True)
    return reviews[0].name if reviews else None


def read_latest_review() -> tuple[str, str] | None:
    """Return (filename, content) for the latest weekly review, or None."""
    review_dir = _review_dir()
    if not review_dir or not review_dir.exists():
        return None
    reviews_list = sorted(review_dir.glob("*-weekly-review.md"), reverse=True)
    if not reviews_list:
        return None
    latest = reviews_list[0]
    return latest.name, latest.read_text(encoding="utf-8")
