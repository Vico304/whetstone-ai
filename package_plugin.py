#!/usr/bin/env python3
"""Package plugin/ as a .plugin (zip) file for Claude Desktop / Cowork upload.

A .plugin is a zip whose root contains .claude-plugin/plugin.json. Usage:

    python3 package_plugin.py [--output ../dist/whetstone.plugin]

Includes: .claude-plugin/, .codex-plugin/, skills/, docs/, README.md.
Excludes: tests/, evals/, examples/, __pycache__, learning packs, dotfiles.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "plugin"
INCLUDE_TOP = {".claude-plugin", ".codex-plugin", "skills", "docs", "README.md"}
SKIP_DIRS = {"__pycache__", "learning-packs"}
SKIP_FILES = {".DS_Store", ".gitignore"}


def package(output: Path) -> int:
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            rel = path.relative_to(ROOT)
            if rel.parts[0] not in INCLUDE_TOP or not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in rel.parts) or path.name in SKIP_FILES or path.suffix == ".pyc":
                continue
            archive.write(path, rel.as_posix())
            count += 1
    print(f"OK: {output} — {manifest['name']} v{manifest.get('version')} — {count} files, {output.stat().st_size} bytes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT.parent.parent / "dist" / "whetstone.plugin")
    args = parser.parse_args()
    return package(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
