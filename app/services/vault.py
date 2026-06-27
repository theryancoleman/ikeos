# Public API — re-exports from vault sub-modules.
# All existing callers of `from app.services.vault import X` continue to work.
# To add new functions, implement them in the appropriate sub-module and re-export here.

from app.services.vault_cache import (  # noqa: F401
    VAULT_PATH,
    VALID_TYPES,
    VALID_STATUSES,
    DECISION_STATUSES,
    TYPE_FOLDERS,
    TYPE_TAGS,
    _TTL,
    _invalidate_cache,
    _projects_cache,
    _projects_cache_ts,
    _entries_cache,
    _entries_cache_ts,
    _hub_pages_cache,
    _hub_pages_cache_ts,
)

from app.services.vault_projects import (  # noqa: F401
    _read_project_meta,
    get_projects,
    get_projects_with_meta,
    write_project_meta,
)

from app.services.vault_entries import (  # noqa: F401
    _slugify,
    write_entry,
    _read_all_entries,
    read_entries,
    read_entry,
    update_entry_status,
    update_entry_status_generic,
)

from app.services.vault_graph import (  # noqa: F401
    _WIKILINK_RE,
    _STALE_DAYS,
    _get_urgency,
    _read_hub_pages,
    get_vault_graph,
    write_hub_page,
    write_component_stub,
)

from app.services.vault_housekeeping import (  # noqa: F401
    _HOUSEKEEPING_ALLOWED_FIELDS,
    _INTERVAL_THRESHOLDS,
    _compute_task_status,
    _compute_next_run,
    read_housekeeping_tasks,
    read_housekeeping_heartbeat,
    update_housekeeping_fields,
    delete_housekeeping_task,
)
