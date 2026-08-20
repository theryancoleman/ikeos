import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_FILE = Path.home() / ".claude-sessions.json"

_lock = threading.Lock()


def _load() -> list[dict]:
    if not SESSIONS_FILE.exists():
        return []
    return json.loads(SESSIONS_FILE.read_text())


def _save(sessions: list[dict]) -> None:
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))


def list_sessions() -> list[dict]:
    with _lock:
        return _load()


def get_session(session_id: str) -> dict | None:
    with _lock:
        return next((s for s in _load() if s["id"] == session_id), None)


def create_session(name: str, project: str, project_dir: str,
                   remote_control: bool = False, ephemeral: bool = False,
                   model: str | None = None) -> dict:
    session = {
        "id": str(uuid.uuid4()),
        "name": name,
        "project": project,
        "project_dir": project_dir,
        "remote_control": remote_control,
        "remote_control_confirmed": False,
        "autonomous_mode": False,
        "ephemeral": ephemeral,
        "model": model,
        "status": "active",
        "tmux_session": name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "message_count": 0,
        "compaction_detected": False,
        "last_pane_check": None,
    }
    with _lock:
        sessions = _load()
        sessions.append(session)
        _save(sessions)
    return session


def update_session(session_id: str, **kwargs: object) -> dict | None:
    with _lock:
        sessions = _load()
        for s in sessions:
            if s["id"] == session_id:
                s.update(kwargs)
                _save(sessions)
                return s
    return None


def remove_session(session_id: str) -> bool:
    with _lock:
        sessions = _load()
        new_sessions = [s for s in sessions if s["id"] != session_id]
        if len(new_sessions) == len(sessions):
            return False
        _save(new_sessions)
    return True
