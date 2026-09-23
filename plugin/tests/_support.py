"""Shared loaders, paths and helpers for the test modules (not collected: the name does not start with test)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = PLUGIN_ROOT / "skills" / "learn" / "scripts"
CLARIFY_SCRIPT_ROOT = PLUGIN_ROOT / "skills" / "clarify" / "scripts"


def load_module(name: str, root: Path = SCRIPT_ROOT):
    spec = importlib.util.spec_from_file_location(name, root / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source_manifest = load_module("source_manifest")
validate_lesson = load_module("validate_lesson")
learning_state = load_module("learning_state")
validate_prerequisites = load_module("validate_prerequisites")
prerequisite_state = load_module("prerequisite_state")
scan_wikilinks = load_module("scan_wikilinks", CLARIFY_SCRIPT_ROOT)
mrg_export = load_module("mrg_export")
store_init = load_module("store_init")
comparator = load_module("comparator")
lrg_record = load_module("lrg_record")
index_match = load_module("index_match")
learner_state_build = load_module("learner_state_build")
review_pool = load_module("review_pool")
lesson_section = load_module("lesson_section")
next_step = load_module("next_step")
review_outline = load_module("review_outline")
cards = load_module("cards")
diagram = load_module("diagram")
mermaid_fit = load_module("mermaid_fit")
outline_status = load_module("outline_status")
store_sync = load_module("store_sync")
score_pack = load_module("score_pack", PLUGIN_ROOT / "evals")
survey_materials = load_module("survey_materials")

TEMPLATE_PLAN = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
EXAMPLE_ROOT = PLUGIN_ROOT / "examples" / "project-consensus"


def load_template():
    return json.loads(TEMPLATE_PLAN.read_text(encoding="utf-8"))


class _StoreHelpers:
    def _store(self, root: Path) -> Path:
        store = root / "store"
        store_init.init_store(store, [])
        store_init.register_lesson(store, TEMPLATE_PLAN)
        public, deep = mrg_export.export(load_template())
        mrg_export.write_json(store / "mrg" / "sample-guided-lesson.json", public)
        mrg_export.write_json(store / "mrg" / "sample-guided-lesson.deep.json", deep)
        index = index_match.load_index(store)
        index_match.register_nodes(index, public["nodes"] + deep["nodes"], "sample-guided-lesson")
        index_match.save_index(store, index)
        return store

    def _append(self, store, at, kind, verdict, confidence=None, depth=None, props=None, section="s01"):
        event = lrg_record.build_event(
            lesson_id="sample-guided-lesson", section_id=section, kind=kind, attempt_number=1, response="r", feedback="",
            verdict=verdict, confidence=confidence, criteria_met=[], depth_reached=depth, extraction=None,
            comparison={"propositions": props or [], "diff": {"conflict": []}, "feedback_priority": []}, elapsed_seconds=None,
        )
        event["at"] = at
        lrg_record.append_event(store, "sample-guided-lesson", event)


SKELETON_PLAN = PLUGIN_ROOT / "skills" / "learn" / "assets" / "skeleton-example" / "lesson-plan.json"
STRUCTURE_PLAN = PLUGIN_ROOT / "skills" / "learn" / "assets" / "structure-example" / "lesson-plan.json"
STRUCTURE_OUTLINE = PLUGIN_ROOT / "skills" / "learn" / "assets" / "structure-example" / "outline.md"
SKELETON_OUTLINE = PLUGIN_ROOT / "skills" / "learn" / "assets" / "skeleton-example" / "outline.md"


def load_skeleton():
    return json.loads(SKELETON_PLAN.read_text(encoding="utf-8"))
