#!/usr/bin/env python3
"""Cross-course concept registry: deterministic recall and registration.

  recall    candidates (name + aliases) → existing ids they may correspond to, plus the
            learner's current state for each hit (if learner-state.json exists). The model
            then confirms "same concept / different concept / different granularity";
            ambiguities go to the learner. Nothing is merged here.
  register  after mrg_export, add every node of a lesson's MRG to the registry: new ids are
            created, existing ids get a new appearance and merged aliases. An alias that
            already points to a *different* id is reported as a conflict and left alone.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


store_init = _load("store_init")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", str(text).strip()).casefold()


def index_path(store: Path) -> Path:
    return store / "concepts" / "index.json"


def load_index(store: Path) -> dict:
    path = index_path(store)
    if not path.is_file():
        return {"schema_version": store_init.STORE_SCHEMA, "updated_at": store_init.utc_now(), "concepts": {}, "alias_index": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("concepts", {})
    data.setdefault("alias_index", {})
    return data


def save_index(store: Path, index: dict) -> None:
    index["updated_at"] = store_init.utc_now()
    store_init.atomic_write(index_path(store), index)


def load_learner_state(store: Path) -> dict:
    path = store / "learner-state.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("concepts", {})


def recall(index: dict, candidates: list[dict], learner_state: dict | None = None) -> list[dict]:
    learner_state = learner_state or {}
    alias_index = {normalize(k): v for k, v in index.get("alias_index", {}).items()}
    results = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str):
            raise ValueError(f"candidate needs a name: {candidate}")
        terms = [candidate["name"], *(candidate.get("aliases") or [])]
        matches: dict[str, dict] = {}
        for term in terms:
            cid = alias_index.get(normalize(term))
            if cid and cid in index["concepts"]:
                entry = index["concepts"][cid]
                match = matches.setdefault(cid, {"id": cid, "name": entry.get("name"), "domain_path": entry.get("domain_path"), "matched_on": []})
                match["matched_on"].append(term)
                state = learner_state.get(cid)
                if state:
                    match["learner"] = {
                        "freshness": state.get("freshness"),
                        "evidence_tier": state.get("evidence_tier"),
                        "depth_max": state.get("depth_max"),
                        "last_evidence_at": state.get("last_evidence_at"),
                    }
        results.append({
            "name": candidate["name"],
            "domain_path": candidate.get("domain_path"),
            "matches": list(matches.values()),
            "decision_needed": "none" if not matches else ("confirm_same" if len(matches) == 1 else "disambiguate"),
        })
    return results


def register_nodes(index: dict, nodes: list[dict], lesson_id: str) -> dict:
    """Add MRG nodes to the registry. Returns {'created': [...], 'updated': [...], 'alias_conflicts': [...]}."""
    report: dict[str, list] = {"created": [], "updated": [], "alias_conflicts": []}
    concepts = index["concepts"]
    alias_index = index["alias_index"]
    for node in nodes:
        cid = node["id"]
        aliases = [node.get("name"), *(node.get("aliases") or [])]
        aliases = [a for a in aliases if isinstance(a, str) and a.strip()]
        appearances = [{"lesson_id": lesson_id, "section_id": sid, "layer": node.get("layer")} for sid in node.get("section_ids", [])]
        if cid not in concepts:
            concepts[cid] = {
                "name": node.get("name"),
                "aliases": [],
                "domain_path": list(node.get("domain_path") or []),
                "layer": node.get("layer"),
                "appearances": [],
                "created_at": store_init.utc_now(),
            }
            report["created"].append(cid)
        else:
            report["updated"].append(cid)
        entry = concepts[cid]
        for appearance in appearances:
            if appearance not in entry["appearances"]:
                entry["appearances"].append(appearance)
        if not entry.get("domain_path") and node.get("domain_path"):
            entry["domain_path"] = list(node["domain_path"])
        for alias in aliases:
            key = normalize(alias)
            existing = None
            for stored_alias, stored_id in alias_index.items():
                if normalize(stored_alias) == key:
                    existing = stored_id
                    break
            if existing is None:
                alias_index[alias] = cid
                if alias != entry.get("name") and alias not in entry["aliases"]:
                    entry["aliases"].append(alias)
            elif existing != cid:
                report["alias_conflicts"].append({"alias": alias, "existing_id": existing, "new_id": cid})
    return report


def command_recall(args: argparse.Namespace) -> int:
    store_init.load_store(args.store)
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise ValueError("candidates file must contain a JSON list")
    results = recall(load_index(args.store), candidates, load_learner_state(args.store))
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


def command_register(args: argparse.Namespace) -> int:
    store_init.load_store(args.store)
    nodes: list[dict] = []
    for suffix in (".json", ".deep.json"):
        path = args.store / "mrg" / f"{args.lesson_id}{suffix}"
        if path.is_file():
            nodes.extend(json.loads(path.read_text(encoding="utf-8")).get("nodes", []))
    if not nodes:
        raise ValueError(f"no MRG nodes found for lesson '{args.lesson_id}' (run mrg_export.py first)")
    index = load_index(args.store)
    report = register_nodes(index, nodes, args.lesson_id)
    save_index(args.store, index)
    print(f"OK: registry now has {len(index['concepts'])} concepts "
          f"(+{len(report['created'])} new, {len(report['updated'])} updated)")
    for conflict in report["alias_conflicts"]:
        print(f"CONFLICT: alias '{conflict['alias']}' already maps to {conflict['existing_id']}, "
              f"not re-pointed to {conflict['new_id']} — confirm manually")
    return 0


def command_show(args: argparse.Namespace) -> int:
    index = load_index(args.store)
    print(f"concepts: {len(index['concepts'])}  aliases: {len(index['alias_index'])}")
    for cid, entry in sorted(index["concepts"].items()):
        path = "/".join(entry.get("domain_path") or [])
        lessons = sorted({a["lesson_id"] for a in entry.get("appearances", [])})
        print(f"- {cid}  {entry.get('name')}  [{path}]  lessons={','.join(lessons)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("recall", help="Find existing ids for candidate concepts")
    r.add_argument("--store", type=Path, required=True)
    r.add_argument("--candidates", type=Path, required=True, help='JSON list of {"name", "aliases": [], "domain_path": []}')
    r.set_defaults(handler=command_recall)
    g = sub.add_parser("register", help="Register a lesson's exported MRG nodes")
    g.add_argument("--store", type=Path, required=True)
    g.add_argument("--lesson-id", required=True)
    g.set_defaults(handler=command_register)
    s = sub.add_parser("show", help="List the registry")
    s.add_argument("--store", type=Path, required=True)
    s.set_defaults(handler=command_show)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
