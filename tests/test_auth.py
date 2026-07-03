from app import create_app
from flask import Blueprint, jsonify
from app.routes.auth import require_capture_token


def test_require_capture_token_allows_valid_token(monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret")
    a = create_app({"TESTING": True})

    bp = Blueprint("auth_test_ok", __name__)

    @bp.route("/test-auth-ok")
    @require_capture_token
    def _protected():
        return jsonify({"ok": True})

    a.register_blueprint(bp)

    client = a.test_client()
    resp = client.get("/test-auth-ok", headers={"X-Capture-Token": "secret"})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_require_capture_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("CAPTURE_TOKEN", "secret")
    a = create_app({"TESTING": True})

    bp = Blueprint("auth_test_reject", __name__)

    @bp.route("/test-auth-reject")
    @require_capture_token
    def _protected():
        return jsonify({"ok": True})

    a.register_blueprint(bp)

    client = a.test_client()
    resp = client.get("/test-auth-reject", headers={"X-Capture-Token": "wrong"})
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Unauthorized"}


def test_require_capture_token_returns_503_when_token_not_configured(monkeypatch):
    monkeypatch.delenv("CAPTURE_TOKEN", raising=False)
    a = create_app({"TESTING": True})

    bp = Blueprint("auth_test_503", __name__)

    @bp.route("/test-auth-503")
    @require_capture_token
    def _protected():
        return jsonify({"ok": True})

    a.register_blueprint(bp)

    client = a.test_client()
    resp = client.get("/test-auth-503")
    assert resp.status_code == 503
    assert resp.get_json() == {"error": "Service unavailable"}
