#!/usr/bin/env python3
"""Validate a guided-learning lesson plan and its human-readable guide."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SUPPORT_TYPES = {"explicit", "entailed", "pedagogical_inference", "external", "unsupported"}
SCHEMA_VERSIONS = {"1.0", "1.1", "1.2", "1.3"}
ROLE_AWARE_VERSIONS = {"1.2", "1.3"}  # course-planning (spec C) fields
SHAPES = {"linear", "skeleton", "branch"}
ANCHOR_MARKERS = {"external", "no-anchor"}
BRANCH_STATUSES = {"candidate", "chosen", "declined"}
MODES = {"full", "fast"}
ROLES = ("core", "supporting", "listed")
DISPOSITIONS = {"core", "supporting", "listed", "appendix", "deferred", "excluded", "pool", "reserve"}
FILE_LEVEL_DISPOSITIONS = {"pool", "reserve", "excluded"}  # may use heading "*" (skeleton courses)
MAX_SUPPORTING_PER_SECTION = 6
MAX_LISTED_EXPLANATION_CHARS = 200
HEADING_MD = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$", re.MULTILINE)
HEADING_ADOC = re.compile(r"^(={1,2})\s+(.+?)\s*$", re.MULTILINE)
LAYERS = ("fact", "mechanism", "rationale", "principle")
PUBLIC_LAYERS = {"fact", "mechanism"}
RELATION_TYPES = {
    "is_a", "part_of", "depends_on", "causes", "enables",
    "implements", "contrasts_with", "instance_of", "prerequisite_for",
}
CONCEPT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")
MAX_DOMAIN_DEPTH = 4

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


def schema_version(plan: dict) -> str:
    version = plan.get("schema_version")
    return version if version in SCHEMA_VERSIONS else "1.0"


def plan_shape(plan: dict) -> str:
    """1.3 course shape; older plans and plans without the field are linear."""
    shape = plan.get("shape") if isinstance(plan, dict) else None
    return shape if shape in SHAPES else "linear"


def under_path(path: str, roots: set[str]) -> bool:
    """True when `path` equals one of `roots` or lies below a root directory."""
    path = path.strip("/")
    for root in roots:
        root = root.strip("/")
        if root in {"", "."} or path == root or path.startswith(root + "/"):
            return True
    return False


def wholesale_paths(plan: dict) -> set[str]:
    """Coverage rows with heading "*" cover the whole file or directory."""
    return {
        item["path"] for item in (plan.get("coverage") or []) if isinstance(plan.get("coverage"), list)
        if isinstance(item, dict) and nonempty(item.get("path")) and item.get("heading") == "*"
    }


def pool_paths(plan: dict) -> set[str]:
    return {
        item["path"] for item in (plan.get("coverage") or []) if isinstance(plan.get("coverage"), list)
        if isinstance(item, dict) and nonempty(item.get("path")) and item.get("disposition") == "pool"
    }


def validate_source_refs(refs: Any, location: str, errors: list[str], manifest_paths: set[str] | None) -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(f"{location}.source_refs must be a non-empty list")
        return
    for ref_index, ref in enumerate(refs):
        ref_location = f"{location}.source_refs[{ref_index}]"
        if not isinstance(ref, dict):
            errors.append(f"{ref_location} must be an object")
            continue
        for key in ("path", "locator", "note"):
            require_text(ref, key, ref_location, errors)
        if ref.get("support") not in SUPPORT_TYPES:
            errors.append(f"{ref_location}.support must be one of {sorted(SUPPORT_TYPES)}")
        path = ref.get("path")
        if is_url(path) and ref.get("support") != "external":
            errors.append(f"{ref_location}: a URL path must carry support 'external'")
        if manifest_paths is not None and nonempty(path) and not is_url(path) and path not in manifest_paths:
            errors.append(f"{ref_location}.path '{path}' is absent from the source manifest")


def is_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def validate_concept_v11(concept: dict, location: str, errors: list[str], names_by_id: dict[str, str]) -> None:
    concept_id = concept.get("id")
    if not nonempty(concept_id) or not CONCEPT_ID.match(concept_id):
        errors.append(f"{location}.id must match '<domain>.<concept>' in lowercase ascii, e.g. 'cs.tee.enclave'")
    elif concept_id in names_by_id and names_by_id[concept_id] != concept.get("name"):
        errors.append(f"{location}.id '{concept_id}' is reused with a different name ('{names_by_id[concept_id]}')")
    elif nonempty(concept.get("name")):
        names_by_id[concept_id] = concept["name"]
    if concept.get("layer") not in LAYERS:
        errors.append(f"{location}.layer must be one of {list(LAYERS)}")
    path = concept.get("domain_path")
    if not isinstance(path, list) or not path or len(path) > MAX_DOMAIN_DEPTH or not all(nonempty(item) for item in path):
        errors.append(f"{location}.domain_path must be 1-{MAX_DOMAIN_DEPTH} non-empty strings")
    aliases = concept.get("aliases", [])
    if not isinstance(aliases, list) or not all(nonempty(item) for item in aliases):
        errors.append(f"{location}.aliases must be a list of non-empty strings when present")


def validate_concept_v12(concept: dict, location: str, errors: list[str]) -> None:
    if concept.get("role") not in ROLES:
        errors.append(f"{location}.role must be one of {list(ROLES)}")
    check = concept.get("check")
    if check is not None:
        if concept.get("role") != "supporting":
            errors.append(f"{location}.check is only allowed on supporting concepts")
        if not isinstance(check, dict):
            errors.append(f"{location}.check must be an object")
        else:
            require_text(check, "prompt", f"{location}.check", errors)
            require_text(check, "hint", f"{location}.check", errors)
            validate_criteria(check, f"{location}.check", errors, "1.2")


def validate_deferred(plan: dict, section_ids: set[str], concept_ids: set[str], errors: list[str]) -> set[str]:
    """Returns the set of deferred section ids."""
    deferred_sections: set[str] = set()
    items = plan.get("deferred", [])
    if not isinstance(items, list):
        errors.append("root.deferred must be a list")
        return deferred_sections
    for index, item in enumerate(items):
        location = f"deferred[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(item, "reason", location, errors)
        kind, ident = item.get("type"), item.get("id")
        if kind == "section":
            if ident not in section_ids:
                errors.append(f"{location}.id '{ident}' is not a section id")
            else:
                deferred_sections.add(ident)
        elif kind == "concept":
            if ident not in concept_ids:
                errors.append(f"{location}.id '{ident}' is not a concept id in this lesson")
        else:
            errors.append(f"{location}.type must be 'section' or 'concept'")
    return deferred_sections


def validate_coverage(plan: dict, section_ids: set[str], errors: list[str], allow_empty: bool) -> None:
    shape = plan_shape(plan)
    coverage = plan.get("coverage")
    if not isinstance(coverage, list):
        errors.append("root.coverage must be a list (schema 1.2)")
        return
    if not coverage and not allow_empty:
        errors.append("root.coverage is empty; every source heading needs a disposition (or pass --allow-empty-coverage)")
    for index, item in enumerate(coverage):
        location = f"coverage[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(item, "path", location, errors)
        require_text(item, "heading", location, errors)
        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{location}.disposition must be one of {sorted(DISPOSITIONS)}")
            continue
        if disposition in {"pool", "reserve"} and shape != "skeleton":
            errors.append(f"{location}.disposition '{disposition}' is only allowed in skeleton courses (schema 1.3, shape = skeleton)")
        if item.get("heading") == "*" and disposition not in FILE_LEVEL_DISPOSITIONS:
            errors.append(f"{location}.heading '*' (whole file) is only allowed for {sorted(FILE_LEVEL_DISPOSITIONS)}")
        if disposition in {"core", "supporting", "listed", "appendix"} and item.get("section_id") not in section_ids:
            errors.append(f"{location}.section_id must name a section for disposition '{disposition}'")
        if disposition in {"deferred", "excluded"} and not nonempty(item.get("reason")):
            errors.append(f"{location}.reason is required for disposition '{disposition}'")


def source_headings(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    pattern = HEADING_ADOC if path.suffix.lower() in {".adoc", ".asciidoc"} else HEADING_MD
    return [m.group(2).strip() for m in pattern.finditer(text)]


def validate_coverage_against_sources(plan: dict, sources_root: Path) -> list[str]:
    """Every level-1/2 heading of every text source referenced by the plan must appear in coverage[]."""
    errors: list[str] = []
    coverage = plan.get("coverage") if isinstance(plan.get("coverage"), list) else []
    covered = {(item.get("path"), normalize_text(str(item.get("heading", "")))) for item in coverage if isinstance(item, dict)}
    paths: set[str] = {item["path"] for item in coverage if isinstance(item, dict) and nonempty(item.get("path"))}
    for section in plan.get("sections", []) or []:
        for ref in (section.get("source_refs") or []) if isinstance(section, dict) else []:
            if isinstance(ref, dict) and nonempty(ref.get("path")):
                paths.add(ref["path"])
    wholesale = wholesale_paths(plan)
    for rel in sorted(paths):
        if under_path(rel, wholesale):
            continue  # whole file/directory has a disposition (pool / reserve / excluded)
        path = sources_root / rel
        if not path.is_file() or path.suffix.lower() not in {".md", ".markdown", ".adoc", ".asciidoc", ".txt"}:
            continue
        for heading in source_headings(path):
            if (rel, normalize_text(heading)) not in covered:
                errors.append(f"coverage is missing heading '{heading}' of {rel}")
    return errors


def validate_anchor(concept: dict, location: str, pools: set[str], errors: list[str]) -> None:
    anchor = concept.get("anchor")
    if anchor is None:
        errors.append(f"{location}.anchor is required for core/supporting concepts of a skeleton course "
                      "({path, locator} in the evidence pool, or \"external\" / \"no-anchor\")")
        return
    if isinstance(anchor, str):
        if anchor not in ANCHOR_MARKERS:
            errors.append(f"{location}.anchor must be an object or one of {sorted(ANCHOR_MARKERS)}")
        return
    if not isinstance(anchor, dict):
        errors.append(f"{location}.anchor must be an object or one of {sorted(ANCHOR_MARKERS)}")
        return
    require_text(anchor, "path", f"{location}.anchor", errors)
    require_text(anchor, "locator", f"{location}.anchor", errors)
    if nonempty(anchor.get("path")) and not is_url(anchor["path"]) and not under_path(anchor["path"], pools):
        errors.append(f"{location}.anchor.path '{anchor['path']}' is not under any coverage row with disposition 'pool'")


def validate_branch_candidates(plan: dict, concept_ids: set[str], errors: list[str]) -> None:
    items = plan.get("branch_candidates")
    if not isinstance(items, list) or not items:
        errors.append("root.branch_candidates must be a non-empty list in a skeleton course")
        return
    material_roots = {
        item["path"] for item in (plan.get("coverage") or [])
        if isinstance(item, dict) and nonempty(item.get("path")) and item.get("disposition") in {"pool", "reserve"}
    }
    seen: set[str] = set()
    for index, item in enumerate(items):
        location = f"branch_candidates[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(item, "id", location, errors)
        require_text(item, "title", location, errors)
        if nonempty(item.get("id")):
            if item["id"] in seen:
                errors.append(f"{location}.id duplicates '{item['id']}'")
            seen.add(item["id"])
        ids = item.get("concept_ids")
        if not isinstance(ids, list) or not ids or not all(nonempty(c) for c in ids):
            errors.append(f"{location}.concept_ids must be a non-empty list of concept ids")
        else:
            for cid in ids:
                if cid not in concept_ids:
                    errors.append(f"{location}.concept_ids references unknown concept '{cid}'")
        materials = item.get("materials")
        if not isinstance(materials, list) or not all(nonempty(m) for m in materials):
            errors.append(f"{location}.materials must be a list of paths (empty allowed for no-anchor candidates)")
        else:
            for material in materials:
                if not under_path(material, material_roots):
                    errors.append(f"{location}.materials '{material}' is not under any 'pool' or 'reserve' coverage row")
        if item.get("status") not in BRANCH_STATUSES:
            errors.append(f"{location}.status must be one of {sorted(BRANCH_STATUSES)}")
        if "work_relevance" in item and not nonempty(item.get("work_relevance")):
            errors.append(f"{location}.work_relevance must be a non-empty string when present")


def validate_v13(plan: dict, concept_ids: set[str], errors: list[str]) -> None:
    """Schema 1.3: shape, parent_course, per-section probes, concept anchors, branch candidates."""
    shape = plan.get("shape", "linear")
    if shape not in SHAPES:
        errors.append(f"root.shape must be one of {sorted(SHAPES)} (schema 1.3)")
        shape = "linear"
    parent = plan.get("parent_course")
    if shape == "branch" and not nonempty(parent):
        errors.append("root.parent_course must name the skeleton course when shape = branch")
    if shape != "branch" and parent is not None:
        errors.append("root.parent_course is only allowed when shape = branch")
    pools = pool_paths(plan)
    for index, section in enumerate(plan.get("sections") or []):
        if not isinstance(section, dict):
            continue
        location = f"sections[{index}]"
        probe = section.get("probe")
        if shape == "skeleton":
            if not isinstance(probe, dict):
                errors.append(f"{location}.probe is required in a skeleton course (principle-level, no-hint question)")
            else:
                require_text(probe, "prompt", f"{location}.probe", errors)
                validate_criteria(probe, f"{location}.probe", errors, "1.3")
                if "hint" in probe and not nonempty(probe.get("hint")):
                    errors.append(f"{location}.probe.hint must be a non-empty string when present")
        elif probe is not None:
            errors.append(f"{location}.probe is only allowed in skeleton courses")
        for c_index, concept in enumerate(section.get("concepts") or []):
            if not isinstance(concept, dict):
                continue
            c_location = f"{location}.concepts[{c_index}]"
            if shape == "skeleton" and concept.get("role") in {"core", "supporting"}:
                validate_anchor(concept, c_location, pools, errors)
            elif "anchor" in concept and shape != "skeleton":
                errors.append(f"{c_location}.anchor is only allowed in skeleton courses")
    if shape == "skeleton":
        validate_branch_candidates(plan, concept_ids, errors)
    elif "branch_candidates" in plan:
        errors.append("root.branch_candidates is only allowed in skeleton courses")


def grounding(plan: dict) -> dict:
    """Anchored / external / no-anchor counts over core+supporting concepts (skeleton courses)."""
    counts = {"anchored": 0, "external": 0, "no_anchor": 0, "total": 0}
    seen: set[str] = set()
    for section in plan.get("sections") or []:
        for concept in (section.get("concepts") or []) if isinstance(section, dict) else []:
            if not isinstance(concept, dict) or concept.get("role") not in {"core", "supporting"}:
                continue
            key = concept.get("id") or concept.get("name")
            if key in seen:
                continue
            seen.add(key)
            counts["total"] += 1
            anchor = concept.get("anchor")
            if isinstance(anchor, dict):
                counts["anchored"] += 1
            elif anchor == "external":
                counts["external"] += 1
            else:
                counts["no_anchor"] += 1
    return counts


def validate_criteria(checkpoint: dict, location: str, errors: list[str], version: str) -> None:
    criteria = checkpoint.get("criteria")
    if version == "1.0":
        require_text_list(checkpoint, "criteria", location, errors)
        return
    if not isinstance(criteria, list) or not criteria:
        errors.append(f"{location}.criteria must be a non-empty list of objects")
        return
    seen: set[str] = set()
    for index, criterion in enumerate(criteria):
        c_location = f"{location}.criteria[{index}]"
        if not isinstance(criterion, dict):
            errors.append(f"{c_location} must be an object with id, text and layer")
            continue
        require_text(criterion, "id", c_location, errors)
        require_text(criterion, "text", c_location, errors)
        if criterion.get("layer") not in LAYERS:
            errors.append(f"{c_location}.layer must be one of {list(LAYERS)}")
        if nonempty(criterion.get("id")):
            if criterion["id"] in seen:
                errors.append(f"{c_location}.id duplicates '{criterion['id']}'")
            seen.add(criterion["id"])


def validate_relations(plan: dict, concept_ids: set[str], errors: list[str], manifest_paths: set[str] | None) -> None:
    relations = plan.get("relations", [])
    if not isinstance(relations, list):
        errors.append("root.relations must be a list")
        return
    seen: set[str] = set()
    for index, relation in enumerate(relations):
        location = f"relations[{index}]"
        if not isinstance(relation, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(relation, "id", location, errors)
        if nonempty(relation.get("id")):
            if relation["id"] in seen:
                errors.append(f"{location}.id duplicates '{relation['id']}'")
            seen.add(relation["id"])
        for end in ("from", "to"):
            if relation.get(end) not in concept_ids:
                errors.append(f"{location}.{end} '{relation.get(end)}' is not a concept id in this lesson")
        if relation.get("from") == relation.get("to") and relation.get("from") is not None:
            errors.append(f"{location} must not connect a concept to itself")
        if relation.get("type") not in RELATION_TYPES:
            errors.append(f"{location}.type must be one of {sorted(RELATION_TYPES)}")
        if relation.get("layer") not in LAYERS:
            errors.append(f"{location}.layer must be one of {list(LAYERS)}")
        if "rationale" in relation and not nonempty(relation.get("rationale")):
            errors.append(f"{location}.rationale must be a non-empty string when present")
        validate_source_refs(relation.get("source_refs"), location, errors, manifest_paths)


def criteria_texts(checkpoint: Any) -> list[str]:
    """Criterion texts for either schema version (strings in 1.0, objects in 1.1)."""
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("criteria"), list):
        return []
    texts: list[str] = []
    for criterion in checkpoint["criteria"]:
        if isinstance(criterion, str):
            texts.append(criterion)
        elif isinstance(criterion, dict) and isinstance(criterion.get("text"), str):
            texts.append(criterion["text"])
    return texts


def validate_plan(plan: Any, manifest_paths: set[str] | None = None, allow_empty_coverage: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["lesson plan root must be an object"]
    if plan.get("schema_version") not in SCHEMA_VERSIONS:
        errors.append(f"schema_version must be one of {sorted(SCHEMA_VERSIONS)}")
    version = schema_version(plan)
    names_by_id: dict[str, str] = {}
    if version in ROLE_AWARE_VERSIONS:
        if plan.get("mode") not in MODES:
            errors.append(f"root.mode must be one of {sorted(MODES)} (schema 1.2)")
        if "outline_confirmed_at" not in plan:
            errors.append("root.outline_confirmed_at must be present (null until the learner confirms the outline)")
        elif plan["outline_confirmed_at"] is not None and not nonempty(plan["outline_confirmed_at"]):
            errors.append("root.outline_confirmed_at must be null or an ISO timestamp")
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
                if version != "1.0":
                    validate_concept_v11(concept, concept_location, errors, names_by_id)
                if version in ROLE_AWARE_VERSIONS:
                    validate_concept_v12(concept, concept_location, errors)

        if "principle" in section and not nonempty(section.get("principle")):
            errors.append(f"{location}.principle must be a non-empty string when present")

        validate_source_refs(section.get("source_refs"), location, errors, manifest_paths)

        checkpoint = section.get("checkpoint")
        if not isinstance(checkpoint, dict):
            errors.append(f"{location}.checkpoint must be an object")
        else:
            require_text(checkpoint, "prompt", f"{location}.checkpoint", errors)
            require_text(checkpoint, "hint", f"{location}.checkpoint", errors)
            validate_criteria(checkpoint, f"{location}.checkpoint", errors, version)

    if version != "1.0":
        validate_relations(plan, set(names_by_id), errors, manifest_paths)
    elif "relations" in plan:
        errors.append("root.relations requires schema_version '1.1'")
    if version in ROLE_AWARE_VERSIONS:
        validate_deferred(plan, seen, set(names_by_id), errors)
        validate_coverage(plan, seen, errors, allow_empty_coverage)
    else:
        for key in ("mode", "coverage", "deferred"):
            if key in plan:
                errors.append(f"root.{key} requires schema_version '1.2'")
    if version == "1.3":
        validate_v13(plan, set(names_by_id), errors)
    else:
        for key in ("shape", "parent_course", "branch_candidates"):
            if key in plan:
                errors.append(f"root.{key} requires schema_version '1.3'")

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
    if len(sections) > MAX_SECTIONS_PER_LESSON and plan_shape(plan) != "skeleton":
        warnings.append(
            f"lesson has {len(sections)} sections (> {MAX_SECTIONS_PER_LESSON}); "
            "consider a skeleton pass with on-demand expansion"
        )
    role_aware = schema_version(plan) in ROLE_AWARE_VERSIONS
    skeleton = plan_shape(plan) == "skeleton"
    confirmed = plan.get("outline_confirmed_at")
    if role_aware and isinstance(confirmed, str) and re.search(r"T00:00(:00)?(\.0+)?(Z|[+-]\d\d:\d\d)?$", confirmed):
        warnings.append("outline_confirmed_at looks like a placeholder (midnight); record the real time, e.g. `date -u +%FT%TZ`")
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        concepts = section.get("concepts")
        if not isinstance(concepts, list):
            continue
        if not role_aware:
            if len(concepts) > MAX_CONCEPTS_PER_SECTION:
                warnings.append(
                    f"sections[{index}] introduces {len(concepts)} concepts "
                    f"(> {MAX_CONCEPTS_PER_SECTION}); consider splitting the section"
                )
            continue
        core = [c for c in concepts if isinstance(c, dict) and c.get("role") == "core"]
        supporting = [c for c in concepts if isinstance(c, dict) and c.get("role") == "supporting"]
        if len(core) > MAX_CONCEPTS_PER_SECTION:
            warnings.append(
                f"sections[{index}] has {len(core)} core concepts (> {MAX_CONCEPTS_PER_SECTION}); "
                "demote some to supporting or split the section — do not drop them"
            )
        if len(supporting) > MAX_SUPPORTING_PER_SECTION:
            warnings.append(f"sections[{index}] has {len(supporting)} supporting concepts (> {MAX_SUPPORTING_PER_SECTION})")
        for c_index, concept in enumerate(concepts):
            if isinstance(concept, dict) and concept.get("role") == "supporting" and not isinstance(concept.get("check"), dict):
                warnings.append(f"sections[{index}].concepts[{c_index}] is 'supporting' but has no check question; the learner cannot ask to verify it")
            if skeleton and isinstance(concept, dict) and concept.get("anchor") == "no-anchor":
                warnings.append(f"sections[{index}].concepts[{c_index}] has no anchor in the learner's materials; the learner decides whether to keep it as general background or drop it")
            if isinstance(concept, dict) and concept.get("role") == "listed" and len(str(concept.get("explanation", ""))) > MAX_LISTED_EXPLANATION_CHARS:
                warnings.append(
                    f"sections[{index}].concepts[{c_index}] is 'listed' but its explanation is long "
                    f"(> {MAX_LISTED_EXPLANATION_CHARS} chars); listed concepts get a one-line fact-layer definition only"
                )
    return warnings


def deferred_section_ids(plan: dict) -> set[str]:
    return {item["id"] for item in (plan.get("deferred") or []) if isinstance(item, dict) and item.get("type") == "section"}


def hidden_texts(section: dict) -> list[tuple[str, str]]:
    """(label, text) pairs that must never appear in learner-facing documents of a 1.2 pack."""
    pairs: list[tuple[str, str]] = []
    for criterion in criteria_texts(section.get("checkpoint")):
        pairs.append(("assessment criterion", criterion))
    for criterion in criteria_texts(section.get("probe")):
        pairs.append(("probe criterion", criterion))
    for concept in section.get("concepts") or []:
        if isinstance(concept, dict):
            for criterion in criteria_texts(concept.get("check")):
                pairs.append(("supporting check criterion", criterion))
    if nonempty(section.get("principle")):
        pairs.append(("principle-layer content", section["principle"]))
    if nonempty(section.get("meaning")):
        pairs.append(("rationale-layer meaning", section["meaning"]))
    for tradeoff in section.get("tradeoffs") or []:
        if nonempty(tradeoff):
            pairs.append(("rationale-layer tradeoff", tradeoff))
    return pairs


def validate_outline(outline: str, plan: dict) -> list[str]:
    """outline.md must show the route and every concept, and hide everything above the public layer."""
    errors: list[str] = []
    normalized = normalize_text(outline)
    if nonempty(plan.get("title")) and plan["title"] not in outline:
        errors.append(f"outline does not contain title '{plan['title']}'")
    mode = plan.get("mode")
    if mode and mode not in outline and {"full": "完整", "fast": "快速"}.get(mode, "") not in outline:
        errors.append("outline must state the learning mode")
    for index, section in enumerate(plan.get("sections", []) or []):
        if not isinstance(section, dict):
            continue
        if nonempty(section.get("title")) and section["title"] not in outline:
            errors.append(f"outline does not contain section title '{section['title']}'")
        for concept in section.get("concepts") or []:
            if isinstance(concept, dict) and nonempty(concept.get("name")) and normalize_text(concept["name"]) not in normalized:
                errors.append(f"outline does not list concept '{concept['name']}' of sections[{index}]")
        for label, text in hidden_texts(section):
            if criterion_leaked(text, normalized):
                errors.append(f"outline leaks {label} from sections[{index}]")
    if plan_shape(plan) == "skeleton":
        for item in plan.get("branch_candidates") or []:
            if isinstance(item, dict) and nonempty(item.get("title")) and normalize_text(item["title"]) not in normalized:
                errors.append(f"outline does not list branch candidate '{item['title']}'")
    return errors


def validate_units(units_dir: Path, plan: dict) -> tuple[list[str], list[str]]:
    """Each non-deferred section needs units/<id>.md with its title, checkpoint and every concept; no leaks."""
    errors: list[str] = []
    warnings: list[str] = []
    deferred = deferred_section_ids(plan)
    for index, section in enumerate(plan.get("sections", []) or []):
        if not isinstance(section, dict) or not nonempty(section.get("id")):
            continue
        path = units_dir / f"{section['id']}.md"
        if section["id"] in deferred:
            if path.exists():
                warnings.append(f"units/{section['id']}.md exists although the section is deferred")
            continue
        if not path.is_file():
            errors.append(f"missing unit document units/{section['id']}.md")
            continue
        text = path.read_text(encoding="utf-8")
        normalized = normalize_text(text)
        if nonempty(section.get("title")) and section["title"] not in text:
            errors.append(f"units/{section['id']}.md does not contain its title")
        if "轮到你" not in text and "Your turn" not in text and "Checkpoint" not in text:
            errors.append(f"units/{section['id']}.md must visibly include the learner checkpoint")
        checkpoint_prompt = (section.get("checkpoint") or {}).get("prompt") if isinstance(section.get("checkpoint"), dict) else None
        if nonempty(checkpoint_prompt) and not criterion_leaked(checkpoint_prompt, normalized):
            errors.append(f"units/{section['id']}.md does not contain its checkpoint.prompt (the visible question must be the checkpoint, not a rewrite)")
        probe_prompt = (section.get("probe") or {}).get("prompt") if isinstance(section.get("probe"), dict) else None
        if nonempty(probe_prompt) and criterion_leaked(probe_prompt, normalized):
            errors.append(f"units/{section['id']}.md contains the probe question; probes are asked no-hint before teaching and never printed in unit documents")
        for concept in section.get("concepts") or []:
            if isinstance(concept, dict) and nonempty(concept.get("name")) and normalize_text(concept["name"]) not in normalized:
                errors.append(f"units/{section['id']}.md does not mention concept '{concept['name']}'")
        if "想验收" in text or "说“验收" in text or '说"验收' in text:
            warnings.append(f"units/{section['id']}.md carries a '验收 X' reminder next to a supporting concept; that instruction belongs in outline.md only")
        for label, text_hidden in hidden_texts(section):
            if label.startswith("rationale-layer"):
                if criterion_leaked(text_hidden, normalized):
                    warnings.append(f"units/{section['id']}.md prints {label} verbatim; it should drive questions, not be shown")
            elif criterion_leaked(text_hidden, normalized):
                errors.append(f"units/{section['id']}.md leaks {label}")
    return errors, warnings


def sources_root_from_manifest(manifest_path: Path, manifest: Any) -> Path | None:
    """Material root recorded in sources.json: base_path relative to the manifest's own directory.
    "." (legacy: relative to whatever cwd was at generation) cannot be resolved and yields None."""
    if not isinstance(manifest, dict):
        return None
    base = manifest.get("base_path")
    if not nonempty(base) or base.strip() == ".":
        return None
    candidate = Path(base).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_path.resolve().parent / candidate
    return candidate.resolve()


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
    normalized_guide = normalize_text(guide)
    for field in (plan.get("title"), *(section.get("title") for section in plan.get("sections", []) if isinstance(section, dict))):
        if nonempty(field) and field not in guide:
            errors.append(f"teaching guide does not contain title '{field}'")
    if "轮到你" not in guide and "Your turn" not in guide and "Checkpoint" not in guide:
        errors.append("teaching guide must visibly include at least one learner checkpoint")
    for index, section in enumerate(plan.get("sections", [])):
        if not isinstance(section, dict):
            continue
        for criterion in criteria_texts(section.get("checkpoint")):
            if nonempty(criterion) and criterion_leaked(criterion, normalized_guide):
                errors.append(
                    f"teaching guide leaks assessment criterion from sections[{index}]: '{criterion}'"
                )
        principle = section.get("principle")
        if nonempty(principle) and criterion_leaked(principle, normalized_guide):
            errors.append(f"teaching guide leaks principle-layer content from sections[{index}]")
    return errors


def guide_warnings(guide: str, plan: dict) -> list[str]:
    """Advisories for 1.1 guides: meaning/tradeoffs belong to the rationale layer and should
    feed questions rather than be printed. Verbatim copies are reported, not failed."""
    warnings: list[str] = []
    if schema_version(plan) == "1.0":
        return warnings
    normalized_guide = normalize_text(guide)
    for index, section in enumerate(plan.get("sections", [])):
        if not isinstance(section, dict):
            continue
        if nonempty(section.get("meaning")) and criterion_leaked(section["meaning"], normalized_guide):
            warnings.append(f"sections[{index}].meaning appears verbatim in the guide; rationale-layer text should drive questions, not be shown")
        for tradeoff in section.get("tradeoffs") or []:
            if nonempty(tradeoff) and criterion_leaked(tradeoff, normalized_guide):
                warnings.append(f"sections[{index}] tradeoff appears verbatim in the guide: '{tradeoff}'")
    return warnings


LEAK_MIN_CHARS = 12
LEAK_WINDOW_CHARS = 16
NORMALIZE_STRIP = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Casefold and drop whitespace/punctuation so cosmetic rewording does not hide a leak."""
    return NORMALIZE_STRIP.sub("", text).casefold()


def criterion_leaked(criterion: str, normalized_guide: str) -> bool:
    """Guardrail, not a proof: catches verbatim and near-verbatim copies.

    A criterion counts as leaked when its normalized form appears in the guide,
    or when a long enough contiguous window of it does (so splitting a criterion
    across two sentences or changing punctuation does not evade the check).
    Paraphrase remains undetectable by construction; that judgment stays with
    the model and the author.
    """
    normalized = normalize_text(criterion)
    if len(normalized) < LEAK_MIN_CHARS:
        return bool(normalized) and normalized in normalized_guide
    if normalized in normalized_guide:
        return True
    if len(normalized) <= LEAK_WINDOW_CHARS:
        return False
    return any(
        normalized[start : start + LEAK_WINDOW_CHARS] in normalized_guide
        for start in range(0, len(normalized) - LEAK_WINDOW_CHARS + 1)
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lesson_plan", type=Path)
    parser.add_argument("--guide", type=Path, help="teaching-guide.md (schema 1.0/1.1 packs)")
    parser.add_argument("--outline", type=Path, help="outline.md (schema 1.2+ packs)")
    parser.add_argument("--units-dir", type=Path, help="units/ directory (schema 1.2+ packs)")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sources-root", type=Path, help="Material root for the coverage check; defaults to sources.json base_path (relative to the pack)")
    parser.add_argument("--allow-empty-coverage", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.lesson_plan)
        manifest = load_json(args.manifest) if args.manifest else None
        paths = manifest_paths(manifest) if manifest is not None else None
        sources_root = args.sources_root
        if sources_root is None:
            manifest_path = args.manifest or (args.lesson_plan.parent / "sources.json")
            if manifest_path.is_file():
                sources_root = sources_root_from_manifest(manifest_path, manifest if manifest is not None else load_json(manifest_path))
                if sources_root is not None:
                    print(f"INFO: sources root {sources_root} (from {manifest_path.name} base_path)")
        errors = validate_plan(plan, paths, allow_empty_coverage=args.allow_empty_coverage)
        warnings = collect_warnings(plan)
        if args.guide:
            guide = args.guide.read_text(encoding="utf-8")
            errors.extend(validate_guide(guide, plan))
            warnings.extend(guide_warnings(guide, plan))
        if args.outline:
            errors.extend(validate_outline(args.outline.read_text(encoding="utf-8"), plan))
        if args.units_dir:
            unit_errors, unit_warnings = validate_units(args.units_dir, plan)
            errors.extend(unit_errors)
            warnings.extend(unit_warnings)
        if sources_root and schema_version(plan) in ROLE_AWARE_VERSIONS:
            errors.extend(validate_coverage_against_sources(plan, sources_root))
        if plan_shape(plan) == "skeleton":
            g = grounding(plan)
            print(f"INFO: grounding {g['anchored']}/{g['total']} core+supporting concepts anchored in the evidence pool "
                  f"({g['external']} external, {g['no_anchor']} no-anchor) — no threshold; the learner judges")
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
