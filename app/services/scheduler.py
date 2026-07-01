import json
import logging
import os
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_DEFAULTS: dict[str, bool | str | int | None] = {
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
        raise ValueError(f"day_of_week must be one of: {', '.join(sorted(_VALID_DAYS))}")
    if "hour" in fields:
        try:
            hour = int(fields["hour"])
        except (TypeError, ValueError):
            raise ValueError("hour must be 0-23")
        if not (0 <= hour <= 23):
            raise ValueError("hour must be 0-23")
    if "minute" in fields:
        try:
            minute = int(fields["minute"])
        except (TypeError, ValueError):
            raise ValueError("minute must be 0-59")
        if not (0 <= minute <= 59):
            raise ValueError("minute must be 0-59")


def _reschedule(config: dict) -> None:
    if _scheduler is None:
        return
    job = _scheduler.get_job("housekeeping")
    if job is None:
        logger.warning("housekeeping job not found in scheduler; live schedule not updated")
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
    unknown = set(fields) - allowed
    if unknown:
        logger.warning("update_config: ignoring unknown field(s): %s", ", ".join(sorted(unknown)))
    for k, v in fields.items():
        if k in allowed:
            current[k] = v
    _write_config(current)
    _reschedule(current)
    return current


def get_config_with_next_run() -> dict:
    config = get_config()
    next_run = None
    if config.get("enabled") and _scheduler is not None:
        job = _scheduler.get_job("housekeeping")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat(timespec="seconds")
    return {**config, "next_run": next_run}


def trigger_now() -> str | None:
    now = datetime.now()
    session_name = f"housekeeping-{now.strftime('%Y%m%d')}"
    sm_url = os.environ.get("SESSION_MANAGER_URL", "http://host.docker.internal:5010")
    project_dir = os.environ.get("HOUSEKEEPING_PROJECT_DIR", "/mnt/c/Server/claude-config")
    try:
        create_resp = requests.post(
            f"{sm_url}/sessions",
            json={
                "name": session_name,
                "project": "claude-config",
                "project_dir": project_dir,
                "initial_command": "/housekeeping — run in scheduled mode",
            },
            timeout=5,
        )
        if not create_resp.ok:
            logger.error("Failed to create housekeeping session: %s", create_resp.status_code)
            return None
        session_id = create_resp.json().get("id")
        if not session_id:
            logger.error("No session ID returned from session manager")
            return None
    except (requests.RequestException, OSError):
        logger.exception("Housekeeping trigger failed")
        return None
    config = get_config()
    config["last_triggered"] = now.isoformat(timespec="seconds")
    try:
        _write_config(config)
    except OSError:
        logger.exception("Failed to write last_triggered after scheduling housekeeping session")

    from app.services.metrics import append_event
    append_event("housekeeping.trigger", {
        "trigger": "scheduled" if _scheduler else "manual",
        "session_id": session_id,
        "project": "claude-config",
    })

    return session_id


def _job() -> None:
    from app.services.capabilities import is_enabled
    if not is_enabled("housekeeping_scheduler"):
        logger.info("Housekeeping job skipped: capability gate disabled")
        return
    logger.info("Housekeeping scheduled trigger firing")
    trigger_now()


def start(app) -> None:
    global _scheduler
    if app.config.get("TESTING"):
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    config = get_config()
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _job,
        "cron",
        id="housekeeping",
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
    )
    _scheduler.start()
    if not config.get("enabled"):
        _scheduler.pause_job("housekeeping")
    logger.info(
        "Housekeeping scheduler started (enabled=%s, schedule=%s %s:%s)",
        config.get("enabled"),
        config["day_of_week"],
        config["hour"],
        config["minute"],
    )
