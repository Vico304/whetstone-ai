#!/usr/bin/env python3
"""List de-personalised error propositions for review questions.

Reads learner-state.json only — never the raw log — so nothing it prints can quote the
learner. Each item is a claim the learner once made wrongly or partially, rewritten by the
model at extraction time without any subject ("你说 / 我认为"). Present it as an anonymous
claim ("有一种说法是……，这个说法哪里有问题？") and close the loop with the correction in the
same turn (hypercorrection needs immediate feedback).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


store_init = _load("store_init")


def load_state(store: Path) -> dict:
    path = store / "learner-state.json"
    if not path.is_file():
        raise ValueError("learner-state.json not built yet; run learner_state_build.py build")
    return json.loads(path.read_text(encoding="utf-8"))


def completed_sections(progress_path: Path | None) -> set[str] | None:
    if progress_path is None:
        return None
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    return {s["id"] for s in progress.get("sections", []) if s.get("status") == "completed"}


def pool(state: dict, lesson_id: str | None, concept_ids: list[str] | None, sections: set[str] | None, limit: int) -> list[dict]:
    items: dict[str, dict] = {}
    for cid, concept in state.get("concepts", {}).items():
        if concept_ids and cid not in concept_ids:
            continue
        for prop in concept.get("error_propositions", []):
            if lesson_id and prop.get("lesson_id") != lesson_id:
                continue
            if sections is not None and prop.get("section_id") not in sections:
                continue
            item = items.setdefault(prop["id"], {
                "id": prop["id"], "claim": prop["text"], "status": prop["status"], "at": prop.get("at"),
                "lesson_id": prop.get("lesson_id"), "section_id": prop.get("section_id"), "concept_ids": [],
                "concept_freshness": {},
            })
            if cid not in item["concept_ids"]:
                item["concept_ids"].append(cid)
                item["concept_freshness"][cid] = concept.get("freshness")
    ordered = sorted(items.values(), key=lambda i: (
        0 if i["status"] == "wrong" else 1,                      # wrong before partial
        0 if "stale" in i["concept_freshness"].values() else 1,  # stale concepts first
        i.get("at") or "",                                       # oldest first
    ))
    return ordered[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--lesson-id", help="Only propositions recorded in this lesson")
    parser.add_argument("--concept", action="append", help="Only these concept ids; repeatable")
    parser.add_argument("--progress", type=Path, help="learning-progress.json: restrict to completed sections (resume opener)")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    try:
        store_init.load_store(args.store)
        state = load_state(args.store)
        items = pool(state, args.lesson_id, args.concept, completed_sections(args.progress), args.limit)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"items": items, "presentation": "有一种说法是「{claim}」，这个说法哪里有问题？——纠正须在同一轮内给出"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
