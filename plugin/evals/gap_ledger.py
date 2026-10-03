#!/usr/bin/env python3
"""Build a gap ledger for one lesson: every prerequisite the lesson assumes, what the learner's
evidence says about it, and where the course will supply it (so no partial or missing prerequisite
is silently skipped).

Inputs: a prerequisite-plan.json (schema 1.0 or 1.1), the lesson-plan.json it serves, and
optionally the learner's background (the table under 相关背景 in the learner profile), a
learner-state.json, a prerequisite-progress.json and a learning plan (the courses around this one,
in order, each with its core concept ids and the concept ids it needs).

The learning plan is either the bare {"courses": [...]} list in array order, or a learning-plan.json with a
schema_version (1.0). Only the second turns on the learning-plan rules below, so a ledger built without one
is unchanged: courses sorted by order, 暂不学 courses left out, a declared core replaced by the course's own
lesson-plan.json when --plan-dir finds it; a gap item needed by >= 2 courses goes to a plan course (a course
of its own, before the first course that needs it); a gap whose owner comes later is supplied here and the
later course is suggested to move first; only R5 (gap) bridge sections are raised past 9 sections.

Evidence, highest tier wins, newest within a tier: 4 diagnosis in prerequisite-progress.json;
3 learner-state.json; 2 a finished earlier or prerequisite course named in the profile table;
1 the learner's own description in the profile table; 0 nothing (state unknown).

Disposition per item, first rule that matches:
  R6 unknown   -> read as gap / partial / known (tier 0) for assessment_mode always / auto / skip
  R1 known     -> none at tier >= 3, else T0 (a one-line reminder)
  R2 scope     -> gap only: core of an earlier course in the learning plan -> defer_to_course;
                  needed by >= 2 courses (plan-course with a learning-plan.json), or depends on another
                  gap -> T3
  R3 def       -> T0
  R4 partial   -> T1 (a "先补三样" item before the section's problem); T2 when that section
                  already has 3 T1 items or >= 3 sections need it
  R5 gap       -> T2 (a bridge section before the first section that needs it) when its cluster
                  has <= 3 gap items, else T3
When the sections plus T2 sections exceed 9, T2 clusters are raised to T3, largest first.

--check prints SUGGEST lines for reorder suggestions (they do not fail) and exits 1 when a partial or gap item has no disposition, a section has more than 3 T1
items, or the lesson is still over 9 sections. Exit 2 when an input cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_SECTIONS = 9
MAX_T1_PER_SECTION = 3
LEVEL_STATE = {"未接触": "gap", "听过": "partial", "用过": "known", "熟练": "known"}
KIND_BY_DEPTH = {"fact": "def", "mechanism": "mech", "tool": "tool"}
UNKNOWN_AS = {"always": "gap", "auto": "partial", "skip": "known"}


def split_id(value: str) -> list[str]:
    return [part for part in re.split(r"[./]", value.strip()) if part]


def read_background(text: str) -> list[dict]:
    """Rows of the first markdown table whose header has 领域 and 自述水平."""
    rows: list[dict] = []
    header: list[str] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if header is not None and rows:
                break
            header = None
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if header is None:
            if "领域" in cells and "自述水平" in cells:
                header = cells
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        row = dict(zip(header, cells))
        if row.get("领域"):
            rows.append(row)
    return rows


def background_evidence(item: dict, rows: list[dict]) -> dict | None:
    """Tier 1 (the learner's own words) or tier 2 (a finished course named as evidence)."""
    concept_id = item.get("concept_id") or ""
    names = {item.get("name") or "", concept_id} - {""}
    best: tuple[int, dict] | None = None
    for row in rows:
        said = {name.strip() for name in re.split(r"[,，、]", row.get("说过的具体概念", "")) if name.strip()}
        domain = split_id(row["领域"])
        if names & said:
            score = 1000
        elif domain and split_id(concept_id)[: len(domain)] == domain:
            score = len(domain)
        else:
            continue
        if best is None or score > best[0]:
            best = (score, row)
    if best is None:
        return None
    score, row = best
    source = row.get("证据", "").strip() or "自述"
    if source.startswith(("旧课", "前置课")):
        return {"source": f"profile:{source}", "tier": 2, "state": "partial", "confidence": 3}
    state = LEVEL_STATE.get(row.get("自述水平", "").strip())
    if state is None:
        return None
    return {"source": "profile:自述", "tier": 1, "state": state, "confidence": 3 if score == 1000 else 2}


def learner_state_evidence(concept_id: str | None, learner_state: dict | None) -> dict | None:
    """Tier 3. A partial here is noisy, so this tier never says gap."""
    if not concept_id or not learner_state:
        return None
    concept = (learner_state.get("concepts") or {}).get(concept_id)
    if not isinstance(concept, dict) or not concept.get("attempts"):
        return None
    immediate = concept.get("evidence_tier") == "immediate"
    freshness = concept.get("freshness")
    if concept.get("last_verdict") == "mastered" and freshness == "fresh":
        state, confidence = "known", 4
    elif concept.get("last_verdict") == "mastered":
        state, confidence = "partial", 3
    elif concept.get("last_verdict") in {"partial", "retry"}:
        state, confidence = "partial", 3
    else:
        return None
    return {"source": "learner-state", "tier": 3, "state": state, "freshness": freshness,
            "confidence": confidence - 1 if immediate else confidence, "at": concept.get("last_evidence_at")}


def diagnosis_evidence(item_id: str, progress: dict | None) -> dict | None:
    """Tier 4: the lesson's own prerequisite diagnosis or bridge question."""
    if not progress:
        return None
    for competency in progress.get("competencies") or []:
        if not isinstance(competency, dict) or competency.get("id") != item_id:
            continue
        attempts = [a for a in (competency.get("assessment_attempts") or []) + (competency.get("bridge_attempts") or [])
                    if isinstance(a, dict)]
        attempts.sort(key=lambda a: a.get("at") or "")
        last = attempts[-1] if attempts else {}
        status = competency.get("status")
        if status == "ready":
            state = "known"
        elif status == "waived":
            state = "unknown"
        elif status == "needs_supplement":
            verdicts = [a.get("verdict") for a in competency.get("assessment_attempts") or [] if isinstance(a, dict)]
            state = "partial" if verdicts and verdicts[-1] == "fragile" else "gap"
        else:
            return None
        confidence = last.get("confidence") if isinstance(last.get("confidence"), int) else 4
        return {"source": "prerequisite-progress", "tier": 4, "state": state, "confidence": confidence, "at": last.get("at")}
    return None


def assess(item: dict, rows: list[dict], learner_state: dict | None, progress: dict | None) -> dict:
    found = [e for e in (diagnosis_evidence(item.get("id", ""), progress),
                         learner_state_evidence(item.get("concept_id"), learner_state),
                         background_evidence(item, rows)) if e]
    if not found:
        return {"source": "none", "tier": 0, "state": "unknown", "confidence": 1}
    found.sort(key=lambda e: (e["tier"], e.get("at") or ""), reverse=True)
    return found[0]


def is_plan_file(learning_plan: dict | None) -> bool:
    """A learning-plan.json (it carries schema_version), not the bare courses list."""
    return isinstance(learning_plan, dict) and "schema_version" in learning_plan


def lesson_core(path: Path) -> list[str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return [c["id"] for s in data.get("sections") or [] if isinstance(s, dict) for c in s.get("concepts") or []
            if isinstance(c, dict) and c.get("role") == "core" and isinstance(c.get("id"), str)]


def plan_courses(learning_plan: dict | None, plan_dir: Path | None = None) -> list[dict]:
    """The courses in study order. The bare list is taken as it is."""
    courses = [c for c in (learning_plan or {}).get("courses") or [] if isinstance(c, dict)]
    if not is_plan_file(learning_plan):
        return courses
    ranked = sorted(enumerate(courses), key=lambda ic: (ic[1]["order"] if isinstance(ic[1].get("order"), int)
                                                       else float("inf"), ic[0]))
    result = []
    for _, course in ranked:
        if course.get("declared_status") == "暂不学":
            continue
        if course.get("core_source") in {"plan-md", "declared"} and course.get("dir") and plan_dir:
            core = lesson_core(plan_dir / course["dir"] / "lesson-plan.json")
            if core is not None:
                course = {**course, "core": core, "core_source": "lesson-plan"}
        result.append(course)
    return result


def course_scope(concept_id: str | None, lesson_id: str, courses: list[dict]) -> tuple[str | None, list[str], str | None]:
    """(earlier course whose core it is, the courses that need it in plan order with this one included,
    later course whose core it is)."""
    if not concept_id or not courses:
        return None, [lesson_id], None
    ids = [c.get("id") for c in courses]
    here = ids.index(lesson_id) if lesson_id in ids else len(courses)
    earlier = next((c["id"] for c in courses[:here] if concept_id in (c.get("core") or [])), None)
    later = next((c["id"] for c in courses[here + 1:] if concept_id in (c.get("core") or [])), None)
    needing = [c.get("id") for c in courses if concept_id in (c.get("needs") or []) or c.get("id") == lesson_id]
    if lesson_id not in needing:
        needing.append(lesson_id)
    return earlier, needing, later


def reorder_is_safe(later: str, lesson_id: str, courses: list[dict]) -> bool:
    """Moving `later` before this lesson makes no cycle: it depends neither on this lesson nor on any course after it."""
    ids = [c.get("id") for c in courses]
    here = ids.index(lesson_id) if lesson_id in ids else len(courses)
    after = {lesson_id} | {c.get("id") for c in courses[here + 1:]}
    course = next(c for c in courses if c.get("id") == later)
    return not (set(course.get("depends_on") or []) & after)


def build_ledger(plan: dict, lesson_plan: dict, background: str | None = None, learner_state: dict | None = None,
                 progress: dict | None = None, learning_plan: dict | None = None, plan_dir: Path | None = None) -> dict:
    lesson_id = plan.get("lesson_id") or ""
    plan_file = is_plan_file(learning_plan)
    courses = plan_courses(learning_plan, plan_dir)
    external = {cid: c.get("id") for c in (learning_plan or {}).get("external_courses") or [] if plan_file
                and isinstance(c, dict) for cid in c.get("core") or []}
    mode = plan.get("assessment_mode") if plan.get("assessment_mode") in UNKNOWN_AS else "auto"
    section_ids = [s["id"] for s in lesson_plan.get("sections") or [] if isinstance(s, dict) and isinstance(s.get("id"), str)]
    order = {sid: index for index, sid in enumerate(section_ids)}
    rows = read_background(background) if background else []
    prerequisites = [p for p in plan.get("prerequisites") or [] if isinstance(p, dict)]
    by_key = {}
    for p in prerequisites:
        by_key[p.get("id")] = p
        if p.get("concept_id"):
            by_key[p["concept_id"]] = p

    evidence = {p.get("id"): assess(p, rows, learner_state, progress) for p in prerequisites}

    def state_of(p: dict) -> tuple[str, int]:
        found = evidence.get(p.get("id")) or assess(p, rows, learner_state, progress)
        if found["state"] == "unknown":
            return UNKNOWN_AS[mode], 0
        return found["state"], found["tier"]

    def depends_on_gap(p: dict) -> bool:
        for key in p.get("depends_on") or []:
            other = by_key.get(key) or {"id": key, "concept_id": key, "name": key}
            if state_of(other)[0] == "gap":
                return True
        return False

    gap_cluster_size: dict[str, int] = {}
    for p in prerequisites:
        if state_of(p)[0] == "gap":
            cluster = p.get("cluster") or p.get("id")
            gap_cluster_size[cluster] = gap_cluster_size.get(cluster, 0) + 1

    items = []
    needed_by: dict[str, list[str]] = {}
    reorder: list[dict] = []
    t1_count: dict[str, int] = {}
    for p in prerequisites:
        state, tier = state_of(p)
        kind = p.get("dependency_kind") or KIND_BY_DEPTH.get(p.get("depth_required"), "mech")
        required_by = [s for s in p.get("required_by") or [] if isinstance(s, str)]
        if "required_by" not in p:  # schema 1.0: keep the required_for entries that start with a section id
            required_by = [s.split()[0] for s in p.get("required_for") or [] if isinstance(s, str) and s.split()
                           and s.split()[0] in order]
        first = min(required_by, key=lambda s: order.get(s, len(order))) if required_by else None
        cluster = p.get("cluster") or p.get("id")
        earlier, needing, later = course_scope(p.get("concept_id"), lesson_id, courses)
        n_courses = len(needing)
        needed_by[cluster] = max(needed_by.get(cluster, []), needing, key=len)
        later = later if plan_file and state == "gap" and not earlier else None
        rule = "R6+" if evidence[p.get("id")]["state"] == "unknown" else ""
        if state == "known":
            disposition, placed_at, why = ("none", None, "known on tier >= 3 evidence") if tier >= 3 else \
                ("T0", first, "known on self-report or a finished course only: keep a one-line reminder")
            rule += "R1"
        elif state == "gap" and earlier:
            disposition, placed_at, why, rule = "defer_to_course", earlier, f"core of the earlier course {earlier}", rule + "R2"
        elif state == "gap" and not later and (n_courses >= 2 or depends_on_gap(p)):
            course_kind = "plan-course" if plan_file and n_courses >= 2 else "prerequisite-course"
            disposition, placed_at, rule = "T3", f"{course_kind}:{cluster}", rule + "R2"
            why = f"needed by {n_courses} courses in the plan" if n_courses >= 2 else "depends on another gap"
        elif kind == "def":
            disposition, placed_at, why, rule = "T0", first, "a definition", rule + "R3"
        elif state == "partial":
            rule += "R4"
            if first is not None and t1_count.get(first, 0) < MAX_T1_PER_SECTION and len(required_by) < 3:
                t1_count[first] = t1_count.get(first, 0) + 1
                disposition, placed_at, why = "T1", first, "partly known: a 先补三样 item"
            else:
                disposition, placed_at = "T2", first
                why = "section already has 3 T1 items" if len(required_by) < 3 else f"needed by {len(required_by)} sections"
        else:
            rule += "R5"
            if gap_cluster_size.get(cluster, 1) <= 3:
                disposition, placed_at, why = "T2", first, "fits in one bridge section"
            else:
                disposition, placed_at, why = "T3", f"prerequisite-course:{cluster}", "cluster needs more than one section"
        if later:
            why += f"; owner later: {later}"
            if reorder_is_safe(later, lesson_id, courses):
                reorder.append({"item": p.get("id"), "concept_id": p.get("concept_id"), "move": later, "before": lesson_id})
        elif plan_file and state == "gap" and not earlier and p.get("concept_id") in external:
            why += f"; owner in another plan: {external[p['concept_id']]}"
        found = dict(evidence[p.get("id")])
        items.append({
            "id": p.get("id"), "concept_id": p.get("concept_id"), "cluster": cluster,
            "dependency_kind": kind, "depth_required": p.get("depth_required"), "required_by": required_by,
            "state": state, "evidence": {k: found.get(k) for k in ("source", "tier", "freshness", "confidence", "at")
                                         if found.get(k) is not None},
            "disposition": disposition, "placed_at": placed_at, "rule": rule, "reason": why,
        })

    t2_clusters = sorted({i["cluster"] for i in items if i["disposition"] == "T2"},
                         key=lambda c: (-sum(1 for i in items if i["cluster"] == c and i["disposition"] == "T2"), c))
    # With a learning-plan.json only bridge sections for gaps (R5) are raised: a course for what was partly
    # learned would contradict R2 leaving partial items alone; such a lesson stays over 9 and --check says split.
    raisable = [c for c in t2_clusters if not plan_file
                or all("R5" in i["rule"] for i in items if i["cluster"] == c and i["disposition"] == "T2")]
    while raisable and len(section_ids) + len(t2_clusters) > MAX_SECTIONS:
        raised = raisable.pop(0)
        t2_clusters.remove(raised)
        course_kind = "plan-course" if plan_file and len(needed_by.get(raised, [])) >= 2 else "prerequisite-course"
        for i in items:
            if i["cluster"] == raised and i["disposition"] == "T2":
                i.update(disposition="T3", placed_at=f"{course_kind}:{raised}", rule=i["rule"] + "+9",
                         reason=f"over {MAX_SECTIONS} sections: bridge sections raised to a prerequisite course")

    open_items = [i for i in items if i["state"] in {"partial", "gap"}]
    counts: dict[str, int] = {}
    for i in items:
        counts[i["disposition"]] = counts.get(i["disposition"], 0) + 1
    t1_per_section: dict[str, int] = {}
    for i in items:
        if i["disposition"] == "T1":
            t1_per_section[i["placed_at"]] = t1_per_section.get(i["placed_at"], 0) + 1
    unknown_sections = sorted({s for i in items for s in i["required_by"] if s not in order})
    ledger = {
        "schema_version": "1.1" if plan_file else "1.0",
        "lesson_id": lesson_id,
        "assessment_mode": mode,
        "items": items,
        "summary": {
            "items": len(items),
            "dispositions": dict(sorted(counts.items())),
            "coverage": round(sum(1 for i in open_items if i["disposition"] != "none") / len(open_items), 3) if open_items else None,
            "t1_per_section": dict(sorted(t1_per_section.items(), key=lambda kv: order.get(kv[0], len(order)))),
            "sections": len(section_ids),
            "bridge_sections": len(t2_clusters),
            "unknown_sections": unknown_sections,
        },
    }
    if plan_file:
        plan_course_clusters = sorted({i["cluster"] for i in items if (i["placed_at"] or "").startswith("plan-course:")})
        ledger["summary"]["reorder_suggestions"] = reorder
        ledger["summary"]["plan_courses"] = [
            {"cluster": c, "items": [i["id"] for i in items if i["cluster"] == c and i["disposition"] == "T3"],
             "needed_by": needed_by[c], "before": needed_by[c][0]} for c in plan_course_clusters]
    return ledger


def check(ledger: dict) -> list[str]:
    summary = ledger["summary"]
    problems = []
    if summary["coverage"] is not None and summary["coverage"] < 1:
        problems.append(f"coverage {summary['coverage']}: a partial or gap prerequisite has no disposition")
    for section, n in summary["t1_per_section"].items():
        if n > MAX_T1_PER_SECTION:
            problems.append(f"{section} has {n} T1 items (max {MAX_T1_PER_SECTION})")
    total = summary["sections"] + summary["bridge_sections"]
    if total > MAX_SECTIONS:
        problems.append(f"{total} sections with bridge sections (max {MAX_SECTIONS}): split the course")
    for section in summary["unknown_sections"]:
        problems.append(f"required_by names {section}, which is not a section of the lesson plan")
    return problems


def suggestions(ledger: dict) -> list[str]:
    return [f"move {s['move']} before {s['before']} ({s['concept_id']})"
            for s in ledger["summary"].get("reorder_suggestions") or []]


def load_json(path: Path, what: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{what} root must be an object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("prerequisite_plan", type=Path)
    parser.add_argument("lesson_plan", type=Path)
    parser.add_argument("--profile", type=Path, help="learner profile markdown with the 相关背景 table")
    parser.add_argument("--learner-state", type=Path)
    parser.add_argument("--progress", type=Path, help="prerequisite-progress.json")
    parser.add_argument("--learning-plan", type=Path,
                        help='learning-plan.json, or {"courses": [{"id", "core": [...], "needs": [...]}]} in order')
    parser.add_argument("--plan-dir", type=Path, help="directory of the learning plan, to read each built course's core")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        ledger = build_ledger(
            load_json(args.prerequisite_plan, "prerequisite plan"),
            load_json(args.lesson_plan, "lesson plan"),
            args.profile.read_text(encoding="utf-8") if args.profile else None,
            load_json(args.learner_state, "learner state") if args.learner_state else None,
            load_json(args.progress, "prerequisite progress") if args.progress else None,
            load_json(args.learning_plan, "learning plan") if args.learning_plan else None,
            args.plan_dir,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    text = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.check:
        problems = check(ledger)
        for line in suggestions(ledger):
            print(f"SUGGEST: {line}", file=sys.stderr)
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
