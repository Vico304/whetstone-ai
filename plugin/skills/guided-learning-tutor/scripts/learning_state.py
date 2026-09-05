#!/usr/bin/env python3
"""Initialize and append to a guided-learning progress file."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERDICTS = {"mastered", "partial", "retry", "skipped"}
DEPTHS = ("fact", "mechanism", "rationale", "principle")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def create_state(plan: dict) -> dict:
    sections = plan.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("lesson plan has no sections")
    section_states = []
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("id"), str) or not section["id"].strip():
            raise ValueError("every lesson section needs a non-empty id")
        section_states.append({"id": section["id"], "status": "pending", "attempts": []})
    now = utc_now()
    return {
        "schema_version": "1.0",
        "lesson_id": plan.get("lesson_id"),
        "created_at": now,
        "updated_at": now,
        "status": "in_progress",
        "current_section_id": section_states[0]["id"],
        "sections": section_states,
        "events": [{"at": now, "type": "initialized"}],
    }


def find_section(state: dict, section_id: str) -> dict:
    for section in state.get("sections", []):
        if isinstance(section, dict) and section.get("id") == section_id:
            return section
    raise ValueError(f"unknown section id: {section_id}")


def recompute_position(state: dict, recorded_id: str) -> None:
    """Update lesson status and current position after an attempt.

    The current position never moves backwards on its own. A review attempt
    (resume-time variant retrieval on an earlier, already completed section)
    may flip that section back to ``in_progress`` as a forgetting signal, but
    the learner keeps working from where they actually are. Regressed sections
    are only revisited once every later section is completed.
    """
    sections = [item for item in state.get("sections", []) if isinstance(item, dict)]
    ids = [item.get("id") for item in sections]
    current = state.get("current_section_id")

    if current is None or current == recorded_id:
        start = ids.index(recorded_id) if recorded_id in ids else 0
        pending = next((item for item in sections[start:] if item.get("status") != "completed"), None)
        if pending is None:
            pending = next((item for item in sections if item.get("status") != "completed"), None)
        current = pending.get("id") if pending else None
    elif current not in ids:
        pending = next((item for item in sections if item.get("status") != "completed"), None)
        current = pending.get("id") if pending else None

    all_completed = all(item.get("status") == "completed" for item in sections)
    if all_completed:
        state["status"] = "completed"
        state["current_section_id"] = None
    else:
        state["status"] = "in_progress"
        state["current_section_id"] = current


def append_attempt(
    state: dict,
    section_id: str,
    response: str,
    feedback: str,
    verdict: str,
    confidence: int | None,
    review: bool = False,
    criteria_met: list[str] | None = None,
    depth_reached: str | None = None,
) -> None:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    if confidence is not None and not 1 <= confidence <= 5:
        raise ValueError("confidence must be between 1 and 5")
    if depth_reached is not None and depth_reached not in DEPTHS:
        raise ValueError(f"depth_reached must be one of {list(DEPTHS)}")
    criteria_met = [item.strip() for item in (criteria_met or []) if item and item.strip()]
    if len(criteria_met) != len(set(criteria_met)):
        raise ValueError("criteria_met must not repeat ids")
    section = find_section(state, section_id)
    now = utc_now()
    attempt = {
        "attempt_number": len(section.get("attempts", [])) + 1,
        "at": now,
        "kind": "review" if review else "checkpoint",
        "response": response,
        "feedback": feedback,
        "verdict": verdict,
        "confidence": confidence,
        "criteria_met": criteria_met,
        "depth_reached": depth_reached,
    }
    section.setdefault("attempts", []).append(attempt)
    section["status"] = "completed" if verdict in {"mastered", "skipped"} else "in_progress"
    state.setdefault("events", []).append(
        {"at": now, "type": "attempt_recorded", "section_id": section_id, "verdict": verdict, "kind": attempt["kind"]}
    )

    was_completed = state.get("status") == "completed"
    recompute_position(state, section_id)
    if state["status"] == "completed" and not was_completed:
        state["events"].append({"at": now, "type": "lesson_completed"})
    state["updated_at"] = now


def command_init(args: argparse.Namespace) -> int:
    if args.output.exists():
        raise ValueError(f"refusing to overwrite existing progress file: {args.output}")
    plan = read_json(args.lesson_plan)
    if not isinstance(plan, dict):
        raise ValueError("lesson plan root must be an object")
    atomic_write(args.output, create_state(plan))
    print(f"OK: created {args.output}")
    return 0


def command_record(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if not isinstance(state, dict):
        raise ValueError("progress state root must be an object")
    response = args.response_file.read_text(encoding="utf-8")
    feedback = args.feedback_file.read_text(encoding="utf-8") if args.feedback_file else ""
    criteria_met = [item for chunk in (args.criteria_met or []) for item in chunk.split(",")]
    append_attempt(
        state, args.section_id, response, feedback, args.verdict, args.confidence,
        review=args.review, criteria_met=criteria_met, depth_reached=args.depth,
    )
    atomic_write(args.state, state)
    print(f"OK: appended {'review' if args.review else 'checkpoint'} attempt for {args.section_id}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    print(f"lesson_id: {state.get('lesson_id')}")
    print(f"status: {state.get('status')}")
    print(f"current_section_id: {state.get('current_section_id')}")
    for section in state.get("sections", []):
        attempts = section.get("attempts", [])
        depths = [a.get("depth_reached") for a in attempts if a.get("depth_reached")]
        depth_note = f", depth {' → '.join(depths)}" if depths else ""
        print(f"- {section.get('id')}: {section.get('status')} ({len(attempts)} attempts{depth_note})")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new progress file")
    init_parser.add_argument("--lesson-plan", type=Path, required=True)
    init_parser.add_argument("--output", type=Path, required=True)
    init_parser.set_defaults(handler=command_init)

    record_parser = subparsers.add_parser("record", help="Append a learner attempt")
    record_parser.add_argument("--state", type=Path, required=True)
    record_parser.add_argument("--section-id", required=True)
    record_parser.add_argument("--response-file", type=Path, required=True)
    record_parser.add_argument("--feedback-file", type=Path)
    record_parser.add_argument("--verdict", choices=sorted(VERDICTS), required=True)
    record_parser.add_argument("--confidence", type=int)
    record_parser.add_argument(
        "--criteria-met",
        action="append",
        metavar="IDS",
        help="Comma-separated checkpoint criteria ids the answer satisfied (e.g. c1,c3); repeatable",
    )
    record_parser.add_argument(
        "--depth",
        choices=DEPTHS,
        help="Deepest understanding layer the answer actually reached (a layer, not a verdict)",
    )
    record_parser.add_argument(
        "--review",
        action="store_true",
        help="Variant-retrieval review of an already completed section (e.g. resume opener); "
        "does not move the current position backwards",
    )
    record_parser.set_defaults(handler=command_record)

    show_parser = subparsers.add_parser("show", help="Show current progress")
    show_parser.add_argument("--state", type=Path, required=True)
    show_parser.add_argument("--json", action="store_true")
    show_parser.set_defaults(handler=command_show)
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
