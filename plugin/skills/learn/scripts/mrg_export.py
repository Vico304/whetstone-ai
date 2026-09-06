#!/usr/bin/env python3
"""Export a lesson plan (schema 1.0 or 1.1) as a layered machine reference graph.

Writes two files:
  <out>/<lesson_id>.json       public layer: fact / mechanism nodes and edges, section skeleton
  <out>/<lesson_id>.deep.json  high layer: rationale / principle nodes and edges, meaning,
                               tradeoffs, principle text and checkpoint criteria per section

Only the public file may ever be rendered for the learner (teaching guide, concept notes,
queries). The deep file is loaded solely for assessment and question generation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_lesson", SCRIPT_DIR / "validate_lesson.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validate_lesson = _load_validator()
PUBLIC_LAYERS = validate_lesson.PUBLIC_LAYERS
LAYERS = validate_lesson.LAYERS

SLUG_STRIP = re.compile(r"[^\w]+", re.UNICODE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(text: str) -> str:
    """Lowercase, NFC-normalised slug that keeps non-ascii letters (Chinese names stay readable)."""
    normalized = unicodedata.normalize("NFC", text.strip()).casefold()
    slug = SLUG_STRIP.sub("-", normalized).strip("-")
    return slug or "concept"


def concept_id(plan: dict, concept: dict) -> str:
    if isinstance(concept.get("id"), str) and concept["id"].strip():
        return concept["id"]
    return f"{slugify(str(plan.get('lesson_id', 'lesson')))}.{slugify(concept.get('name', ''))}"


def build_nodes(plan: dict) -> dict[str, dict]:
    """Merge concept mentions across sections into one node per id."""
    nodes: dict[str, dict] = {}
    lesson_id = plan.get("lesson_id")
    for section in plan.get("sections", []):
        section_refs = section.get("source_refs", [])
        for concept in section.get("concepts", []):
            cid = concept_id(plan, concept)
            node = nodes.get(cid)
            if node is None:
                node = {
                    "id": cid,
                    "name": concept.get("name"),
                    "aliases": list(concept.get("aliases", [])),
                    "domain_path": list(concept.get("domain_path", [])),
                    "layer": concept.get("layer", "mechanism"),
                    "lesson_id": lesson_id,
                    "section_ids": [],
                    "explanation": concept.get("explanation"),
                    "source_refs": [],
                }
                nodes[cid] = node
            else:
                for alias in concept.get("aliases", []):
                    if alias not in node["aliases"]:
                        node["aliases"].append(alias)
            if section["id"] not in node["section_ids"]:
                node["section_ids"].append(section["id"])
            for ref in section_refs:
                if ref not in node["source_refs"]:
                    node["source_refs"].append(ref)
    return nodes


def build_edges(plan: dict) -> list[dict]:
    edges: list[dict] = []
    for relation in plan.get("relations", []) or []:
        edge = {
            "id": relation.get("id"),
            "from": relation.get("from"),
            "to": relation.get("to"),
            "type": relation.get("type"),
            "layer": relation.get("layer", "mechanism"),
            "source_refs": list(relation.get("source_refs", [])),
        }
        if relation.get("rationale"):
            edge["rationale"] = relation["rationale"]
        edges.append(edge)
    return edges


def section_skeleton(plan: dict) -> list[dict]:
    """What the learner may see about each section: problem, solution, mechanism, new problem."""
    skeleton = []
    for section in plan.get("sections", []):
        skeleton.append(
            {
                "id": section["id"],
                "title": section.get("title"),
                "depends_on": list(section.get("depends_on", [])),
                "problem": section.get("problem"),
                "solution": section.get("solution"),
                "mechanism": section.get("mechanism"),
                "new_problem": section.get("new_problem"),
                "concept_ids": [concept_id(plan, concept) for concept in section.get("concepts", [])],
                "checkpoint_prompt": (section.get("checkpoint") or {}).get("prompt"),
            }
        )
    return skeleton


def section_deep(plan: dict) -> list[dict]:
    """Rationale-layer material per section: never rendered, used for questions and assessment."""
    deep = []
    for section in plan.get("sections", []):
        checkpoint = section.get("checkpoint") or {}
        criteria = []
        for index, criterion in enumerate(checkpoint.get("criteria", []) or []):
            if isinstance(criterion, str):
                criteria.append({"id": f"c{index + 1}", "text": criterion, "layer": "mechanism"})
            elif isinstance(criterion, dict):
                criteria.append({"id": criterion.get("id"), "text": criterion.get("text"), "layer": criterion.get("layer")})
        deep.append(
            {
                "id": section["id"],
                "meaning": section.get("meaning"),
                "tradeoffs": list(section.get("tradeoffs", []) or []),
                "principle": section.get("principle"),
                "criteria": criteria,
                "hint": checkpoint.get("hint"),
            }
        )
    return deep


def export(plan: dict) -> tuple[dict, dict]:
    nodes = build_nodes(plan)
    edges = build_edges(plan)
    base = {
        "schema_version": "1.1",
        "lesson_id": plan.get("lesson_id"),
        "title": plan.get("title"),
        "source_schema_version": validate_lesson.schema_version(plan),
        "generated_at": utc_now(),
    }
    public = {
        **base,
        "layers": sorted(PUBLIC_LAYERS),
        "big_picture": plan.get("big_picture"),
        "sections": section_skeleton(plan),
        "nodes": [node for node in nodes.values() if node["layer"] in PUBLIC_LAYERS],
        "edges": [edge for edge in edges if edge["layer"] in PUBLIC_LAYERS],
    }
    deep = {
        **base,
        "layers": [layer for layer in LAYERS if layer not in PUBLIC_LAYERS],
        "sections": section_deep(plan),
        "nodes": [node for node in nodes.values() if node["layer"] not in PUBLIC_LAYERS],
        "edges": [edge for edge in edges if edge["layer"] not in PUBLIC_LAYERS],
        "final_challenge": plan.get("final_challenge"),
    }
    return public, deep


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("lesson_plan", type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--store", type=Path, help="Knowledge store root; writes to <store>/mrg/")
    target.add_argument("--output-dir", type=Path, help="Write both files into this directory")
    parser.add_argument("--manifest", type=Path, help="sources.json for path cross-checks during validation")
    parser.add_argument("--force", action="store_true", help="Overwrite existing export files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = json.loads(args.lesson_plan.read_text(encoding="utf-8"))
        manifest = None
        if args.manifest:
            manifest = validate_lesson.manifest_paths(json.loads(args.manifest.read_text(encoding="utf-8")))
        errors = validate_lesson.validate_plan(plan, manifest)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            print("ERROR: lesson plan failed validation; nothing exported")
            return 1
        public, deep = export(plan)
        out_dir = args.store / "mrg" if args.store else args.output_dir
        public_path = out_dir / f"{plan['lesson_id']}.json"
        deep_path = out_dir / f"{plan['lesson_id']}.deep.json"
        for path in (public_path, deep_path):
            if path.exists() and not args.force:
                print(f"ERROR: {path} exists; use --force to overwrite (MRG revisions should be new versions)")
                return 1
        write_json(public_path, public)
        write_json(deep_path, deep)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2
    print(f"OK: exported {len(public['nodes'])} public / {len(deep['nodes'])} deep nodes, "
          f"{len(public['edges'])} public / {len(deep['edges'])} deep edges")
    print(f"  public: {public_path}")
    print(f"  deep:   {deep_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
