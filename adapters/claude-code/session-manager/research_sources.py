import base64
import json
import os
import threading
from datetime import date
from pathlib import Path

# Standalone reference-implementation storage: a home-directory dotfile,
# matching sessions.py's SESSIONS_FILE convention — no dependency on any
# specific host's private repo layout.
RESEARCH_SOURCES_FILE = Path.home() / ".claude-research-sources.json"

_lock = threading.Lock()


def _encode_id(url: str) -> str:
    """Derive a stable, URL-path-safe id from a source's URL (its natural key)."""
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def _decode_id(source_id: str) -> str | None:
    padded = source_id + "=" * (-len(source_id) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        return None


def _with_id(source: dict) -> dict:
    return {"id": _encode_id(source["url"]), **source}


def _load() -> dict:
    if not RESEARCH_SOURCES_FILE.exists():
        return {"_version": 1, "sources": []}
    return json.loads(RESEARCH_SOURCES_FILE.read_text())


def _save(data: dict) -> None:
    """Atomic write: write to a temp file in the same directory, then rename."""
    tmp_path = RESEARCH_SOURCES_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, indent=2))
    os.replace(tmp_path, RESEARCH_SOURCES_FILE)


def list_sources() -> list[dict]:
    with _lock:
        data = _load()
    return [_with_id(s) for s in data.get("sources", [])]


def add_source(url: str, label: str) -> dict:
    with _lock:
        data = _load()
        source = {
            "url": url,
            "label": label,
            "status": "active",
            "last_fetched": None,
            "entries_generated": 0,
            "added": date.today().isoformat(),
            "blacklisted": False,
        }
        data.setdefault("sources", []).append(source)
        _save(data)
    return _with_id(source)


def find_source(source_id: str) -> dict | None:
    url = _decode_id(source_id)
    if url is None:
        return None
    with _lock:
        data = _load()
    source = next((s for s in data.get("sources", []) if s["url"] == url), None)
    return _with_id(source) if source else None


def set_blacklisted(source_id: str, blacklisted: bool) -> dict | None:
    url = _decode_id(source_id)
    if url is None:
        return None
    with _lock:
        data = _load()
        source = next((s for s in data.get("sources", []) if s["url"] == url), None)
        if source is None:
            return None
        source["blacklisted"] = blacklisted
        _save(data)
        return _with_id(source)
