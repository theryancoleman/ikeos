import pytest
from app import create_app


@pytest.fixture
def client(set_env):
    """Create a fresh app client; depends on set_env so FLASK_SECRET_KEY is available."""
    a = create_app({"TESTING": True})
    return a.test_client()


def test_require_capture_token_allows_valid_token(client, monkeypatch):
    """A request with the correct X-Capture-Token header returns the route's response."""
    monkeypatch.setenv("CAPTURE_TOKEN", "secret")
    from app.services.auth import require_capture_token
    from flask import Blueprint, jsonify

    app = client.application

    bp = Blueprint("auth_test", __name__)

    @bp.route("/test-auth")
    @require_capture_token
    def _protected():
        return jsonify({"ok": True})

    app.register_blueprint(bp)
    resp = client.get("/test-auth", headers={"X-Capture-Token": "secret"})
    assert resp.status_code == 200


def test_require_capture_token_rejects_wrong_token(client, monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret")
    from app.services.auth import require_capture_token
    from flask import Blueprint, jsonify

    app = client.application

    bp2 = Blueprint("auth_test2", __name__)

    @bp2.route("/test-auth2")
    @require_capture_token
    def _protected2():
        return jsonify({"ok": True})

    app.register_blueprint(bp2)
    resp = client.get("/test-auth2", headers={"X-Capture-Token": "wrong"})
    assert resp.status_code == 401


def test_require_capture_token_returns_503_when_token_not_configured(client, monkeypatch):
    monkeypatch.delenv("CAPTURE_TOKEN", raising=False)
    from app.services.auth import require_capture_token
    from flask import Blueprint, jsonify

    app = client.application

    bp3 = Blueprint("auth_test3", __name__)

    @bp3.route("/test-auth3")
    @require_capture_token
    def _protected3():
        return jsonify({"ok": True})

    app.register_blueprint(bp3)
    resp = client.get("/test-auth3")
    assert resp.status_code == 503
