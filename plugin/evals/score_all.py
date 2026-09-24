#!/usr/bin/env python3
"""Score every course directory under the given roots with score_pack.py and print one table.

A course directory is any directory that holds lesson-plan.json. A directory that holds
teaching-guide.md, outline.md, sources.json or units/ but no lesson-plan.json looks like a
half-built course directory; it is listed as skipped with the reason. So is a course directory
whose lesson-plan.json cannot be read or scored. Nothing else in the roots is reported.

Default roots: plugin/evals and plugin/examples. A directory named after an id in
materials.json (the results/<run>/<material-id>/ layout) is checked against that material's
expectations. The locator check uses --sources-root when given, otherwise each directory's
sources.json base_path, the same rule as score_pack.py. When plugin/evals is searched, the
materials.json ids that have no scored course directory yet are named after the table.

Status: ok = scored, no validator errors, expectations met; fail = scored, with validator
errors or an unmet expectation; skipped = could not be scored (reason in the note column).
Exit status: 0 when every course directory found is ok; 1 when any is fail or skipped;
2 when a root does not exist, materials.json cannot be read, or no course directory is found.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_ROOTS = [EVALS_DIR, EVALS_DIR.parent / "examples"]
PLAN = "lesson-plan.json"
PACK_MARKERS = ("teaching-guide.md", "outline.md", "sources.json", "units")
SKIP_DIRS = {"__pycache__"}


def _load_score_pack():
    spec = importlib.util.spec_from_file_location("score_pack", EVALS_DIR / "score_pack.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


score_pack = _load_score_pack()


def find_course_dirs(root: Path) -> list[Path]:
    """Directories under root (root included) that hold lesson-plan.json or a course-directory
    marker, in sorted order. The walk does not descend into a directory that holds lesson-plan.json."""
    found: list[Path] = []
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:  # unreadable directory: nothing in it can be scored or reported
            continue
        names = {p.name for p in entries}
        if PLAN in names:
            found.append(current)
            continue
        if any(marker in names for marker in PACK_MARKERS):
            found.append(current)
        subdirs = [p for p in entries if p.is_dir() and not p.is_symlink() and p.name not in SKIP_DIRS and not p.name.startswith(".")]
        pending.extend(reversed(subdirs))
    return sorted(found)


def load_expectations(path: Path) -> dict[str, dict]:
    materials = json.loads(path.read_text(encoding="utf-8")).get("materials", [])
    return {m["id"]: m.get("expect") or {} for m in materials if isinstance(m, dict) and isinstance(m.get("id"), str)}


def score_one(pack: Path, sources_root: Path | None, expectations: dict[str, dict], store: Path | None) -> dict:
    """Score one course directory. Returns {"status", "note", "result"}; never raises for a bad directory."""
    if not (pack / PLAN).is_file():
        return {"status": "skipped", "note": f"no {PLAN}", "result": None}
    try:
        plan = json.loads((pack / PLAN).read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            return {"status": "skipped", "note": f"{PLAN} is not a JSON object", "result": None}
        root = sources_root
        manifest_path = pack / "sources.json"
        if root is None and manifest_path.is_file():
            root = score_pack.validate_lesson.sources_root_from_manifest(
                manifest_path, json.loads(manifest_path.read_text(encoding="utf-8")))
        expect = expectations.get(pack.name)
        result = {"pack": str(pack), "build": score_pack.build_metrics(pack, root, expect)}
        if store is not None:
            result["teach"] = score_pack.teach_metrics(store, plan.get("lesson_id"))
    except json.JSONDecodeError as error:
        return {"status": "skipped", "note": f"invalid JSON: {error}", "result": None}
    except OSError as error:
        return {"status": "skipped", "note": f"unreadable: {error}", "result": None}
    except Exception as error:  # a malformed plan must not stop the other directories from being scored
        return {"status": "skipped", "note": f"score_pack failed: {type(error).__name__}: {error}", "result": None}

    build = result["build"]
    problems = []
    if build["validator_errors"]:
        problems.append(f"{build['validator_errors']} validator errors, first: {build['errors'][0]}")
    unmet = [name for name, met in (build.get("expectations") or {}).items() if not met]
    if unmet:
        problems.append("expectation not met: " + ", ".join(unmet))
    if problems:
        return {"status": "fail", "note": "; ".join(problems), "result": result}
    note = f"expectations of {pack.name} met" if expect else ""
    return {"status": "ok", "note": note, "result": result}


def display_path(path: Path) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:  # different drive on Windows
        return str(path)


def _cell(value) -> str:
    return "-" if value is None else str(value)


def table(rows: list[dict], with_teach: bool) -> list[str]:
    header = ["status", "course directory", "schema", "sections", "relations", "errors/warnings", "locator hit", "unsupported"]
    if with_teach:
        header.append("attempts")
    header.append("note")
    lines = [header]
    for row in rows:
        build = (row["result"] or {}).get("build")
        if build is None:
            cells = [row["status"], row["path"]] + ["-"] * (len(header) - 3) + [row["note"]]
        else:
            cells = [row["status"], row["path"], _cell(build["schema_version"]), str(build["sections"]), str(build["relations"]),
                     f"{build['validator_errors']}/{build['validator_warnings']}", _cell(build["locator_hit_rate"]),
                     _cell(build["unsupported_ratio"])]
            if with_teach:
                cells.append(str(row["result"]["teach"].get("attempts", 0)))
            cells.append(row["note"])
        lines.append(cells)
    widths = [max(len(line[i]) for line in lines) for i in range(len(header) - 1)]
    return [("  ".join(cell.ljust(width) for cell, width in zip(line, widths)) + "  " + line[-1]).rstrip() for line in lines]


def output_name(root: Path, pack: Path) -> str:
    relative = pack.relative_to(root)
    parts = [root.resolve().name] + ([] if relative == Path(".") else list(relative.parts))
    return "--".join(parts) + ".json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="*", type=Path, help="Directories to search (default: plugin/evals and plugin/examples)")
    parser.add_argument("--sources-root", type=Path, help="Material root for every directory (enables the locator check); defaults to each sources.json base_path")
    parser.add_argument("--store", type=Path, help="Knowledge store; adds teach metrics from its LRG log")
    parser.add_argument("--output-dir", type=Path, help="Write one score_pack result JSON per scored directory here (usable as --baseline for score_pack.py)")
    args = parser.parse_args(argv)

    roots = args.roots or DEFAULT_ROOTS
    for root in roots:
        if not root.is_dir():
            print(f"ERROR: not a directory: {root}", file=sys.stderr)
            return 2
    try:
        expectations = load_expectations(EVALS_DIR / "materials.json")
    except (OSError, ValueError, AttributeError) as error:
        print(f"ERROR: cannot read materials.json: {error}", file=sys.stderr)
        return 2

    rows = []
    seen: set[Path] = set()
    for root in roots:
        for pack in find_course_dirs(root):
            if pack.resolve() in seen:
                continue
            seen.add(pack.resolve())
            row = score_one(pack, args.sources_root, expectations, args.store)
            row["path"] = display_path(pack)
            row["output"] = output_name(root, pack)
            rows.append(row)
    if not rows:
        print("ERROR: no course directory (a directory with lesson-plan.json) under " + ", ".join(str(r) for r in roots), file=sys.stderr)
        return 2

    for line in table(rows, args.store is not None):
        print(line)
    counts = {status: sum(1 for row in rows if row["status"] == status) for status in ("ok", "fail", "skipped")}
    print(f"{len(rows)} course directories: {counts['ok']} ok, {counts['fail']} fail, {counts['skipped']} skipped")
    if any(root.resolve() == EVALS_DIR for root in roots):
        built = {Path(row["path"]).name for row in rows if row["result"] is not None}
        unbuilt = [material for material in expectations if material not in built]
        if unbuilt:
            print("materials.json entries with no scored course directory (build them into evals/results/<run>/<id>/): " + ", ".join(unbuilt))

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for row in rows:
            if row["result"] is not None:
                (args.output_dir / row["output"]).write_text(json.dumps(row["result"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if counts["ok"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
