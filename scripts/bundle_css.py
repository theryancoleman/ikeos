"""
Inline all @import chains from style.css into a single bundle.css.
Run at Docker build time to eliminate the CSS waterfall on first load.
"""
import re
from pathlib import Path

STATIC = Path("app/static")
OUT = STATIC / "bundle.css"

# Matches both: @import url("f.css") and @import "f.css" / @import 'f.css'
IMPORT_RE = re.compile(
    r'@import\s+(?:url\(["\']?([^"\')\s]+)["\']?\)|["\']([^"\']+)["\'])\s*;'
)


def inline_imports(css_text: str, base_dir: Path, seen: set) -> str:
    def replace_import(m):
        raw = m.group(1) or m.group(2)
        path = (base_dir / raw).resolve()
        if path in seen:
            return ""
        seen.add(path)
        if not path.exists():
            return m.group(0)
        content = path.read_text(encoding="utf-8")
        return inline_imports(content, path.parent, seen)

    return IMPORT_RE.sub(replace_import, css_text)


seen: set = set()
root = STATIC / "style.css"
seen.add(root.resolve())
bundled = inline_imports(root.read_text(encoding="utf-8"), root.parent, seen)
OUT.write_text(bundled, encoding="utf-8")
print(f"bundle.css written ({len(bundled):,} bytes, {len(seen)} files inlined)")
