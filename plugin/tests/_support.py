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


# Scripts are loaded on first use, not at import: a script that fails to load then breaks only the tests
# that use it, and running one test file does not execute all 23. Each is loaded once and cached, so every
# test module sees the same module object, as before.
_SCRIPTS = {
    "source_manifest": SCRIPT_ROOT, "validate_lesson": SCRIPT_ROOT, "learning_state": SCRIPT_ROOT,
    "validate_prerequisites": SCRIPT_ROOT, "prerequisite_state": SCRIPT_ROOT,
    "scan_wikilinks": CLARIFY_SCRIPT_ROOT, "mrg_export": SCRIPT_ROOT, "store_init": SCRIPT_ROOT,
    "comparator": SCRIPT_ROOT, "lrg_record": SCRIPT_ROOT, "index_match": SCRIPT_ROOT,
    "learner_state_build": SCRIPT_ROOT, "review_pool": SCRIPT_ROOT, "lesson_section": SCRIPT_ROOT,
    "next_step": SCRIPT_ROOT, "review_outline": SCRIPT_ROOT, "cards": SCRIPT_ROOT, "diagram": SCRIPT_ROOT,
    "mermaid_fit": SCRIPT_ROOT, "outline_status": SCRIPT_ROOT, "store_sync": SCRIPT_ROOT,
    "score_pack": PLUGIN_ROOT / "evals", "survey_materials": SCRIPT_ROOT,
}


def __getattr__(name: str):
    """PEP 562: ``from _support import validate_lesson`` lands here the first time."""
    if name not in _SCRIPTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = globals()[name] = load_module(name, _SCRIPTS[name])
    return module

TEMPLATE_PLAN = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
EXAMPLE_ROOT = PLUGIN_ROOT / "examples" / "project-consensus"


def load_template():
    return json.loads(TEMPLATE_PLAN.read_text(encoding="utf-8"))


class _StoreHelpers:
    def _store(self, root: Path) -> Path:
        # Bare names inside this module do not go through __getattr__, so fetch the scripts explicitly.
        store_init, mrg_export, index_match = (__getattr__(n) for n in ("store_init", "mrg_export", "index_match"))
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
        lrg_record = __getattr__("lrg_record")
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
