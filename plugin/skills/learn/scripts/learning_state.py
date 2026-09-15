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
DONE_STATUSES = {"completed", "deferred"}
MARK_TYPES = {"probe_completed", "probe_skipped"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_time(value: str) -> str:
    """ISO 8601 with a zone offset -> UTC 'Z' form, the only form written to state files."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"--at must be an ISO 8601 time such as 2026-09-12T20:25:00+08:00 ({error})") from None
    if parsed.tzinfo is None:
        raise ValueError("--at needs a timezone offset, e.g. 2026-09-12T20:25:00+08:00")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def refresh_outline(progress_path: Path, store: Path | None = None) -> None:
    """Keep outline.md next to the progress file current; never fails a record."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("outline_status", Path(__file__).resolve().parent / "outline_status.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        module.refresh(Path(progress_path).resolve().parent, store)
    except Exception as error:  # noqa: BLE001 — the record itself must not depend on the outline
        print(f"note: outline.md not refreshed ({error})")


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
    deferred = {item.get("id") for item in (plan.get("deferred") or []) if isinstance(item, dict) and item.get("type") == "section"}
    section_states = []
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("id"), str) or not section["id"].strip():
            raise ValueError("every lesson section needs a non-empty id")
        status = "deferred" if section["id"] in deferred else "pending"
        section_states.append({"id": section["id"], "status": status, "attempts": []})
    first = next((item for item in section_states if item["status"] != "deferred"), None)
    if first is None:
        raise ValueError("every section is deferred; nothing to teach")
    now = utc_now()
    return {
        "schema_version": "1.0",
        "lesson_id": plan.get("lesson_id"),
        "mode": plan.get("mode", "full"),
        "created_at": now,
        "updated_at": now,
        "status": "in_progress",
        "current_section_id": first["id"],
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
        pending = next((item for item in sections[start:] if item.get("status") not in DONE_STATUSES), None)
        if pending is None:
            pending = next((item for item in sections if item.get("status") not in DONE_STATUSES), None)
        current = pending.get("id") if pending else None
    elif current not in ids:
        pending = next((item for item in sections if item.get("status") not in DONE_STATUSES), None)
        current = pending.get("id") if pending else None

    all_completed = all(item.get("status") in DONE_STATUSES for item in sections)
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
    at: str | None = None,
    force: bool = False,
) -> None:
    """Append one attempt. `at` backfills the learner's time (ISO 8601 with offset); an identical
    response for the same section and kind is refused unless `force`."""
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
    if section.get("status") == "deferred":
        raise ValueError(f"section {section_id} is deferred in this course; un-defer it in the lesson plan first")
    if section.get("blocked_by") and not review:
        raise ValueError(f"section {section_id} is blocked by prerequisite course '{section['blocked_by']}'; "
                         f"finish that course (or `unblock`) before recording an attempt here")
    kind = "review" if review else "checkpoint"
    for earlier in section.get("attempts", []):
        if earlier.get("kind") == kind and (earlier.get("response") or "").strip() == response.strip() and not force:
            raise ValueError(f"section {section_id} already has an identical {kind} response "
                             f"(attempt #{earlier.get('attempt_number')} at {earlier.get('at')}); pass --force to append anyway")
    now = normalize_time(at) if at else utc_now()
    attempt = {
        "attempt_number": len(section.get("attempts", [])) + 1,
        "at": now,
        "kind": kind,
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
        review=args.review, criteria_met=criteria_met, depth_reached=args.depth, at=args.at, force=args.force,
    )
    atomic_write(args.state, state)
    refresh_outline(args.state)
    print(f"OK: appended {'review' if args.review else 'checkpoint'} attempt for {args.section_id}")
    return 0


def mark_event(state: dict, event_type: str, note: str | None = None) -> None:
    """Append a milestone that has no other trace in the file (the probe round is one)."""
    if event_type not in MARK_TYPES:
        raise ValueError(f"event type must be one of {sorted(MARK_TYPES)}")
    now = utc_now()
    event: dict[str, Any] = {"at": now, "type": event_type}
    if note and note.strip():
        event["note"] = note.strip()
    state.setdefault("events", []).append(event)
    state["updated_at"] = now


def command_mark(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    mark_event(state, args.type, args.note)
    atomic_write(args.state, state)
    refresh_outline(args.state)
    print(f"OK: marked {args.type} in {args.state}")
    return 0


def defer_section(state: dict, section_id: str, reason: str) -> None:
    """Mark a not-yet-started section deferred (probe passed, or the learner chose to skip).

    Only pending sections can be deferred here; a section with attempts keeps its
    evidence and must be skipped through a recorded verdict instead.
    """
    if not reason.strip():
        raise ValueError("a reason is required to defer a section")
    section = find_section(state, section_id)
    if section.get("status") == "deferred":
        raise ValueError(f"section {section_id} is already deferred")
    if section.get("attempts"):
        raise ValueError(f"section {section_id} already has attempts; record a verdict instead of deferring it")
    now = utc_now()
    section["status"] = "deferred"
    section["deferred_reason"] = reason.strip()
    state.setdefault("events", []).append({"at": now, "type": "section_deferred", "section_id": section_id, "reason": reason.strip()})
    was_completed = state.get("status") == "completed"
    recompute_position(state, section_id)
    if state["status"] == "completed" and not was_completed:
        state["events"].append({"at": now, "type": "lesson_completed"})
    state["updated_at"] = now


def block_section(state: dict, section_id: str, child_lesson_id: str) -> None:
    """Mark a section as waiting on a prerequisite course. The parent stays in_progress at that section;
    attempts on it are refused until `unblock` (normally run when the child course finishes)."""
    if not child_lesson_id or not child_lesson_id.strip():
        raise ValueError("--by must name the prerequisite course")
    section = find_section(state, section_id)
    if section.get("status") == "deferred":
        raise ValueError(f"section {section_id} is deferred; it cannot be blocked")
    if section.get("blocked_by"):
        raise ValueError(f"section {section_id} is already blocked by '{section['blocked_by']}'")
    now = utc_now()
    section["blocked_by"] = child_lesson_id.strip()
    state["blocked"] = {"section_id": section_id, "by": section["blocked_by"], "at": now}
    state["status"] = "in_progress"
    state["current_section_id"] = section_id
    state.setdefault("events", []).append({"at": now, "type": "section_blocked", "section_id": section_id, "by": section["blocked_by"]})


def unblock_section(state: dict, section_id: str) -> str:
    section = find_section(state, section_id)
    child = section.get("blocked_by")
    if not child:
        raise ValueError(f"section {section_id} is not blocked")
    now = utc_now()
    del section["blocked_by"]
    state.pop("blocked", None)
    state["current_section_id"] = section_id
    state.setdefault("events", []).append({"at": now, "type": "section_unblocked", "section_id": section_id, "by": child})
    return child


def command_block(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if not isinstance(state, dict):
        raise ValueError("progress state root must be an object")
    block_section(state, args.section_id, args.by)
    atomic_write(args.state, state)
    refresh_outline(args.state)
    print(f"OK: {args.section_id} blocked by prerequisite course '{args.by}'; resume this course after it finishes")
    return 0


def command_unblock(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if not isinstance(state, dict):
        raise ValueError("progress state root must be an object")
    child = unblock_section(state, args.section_id)
    atomic_write(args.state, state)
    refresh_outline(args.state)
    print(f"OK: {args.section_id} unblocked (prerequisite course '{child}' done); current section is {state.get('current_section_id')}")
    return 0


def command_defer(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if not isinstance(state, dict):
        raise ValueError("progress state root must be an object")
    defer_section(state, args.section_id, args.reason)
    atomic_write(args.state, state)
    refresh_outline(args.state)
    print(f"OK: deferred {args.section_id} ({args.reason}); current section is now {state.get('current_section_id')}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    print(f"lesson_id: {state.get('lesson_id')}")
    print(f"status: {state.get('status')}")
    print(f"current_section_id: {state.get('current_section_id')}")
    if state.get("blocked"):
        print(f"blocked: {state['blocked'].get('section_id')} waits for prerequisite course '{state['blocked'].get('by')}'")
    for section in state.get("sections", []):
        attempts = section.get("attempts", [])
        depths = [a.get("depth_reached") for a in attempts if a.get("depth_reached")]
        depth_note = f", depth {' → '.join(depths)}" if depths else ""
        blocked_note = f", blocked by {section['blocked_by']}" if section.get("blocked_by") else ""
        print(f"- {section.get('id')}: {section.get('status')} ({len(attempts)} attempts{depth_note}{blocked_note})")
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
    record_parser.add_argument("--at", metavar="TIME", help="Backfill: when the attempt really happened (ISO 8601 with offset)")
    record_parser.add_argument("--force", action="store_true", help="Append even if an identical response for this section exists")
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

    defer_parser = subparsers.add_parser("defer", help="Defer a pending section (probe passed / learner chose to skip)")
    defer_parser.add_argument("--state", type=Path, required=True)
    defer_parser.add_argument("--section-id", required=True)
    defer_parser.add_argument("--reason", required=True, help="Why it is skipped, e.g. '原理探测通过，学习者选择跳过'")
    defer_parser.set_defaults(handler=command_defer)

    block_parser = subparsers.add_parser("block", help="Mark a section as waiting on a prerequisite course")
    block_parser.add_argument("--state", type=Path, required=True)
    block_parser.add_argument("--section-id", required=True)
    block_parser.add_argument("--by", required=True, help="lesson_id of the prerequisite course")
    block_parser.set_defaults(handler=command_block)

    unblock_parser = subparsers.add_parser("unblock", help="Release a blocked section (the prerequisite course finished)")
    unblock_parser.add_argument("--state", type=Path, required=True)
    unblock_parser.add_argument("--section-id", required=True)
    unblock_parser.set_defaults(handler=command_unblock)

    mark_parser = subparsers.add_parser("mark", help="Append a free event to the progress file (e.g. probe_completed)")
    mark_parser.add_argument("--state", type=Path, required=True)
    mark_parser.add_argument("--type", required=True, choices=sorted(MARK_TYPES))
    mark_parser.add_argument("--note", help="Optional one-line note")
    mark_parser.set_defaults(handler=command_mark)

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
