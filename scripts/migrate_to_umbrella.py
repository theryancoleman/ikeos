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
