import os
from pathlib import Path

import yaml

_REGISTRY_PATH = Path(
    os.environ.get(
        "SKILLS_REGISTRY_PATH",
        Path(__file__).parent.parent.parent / "skills_registry.yaml",
    )
)


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
        grouped.setdefault(cat, []).append(skill)
    return grouped
