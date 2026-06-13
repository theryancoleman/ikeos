import pytest
from pathlib import Path
from unittest.mock import patch
import yaml


def _write_registry(tmp_path, data):
    reg = tmp_path / "umbrella_registry.yaml"
    reg.write_text(yaml.dump(data))
    return reg


def _patch_registry(path):
    return patch("app.services.umbrella._REGISTRY_PATH", path)


def _reset():
    import app.services.umbrella as m
    m._registry = None


def test_load_registry_returns_empty_when_file_missing(tmp_path):
    with _patch_registry(tmp_path / "missing.yaml"):
        _reset()
        from app.services.umbrella import load_registry
        assert load_registry() == {}


def test_get_components_returns_list(tmp_path):
    reg = _write_registry(tmp_path, {
        "ikeos": {"name": "IkeOS", "components": ["voice-bridge", "display"]}
    })
    with _patch_registry(reg):
        _reset()
        from app.services.umbrella import get_components
        assert get_components("ikeos") == ["voice-bridge", "display"]


def test_get_components_returns_empty_for_flat_umbrella(tmp_path):
    reg = _write_registry(tmp_path, {"wayvr": {"name": "Wayvr", "components": []}})
    with _patch_registry(reg):
        _reset()
        from app.services.umbrella import get_components
        assert get_components("wayvr") == []


def test_get_components_returns_empty_for_unknown_slug(tmp_path):
    reg = _write_registry(tmp_path, {})
    with _patch_registry(reg):
        _reset()
        from app.services.umbrella import get_components
        assert get_components("unknown") == []


def test_is_component_true(tmp_path):
    reg = _write_registry(tmp_path, {
        "homelab-manager": {"name": "Homelab Manager", "components": ["obsidian-capture"]}
    })
    with _patch_registry(reg):
        _reset()
        from app.services.umbrella import is_component
        assert is_component("obsidian-capture") is True
        assert is_component("homelab-manager") is False


def test_get_parent_umbrella(tmp_path):
    reg = _write_registry(tmp_path, {
        "homelab-manager": {"name": "Homelab Manager", "components": ["obsidian-capture"]}
    })
    with _patch_registry(reg):
        _reset()
        from app.services.umbrella import get_parent_umbrella
        assert get_parent_umbrella("obsidian-capture") == "homelab-manager"
        assert get_parent_umbrella("unknown") is None


def test_get_all_umbrellas_returns_dict(tmp_path):
    data = {
        "ikeos": {"name": "IkeOS", "components": ["voice-bridge"]},
        "wayvr": {"name": "Wayvr", "components": []},
    }
    reg = _write_registry(tmp_path, data)
    with _patch_registry(reg):
        _reset()
        from app.services.umbrella import get_all_umbrellas
        result = get_all_umbrellas()
    assert set(result.keys()) == {"ikeos", "wayvr"}
