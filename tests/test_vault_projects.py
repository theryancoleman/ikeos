import pytest
from unittest.mock import patch
import frontmatter as fm
import app.services.vault_cache as _vc


@pytest.fixture(autouse=True)
def reset_cache():
    _vc._invalidate_cache()
    yield
    _vc._invalidate_cache()


def test_get_projects_returns_sorted_list(tmp_path):
    (tmp_path / "projects" / "alpha").mkdir(parents=True)
    (tmp_path / "projects" / "beta").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects
        result = get_projects()
    assert result == ["alpha", "beta"]


def test_get_projects_empty_when_no_dir(tmp_path):
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects
        result = get_projects()
    assert result == []


def test_get_projects_with_meta_returns_name_from_project_md(tmp_path):
    proj_dir = tmp_path / "projects" / "myproj"
    proj_dir.mkdir(parents=True)
    meta = fm.Post("", name="My Project", description="desc", hidden=False)
    (proj_dir / "project.md").write_text(fm.dumps(meta))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects_with_meta
        result = get_projects_with_meta()
    assert len(result) == 1
    assert result[0]["name"] == "My Project"
    assert result[0]["slug"] == "myproj"


def test_get_projects_with_meta_excludes_hidden_by_default(tmp_path):
    proj_dir = tmp_path / "projects" / "hidden-proj"
    proj_dir.mkdir(parents=True)
    meta = fm.Post("", name="Hidden", description="", hidden=True)
    (proj_dir / "project.md").write_text(fm.dumps(meta))
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import get_projects_with_meta
        result = get_projects_with_meta()
    assert result == []


def test_write_project_meta_creates_project_md(tmp_path):
    (tmp_path / "projects" / "myproj").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_projects import write_project_meta
        result = write_project_meta("myproj", "My Project", "A description", False)
    assert result is True
    post = fm.load(tmp_path / "projects" / "myproj" / "project.md")
    assert post.metadata["name"] == "My Project"
    assert post.metadata["description"] == "A description"
