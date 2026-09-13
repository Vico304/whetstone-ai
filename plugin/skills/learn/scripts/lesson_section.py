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


def render_section(plan: dict, section_id: str) -> str:
    section = find_section(plan, section_id)
    flag = " [deferred]" if section_id in deferred_ids(plan) else ""
    out = [f"# {section_id} {section.get('title')}{flag}  ({plan.get('lesson_id')}, mode {plan.get('mode', 'full')})",
           f"depends_on: {', '.join(section.get('depends_on', []) or []) or '-'}"]
    parent = section.get("parent_section")
    if isinstance(parent, dict):
        out.append(f"子节，深化 {parent.get('lesson_id')} 的 {parent.get('section_id')}")
    out.append("")
    for label, key in (("当前问题", "problem"), ("方案", "solution"), ("机制", "mechanism"), ("引出的新问题", "new_problem")):
        out += [f"## {label}", str(section.get(key) or "-"), ""]
    out += ["## 概念", *concept_lines(section), ""]
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
