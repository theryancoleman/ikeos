import pytest
from unittest.mock import patch
import frontmatter as fm
import app.services.vault_cache as _vc


@pytest.fixture(autouse=True)
def reset_cache():
    _vc._invalidate_cache()
    yield
    _vc._invalidate_cache()


def test_get_vault_graph_returns_expected_structure(tmp_path):
    (tmp_path / "projects" / "myproj" / "notes").mkdir(parents=True)
    (tmp_path / "projects" / "myproj" / "notes" / "2026-01-01-note.md").write_text(
        "---\ntype: note\ntitle: My Note\nproject: myproj\n"
        "status: new\ncreated: 2026-01-01T00:00:00\ntags: []\n---\n## Description\nHello\n"
    )
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_graph import get_vault_graph
        result = get_vault_graph()
    assert "nodes" in result
    assert "links" in result
    assert "health" in result
    assert any(n["id"] == "2026-01-01-note" for n in result["nodes"])


def test_write_hub_page_creates_hub_file(tmp_path):
    (tmp_path / "projects" / "myplatform").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_graph import write_hub_page
        write_hub_page("myplatform", "My Platform", ["api", "worker"])
    files = list((tmp_path / "projects" / "myplatform").glob("*.md"))
    assert any(f.name == "My Platform.md" for f in files)
    post = fm.load(tmp_path / "projects" / "myplatform" / "My Platform.md")
    assert post.metadata["type"] == "hub"


def test_write_component_stub_creates_stub(tmp_path):
    (tmp_path / "projects" / "myplatform").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        from app.services.vault_graph import write_component_stub
        write_component_stub("myplatform", "api")
    stubs_dir = tmp_path / "projects" / "myplatform" / "components"
    assert (stubs_dir / "api.md").exists()
