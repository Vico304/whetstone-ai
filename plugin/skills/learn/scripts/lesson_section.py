#!/usr/bin/env python3
"""Print one section of a lesson plan — everything the tutor needs for that section and
nothing else — so the model never has to read the whole lesson-plan.json while teaching.

  lesson_section.py lesson-plan.json --list            one line per section
  lesson_section.py lesson-plan.json --section s03     the section: problem, solution, mechanism,
                                                       new problem, concepts, main question, criteria,
                                                       hint, meaning, tradeoffs, principle, probe
  lesson_section.py lesson-plan.json --final           final challenge, branch candidates, and the
                                                       lesson's concept names in a fixed shuffled order

The output goes to the model, not to the learner: it includes the layers that are never rendered
(meaning, tradeoffs, principle, criteria). Render for the learner only from units/<id>.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or not isinstance(plan.get("sections"), list):
        raise ValueError("lesson plan root must be an object with a sections list")
    return plan


def deferred_ids(plan: dict) -> set[str]:
    return {item.get("id") for item in (plan.get("deferred") or []) if isinstance(item, dict) and item.get("type") == "section"}


def find_section(plan: dict, section_id: str) -> dict:
    for section in plan["sections"]:
        if isinstance(section, dict) and section.get("id") == section_id:
            return section
    raise ValueError(f"section '{section_id}' not in {plan.get('lesson_id')}; --list shows the ids")


def criteria_lines(criteria: Any) -> list[str]:
    lines = []
    for index, item in enumerate(criteria or []):
        if isinstance(item, str):
            lines.append(f"- c{index + 1}: {item}")
        elif isinstance(item, dict):
            lines.append(f"- {item.get('id')} [{item.get('layer')}]: {item.get('text')}")
    return lines


def tradeoff_lines(tradeoffs: list) -> list[str]:
    lines = []
    for item in tradeoffs:
        if isinstance(item, str):
            lines.append(f"- {item}")
        elif isinstance(item, dict):
            line = f"- {item.get('text')}"
            if item.get("contested"):
                line += "  [材料在此处不一致，可展示为事实；主问题可问“你信哪个、凭什么”]"
                for side in item.get("sides") or []:
                    if isinstance(side, dict):
                        refs = "; ".join(f"{r.get('path')} {r.get('locator') or ''}".strip() for r in side.get("source_refs") or [] if isinstance(r, dict))
                        line += f"\n  一方: {side.get('claim')}" + (f" [{refs}]" if refs else "")
            lines.append(line)
    return lines


def concept_lines(section: dict) -> list[str]:
    lines = []
    for concept in section.get("concepts", []) or []:
        if not isinstance(concept, dict):
            continue
        role = concept.get("role", "core")
        ident = concept.get("id") or concept.get("name")
        line = f"- {role} {concept.get('name')} (`{ident}`, {concept.get('layer', 'mechanism')}"
        line += f", {concept['ontology']}" if concept.get("ontology") else ""
        line += f"): {concept.get('explanation')}"
        contrast = concept.get("contrast")
        if isinstance(contrast, dict):
            line += f"\n  易混对: {contrast.get('with')} —— 差在 {contrast.get('differs_in')}"
        for index, case in enumerate(concept.get("cases") or []):
            if isinstance(case, dict):
                refs = "; ".join(f"{r.get('path')} {r.get('locator') or ''}".strip() for r in case.get("source_refs") or [] if isinstance(r, dict))
                line += f"\n  案例 {index + 1}: {case.get('summary')}" + (f" [{refs}]" if refs else "")
        check = concept.get("check")
        if isinstance(check, dict) and check.get("prompt"):
            line += f"\n  验收题: {check['prompt']}"
            line += "".join("\n  " + c for c in criteria_lines(check.get("criteria")))
        lines.append(line)
    return lines


def render_list(plan: dict) -> str:
    deferred = deferred_ids(plan)
    lines = [f"{plan.get('lesson_id')}  mode: {plan.get('mode', 'full')}  shape: {plan.get('shape', 'linear')}  sections: {len(plan['sections'])}"]
    for section in plan["sections"]:
        if not isinstance(section, dict):
            continue
        concepts = section.get("concepts", []) or []
        roles = {}
        for concept in concepts:
            if isinstance(concept, dict):
                roles[concept.get("role", "core")] = roles.get(concept.get("role", "core"), 0) + 1
        flag = "  [deferred]" if section.get("id") in deferred else ""
        depends = ",".join(section.get("depends_on", []) or []) or "-"
        lines.append(f"- {section.get('id')} {section.get('title')}{flag}  depends_on: {depends}  concepts: "
                     + " ".join(f"{k}={v}" for k, v in sorted(roles.items())))
    return "\n".join(lines)


def cross_lesson_lines(plan: dict, section: dict) -> list[str]:
    """Relations from this section's concepts to a concept carried over from an earlier course."""
    local_all = {c["id"] for s in (plan.get("sections") or []) if isinstance(s, dict)
                 for c in (s.get("concepts") or []) if isinstance(c, dict) and c.get("id")}
    names = {c["id"]: c.get("name") or c["id"] for s in (plan.get("sections") or []) if isinstance(s, dict)
             for c in (s.get("concepts") or []) if isinstance(c, dict) and c.get("id")}
    here = {c["id"] for c in (section.get("concepts") or []) if isinstance(c, dict) and c.get("id")}
    lines = []
    for relation in plan.get("relations") or []:
        if not isinstance(relation, dict):
            continue
        ends = (relation.get("from"), relation.get("to"))
        outside = [e for e in ends if e not in local_all]
        if not outside or not any(e in here for e in ends):
            continue
        lines.append(f"- {names.get(ends[0], ends[0])} --{relation.get('type')}--> {names.get(ends[1], ends[1])}"
                     f"　依据：{relation.get('rationale') or '-'}")
    return lines


def render_section(plan: dict, section_id: str) -> str:
    section = find_section(plan, section_id)
    flag = " [deferred]" if section_id in deferred_ids(plan) else ""
    out = [f"# {section_id} {section.get('title')}{flag}  ({plan.get('lesson_id')}, mode {plan.get('mode', 'full')})",
           f"depends_on: {', '.join(section.get('depends_on', []) or []) or '-'}"]
    parent = section.get("parent_section")
    if isinstance(parent, dict):
        kind = section.get("review_kind")
        label = {"repeat": "复习节，重访", "deepen": "子节，深化"}.get(kind, "子节，深化")
        out.append(f"{label} {parent.get('lesson_id')} 的 {parent.get('section_id')}" + ("（先作答，判定后再揭示本节文档）" if kind else ""))
    out.append("")
    for label, key in (("当前问题", "problem"), ("方案", "solution"), ("机制", "mechanism"), ("引出的新问题", "new_problem")):
        out += [f"## {label}", str(section.get(key) or "-"), ""]
    out += ["## 概念", *concept_lines(section), ""]
    position = section.get("position")
    steps = section.get("steps")
    if position or (isinstance(steps, list) and steps):
        names = {c["id"]: c.get("name") or c["id"] for s in (plan.get("sections") or []) if isinstance(s, dict)
                 for c in (s.get("concepts") or []) if isinstance(c, dict) and c.get("id")}
    if position:
        out += ["## 返回位置", f"本节展开的是系统图上的 {names.get(position, position)}（`{position}`）", ""]
    if isinstance(steps, list) and steps:
        out += ["## 步骤（过程讲解节；验收时合上本表）"]
        for index, step in enumerate(steps, start=1):
            if isinstance(step, dict):
                actor = names.get(step.get("actor"), step.get("actor"))
                target = f" → {names.get(step.get('target'), step.get('target'))}" if step.get("target") else ""
                out.append(f"{index}. {actor}{target}：{step.get('action')}　变化：{step.get('changes')}")
        out.append("")
    crossing = cross_lesson_lines(plan, section)
    if crossing:
        out += ["## 跨课关系（不展示，先问后揭示：protocol/predict.md）", *crossing, ""]
    probe = section.get("probe")
    if isinstance(probe, dict) and probe.get("prompt"):
        out += ["## 探测题（骨架课，教学前）", probe["prompt"], *criteria_lines(probe.get("criteria")), ""]
    checkpoint = section.get("checkpoint") or {}
    out += ["## 主问题（原样放进讲义的“轮到你”）", str(checkpoint.get("prompt") or "-"), "",
            "## 判定标准（不展示）", *(criteria_lines(checkpoint.get("criteria")) or ["-"]), "",
            "## 提示（首次作答后按需）", str(checkpoint.get("hint") or "-"), ""]
    out += ["## 意义（不展示，出题素材）", str(section.get("meaning") or "-"), ""]
    out += ["## 取舍（不展示，追问素材）", *(tradeoff_lines(section.get("tradeoffs") or []) or ["-"]), ""]
    out += ["## 思想（不展示，迁移题素材）", str(section.get("principle") or "-")]
    return "\n".join(out)


def shuffled_concept_names(plan: dict) -> list[str]:
    """Core + supporting concept names of the non-deferred sections, in an order fixed by the lesson id."""
    deferred = deferred_ids(plan)
    names: list[str] = []
    for section in plan["sections"]:
        if not isinstance(section, dict) or section.get("id") in deferred:
            continue
        if section.get("kind") == "structure":
            continue  # a structure section is a reference to come back to, not something to rebuild from memory
        for concept in section.get("concepts", []) or []:
            if isinstance(concept, dict) and concept.get("role", "core") in {"core", "supporting"} and concept.get("name") not in names:
                names.append(concept["name"])
    seed = plan.get("lesson_id") or "lesson"
    return sorted(names, key=lambda n: hashlib.sha1(f"{seed}:{n}".encode("utf-8")).hexdigest())


def render_final(plan: dict) -> str:
    out = [f"# 结课  ({plan.get('lesson_id')}, mode {plan.get('mode', 'full')}, shape {plan.get('shape', 'linear')})", ""]
    final = plan.get("final_challenge")
    if isinstance(final, dict):
        out += ["## 结课题（迁移 / 桥接）", str(final.get("prompt") or "-"), *criteria_lines(final.get("criteria")), ""]
    elif isinstance(final, str):
        out += ["## 结课题（迁移 / 桥接）", final, ""]
    out += ["## 本课概念名（打乱顺序，链重建时只给这份，不给节标题和顺序）", *(f"- {n}" for n in shuffled_concept_names(plan)), ""]
    system_map = (plan.get("big_picture") or {}).get("system_map")
    if isinstance(system_map, dict):
        names = {c["id"]: c.get("name") or c["id"] for s in (plan.get("sections") or []) if isinstance(s, dict)
                 for c in (s.get("concepts") or []) if isinstance(c, dict) and c.get("id")}
        out += ["## 系统图（路线重建：给起点与终点，只判这一条路径）"]
        for item in system_map.get("components") or []:
            if isinstance(item, dict) and item.get("id"):
                inside = f"，在 {names.get(item['parent'], item['parent'])} 里" if item.get("parent") else ""
                out.append(f"- {names.get(item['id'], item['id'])}（`{item['id']}`）{inside}")
        for link in system_map.get("links") or []:
            if isinstance(link, dict):
                out.append(f"- {names.get(link.get('from'), link.get('from'))} → "
                           f"{names.get(link.get('to'), link.get('to'))}：{link.get('label')}")
        out.append("")
    candidates = plan.get("branch_candidates") or []
    if candidates:
        out += ["## 分支候选（骨架课）"]
        for item in candidates:
            if isinstance(item, dict):
                out.append(f"- {item.get('id')} {item.get('title') or ''}: {item.get('principle') or item.get('reason') or ''} "
                           f"| path {item.get('path') or item.get('material') or '-'} | relevance {item.get('work_relevance') or '-'} | status {item.get('status') or 'candidate'}")
        out.append("")
    if plan.get("prerequisite_of"):
        out += [f"## 前置课：结课后回 {plan['prerequisite_of']} 第 {plan.get('blocked_at')} 节（prerequisite/return.md）"]
    return "\n".join(out).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", type=Path, help="lesson-plan.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="One line per section")
    group.add_argument("--section", metavar="ID", help="Print this section (all layers)")
    group.add_argument("--final", action="store_true", help="Final challenge, shuffled concept names, branch candidates")
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        if args.list:
            print(render_list(plan))
        elif args.section:
            print(render_section(plan, args.section))
        else:
            print(render_final(plan))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
