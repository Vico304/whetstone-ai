#!/usr/bin/env python3
"""Fact cards: the conventions of a course (fact-layer and listed concepts) as recall items.

  cards.py build --store <store> --lesson-id <id>          cards from the public MRG export → cards/<id>.json
  cards.py due   --store <store> [--lesson-id <id>] [--limit N] [--now ISO]
                                                          cards to ask now, most overdue first
  cards.py show  --store <store> --lesson-id <id>          counts only

A card is made only for a concept whose layer is `fact` or whose role is `listed`; never for
mechanism, rationale or principle. Answers are recorded with `lrg_record.py append --kind recall
--concept <id>`; a recall event touches that concept only. Scheduling is the same window as
freshness (7 · 2^(successes−1) days, max 180) — a placeholder, not a forgetting model.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CARDS_SCHEMA = "1.0"
CARD_LAYERS = {"fact"}
CARD_ROLES = {"listed"}
NEVER_CARD_LAYERS = {"rationale", "principle"}
BASE_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 180


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


store_init = _load("store_init")
lrg_record = _load("lrg_record")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def cards_path(store: Path, lesson_id: str) -> Path:
    return store / "cards" / f"{lesson_id}.json"


def load_cards(store: Path, lesson_id: str) -> dict:
    path = cards_path(store, lesson_id)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": CARDS_SCHEMA, "lesson_id": lesson_id, "generated_at": None, "cards": []}


def eligible(node: dict) -> bool:
    if node.get("layer") in NEVER_CARD_LAYERS:
        return False
    return node.get("layer") in CARD_LAYERS or node.get("role") in CARD_ROLES


def build(store: Path, lesson_id: str) -> dict:
    """Add a card per eligible public node; existing cards are kept as they are."""
    public_path = store / "mrg" / f"{lesson_id}.json"
    if not public_path.is_file():
        raise ValueError(f"no MRG export for '{lesson_id}' in {store} (run mrg_export.py first)")
    public = json.loads(public_path.read_text(encoding="utf-8"))
    data = load_cards(store, lesson_id)
    existing = {card["concept_id"] for card in data["cards"]}
    added = []
    for node in public.get("nodes", []) or []:
        if node.get("deferred") or not eligible(node) or node["id"] in existing:
            continue
        card = {
            "id": f"card:{node['id']}",
            "concept_id": node["id"],
            "section_id": (node.get("section_ids") or [None])[0],
            "prompt": f"{node.get('name')}——是什么？",
            "answer": node.get("explanation"),
            "layer": node.get("layer"),
            "role": node.get("role", "core"),
            "source_refs": list(node.get("source_refs") or [])[:2],
            "created_at": utc_now(),
        }
        data["cards"].append(card)
        added.append(node["id"])
    data["generated_at"] = utc_now()
    store_init.atomic_write(cards_path(store, lesson_id), data)
    return {"lesson_id": lesson_id, "cards": len(data["cards"]), "added": added}


def recall_history(store: Path) -> dict[str, dict]:
    """{concept_id: {last_success, success_days, last_verdict}} from recall events of every lesson log —
    a concept id is shared across courses, so a recall recorded under one course counts for the others."""
    history: dict[str, dict] = {}
    events: list[dict] = []
    lrg_dir = store / "lrg"
    for path in sorted(lrg_dir.glob("*.jsonl")) if lrg_dir.is_dir() else []:
        events.extend(lrg_record.read_events(store, path.stem))
    events.sort(key=lambda e: e.get("at") or "")
    for event in events:
        if event.get("event") != "attempt" or event.get("kind") != "recall":
            continue
        for cid in event.get("target_concept_ids") or []:
            entry = history.setdefault(cid, {"last_success": None, "success_days": set(), "last_verdict": None})
            entry["last_verdict"] = event.get("verdict")
            if event.get("verdict") == "mastered":
                entry["last_success"] = event.get("at")
                entry["success_days"].add((event.get("at") or "")[:10])
    return history


def window(success_days: int) -> timedelta:
    return timedelta(days=min(BASE_WINDOW_DAYS * (2 ** max(success_days - 1, 0)), MAX_WINDOW_DAYS))


def due(store: Path, lesson_ids: list[str], now: datetime, limit: int) -> list[dict]:
    items: list[dict] = []
    history = recall_history(store)
    seen: set[str] = set()
    for lesson_id in lesson_ids:
        for card in load_cards(store, lesson_id)["cards"]:
            if card["concept_id"] in seen:
                continue  # the same concept in another course: one card is enough
            seen.add(card["concept_id"])
            entry = history.get(card["concept_id"])
            if entry is None or entry["last_success"] is None:
                overdue_days, reason = float("inf"), "never recalled"
            elif entry["last_verdict"] != "mastered":
                overdue_days, reason = float("inf"), f"last recall was {entry['last_verdict']}"
            else:
                age = now - parse_time(entry["last_success"])
                overdue = age - window(len(entry["success_days"]))
                if overdue < timedelta(0):
                    continue
                overdue_days, reason = overdue.days, f"window of {window(len(entry['success_days'])).days} days passed"
            items.append({**{k: card[k] for k in ("id", "concept_id", "section_id", "prompt", "answer", "source_refs")},
                          "lesson_id": lesson_id, "reason": reason, "overdue_days": None if overdue_days == float("inf") else overdue_days})
    items.sort(key=lambda i: (0 if i["overdue_days"] is None else 1, -(i["overdue_days"] or 0), i["concept_id"]))
    return items[:limit]


def lesson_ids_with_cards(store: Path) -> list[str]:
    directory = store / "cards"
    return sorted(p.stem for p in directory.glob("*.json")) if directory.is_dir() else []


def command_build(args: argparse.Namespace) -> int:
    store_init.load_store(args.store)
    result = build(args.store, args.lesson_id)
    print(f"OK: {result['cards']} cards for {result['lesson_id']} ({len(result['added'])} added)")
    return 0


def command_due(args: argparse.Namespace) -> int:
    store_init.load_store(args.store)
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    lesson_ids = args.lesson_id or lesson_ids_with_cards(args.store)
    items = due(args.store, lesson_ids, now, args.limit)
    print(json.dumps({"due": items, "record": "lrg_record.py append --kind recall --concept <concept_id> --section-id <section_id> "
                                              "--response-file … --verdict mastered|partial|retry [--depth fact]"},
                     ensure_ascii=False, indent=2))
    return 0


def command_show(args: argparse.Namespace) -> int:
    store_init.load_store(args.store)
    data = load_cards(args.store, args.lesson_id)
    history = recall_history(args.store)
    recalled = sum(1 for c in data["cards"] if (history.get(c["concept_id"]) or {}).get("last_success"))
    print(f"{args.lesson_id}: {len(data['cards'])} cards, {recalled} recalled at least once")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="Cards from the public MRG export (fact-layer and listed concepts)")
    b.add_argument("--store", type=Path, required=True)
    b.add_argument("--lesson-id", required=True)
    b.set_defaults(handler=command_build)
    d = sub.add_parser("due", help="Cards to ask now")
    d.add_argument("--store", type=Path, required=True)
    d.add_argument("--lesson-id", action="append", help="Restrict to these lessons (default: every lesson with cards)")
    d.add_argument("--limit", type=int, default=5)
    d.add_argument("--now", help="ISO timestamp (tests)")
    d.set_defaults(handler=command_due)
    s = sub.add_parser("show", help="Counts only")
    s.add_argument("--store", type=Path, required=True)
    s.add_argument("--lesson-id", required=True)
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
