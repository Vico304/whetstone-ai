#!/usr/bin/env python3
"""Initialize and append to a scoped prerequisite-assessment progress file."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ASSESSMENT_VERDICTS = {"ready", "fragile", "gap", "misconception", "skipped"}
BRIDGE_VERDICTS = {"ready", "retry", "skipped"}
SOURCE_TIERS = {"official_or_primary", "standards_or_textbooks", "reputable_secondary"}


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
    prerequisites = plan.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("prerequisite plan has no prerequisites")
    competencies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for prerequisite in prerequisites:
        if not isinstance(prerequisite, dict):
            raise ValueError("every prerequisite must be an object")
        prerequisite_id = prerequisite.get("id")
        name = prerequisite.get("name")
        if not isinstance(prerequisite_id, str) or not prerequisite_id.strip():
            raise ValueError("every prerequisite needs a non-empty id")
        if prerequisite_id in seen:
            raise ValueError(f"duplicate prerequisite id: {prerequisite_id}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("every prerequisite needs a non-empty name")
        seen.add(prerequisite_id)
        competencies.append(
            {
                "id": prerequisite_id,
                "name": name,
                "status": "unassessed",
                "assessment_attempts": [],
                "supplement_sources": [],
                "bridge_attempts": [],
            }
        )
    now = utc_now()
    return {
        "schema_version": "1.0",
        "lesson_id": plan.get("lesson_id"),
        "scope_statement": plan.get("scope_statement"),
        "created_at": now,
        "updated_at": now,
        "status": "in_progress",
        "phase": "assessment",
        "current_prerequisite_id": competencies[0]["id"],
        "competencies": competencies,
        "events": [{"at": now, "type": "prerequisite_assessment_initialized"}],
    }


def find_competency(state: dict, prerequisite_id: str) -> dict:
    for competency in state.get("competencies", []):
        if isinstance(competency, dict) and competency.get("id") == prerequisite_id:
            return competency
    raise ValueError(f"unknown prerequisite id: {prerequisite_id}")


def validate_confidence(confidence: int | None) -> None:
    if confidence is not None and not 1 <= confidence <= 5:
        raise ValueError("confidence must be between 1 and 5")


def recompute_state(state: dict) -> None:
    competencies = [item for item in state.get("competencies", []) if isinstance(item, dict)]
    unassessed = next((item for item in competencies if item.get("status") == "unassessed"), None)
    if unassessed is not None:
        state["status"] = "in_progress"
        state["phase"] = "assessment"
        state["current_prerequisite_id"] = unassessed.get("id")
    else:
        needs_supplement = next((item for item in competencies if item.get("status") == "needs_supplement"), None)
        if needs_supplement is not None:
            state["status"] = "in_progress"
            state["phase"] = "supplement"
            state["current_prerequisite_id"] = needs_supplement.get("id")
        else:
            state["status"] = "ready_for_main_course"
            state["phase"] = "ready"
            state["current_prerequisite_id"] = None
    state["updated_at"] = utc_now()


def append_assessment(
    state: dict,
    prerequisite_id: str,
    response: str,
    feedback: str,
    verdict: str,
    confidence: int | None,
) -> None:
    if verdict not in ASSESSMENT_VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(ASSESSMENT_VERDICTS)}")
    validate_confidence(confidence)
    competency = find_competency(state, prerequisite_id)
    now = utc_now()
    attempts = competency.setdefault("assessment_attempts", [])
    attempts.append(
        {
            "attempt_number": len(attempts) + 1,
            "at": now,
            "response": response,
            "feedback": feedback,
            "verdict": verdict,
            "confidence": confidence,
        }
    )
    if verdict == "ready":
        competency["status"] = "ready"
    elif verdict == "skipped":
        competency["status"] = "waived"
    else:
        competency["status"] = "needs_supplement"
    state.setdefault("events", []).append(
        {"at": now, "type": "prerequisite_assessment_recorded", "prerequisite_id": prerequisite_id, "verdict": verdict}
    )
    recompute_state(state)


def validate_web_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source URL must be an absolute http(s) URL")


def add_source(
    state: dict,
    prerequisite_id: str,
    title: str,
    publisher: str,
    url: str,
    source_tier: str,
    note: str,
) -> None:
    if source_tier not in SOURCE_TIERS:
        raise ValueError(f"source tier must be one of {sorted(SOURCE_TIERS)}")
    for label, value in (("title", title), ("publisher", publisher), ("note", note)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"source {label} must be a non-empty string")
    validate_web_url(url)
    competency = find_competency(state, prerequisite_id)
    now = utc_now()
    sources = competency.setdefault("supplement_sources", [])
    sources.append(
        {
            "source_number": len(sources) + 1,
            "title": title,
            "publisher": publisher,
            "url": url,
            "source_tier": source_tier,
            "support": "external",
            "note": note,
            "accessed_at": now,
        }
    )
    state.setdefault("events", []).append(
        {"at": now, "type": "prerequisite_source_added", "prerequisite_id": prerequisite_id, "url": url}
    )
    state["updated_at"] = now


def append_bridge(
    state: dict,
    prerequisite_id: str,
    response: str,
    feedback: str,
    verdict: str,
    confidence: int | None,
) -> None:
    if verdict not in BRIDGE_VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(BRIDGE_VERDICTS)}")
    validate_confidence(confidence)
    competency = find_competency(state, prerequisite_id)
    if not competency.get("assessment_attempts"):
        raise ValueError("cannot record a bridge attempt before an assessment attempt")
    now = utc_now()
    attempts = competency.setdefault("bridge_attempts", [])
    attempts.append(
        {
            "attempt_number": len(attempts) + 1,
            "at": now,
            "response": response,
            "feedback": feedback,
            "verdict": verdict,
            "confidence": confidence,
        }
    )
    if verdict == "ready":
        competency["status"] = "ready"
    elif verdict == "skipped":
        competency["status"] = "waived"
    else:
        competency["status"] = "needs_supplement"
    state.setdefault("events", []).append(
        {"at": now, "type": "prerequisite_bridge_recorded", "prerequisite_id": prerequisite_id, "verdict": verdict}
    )
    recompute_state(state)


def command_init(args: argparse.Namespace) -> int:
    if args.output.exists():
        raise ValueError(f"refusing to overwrite existing progress file: {args.output}")
    plan = read_json(args.prerequisite_plan)
    if not isinstance(plan, dict):
        raise ValueError("prerequisite plan root must be an object")
    atomic_write(args.output, create_state(plan))
    print(f"OK: created {args.output}")
    return 0


def command_record(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if not isinstance(state, dict):
        raise ValueError("prerequisite state root must be an object")
    response = args.response_file.read_text(encoding="utf-8")
    feedback = args.feedback_file.read_text(encoding="utf-8") if args.feedback_file else ""
    append_assessment(state, args.prerequisite_id, response, feedback, args.verdict, args.confidence)
    atomic_write(args.state, state)
    print(f"OK: appended assessment for {args.prerequisite_id}")
    return 0


def command_add_source(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if not isinstance(state, dict):
        raise ValueError("prerequisite state root must be an object")
    add_source(state, args.prerequisite_id, args.title, args.publisher, args.url, args.source_tier, args.note)
    atomic_write(args.state, state)
    print(f"OK: added source for {args.prerequisite_id}")
    return 0


def command_bridge(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if not isinstance(state, dict):
        raise ValueError("prerequisite state root must be an object")
    response = args.response_file.read_text(encoding="utf-8")
    feedback = args.feedback_file.read_text(encoding="utf-8") if args.feedback_file else ""
    append_bridge(state, args.prerequisite_id, response, feedback, args.verdict, args.confidence)
    atomic_write(args.state, state)
    print(f"OK: appended bridge attempt for {args.prerequisite_id}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    state = read_json(args.state)
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    print(f"lesson_id: {state.get('lesson_id')}")
    print(f"status: {state.get('status')}")
    print(f"phase: {state.get('phase')}")
    print(f"current_prerequisite_id: {state.get('current_prerequisite_id')}")
    for competency in state.get("competencies", []):
        print(
            f"- {competency.get('id')}: {competency.get('status')} "
            f"({len(competency.get('assessment_attempts', []))} assessments, "
            f"{len(competency.get('supplement_sources', []))} sources, "
            f"{len(competency.get('bridge_attempts', []))} bridge attempts)"
        )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a prerequisite progress file")
    init_parser.add_argument("--prerequisite-plan", type=Path, required=True)
    init_parser.add_argument("--output", type=Path, required=True)
    init_parser.set_defaults(handler=command_init)

    record_parser = subparsers.add_parser("record", help="Append a prerequisite assessment attempt")
    record_parser.add_argument("--state", type=Path, required=True)
    record_parser.add_argument("--prerequisite-id", required=True)
    record_parser.add_argument("--response-file", type=Path, required=True)
    record_parser.add_argument("--feedback-file", type=Path)
    record_parser.add_argument("--verdict", choices=sorted(ASSESSMENT_VERDICTS), required=True)
    record_parser.add_argument("--confidence", type=int)
    record_parser.set_defaults(handler=command_record)

    source_parser = subparsers.add_parser("add-source", help="Attach a cited external source to a prerequisite")
    source_parser.add_argument("--state", type=Path, required=True)
    source_parser.add_argument("--prerequisite-id", required=True)
    source_parser.add_argument("--title", required=True)
    source_parser.add_argument("--publisher", required=True)
    source_parser.add_argument("--url", required=True)
    source_parser.add_argument("--source-tier", choices=sorted(SOURCE_TIERS), required=True)
    source_parser.add_argument("--note", required=True)
    source_parser.set_defaults(handler=command_add_source)

    bridge_parser = subparsers.add_parser("bridge", help="Append a post-supplement bridge attempt")
    bridge_parser.add_argument("--state", type=Path, required=True)
    bridge_parser.add_argument("--prerequisite-id", required=True)
    bridge_parser.add_argument("--response-file", type=Path, required=True)
    bridge_parser.add_argument("--feedback-file", type=Path)
    bridge_parser.add_argument("--verdict", choices=sorted(BRIDGE_VERDICTS), required=True)
    bridge_parser.add_argument("--confidence", type=int)
    bridge_parser.set_defaults(handler=command_bridge)

    show_parser = subparsers.add_parser("show", help="Show prerequisite progress")
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

