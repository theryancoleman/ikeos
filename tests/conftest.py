import os
import pytest
from unittest.mock import patch
from app import create_app
from app.services.vault import _invalidate_cache


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")


@pytest.fixture(autouse=True)
def reset_vault_cache():
    _invalidate_cache()
    yield
    _invalidate_cache()


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as c:
        yield c


@pytest.fixture
def tmp_vault(tmp_path):
    """Vault fixture that patches VAULT_PATH and creates a testproject directory."""
    (tmp_path / "projects" / "testproject").mkdir(parents=True)
    with patch("app.services.vault_cache.VAULT_PATH", tmp_path):
        yield tmp_path
