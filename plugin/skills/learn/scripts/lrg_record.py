#!/usr/bin/env python3
"""Append one learner attempt to the store's reconstruction log (LRG) and, optionally,
mirror it into the lesson pack's learning-progress.json in the same command.

The log is append-only and is never shown to the learner. `show` prints counts and
layers only; it never prints response text. The raw response stays in the log so the
system can later derive de-personalised propositions — it must not be quoted back.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
KINDS = ("checkpoint", "review", "variant", "transfer", "bridge", "final")
IMMEDIATE_KINDS = {"checkpoint", "bridge"}
DELAYED_KINDS = {"review", "variant"}
TRANSFER_KINDS = {"transfer", "final"}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


learning_state = _load("learning_state")
comparator = _load("comparator")
store_init = _load("store_init")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def evidence_tier(kind: str) -> str:
    if kind in TRANSFER_KINDS:
        return "transfer"
    if kind in DELAYED_KINDS:
        return "delayed"
    return "immediate"


def log_path(store: Path, lesson_id: str) -> Path:
    return store / "lrg" / f"{lesson_id}.jsonl"


def read_events(store: Path, lesson_id: str) -> list[dict]:
    path = log_path(store, lesson_id)
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def append_event(store: Path, lesson_id: str, event: dict) -> None:
    path = log_path(store, lesson_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def build_event(
    *,
    lesson_id: str,
    section_id: str,
    kind: str,
    attempt_number: int,
    response: str,
    feedback: str,
    verdict: str,
    confidence: int | None,
    criteria_met: list[str],
    depth_reached: str | None,
    extraction: dict | None,
    comparison: dict | None,
    elapsed_seconds: int | None,
) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {list(KINDS)}")
    if verdict not in learning_state.VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(learning_state.VERDICTS)}")
    if depth_reached is not None and depth_reached not in learning_state.DEPTHS:
        raise ValueError(f"depth_reached must be one of {list(learning_state.DEPTHS)}")
    if confidence is not None and not 1 <= confidence <= 5:
        raise ValueError("confidence must be between 1 and 5")
    if extraction is not None and extraction.get("extracted_by") not in {"model", "learner"}:
        raise ValueError("extraction.extracted_by must be 'model' or 'learner'")
    event: dict[str, Any] = {
        "at": utc_now(),
        "event": "attempt",
        "lesson_id": lesson_id,
        "section_id": section_id,
        "kind": kind,
        "evidence_tier": evidence_tier(kind),
        "attempt_number": attempt_number,
        "confidence": confidence,
        "verdict": verdict,
        "criteria_met": criteria_met,
        "depth_reached": depth_reached,
        "response": response,
        "feedback": feedback,
    }
    if elapsed_seconds is not None:
        event["elapsed_seconds"] = elapsed_seconds
    if extraction is not None:
        event["extraction"] = extraction
    if comparison is not None:
        event["propositions"] = comparison.get("propositions", [])
        event["diff"] = comparison.get("diff", {})
        event["feedback_priority"] = comparison.get("feedback_priority", [])
    return event


def command_append(args: argparse.Namespace) -> int:
    store_init.load_store(args.store)  # validates the store
    response = args.response_file.read_text(encoding="utf-8")
    feedback = args.feedback_file.read_text(encoding="utf-8") if args.feedback_file else ""
    criteria_met = [c.strip() for chunk in (args.criteria_met or []) for c in chunk.split(",") if c.strip()]

    extraction = json.loads(args.extraction.read_text(encoding="utf-8")) if args.extraction else None
    comparison = None
    if extraction is not None and not args.no_compare:
        reference = comparator.load_reference(args.store, args.lesson_id)
        comparison = comparator.compare(reference, args.section_id, extraction)

    attempt_number = None
    if args.progress:
        state = learning_state.read_json(args.progress)
        learning_state.append_attempt(
            state, args.section_id, response, feedback, args.verdict, args.confidence,
            review=(args.kind == "review"), criteria_met=criteria_met, depth_reached=args.depth,
        )
        attempt_number = learning_state.find_section(state, args.section_id)["attempts"][-1]["attempt_number"]
        learning_state.atomic_write(args.progress, state)
    if attempt_number is None:
        attempt_number = 1 + sum(
            1 for e in read_events(args.store, args.lesson_id)
            if e.get("event") == "attempt" and e.get("section_id") == args.section_id
        )

    event = build_event(
        lesson_id=args.lesson_id, section_id=args.section_id, kind=args.kind, attempt_number=attempt_number,
        response=response, feedback=feedback, verdict=args.verdict, confidence=args.confidence,
        criteria_met=criteria_met, depth_reached=args.depth, extraction=extraction, comparison=comparison,
        elapsed_seconds=args.elapsed_seconds,
    )
    append_event(args.store, args.lesson_id, event)
    summary = f"OK: appended {args.kind} attempt #{attempt_number} for {args.lesson_id}/{args.section_id}"
    if comparison is not None:
        summary += f" (feedback priority: {', '.join(comparison['feedback_priority']) or 'none'})"
    print(summary)
    return 0


def command_show(args: argparse.Namespace) -> int:
    events = read_events(args.store, args.lesson_id)
    attempts = [e for e in events if e.get("event") == "attempt"]
    print(f"lesson: {args.lesson_id}  attempts: {len(attempts)}")
    by_section: dict[str, list[dict]] = {}
    for e in attempts:
        by_section.setdefault(e["section_id"], []).append(e)
    for section_id, items in by_section.items():
        kinds = ",".join(e["kind"][0] for e in items)
        depths = " → ".join(e["depth_reached"] or "?" for e in items)
        verdicts = ",".join(e["verdict"] for e in items)
        conflicts = sum(len(e.get("diff", {}).get("conflict", [])) for e in items)
        print(f"- {section_id}: {len(items)} attempts [{kinds}] verdicts {verdicts} | depth {depths} | conflicts {conflicts}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("append", help="Append one attempt event")
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--lesson-id", required=True)
    p.add_argument("--section-id", required=True)
    p.add_argument("--kind", choices=KINDS, default="checkpoint")
    p.add_argument("--response-file", type=Path, required=True)
    p.add_argument("--feedback-file", type=Path)
    p.add_argument("--verdict", choices=sorted(learning_state.VERDICTS), required=True)
    p.add_argument("--confidence", type=int)
    p.add_argument("--criteria-met", action="append", metavar="IDS")
    p.add_argument("--depth", choices=learning_state.DEPTHS)
    p.add_argument("--extraction", type=Path, help="Model extraction JSON; triggers the comparator")
    p.add_argument("--no-compare", action="store_true", help="Store the extraction without running the comparator")
    p.add_argument("--progress", type=Path, help="learning-progress.json to mirror the attempt into")
    p.add_argument("--elapsed-seconds", type=int, help="Wall-clock time for this section step (interaction-cost metric)")
    p.set_defaults(handler=command_append)
    s = sub.add_parser("show", help="Counts and layers only; never prints responses")
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
