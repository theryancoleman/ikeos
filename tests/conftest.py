import os
import pytest
from app import create_app


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
