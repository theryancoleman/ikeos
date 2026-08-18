import pytest
from unittest.mock import patch
import frontmatter as fm
import app.services.vault_cache as _vc


@pytest.fixture(autouse=True)
def reset_cache():
    _vc._invalidate_cache()
    yield
    _vc._invalidate_cache()


def _write_council_item(tmp_path, project="myproj", slug="2026-08-18-test-item"):
    d = tmp_path / "projects" / project / "council"
    d.mkdir(parents=True)
    entry = fm.Post(
        "## Description\nbody\n",
        type="council-item", title="Test item", project=project,
        status="pending-review", created="2026-08-18T00:00:00",
        tags=["council", project, "status/pending-review"],
        match_slug="test-item", source="narrative-review", source_review="",
        weeks_open="1", discussion_session_id="", decision_ref="",
    )
    (d / f"{slug}.md").write_text(fm.dumps(entry))
    return d / f"{slug}.md"


def test_update_council_fields_bumps_weeks_open(tmp_path):
    filepath = _write_council_item(tmp_path)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "2026-08-18-test-item", {"weeks_open": "2"})
    assert result is True
    post = fm.load(filepath)
    assert post.metadata["weeks_open"] == "2"


def test_update_council_fields_sets_decision_ref(tmp_path):
    filepath = _write_council_item(tmp_path)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "2026-08-18-test-item", {"decision_ref": "2026-08-25-recover-weak-signals-decision"})
    assert result is True
    post = fm.load(filepath)
    assert post.metadata["decision_ref"] == "2026-08-25-recover-weak-signals-decision"


def test_update_council_fields_accepts_source_and_source_review(tmp_path):
    filepath = _write_council_item(tmp_path)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields(
            "myproj", "2026-08-18-test-item",
            {"source": "narrative-review", "source_review": "2026-08-25-review"},
        )
    assert result is True
    post = fm.load(filepath)
    assert post.metadata["source"] == "narrative-review"
    assert post.metadata["source_review"] == "2026-08-25-review"


def test_update_council_fields_rejects_disallowed_field(tmp_path):
    _write_council_item(tmp_path)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "2026-08-18-test-item", {"title": "Hijacked"})
    assert result is False


def test_update_council_fields_missing_entry_returns_false(tmp_path):
    (tmp_path / "projects" / "myproj" / "council").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "does-not-exist", {"weeks_open": "2"})
    assert result is False


def test_update_council_fields_rejects_path_traversal(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_council import update_council_fields
        result = update_council_fields("myproj", "../../etc/passwd", {"weeks_open": "2"})
    assert result is False
