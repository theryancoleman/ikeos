import os
from pathlib import Path

import yaml

_REGISTRY_PATH = Path(
    os.environ.get(
        "UMBRELLA_REGISTRY_PATH",
        Path(__file__).parent.parent.parent / "umbrella_registry.yaml",
    )
)

_registry: dict | None = None


def _reset_cache() -> None:
    global _registry
    _registry = None


def load_registry() -> dict:
    global _registry
    if _registry is not None:
        return _registry
    if not _REGISTRY_PATH.exists():
        _registry = {}
        return _registry
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _registry = data
    return _registry


def get_all_umbrellas() -> dict:
    return load_registry()


def get_umbrella(slug: str) -> dict | None:
    return load_registry().get(slug)


def get_components(umbrella_slug: str) -> list[str]:
    entry = get_umbrella(umbrella_slug)
    if not entry:
        return []
    return entry.get("components", [])


def is_component(slug: str) -> bool:
    for umbrella in load_registry().values():
        if slug in umbrella.get("components", []):
            return True
    return False


def get_parent_umbrella(component_slug: str) -> str | None:
    for umbrella_slug, umbrella in load_registry().items():
        if component_slug in umbrella.get("components", []):
            return umbrella_slug
    return None


def get_umbrella_name(slug: str) -> str:
    """Return the display name for an umbrella slug, falling back to the slug itself."""
    entry = get_umbrella(slug)
    if not entry:
        return slug
    return entry.get("name", slug)
