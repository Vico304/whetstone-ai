#!/usr/bin/env python3
"""Scan a course directory for unresolved [[wikilinks]] and inbox entries, grouped by unit.

Each pending concept is assigned to the unit it belongs to (the units/<id>.md it was marked
in, else the lesson plan section that lists it, else the unit document that mentions it);
one marked concept in a unit is `isolated`, two or more are a `cluster` — the note for that
unit then deepens the unit from those concepts instead of only defining them.

Given a workspace or plan directory instead of a course, scan only the course whose
learning-progress.json was updated most recently (the one being studied) and list the
others with their inbox counts; --all scans every course, --course picks one.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

WIKILINK = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1[ \t]*$", re.DOTALL | re.MULTILINE)
INLINE_CODE = re.compile(r"`[^`\n]*`")
FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*\r?\n", re.DOTALL)
ALIASES_INLINE = re.compile(r"^aliases:\s*\[(.*)\]\s*$", re.MULTILINE)
ALIASES_BLOCK = re.compile(r"^aliases:\s*$\n((?:[ \t]+-[ \t]*.*\n?)+)", re.MULTILINE)


def normalize(name: str) -> str:
    return unicodedata.normalize("NFC", name.strip()).casefold()


def note_names(concepts_dir: Path) -> set[str]:
    """Known targets: note filenames (stem) plus frontmatter aliases, and every other .md stem in the
    course (Obsidian resolves [[u01]] to units/u01.md), so only concept links without a note count."""
    known: set[str] = set()
    course = concepts_dir.parent
    if course.is_dir():
        for other in course.rglob("*.md"):
            if "__pycache__" not in other.parts and not other.name.startswith("_") and other.parent != concepts_dir:
                known.add(normalize(other.stem))
    if not concepts_dir.is_dir():
        return known
    for note in concepts_dir.glob("*.md"):
        if note.name.startswith("_"):
            continue
        known.add(normalize(note.stem))
        head = note.read_text(encoding="utf-8", errors="replace")[:2000]
        match = FRONTMATTER.match(head)
        if match:
            for alias in frontmatter_aliases(match.group(0)):
                known.add(normalize(alias))
    return known


def frontmatter_aliases(frontmatter: str) -> list[str]:
    """Read ``aliases`` from frontmatter in either inline-list or block-list form."""
    aliases: list[str] = []
    inline = ALIASES_INLINE.search(frontmatter)
    if inline:
        for alias in inline.group(1).split(","):
            alias = alias.strip().strip("\"'")
            if alias:
                aliases.append(alias)
        return aliases
    block = ALIASES_BLOCK.search(frontmatter)
    if block:
        for line in block.group(1).splitlines():
            alias = line.strip().lstrip("-").strip().strip("\"'")
            if alias:
                aliases.append(alias)
    return aliases


def strip_code(text: str) -> str:
    """Remove fenced blocks and inline code spans so their [[links]] are not scanned."""
    return INLINE_CODE.sub("", FENCE.sub("", text))


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


def is_course_dir(path: Path) -> bool:
    return path.is_dir() and ((path / "lesson-plan.json").is_file() or (path / "teaching-guide.md").is_file())


def course_dirs(root: Path) -> list[Path]:
    """Course directories under a workspace or plan directory, most recently studied first."""
    found = sorted({p.parent for p in root.rglob("lesson-plan.json")} | {p.parent for p in root.rglob("teaching-guide.md")}
                   if not is_course_dir(root) else {root})

    def updated(course: Path) -> str:
        progress = course / "learning-progress.json"
        if progress.is_file():
            try:
                return str(json.loads(progress.read_text(encoding="utf-8")).get("updated_at") or "")
            except (OSError, ValueError):
                return ""
        return ""
    return sorted(found, key=lambda c: (updated(c), str(c)), reverse=True)


UNIT_FILE = re.compile(r"^(?:units|zoom)/([^/]+?)(?:-guide)?\.md$")


def load_plan(pack_dir: Path) -> dict:
    path = pack_dir / "lesson-plan.json"
    if not path.is_file():
        return {}
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return plan if isinstance(plan, dict) else {}


def plan_units(plan: dict) -> list[dict]:
    """[{id, title, names: {normalized name/alias}}] per section of the lesson plan."""
    units = []
    for section in plan.get("sections", []) or []:
        if not isinstance(section, dict) or not isinstance(section.get("id"), str):
            continue
        names: set[str] = set()
        for concept in section.get("concepts", []) or []:
            if isinstance(concept, dict):
                for name in [concept.get("name"), *(concept.get("aliases") or [])]:
                    if isinstance(name, str) and name.strip():
                        names.add(normalize(name))
        units.append({"id": section["id"], "title": section.get("title") or "", "names": names})
    return units


def unit_texts(pack_dir: Path) -> dict[str, str]:
    """{unit id: normalized text of units/<id>.md} for mention lookup."""
    texts = {}
    units_dir = pack_dir / "units"
    if units_dir.is_dir():
        for path in sorted(units_dir.glob("*.md")):
            texts[path.stem] = normalize(strip_code(path.read_text(encoding="utf-8", errors="replace")))
    return texts


def assign_unit(concept: str, found_in: list[str], units: list[dict], texts: dict[str, str]) -> str | None:
    """The unit a concept belongs to: where it was marked, else where the plan lists it, else where a unit mentions it."""
    for path in found_in:
        match = UNIT_FILE.match(path.replace("\\", "/"))
        if match:
            return match.group(1)
    key = normalize(concept)
    for unit in units:
        if key in unit["names"]:
            return unit["id"]
    for unit_id, text in texts.items():
        if key and key in text:
            return unit_id
    return None


def group_by_unit(pending: dict[str, list[str]], plan: dict, pack_dir: Path) -> list[dict]:
    units = plan_units(plan)
    texts = unit_texts(pack_dir)
    titles = {u["id"]: u["title"] for u in units}
    groups: dict[str | None, list[str]] = {}
    for concept, found_in in pending.items():
        groups.setdefault(assign_unit(concept, found_in, units, texts), []).append(concept)
    order = {u["id"]: index for index, u in enumerate(units)}
    result = []
    for unit_id, concepts in sorted(groups.items(), key=lambda item: (item[0] is None, order.get(item[0], 10**6), str(item[0]))):
        concepts = sorted(set(concepts))
        result.append({
            "unit": unit_id, "title": titles.get(unit_id, ""), "concepts": concepts,
            "scope": "cluster" if len(concepts) >= 2 else "isolated",
            "note_file": f"concepts/{unit_id}.md" if unit_id else "concepts/<主题>.md",
        })
    return result


def scan(pack_dir: Path, inbox: Path | None) -> dict:
    concepts_dir = pack_dir / "concepts"
    known = note_names(concepts_dir)
    occurrences: dict[str, list[str]] = {}
    for md_file in sorted(pack_dir.rglob("*.md")):
        if md_file.name.startswith("_") or "__pycache__" in md_file.parts:
            continue
        text = strip_code(md_file.read_text(encoding="utf-8", errors="replace"))
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
    pending = {concept: sorted(set(paths)) for concept, paths in occurrences.items()}
    for entry in inbox_pending:
        pending.setdefault(entry, [])
    return {
        "pack_dir": str(pack_dir),
        "known_notes": sorted(known),
        "unresolved_links": [
            {"concept": concept, "found_in": sorted(set(paths))}
            for concept, paths in sorted(occurrences.items())
        ],
        "inbox_pending": inbox_pending,
        "by_unit": group_by_unit(pending, load_plan(pack_dir), pack_dir),
        "rule": "one note per unit (concepts/<unit>.md, aliases = its concepts); isolated: explain those concepts only; cluster: also deepen the unit from them",
    }


def scan_scope(root: Path, inbox: Path | None, scan_all: bool, chosen: Path | None) -> dict:
    """One course by default (the one studied most recently); the others are only counted."""
    courses = course_dirs(root)
    if chosen is not None:
        if not is_course_dir(chosen):
            raise ValueError(f"not a course directory (no lesson-plan.json): {chosen}")
        courses = [chosen] + [c for c in courses if c.resolve() != chosen.resolve()]
    if not courses:
        return {"error": f"no course directory (lesson-plan.json) under {root}", "courses": []}
    targets = courses if scan_all else courses[:1]
    scanned = [scan(course, inbox if course == targets[0] else None) for course in targets]
    others = [{"pack_dir": str(c), "inbox_pending": len(inbox_entries(c / "concepts" / "_inbox.md"))}
              for c in courses if c not in targets]
    return {"current_course": str(targets[0]), "scanned": scanned, "other_courses": others,
            "note": "only the current course was scanned; pass --all to scan every course, --course <dir> to pick one" if others else ""}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pack_dir", type=Path, help="A course directory, or a workspace / plan directory holding several")
    parser.add_argument("--inbox", type=Path, help="Inbox file (default: <course>/concepts/_inbox.md)")
    parser.add_argument("--all", action="store_true", help="Scan every course under the directory")
    parser.add_argument("--course", type=Path, help="Scan this course (a directory with lesson-plan.json)")
    args = parser.parse_args()
    if not args.pack_dir.is_dir():
        print(f"ERROR: not a directory: {args.pack_dir}")
        return 2
    try:
        if is_course_dir(args.pack_dir) and not args.all and args.course is None:
            print(json.dumps(scan(args.pack_dir, args.inbox), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(scan_scope(args.pack_dir, args.inbox, args.all, args.course), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
