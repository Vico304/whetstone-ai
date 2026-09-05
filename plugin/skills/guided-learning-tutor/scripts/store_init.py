#!/usr/bin/env python3
"""Create and maintain the optional persistent knowledge store.

Layout (docs/specs/knowledge-store.md §2):
  <store>/store.json            schema_version, domain roots, registered lessons
  <store>/concepts/index.json   cross-course concept registry
  <store>/mrg/                  <lesson>.json (public) + <lesson>.deep.json (high layers)
  <store>/lrg/                  <lesson>.jsonl append-only attempt log (never shown to the learner)
  <store>/exports/              derived visualisation exports
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STORE_SCHEMA = "1.1"
SUBDIRS = ("concepts", "mrg", "lrg", "exports")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def store_file(store: Path) -> Path:
    return store / "store.json"


def load_store(store: Path) -> dict:
    path = store_file(store)
    if not path.is_file():
        raise ValueError(f"not a knowledge store (missing store.json): {store}")
    data = read_json(path)
    if not isinstance(data, dict) or data.get("schema_version") != STORE_SCHEMA:
        raise ValueError(f"unsupported store schema in {path}")
    return data


def init_store(store: Path, domain_roots: list[str]) -> dict:
    if store_file(store).exists():
        raise ValueError(f"refusing to re-initialise existing store: {store}")
    now = utc_now()
    for name in SUBDIRS:
        (store / name).mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": STORE_SCHEMA,
        "created_at": now,
        "updated_at": now,
        "domain_roots": [root for root in domain_roots if root.strip()],
        "lessons": [],
    }
    atomic_write(store_file(store), data)
    index_path = store / "concepts" / "index.json"
    if not index_path.exists():
        atomic_write(index_path, {"schema_version": STORE_SCHEMA, "updated_at": now, "concepts": {}, "alias_index": {}})
    return data


def register_lesson(store: Path, plan_path: Path) -> dict:
    data = load_store(store)
    plan = read_json(plan_path)
    if not isinstance(plan, dict) or not isinstance(plan.get("lesson_id"), str):
        raise ValueError("lesson plan must be an object with a lesson_id")
    lesson_id = plan["lesson_id"]
    for lesson in data["lessons"]:
        if lesson.get("lesson_id") == lesson_id:
            lesson["pack_dir"] = plan_path.resolve().parent.as_posix()
            lesson["title"] = plan.get("title")
            break
    else:
        data["lessons"].append(
            {
                "lesson_id": lesson_id,
                "title": plan.get("title"),
                "pack_dir": plan_path.resolve().parent.as_posix(),
                "schema_version": plan.get("schema_version"),
                "registered_at": utc_now(),
                "mrg_version": 1,
            }
        )
    data["updated_at"] = utc_now()
    atomic_write(store_file(store), data)
    return data


def command_init(args: argparse.Namespace) -> int:
    init_store(args.store, args.domain_root or [])
    print(f"OK: initialised knowledge store at {args.store}")
    return 0


def command_register(args: argparse.Namespace) -> int:
    data = register_lesson(args.store, args.lesson_plan)
    print(f"OK: {len(data['lessons'])} lesson(s) registered in {args.store}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    data = load_store(args.store)
    print(f"store: {args.store}")
    print(f"domain_roots: {', '.join(data.get('domain_roots') or []) or '(none)'}")
    for lesson in data.get("lessons", []):
        mrg = (args.store / "mrg" / f"{lesson['lesson_id']}.json").exists()
        lrg = args.store / "lrg" / f"{lesson['lesson_id']}.jsonl"
        events = sum(1 for line in lrg.read_text(encoding="utf-8").splitlines() if line.strip()) if lrg.exists() else 0
        print(f"- {lesson['lesson_id']}: mrg={'yes' if mrg else 'no'} lrg_events={events} ({lesson.get('title')})")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="Create a new store directory")
    p_init.add_argument("--store", type=Path, required=True)
    p_init.add_argument("--domain-root", action="append", help="Top-level discipline name; repeatable")
    p_init.set_defaults(handler=command_init)
    p_reg = sub.add_parser("register", help="Register a lesson pack in the store")
    p_reg.add_argument("--store", type=Path, required=True)
    p_reg.add_argument("--lesson-plan", type=Path, required=True)
    p_reg.set_defaults(handler=command_register)
    p_show = sub.add_parser("show", help="Summarise the store (never prints learner responses)")
    p_show.add_argument("--store", type=Path, required=True)
    p_show.set_defaults(handler=command_show)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
