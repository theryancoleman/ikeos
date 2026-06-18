import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_DEFAULTS: dict = {
    "enabled": False,
    "day_of_week": "sun",
    "hour": 3,
    "minute": 7,
    "last_triggered": None,
}

_scheduler = None  # set by start(); None in tests and before startup


def _schedule_path() -> Path:
    vault = Path(os.environ.get("VAULT_PATH", "/vault"))
    return vault / "projects" / "claude-config" / "housekeeping" / "schedule.json"


def _write_config(config: dict) -> None:
    path = _schedule_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(config, f, indent=2)
    tmp.replace(path)


def get_config() -> dict:
    path = _schedule_path()
    if not path.exists():
        return _DEFAULTS.copy()
    try:
        with open(path) as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except Exception:
        logger.exception("Failed to read schedule config from %s", path)
        return _DEFAULTS.copy()


def _validate(fields: dict) -> None:
    if "day_of_week" in fields and fields["day_of_week"] not in _VALID_DAYS:
        raise ValueError(
            f"day_of_week must be one of: {', '.join(sorted(_VALID_DAYS))}"
        )
    if "hour" in fields and not (0 <= int(fields["hour"]) <= 23):
        raise ValueError("hour must be 0–23")
    if "minute" in fields and not (0 <= int(fields["minute"]) <= 59):
        raise ValueError("minute must be 0–59")


def _reschedule(config: dict) -> None:
    if _scheduler is None:
        return
    job = _scheduler.get_job("housekeeping")
    if job is None:
        return
    _scheduler.reschedule_job(
        "housekeeping",
        trigger="cron",
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
    )
    if config.get("enabled"):
        _scheduler.resume_job("housekeeping")
    else:
        _scheduler.pause_job("housekeeping")


def update_config(fields: dict) -> dict:
    _validate(fields)
    current = get_config()
    allowed = {"enabled", "day_of_week", "hour", "minute"}
    for k, v in fields.items():
        if k in allowed:
            current[k] = v
    _write_config(current)
    _reschedule(current)
    return current


def get_config_with_next_run() -> dict:
    config = get_config()
    config["next_run"] = None
    if config.get("enabled") and _scheduler is not None:
        job = _scheduler.get_job("housekeeping")
        if job and job.next_run_time:
            config["next_run"] = job.next_run_time.isoformat(timespec="seconds")
    return config
