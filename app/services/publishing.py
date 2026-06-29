import logging
from datetime import date as _date
from pathlib import Path

import frontmatter
import requests

logger = logging.getLogger(__name__)


def _parse_date(d: str) -> _date:
    try:
        return _date.fromisoformat(d)
    except (ValueError, TypeError):
        return _date.min


def read_blog_posts(posts_dir: str | Path) -> list[dict]:
    """Read blog post markdown files from posts_dir, sorted newest-first.

    Excludes companion bluesky .txt files. Returns empty list if directory is missing.
    """
    posts_dir = Path(posts_dir)
    if not posts_dir.exists():
        return []

    posts = []
    for path in posts_dir.glob("*.md"):
        try:
            post = frontmatter.load(str(path))
        except Exception as e:
            logger.warning("Failed to parse %s: %s", path, e)
            continue
        slug = path.stem
        date_val = post.metadata.get("date")
        posts.append({
            "slug": slug,
            "filename": path.name,
            "title": post.metadata.get("title", slug),
            "date": str(date_val) if date_val else "",
            "draft": bool(post.metadata.get("draft", False)),
            "description": post.metadata.get("description", ""),
        })

    return sorted(posts, key=lambda p: _parse_date(p["date"]), reverse=True)


def read_bluesky_posts(handle: str, *, limit: int = 5) -> list[dict]:
    """Fetch recent posts for a Bluesky handle using the public API.

    Returns empty list on any error (network failure, API change, bad handle).
    """
    try:
        resp = requests.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",
            params={"actor": handle, "limit": limit},
            timeout=5,
        )
        if not resp.ok:
            return []
        feed = resp.json().get("feed", [])
        posts = []
        for item in feed:
            p = item.get("post", {})
            record = p.get("record", {})
            uri = p.get("uri", "")
            rkey = uri.split("/")[-1] if "/" in uri else ""
            url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else ""
            posts.append({
                "text": record.get("text", ""),
                "created_at": str(record.get("createdAt", "")),
                "likes": p.get("likeCount", 0),
                "reposts": p.get("repostCount", 0),
                "replies": p.get("replyCount", 0),
                "url": url,
            })
        return posts
    except Exception:
        logger.exception("Bluesky API request failed for handle %r", handle)
        return []
