import os
import pytest
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
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
