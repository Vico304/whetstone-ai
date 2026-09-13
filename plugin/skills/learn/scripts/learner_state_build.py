#!/usr/bin/env python3
"""Derive learner-state.json from the append-only LRG logs and the exported MRGs.

The state is a *derived* view: it can be rebuilt at any time and is never edited by hand.
Per concept it keeps several dimensions apart (consensus §11): evidence tier of the latest
success, freshness (a deliberately simple window, not a forgetting model), stability, depth
reached, error propositions (de-personalised text only), calibration counts — and one
scalar `mastery_estimate` that exists solely for visualisation colour.

The evidence tier is derived here, per concept, from the *interval* since the concept's
previous record — not from the question kind: a "review" asked minutes after the
teaching is still immediate evidence. `kind` only says what was asked.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date, datetime, timedelta, timezone, tzinfo
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

DEPTH_ORDER = {"fact": 0, "mechanism": 1, "rationale": 2, "principle": 3}
TIER_ORDER = {"immediate": 0, "delayed": 1, "transfer": 2}
TIER_WEIGHT = {"none": 0.0, "immediate": 0.4, "delayed": 0.7, "transfer": 1.0}
FRESHNESS_WEIGHT = {"fresh": 1.0, "stale": 0.5, "unknown": 0.2}
SUCCESS_VERDICTS = {"mastered"}
BASE_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 180
TEACHING_KINDS = {"checkpoint", "probe", "diagnostic"}  # asked in the same sitting as the teaching: never delayed
TRANSFER_KINDS = {"transfer", "final"}
DELAYED_MIN_HOURS = 8  # together with a local day boundary: "a night in between"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def local_day(at: datetime, tz: tzinfo) -> date:
    return at.astimezone(tz).date()


def is_delayed(previous: datetime, current: datetime, tz: tzinfo) -> bool:
    """True when `current` is on a later local day than `previous` and at least DELAYED_MIN_HOURS after it."""
    return current - previous >= timedelta(hours=DELAYED_MIN_HOURS) and local_day(current, tz) > local_day(previous, tz)


def tier_for(kind: str, previous_at: datetime | None, at: datetime, tz: tzinfo) -> str:
    """Evidence tier of one attempt for one concept: immediate unless a real retention interval precedes it."""
    if kind in TEACHING_KINDS or previous_at is None or not is_delayed(previous_at, at, tz):
        return "immediate"
    return "transfer" if kind in TRANSFER_KINDS else "delayed"


def freshness_window(stability: int) -> timedelta:
    days = min(BASE_WINDOW_DAYS * (2 ** max(stability - 1, 0)), MAX_WINDOW_DAYS)
    return timedelta(days=days)


def load_section_concepts(store: Path) -> dict[str, dict[str, list[str]]]:
    """{lesson_id: {section_id: [concept ids]}} from the public MRG exports."""
    mapping: dict[str, dict[str, list[str]]] = {}
    mrg_dir = store / "mrg"
    if not mrg_dir.is_dir():
        return mapping
    for path in sorted(mrg_dir.glob("*.json")):
        if path.name.endswith(".deep.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping[data.get("lesson_id")] = {s["id"]: list(s.get("concept_ids", [])) for s in data.get("sections", [])}
    return mapping


def load_events(store: Path) -> list[dict]:
    events: list[dict] = []
    lrg_dir = store / "lrg"
    if not lrg_dir.is_dir():
        return events
    for path in sorted(lrg_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = json.loads(line)
                if event.get("event") == "attempt":
                    events.append(event)
    events.sort(key=lambda e: e.get("at", ""))
    return events


def concepts_for_event(event: dict, section_concepts: dict) -> set[str]:
    ids: set[str] = set(section_concepts.get(event.get("lesson_id"), {}).get(event.get("section_id"), []))
    ids.update(event.get("target_concept_ids", []) or [])
    for prop in event.get("propositions", []) or []:
        ids.update(prop.get("concept_ids", []) or [])
    for item in (event.get("extraction") or {}).get("concepts", []) or []:
        ref = item.get("ref")
        if isinstance(ref, str) and "." in ref and " " not in ref:
            ids.add(ref)  # already an id
    return ids


def new_state() -> dict:
    return {
        "evidence_tier": "none",
        "last_evidence_at": None,
        "last_success_at": None,
        "last_verdict": None,
        "depth_latest": None,
        "depth_max": None,
        "stability": 0,
        "rigor_max": None,
        "attempts": 0,
        "freshness": "unknown",
        "error_propositions": [],
        "calibration": {"overconfident": 0, "underconfident": 0},
        "lessons": [],
        "mastery_estimate": 0.0,
    }


def build(store: Path, now: datetime | None = None, tz: tzinfo | None = None) -> dict:
    """Derive the state. `tz` fixes the local day boundary (defaults to this machine's zone)."""
    now = now or datetime.now(timezone.utc)
    tz = tz or datetime.now().astimezone().tzinfo or timezone.utc
    section_concepts = load_section_concepts(store)
    events = load_events(store)
    states: dict[str, dict] = {}
    success_days: dict[str, set[str]] = {}
    latest_success: dict[str, tuple[str, str]] = {}  # cid -> (at, tier) of the most recent success
    last_seen: dict[str, datetime] = {}  # cid -> time of the concept's previous record, any verdict

    for event in events:
        verdict = event.get("verdict")
        kind = event.get("kind", "checkpoint")
        depth = event.get("depth_reached")
        confidence = event.get("confidence")
        at = event.get("at")
        at_time = parse_time(at) if at else now
        conflicts_high = any(c.get("confidence_high") for c in (event.get("diff") or {}).get("conflict", []))
        rigor = event.get("rigor", "full")
        for cid in concepts_for_event(event, section_concepts):
            state = states.setdefault(cid, new_state())
            state["attempts"] += 1
            tier = tier_for(kind, last_seen.get(cid), at_time, tz)
            last_seen[cid] = at_time
            if verdict in SUCCESS_VERDICTS and (state["rigor_max"] is None or rigor == "full"):
                state["rigor_max"] = rigor
            state["last_evidence_at"] = at
            state["last_verdict"] = verdict
            if event.get("lesson_id") and event["lesson_id"] not in state["lessons"]:
                state["lessons"].append(event["lesson_id"])
            if depth in DEPTH_ORDER:
                state["depth_latest"] = depth
                if state["depth_max"] is None or DEPTH_ORDER[depth] > DEPTH_ORDER[state["depth_max"]]:
                    state["depth_max"] = depth
            if verdict in SUCCESS_VERDICTS:
                state["last_success_at"] = at
                latest_success[cid] = (at, tier)
                success_days.setdefault(cid, set()).add(local_day(at_time, tz).isoformat())
                if confidence is not None and confidence <= 2:
                    state["calibration"]["underconfident"] += 1
            elif verdict == "retry" or conflicts_high:
                if confidence is not None and confidence >= 4:
                    state["calibration"]["overconfident"] += 1
            for prop in event.get("propositions", []) or []:
                if prop.get("status") in {"wrong", "partial"} and cid in (prop.get("concept_ids") or []):
                    if not any(p["id"] == prop["id"] for p in state["error_propositions"]):
                        state["error_propositions"].append({
                            "id": prop["id"], "text": prop["text"], "status": prop["status"],
                            "at": at, "lesson_id": event.get("lesson_id"), "section_id": event.get("section_id"),
                        })

    for cid, state in states.items():
        state["stability"] = len(success_days.get(cid, set()))
        if cid in latest_success:
            at, tier = latest_success[cid]
            state["evidence_tier"] = tier
            if tier == "immediate":
                state["freshness"] = "unknown"
            else:
                age = now - parse_time(at)
                state["freshness"] = "fresh" if age <= freshness_window(state["stability"]) else "stale"
        else:
            state["evidence_tier"] = "none"
            state["freshness"] = "unknown"
        state["mastery_estimate"] = round(TIER_WEIGHT[state["evidence_tier"]] * FRESHNESS_WEIGHT[state["freshness"]], 3)

    return {
        "schema_version": store_init.STORE_SCHEMA,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "tier_rule": f"delayed/transfer only if the concept's previous record is on an earlier local day (UTC{now.astimezone(tz).strftime('%z')}) and at least {DELAYED_MIN_HOURS} h earlier; checkpoint/probe/diagnostic are always immediate",
        "freshness_rule": f"fresh if latest delayed/transfer success is within {BASE_WINDOW_DAYS}*2^(stability-1) days (max {MAX_WINDOW_DAYS}); immediate-only evidence is 'unknown'",
        "concepts": dict(sorted(states.items())),
    }


def parse_offset(value: str) -> tzinfo:
    """'+08:00' / '-0500' -> a fixed-offset zone for the local day boundary."""
    try:
        return datetime.strptime(value.replace(":", ""), "%z").tzinfo  # type: ignore[return-value]
    except ValueError:
        raise ValueError("--tz must be a UTC offset such as +08:00") from None


def command_build(args: argparse.Namespace) -> int:
    store_init.load_store(args.store)
    now = parse_time(args.now) if args.now else None
    state = build(args.store, now, tz=parse_offset(args.tz) if args.tz else None)
    store_init.atomic_write(args.store / "learner-state.json", state)
    counts: dict[str, int] = {}
    for concept in state["concepts"].values():
        counts[concept["freshness"]] = counts.get(concept["freshness"], 0) + 1
    print(f"OK: learner-state.json rebuilt for {len(state['concepts'])} concepts "
          f"(fresh={counts.get('fresh', 0)}, stale={counts.get('stale', 0)}, unknown={counts.get('unknown', 0)})")
    return 0


def command_show(args: argparse.Namespace) -> int:
    path = args.store / "learner-state.json"
    if not path.is_file():
        raise ValueError("learner-state.json not built yet; run `build`")
    state = json.loads(path.read_text(encoding="utf-8"))
    for cid, concept in state["concepts"].items():
        print(f"- {cid}: {concept['freshness']}/{concept['evidence_tier']} depth_max={concept['depth_max']} "
              f"stability={concept['stability']} errors={len(concept['error_propositions'])} est={concept['mastery_estimate']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="Rebuild learner-state.json from lrg/ and mrg/")
    b.add_argument("--store", type=Path, required=True)
    b.add_argument("--now", help="ISO timestamp to evaluate freshness against (tests)")
    b.add_argument("--tz", metavar="OFFSET", help="UTC offset for the local day boundary, e.g. +08:00 (default: this machine's zone)")
    b.set_defaults(handler=command_build)
    s = sub.add_parser("show", help="Summarise learner state (no response text)")
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
