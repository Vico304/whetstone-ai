#!/usr/bin/env python3
"""Raw material for a review course, derived from the store: what is weak in one or more
finished courses (grouped by the sections they came from) and which sections are stable
enough to grow a sub-section.

  review_outline.py --store <store> --lesson-id <reviewed course> [--lesson-id <another>]

Reads learner-state.json (build it first), the public MRG exports and store.json. Prints
JSON; the model turns it into the outline of a `shape: review` course. Nothing here is a
score; the stable-section gate is the only threshold, and it is written out with the result.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SUB_UNIT_MIN_DELAYED = 2  # delayed or transfer successes per core concept, on different days by construction
DEEP_LAYERS = {"rationale", "principle"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


store_init = _load("store_init")
review_pool = _load("review_pool")


def load_public(store: Path, lesson_id: str) -> dict:
    path = store / "mrg" / f"{lesson_id}.json"
    if not path.is_file():
        raise ValueError(f"no MRG export for '{lesson_id}' in {store}")
    return json.loads(path.read_text(encoding="utf-8"))


def pack_dirs(store: Path) -> dict[str, str]:
    data = store_init.load_store(store)
    return {l.get("lesson_id"): l.get("pack_dir") for l in data.get("lessons", []) if isinstance(l, dict)}


def section_is_stable(section: dict, concepts: dict[str, dict]) -> tuple[bool, str]:
    core = [cid for cid in section.get("core_concept_ids") or section.get("concept_ids") or []]
    if not core:
        return False, "no core concepts"
    for cid in core:
        state = concepts.get(cid) or {}
        if int(state.get("delayed_successes") or 0) < SUB_UNIT_MIN_DELAYED:
            return False, f"{cid} has {int(state.get('delayed_successes') or 0)} delayed/transfer successes (need {SUB_UNIT_MIN_DELAYED})"
    if not any((concepts.get(cid) or {}).get("depth_max") in DEEP_LAYERS for cid in core):
        return False, "no core concept has reached the rationale layer"
    return True, "every core concept has repeated delayed evidence and one reached rationale"


def outline(store: Path, lesson_ids: list[str]) -> dict:
    state = review_pool.load_state(store)
    concepts = state.get("concepts", {})
    dirs = pack_dirs(store)
    reviewed, clusters, stable = [], [], []
    for lesson_id in lesson_ids:
        public = load_public(store, lesson_id)
        reviewed.append({"lesson_id": lesson_id, "title": public.get("title"), "pack_dir": dirs.get(lesson_id),
                         "chain_rebuild": (state.get("lessons") or {}).get(lesson_id, {}).get("chain_rebuild")})
        suspect = {s["id"]: s for s in review_pool.suspect_pool(state, lesson_id, 1000)}
        errors = review_pool.pool(state, lesson_id, None, None, 1000)
        edges = review_pool.missing_edges(state, lesson_id, 1000)
        stale = {s["id"] for s in review_pool.stale_pool(state, lesson_id, 1000)}
        for section in public.get("sections", []) or []:
            if section.get("deferred"):
                continue
            ids = list(section.get("concept_ids") or [])
            id_set = set(ids)
            reasons: list[dict] = []
            for cid in ids:
                c = concepts.get(cid) or {}
                if cid in suspect:
                    reasons.append({"kind": "suspect", "concept": cid, "weak_prerequisites": suspect[cid]["weak_prerequisites"]})
                if c.get("attempts") and c.get("last_verdict") in {"partial", "retry"}:
                    reasons.append({"kind": "unmastered", "concept": cid, "last_verdict": c.get("last_verdict")})
                if cid in stale:
                    reasons.append({"kind": "stale", "concept": cid, "last_success_at": c.get("last_success_at")})
            for prop in errors:
                if prop.get("section_id") == section.get("id"):
                    reasons.append({"kind": "error_proposition", "id": prop["id"], "claim": prop["claim"], "concept_ids": prop["concept_ids"]})
            for edge in edges:
                if edge.get("from") in id_set or edge.get("to") in id_set:
                    reasons.append({"kind": "missing_edge", "from": edge.get("from"), "to": edge.get("to"), "type": edge.get("type"), "status": edge.get("status")})
            entry = {"lesson_id": lesson_id, "section_id": section.get("id"), "title": section.get("title"),
                     "core_concept_ids": section.get("core_concept_ids") or ids, "reasons": reasons}
            if reasons:
                clusters.append(entry)
            ok, why = section_is_stable(section, concepts)
            if ok:
                stable.append({"lesson_id": lesson_id, "section_id": section.get("id"), "title": section.get("title"),
                               "listed_concept_ids": section.get("listed_concept_ids") or [], "why": why})
    clusters.sort(key=lambda c: (-len(c["reasons"]), c["lesson_id"], c["section_id"]))
    return {
        "reviewed": reviewed,
        "clusters": clusters,
        "stable_sections": stable,
        "rules": {"cluster_order": "most reasons first; the model may merge adjacent clusters that share edges",
                  "sub_unit_gate": f"every core concept has >= {SUB_UNIT_MIN_DELAYED} delayed/transfer successes and one core concept reached rationale",
                  "sub_units_per_review": 1},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--lesson-id", action="append", required=True, help="A finished course to review; repeatable")
    args = parser.parse_args()
    try:
        print(json.dumps(outline(args.store, args.lesson_id), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
