import os
from datetime import date
from pathlib import Path

import yaml

_REGISTRY_PATH = Path(
    os.environ.get(
        "SKILLS_REGISTRY_PATH",
        Path(__file__).parent.parent.parent / "skills_registry.yaml",
    )
)

_BADGE_WINDOW_DAYS = 14


def _compute_badge(skill: dict) -> str | None:
    today = date.today()

    added = skill.get("added")
    if added is not None:
        added_date = added if isinstance(added, date) else date.fromisoformat(str(added))
        if (today - added_date).days <= _BADGE_WINDOW_DAYS:
            return "new"

    updated = skill.get("updated")
    if updated is not None:
        updated_date = updated if isinstance(updated, date) else date.fromisoformat(str(updated))
        if (today - updated_date).days <= _BADGE_WINDOW_DAYS:
            return "updated"

    return None


def get_skills() -> list[dict]:
    if not _REGISTRY_PATH.exists():
        return []
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("skills", [])


def get_skills_by_category() -> dict[str, list[dict]]:
    skills = get_skills()
    grouped: dict[str, list[dict]] = {}
    for skill in skills:
        cat = skill.get("category", "Other")
        skill_entry = dict(skill)
        skill_entry["badge"] = _compute_badge(skill)
        grouped.setdefault(cat, []).append(skill_entry)
    return grouped
