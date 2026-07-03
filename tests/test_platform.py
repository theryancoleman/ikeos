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
