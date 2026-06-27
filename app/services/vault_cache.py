import os
import time
from pathlib import Path

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))

VALID_STATUSES = {"new", "open", "in-progress", "done", "deferred"}
DECISION_STATUSES = {"proposed", "accepted", "rejected", "superseded"}
EXPERIMENT_STATUSES = {"running", "complete", "abandoned"}

ENTRY_TYPE_CONFIG: dict[str, dict] = {
    "note":       {"folder": "notes",       "tag": "documentation", "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "idea":       {"folder": "ideas",       "tag": "enhancement",   "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "bug":        {"folder": "bugs",        "tag": "bug",           "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "grill-me":   {"folder": "grill-me",    "tag": "grill-me",      "initial_status": "new",     "valid_statuses": VALID_STATUSES},
    "experiment": {"folder": "experiments", "tag": "experiment",    "initial_status": "running", "valid_statuses": EXPERIMENT_STATUSES},
}

TYPE_FOLDERS = {k: v["folder"] for k, v in ENTRY_TYPE_CONFIG.items()}
TYPE_TAGS = {k: v["tag"] for k, v in ENTRY_TYPE_CONFIG.items()}

VALID_TYPES = set(ENTRY_TYPE_CONFIG.keys()) | {
    "decision", "housekeeping-task", "housekeeping-heartbeat",
}

PATCH_VALID_TYPES: frozenset[str] = frozenset(ENTRY_TYPE_CONFIG.keys()) | {"decision"}
CAPTURE_JSON_VALID_TYPES: frozenset[str] = (
    frozenset(ENTRY_TYPE_CONFIG.keys()) | {"housekeeping-task", "housekeeping-heartbeat"}
)

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
