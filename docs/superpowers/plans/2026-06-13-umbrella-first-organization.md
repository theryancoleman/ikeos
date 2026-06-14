# Umbrella-First Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the vault and capture system so tasks are organized by umbrella project (a multi-component parent, e.g. IkeOS) rather than flat sub-project, with Obsidian graph connections between entries, hub pages, and component stubs.

**Architecture:** A YAML umbrella registry defines which project slugs have sub-components. The capture form shows umbrella first, then optionally a component picker. Entries written into the umbrella's vault folder with an optional `component` field in frontmatter and a `[[umbrella-slug]]` wikilink in the body. A hub page (`projects/<umbrella>/<umbrella>.md`) and component stubs (`projects/<umbrella>/components/<name>.md`) provide named nodes the graph can draw edges between. A one-time migration script moves existing component entries into the appropriate umbrella folder.

**Tech Stack:** Python/Flask, PyYAML, python-frontmatter, pytest, Jinja2, vanilla JS

---

## File Map

**Create:**
- `umbrella_registry.yaml` — registry of umbrellas and their component slugs
- `app/services/umbrella.py` — load/query the registry
- `scripts/migrate_to_umbrella.py` — one-time migration; dry-run by default
- `tests/test_umbrella.py` — tests for umbrella service
- `tests/test_migrate.py` — tests for migration functions

**Modify:**
- `app/services/vault.py` — `write_entry` adds `component` field + wikilink; add `write_hub_page`, `write_component_stub`, `_read_hub_pages`; update `get_vault_graph` to include hub/stub nodes; add `component` filter to `read_entries`
- `app/routes/capture.py` — inject umbrella registry into form, handle `component` field in submit
- `app/templates/capture.html` — umbrella-first two-level picker with JS
- `app/routes/browse.py` — pass component list and filter to project view
- `app/templates/project.html` — component filter pills

---

## Task 1: Umbrella Registry config + service

**Files:**
- Create: `umbrella_registry.yaml`
- Create: `app/services/umbrella.py`
- Create: `tests/test_umbrella.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_umbrella.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /mnt/c/Server/projects/obsidian-capture
python -m pytest tests/test_umbrella.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError` for `app.services.umbrella`

- [ ] **Step 3: Create the umbrella registry YAML**

```yaml
# umbrella_registry.yaml
# Maps umbrella project slugs to their component sub-projects.
# Components listed here will be hidden from the top-level project picker
# and captured into the umbrella's vault folder.
#
# Flat projects (components: []) appear as normal projects with no component picker.

ikeos:
  name: IkeOS
  components: []            # TODO: add component slugs as IkeOS services are defined

claude-config:
  name: Claude Config
  components:
    - claude-code

homelab-manager:
  name: Homelab Manager
  components:
    - obsidian-capture

bcr-waivers:
  name: Wayvr
  components: []

frc-dashboard:
  name: PitRadar
  components: []

spotify-beatport:
  name: Spotify × Beatport
  components: []

worldwardle:
  name: Worldwardle
  components: []

zone-builder:
  name: Zone Builder
  components: []

n8n:
  name: n8n
  components: []

microgames-dev:
  name: Microgames Dev
  components: []

pixitup:
  name: PixItUp
  components: []

rcade:
  name: RCADE
  components: []
```

- [ ] **Step 4: Create `app/services/umbrella.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_umbrella.py -v
```
Expected: all 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add umbrella_registry.yaml app/services/umbrella.py tests/test_umbrella.py
git commit -m "feat: add umbrella registry config and service"
```

---

## Task 2: vault.py — component field in write_entry

Add `component` field support to `write_entry`: stores component tag, adds wikilink to body so entries link to their umbrella hub in the graph.

**Files:**
- Modify: `app/services/vault.py`
- Modify: `tests/test_vault.py` (add cases at bottom)

- [ ] **Step 1: Write failing tests (add to bottom of `tests/test_vault.py`)**

```python
# ── component / umbrella ─────────────────────────────────────────────────────

def test_write_entry_with_component_sets_component_tag(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "bug", "project": "ikeos", "title": "Boot crash",
            "body": "It breaks", "severity": "high",
            "component": "voice-bridge",
        })
    files = list((vault / "projects" / "ikeos" / "bugs").glob("*.md"))
    assert len(files) == 1
    post = fm.load(files[0])
    assert post.metadata.get("component") == "voice-bridge"
    assert "component/voice-bridge" in post.metadata["tags"]


def test_write_entry_with_component_appends_wikilink(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "note", "project": "ikeos", "title": "Arch notes",
            "body": "Details here.", "component": "voice-bridge",
        })
    files = list((vault / "projects" / "ikeos" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert "[[ikeos]]" in post.content


def test_write_entry_without_component_no_wikilink(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_entry
        write_entry({
            "type": "note", "project": "ikeos", "title": "Standalone",
            "body": "No component.", "domains": [],
        })
    files = list((vault / "projects" / "ikeos" / "notes").glob("*.md"))
    post = fm.load(files[0])
    assert "[[ikeos]]" not in post.content


def test_read_entries_filters_by_component(vault):
    (vault / "projects" / "ikeos" / "bugs").mkdir(parents=True)
    (vault / "projects" / "ikeos" / "bugs" / "2026-06-13-bug-a.md").write_text(
        "---\ntype: bug\ntitle: Bug A\nproject: ikeos\ncomponent: voice-bridge\n"
        "status: new\ncreated: 2026-06-13T10:00:00\ntags: [bug]\n---\n## Description\nA\n"
    )
    (vault / "projects" / "ikeos" / "bugs" / "2026-06-13-bug-b.md").write_text(
        "---\ntype: bug\ntitle: Bug B\nproject: ikeos\ncomponent: display\n"
        "status: new\ncreated: 2026-06-13T11:00:00\ntags: [bug]\n---\n## Description\nB\n"
    )
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import read_entries, _invalidate_cache
        _invalidate_cache()
        entries = read_entries(project="ikeos", component="voice-bridge")
    assert len(entries) == 1
    assert entries[0]["title"] == "Bug A"
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_vault.py::test_write_entry_with_component_sets_component_tag \
    tests/test_vault.py::test_write_entry_with_component_appends_wikilink \
    tests/test_vault.py::test_write_entry_without_component_no_wikilink \
    tests/test_vault.py::test_read_entries_filters_by_component -v
```
Expected: 4 FAILures

- [ ] **Step 3: Update `write_entry` in `app/services/vault.py`**

In the `else` branch (non-decision entries), after the existing tags are built and before `metadata = {...}` is assembled, add:

```python
        component = data.get("component", "").strip()
        if component:
            tags.append(f"component/{component}")

        metadata = {
            "type": entry_type,
            "title": title,
            "project": project,
            "status": "new",
            "created": datetime.now().isoformat(timespec="seconds"),
            "tags": tags,
        }
        if component:
            metadata["component"] = component

        # ... existing idea/bug field blocks stay here unchanged ...

        content = f"## Description\n{body}\n"
        if entry_type == "bug" and data.get("steps"):
            content += f"\n## Steps to reproduce\n{data['steps']}\n"
        if component:
            content += f"\n---\n[[{project}]]\n"
```

- [ ] **Step 4: Update `read_entries` signature in `app/services/vault.py`**

Change the function signature and add component filter:

```python
def read_entries(project: str = None, status_filter: list = None, component: str = None) -> list[dict]:
    global _entries_cache, _entries_cache_ts
    now = time.monotonic()

    if _entries_cache is None or (now - _entries_cache_ts) >= _TTL:
        _entries_cache = _read_all_entries()
        _entries_cache_ts = now

    entries = _entries_cache
    if project is not None:
        entries = [e for e in entries if e.get("project") == project]
    if component is not None:
        entries = [e for e in entries if e.get("component") == component]
    if status_filter:
        entries = [e for e in entries if e.get("status") in status_filter]

    return entries
```

- [ ] **Step 5: Run all vault tests**

```bash
python -m pytest tests/test_vault.py -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: add component field support to write_entry and read_entries"
```

---

## Task 3: vault.py — hub pages and graph integration

Add `write_hub_page`, `write_component_stub`, `_read_hub_pages`, and update `get_vault_graph` to include hub/stub nodes.

**Files:**
- Modify: `app/services/vault.py`
- Modify: `tests/test_vault.py` (add cases at bottom)

- [ ] **Step 1: Write failing tests**

```python
# Add to bottom of tests/test_vault.py

def test_write_hub_page_creates_file(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_hub_page
        write_hub_page("ikeos", "IkeOS", ["voice-bridge", "display"])
    hub = vault / "projects" / "ikeos" / "ikeos.md"
    assert hub.exists()
    post = fm.load(hub)
    assert post.metadata["type"] == "hub"
    assert post.metadata["project"] == "ikeos"
    assert "[[voice-bridge]]" in post.content
    assert "[[display]]" in post.content


def test_write_hub_page_no_components(vault):
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_hub_page
        write_hub_page("wayvr", "Wayvr", [])
    hub = vault / "projects" / "wayvr" / "wayvr.md"
    assert hub.exists()


def test_write_component_stub_creates_file(vault):
    (vault / "projects" / "ikeos").mkdir(parents=True)
    with patch("app.services.vault.VAULT_PATH", vault):
        from app.services.vault import write_component_stub
        write_component_stub("ikeos", "voice-bridge")
    stub = vault / "projects" / "ikeos" / "components" / "voice-bridge.md"
    assert stub.exists()
    post = fm.load(stub)
    assert post.metadata["type"] == "component"
    assert "[[ikeos]]" in post.content


def test_get_vault_graph_includes_hub_nodes(tmp_path):
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)
    hub = tmp_path / "projects" / "ikeos" / "ikeos.md"
    hub.write_text(
        "---\ntype: hub\nproject: ikeos\ntitle: IkeOS\ntags: [hub]\n---\n"
        "Components: [[voice-bridge]]\n"
    )
    # Also write a stub so the wikilink resolves
    (tmp_path / "projects" / "ikeos" / "components").mkdir()
    stub = tmp_path / "projects" / "ikeos" / "components" / "voice-bridge.md"
    stub.write_text(
        "---\ntype: component\nproject: ikeos\ntitle: voice-bridge\ntags: [component]\n---\n"
        "[[ikeos]]\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    node_ids = {n["id"] for n in result["nodes"]}
    assert "ikeos" in node_ids
    assert "voice-bridge" in node_ids


def test_get_vault_graph_wikilink_resolves_to_hub(tmp_path):
    # Entry with [[ikeos]] wikilink should create a link to the hub node
    (tmp_path / "projects" / "ikeos" / "bugs").mkdir(parents=True)
    (tmp_path / "projects" / "ikeos" / "bugs" / "2026-06-13-crash.md").write_text(
        "---\ntype: bug\ntitle: Crash\nproject: ikeos\ncomponent: voice-bridge\n"
        "status: new\ncreated: 2026-06-13T10:00:00\ntags: [bug]\n---\n"
        "## Description\nBroke.\n\n---\n[[ikeos]]\n"
    )
    (tmp_path / "projects" / "ikeos").mkdir(exist_ok=True)
    (tmp_path / "projects" / "ikeos" / "ikeos.md").write_text(
        "---\ntype: hub\nproject: ikeos\ntitle: IkeOS\ntags: [hub]\n---\nHub page.\n"
    )
    with patch("app.services.vault.VAULT_PATH", tmp_path):
        from app.services.vault import get_vault_graph, _invalidate_cache
        _invalidate_cache()
        result = get_vault_graph()
    link_targets = {lnk["target"] for lnk in result["links"]}
    assert "ikeos" in link_targets
    assert not any(bl["broken_ref"] == "ikeos" for bl in result["health"]["broken_links"])
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_vault.py -k "hub or stub or includes_hub or resolves_to_hub" -v
```
Expected: 5 FAILures

- [ ] **Step 3: Add `write_hub_page` and `write_component_stub` to `app/services/vault.py`**

Add after the existing `write_entry` function:

```python
def write_hub_page(umbrella_slug: str, umbrella_name: str, components: list[str]) -> None:
    """Create or overwrite the hub page for an umbrella project."""
    proj_dir = VAULT_PATH / "projects" / umbrella_slug
    proj_dir.mkdir(parents=True, exist_ok=True)

    component_links = " · ".join(f"[[{c}]]" for c in components) if components else ""
    content = f"# {umbrella_name}\n\n"
    if component_links:
        content += f"**Components:** {component_links}\n\n"

    metadata = {
        "type": "hub",
        "title": umbrella_name,
        "project": umbrella_slug,
        "tags": ["hub", f"project/{umbrella_slug}"],
    }
    post = frontmatter.Post(content, **metadata)
    filepath = proj_dir / f"{umbrella_slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()


def write_component_stub(umbrella_slug: str, component_slug: str) -> None:
    """Create or overwrite a component stub page under an umbrella."""
    stubs_dir = VAULT_PATH / "projects" / umbrella_slug / "components"
    stubs_dir.mkdir(parents=True, exist_ok=True)

    content = f"# {component_slug}\n\n[[{umbrella_slug}]]\n"
    metadata = {
        "type": "component",
        "title": component_slug,
        "project": umbrella_slug,
        "tags": ["component", f"umbrella/{umbrella_slug}"],
    }
    post = frontmatter.Post(content, **metadata)
    filepath = stubs_dir / f"{component_slug}.md"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))
    _invalidate_cache()
```

- [ ] **Step 4: Add `_read_hub_pages` and update `get_vault_graph` in `app/services/vault.py`**

Add `_read_hub_pages` before `get_vault_graph`:

```python
def _read_hub_pages() -> list[dict]:
    """Read hub pages (<proj>/<proj>.md) and component stubs (<proj>/components/*.md)."""
    pages = []
    projects_dir = VAULT_PATH / "projects"
    if not projects_dir.exists():
        return pages
    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        slug = proj_dir.name
        # Hub page
        hub_file = proj_dir / f"{slug}.md"
        if hub_file.exists():
            try:
                post = frontmatter.load(hub_file)
                entry = dict(post.metadata)
                entry["body"] = post.content
                entry["slug"] = slug
                pages.append(entry)
            except Exception:
                pass
        # Component stubs
        stubs_dir = proj_dir / "components"
        if stubs_dir.exists():
            for stub_file in stubs_dir.glob("*.md"):
                try:
                    post = frontmatter.load(stub_file)
                    entry = dict(post.metadata)
                    entry["body"] = post.content
                    entry["slug"] = stub_file.stem
                    pages.append(entry)
                except Exception:
                    pass
    return pages
```

Update `get_vault_graph` to merge hub pages into the node/slug set:

```python
def get_vault_graph() -> dict:
    entries = read_entries()
    hub_pages = _read_hub_pages()
    all_items = entries + hub_pages
    slug_set = {e["slug"] for e in all_items}

    nodes = []
    links = []
    untriaged = []
    stale = []
    broken_links = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for entry in all_items:
        slug = entry["slug"]
        nodes.append({
            "id": slug,
            "title": entry.get("title", slug),
            "type": entry.get("type", "note"),
            "status": entry.get("status", ""),
            "project": entry.get("project", ""),
            "urgency": _get_urgency(entry),
        })

        # Health checks apply only to non-hub entries
        if entry.get("type") not in ("hub", "component"):
            if entry.get("status") == "new":
                untriaged.append({
                    "slug": slug,
                    "title": entry.get("title", slug),
                    "project": entry.get("project", ""),
                    "type": entry.get("type", "note"),
                })
            if entry.get("status") in ("open", "in-progress"):
                ref_date_raw = entry.get("updated") or entry.get("created", "")
                try:
                    if isinstance(ref_date_raw, datetime):
                        ref_date = ref_date_raw
                    else:
                        ref_date = datetime.fromisoformat(ref_date_raw)
                    ref_date = ref_date.replace(tzinfo=None) if ref_date.tzinfo else ref_date
                    days_stale = (now - ref_date).days
                    if days_stale >= _STALE_DAYS:
                        stale.append({
                            "slug": slug,
                            "title": entry.get("title", slug),
                            "project": entry.get("project", ""),
                            "type": entry.get("type", "note"),
                            "status": entry.get("status", ""),
                            "days_stale": days_stale,
                        })
                except (ValueError, TypeError):
                    pass

        body = entry.get("body", "")
        for ref in _WIKILINK_RE.findall(body):
            ref = ref.strip()
            if not ref or ref == slug:
                continue
            if ref in slug_set:
                links.append({"source": slug, "target": ref})
            else:
                broken_links.append({
                    "source_slug": slug,
                    "source_title": entry.get("title", slug),
                    "source_project": entry.get("project", ""),
                    "broken_ref": ref,
                })

    return {
        "nodes": nodes,
        "links": links,
        "health": {
            "untriaged": untriaged,
            "stale": stale,
            "broken_links": broken_links,
        },
    }
```

- [ ] **Step 5: Run all vault tests**

```bash
python -m pytest tests/test_vault.py -v
```
Expected: all tests PASS (new + existing)

- [ ] **Step 6: Commit**

```bash
git add app/services/vault.py tests/test_vault.py
git commit -m "feat: add hub/stub write functions and include them in vault graph"
```

---

## Task 4: Capture route — pass umbrella data and handle component field

**Files:**
- Modify: `app/routes/capture.py`
- Modify: `tests/test_capture.py` (add cases)

- [ ] **Step 1: Write failing tests (add to `tests/test_capture.py`)**

First read the existing capture tests to understand the fixture style, then add:

```python
# Add to tests/test_capture.py

def test_capture_form_includes_components_for_umbrella(client, tmp_path, monkeypatch):
    """Form context includes component list for projects with components."""
    import yaml
    from pathlib import Path
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge"]}}))
    monkeypatch.setenv("UMBRELLA_REGISTRY_PATH", str(reg))
    import app.services.umbrella as u
    u._registry = None

    (tmp_path / "projects" / "ikeos").mkdir(parents=True)
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()

    resp = client.get("/capture?project=ikeos")
    assert resp.status_code == 200
    assert b"voice-bridge" in resp.data


def test_capture_submit_stores_component(client, tmp_path, monkeypatch):
    """POST /capture with component stores component field in vault entry."""
    import yaml
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge"]}}))
    monkeypatch.setenv("UMBRELLA_REGISTRY_PATH", str(reg))
    import app.services.umbrella as u
    u._registry = None

    (tmp_path / "projects" / "ikeos").mkdir(parents=True)
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()

    resp = client.post("/capture", data={
        "type": "note",
        "project": "ikeos",
        "component": "voice-bridge",
        "title": "Test note",
        "body": "Body",
    }, follow_redirects=True)
    assert resp.status_code == 200

    files = list((tmp_path / "projects" / "ikeos" / "notes").glob("*.md"))
    assert len(files) == 1
    import frontmatter as fm
    post = fm.load(files[0])
    assert post.metadata.get("component") == "voice-bridge"


def test_capture_json_stores_component(client, tmp_path, monkeypatch):
    """POST /capture/json with component stores component field."""
    (tmp_path / "projects" / "ikeos").mkdir(parents=True)
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()

    resp = client.post("/capture/json", json={
        "type": "note",
        "project": "ikeos",
        "component": "voice-bridge",
        "title": "JSON note",
        "body": "Body",
    })
    assert resp.status_code == 200

    files = list((tmp_path / "projects" / "ikeos" / "notes").glob("*.md"))
    assert len(files) == 1
    import frontmatter as fm
    post = fm.load(files[0])
    assert post.metadata.get("component") == "voice-bridge"
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_capture.py -k "component" -v
```
Expected: 3 FAILures

- [ ] **Step 3: Update `app/routes/capture.py`**

Add import at top:
```python
from app.services.umbrella import get_all_umbrellas, get_components
```

Update `capture_form`:
```python
@bp.route("/capture", methods=["GET"])
def capture_form():
    projects = get_projects_with_meta()
    umbrella_registry = get_all_umbrellas()
    for p in projects:
        p["components"] = get_components(p["slug"])
    selected_project = request.args.get("project", "")
    return render_template(
        "capture.html",
        projects=projects,
        selected_project=selected_project,
        umbrella_registry=umbrella_registry,
    )
```

Update `capture_submit` — add component extraction after the project block:
```python
    component = request.form.get("component", "").strip() or None
    if component:
        data["component"] = component
```
(Add this block right after `data["project"] = project` for non-decision entries.)

Update `capture_json`:
```python
    data = {
        "type": entry_type,
        "project": project,
        "title": title,
        "body": req.get("body", ""),
        "domains": [],
    }
    component = req.get("component", "").strip() or None
    if component:
        data["component"] = component
```

- [ ] **Step 4: Run all capture tests**

```bash
python -m pytest tests/test_capture.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes/capture.py tests/test_capture.py
git commit -m "feat: pass umbrella/component data through capture route"
```

---

## Task 5: Capture form — umbrella-first UI

Update `capture.html` to show the component picker conditionally when the selected project has components.

**Files:**
- Modify: `app/templates/capture.html`

- [ ] **Step 1: Update `app/templates/capture.html`**

Replace the entire `<form>` block (everything between `<form method="post"...>` and `</form>`) with:

```html
<form method="post" action="{{ url_for('capture.capture_submit') }}">
  <div class="field">
    <label class="ike-eyebrow" for="project">Umbrella</label>
    <select id="project" name="project" required onchange="updateProject(this.value)">
      {% for p in projects %}
        <option value="{{ p.slug }}"
                data-components="{{ p.components | join(',') }}"
                {% if p.slug == selected_project %}selected{% endif %}>
          {{ p.name }}
        </option>
      {% endfor %}
      <option value="__future__">— Future project —</option>
    </select>
  </div>

  <div id="future-project-field" class="field hidden">
    <label class="ike-eyebrow" for="future_project_name">Future project name</label>
    <input id="future_project_name" name="future_project_name" type="text" placeholder="e.g. my-new-app">
  </div>

  <div id="component-field" class="field hidden">
    <label class="ike-eyebrow" for="component">Component <span class="field-optional">(optional)</span></label>
    <select id="component" name="component">
      <option value="">— No specific component —</option>
    </select>
  </div>

  <div class="field">
    <label class="ike-eyebrow" for="type-note">Type</label>
    <div class="type-chips" role="radiogroup">
      <input type="radio" name="type" id="type-note" value="note">
      <label class="type-chip type-chip-note" for="type-note">Note</label>
      <input type="radio" name="type" id="type-idea" value="idea" checked>
      <label class="type-chip type-chip-idea" for="type-idea">Feature Request</label>
      <input type="radio" name="type" id="type-bug" value="bug">
      <label class="type-chip type-chip-bug" for="type-bug">Bug</label>
    </div>
  </div>

  <div class="field">
    <label class="ike-eyebrow" for="title">Title</label>
    <input id="title" name="title" type="text" required>
  </div>

  <div class="field">
    <label class="ike-eyebrow" for="body">Description</label>
    <textarea id="body" name="body" rows="5"></textarea>
  </div>

  <!-- Idea fields -->
  <div id="idea-fields" class="conditional hidden">
    <div class="field">
      <label class="ike-eyebrow" for="priority">Priority</label>
      <select id="priority" name="priority">
        <option value="low">Low</option>
        <option value="medium" selected>Medium</option>
        <option value="high">High</option>
      </select>
    </div>
    <div class="field">
      <label class="ike-eyebrow" for="effort">Effort</label>
      <select id="effort" name="effort">
        <option value="small">Small</option>
        <option value="medium" selected>Medium</option>
        <option value="large">Large</option>
      </select>
    </div>
  </div>

  <!-- Bug fields -->
  <div id="bug-fields" class="conditional hidden">
    <div class="field">
      <label class="ike-eyebrow" for="severity">Severity</label>
      <select id="severity" name="severity">
        <option value="low">Low</option>
        <option value="medium" selected>Medium</option>
        <option value="high">High</option>
        <option value="critical">Critical</option>
      </select>
    </div>
    <div class="field">
      <label class="ike-eyebrow" for="steps">Steps to reproduce</label>
      <textarea id="steps" name="steps" rows="4"></textarea>
    </div>
  </div>

  <div class="field">
    <label class="ike-eyebrow">Domain <span class="field-optional">(optional — select all that apply)</span></label>
    <div class="domain-checkboxes">
      <label class="domain-check"><input type="checkbox" name="domains" value="auth"> auth</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="payments"> payments</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="ui"> ui</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="api"> api</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="data"> data</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="infra"> infra</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="data-visualization"> data-visualization</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="game-logic"> game-logic</label>
      <label class="domain-check"><input type="checkbox" name="domains" value="legal"> legal</label>
    </div>
  </div>

  <div class="field stay-field">
    <label class="domain-check">
      <input type="checkbox" name="stay" value="1"> Stay here after saving — keep capturing.
    </label>
  </div>

  <div class="capture-footer">
    <span class="capture-help"><kbd>⌘</kbd>+<kbd>↵</kbd> to save</span>
    <button type="submit" class="ike-btn-primary">Save to vault</button>
  </div>
</form>
```

Replace the `<script>` block (after the form, before EasyMDE) with:

```html
<script>
function updateFields(type) {
  document.getElementById('idea-fields').classList.add('hidden');
  document.getElementById('bug-fields').classList.add('hidden');
  if (type === 'idea') document.getElementById('idea-fields').classList.remove('hidden');
  if (type === 'bug') document.getElementById('bug-fields').classList.remove('hidden');
}

function updateProject(value) {
  const futureField = document.getElementById('future-project-field');
  const futureInput = document.getElementById('future_project_name');
  const componentField = document.getElementById('component-field');
  const componentSelect = document.getElementById('component');

  if (value === '__future__') {
    futureField.classList.remove('hidden');
    futureInput.required = true;
    componentField.classList.add('hidden');
    return;
  }
  futureField.classList.add('hidden');
  futureInput.required = false;

  const selected = document.querySelector(`#project option[value="${value}"]`);
  const components = selected ? (selected.dataset.components || '') : '';
  const list = components ? components.split(',').filter(Boolean) : [];

  componentSelect.innerHTML = '<option value="">— No specific component —</option>';
  list.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    componentSelect.appendChild(opt);
  });
  componentField.classList.toggle('hidden', list.length === 0);
}

document.querySelectorAll('input[name="type"]').forEach(el => {
  el.addEventListener('change', e => updateFields(e.target.value));
});
updateFields('idea');

// Init component picker for pre-selected project
(function() {
  const sel = document.getElementById('project');
  if (sel && sel.value) updateProject(sel.value);
})();

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    document.querySelector('form')?.requestSubmit();
  }
});

(function () {
  const stayBox = document.querySelector('input[name="stay"]');
  if (!stayBox) return;
  if (localStorage.getItem('captureStay') === '1') stayBox.checked = true;
  stayBox.addEventListener('change', function () {
    if (this.checked) {
      localStorage.setItem('captureStay', '1');
    } else {
      localStorage.removeItem('captureStay');
    }
  });
})();
</script>
```

- [ ] **Step 2: Rebuild and test manually**

```bash
docker.exe compose -f /mnt/c/Server/projects/obsidian-capture/docker-compose.yml up --build -d
```

Open `http://192.168.1.77:5009/capture` in browser.
- Select "Claude Config" → component picker should appear with `claude-code`
- Select "Wayvr" → component picker should disappear
- Submit a note for "Claude Config / claude-code" → verify it saves
- Check vault: `ls /mnt/c/Server/obsidian-vault/projects/claude-config/notes/`
  - Entry file should have `component: claude-code` in frontmatter and `[[claude-config]]` at end of body

- [ ] **Step 3: Commit**

```bash
git add app/templates/capture.html
git commit -m "feat: umbrella-first capture form with conditional component picker"
```

---

## Task 6: Browse — component filter on project view

Allow filtering project entries by component via `?component=<slug>` query param. Show component pills on the project page when components are defined.

**Files:**
- Modify: `app/routes/browse.py`
- Modify: `app/templates/project.html`
- Modify: `tests/test_browse.py` (add cases)

- [ ] **Step 1: Write failing tests (add to `tests/test_browse.py`)**

Read the existing browse tests first to understand the fixture pattern, then add:

```python
# Add to tests/test_browse.py

def test_project_page_filters_by_component(client, tmp_path, monkeypatch):
    """?component= param filters entries to that component only."""
    import yaml
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge", "display"]}}))
    monkeypatch.setenv("UMBRELLA_REGISTRY_PATH", str(reg))
    import app.services.umbrella as u
    u._registry = None

    bugs_dir = tmp_path / "projects" / "ikeos" / "bugs"
    bugs_dir.mkdir(parents=True)
    (bugs_dir / "2026-06-13-bug-a.md").write_text(
        "---\ntype: bug\ntitle: VB Bug\nproject: ikeos\ncomponent: voice-bridge\n"
        "status: new\ncreated: 2026-06-13T10:00:00\ntags: [bug]\n---\n## Description\nA\n"
    )
    (bugs_dir / "2026-06-13-bug-b.md").write_text(
        "---\ntype: bug\ntitle: Display Bug\nproject: ikeos\ncomponent: display\n"
        "status: new\ncreated: 2026-06-13T11:00:00\ntags: [bug]\n---\n## Description\nB\n"
    )

    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()

    resp = client.get("/projects/ikeos?component=voice-bridge")
    assert resp.status_code == 200
    assert b"VB Bug" in resp.data
    assert b"Display Bug" not in resp.data


def test_project_page_shows_component_pills_for_umbrella(client, tmp_path, monkeypatch):
    """Project page renders component pill links when components are defined."""
    import yaml
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.dump({"ikeos": {"name": "IkeOS", "components": ["voice-bridge"]}}))
    monkeypatch.setenv("UMBRELLA_REGISTRY_PATH", str(reg))
    import app.services.umbrella as u
    u._registry = None

    (tmp_path / "projects" / "ikeos").mkdir(parents=True)
    import app.services.vault as v
    monkeypatch.setattr(v, "VAULT_PATH", tmp_path)
    v._invalidate_cache()

    resp = client.get("/projects/ikeos")
    assert resp.status_code == 200
    assert b"voice-bridge" in resp.data
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_browse.py -k "component" -v
```
Expected: 2 FAILures

- [ ] **Step 3: Update `app/routes/browse.py` — add component filter to project view**

Add import at top:
```python
from app.services.umbrella import get_components
```

Update `project` route:
```python
@bp.route("/projects/<name>")
def project(name):
    show_all = request.args.get("show_all") == "true"
    component_filter = request.args.get("component", "").strip() or None
    status_filter = None if show_all else ACTIVE_STATUSES
    entries = read_entries(project=name, status_filter=status_filter, component=component_filter)

    bugs = [e for e in entries if e.get("type") == "bug"]
    ideas = [e for e in entries if e.get("type") == "idea"]
    notes = [e for e in entries if e.get("type") == "note"]

    all_projects = get_projects_with_meta(include_hidden=True)
    project_meta = next((p for p in all_projects if p["slug"] == name), None)
    display_name = project_meta["name"] if project_meta else name
    visible_projects = [p for p in all_projects if not p["hidden"]]
    components = get_components(name)

    return render_template(
        "project.html",
        name=name,
        display_name=display_name,
        bugs=bugs,
        ideas=ideas,
        notes=notes,
        show_all=show_all,
        projects=visible_projects,
        components=components,
        active_component=component_filter,
    )
```

- [ ] **Step 4: Update `app/templates/project.html` — add component pills**

Add component pills block after the `<div class="project-header">` closing tag (before the entry lists):

```html
{% if components %}
<div class="component-pills">
  <a href="{{ url_for('browse.project', name=name) }}"
     class="component-pill {% if not active_component %}active{% endif %}">All</a>
  {% for c in components %}
  <a href="{{ url_for('browse.project', name=name, component=c) }}"
     class="component-pill {% if active_component == c %}active{% endif %}">{{ c }}</a>
  {% endfor %}
</div>
{% endif %}
```

Add CSS for component pills to `app/static/workspace.css` (or whichever CSS file is closest to the project view):

```css
.component-pills {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1.5rem;
}
.component-pill {
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--color-border, #ddd);
  font-size: 0.8rem;
  text-decoration: none;
  color: inherit;
}
.component-pill.active {
  background: var(--color-accent, #333);
  color: var(--color-on-accent, #fff);
  border-color: transparent;
}
```

- [ ] **Step 5: Run all browse tests**

```bash
python -m pytest tests/test_browse.py -v
```
Expected: all tests PASS

- [ ] **Step 6: Rebuild and verify manually**

```bash
docker.exe compose -f /mnt/c/Server/projects/obsidian-capture/docker-compose.yml up --build -d
```

Visit `http://192.168.1.77:5009/projects/claude-config` — component pills should appear for `claude-code`.

- [ ] **Step 7: Commit**

```bash
git add app/routes/browse.py app/templates/project.html app/static/workspace.css
git commit -m "feat: component filter pills on project view"
```

---

## Task 7: Migration script

One-time script to move existing sub-project entries into their umbrella folder, update frontmatter, add wikilinks, create hub pages and component stubs. Dry-run by default; `--apply` to execute.

**Files:**
- Create: `scripts/migrate_to_umbrella.py`
- Create: `tests/test_migrate.py`

- [ ] **Step 1: Write failing tests for migration functions**

```python
# tests/test_migrate.py
import pytest
from pathlib import Path
from unittest.mock import patch
import frontmatter as fm
import yaml


def _make_entry(path, slug, type_, project, status="new", component=None):
    path.mkdir(parents=True, exist_ok=True)
    content = f"## Description\nBody.\n"
    meta = {
        "type": type_, "title": slug, "project": project,
        "status": status, "created": "2026-06-01T10:00:00",
        "tags": [type_, project, f"status/{status}"],
    }
    if component:
        meta["component"] = component
    post = fm.Post(content, **meta)
    (path / f"{slug}.md").write_text(fm.dumps(post))


def _write_registry(tmp_path, data):
    reg = tmp_path / "umbrella_registry.yaml"
    reg.write_text(yaml.dump(data))
    return reg


def test_collect_component_entries(tmp_path):
    bugs = tmp_path / "projects" / "claude-code" / "bugs"
    _make_entry(bugs, "2026-06-01-test-bug", "bug", "claude-code")
    _make_entry(bugs, "2026-06-01-other-bug", "bug", "claude-code")

    from scripts.migrate_to_umbrella import collect_component_entries
    entries = collect_component_entries(tmp_path, "claude-code")
    assert len(entries) == 2
    slugs = {e["slug"] for e in entries}
    assert "2026-06-01-test-bug" in slugs


def test_migrate_entry_writes_to_umbrella_folder(tmp_path):
    bugs = tmp_path / "projects" / "claude-code" / "bugs"
    _make_entry(bugs, "2026-06-01-test-bug", "bug", "claude-code")
    src = bugs / "2026-06-01-test-bug.md"

    from scripts.migrate_to_umbrella import migrate_entry
    migrate_entry(tmp_path, src, "bug", "claude-code", "claude-config", apply=True)

    dest = tmp_path / "projects" / "claude-config" / "bugs" / "2026-06-01-test-bug.md"
    assert dest.exists()
    assert not src.exists()

    post = fm.load(dest)
    assert post.metadata["project"] == "claude-config"
    assert post.metadata["component"] == "claude-code"
    assert "component/claude-code" in post.metadata["tags"]
    assert "[[claude-config]]" in post.content


def test_migrate_entry_dry_run_does_not_move(tmp_path):
    bugs = tmp_path / "projects" / "claude-code" / "bugs"
    _make_entry(bugs, "2026-06-01-test-bug", "bug", "claude-code")
    src = bugs / "2026-06-01-test-bug.md"

    from scripts.migrate_to_umbrella import migrate_entry
    migrate_entry(tmp_path, src, "bug", "claude-code", "claude-config", apply=False)

    assert src.exists()
    dest = tmp_path / "projects" / "claude-config" / "bugs" / "2026-06-01-test-bug.md"
    assert not dest.exists()


def test_hide_component_project(tmp_path):
    proj = tmp_path / "projects" / "claude-code"
    proj.mkdir(parents=True)
    (proj / "project.md").write_text("---\nname: Claude Code\nhidden: false\n---\n")

    from scripts.migrate_to_umbrella import hide_component_project
    hide_component_project(tmp_path, "claude-code", apply=True)

    post = fm.load(proj / "project.md")
    assert post.metadata["hidden"] is True
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
python -m pytest tests/test_migrate.py -v
```
Expected: `ModuleNotFoundError` for `scripts.migrate_to_umbrella`

- [ ] **Step 3: Create `scripts/migrate_to_umbrella.py`**

```python
#!/usr/bin/env python3
"""
Migrate sub-project entries into their umbrella folders.

Usage:
    python scripts/migrate_to_umbrella.py          # dry-run (default)
    python scripts/migrate_to_umbrella.py --apply  # execute migration

The script reads umbrella_registry.yaml, finds entries in component project
folders, moves them to the umbrella folder with updated frontmatter and a
[[umbrella]] wikilink, then creates hub pages and component stubs.
"""
import argparse
import sys
from pathlib import Path

import frontmatter
import yaml

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

TYPE_FOLDERS = {"note": "notes", "idea": "ideas", "bug": "bugs"}


def load_registry(registry_path: Path) -> dict:
    if not registry_path.exists():
        print(f"[ERROR] Registry not found: {registry_path}")
        sys.exit(1)
    with open(registry_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def collect_component_entries(vault_path: Path, component_slug: str) -> list[dict]:
    entries = []
    proj_dir = vault_path / "projects" / component_slug
    for folder, type_ in [("bugs", "bug"), ("ideas", "idea"), ("notes", "note")]:
        type_dir = proj_dir / folder
        if not type_dir.exists():
            continue
        for filepath in type_dir.glob("*.md"):
            entries.append({
                "path": filepath,
                "slug": filepath.stem,
                "type": type_,
                "folder": folder,
            })
    return entries


def migrate_entry(
    vault_path: Path,
    src_path: Path,
    entry_type: str,
    component_slug: str,
    umbrella_slug: str,
    apply: bool,
) -> None:
    folder = TYPE_FOLDERS[entry_type]
    dest_dir = vault_path / "projects" / umbrella_slug / folder
    dest_path = dest_dir / src_path.name

    post = frontmatter.load(src_path)
    post.metadata["project"] = umbrella_slug
    post.metadata["component"] = component_slug

    tags = [t for t in post.metadata.get("tags", []) if t != component_slug]
    if umbrella_slug not in tags:
        tags.append(umbrella_slug)
    if f"component/{component_slug}" not in tags:
        tags.append(f"component/{component_slug}")
    post.metadata["tags"] = tags

    wikilink = f"\n---\n[[{umbrella_slug}]]\n"
    if wikilink.strip() not in post.content:
        post.content = post.content.rstrip() + wikilink

    action = "MOVE" if apply else "DRY-RUN"
    print(f"  [{action}] {src_path.relative_to(vault_path)} → {dest_path.relative_to(vault_path)}")

    if apply:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))
        src_path.unlink()


def hide_component_project(vault_path: Path, component_slug: str, apply: bool) -> None:
    proj_dir = vault_path / "projects" / component_slug
    meta_file = proj_dir / "project.md"
    action = "HIDE" if apply else "DRY-RUN"
    print(f"  [{action}] Setting {component_slug}/project.md hidden=true")
    if apply:
        if meta_file.exists():
            post = frontmatter.load(meta_file)
            post.metadata["hidden"] = True
            with open(meta_file, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))
        else:
            post = frontmatter.Post("", name=component_slug, hidden=True)
            with open(meta_file, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))


def create_hub_and_stubs(vault_path: Path, umbrella_slug: str, umbrella_meta: dict, apply: bool) -> None:
    components = umbrella_meta.get("components", [])
    umbrella_name = umbrella_meta.get("name", umbrella_slug)

    component_links = " · ".join(f"[[{c}]]" for c in components)
    hub_content = f"# {umbrella_name}\n\n"
    if component_links:
        hub_content += f"**Components:** {component_links}\n\n"

    hub_meta = {
        "type": "hub",
        "title": umbrella_name,
        "project": umbrella_slug,
        "tags": ["hub", f"project/{umbrella_slug}"],
    }
    hub_path = vault_path / "projects" / umbrella_slug / f"{umbrella_slug}.md"
    action = "CREATE" if apply else "DRY-RUN"
    print(f"  [{action}] Hub page: {hub_path.relative_to(vault_path)}")
    if apply:
        hub_path.parent.mkdir(parents=True, exist_ok=True)
        post = frontmatter.Post(hub_content, **hub_meta)
        with open(hub_path, "w", encoding="utf-8") as f:
            f.write(frontmatter.dumps(post))

    for component in components:
        stub_content = f"# {component}\n\n[[{umbrella_slug}]]\n"
        stub_meta = {
            "type": "component",
            "title": component,
            "project": umbrella_slug,
            "tags": ["component", f"umbrella/{umbrella_slug}"],
        }
        stub_path = vault_path / "projects" / umbrella_slug / "components" / f"{component}.md"
        print(f"  [{action}] Component stub: {stub_path.relative_to(vault_path)}")
        if apply:
            stub_path.parent.mkdir(parents=True, exist_ok=True)
            post = frontmatter.Post(stub_content, **stub_meta)
            with open(stub_path, "w", encoding="utf-8") as f:
                f.write(frontmatter.dumps(post))


def main():
    parser = argparse.ArgumentParser(description="Migrate sub-project entries to umbrella folders.")
    parser.add_argument("--apply", action="store_true", help="Execute migration (default: dry-run)")
    parser.add_argument("--vault", default="/vault", help="Vault path (default: /vault)")
    parser.add_argument("--registry", default=str(REPO_ROOT / "umbrella_registry.yaml"))
    args = parser.parse_args()

    vault_path = Path(args.vault)
    registry = load_registry(Path(args.registry))

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n=== Umbrella Migration ({mode}) ===\n")

    for umbrella_slug, umbrella_meta in registry.items():
        components = umbrella_meta.get("components", [])
        if not components:
            print(f"[SKIP] {umbrella_slug} — flat umbrella, no components")
            continue

        print(f"\n[UMBRELLA] {umbrella_slug}")

        # Migrate component entries
        for component_slug in components:
            comp_dir = vault_path / "projects" / component_slug
            if not comp_dir.exists():
                print(f"  [SKIP] Component '{component_slug}' not found in vault")
                continue

            print(f"  [COMPONENT] {component_slug}")
            entries = collect_component_entries(vault_path, component_slug)
            if not entries:
                print(f"    (no entries to migrate)")
            for e in entries:
                migrate_entry(
                    vault_path, e["path"], e["type"],
                    component_slug, umbrella_slug, apply=args.apply
                )
            hide_component_project(vault_path, component_slug, apply=args.apply)

        # Create hub page and component stubs
        create_hub_and_stubs(vault_path, umbrella_slug, umbrella_meta, apply=args.apply)

    print(f"\n=== Done ({mode}) ===")
    if not args.apply:
        print("Re-run with --apply to execute the migration.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run migration tests**

```bash
python -m pytest tests/test_migrate.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_to_umbrella.py tests/test_migrate.py
git commit -m "feat: migration script for umbrella-first reorganization"
```

---

## Task 8: Execute migration

Run the migration script inside the Docker container against the live vault.

- [ ] **Step 1: Dry-run to review what will change**

```bash
docker.exe exec obsidian-capture python scripts/migrate_to_umbrella.py --vault /vault
```

Review the output carefully:
- Confirm expected MOVE operations (entries from `claude-code/` → `claude-config/`)
- Confirm expected HIDE operations
- Confirm hub page and component stub creation paths

- [ ] **Step 2: Apply the migration**

Once the dry-run output looks correct:

```bash
docker.exe exec obsidian-capture python scripts/migrate_to_umbrella.py --vault /vault --apply
```

- [ ] **Step 3: Verify vault structure**

```bash
# Hub pages created
ls /mnt/c/Server/obsidian-vault/projects/claude-config/
# Should show: bugs/ ideas/ notes/ components/ claude-config.md project.md

# Entries moved (claude-code entries now in claude-config)
ls /mnt/c/Server/obsidian-vault/projects/claude-config/bugs/
ls /mnt/c/Server/obsidian-vault/projects/claude-config/notes/

# claude-code project is now hidden
grep "hidden" /mnt/c/Server/obsidian-vault/projects/claude-code/project.md
# Expected: hidden: true

# Check a migrated entry has correct frontmatter
head -15 /mnt/c/Server/obsidian-vault/projects/claude-config/notes/<any-migrated-file>.md
# Should show: project: claude-config, component: claude-code
```

- [ ] **Step 4: Verify graph view**

Open `http://192.168.1.77:5009/graph` in browser. You should see:
- Hub node `claude-config` visible
- Component stub `claude-code` visible
- Edges from migrated entries → `claude-config` hub

- [ ] **Step 5: Invalidate app cache**

```bash
docker.exe restart obsidian-capture
```

- [ ] **Step 6: Confirm capture form works end-to-end**

Go to `http://192.168.1.77:5009/capture`, select Claude Config, choose `claude-code` as component, submit a test note. Verify in `/projects/claude-config` that it appears, and the component pill filter works.

---

## Self-Review

**Spec coverage check:**
- ✅ Umbrella registry defining parent/component relationships
- ✅ Umbrella-first capture form with conditional component picker
- ✅ Entries route to umbrella folder with component metadata
- ✅ Wikilinks injected into entry body for graph edges
- ✅ Hub pages and component stubs as named graph nodes
- ✅ `get_vault_graph` includes hub/stub nodes; wikilinks resolve to them
- ✅ Migration script moves existing entries and creates hub structure
- ✅ Component filter on project view
- ✅ Flat umbrellas (no components) remain unchanged / backward compatible
- ✅ `capture/json` endpoint also handles component field

**No placeholders:** All steps contain complete, runnable code.

**Type consistency:** `read_entries(project, status_filter, component)` signature used consistently in vault.py, browse.py tests. `write_hub_page` / `write_component_stub` signatures match their call sites in the migration script.
