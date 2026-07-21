import fcntl
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from app.services.driver import run_scheduled_housekeeping
from app.services.metrics import append_event
from app.services.platform import project_slug

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Toronto")

_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_DEFAULTS: dict[str, bool | str | int | None] = {
    "enabled": False,
    "day_of_week": "sun",
    "hour": 3,
    "minute": 7,
    "last_triggered": None,
}

_scheduler = None  # set by start() — only on the worker that wins leader election
_lock_fd = None  # open file object backing the leader lock; kept open for process lifetime
_applied_config = None  # dict of day_of_week/hour/minute/enabled last applied to the live job (leader only)

# Advisory lock used for gunicorn multi-worker leader election so only one
# worker process owns the live APScheduler instance. Lives in the
# container's own /tmp (not a mounted volume) — shared by all worker
# processes of a single container, reset on container restart.
_LOCK_PATH = Path(os.environ.get("SCHEDULER_LOCK_PATH", "/tmp/ikeos-scheduler.lock"))

# How often the leader re-checks schedule.json against the live cron job.
# Bridges the gap when a PATCH request lands on a non-leader worker (which
# has no live scheduler to reschedule directly) — the leader picks up the
# on-disk change within one sync interval.
_SYNC_INTERVAL_SECONDS = 60


def _schedule_path() -> Path:
    vault = Path(os.environ.get("VAULT_PATH", "/vault"))
    return vault / "projects" / project_slug() / "housekeeping" / "schedule.json"


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


def _acquire_leader_lock(path: Path = None):
    """Try to acquire a non-blocking exclusive advisory lock at `path`.

    Returns the open file object on success (caller must keep it open for
    the lock to hold — it releases automatically when the fd is closed or
    the process exits/crashes), or None if another process already holds
    it. Pure and stateless — safe to call directly in tests to simulate
    multiple worker processes racing for leadership.
    """
    if path is None:
        path = _LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def _compute_next_run(config: dict, now: datetime | None = None) -> str | None:
    """Analytically compute the next fire time from cron fields alone.

    Deliberately independent of any live APScheduler instance so every
    worker process — leader or not — computes the identical value from the
    same on-disk config. This is what makes GET /housekeeping/schedule
    consistent regardless of which worker answers it.
    """
    if not config.get("enabled"):
        return None
    trigger = CronTrigger(
        day_of_week=config["day_of_week"],
        hour=config["hour"],
        minute=config["minute"],
        timezone=_TZ,
    )
    next_fire = trigger.get_next_fire_time(None, now or datetime.now(_TZ))
    return next_fire.isoformat(timespec="seconds") if next_fire else None


def _apply_to_live_scheduler(config: dict) -> None:
    """Reschedule the live cron job to match `config`. No-op unless this
    process is the leader (i.e. holds a real `_scheduler`)."""
    global _applied_config
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
        timezone=_TZ,
    )
    if config.get("enabled"):
        _scheduler.resume_job("housekeeping")
    else:
        _scheduler.pause_job("housekeeping")
    _applied_config = {k: config[k] for k in ("day_of_week", "hour", "minute", "enabled")}


def _sync_schedule() -> None:
    """Leader-only periodic tick: re-read schedule.json and reapply to the
    live job if it has changed since we last applied it. Covers the case
    where PATCH /housekeeping/schedule was handled by a non-leader worker,
    which can write schedule.json but has no live job to reschedule."""
    config = get_config()
    desired = {k: config[k] for k in ("day_of_week", "hour", "minute", "enabled")}
    if desired != _applied_config:
        _apply_to_live_scheduler(config)


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
    _apply_to_live_scheduler(current)
    return current


def get_config_with_next_run() -> dict:
    config = get_config()
    return {**config, "next_run": _compute_next_run(config)}


def trigger_now() -> str | None:
    """One-shot immediate run. Deliberately independent of leader election —
    any worker can serve "Run Now" by invoking the housekeeping run directly
    in-process; it never needs the live APScheduler instance."""
    result = run_scheduled_housekeeping()
    if not result.ok:
        logger.error("Failed to create housekeeping session: %s", result.error)
        return None
    session_id = result.session_id
    config = get_config()
    config["last_triggered"] = datetime.now(_TZ).isoformat(timespec="seconds")
    try:
        _write_config(config)
    except OSError:
        logger.exception("Failed to write last_triggered after scheduling housekeeping session")
    append_event("housekeeping.trigger", {
        "trigger": "scheduled" if _scheduler else "manual",
        "session_id": session_id,
        "project": project_slug(),
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
    global _scheduler, _lock_fd, _applied_config
    if app.config.get("TESTING"):
        return
    if _scheduler is not None and _scheduler.running:
        logger.warning(
            "APScheduler already running in this process — skipping duplicate start."
        )
        return

    if _lock_fd is None:
        _lock_fd = _acquire_leader_lock()
    if _lock_fd is None:
        logger.info(
            "Scheduler leader lock (%s) held by another worker process — this "
            "worker will not run a live scheduler. Schedule reads/writes and "
            "trigger_now() remain fully functional.",
            _LOCK_PATH,
        )
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
        timezone=_TZ,
    )
    _scheduler.add_job(
        _sync_schedule,
        "interval",
        id="housekeeping-sync",
        seconds=_SYNC_INTERVAL_SECONDS,
    )
    _scheduler.start()
    if not config.get("enabled"):
        _scheduler.pause_job("housekeeping")
    _applied_config = {k: config[k] for k in ("day_of_week", "hour", "minute", "enabled")}
    logger.info(
        "Housekeeping scheduler started as leader worker (pid=%s, enabled=%s, schedule=%s %s:%s)",
        os.getpid(),
        config.get("enabled"),
        config["day_of_week"],
        config["hour"],
        config["minute"],
    )
