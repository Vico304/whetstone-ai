#!/usr/bin/env python3
"""Scan a lesson pack for unresolved [[wikilinks]] and inbox entries."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

WIKILINK = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
FENCE = re.compile(r"```.*?```", re.DOTALL)
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
ALIASES_LINE = re.compile(r"^aliases:\s*\[(.*)\]\s*$", re.MULTILINE)


def normalize(name: str) -> str:
    return unicodedata.normalize("NFC", name.strip()).casefold()


def note_names(concepts_dir: Path) -> set[str]:
    """Known targets: note filenames (stem) plus frontmatter aliases."""
    known: set[str] = set()
    if not concepts_dir.is_dir():
        return known
    for note in concepts_dir.glob("*.md"):
        if note.name.startswith("_"):
            continue
        known.add(normalize(note.stem))
        head = note.read_text(encoding="utf-8", errors="replace")[:2000]
        match = FRONTMATTER.match(head)
        if match:
            alias_match = ALIASES_LINE.search(match.group(0))
            if alias_match:
                for alias in alias_match.group(1).split(","):
                    alias = alias.strip().strip("\"'")
                    if alias:
                        known.add(normalize(alias))
    return known


def inbox_entries(inbox: Path) -> list[str]:
    if not inbox.is_file():
        return []
    entries: list[str] = []
    for line in inbox.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().lstrip("-*").strip()
        if not line or line.startswith("#"):
            continue
        link = WIKILINK.fullmatch(line)
        entries.append(link.group(1).strip() if link else line)
    return entries


def scan(pack_dir: Path, inbox: Path | None) -> dict:
    concepts_dir = pack_dir / "concepts"
    known = note_names(concepts_dir)
    occurrences: dict[str, list[str]] = {}
    for md_file in sorted(pack_dir.rglob("*.md")):
        if md_file.name.startswith("_") or "__pycache__" in md_file.parts:
            continue
        text = FENCE.sub("", md_file.read_text(encoding="utf-8", errors="replace"))
        for match in WIKILINK.finditer(text):
            target = match.group(1).strip()
            if target and normalize(target) not in known:
                occurrences.setdefault(target, []).append(
                    str(md_file.relative_to(pack_dir))
                )
    inbox_pending = [
        entry
        for entry in inbox_entries(inbox or pack_dir / "concepts" / "_inbox.md")
        if normalize(entry) not in known
    ]
    return {
        "pack_dir": str(pack_dir),
        "known_notes": sorted(known),
        "unresolved_links": [
            {"concept": concept, "found_in": sorted(set(paths))}
            for concept, paths in sorted(occurrences.items())
        ],
        "inbox_pending": inbox_pending,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path, help="Lesson pack directory")
    parser.add_argument("--inbox", type=Path, help="Inbox file (default: <pack>/concepts/_inbox.md)")
    args = parser.parse_args()
    if not args.pack_dir.is_dir():
        print(f"ERROR: not a directory: {args.pack_dir}")
        return 2
    print(json.dumps(scan(args.pack_dir, args.inbox), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
