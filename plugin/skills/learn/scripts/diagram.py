#!/usr/bin/env python3
"""Mermaid diagrams from a lesson plan — pasted into outline.md and, optionally, unit documents.

  diagram.py lesson-plan.json --chain          the problem chain: one box per section, arrows along depends_on
  diagram.py lesson-plan.json --system         the system map: components nested by parent, links labelled
  diagram.py lesson-plan.json --section s02    a chain or structure section's concepts; a process section's run

Only public fields are used (titles, ids, concept names, the system map, fact/mechanism relations
and the steps of a process section), so nothing here can leak a criterion, a meaning or a
principle. Obsidian, GitHub and VS Code render ```mermaid blocks natively.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

PUBLIC_LAYERS = {"fact", "mechanism"}
SAFE = re.compile(r"[^A-Za-z0-9_]")
RELATION_WORDS = {"is_a": "是一种", "part_of": "属于", "depends_on": "依赖", "causes": "导致",
                  "enables": "促成", "implements": "实现", "contrasts_with": "对照",
                  "instance_of": "实例", "prerequisite_for": "前置"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mermaid_fit = _load("mermaid_fit")


def fenced(body: list[str], prefer: str = "TD") -> str:
    """A flowchart in a Mermaid fence, laid out to fit the width of a note.

    Direction is the single largest factor in how wide a diagram ends up: LR grows with the depth
    of the chain, TD with the widest fan-out. Neither the model writing the plan nor the learner
    reading the note can see that, so `mermaid_fit` decides it here — and folds long names and
    labels when the result is still too wide. `prefer` only settles a tie.
    """
    return mermaid_fit.fit("\n".join(["```mermaid", f"flowchart {prefer}"] + body + ["```"]))[0]


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


def concept_names(plan: dict) -> dict[str, str]:
    return {c["id"]: c.get("name") or c["id"]
            for s in plan.get("sections") or [] if isinstance(s, dict)
            for c in (s.get("concepts") or []) if isinstance(c, dict) and c.get("id")}


def structured_map(plan: dict) -> dict | None:
    """{components: {id: parent}, links: [...]} when the plan carries a system map of parts, else None."""
    system_map = (plan.get("big_picture") or {}).get("system_map")
    if not isinstance(system_map, dict):
        return None
    components = {item["id"]: item.get("parent")
                  for item in (system_map.get("components") or []) if isinstance(item, dict) and item.get("id")}
    links = [link for link in (system_map.get("links") or []) if isinstance(link, dict)
             and link.get("from") in components and link.get("to") in components]
    return {"components": components, "links": links}


def nested_nodes(components: dict[str, Any], names: dict[str, str], indent: str = "    ") -> list[str]:
    """Parts as Mermaid nodes; a part with children becomes a subgraph so containment reads as nesting."""
    children: dict[Any, list[str]] = {}
    for cid, parent in components.items():
        children.setdefault(parent, []).append(cid)
    lines: list[str] = []

    def draw(cid: str, depth: int) -> None:
        pad = indent + "    " * depth
        text = names.get(cid, cid)
        if cid in children:
            lines.append(f"{pad}subgraph {node_id('C_', cid)}[{label(text)}]")
            for child in sorted(children[cid]):
                draw(child, depth + 1)
            lines.append(f"{pad}end")
        else:
            lines.append(f"{pad}{node_id('C_', cid)}[{label(text)}]")

    for root in sorted(children.get(None, [])):
        draw(root, 0)
    orphans = [cid for cid, parent in components.items() if parent is not None and parent not in components]
    for cid in sorted(orphans):  # a parent outside the map: draw the part on its own rather than dropping it
        draw(cid, 0)
    return lines


def deferred_ids(plan: dict) -> set[str]:
    return {item.get("id") for item in (plan.get("deferred") or []) if isinstance(item, dict) and item.get("type") == "section"}


def chain(plan: dict) -> str:
    deferred = deferred_ids(plan)
    sections = [s for s in plan["sections"] if isinstance(s, dict) and s.get("id") and s["id"] not in deferred]
    lines: list[str] = []
    for index, section in enumerate(sections, start=1):
        title = section.get("title") or section["id"]
        mark = {"structure": "（结构）", "process": "（过程）"}.get(section.get("kind"), "")
        lines.append(f"    {node_id('S_', section['id'])}[{label(f'{index} {title}{mark}')}]")
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
    return fenced(lines)


def system(plan: dict) -> str:
    structured = structured_map(plan)
    if structured is not None:
        components = structured["components"]
        if not components:
            raise ValueError("big_picture.system_map has no components; nothing to draw")
        names = concept_names(plan)
        lines = nested_nodes(components, names)
        for link in structured["links"]:
            lines.append(f"    {node_id('C_', link['from'])} -- {label(link.get('label') or '')} --> "
                         f"{node_id('C_', link['to'])}")
        if not structured["links"]:
            lines.append("    %% 部件之间还没有连线")
        return fenced(lines)
    steps = [s for s in ((plan.get("big_picture") or {}).get("system_map") or []) if isinstance(s, str) and s.strip()]
    if not steps:
        raise ValueError("big_picture.system_map is empty; nothing to draw")
    lines = []
    for index, step in enumerate(steps, start=1):
        lines.append(f"    M{index}[{label(step)}]")
    for index in range(1, len(steps)):
        lines.append(f"    M{index} --> M{index + 1}")
    return fenced(lines)


def structure_section_graph(plan: dict, section: dict, structured: dict) -> str:
    """The parts this section places, with the parents they sit in, and the links among them."""
    components = structured["components"]
    here = {c["id"] for c in (section.get("concepts") or []) if isinstance(c, dict) and c.get("id")}
    shown = {cid for cid in here if cid in components}
    if not shown:
        raise ValueError(f"section '{section.get('id')}' places no component of big_picture.system_map")
    for cid in list(shown):  # keep the parents so the nesting still reads
        walk = components.get(cid)
        while walk is not None and walk not in shown:
            shown.add(walk)
            walk = components.get(walk)
    names = concept_names(plan)
    lines = nested_nodes({cid: components[cid] if components.get(cid) in shown else None for cid in shown}, names)
    drawn = 0
    for link in structured["links"]:
        if link["from"] in shown and link["to"] in shown:
            lines.append(f"    {node_id('C_', link['from'])} -- {label(link.get('label') or '')} --> "
                         f"{node_id('C_', link['to'])}")
            drawn += 1
    if not drawn:
        lines.append("    %% 这些部件之间还没有连线")
    return fenced(lines)


def process_section_graph(plan: dict, section: dict) -> str:
    """One run, step by step: who acts on whom, and what changes."""
    steps = [step for step in (section.get("steps") or []) if isinstance(step, dict)]
    if not steps:
        raise ValueError(f"section '{section.get('id')}' has no steps to draw")
    names = concept_names(plan)
    order: list[str] = []
    for step in steps:
        for end in ("actor", "target"):
            cid = step.get(end)
            if cid and cid not in order:
                order.append(cid)
    def plain(text: Any) -> str:  # a sequence diagram reads to the end of the line: no newlines, no semicolons
        return str(text or "").replace("\n", " ").replace(";", "；").strip()

    lines = ["```mermaid", "sequenceDiagram"]
    for cid in order:
        lines.append(f"    participant {node_id('P_', cid)} as {plain(names.get(cid, cid))}")
    for step in steps:
        actor, target = step.get("actor"), step.get("target")
        action = plain(step.get("action"))
        if target:
            lines.append(f"    {node_id('P_', actor)}->>{node_id('P_', target)}: {action}")
        else:
            lines.append(f"    Note over {node_id('P_', actor)}: {action}")
        changes = plain(step.get("changes"))
        if changes:
            lines.append(f"    Note over {node_id('P_', target or actor)}: {changes}")
    lines.append("```")
    return "\n".join(lines)


def section_graph(plan: dict, section_id: str) -> str:
    section = next((s for s in plan["sections"] if isinstance(s, dict) and s.get("id") == section_id), None)
    if section is None:
        raise ValueError(f"section '{section_id}' not in {plan.get('lesson_id')}")
    if section.get("kind") == "process":
        return process_section_graph(plan, section)
    structured = structured_map(plan)
    if section.get("kind") == "structure" and structured is not None:
        return structure_section_graph(plan, section, structured)
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
    lines: list[str] = []
    for cid in sorted(shown, key=lambda c: (c not in local, c)):
        text = names.get(cid, cid)
        if cid in local and roles[cid] != "core":
            text += f"（{roles[cid]}）"
        shape = f"[{label(text)}]" if cid in local else f"({label(text)})"
        lines.append(f"    {node_id('C_', cid)}{shape}")
    for r in edges:
        word = RELATION_WORDS.get(r.get("type"), r.get("type"))
        lines.append(f"    {node_id('C_', r['from'])} -- {label(word)} --> {node_id('C_', r['to'])}")
    if not edges:
        lines.append("    %% 本节概念之间没有公开层的关系边")
    return fenced(lines, prefer="LR")


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
