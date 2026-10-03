#!/usr/bin/env python3
"""Derive learning-plan.json (schema 1.0) for one plan directory, print its progress view, or check it.

Sources: learning-plan.md (level-3 course headings with 状态：, and the 前置依赖 / 核心概念 / 对象 / 规模估计 /
材料 lines under each; the last declaration of a course wins) and the course directories beside it. Directories
match by id, then title; undeclared built courses follow in outline confirmation order; a prerequisite course
goes right before its parent. gap_ledger.py --learning-plan reads the result.

build [--store STORE] [--output FILE] writes it; --status prints the progress view; --check reports DUP-CORE,
SPLIT, DEPTH, UNLISTED, UNBUILT-REGISTERED and exits 1 only on ORDER (a depends_on pointing to a later course;
every cycle has one). Exit 2 when an input cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_SECTIONS = 9
SECTIONS_PER_DOCUMENT = 3
STALE_DAYS = 30
DONE_STATUSES = {"completed", "deferred"}
HEADING = re.compile(r"^###\s+(?:[\d.]+\s+)?(课程|骨架课|课)\s*(\d+)?\s*[：:]?\s*(?:`([^`]+)`|([A-Za-z][\w.-]*))?\s*[：:]?\s*"
                     r"(?:《(?P<title>[^》]+)》|(?P<bare>.+?))\s*状态[：:]\s*\**(?P<status>[^\s*（(　`]+)(?P<rest>.*)$")
COURSE_REF = re.compile(r"(?:课程|骨架课|课)\s*(\d+(?:\s*[、,，–—~至-]\s*\d+)*)")
ASIDE = re.compile(r"（[^）]*）|\([^)]*\)")
FIELD = re.compile(r"^\s*-\s*(前置依赖|核心概念|对象|规模估计|规模|材料(?:（具体路径）)?)[：:]\s*(.*)$")


def read_json(path: Path) -> dict | None:
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    if data is not None and not isinstance(data, dict):
        raise ValueError(f"{path}: root must be an object")
    return data


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def norm(text: str) -> str:  # titles compare without spaces, backticks, emphasis or 《》
    return re.sub(r"[\s`*《》]", "", text or "")


def parse_plan_md(text: str) -> list[dict]:
    """Course entries in order of their last declaration."""
    entries: dict[str, dict] = {}
    position = 0
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("#"):
            current = None
            match = HEADING.match(line.strip())
            if match:
                label, number, quoted, bare_id, title = match.group(1, 2, 3, 4, "title")
                title = (title or match.group("bare") or "").strip(" 　：:")
                course_id = quoted or bare_id
                key = course_id or f"{label}-{number or title}"
                position += 1
                shape = re.search(r"shape:\s*(\w+)", match.group("rest"))
                earlier = entries.pop(key, None)  # the last declaration wins; lines it does not repeat carry over
                current = entries[key] = {"key": key, "id": course_id, "title": title, "number": number or (earlier or {}).get("number"),
                                          "position": position, "declared_status": match.group("status"),
                                          "shape": shape.group(1) if shape else (earlier or {}).get("shape"),
                                          "fields": {}, "inherited": (earlier or {}).get("fields", {})}
            continue
        if current is not None:
            for part in re.split(r"[；;]\s*(?=前置依赖|核心概念|对象|规模)", line):
                field = FIELD.match(part if part.lstrip().startswith("-") else f"- {part.strip()}")
                if field:
                    name = "材料" if field.group(1).startswith("材料") else "规模估计" if field.group(1) == "规模" else field.group(1)
                    current["fields"].setdefault(name, field.group(2).strip())
    for entry in entries.values():
        entry["fields"] = {**entry.pop("inherited"), **entry["fields"]}
    return sorted(entries.values(), key=lambda e: e["position"])


def concepts_by_role(lesson: dict) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    for section in [s for s in lesson.get("sections") or [] if isinstance(s, dict)]:
        for concept in [c for c in section.get("concepts") or [] if isinstance(c, dict) and isinstance(c.get("id"), str)]:
            roles.setdefault(concept.get("role") or "?", []).append(concept["id"])
    return {role: list(dict.fromkeys(ids)) for role, ids in roles.items()}


def course_numbers(text: str) -> list[str]:
    """课程 1、2 / 课程 1–3 / 骨架课 1 -> the numbers named."""
    numbers: list[str] = []
    for group in COURSE_REF.findall(text):
        for part in re.split(r"\s*[、,，]\s*", group):
            ends = [int(n) for n in re.split(r"\s*[–—~至-]\s*", part) if n]
            numbers += [str(n) for n in range(ends[0], ends[-1] + 1)]
    return numbers


def split_list(text: str) -> list[str]:
    return [part.strip(" `") for part in re.split(r"[,，、]", text) if part.strip(" `")]


def size_estimate(fields: dict) -> int | None:
    """Sections a course is expected to have: 规模估计 'N 个 unit' / 'N 节', else documents x 3."""
    unit = re.search(r"(\d+)\s*(?:个\s*unit|节)", fields.get("规模估计", ""))
    documents = re.findall(r"`[^`]+`", fields.get("材料", ""))
    return int(unit.group(1)) if unit else len(documents) * SECTIONS_PER_DOCUMENT if documents else None


def build(plan_dir: Path, store: Path | None = None, now: str | None = None) -> dict:
    md_path = plan_dir / "learning-plan.md"
    entries = parse_plan_md(md_path.read_text(encoding="utf-8")) if md_path.is_file() else []
    built: dict[str, tuple[str, dict]] = {}
    for path, lesson in ((path, read_json(path)) for path in sorted(plan_dir.glob("*/lesson-plan.json"))):
        built[lesson.get("lesson_id") or path.parent.name] = (path.parent.name, lesson)
    by_title = {norm(lesson.get("title") or ""): lid for lid, (_, lesson) in built.items()}
    courses: list[dict] = []
    matched: set[str] = set()
    for entry in entries:
        lid = entry["id"] if entry["id"] in built else by_title.get(norm(entry["title"]))
        if lid is None and entry["id"] is None:
            lid = next((k for k, (_, l) in built.items() if norm(entry["title"]) and norm(entry["title"]) in norm(l.get("title") or "")), None)
        course_id = lid or entry["id"] or entry["key"]
        matched.add(course_id)
        courses.append({"id": course_id, "entry": entry})
    unlisted = sorted((lid for lid in built if lid not in matched),
                      key=lambda lid: (built[lid][1].get("outline_confirmed_at") or "9999", lid))
    courses += [{"id": lid, "entry": None} for lid in unlisted]
    courses = [c for i, c in enumerate(courses) if c["id"] not in {d["id"] for d in courses[:i]}]
    # a prerequisite course goes right before its parent; deeper ones before shallower ones
    ids = [c["id"] for c in courses]
    for lid, (_, lesson) in sorted(built.items(), key=lambda kv: kv[1][1].get("depth") or 0):
        parent = lesson.get("prerequisite_of")
        if parent in ids and lid in ids:
            ids.remove(lid)
            ids.insert(ids.index(parent), lid)
    courses.sort(key=lambda c: ids.index(c["id"]))
    numbers = {c["entry"]["number"]: c["id"] for c in courses if c["entry"] and c["entry"]["number"]}
    plan_ids = [c["id"] for c in courses]
    result = []
    owner: dict[str, str] = {}
    for order, course in enumerate(courses, 1):
        entry, lid = course["entry"] or {"fields": {}}, course["id"]
        directory, lesson = built.get(lid, (None, None))
        fields = entry["fields"]
        item: dict = {"id": lid, "title": (lesson or {}).get("title") or entry.get("title"), "order": order}
        shape = (lesson or {}).get("shape") or entry.get("shape")
        item.update({k: v for k, v in (("dir", directory and directory + "/"), ("shape", shape)) if v})
        depends = []
        dep_text = ASIDE.sub("", fields.get("前置依赖", ""))
        for other in plan_ids:
            if other != lid and re.search(rf"(?<![\w-]){re.escape(other)}(?![\w-])", dep_text):
                depends.append(other)
        depends += [numbers[n] for n in course_numbers(dep_text) if n in numbers and numbers[n] != lid]
        depends += [other_id for other_id, (_, other) in built.items() if other.get("prerequisite_of") == lid]
        item["depends_on"] = list(dict.fromkeys(depends + ([lesson["parent_course"]] if (lesson or {}).get("parent_course") else [])))
        item.update({k: lesson[k] for k in ("prerequisite_of", "blocked_at", "depth") if (lesson or {}).get(k) is not None})
        roles = concepts_by_role(lesson or {})
        item["core"], item["core_source"] = (roles.get("core", []), "lesson-plan") if lesson is not None else \
            (split_list(fields.get("核心概念", "")), "plan-md")
        prerequisite_plan = (read_json(plan_dir / directory / "prerequisite-plan.json") if directory else None) or {}
        needs = [p["concept_id"] for p in prerequisite_plan.get("prerequisites") or [] if isinstance(p, dict) and p.get("concept_id")]
        needs_source = "prerequisite-plan" if needs else None
        earlier_core = [c for c in roles.get("supporting", []) + roles.get("listed", []) if owner.get(c, lid) != lid and c not in needs]
        needs, needs_source = needs + earlier_core, needs_source or ("earlier-core" if earlier_core else None)
        subject = ((lesson or {}).get("subject") or fields.get("对象") or "").strip("` ")
        extra = {"needs": needs, "needs_source": needs_source, "subject": subject or None,
                 "declared_status": entry.get("declared_status"), "size_estimate": size_estimate(fields),
                 "sections": len([s for s in lesson.get("sections") or [] if isinstance(s, dict)]) if lesson else None}
        item.update({k: v for k, v in extra.items() if v is not None})
        owner.update({cid: lid for cid in item["core"] if cid not in owner})
        result.append(item)

    # store.json pack_dir paths are the learner's own; only the last two parts (plan, course) are compared
    external, unbuilt = [], []
    for lesson in (read_json(store / "store.json") or {}).get("lessons") or [] if store else []:
        if not isinstance(lesson, dict) or not lesson.get("lesson_id"):
            continue
        pack = Path(str(lesson.get("pack_dir") or ""))
        if pack.parent.name == plan_dir.name:
            unbuilt += [] if lesson["lesson_id"] in built else [lesson["lesson_id"]]
            continue
        record = {"id": lesson["lesson_id"], "plan_dir": f"../{pack.parent.name}/", "use": "evidence"}
        other = read_json(store.parent / "courses" / pack.parent.name / pack.name / "lesson-plan.json")
        external.append({**record, "core": concepts_by_role(other).get("core", [])} if other else record)
    stamp = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "goal": plan_dir.name,
        "generated_at": stamp,
        "generated_from": {"plan_md": "learning-plan.md" if md_path.is_file() else None, "course_dirs": len(built),
                           "store": str(store) if store else None},
        "courses": result,
        "external_courses": external,
        "unbuilt_registered": unbuilt,
        "unlisted": unlisted,
    }


def course_state(course: dict, plan_dir: Path, now: datetime) -> tuple[str, bool, dict | None]:
    """(view state, stale flag, learning-progress.json)."""
    if course.get("declared_status") == "暂不学":
        return "暂不学", False, None
    if not course.get("dir"):
        return "未建", False, None
    if (read_json(plan_dir / course["dir"] / "lesson-plan.json") or {}).get("outline_confirmed_at") is None:
        return "大纲未确认", False, None
    progress = read_json(plan_dir / course["dir"] / "learning-progress.json")
    if progress is None:
        return "未开始", False, None
    if progress.get("blocked") or progress.get("status") == "completed":
        return ("等前置" if progress.get("blocked") else "已结课"), False, progress
    updated = progress.get("updated_at")
    return "教学中", bool(updated) and (now - parse_time(updated)).days >= STALE_DAYS, progress


def status(plan: dict, plan_dir: Path, store: Path | None, now: datetime) -> list[str]:
    learner = read_json(store / "learner-state.json") if store else None
    concepts = (learner or {}).get("concepts") or {}
    suspect = {s if isinstance(s, str) else s.get("id") or s.get("concept_id")
               for s in ((learner or {}).get("fringe") or {}).get("suspect") or [] if isinstance(s, (str, dict))}
    lines = ["order  course                                  state       sections  core mastered/delayed/suspect"]
    states = []
    done_sections = total_sections = 0
    for course in plan["courses"]:
        state, stale, progress = course_state(course, plan_dir, now)
        states.append((course["id"], state))
        sections = [s for s in (progress or {}).get("sections") or [] if isinstance(s, dict)]
        done = sum(1 for s in sections if s.get("status") in DONE_STATUSES)
        done_sections, total_sections = done_sections + done, total_sections + len(sections)
        core = [concepts.get(c) or {} for c in course.get("core") or []]
        mastered = sum(1 for c in core if c.get("last_verdict") == "mastered")
        delayed = sum(1 for c in core if c.get("evidence_tier") in {"delayed", "transfer"})
        flagged = sum(1 for c in course.get("core") or [] if c in suspect)
        cells = f"{mastered}/{delayed}/{flagged}" if learner else "-"
        label = state + ("（搁置）" if stale else "")
        lines.append(f"{course['order']:<6} {course['id']:<39} {label:<10} {f'{done}/{len(sections)}' if sections else '-':<9} {cells}")
    counted = [s for _, s in states if s != "暂不学"]
    here = next((i for i, (_, s) in enumerate(states) if s in {"教学中", "等前置"}), None)
    current = states[here][0] if here is not None else None
    after = [cid for cid, s in states[(here or -1) + 1:] if s in {"未开始", "未建"}]
    tally = ", ".join(f"{s} {counted.count(s)}" for s in dict.fromkeys(counted))
    lines.append(f"courses: {counted.count('已结课')}/{len(counted)} completed; {tally}")
    lines.append(f"current: {current or '-'}; next: {after[0] if after else '-'}; sections done: {done_sections}/{total_sections}")
    return lines


def check(plan: dict) -> tuple[list[str], list[str]]:
    """(reported lines, failing lines)."""
    reports, failures = [], []
    position = {c["id"]: c["order"] for c in plan["courses"]}
    holders: dict[str, list[str]] = {}
    for course in plan["courses"]:
        for cid in course.get("core") or []:
            holders.setdefault(cid, []).append(course["id"])
    reports += [f"DUP-CORE: {cid} is core in {', '.join(ids)} (owner {ids[0]})" for cid, ids in sorted(holders.items()) if len(ids) > 1]
    for course in plan["courses"]:
        size, said = (course["sections"], "有") if "sections" in course else (course.get("size_estimate") or 0, "预计")
        if size > MAX_SECTIONS:
            reports.append(f"SPLIT: {course['id']} {said} {size} 节 (max {MAX_SECTIONS})")
        if (course.get("depth") or 0) >= 2:
            reports.append(f"DEPTH: {course['id']} is a prerequisite course at depth {course['depth']}")
        for dep in course.get("depends_on") or []:
            if dep in position and position[dep] > course["order"]:
                failures.append(f"ORDER: {course['id']} depends on {dep}, which comes later")
    reports += [f"UNLISTED: {cid} has a course directory but no course heading in learning-plan.md" for cid in plan["unlisted"]]
    reports += [f"UNBUILT-REGISTERED: {cid} is in store.json but has no course directory here" for cid in plan["unbuilt_registered"]]
    return reports, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", nargs="?", choices=["build"])
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--store", type=Path, help="knowledge store (store.json, learner-state.json)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--now", help="fixed ISO time for generated_at and the stale flag")
    args = parser.parse_args(argv)
    try:
        if not args.plan_dir.is_dir():
            raise OSError(f"not a directory: {args.plan_dir}")
        plan = build(args.plan_dir, args.store, args.now)
        now = parse_time(plan["generated_at"])
        view = status(plan, args.plan_dir, args.store, now) if args.status else []
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.command == "build" or not (args.status or args.check):
        text = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        args.output.write_text(text, encoding="utf-8") if args.output else sys.stdout.write(text)
    reports, failures = check(plan) if args.check else ([], [])
    print("\n".join(view + reports + failures), end="\n" if view or reports or failures else "")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
