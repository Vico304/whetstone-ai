#!/usr/bin/env python3
"""Push a workspace's local knowledge store into the learner home, and rebuild the cross-workspace aggregates.

Two layers:

  <workspace>/store/            local store — the authority for that workspace's courses.
                                Every per-answer write (lrg_record.py) lands here, inside the
                                directory the host already trusts, so teaching never prompts.
  ~/.whetstone/                 learner home — derived, rebuildable, holds no raw answers.
    home.json
    workspaces.json             {slug: {path, store, last_push_at, lessons[]}}
    snapshots/<slug>/           copies of each workspace's concepts/index.json + learner-state.json
    concepts/index.json         aggregate registry   (what index_match.py --home reads)
    learner-state.json          aggregate learner state (what review_pool.py --home reads)

`push` runs once at the end of a course (or whenever the learner asks); `rebuild` re-aggregates from
snapshots only, so the home never needs to read other workspaces. Override the home with
--home or $WHETSTONE_HOME.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


store_init = _load("store_init")
index_match = _load("index_match")
learner_state_build = _load("learner_state_build")

HOME_SCHEMA = "1.0"
DEPTH_ORDER = learner_state_build.DEPTH_ORDER


def default_home() -> Path:
    env = os.environ.get("WHETSTONE_HOME")
    return Path(env).expanduser() if env else Path.home() / ".whetstone"


def resolve_home(value: Path | None) -> Path:
    return (value or default_home()).expanduser().resolve()


def workspace_slug(workspace: Path) -> str:
    """<label>-<hash>: the label is the first ancestor not named whetstone/store, i.e. the materials root."""
    digest = hashlib.sha1(str(workspace).encode("utf-8")).hexdigest()[:8]
    label = workspace
    while label.name in {"whetstone", "store", ""} and label.parent != label:
        label = label.parent
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", label.name).strip("-") or "workspace"
    return f"{base}-{digest}"


def ensure_home(home: Path) -> dict:
    home.mkdir(parents=True, exist_ok=True)
    meta_path = home / "home.json"
    if meta_path.is_file():
        meta = store_init.read_json(meta_path)
        if meta.get("schema_version") != HOME_SCHEMA:
            raise ValueError(f"unsupported learner home schema in {meta_path}")
        return meta
    now = store_init.utc_now()
    meta = {"schema_version": HOME_SCHEMA, "created_at": now, "updated_at": now}
    store_init.atomic_write(meta_path, meta)
    store_init.atomic_write(home / "workspaces.json", {"schema_version": HOME_SCHEMA, "workspaces": {}})
    return meta


def load_workspaces(home: Path) -> dict:
    path = home / "workspaces.json"
    if not path.is_file():
        return {"schema_version": HOME_SCHEMA, "workspaces": {}}
    return store_init.read_json(path)


# ---------------------------------------------------------------- aggregation

def merge_indexes(snapshots: list[tuple[str, dict]]) -> tuple[dict, list[dict]]:
    """Union of workspace registries. Same id → union of appearances/aliases; alias conflicts keep the first."""
    merged = {"schema_version": store_init.STORE_SCHEMA, "updated_at": store_init.utc_now(), "concepts": {}, "alias_index": {}}
    conflicts: list[dict] = []
    normalized_alias: dict[str, str] = {}
    for slug, index in snapshots:
        for cid, entry in (index.get("concepts") or {}).items():
            target = merged["concepts"].get(cid)
            if target is None:
                target = {
                    "name": entry.get("name"), "aliases": [], "domain_path": list(entry.get("domain_path") or []),
                    "layer": entry.get("layer"), "appearances": [], "created_at": entry.get("created_at"), "workspaces": [],
                }
                merged["concepts"][cid] = target
            if slug not in target["workspaces"]:
                target["workspaces"].append(slug)
            for appearance in entry.get("appearances") or []:
                stamped = dict(appearance, workspace=slug)
                if stamped not in target["appearances"]:
                    target["appearances"].append(stamped)
            if not target.get("domain_path") and entry.get("domain_path"):
                target["domain_path"] = list(entry["domain_path"])
            for alias in entry.get("aliases") or []:
                if alias not in target["aliases"] and alias != target.get("name"):
                    target["aliases"].append(alias)
        for alias, cid in (index.get("alias_index") or {}).items():
            key = index_match.normalize(alias)
            existing = normalized_alias.get(key)
            if existing is None:
                normalized_alias[key] = cid
                merged["alias_index"][alias] = cid
            elif existing != cid:
                conflicts.append({"alias": alias, "existing_id": existing, "new_id": cid, "workspace": slug})
    return merged, conflicts


def merge_concept_states(states: list[tuple[str, dict]], now: datetime) -> dict:
    """Merge one concept's per-workspace derived states. Approximation: stability adds across workspaces."""
    merged = learner_state_build.new_state()
    merged["workspaces"] = []
    latest_evidence: tuple[str, dict] | None = None
    latest_success: tuple[str, dict] | None = None
    for slug, state in states:
        merged["workspaces"].append(slug)
        merged["attempts"] += int(state.get("attempts") or 0)
        merged["stability"] += int(state.get("stability") or 0)
        for lesson in state.get("lessons") or []:
            if lesson not in merged["lessons"]:
                merged["lessons"].append(lesson)
        for key in ("overconfident", "underconfident"):
            merged["calibration"][key] += int((state.get("calibration") or {}).get(key) or 0)
        for prop in state.get("error_propositions") or []:
            if not any(p.get("id") == prop.get("id") for p in merged["error_propositions"]):
                merged["error_propositions"].append(dict(prop, workspace=slug))
        depth = state.get("depth_max")
        if depth in DEPTH_ORDER and (merged["depth_max"] is None or DEPTH_ORDER[depth] > DEPTH_ORDER[merged["depth_max"]]):
            merged["depth_max"] = depth
        rigor = state.get("rigor_max")
        if rigor == "full" or (rigor == "fast" and merged["rigor_max"] is None):
            merged["rigor_max"] = rigor
        at = state.get("last_evidence_at")
        if at and (latest_evidence is None or at > latest_evidence[0]):
            latest_evidence = (at, state)
        success_at = state.get("last_success_at")
        if success_at and (latest_success is None or success_at > latest_success[0]):
            latest_success = (success_at, state)
    if latest_evidence:
        merged["last_evidence_at"] = latest_evidence[0]
        merged["last_verdict"] = latest_evidence[1].get("last_verdict")
        merged["depth_latest"] = latest_evidence[1].get("depth_latest")
    if latest_success:
        merged["last_success_at"] = latest_success[0]
        tier = latest_success[1].get("evidence_tier") or "immediate"
        merged["evidence_tier"] = tier
        if tier == "immediate":
            merged["freshness"] = "unknown"
        else:
            age = now - learner_state_build.parse_time(latest_success[0])
            merged["freshness"] = "fresh" if age <= learner_state_build.freshness_window(merged["stability"]) else "stale"
    merged["mastery_estimate"] = round(
        learner_state_build.TIER_WEIGHT[merged["evidence_tier"]] * learner_state_build.FRESHNESS_WEIGHT[merged["freshness"]], 3
    )
    merged["error_propositions"].sort(key=lambda p: p.get("at") or "")
    return merged


def merge_learner_states(snapshots: list[tuple[str, dict]], now: datetime) -> dict:
    per_concept: dict[str, list[tuple[str, dict]]] = {}
    for slug, state in snapshots:
        for cid, concept in (state.get("concepts") or {}).items():
            per_concept.setdefault(cid, []).append((slug, concept))
    return {
        "schema_version": store_init.STORE_SCHEMA,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "aggregate_of": sorted({slug for slug, _ in snapshots}),
        "note": "derived from workspace snapshots; stability adds across workspaces; no raw answers here",
        "concepts": {cid: merge_concept_states(states, now) for cid, states in sorted(per_concept.items())},
    }


def rebuild(home: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    ensure_home(home)
    workspaces = load_workspaces(home)
    index_snaps: list[tuple[str, dict]] = []
    state_snaps: list[tuple[str, dict]] = []
    for slug in sorted(workspaces.get("workspaces") or {}):
        snap = home / "snapshots" / slug
        if (snap / "index.json").is_file():
            index_snaps.append((slug, store_init.read_json(snap / "index.json")))
        if (snap / "learner-state.json").is_file():
            state_snaps.append((slug, store_init.read_json(snap / "learner-state.json")))
    index, conflicts = merge_indexes(index_snaps)
    state = merge_learner_states(state_snaps, now)
    store_init.atomic_write(home / "concepts" / "index.json", index)
    store_init.atomic_write(home / "learner-state.json", state)
    meta = store_init.read_json(home / "home.json")
    meta["updated_at"] = store_init.utc_now()
    store_init.atomic_write(home / "home.json", meta)
    return {"workspaces": len(index_snaps), "concepts": len(index["concepts"]),
            "states": len(state["concepts"]), "alias_conflicts": conflicts}


# ---------------------------------------------------------------- push

def push(store: Path, home: Path, workspace: Path | None = None, now: datetime | None = None) -> dict:
    store = store.expanduser().resolve()
    data = store_init.load_store(store)
    workspace = (workspace or store.parent).expanduser().resolve()
    now = now or datetime.now(timezone.utc)
    ensure_home(home)
    # the local derived state is rebuilt first, so a push always reflects the latest lrg/
    local_state = learner_state_build.build(store, now)
    store_init.atomic_write(store / "learner-state.json", local_state)
    slug = workspace_slug(workspace)
    snap = home / "snapshots" / slug
    store_init.atomic_write(snap / "index.json", index_match.load_index(store))
    store_init.atomic_write(snap / "learner-state.json", local_state)
    workspaces = load_workspaces(home)
    entry = workspaces.setdefault("workspaces", {}).setdefault(slug, {"path": str(workspace), "store": str(store)})
    entry.update({"path": str(workspace), "store": str(store), "last_push_at": store_init.utc_now(),
                  "lessons": sorted({l.get("lesson_id") for l in data.get("lessons", []) if isinstance(l, dict) and l.get("lesson_id")})})
    store_init.atomic_write(home / "workspaces.json", workspaces)
    report = rebuild(home, now)
    report["slug"] = slug
    return report


def command_push(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    now = learner_state_build.parse_time(args.now) if args.now else None
    report = push(args.store, home, args.workspace, now)
    print(f"OK: pushed workspace {report['slug']} to {home}; home now aggregates {report['workspaces']} workspace(s), "
          f"{report['concepts']} concepts, {report['states']} learner states")
    for conflict in report["alias_conflicts"]:
        print(f"CONFLICT: alias '{conflict['alias']}' maps to {conflict['existing_id']} in an earlier workspace, "
              f"not re-pointed to {conflict['new_id']} ({conflict['workspace']}) — confirm manually")
    return 0


def command_rebuild(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    now = learner_state_build.parse_time(args.now) if args.now else None
    report = rebuild(home, now)
    print(f"OK: rebuilt {home} from {report['workspaces']} snapshot(s): {report['concepts']} concepts, {report['states']} learner states")
    return 0


def command_show(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    if not (home / "home.json").is_file():
        print(f"no learner home at {home} (nothing pushed yet)")
        return 0
    workspaces = load_workspaces(home).get("workspaces") or {}
    print(f"learner home: {home}")
    for slug, entry in sorted(workspaces.items()):
        print(f"- {slug}: {entry.get('path')}  lessons={','.join(entry.get('lessons') or [])}  last_push={entry.get('last_push_at')}")
    state_path = home / "learner-state.json"
    if state_path.is_file():
        state = store_init.read_json(state_path)
        counts: dict[str, int] = {}
        for concept in state.get("concepts", {}).values():
            counts[concept["freshness"]] = counts.get(concept["freshness"], 0) + 1
        print(f"concepts: {len(state.get('concepts', {}))} (fresh={counts.get('fresh', 0)}, stale={counts.get('stale', 0)}, unknown={counts.get('unknown', 0)})")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("push", help="Snapshot a workspace's local store into the learner home and re-aggregate")
    p.add_argument("--store", type=Path, required=True, help="local store, normally <materials>/whetstone/store")
    p.add_argument("--workspace", type=Path, help="workspace root (default: parent of --store)")
    p.add_argument("--home", type=Path, help="learner home (default: $WHETSTONE_HOME or ~/.whetstone)")
    p.add_argument("--now", help="ISO timestamp for freshness (tests)")
    p.set_defaults(handler=command_push)
    r = sub.add_parser("rebuild", help="Re-aggregate the learner home from its snapshots")
    r.add_argument("--home", type=Path)
    r.add_argument("--now")
    r.set_defaults(handler=command_rebuild)
    s = sub.add_parser("show", help="List pushed workspaces and aggregate counts (never prints answers)")
    s.add_argument("--home", type=Path)
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
