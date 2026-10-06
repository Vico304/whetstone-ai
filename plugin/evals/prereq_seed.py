#!/usr/bin/env python3
"""Seed a draft prerequisite plan (schema 1.1) from what a model already wrote into lesson-plan.json, so
gap_ledger.py has an input when no prerequisite-plan.json was written, and so a plan the model did write can
be compared with what the outline itself implies.

Four rules, each item records which one produced it (`seed.rule`) and the text it came from:
  node      a lower-level material node named in uncertainties[], a coverage reason or a deferred reason,
            e.g. "L0-收益率的度量" or "L0（收益率的度量、风险是什么）". "Lower" means a smaller L<n> than the
            lowest level among the material file names; when the files carry no level, the sentence must
            also say 前置 / 依赖 / 已经知道 / 准备度.
  assumed   a concept whose explanation or source_refs locator cites the material's 「你已经知道的」 part.
  section   when no node was found: each 「你已经知道的」 coverage row, the part itself is the item.
  code      the lesson cites code files: reading the code is a tool prerequisite of the sections citing it.
required_by of node and section items is the sections that carry the 「你已经知道的」 rows (the first section
when there are none). The draft has no diagnostic questions, so it does not pass validate_prerequisites; the
readiness is unevaluated. assessment_mode comes from prerequisite_check in --profile (default auto).

--against PLAN compares the draft with a written plan: a draft item matches a written item when the concept
ids are equal, when the draft's code item meets a written tool item, or when one part of the draft item's name
(split at 与 / 和 / 、, filler words dropped) has at least half of its character pairs in the written item's
text. It prints the comparison as JSON instead of the draft (write the draft with --output). Exit 2 when an
input cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KNOWN_PART = "你已经知道的"
CODE_SUFFIXES = (".py", ".ipynb", ".r", ".js", ".ts", ".rs", ".go", ".java", ".c", ".cpp", ".sql", ".sh")
LEVEL_FILE = re.compile(r"(?:^|/)L(\d+)-")
NODE_DASH = re.compile(r"L(\d+)-([^\s、，。,；;：:（）()「」『』“”\"'`]+)")
NODE_GROUP = re.compile(r"L(\d+)\s*层?\s*[（(]([^）)]+)[）)]")
NODE_TAIL = re.compile(r"等|不在|节点|讲义|材料")  # "L1-随机游走与市场有效性等前置节点" ends before 等
PREREQ_WORDS = re.compile(r"前置|依赖|已经知道|准备度")
NAME_SPLIT = re.compile(r"[与和、及/]")
FILLER = re.compile(r"是什么|为什么|怎么|的")
KIND = {"fact": ("def", "fact"), "mechanism": ("mech", "mechanism")}


def load_json(path: Path, what: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{what} root must be an object")
    return data


def heading_text(value: str | None) -> str:
    return (value or "").lstrip("#").strip()


def nodes_in(text: str) -> list[tuple[int, str]]:
    found = [(int(level), NODE_TAIL.split(name)[0].strip()) for level, name in NODE_DASH.findall(text)]
    for level, inner in NODE_GROUP.findall(text):
        found += [(int(level), part.strip()) for part in re.split(r"[、，,]", inner)]
    return [(level, name) for level, name in found if name]


def material_level(paths: list[str]) -> int | None:
    levels = [int(m.group(1)) for p in paths for m in [LEVEL_FILE.search(p)] if m]
    return min(levels) if levels else None


def pairs(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text)
    return {text[i:i + 2] for i in range(len(text) - 1)} or ({text} if text else set())


def name_parts(name: str) -> list[str]:
    parts = [FILLER.sub("", part).strip() for part in NAME_SPLIT.split(re.sub(r"^L\d+-", "", name))]
    return [p for p in parts if p] or [name]


def concepts(lesson: dict) -> list[tuple[str, dict]]:
    return [(s["id"], c) for s in lesson.get("sections") or [] if isinstance(s, dict) and isinstance(s.get("id"), str)
            for c in s.get("concepts") or [] if isinstance(c, dict) and isinstance(c.get("id"), str)]


def ref_paths(lesson: dict) -> list[tuple[str, str]]:
    """(section id, source path) for every source_refs entry of a section or its concepts."""
    found = []
    for s in lesson.get("sections") or []:
        if not isinstance(s, dict):
            continue
        refs = list(s.get("source_refs") or []) + [r for c in s.get("concepts") or [] if isinstance(c, dict)
                                                   for r in c.get("source_refs") or []]
        found += [(s.get("id"), r["path"]) for r in refs if isinstance(r, dict) and isinstance(r.get("path"), str)]
    return found


def seed(lesson: dict, profile: str | None = None) -> dict:
    section_ids = [s["id"] for s in lesson.get("sections") or [] if isinstance(s, dict) and isinstance(s.get("id"), str)]
    order = {sid: i for i, sid in enumerate(section_ids)}
    coverage = [c for c in lesson.get("coverage") or [] if isinstance(c, dict)]
    known_rows = [c for c in coverage if heading_text(c.get("heading")) == KNOWN_PART]
    known_sections = sorted({c["section_id"] for c in known_rows if c.get("section_id") in order}, key=order.get)
    default_sections = known_sections or section_ids[:1]
    paths = [c.get("path") or "" for c in coverage] + [p for _, p in ref_paths(lesson)]
    level = material_level(paths)
    domains = [cid.split(".")[0] for _, c in concepts(lesson) for cid in [c["id"]] if "." in cid]
    domain = max(set(domains), key=domains.count) if domains else "material"
    items: list[dict] = []

    def add(**item) -> None:
        item["id"] = f"q{len(items) + 1:02d}"
        item.setdefault("required_for", [f"{s} 用到" for s in item["required_by"]] or ["本课用到"])
        items.append(item)

    sources = [(f"uncertainties[{i}]", "lesson-plan.json", text) for i, text in enumerate(lesson.get("uncertainties") or [])
               if isinstance(text, str)]
    sources += [(f"coverage {c.get('path')} {heading_text(c.get('heading'))}", c.get("path") or "lesson-plan.json", c["reason"])
                for c in coverage if isinstance(c.get("reason"), str)]
    sources += [(f"deferred {d.get('id')}", "lesson-plan.json", d["reason"]) for d in lesson.get("deferred") or []
                if isinstance(d, dict) and isinstance(d.get("reason"), str)]
    seen_nodes: set[tuple[int, str]] = set()
    for locator, path, text in sources:
        for node_level, name in nodes_in(text):
            if (node_level, name) in seen_nodes:
                continue
            if level is not None and node_level >= level:
                continue
            if level is None and not PREREQ_WORDS.search(text):
                continue
            seen_nodes.add((node_level, name))
            add(name=f"L{node_level}-{name}", concept_id=f"{domain}.L{node_level}-{name}", cluster=f"L{node_level}",
                required_by=list(default_sections), depth_required="mechanism", dependency_kind="mech",
                why_needed=f"大纲提到本课依赖材料之外的 L{node_level} 节点「{name}」",
                source_refs=[{"path": path, "locator": locator, "support": "entailed", "note": text[:120]}],
                seed={"rule": "node", "text": text})
    for section_id, concept in concepts(lesson):
        cited = [r for r in concept.get("source_refs") or [] if isinstance(r, dict) and KNOWN_PART in str(r.get("locator"))]
        if not cited and KNOWN_PART not in str(concept.get("explanation")):
            continue
        dependency_kind, depth = KIND.get(concept.get("layer"), ("mech", "mechanism"))
        path_list = concept.get("domain_path") if isinstance(concept.get("domain_path"), list) else []
        add(name=concept.get("name") or concept["id"], concept_id=concept["id"],
            cluster=str(path_list[-1]) if path_list else "assumed", required_by=[section_id], depth_required=depth,
            dependency_kind=dependency_kind,
            why_needed=f"{section_id} 的概念「{concept.get('name') or concept['id']}」按材料的「你已经知道的」当作已知",
            source_refs=[{"path": r.get("path") or "lesson-plan.json", "locator": r.get("locator") or KNOWN_PART,
                          "support": "entailed", "note": "概念引用了「你已经知道的」"} for r in cited]
            or [{"path": "lesson-plan.json", "locator": f"{section_id} {concept['id']}", "support": "entailed",
                 "note": "概念说明引用了「你已经知道的」"}],
            seed={"rule": "assumed", "text": concept.get("explanation") or ""})
    for row in known_rows if not seen_nodes else []:
        sections = [row["section_id"]] if row.get("section_id") in order else list(default_sections)
        add(name=f"{row.get('path')} 的「你已经知道的」", concept_id=f"{domain}.known:{row.get('path')}",
            cluster="你已经知道的", required_by=sections, depth_required="mechanism", dependency_kind="mech",
            why_needed=f"材料 {row.get('path')} 用「你已经知道的」一节列出假定已会的内容（大纲记作 {row.get('disposition')}）",
            source_refs=[{"path": row.get("path") or "lesson-plan.json", "locator": f"## {KNOWN_PART}",
                          "support": "entailed", "note": row.get("reason") or f"disposition {row.get('disposition')}"}],
            seed={"rule": "section", "text": row.get("reason") or ""})
    code_sections: dict[str, list[str]] = {}
    for section_id, path in ref_paths(lesson):
        if path.lower().endswith(CODE_SUFFIXES):
            code_sections.setdefault(path, [])
            if section_id not in code_sections[path]:
                code_sections[path].append(section_id)
    if code_sections:
        sections = sorted({s for ss in code_sections.values() for s in ss}, key=order.get)
        add(name="读懂配套代码", concept_id=f"code.{lesson.get('lesson_id') or 'lesson'}-reading", cluster="code",
            required_by=sections, depth_required="tool", dependency_kind="tool",
            why_needed=f"{len(sections)} 节的来源指向代码文件，读懂这些代码是本课默认会的",
            source_refs=[{"path": p, "locator": p, "support": "entailed", "note": "、".join(s)} for p, s in sorted(code_sections.items())],
            seed={"rule": "code", "text": "、".join(sorted(code_sections))})
    mode = "auto"
    if profile:
        found = re.search(r"prerequisite_check\s*=\s*`?(always|auto|skip)", profile)
        if found:
            mode = found.group(1)
    return {
        "schema_version": "1.1",
        "lesson_id": lesson.get("lesson_id") or "",
        "assessment_mode": mode,
        "scope_statement": "由 prereq_seed.py 从 lesson-plan.json 推出的草稿，只列大纲本身暗示的前置，不含诊断题。",
        "prerequisites": items,
        "research_policy": {"trigger": ["fragile", "gap", "misconception"],
                            "source_priority": ["official_or_primary", "standards_or_textbooks", "reputable_secondary"],
                            "separate_external_claims": True},
        "uncertainties": ["准备度未评估：草稿未作答，也没有诊断题。"],
        "seed_summary": {"material_level": level, "rules": {r: sum(1 for i in items if i["seed"]["rule"] == r)
                                                             for r in ("node", "assumed", "section", "code")}},
    }


def item_text(item: dict) -> str:
    refs = " ".join(f"{r.get('locator')} {r.get('note')}" for r in item.get("source_refs") or [] if isinstance(r, dict))
    return " ".join(str(item.get(k) or "") for k in ("name", "concept_id", "why_needed")) + " " + \
        " ".join(item.get("required_for") or []) + " " + refs


def match_score(draft_item: dict, written: dict) -> float:
    if draft_item.get("concept_id") and draft_item.get("concept_id") == written.get("concept_id"):
        return 1.0
    if draft_item["seed"]["rule"] == "code" and written.get("dependency_kind") == "tool":
        return 1.0
    text = pairs(item_text(written))
    return max((len(pairs(part) & text) / len(pairs(part)) for part in name_parts(draft_item.get("name") or "")
                if pairs(part)), default=0.0)


def compare(draft: dict, written: dict, threshold: float = 0.5) -> dict:
    drafted = [p for p in draft.get("prerequisites") or [] if isinstance(p, dict)]
    plan = [p for p in written.get("prerequisites") or [] if isinstance(p, dict)]
    links = [{"draft": d["id"], "written": w.get("id"), "score": round(match_score(d, w), 3)}
             for d in drafted for w in plan]
    links = [link for link in links if link["score"] >= threshold]
    matched_written = {link["written"] for link in links}
    matched_draft = {link["draft"] for link in links}
    return {
        "lesson_id": written.get("lesson_id"),
        "draft_items": len(drafted),
        "written_items": len(plan),
        "links": links,
        "written_found": sorted(matched_written),
        "written_missed": [{"id": w.get("id"), "name": w.get("name"), "concept_id": w.get("concept_id")}
                           for w in plan if w.get("id") not in matched_written],
        "draft_unmatched": [{"id": d["id"], "name": d["name"], "rule": d["seed"]["rule"]}
                            for d in drafted if d["id"] not in matched_draft],
        "recall": round(len(matched_written) / len(plan), 3) if plan else None,
        "precision": round(len(matched_draft) / len(drafted), 3) if drafted else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("lesson_plan", type=Path)
    parser.add_argument("--profile", type=Path, help="learner profile markdown; prerequisite_check sets assessment_mode")
    parser.add_argument("--against", type=Path, help="a written prerequisite-plan.json to compare the draft with")
    parser.add_argument("--output", type=Path, help="write the draft here")
    args = parser.parse_args(argv)
    try:
        lesson = load_json(args.lesson_plan, "lesson plan")
        draft = seed(lesson, args.profile.read_text(encoding="utf-8") if args.profile else None)
        written = load_json(args.against, "prerequisite plan") if args.against else None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    text = json.dumps(draft, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    if written is not None:
        sys.stdout.write(json.dumps(compare(draft, written), ensure_ascii=False, indent=2) + "\n")
    elif not args.output:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
