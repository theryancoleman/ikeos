import pytest
from app.services.platform import config_version_path, project_slug


def test_project_slug_default(monkeypatch):
    monkeypatch.delenv("PLATFORM_PROJECT_SLUG", raising=False)
    assert project_slug() == "claude-config"


def test_project_slug_env_override(monkeypatch):
    monkeypatch.setenv("PLATFORM_PROJECT_SLUG", "my-config")
    assert project_slug() == "my-config"


def test_config_version_path_default(monkeypatch):
    monkeypatch.delenv("CONFIG_VERSION_PATH", raising=False)
    assert config_version_path() == "/claude-config/VERSION"


def test_config_version_path_blank_disables(monkeypatch):
    monkeypatch.setenv("CONFIG_VERSION_PATH", "")
    assert config_version_path() == ""


def test_context_processor_reads_from_config_version_path(tmp_path, monkeypatch):
    """inject_config_version uses config_version_path(), not a hardcoded path."""
    version_file = tmp_path / "VERSION"
    version_file.write_text("2026.07.03-test\n")
    monkeypatch.setenv("CONFIG_VERSION_PATH", str(version_file))
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    from app import create_app
    app = create_app({"TESTING": True})
    with app.app_context():
        for cp in app.template_context_processors[None]:
            result = cp()
            if "config_version" in result:
                assert result["config_version"] == "2026.07.03-test"
                return
        pytest.fail("inject_config_version context processor not found")


def test_context_processor_returns_none_when_path_blank(monkeypatch):
    """inject_config_version returns None when CONFIG_VERSION_PATH is blank."""
    monkeypatch.setenv("CONFIG_VERSION_PATH", "")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    from app import create_app
    app = create_app({"TESTING": True})
    with app.app_context():
        for cp in app.template_context_processors[None]:
            result = cp()
            if "config_version" in result:
                assert result["config_version"] is None
                return
        pytest.fail("inject_config_version context processor not found")
