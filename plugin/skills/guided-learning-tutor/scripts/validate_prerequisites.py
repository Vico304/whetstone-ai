#!/usr/bin/env python3
"""Validate a guided-learning prerequisite plan and optional supplement guide."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ASSESSMENT_MODES = {"auto", "always", "skip"}
ASSESSMENT_TRIGGERS = {"fragile", "gap", "misconception"}
SOURCE_PRIORITIES = {"official_or_primary", "standards_or_textbooks", "reputable_secondary"}
SUPPORT_TYPES = {"explicit", "entailed", "pedagogical_inference", "external", "unsupported"}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_text(container: dict, key: str, location: str, errors: list[str]) -> None:
    if not nonempty(container.get(key)):
        errors.append(f"{location}.{key} must be a non-empty string")


def require_text_list(
    container: dict,
    key: str,
    location: str,
    errors: list[str],
    *,
    allow_empty: bool = False,
) -> None:
    value = container.get(key)
    if not isinstance(value, list) or (not value and not allow_empty) or not all(nonempty(item) for item in value):
        suffix = " (empty allowed)" if allow_empty else ""
        errors.append(f"{location}.{key} must be a list of non-empty strings{suffix}")


def validate_plan(plan: Any, manifest_paths: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["prerequisite plan root must be an object"]
    if plan.get("schema_version") != "1.0":
        errors.append("schema_version must equal '1.0'")
    for key in ("lesson_id", "scope_statement"):
        require_text(plan, key, "root", errors)
    if plan.get("assessment_mode") not in ASSESSMENT_MODES:
        errors.append(f"root.assessment_mode must be one of {sorted(ASSESSMENT_MODES)}")

    prerequisites = plan.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        errors.append("root.prerequisites must be a non-empty list")
        prerequisites = []

    seen: set[str] = set()
    for index, prerequisite in enumerate(prerequisites):
        location = f"prerequisites[{index}]"
        if not isinstance(prerequisite, dict):
            errors.append(f"{location} must be an object")
            continue
        for key in ("id", "name", "why_needed"):
            require_text(prerequisite, key, location, errors)
        prerequisite_id = prerequisite.get("id")
        if nonempty(prerequisite_id):
            if prerequisite_id in seen:
                errors.append(f"{location}.id duplicates '{prerequisite_id}'")
            seen.add(prerequisite_id)
        require_text_list(prerequisite, "required_for", location, errors)

        refs = prerequisite.get("source_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{location}.source_refs must be a non-empty list")
        else:
            for ref_index, ref in enumerate(refs):
                ref_location = f"{location}.source_refs[{ref_index}]"
                if not isinstance(ref, dict):
                    errors.append(f"{ref_location} must be an object")
                    continue
                for key in ("path", "locator", "note"):
                    require_text(ref, key, ref_location, errors)
                if ref.get("support") not in SUPPORT_TYPES:
                    errors.append(f"{ref_location}.support must be one of {sorted(SUPPORT_TYPES)}")
                if manifest_paths is not None and nonempty(ref.get("path")) and ref["path"] not in manifest_paths:
                    errors.append(f"{ref_location}.path '{ref['path']}' is absent from the source manifest")

        diagnostic = prerequisite.get("diagnostic")
        if not isinstance(diagnostic, dict):
            errors.append(f"{location}.diagnostic must be an object")
        else:
            for key in ("prompt", "follow_up_prompt", "bridge_prompt"):
                require_text(diagnostic, key, f"{location}.diagnostic", errors)
            require_text_list(diagnostic, "criteria", f"{location}.diagnostic", errors)

    policy = plan.get("research_policy")
    if not isinstance(policy, dict):
        errors.append("root.research_policy must be an object")
    else:
        trigger = policy.get("trigger")
        if not isinstance(trigger, list) or not trigger or not all(item in ASSESSMENT_TRIGGERS for item in trigger):
            errors.append(f"research_policy.trigger must use values from {sorted(ASSESSMENT_TRIGGERS)}")
        priority = policy.get("source_priority")
        if not isinstance(priority, list) or not priority or not all(item in SOURCE_PRIORITIES for item in priority):
            errors.append(f"research_policy.source_priority must use values from {sorted(SOURCE_PRIORITIES)}")
        if policy.get("separate_external_claims") is not True:
            errors.append("research_policy.separate_external_claims must be true")

    uncertainties = plan.get("uncertainties")
    if not isinstance(uncertainties, list) or not all(nonempty(item) for item in uncertainties):
        errors.append("root.uncertainties must be a list of non-empty strings")
    return errors


def manifest_paths(manifest: Any) -> set[str]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("source manifest must contain a files list")
    return {
        item["path"]
        for item in manifest["files"]
        if isinstance(item, dict) and nonempty(item.get("path"))
    }


def validate_guide(guide: str) -> list[str]:
    errors: list[str] = []
    if "前置知识" not in guide and "Prerequisite" not in guide:
        errors.append("prerequisite guide must identify itself as a prerequisite supplement")
    if "轮到你" not in guide and "Your turn" not in guide and "Checkpoint" not in guide:
        errors.append("prerequisite guide must visibly include a learner reconstruction checkpoint")
    if "https://" not in guide and "http://" not in guide:
        errors.append("prerequisite guide must include at least one external source URL")
    return errors


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prerequisite_plan", type=Path)
    parser.add_argument("--guide", type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.prerequisite_plan)
        paths = manifest_paths(load_json(args.manifest)) if args.manifest else None
        errors = validate_plan(plan, paths)
        if args.guide:
            errors.extend(validate_guide(args.guide.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {args.prerequisite_plan} is a valid prerequisite plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

