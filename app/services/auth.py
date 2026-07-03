import functools
import os

from flask import jsonify, request


def require_capture_token(f):
    """Decorator: rejects requests that lack a valid X-Capture-Token header.

    Returns 503 when CAPTURE_TOKEN is not configured, 401 on mismatch.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = os.environ.get("CAPTURE_TOKEN", "")
        if not token:
            return jsonify({"error": "Service unavailable"}), 503
        if request.headers.get("X-Capture-Token", "") != token:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated
