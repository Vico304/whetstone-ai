#!/usr/bin/env python3
"""Validate a guided-learning lesson plan and its human-readable guide."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SUPPORT_TYPES = {"explicit", "entailed", "pedagogical_inference", "external", "unsupported"}

MAX_CONCEPTS_PER_SECTION = 4
MAX_SECTIONS_PER_LESSON = 9


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_text(container: dict, key: str, location: str, errors: list[str]) -> None:
    if not nonempty(container.get(key)):
        errors.append(f"{location}.{key} must be a non-empty string")


def require_text_list(container: dict, key: str, location: str, errors: list[str], allow_empty: bool = False) -> None:
    value = container.get(key)
    if not isinstance(value, list) or (not value and not allow_empty) or not all(nonempty(item) for item in value):
        suffix = " (empty allowed)" if allow_empty else ""
        errors.append(f"{location}.{key} must be a list of non-empty strings{suffix}")


def validate_plan(plan: Any, manifest_paths: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["lesson plan root must be an object"]
    if plan.get("schema_version") != "1.0":
        errors.append("schema_version must equal '1.0'")
    for key in ("lesson_id", "title", "learning_goal"):
        require_text(plan, key, "root", errors)

    big_picture = plan.get("big_picture")
    if not isinstance(big_picture, dict):
        errors.append("root.big_picture must be an object")
    else:
        require_text(big_picture, "problem", "big_picture", errors)
        require_text(big_picture, "outcome", "big_picture", errors)
        require_text_list(big_picture, "system_map", "big_picture", errors)

    sections = plan.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("root.sections must be a non-empty list")
        sections = []

    seen: set[str] = set()
    for index, section in enumerate(sections):
        location = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{location} must be an object")
            continue
        for key in ("id", "title", "problem", "solution", "mechanism", "meaning"):
            require_text(section, key, location, errors)
        section_id = section.get("id")
        if nonempty(section_id):
            if section_id in seen:
                errors.append(f"{location}.id duplicates '{section_id}'")

        depends_on = section.get("depends_on")
        if not isinstance(depends_on, list) or not all(nonempty(item) for item in depends_on):
            errors.append(f"{location}.depends_on must be a list of section ids")
        else:
            for dependency in depends_on:
                if dependency not in seen:
                    errors.append(f"{location}.depends_on references '{dependency}' before it is available")
        if nonempty(section_id):
            seen.add(section_id)

        require_text_list(section, "tradeoffs", location, errors, allow_empty=True)
        new_problem = section.get("new_problem")
        if index < len(sections) - 1 and not nonempty(new_problem):
            errors.append(f"{location}.new_problem must lead into the next section")
        elif index == len(sections) - 1 and new_problem is not None and not nonempty(new_problem):
            errors.append(f"{location}.new_problem must be null or a non-empty string")

        concepts = section.get("concepts")
        if not isinstance(concepts, list) or not concepts:
            errors.append(f"{location}.concepts must be a non-empty list")
        else:
            for concept_index, concept in enumerate(concepts):
                concept_location = f"{location}.concepts[{concept_index}]"
                if not isinstance(concept, dict):
                    errors.append(f"{concept_location} must be an object")
                    continue
                require_text(concept, "name", concept_location, errors)
                require_text(concept, "explanation", concept_location, errors)

        refs = section.get("source_refs")
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

        checkpoint = section.get("checkpoint")
        if not isinstance(checkpoint, dict):
            errors.append(f"{location}.checkpoint must be an object")
        else:
            require_text(checkpoint, "prompt", f"{location}.checkpoint", errors)
            require_text(checkpoint, "hint", f"{location}.checkpoint", errors)
            require_text_list(checkpoint, "criteria", f"{location}.checkpoint", errors)

    final_challenge = plan.get("final_challenge")
    if not isinstance(final_challenge, dict):
        errors.append("root.final_challenge must be an object")
    else:
        require_text(final_challenge, "prompt", "final_challenge", errors)
        require_text_list(final_challenge, "criteria", "final_challenge", errors)

    uncertainties = plan.get("uncertainties")
    if not isinstance(uncertainties, list) or not all(nonempty(item) for item in uncertainties):
        errors.append("root.uncertainties must be a list of non-empty strings")
    return errors


def collect_warnings(plan: Any) -> list[str]:
    """Cognitive-load advisories that do not fail validation."""
    warnings: list[str] = []
    if not isinstance(plan, dict):
        return warnings
    sections = plan.get("sections")
    if not isinstance(sections, list):
        return warnings
    if len(sections) > MAX_SECTIONS_PER_LESSON:
        warnings.append(
            f"lesson has {len(sections)} sections (> {MAX_SECTIONS_PER_LESSON}); "
            "consider a skeleton pass with on-demand expansion"
        )
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        concepts = section.get("concepts")
        if isinstance(concepts, list) and len(concepts) > MAX_CONCEPTS_PER_SECTION:
            warnings.append(
                f"sections[{index}] introduces {len(concepts)} concepts "
                f"(> {MAX_CONCEPTS_PER_SECTION}); consider splitting the section"
            )
    return warnings


def manifest_paths(manifest: Any) -> set[str]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("source manifest must contain a files list")
    return {
        item["path"]
        for item in manifest["files"]
        if isinstance(item, dict) and nonempty(item.get("path"))
    }


def validate_guide(guide: str, plan: dict) -> list[str]:
    errors: list[str] = []
    for field in (plan.get("title"), *(section.get("title") for section in plan.get("sections", []) if isinstance(section, dict))):
        if nonempty(field) and field not in guide:
            errors.append(f"teaching guide does not contain title '{field}'")
    if "轮到你" not in guide and "Your turn" not in guide and "Checkpoint" not in guide:
        errors.append("teaching guide must visibly include at least one learner checkpoint")
    for index, section in enumerate(plan.get("sections", [])):
        if not isinstance(section, dict):
            continue
        checkpoint = section.get("checkpoint")
        if not isinstance(checkpoint, dict):
            continue
        criteria = checkpoint.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if nonempty(criterion) and criterion in guide:
                errors.append(
                    f"teaching guide leaks assessment criterion from sections[{index}]: '{criterion}'"
                )
    return errors


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lesson_plan", type=Path)
    parser.add_argument("--guide", type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.lesson_plan)
        paths = manifest_paths(load_json(args.manifest)) if args.manifest else None
        errors = validate_plan(plan, paths)
        warnings = collect_warnings(plan)
        if args.guide:
            errors.extend(validate_guide(args.guide.read_text(encoding="utf-8"), plan))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {args.lesson_plan} is a valid guided-learning lesson plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
