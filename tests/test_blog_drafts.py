import pytest
from app.services import blog_drafts, reviews


@pytest.fixture
def posts_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AIOS_BLOG_POSTS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def review_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WEEKLY_REVIEW_OUTPUT_DIR", str(tmp_path))
    return tmp_path


def test_latest_draft_none_when_empty(posts_dir):
    assert blog_drafts.latest_draft_paths() == (None, None)
    assert blog_drafts.latest_draft_name() is None


def test_latest_draft_picks_newest_with_bluesky(posts_dir):
    (posts_dir / "2026-06-01-weekly-draft.md").write_text("old", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("new", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-bluesky.txt").write_text("sky", encoding="utf-8")
    draft, bluesky = blog_drafts.latest_draft_paths()
    assert draft.name == "2026-07-01-weekly-draft.md"
    assert bluesky.name == "2026-07-01-weekly-bluesky.txt"


def test_latest_draft_bluesky_none_when_missing(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("body", encoding="utf-8")
    draft, bluesky = blog_drafts.latest_draft_paths()
    assert draft.name == "2026-07-01-weekly-draft.md"
    assert bluesky is None


def test_latest_draft_name(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("body", encoding="utf-8")
    assert blog_drafts.latest_draft_name() == "2026-07-01-weekly-draft.md"


def test_read_draft_bundle(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("body", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-bluesky.txt").write_text("sky", encoding="utf-8")
    bundle = blog_drafts.read_draft_bundle()
    assert bundle["filename"] == "2026-07-01-weekly-draft.md"
    assert bundle["content"] == "body"
    assert bundle["bluesky_text"] == "sky"
    assert bundle["bluesky_filename"] == "2026-07-01-weekly-bluesky.txt"


def test_read_draft_bundle_none_when_no_draft(posts_dir):
    assert blog_drafts.read_draft_bundle() is None


def test_save_draft_writes_files(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("old body", encoding="utf-8")
    (posts_dir / "2026-07-01-weekly-bluesky.txt").write_text("old sky", encoding="utf-8")
    filename = blog_drafts.save_draft("new body", "new sky")
    assert filename == "2026-07-01-weekly-draft.md"
    assert (posts_dir / "2026-07-01-weekly-draft.md").read_text(encoding="utf-8") == "new body"
    assert (posts_dir / "2026-07-01-weekly-bluesky.txt").read_text(encoding="utf-8") == "new sky"


def test_save_draft_raises_when_no_draft(posts_dir):
    with pytest.raises(FileNotFoundError):
        blog_drafts.save_draft("content", "sky")


def test_latest_draft_none_when_dir_not_configured(monkeypatch):
    monkeypatch.delenv("AIOS_BLOG_POSTS_DIR", raising=False)
    assert blog_drafts.latest_draft_paths() == (None, None)
    assert blog_drafts.latest_draft_name() is None
    assert blog_drafts.read_draft_bundle() is None


def test_save_draft_works_without_bluesky_file(posts_dir):
    (posts_dir / "2026-07-01-weekly-draft.md").write_text("old body", encoding="utf-8")
    # no bluesky file
    filename = blog_drafts.save_draft("new body", "")
    assert filename == "2026-07-01-weekly-draft.md"
    assert (posts_dir / "2026-07-01-weekly-draft.md").read_text(encoding="utf-8") == "new body"


def test_latest_review_none_when_empty(review_dir):
    assert reviews.latest_review_name() is None


def test_latest_review_name(review_dir):
    (review_dir / "2026-07-01-weekly-review.md").write_text("r", encoding="utf-8")
    assert reviews.latest_review_name() == "2026-07-01-weekly-review.md"


def test_read_latest_review(review_dir):
    (review_dir / "2026-07-01-weekly-review.md").write_text("content", encoding="utf-8")
    name, content = reviews.read_latest_review()
    assert name == "2026-07-01-weekly-review.md"
    assert content == "content"


def test_read_latest_review_none_when_empty(review_dir):
    assert reviews.read_latest_review() is None


def test_reviews_returns_none_when_dir_not_configured(monkeypatch):
    monkeypatch.delenv("WEEKLY_REVIEW_OUTPUT_DIR", raising=False)
    assert reviews.latest_review_name() is None
    assert reviews.read_latest_review() is None
