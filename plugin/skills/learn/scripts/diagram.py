#!/usr/bin/env python3
"""Mermaid diagrams from a lesson plan — pasted into outline.md and, optionally, unit documents.

  diagram.py lesson-plan.json --chain          the problem chain: one box per section, arrows along depends_on
  diagram.py lesson-plan.json --system         the system map: big_picture.system_map as a left-to-right flow
  diagram.py lesson-plan.json --section s02    the section's concepts and the public-layer relations among them

Only public fields are used (titles, ids, concept names, system-map steps, fact/mechanism
relations), so nothing here can leak a criterion, a meaning or a principle. Obsidian, GitHub and
VS Code render ```mermaid blocks natively.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PUBLIC_LAYERS = {"fact", "mechanism"}
SAFE = re.compile(r"[^A-Za-z0-9_]")


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or not isinstance(plan.get("sections"), list):
        raise ValueError("lesson plan root must be an object with a sections list")
    return plan


def label(text: str) -> str:
    """A Mermaid-safe quoted label."""
    return '"' + str(text).replace('"', "'").replace("\n", " ").strip() + '"'


def node_id(prefix: str, raw: str) -> str:
    return prefix + SAFE.sub("_", str(raw))


def deferred_ids(plan: dict) -> set[str]:
    return {item.get("id") for item in (plan.get("deferred") or []) if isinstance(item, dict) and item.get("type") == "section"}


def chain(plan: dict) -> str:
    deferred = deferred_ids(plan)
    sections = [s for s in plan["sections"] if isinstance(s, dict) and s.get("id") and s["id"] not in deferred]
    lines = ["```mermaid", "flowchart TD"]
    for index, section in enumerate(sections, start=1):
        title = section.get("title") or section["id"]
        lines.append(f"    {node_id('S_', section['id'])}[{label(f'{index} {title}')}]")
    ids = [s["id"] for s in sections]
    drawn: set[tuple[str, str]] = set()
    for index, section in enumerate(sections):
        depends = [d for d in (section.get("depends_on") or []) if d in ids]
        if not depends and index > 0:
            depends = [ids[index - 1]]
        for dep in depends:
            if (dep, section["id"]) not in drawn:
                lines.append(f"    {node_id('S_', dep)} --> {node_id('S_', section['id'])}")
                drawn.add((dep, section["id"]))
    if deferred:
        lines.append(f"    %% 本次略过：{', '.join(sorted(deferred))}")
    lines.append("```")
    return "\n".join(lines)


def system(plan: dict) -> str:
    steps = [s for s in ((plan.get("big_picture") or {}).get("system_map") or []) if isinstance(s, str) and s.strip()]
    if not steps:
        raise ValueError("big_picture.system_map is empty; nothing to draw")
    lines = ["```mermaid", "flowchart LR"]
    for index, step in enumerate(steps, start=1):
        lines.append(f"    M{index}[{label(step)}]")
    for index in range(1, len(steps)):
        lines.append(f"    M{index} --> M{index + 1}")
    lines.append("```")
    return "\n".join(lines)


def section_graph(plan: dict, section_id: str) -> str:
    section = next((s for s in plan["sections"] if isinstance(s, dict) and s.get("id") == section_id), None)
    if section is None:
        raise ValueError(f"section '{section_id}' not in {plan.get('lesson_id')}")
    names: dict[str, str] = {}
    roles: dict[str, str] = {}
    for s in plan["sections"]:
        for concept in (s.get("concepts") or []) if isinstance(s, dict) else []:
            if isinstance(concept, dict) and concept.get("id"):
                names[concept["id"]] = concept.get("name") or concept["id"]
                if s is section:
                    roles[concept["id"]] = concept.get("role", "core")
    local = set(roles)
    edges = [r for r in (plan.get("relations") or []) if isinstance(r, dict)
             and r.get("layer", "mechanism") in PUBLIC_LAYERS and (r.get("from") in local or r.get("to") in local)]
    shown = set(local) | {r["from"] for r in edges} | {r["to"] for r in edges}
    lines = ["```mermaid", "flowchart LR"]
    for cid in sorted(shown, key=lambda c: (c not in local, c)):
        text = names.get(cid, cid)
        if cid in local and roles[cid] != "core":
            text += f"（{roles[cid]}）"
        shape = f"[{label(text)}]" if cid in local else f"({label(text)})"
        lines.append(f"    {node_id('C_', cid)}{shape}")
    for r in edges:
        lines.append(f"    {node_id('C_', r['from'])} -- {r.get('type')} --> {node_id('C_', r['to'])}")
    if not edges:
        lines.append("    %% 本节概念之间没有公开层的关系边")
    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", type=Path, help="lesson-plan.json")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--chain", action="store_true", help="Problem chain over the sections")
    group.add_argument("--system", action="store_true", help="System map from big_picture.system_map")
    group.add_argument("--section", metavar="ID", help="Concept relation graph of one section")
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
        if args.chain:
            print(chain(plan))
        elif args.system:
            print(system(plan))
        else:
            print(section_graph(plan, args.section))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
