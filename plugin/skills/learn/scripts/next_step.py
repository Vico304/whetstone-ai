#!/usr/bin/env python3
"""Where is this course, what to read, what to run — from learning-progress.json alone.

  next_step.py --progress <course>/learning-progress.json [--lesson-plan <plan>] [--store <store>] [--resume]

Prints one block: the lesson, the current section and its state, the single protocol file to
read for that state, and the next commands with their paths filled in. The state machine's
loading table (references/protocol/_state-machine.md) stays the reference; this script applies
it so the model does not have to hold it.

States: BLOCKED (waiting on a prerequisite course), RESUME (a new sitting: variant question
first), PROBE (skeleton course before its probe round), READY (section not answered yet:
READY → PREDICT → MAIN in the conversation), AWAITING_RETRY (last verdict partial/retry:
one follow-up, then assess again), FINISH (every section done).
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL = SCRIPT_DIR.parent / "references" / "protocol"
NEW_SITTING_AFTER = timedelta(hours=1)
WEAK_VERDICTS = {"partial", "retry"}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def section_titles(plan: dict | None) -> dict[str, str]:
    if not plan:
        return {}
    return {s.get("id"): s.get("title") or "" for s in plan.get("sections", []) if isinstance(s, dict)}


def decide(progress: dict, plan: dict | None, now: datetime, resume: bool) -> dict:
    """The state and the reasons; pure function for tests."""
    sections = [s for s in progress.get("sections", []) if isinstance(s, dict)]
    events = [e for e in progress.get("events", []) if isinstance(e, dict)]
    done = sum(1 for s in sections if s.get("status") == "completed")
    deferred = [s["id"] for s in sections if s.get("status") == "deferred"]
    regressed = [s["id"] for s in sections if s.get("status") == "in_progress" and s.get("id") != progress.get("current_section_id")]
    blocked = next((s for s in sections if s.get("blocked_by") and s.get("status") != "completed"), None)
    updated = parse_time(progress.get("updated_at"))
    new_sitting = resume or (updated is not None and now - updated >= NEW_SITTING_AFTER)
    shape = (plan or {}).get("shape", "linear")
    probed = any(e.get("type") == "probe_completed" for e in events)
    any_attempts = any(s.get("attempts") for s in sections)
    out = {"done": done, "total": len(sections), "deferred": deferred, "regressed": regressed, "new_sitting": new_sitting,
           "section_id": progress.get("current_section_id"), "opener": None}

    if blocked:
        out.update(state="BLOCKED", section_id=blocked["id"], blocked_by=blocked["blocked_by"],
                   read="../prerequisite/return.md", why=f"section {blocked['id']} waits on prerequisite course '{blocked['blocked_by']}'")
        return out
    if progress.get("status") == "completed" or out["section_id"] is None:
        out.update(state="FINISH", read="finish.md", why="every section is completed or deferred")
        return out
    if shape == "skeleton" and not probed and not any_attempts and not deferred:  # review courses have no probe round
        out.update(state="PROBE", read="probe.md", why="skeleton course: the probe round has not been recorded (learning_state.py mark --type probe_completed)")
        return out
    current = next((s for s in sections if s.get("id") == out["section_id"]), None)
    attempts = (current or {}).get("attempts") or []
    if new_sitting and done:
        out["opener"] = "resume.md"
    last = attempts[-1] if attempts else None
    if last and last.get("verdict") in WEAK_VERDICTS:
        out.update(state="AWAITING_RETRY", read="feedback.md", attempt_number=last.get("attempt_number"), last_verdict=last.get("verdict"),
                   why=f"attempt #{last.get('attempt_number')} was {last.get('verdict')}: one targeted follow-up, then assess again")
    elif shape == "review":
        out.update(state="READY", read="main.md", why="review course: ask the main question first (no PREDICT reveal); reveal units/<id>.md only after the verdict")
    else:
        out.update(state="READY", read="ready.md", why="no attempt on this section yet: READY → PREDICT → MAIN, then wait for the answer")
    return out


def q(path: Path | str) -> str:
    """Shell-quoted path (course directories often contain spaces)."""
    return shlex.quote(str(path))


def render(decision: dict, progress: dict, plan: dict | None, args: argparse.Namespace) -> str:
    titles = section_titles(plan)
    sid = decision.get("section_id")
    title = f" 「{titles[sid]}」" if sid in titles else ""
    plan_path = q(args.lesson_plan or (args.progress.parent / "lesson-plan.json"))
    progress_path, store = q(args.progress), q(args.store) if args.store else None
    py = "python3"
    lines = [f"lesson: {progress.get('lesson_id')}  mode: {progress.get('mode', 'full')}  shape: {(plan or {}).get('shape', 'linear')}  "
             f"progress: {decision['done']}/{decision['total']} completed"
             + (f", deferred {', '.join(decision['deferred'])}" if decision["deferred"] else "")
             + (f", to redo later {', '.join(decision['regressed'])}" if decision["regressed"] else ""),
             f"state: {decision['state']}  section: {sid}{title}",
             f"why: {decision['why']}"]
    if decision.get("opener"):
        lines.append(f"opener: new sitting — read {PROTOCOL / decision['opener']} first (variant question from a completed section), then continue below")
        if args.store:
            lines.append(f"  {py} {q(SCRIPT_DIR / 'learner_state_build.py')} build --store {store}")
            lines.append(f"  {py} {q(SCRIPT_DIR / 'cards.py')} due --store {store} --lesson-id {progress.get('lesson_id')}   (due fact cards first, one at a time)")
            lines.append(f"  {py} {q(SCRIPT_DIR / 'review_pool.py')} --store {store} --lesson-id {progress.get('lesson_id')} --progress {progress_path}")
    lines.append(f"read: {(PROTOCOL / decision['read']).resolve()}")
    if decision["state"] == "READY" and decision["read"] == "ready.md":
        lines.append(f"then: {PROTOCOL / 'predict.md'} → {PROTOCOL / 'main.md'} (one state per reply; deepen.md only if the learner asks)")
    if decision["state"] in {"READY", "AWAITING_RETRY"}:
        lines.append(f"section data: {py} {q(SCRIPT_DIR / 'lesson_section.py')} {plan_path} --section {sid}   (not the whole lesson-plan.json)")
        lines.append(f"assess: {PROTOCOL / 'assess.md'}; record: {PROTOCOL / 'record.md'}")
        if args.store:
            lines.append(f"record: {py} {q(SCRIPT_DIR / 'lrg_record.py')} append --store {store} --lesson-id {progress.get('lesson_id')} "
                         f"--section-id {sid} --kind checkpoint --response-file <回答文件> --verdict <mastered|partial|retry|skipped> "
                         f"[--confidence N] [--criteria-met c1,c3] [--depth <层>] --extraction <抽取.json> --progress {progress_path}")
        else:
            lines.append(f"record: {py} {q(SCRIPT_DIR / 'learning_state.py')} record --state {progress_path} --section-id {sid} "
                         f"--response-file <回答文件> --verdict <mastered|partial|retry|skipped> [--confidence N] [--criteria-met c1,c3] [--depth <层>]")
    if decision["state"] == "PROBE":
        lines.append(f"after the round: {py} {q(SCRIPT_DIR / 'learning_state.py')} mark --state {progress_path} --type probe_completed")
    if decision["state"] == "FINISH":
        lines.append(f"final data: {py} {q(SCRIPT_DIR / 'lesson_section.py')} {plan_path} --final")
        if args.store:
            lines.append(f"then: {py} {q(SCRIPT_DIR / 'store_sync.py')} push --store {store}")
    if decision["state"] == "BLOCKED":
        lines.append(f"release: {py} {q(SCRIPT_DIR / 'learning_state.py')} unblock --state {progress_path} --section-id {sid}   (after '{decision['blocked_by']}' finishes)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--progress", type=Path, required=True, help="learning-progress.json of the course")
    parser.add_argument("--lesson-plan", type=Path, help="lesson-plan.json (default: next to the progress file)")
    parser.add_argument("--store", type=Path, help="the knowledge store, when it is on: record commands use lrg_record.py")
    parser.add_argument("--resume", action="store_true", help="Force the new-sitting opener")
    parser.add_argument("--now", help="ISO timestamp (tests)")
    args = parser.parse_args()
    try:
        args.progress = args.progress.resolve()
        progress = load_json(args.progress)
        plan_path = args.lesson_plan or (args.progress.parent / "lesson-plan.json")
        plan = load_json(plan_path) if plan_path.is_file() else None
        now = parse_time(args.now) or datetime.now(timezone.utc)
        decision = decide(progress, plan, now, args.resume)
        print(render(decision, progress, plan, args))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
