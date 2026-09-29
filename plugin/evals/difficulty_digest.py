#!/usr/bin/env python3
"""Digest what each section of a lesson-plan.json asks the learner to rebuild, so a change to the
course (added prerequisite material, a regenerated outline) can be checked for lowering that bar.

Per section: criteria count, criteria layer counts, core concept ids, a digest of the checkpoint
prompt and one digest per criterion text; the same for a skeleton course's probe and for each
supporting concept's check. The final challenge gets the same treatment.

With --against BASELINE (an earlier digest), every reduction is listed and the exit code is 1:
a section or check that disappeared, fewer criteria, fewer criteria in any layer, a core concept
that is gone, a changed prompt, or a criterion text that no longer occurs. Additions are listed
but allowed. Exit 2 when a file cannot be read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def criteria_items(block) -> list[tuple[str, str]]:
    """(text, layer) per criterion; plain-string criteria (schema 1.0, final_challenge) have layer 'unset'."""
    if not isinstance(block, dict) or not isinstance(block.get("criteria"), list):
        return []
    items = []
    for criterion in block["criteria"]:
        if isinstance(criterion, str):
            items.append((criterion, "unset"))
        elif isinstance(criterion, dict) and isinstance(criterion.get("text"), str):
            layer = criterion.get("layer")
            items.append((criterion["text"], layer if isinstance(layer, str) else "unset"))
    return items


def block_digest(block) -> dict:
    items = criteria_items(block)
    prompt = block.get("prompt") if isinstance(block, dict) else None
    return {
        "n_criteria": len(items),
        "layers": dict(sorted(Counter(layer for _, layer in items).items())),
        "prompt_sha": text_digest(prompt) if isinstance(prompt, str) else None,
        "criteria_sha": [text_digest(text) for text, _ in items],
    }


def digest(plan: dict) -> dict:
    sections = {}
    for section in plan.get("sections") or []:
        if not isinstance(section, dict) or not isinstance(section.get("id"), str):
            continue
        concepts = [c for c in (section.get("concepts") or []) if isinstance(c, dict)]
        entry = block_digest(section.get("checkpoint"))
        entry["core_ids"] = sorted(c["id"] for c in concepts
                                   if isinstance(c.get("id"), str) and c.get("role", "core") == "core")
        if isinstance(section.get("probe"), dict):
            entry["probe"] = block_digest(section["probe"])
        checks = {c["id"]: block_digest(c["check"]) for c in concepts
                  if isinstance(c.get("id"), str) and isinstance(c.get("check"), dict)}
        if checks:
            entry["checks"] = checks
        sections[section["id"]] = entry
    final = plan.get("final_challenge")
    return {"lesson_id": plan.get("lesson_id"), "sections": sections,
            "final": block_digest(final) if isinstance(final, dict) else None}


def compare_block(where: str, old: dict, new: dict | None, reductions: list[str], additions: list[str]) -> None:
    if new is None:
        reductions.append(f"{where}: removed")
        return
    if new["n_criteria"] < old["n_criteria"]:
        reductions.append(f"{where}: criteria {old['n_criteria']} → {new['n_criteria']}")
    elif new["n_criteria"] > old["n_criteria"]:
        additions.append(f"{where}: criteria {old['n_criteria']} → {new['n_criteria']}")
    for layer, count in old["layers"].items():
        if new["layers"].get(layer, 0) < count:
            reductions.append(f"{where}: {layer} criteria {count} → {new['layers'].get(layer, 0)}")
    if old["prompt_sha"] != new["prompt_sha"]:
        reductions.append(f"{where}: prompt changed")
    missing = [i + 1 for i, sha in enumerate(old["criteria_sha"]) if sha not in new["criteria_sha"]]
    if missing:
        reductions.append(f"{where}: criterion text changed or removed (#{', #'.join(map(str, missing))})")


def compare(old: dict, new: dict) -> tuple[list[str], list[str]]:
    """Reductions (not allowed) and additions (allowed, listed for review) from old to new."""
    reductions: list[str] = []
    additions: list[str] = []
    for sid, before in old["sections"].items():
        after = new["sections"].get(sid)
        compare_block(sid, before, after, reductions, additions)
        if after is None:
            continue
        gone = sorted(set(before["core_ids"]) - set(after["core_ids"]))
        if gone:
            reductions.append(f"{sid}: core concepts removed: {', '.join(gone)}")
        if "probe" in before:
            compare_block(f"{sid}.probe", before["probe"], after.get("probe"), reductions, additions)
        for cid, check in (before.get("checks") or {}).items():
            compare_block(f"{sid}.check[{cid}]", check, (after.get("checks") or {}).get(cid), reductions, additions)
    for sid in new["sections"]:
        if sid not in old["sections"]:
            additions.append(f"{sid}: new section")
    if old.get("final") is not None:
        compare_block("final_challenge", old["final"], new.get("final"), reductions, additions)
    return reductions, additions


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("plan", type=Path, help="lesson-plan.json")
    parser.add_argument("--against", type=Path, help="Earlier digest JSON; list reductions and exit 1 if any")
    parser.add_argument("--output", type=Path, help="Write the digest JSON here")
    args = parser.parse_args()
    try:
        current = digest(read_json(args.plan))
        baseline = read_json(args.against) if args.against else None
        if baseline is not None and not isinstance(baseline.get("sections"), dict):
            raise ValueError(f"{args.against} is not a difficulty digest (no sections object)")
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if baseline is None:
        if not args.output:
            print(json.dumps(current, ensure_ascii=False, indent=2))
        return 0
    reductions, additions = compare(baseline, current)
    for line in reductions:
        print(f"REDUCED {line}")
    for line in additions:
        print(f"ADDED {line}")
    print(f"{len(reductions)} reductions, {len(additions)} additions")
    return 1 if reductions else 0


if __name__ == "__main__":
    raise SystemExit(main())
