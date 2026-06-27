import os
import time
from pathlib import Path

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))

VALID_TYPES = {
    "note", "idea", "bug", "decision",
    "grill-me", "housekeeping-task", "housekeeping-heartbeat",
}
VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs", "grill-me": "grill-me"}
TYPE_TAGS = {
    "note": "documentation",
    "idea": "enhancement",
    "bug": "bug",
    "decision": "decision",
    "grill-me": "grill-me",
}

_TTL = 600.0  # 10 minutes

_projects_cache: list | None = None
_projects_cache_ts: float = 0.0

_entries_cache: list | None = None
_entries_cache_ts: float = 0.0

_hub_pages_cache: list | None = None
_hub_pages_cache_ts: float = 0.0


def _invalidate_cache() -> None:
    global _projects_cache, _projects_cache_ts
    global _entries_cache, _entries_cache_ts
    global _hub_pages_cache, _hub_pages_cache_ts
    _projects_cache = None
    _projects_cache_ts = 0.0
    _entries_cache = None
    _entries_cache_ts = 0.0
    _hub_pages_cache = None
    _hub_pages_cache_ts = 0.0
