import pytest
from pathlib import Path
from app.services.publishing import read_blog_posts


@pytest.fixture
def posts_dir(tmp_path):
    (tmp_path / "2026-06-08-week-june-2.md").write_text(
        "---\ntitle: Week June 2\ndate: 2026-06-08\ndraft: false\ndescription: A summary\n---\nBody text here."
    )
    (tmp_path / "2026-06-15-week-june-11.md").write_text(
        "---\ntitle: Week June 11\ndate: 2026-06-15\ndraft: true\n---\nDraft body."
    )
    # Bluesky companion file — should be excluded
    (tmp_path / "2026-06-08-week-june-2-bluesky.txt").write_text("bluesky text")
    return tmp_path


def test_read_blog_posts_returns_posts_newest_first(posts_dir):
    posts = read_blog_posts(posts_dir)
    assert len(posts) == 2
    assert posts[0]["date"] == "2026-06-15"
    assert posts[1]["date"] == "2026-06-08"


def test_read_blog_posts_includes_title_and_draft_status(posts_dir):
    posts = read_blog_posts(posts_dir)
    newest = posts[0]
    assert newest["title"] == "Week June 11"
    assert newest["draft"] is True
    assert newest["slug"] == "2026-06-15-week-june-11"


def test_read_blog_posts_includes_description(posts_dir):
    posts = read_blog_posts(posts_dir)
    oldest = posts[1]
    assert oldest["description"] == "A summary"


def test_read_blog_posts_excludes_bluesky_companion_files(posts_dir):
    posts = read_blog_posts(posts_dir)
    slugs = [p["slug"] for p in posts]
    assert not any("bluesky" in s for s in slugs)


def test_read_blog_posts_returns_empty_for_missing_dir():
    posts = read_blog_posts(Path("/nonexistent/path"))
    assert posts == []


from unittest.mock import MagicMock, patch
from app.services.publishing import read_bluesky_posts


def test_read_bluesky_posts_returns_formatted_posts(mocker):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "feed": [
            {
                "post": {
                    "uri": "at://did:plc:abc/app.bsky.feed.post/xyz123",
                    "record": {
                        "text": "Hello from IkeOS!",
                        "createdAt": "2026-06-28T12:00:00Z",
                    },
                    "likeCount": 5,
                    "repostCount": 2,
                    "replyCount": 1,
                }
            }
        ]
    }
    mocker.patch("app.services.publishing.requests.get", return_value=mock_resp)

    posts = read_bluesky_posts("ikeos.bsky.social", limit=5)
    assert len(posts) == 1
    assert posts[0]["text"] == "Hello from IkeOS!"
    assert posts[0]["likes"] == 5
    assert posts[0]["reposts"] == 2
    assert posts[0]["replies"] == 1
    assert "ikeos.bsky.social" in posts[0]["url"]
    assert "xyz123" in posts[0]["url"]


def test_read_bluesky_posts_returns_empty_on_error(mocker):
    mocker.patch("app.services.publishing.requests.get",
                 side_effect=Exception("network error"))
    posts = read_bluesky_posts("ikeos.bsky.social")
    assert posts == []


def test_read_bluesky_posts_returns_empty_on_non_ok_response(mocker):
    mock_resp = MagicMock()
    mock_resp.ok = False
    mocker.patch("app.services.publishing.requests.get", return_value=mock_resp)
    posts = read_bluesky_posts("ikeos.bsky.social")
    assert posts == []
