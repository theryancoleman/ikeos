from pathlib import Path

import frontmatter


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
        except Exception:
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

    return sorted(posts, key=lambda p: p["date"], reverse=True)
